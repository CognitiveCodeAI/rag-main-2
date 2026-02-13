"""Full ingestion pipeline for graph RAG.

Orchestrates:
1. Document registration + idempotency check
2. Page extraction (native text + OCR fallback)
3. Metadata extraction (date, type, department, authority)
4. Page-bounded chunking
5. Figure/table detection + OCR
6. Node creation (chunks + figures) with metadata propagation
7. Edge creation (adjacency + references + explained_by)
8. Database persistence with health metrics
"""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

from sqlalchemy.orm import Session

from app.db.graph_models import DocumentGraph, Node, Edge, NodeType, ContentRegistry
from app.metadata.extractor import MetadataExtractor, ExtractedMetadata
from app.ocr import get_ocr_client, OCRClient
from app.storage.minio_client import get_storage_client
from app.services.highlighting import (
    build_selector_artifacts_for_nodes,
    hydrate_nodes_with_selectors,
    persist_highlight_artifacts,
)

from .ids import compute_doc_id, compute_content_hash, IdempotencyChecker
from .content_registry import ContentRegistryManager
from .page_extractor import PageExtractor, ExtractionResult
from .chunker import PageBoundedChunker
from .figure_detector import FigureDetector
from .nodes import create_chunk_nodes, create_figure_nodes, create_figure_nodes_from_data
from .edges import create_all_edges
from .figure_detector import FigureData

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result of document ingestion."""
    doc_id: str
    version: int
    source_uri: str
    is_new: bool  # False if idempotent (content already existed)
    total_pages: int
    total_chunks: int
    total_figures: int
    total_tables: int
    total_edges: int
    ocr_pages: int
    
    # Content identity
    canonical_doc_id: Optional[str] = None
    is_content_duplicate: bool = False  # True if same content exists under different doc_id
    
    # Metadata extraction results
    metadata_extracted: Optional[Dict[str, Any]] = None
    health_metrics: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> dict:
        return {
            'doc_id': self.doc_id,
            'version': self.version,
            'source_uri': self.source_uri,
            'is_new': self.is_new,
            'canonical_doc_id': self.canonical_doc_id,
            'is_content_duplicate': self.is_content_duplicate,
            'total_pages': self.total_pages,
            'total_chunks': self.total_chunks,
            'total_figures': self.total_figures,
            'total_tables': self.total_tables,
            'total_edges': self.total_edges,
            'ocr_pages': self.ocr_pages,
            'metadata_extracted': self.metadata_extracted,
            'health_metrics': self.health_metrics,
        }


class GraphIngestionPipeline:
    """Full pipeline for ingesting documents into graph RAG."""
    
    def __init__(
        self,
        db: Session,
        ocr_client: Optional[OCRClient] = None,
        skip_ocr: bool = False,
        enable_llm_metadata: bool = False,
        ingestion_backend: Optional[str] = None,
        filename: Optional[str] = None,
        source_type: str = "pdf",
        # OCR settings
        ocr_quality_threshold: Optional[float] = None,
        # ACL fields
        tenant_id: Optional[str] = None,
        visibility: Optional[str] = None,
        allowed_roles: Optional[List[str]] = None,
        allowed_groups: Optional[List[str]] = None,
        allowed_users: Optional[List[str]] = None,
    ):
        """Initialize pipeline.

        Args:
            db: Database session
            ocr_client: Optional OCR client (will create if None)
            skip_ocr: If True, skip OCR even for low-quality pages
            enable_llm_metadata: Enable LLM fallback for metadata extraction
            ingestion_backend: Optional backend override ("native" or "docling")
            filename: Original filename (used by Docling adapter)
            source_type: Document source type (pdf, docx, pptx, etc.)
            ocr_quality_threshold: OCR quality threshold override (uses runtime setting if None)
            tenant_id: Tenant ID for ACL (None = use default)
            visibility: Visibility tier: public|internal|restricted
            allowed_roles: Roles allowed access (for internal/restricted)
            allowed_groups: Groups allowed access
            allowed_users: Users allowed access (for restricted)
        """
        self.db = db
        self.ocr_client = ocr_client

        # Initialize components
        self.skip_ocr = skip_ocr
        self.page_extractor = PageExtractor(
            ocr_client=ocr_client,
            skip_ocr=skip_ocr,
            quality_threshold=ocr_quality_threshold
        )
        self.chunker = PageBoundedChunker()
        self.figure_detector = FigureDetector()
        self.idempotency = IdempotencyChecker(db)
        self.metadata_extractor = MetadataExtractor(enable_llm_fallback=enable_llm_metadata)
        self.content_registry = ContentRegistryManager(db)

        # Docling backend settings
        self.ingestion_backend = ingestion_backend
        self.filename = filename
        self.source_type = source_type

        # ACL settings
        self.tenant_id = tenant_id
        self.visibility = visibility or "public"
        self.allowed_roles = allowed_roles
        self.allowed_groups = allowed_groups
        self.allowed_users = allowed_users
    
    def ingest(
        self,
        pdf_bytes: bytes = None,
        source_uri: str = "",
        force_reprocess: bool = False,
        *,
        raw_bytes: bytes = None,
        stage_callback: Optional[callable] = None,
        metadata_overrides: Optional[Dict[str, Any]] = None,
    ) -> IngestionResult:
        """Ingest a document.

        Args:
            pdf_bytes: Raw file bytes (kept for backward compat)
            source_uri: Source URI (file path, URL, etc.)
            force_reprocess: If True, reprocess even if content exists
            raw_bytes: Alias for pdf_bytes (preferred for non-PDF documents)
            metadata_overrides: Optional user-edited metadata values to apply

        Returns:
            IngestionResult with details
        """
        # Support raw_bytes as alias for pdf_bytes
        if raw_bytes is not None and pdf_bytes is None:
            pdf_bytes = raw_bytes
        if pdf_bytes is None:
            raise ValueError("Either pdf_bytes or raw_bytes must be provided")
        # 1. Compute IDs
        doc_id = compute_doc_id(source_uri)
        content_hash = compute_content_hash(pdf_bytes)
        
        logger.info(f"Ingesting document: doc_id={doc_id}, uri={source_uri}")
        
        # 2. Idempotency check
        if not force_reprocess:
            exists, existing_version = self.idempotency.document_exists(doc_id, content_hash)
            if exists:
                logger.info(f"Document already exists: doc_id={doc_id}, version={existing_version}")
                # Return existing info without reprocessing
                return self._get_existing_result(doc_id, existing_version, source_uri)
        
        # 3. Resolve content identity (prevents logical duplicates across different paths)
        content_identity = self.content_registry.resolve_or_register(
            content_hash=content_hash,
            doc_id=doc_id,
            source_uri=source_uri,
            tenant_id=self.tenant_id,
        )
        canonical_doc_id = content_identity.canonical_doc_id
        
        # Handle content duplicate (alias) - skip node/edge creation, reuse canonical
        if content_identity.is_duplicate:
            logger.info(
                f"Content already exists under canonical_doc_id={canonical_doc_id}. "
                f"Creating alias record for doc_id={doc_id} (alias #{content_identity.alias_count}). "
                f"Skipping node/edge creation - will reuse canonical embeddings."
            )
            return self._create_alias_record(
                doc_id=doc_id,
                source_uri=source_uri,
                content_hash=content_hash,
                canonical_doc_id=canonical_doc_id,
                alias_count=content_identity.alias_count,
                pdf_bytes=pdf_bytes
            )
        
        # 4. Get next version (only for new canonical documents)
        version = self.idempotency.get_next_version(doc_id)
        
        logger.info(f"Processing new canonical document: doc_id={doc_id}, version={version}")
        
        # 5. Extract pages + figures via backend dispatch
        if stage_callback:
            stage_callback("extracting_content")
        extraction, figures, backend_used, docling_provenance = self._extract_content(
            pdf_bytes, doc_id
        )

        # 6. Extract metadata (deterministic first, LLM fallback optional)
        filename = self.filename or Path(source_uri).name
        metadata = self.metadata_extractor.extract(
            pdf_bytes=pdf_bytes,
            source_uri=source_uri,
            filename=filename
        )
        metadata = self._apply_metadata_overrides(metadata, metadata_overrides)
        logger.info(
            f"[{doc_id}] Metadata extracted: year={metadata.year}, "
            f"doc_type={metadata.doc_type}, department={metadata.department}"
        )

        # 7. Chunk pages (with bbox data for citation anchoring)
        if stage_callback:
            stage_callback("chunking")
        pages_for_chunking = [
            (p.page_no, p.text_plain) for p in extraction.pages
        ]
        chunks = self.chunker.chunk_pages(
            pages=pages_for_chunking,
            doc_id=doc_id,
            version=version,
            page_data_list=extraction.pages  # Pass full PageData for bbox extraction
        )

        # 8. Create nodes with metadata propagation
        if stage_callback:
            stage_callback("creating_nodes")
        # Prepare metadata fields to propagate to each node
        node_metadata_fields = {
            'year': metadata.year,
            'doc_type': metadata.doc_type,
            'department': metadata.department,
            'authority_tier': metadata.authority_tier,
        }

        chunk_nodes = create_chunk_nodes(
            chunks=chunks,
            doc_id=doc_id,
            version=version
        )

        # Create figure nodes: use appropriate function based on backend
        if backend_used == "docling":
            figure_nodes = create_figure_nodes_from_data(
                figures=figures,
                doc_id=doc_id,
                version=version,
            )
        else:
            figure_nodes = create_figure_nodes(
                figures=figures,
                pdf_bytes=pdf_bytes,
                doc_id=doc_id,
                version=version,
                ocr_client=self.ocr_client,
                skip_ocr=self.skip_ocr,
            )
        
        all_nodes = chunk_nodes + figure_nodes
        
        # Propagate metadata to all nodes
        self._propagate_metadata_to_nodes(all_nodes, node_metadata_fields)
        
        # 10. Build canonical highlighting selectors/artifacts
        highlight_artifacts: Optional[Dict[str, Any]] = None
        try:
            # Build selector bundles and attach to node.meta before persistence.
            temp_doc = DocumentGraph(
                doc_id=doc_id,
                source_uri=source_uri,
                content_hash=content_hash,
                version=version,
            )
            highlight_artifacts = build_selector_artifacts_for_nodes(
                doc=temp_doc,
                nodes=all_nodes,
                source_type=self.source_type,
                mime_type=None,
            )
            hydrate_nodes_with_selectors(all_nodes, highlight_artifacts["selectors"])
        except Exception as e:
            logger.warning(f"[{doc_id}] Failed to build highlight selectors during ingestion: {e}")
            highlight_artifacts = None

        # 11. Create edges
        edges = create_all_edges(
            nodes=all_nodes,
            doc_id=doc_id,
            version=version
        )
        
        # 12. Compute health metrics
        health_metrics = self._compute_health_metrics(all_nodes, metadata)
        
        # 13. Create document record with metadata
        doc_meta = extraction.to_meta()
        doc_meta['metadata'] = metadata.to_dict()
        doc_meta['health'] = health_metrics
        doc_meta['ingestion_backend'] = backend_used
        if highlight_artifacts:
            doc_meta["highlighting"] = {
                "normalization": "unicode_nfkc+ws_collapse",
                "nodes_with_selectors": highlight_artifacts.get("nodes_with_selectors", 0),
                "total_nodes": highlight_artifacts.get("total_nodes", 0),
            }
        if docling_provenance:
            doc_meta['docling'] = docling_provenance
        
        doc = DocumentGraph(
            doc_id=doc_id,
            source_uri=source_uri,
            content_hash=content_hash,
            version=version,
            meta=doc_meta,
            # Content identity - this doc is its own canonical
            canonical_doc_id=canonical_doc_id,
            # Metadata columns
            doc_date=metadata.doc_date,
            year=metadata.year,
            source_system=metadata.source_system,
            doc_type=metadata.doc_type,
            department=metadata.department,
            authority_tier=metadata.authority_tier,
            effective_from=metadata.effective_from,
            effective_to=metadata.effective_to,
            # ACL columns
            tenant_id=self.tenant_id,
            visibility=self.visibility,
            allowed_roles=self.allowed_roles,
            allowed_groups=self.allowed_groups,
            allowed_users=self.allowed_users,
            policy_version=1,
        )
        
        # 14. Persist to database
        if stage_callback:
            stage_callback("persisting")
        self._persist(doc, all_nodes, edges)

        # 15. Persist highlight artifacts to object storage (non-fatal)
        if highlight_artifacts:
            try:
                storage = get_storage_client()
                persist_highlight_artifacts(
                    storage=storage,
                    doc_id=doc_id,
                    version=version,
                    canonical_html=highlight_artifacts["canonical_html"],
                    source_map=highlight_artifacts["source_map"],
                    selectors=highlight_artifacts["selectors"],
                )
            except Exception as e:
                logger.warning(f"[{doc_id}] Failed to store highlight artifacts: {e}")
        
        # Count figures vs tables
        fig_count = sum(1 for n in figure_nodes if n.node_type == NodeType.figure)
        table_count = sum(1 for n in figure_nodes if n.node_type == NodeType.table)
        
        result = IngestionResult(
            doc_id=doc_id,
            version=version,
            source_uri=source_uri,
            is_new=True,
            total_pages=extraction.total_pages,
            total_chunks=len(chunk_nodes),
            total_figures=fig_count,
            total_tables=table_count,
            total_edges=len(edges),
            ocr_pages=extraction.ocr_pages,
            canonical_doc_id=canonical_doc_id,
            is_content_duplicate=False,
            metadata_extracted=metadata.to_dict(),
            health_metrics=health_metrics
        )
        
        # Detailed ingestion summary log
        logger.info(
            f"[{doc_id}] Ingestion complete (canonical): "
            f"pages={result.total_pages} (ocr={result.ocr_pages}), "
            f"chunks={result.total_chunks}, "
            f"figures={result.total_figures}, tables={result.total_tables}, "
            f"edges={result.total_edges}"
        )
        
        # Log edge breakdown
        from collections import Counter
        edge_types = Counter(e.edge_type.value for e in edges)
        logger.info(f"[{doc_id}] Edge breakdown: {dict(edge_types)}")
        
        return result
    
    def _extract_content(
        self,
        raw_bytes: bytes,
        doc_id: str,
    ) -> Tuple[ExtractionResult, List[FigureData], str, Optional[Dict[str, Any]]]:
        """Dispatch content extraction to the appropriate backend.

        Returns:
            Tuple of (extraction_result, figures, backend_used, docling_provenance)
        """
        from .backend_selector import resolve_backend
        from app.config import get_settings

        settings = get_settings()
        backend = resolve_backend(
            source_type=self.source_type,
            request_override=self.ingestion_backend,
        )

        if backend == "docling":
            try:
                from .docling_adapter import convert_with_docling

                extraction, figures, provenance = convert_with_docling(
                    raw_bytes=raw_bytes,
                    filename=self.filename or "document",
                    source_type=self.source_type,
                    doc_id=doc_id,
                    max_pages=settings.docling_max_pages,
                    max_file_size_mb=settings.docling_max_file_size_mb,
                )
                return extraction, figures, "docling", provenance

            except Exception as e:
                logger.warning(
                    f"[{doc_id}] Docling extraction failed, falling back to native: {e}"
                )
                # Fall through to native

        # Native backend
        extraction = self.page_extractor.extract_pages(
            pdf_bytes=raw_bytes,
            doc_id=doc_id,
        )
        figures = self.figure_detector.detect_in_document(
            pdf_bytes=raw_bytes,
            doc_id=doc_id,
        )
        return extraction, figures, "native", None

    @staticmethod
    def _coerce_iso_date(value: Any) -> Optional[date]:
        """Coerce user override values to date objects."""
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
        return None

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        """Coerce user override values to integers."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                return int(raw)
            except ValueError:
                return None
        return None

    def _apply_metadata_overrides(
        self,
        metadata: ExtractedMetadata,
        metadata_overrides: Optional[Dict[str, Any]],
    ) -> ExtractedMetadata:
        """Apply user overrides with precedence over extracted metadata."""
        if not metadata_overrides:
            return metadata

        allowed_fields = {
            "doc_date",
            "year",
            "source_system",
            "doc_type",
            "department",
            "authority_tier",
            "effective_from",
            "effective_to",
        }
        date_fields = {"doc_date", "effective_from", "effective_to"}
        int_fields = {"year", "authority_tier"}

        for field, raw_value in metadata_overrides.items():
            if field not in allowed_fields:
                continue

            value = raw_value
            if field in date_fields:
                value = self._coerce_iso_date(raw_value)
                if raw_value not in (None, "") and value is None:
                    logger.warning(f"Ignoring invalid date override for {field}: {raw_value!r}")
                    continue
            elif field in int_fields:
                value = self._coerce_int(raw_value)
                if raw_value not in (None, "") and value is None:
                    logger.warning(f"Ignoring invalid integer override for {field}: {raw_value!r}")
                    continue
            elif isinstance(raw_value, str):
                stripped = raw_value.strip()
                value = stripped or None

            setattr(metadata, field, value)
            metadata.provenance[field] = "user"
            metadata.confidence[field] = 1.0 if value is not None else 0.0

        if metadata.year is None and metadata.doc_date is not None:
            metadata.year = metadata.doc_date.year
            if "year" not in metadata_overrides:
                metadata.provenance["year"] = metadata.provenance.get("doc_date", "derived")
                metadata.confidence["year"] = metadata.confidence.get("doc_date", 0.5)

        # If user changed doc_type but left authority tier unset, infer it from doc_type.
        if metadata.authority_tier is None:
            self.metadata_extractor._infer_authority_tier(metadata)

        return metadata

    def _persist(
        self,
        doc: DocumentGraph,
        nodes: List[Node],
        edges: List[Edge]
    ) -> None:
        """Persist document, nodes, and edges to database.
        
        Args:
            doc: Document record
            nodes: Node records
            edges: Edge records
        """
        try:
            # Add document
            self.db.add(doc)
            self.db.flush()  # Get doc_id constraint check early
            
            # Add nodes
            for node in nodes:
                self.db.add(node)
            self.db.flush()  # Ensure nodes exist before edges
            
            # Add edges
            for edge in edges:
                self.db.add(edge)
            
            self.db.commit()
            
            logger.info(f"Persisted: 1 doc, {len(nodes)} nodes, {len(edges)} edges")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to persist: {e}")
            raise
    
    def _propagate_metadata_to_nodes(
        self,
        nodes: List[Node],
        metadata_fields: Dict[str, Any]
    ) -> None:
        """Propagate document-level metadata to each node's meta field.
        
        Args:
            nodes: List of nodes to update
            metadata_fields: Metadata fields to propagate (year, doc_type, etc.)
        """
        for node in nodes:
            if node.meta is None:
                node.meta = {}
            
            # Add metadata fields to node.meta for fast access at retrieval time
            for key, value in metadata_fields.items():
                if value is not None:
                    node.meta[key] = value
    
    def _compute_health_metrics(
        self,
        nodes: List[Node],
        metadata: ExtractedMetadata
    ) -> Dict[str, Any]:
        """Compute metadata completeness health metrics.
        
        Args:
            nodes: All nodes in the document
            metadata: Extracted document metadata
            
        Returns:
            Health metrics dictionary
        """
        total_nodes = len(nodes)
        if total_nodes == 0:
            return {
                'metadata_completeness': {
                    'year_set': metadata.year is not None,
                    'doc_type_set': metadata.doc_type is not None,
                    'department_set': metadata.department is not None,
                    'nodes_with_year_pct': 0.0,
                    'nodes_with_section_hint_pct': 0.0,
                }
            }
        
        # Count nodes with metadata
        nodes_with_year = sum(
            1 for n in nodes 
            if n.meta and n.meta.get('year') is not None
        )
        nodes_with_section_hint = sum(
            1 for n in nodes 
            if n.meta and n.meta.get('section_hint') is not None
        )
        
        return {
            'metadata_completeness': {
                'year_set': metadata.year is not None,
                'doc_type_set': metadata.doc_type is not None,
                'department_set': metadata.department is not None,
                'authority_tier_set': metadata.authority_tier is not None,
                'nodes_with_year_pct': round(100.0 * nodes_with_year / total_nodes, 1),
                'nodes_with_section_hint_pct': round(100.0 * nodes_with_section_hint / total_nodes, 1),
            }
        }
    
    def _get_existing_result(
        self,
        doc_id: str,
        version: int,
        source_uri: str
    ) -> IngestionResult:
        """Get result for existing document (idempotent case).
        
        Args:
            doc_id: Document ID
            version: Existing version
            source_uri: Source URI
            
        Returns:
            IngestionResult with existing info
        """
        # Query existing stats
        from sqlalchemy import func
        
        chunk_count = self.db.query(func.count(Node.node_id)).filter(
            Node.doc_id == doc_id,
            Node.version == version,
            Node.node_type == NodeType.chunk
        ).scalar() or 0
        
        fig_count = self.db.query(func.count(Node.node_id)).filter(
            Node.doc_id == doc_id,
            Node.version == version,
            Node.node_type == NodeType.figure
        ).scalar() or 0
        
        table_count = self.db.query(func.count(Node.node_id)).filter(
            Node.doc_id == doc_id,
            Node.version == version,
            Node.node_type == NodeType.table
        ).scalar() or 0
        
        edge_count = self.db.query(func.count(Edge.id)).filter(
            Edge.doc_id == doc_id,
            Edge.version == version
        ).scalar() or 0
        
        # Get doc meta for page count
        doc = self.db.query(DocumentGraph).filter(
            DocumentGraph.doc_id == doc_id,
            DocumentGraph.version == version
        ).first()
        
        total_pages = 0
        ocr_pages = 0
        if doc and doc.meta:
            total_pages = doc.meta.get('total_pages', 0)
            ocr_pages = doc.meta.get('ocr_pages', 0)
        
        return IngestionResult(
            doc_id=doc_id,
            version=version,
            source_uri=source_uri,
            is_new=False,
            total_pages=total_pages,
            total_chunks=chunk_count,
            total_figures=fig_count,
            total_tables=table_count,
            total_edges=edge_count,
            ocr_pages=ocr_pages
        )
    
    def _create_alias_record(
        self,
        doc_id: str,
        source_uri: str,
        content_hash: str,
        canonical_doc_id: str,
        alias_count: int,
        pdf_bytes: bytes
    ) -> IngestionResult:
        """Create an alias document record without duplicating nodes/edges.
        
        When content already exists under a different doc_id (canonical), we only
        store a document alias record pointing to the canonical. This avoids
        duplicate nodes, edges, and embeddings.
        
        Args:
            doc_id: New doc_id for this alias
            source_uri: Source URI of the alias
            content_hash: Content hash (same as canonical)
            canonical_doc_id: The canonical doc_id for this content
            alias_count: Current count of aliases
            pdf_bytes: PDF bytes (for metadata extraction only)
            
        Returns:
            IngestionResult marked as alias
        """
        # Get canonical document info
        canonical_doc = self.db.query(DocumentGraph).filter(
            DocumentGraph.doc_id == canonical_doc_id
        ).first()
        
        if not canonical_doc:
            raise RuntimeError(
                f"Canonical document {canonical_doc_id} not found for alias {doc_id}"
            )
        
        # Extract minimal metadata for the alias record
        filename = Path(source_uri).name
        metadata = self.metadata_extractor.extract(
            pdf_bytes=pdf_bytes,
            source_uri=source_uri,
            filename=filename
        )
        
        # Create alias document record (no nodes, no edges)
        alias_meta = {
            'is_alias': True,
            'canonical_doc_id': canonical_doc_id,
            'alias_number': alias_count,
            'metadata': metadata.to_dict(),
            # Copy page info from canonical
            'total_pages': canonical_doc.meta.get('total_pages', 0) if canonical_doc.meta else 0,
            'ocr_pages': canonical_doc.meta.get('ocr_pages', 0) if canonical_doc.meta else 0,
        }
        
        alias_doc = DocumentGraph(
            doc_id=doc_id,
            source_uri=source_uri,
            content_hash=content_hash,
            version=1,  # Aliases start at version 1
            meta=alias_meta,
            canonical_doc_id=canonical_doc_id,
            # Copy metadata from canonical for consistency
            doc_date=canonical_doc.doc_date,
            year=canonical_doc.year,
            source_system=metadata.source_system,  # Use alias's source system
            doc_type=canonical_doc.doc_type,
            department=canonical_doc.department,
            authority_tier=canonical_doc.authority_tier,
            effective_from=canonical_doc.effective_from,
            effective_to=canonical_doc.effective_to,
        )
        
        # Persist alias record (no nodes, no edges)
        self.db.add(alias_doc)
        self.db.commit()
        
        logger.info(
            f"[{doc_id}] Alias record created -> canonical={canonical_doc_id}. "
            f"No nodes/edges created (reusing canonical). Alias #{alias_count}."
        )
        
        # Return result indicating this is a content duplicate/alias
        return IngestionResult(
            doc_id=doc_id,
            version=1,
            source_uri=source_uri,
            is_new=True,  # The alias record is new
            total_pages=alias_meta['total_pages'],
            total_chunks=0,  # No new chunks - reusing canonical
            total_figures=0,  # No new figures - reusing canonical
            total_tables=0,   # No new tables - reusing canonical
            total_edges=0,    # No new edges - reusing canonical
            ocr_pages=alias_meta['ocr_pages'],
            canonical_doc_id=canonical_doc_id,
            is_content_duplicate=True,
            metadata_extracted=metadata.to_dict(),
            health_metrics={'alias': True, 'canonical_doc_id': canonical_doc_id}
        )
