"""Documents API routes for listing and browsing documents."""

import logging
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.acl.dependencies import get_entitlements
from app.acl.models import DocumentACL, Entitlements
from app.acl.postgres_filter import ACLPostgresFilter
from app.config import get_settings
from app.db.session import get_session
from app.db.models import Document, IngestJob, DocumentIR, Chunk, VectorIndexVersion, EmbeddingJob
from app.db.graph_models import DocumentGraph, Node, Edge, NodeType, EdgeType, ContentRegistry
from app.services.document_identity import find_legacy_for_graph
from app.services.highlighting import (
    build_source_manifest,
    ensure_highlight_artifacts,
)
from app.storage.minio_client import get_storage_client
from app.graph.vector_index import GraphVectorIndex

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/v1/documents", tags=["documents"])


# ============================================
# Response Models
# ============================================

class DocumentResponse(BaseModel):
    """Response model for a single document."""
    doc_id: str
    source_uri: str
    content_hash: str
    version: int
    ingested_at: datetime
    doc_summary_md: Optional[str] = None
    doc_summary_text: Optional[str] = None
    canonical_doc_id: Optional[str] = None
    embedded_collection_version: Optional[str] = None
    doc_date: Optional[str] = None
    year: Optional[int] = None
    source_system: Optional[str] = None
    doc_type: Optional[str] = None
    department: Optional[str] = None
    authority_tier: Optional[int] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    supersedes_doc_id: Optional[str] = None
    node_count: Optional[int] = None
    visibility: Optional[str] = None
    processing_status: Optional[str] = None
    processing_stage: Optional[str] = None
    processing_error: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Response model for document list."""
    items: List[DocumentResponse]
    total: int
    page: int
    limit: int
    has_more: bool


class NodeResponse(BaseModel):
    """Response model for a single node."""
    node_id: str
    doc_id: str
    version: int
    node_type: str
    page_no: Optional[int] = None
    chunk_index_in_page: Optional[int] = None
    label: Optional[str] = None
    caption_md: Optional[str] = None
    text_md: Optional[str] = None
    text_plain: Optional[str] = None
    bbox: Optional[dict] = None
    content_hash: Optional[str] = None
    meta: Optional[dict] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class NodeListResponse(BaseModel):
    """Response model for node list."""
    items: List[NodeResponse]
    total: int
    page: int
    limit: int
    has_more: bool


class EdgeResponse(BaseModel):
    """Response model for a single edge."""
    id: int
    doc_id: str
    version: int
    from_node_id: str
    to_node_id: str
    edge_type: str
    confidence: Optional[float] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class EdgeListResponse(BaseModel):
    """Response model for edge list."""
    items: List[EdgeResponse]
    total: int


class DocumentStatsResponse(BaseModel):
    """Response model for document statistics."""
    total_documents: int
    total_nodes: int
    total_edges: int
    by_type: dict
    by_department: dict
    by_year: dict


class SourceManifestResponse(BaseModel):
    """Source/selector artifact availability for citation highlighting."""

    doc_id: str
    version: int
    raw_url: str
    mime_type: str
    canonical_view_available: bool
    source_map_available: bool
    selectors_available: bool
    selector_coverage: dict
    backfill_needed: bool


# ============================================
# Helpers
# ============================================

def _check_doc_access(
    doc: DocumentGraph,
    entitlements: Optional[Entitlements],
) -> None:
    """Check if user can access a single document. Raises 404 or 403."""
    if entitlements is None:
        return  # ACL disabled
    acl = DocumentACL.from_db_row(doc)
    if acl.permits(entitlements):
        return
    settings = get_settings()
    if settings.acl_disclosure_mode == "opaque":
        raise HTTPException(status_code=404, detail=f"Document {doc.doc_id} not found")
    else:
        raise HTTPException(status_code=403, detail="Access denied")


def _infer_media_type(filename: str, explicit_content_type: Optional[str]) -> str:
    """Best-effort media type resolution for raw document responses."""
    if explicit_content_type:
        return explicit_content_type
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _resolve_processing_state(
    ingest_job: Optional[IngestJob],
    embed_job: Optional[EmbeddingJob],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return a unified processing state across ingest and embedding jobs.

    Precedence:
    1. Ingest failure or active ingest always wins.
    2. Embedding status is used once ingest has completed.
    3. Completed ingest with no embed job is reported as pending embedding.
    """
    if ingest_job and ingest_job.status in {"failed", "pending", "processing", "queued"}:
        return ingest_job.status, ingest_job.pipeline_stage, ingest_job.error

    if embed_job:
        return embed_job.status, embed_job.pipeline_stage, embed_job.error

    if ingest_job:
        if ingest_job.status == "completed":
            return "pending", "awaiting_embedding", None
        return ingest_job.status, ingest_job.pipeline_stage, ingest_job.error

    return None, None, None


# ============================================
# Routes
# ============================================

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    doc_type: Optional[str] = Query(default=None, description="Filter by document type"),
    department: Optional[str] = Query(default=None, description="Filter by department"),
    authority_tier: Optional[int] = Query(default=None, ge=1, le=3, description="Filter by authority tier"),
    year: Optional[int] = Query(default=None, description="Filter by year"),
    search: Optional[str] = Query(default=None, description="Search in source_uri"),
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> DocumentListResponse:
    """List all documents with optional filtering and pagination."""

    # Build query
    query = db.query(DocumentGraph)

    # ACL filter (always applied before other filters)
    query = ACLPostgresFilter.document_filter(query, entitlements)

    # Apply filters
    if doc_type:
        query = query.filter(DocumentGraph.doc_type == doc_type)
    if department:
        query = query.filter(DocumentGraph.department == department)
    if authority_tier:
        query = query.filter(DocumentGraph.authority_tier == authority_tier)
    if year:
        query = query.filter(DocumentGraph.year == year)
    if search:
        query = query.filter(DocumentGraph.source_uri.ilike(f"%{search}%"))
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    documents = query.order_by(desc(DocumentGraph.ingested_at)).offset(offset).limit(limit).all()
    
    # Get node counts for each document
    doc_ids = [doc.doc_id for doc in documents]
    node_counts = {}
    if doc_ids:
        counts = db.query(
            Node.doc_id, func.count(Node.node_id)
        ).filter(Node.doc_id.in_(doc_ids)).group_by(Node.doc_id).all()
        node_counts = {doc_id: count for doc_id, count in counts}

    # Get latest embedding job per document for processing status/error visibility
    latest_embed_by_doc: dict[str, EmbeddingJob] = {}
    if doc_ids:
        embed_jobs = (
            db.query(EmbeddingJob)
            .filter(EmbeddingJob.doc_id.in_(doc_ids))
            .order_by(EmbeddingJob.doc_id.asc(), EmbeddingJob.created_at.desc())
            .all()
        )
        for job in embed_jobs:
            if job.doc_id and job.doc_id not in latest_embed_by_doc:
                latest_embed_by_doc[job.doc_id] = job

    # Get latest ingest job per graph document for unified processing status.
    latest_ingest_by_doc: dict[str, IngestJob] = {}
    if doc_ids:
        ingest_jobs = (
            db.query(IngestJob)
            .filter(
                or_(
                    IngestJob.graph_doc_id.in_(doc_ids),
                    IngestJob.doc_id.in_(doc_ids),
                )
            )
            .order_by(desc(IngestJob.created_at))
            .all()
        )
        for job in ingest_jobs:
            candidate_doc_id = job.graph_doc_id or job.doc_id
            if candidate_doc_id and candidate_doc_id in doc_ids and candidate_doc_id not in latest_ingest_by_doc:
                latest_ingest_by_doc[candidate_doc_id] = job
    
    # Build response
    items = []
    for doc in documents:
        latest_embed = latest_embed_by_doc.get(doc.doc_id)
        latest_ingest = latest_ingest_by_doc.get(doc.doc_id)
        processing_status, processing_stage, processing_error = _resolve_processing_state(
            ingest_job=latest_ingest,
            embed_job=latest_embed,
        )
        item = DocumentResponse(
            doc_id=doc.doc_id,
            source_uri=doc.source_uri,
            content_hash=doc.content_hash,
            version=doc.version,
            ingested_at=doc.ingested_at,
            doc_summary_md=doc.doc_summary_md,
            doc_summary_text=doc.doc_summary_text,
            canonical_doc_id=doc.canonical_doc_id,
            embedded_collection_version=doc.embedded_collection_version,
            doc_date=str(doc.doc_date) if doc.doc_date else None,
            year=doc.year,
            source_system=doc.source_system,
            doc_type=doc.doc_type,
            department=doc.department,
            authority_tier=doc.authority_tier,
            effective_from=str(doc.effective_from) if doc.effective_from else None,
            effective_to=str(doc.effective_to) if doc.effective_to else None,
            supersedes_doc_id=doc.supersedes_doc_id,
            node_count=node_counts.get(doc.doc_id, 0),
            visibility=doc.visibility,
            processing_status=processing_status,
            processing_stage=processing_stage,
            processing_error=processing_error,
        )
        items.append(item)
    
    return DocumentListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=offset + len(documents) < total,
    )


@router.get("/stats", response_model=DocumentStatsResponse)
async def get_document_stats(
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> DocumentStatsResponse:
    """Get document statistics (scoped by ACL)."""

    # Helper to build a fresh ACL-scoped DocumentGraph query
    def _acl_query():
        return ACLPostgresFilter.document_filter(db.query(DocumentGraph), entitlements)

    accessible_ids = {row.doc_id for row in _acl_query().with_entities(DocumentGraph.doc_id).all()}

    total_documents = len(accessible_ids)
    if accessible_ids:
        total_nodes = db.query(func.count(Node.node_id)).filter(Node.doc_id.in_(accessible_ids)).scalar() or 0
        total_edges = db.query(func.count(Edge.id)).filter(Edge.doc_id.in_(accessible_ids)).scalar() or 0
    else:
        total_nodes = 0
        total_edges = 0

    # By type
    type_counts = _acl_query().with_entities(
        DocumentGraph.doc_type, func.count(DocumentGraph.doc_id)
    ).filter(DocumentGraph.doc_type.isnot(None)).group_by(DocumentGraph.doc_type).all()
    by_type = {t or "unknown": c for t, c in type_counts}

    # By department
    dept_counts = _acl_query().with_entities(
        DocumentGraph.department, func.count(DocumentGraph.doc_id)
    ).filter(DocumentGraph.department.isnot(None)).group_by(DocumentGraph.department).all()
    by_department = {d or "unknown": c for d, c in dept_counts}

    # By year
    year_counts = _acl_query().with_entities(
        DocumentGraph.year, func.count(DocumentGraph.doc_id)
    ).filter(DocumentGraph.year.isnot(None)).group_by(DocumentGraph.year).all()
    by_year = {y: c for y, c in year_counts if y}
    
    return DocumentStatsResponse(
        total_documents=total_documents,
        total_nodes=total_nodes,
        total_edges=total_edges,
        by_type=by_type,
        by_department=by_department,
        by_year=by_year,
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> DocumentResponse:
    """Get a single document by ID."""

    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()

    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    _check_doc_access(doc, entitlements)
    
    # Get node count
    node_count = db.query(func.count(Node.node_id)).filter(Node.doc_id == doc_id).scalar() or 0
    latest_embed = (
        db.query(EmbeddingJob)
        .filter(EmbeddingJob.doc_id == doc_id)
        .order_by(desc(EmbeddingJob.created_at))
        .first()
    )
    latest_ingest = (
        db.query(IngestJob)
        .filter(
            or_(
                IngestJob.graph_doc_id == doc_id,
                IngestJob.doc_id == doc_id,
            )
        )
        .order_by(desc(IngestJob.created_at))
        .first()
    )
    processing_status, processing_stage, processing_error = _resolve_processing_state(
        ingest_job=latest_ingest,
        embed_job=latest_embed,
    )
    
    return DocumentResponse(
        doc_id=doc.doc_id,
        source_uri=doc.source_uri,
        content_hash=doc.content_hash,
        version=doc.version,
        ingested_at=doc.ingested_at,
        doc_summary_md=doc.doc_summary_md,
        doc_summary_text=doc.doc_summary_text,
        canonical_doc_id=doc.canonical_doc_id,
        embedded_collection_version=doc.embedded_collection_version,
        doc_date=str(doc.doc_date) if doc.doc_date else None,
        year=doc.year,
        source_system=doc.source_system,
        doc_type=doc.doc_type,
        department=doc.department,
        authority_tier=doc.authority_tier,
        effective_from=str(doc.effective_from) if doc.effective_from else None,
        effective_to=str(doc.effective_to) if doc.effective_to else None,
        supersedes_doc_id=doc.supersedes_doc_id,
        node_count=node_count,
        visibility=doc.visibility,
        processing_status=processing_status,
        processing_stage=processing_stage,
        processing_error=processing_error,
    )


@router.get("/{doc_id}/nodes", response_model=NodeListResponse)
async def list_document_nodes(
    doc_id: str,
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=50, ge=1, le=200, description="Items per page"),
    node_type: Optional[str] = Query(default=None, description="Filter by node type (chunk, figure, table, page)"),
    page_no: Optional[int] = Query(default=None, description="Filter by page number"),
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> NodeListResponse:
    """List nodes for a specific document."""

    # Verify document exists and user has access
    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    _check_doc_access(doc, entitlements)
    
    # Build query
    query = db.query(Node).filter(Node.doc_id == doc_id)
    
    # Apply filters
    if node_type:
        try:
            nt = NodeType(node_type)
            query = query.filter(Node.node_type == nt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid node type: {node_type}")
    if page_no is not None:
        query = query.filter(Node.page_no == page_no)
    
    # Get total count
    total = query.count()
    
    # Apply pagination and ordering
    offset = (page - 1) * limit
    nodes = query.order_by(Node.page_no, Node.chunk_index_in_page).offset(offset).limit(limit).all()
    
    # Build response
    items = []
    for node in nodes:
        items.append(NodeResponse(
            node_id=node.node_id,
            doc_id=node.doc_id,
            version=node.version,
            node_type=node.node_type.value,
            page_no=node.page_no,
            chunk_index_in_page=node.chunk_index_in_page,
            label=node.label,
            caption_md=node.caption_md,
            text_md=node.text_md,
            text_plain=node.text_plain,
            bbox=node.bbox,
            content_hash=node.content_hash,
            meta=node.meta,
            created_at=node.created_at,
        ))
    
    return NodeListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        has_more=offset + len(nodes) < total,
    )


@router.get("/{doc_id}/edges", response_model=EdgeListResponse)
async def list_document_edges(
    doc_id: str,
    edge_type: Optional[str] = Query(default=None, description="Filter by edge type"),
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> EdgeListResponse:
    """List edges for a specific document."""

    # Verify document exists and user has access
    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    _check_doc_access(doc, entitlements)
    
    # Build query
    query = db.query(Edge).filter(Edge.doc_id == doc_id)
    
    # Apply filters
    if edge_type:
        try:
            et = EdgeType(edge_type)
            query = query.filter(Edge.edge_type == et)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid edge type: {edge_type}")
    
    # Get all edges (no pagination for edges)
    edges = query.all()
    
    # Build response
    items = []
    for edge in edges:
        items.append(EdgeResponse(
            id=edge.id,
            doc_id=edge.doc_id,
            version=edge.version,
            from_node_id=edge.from_node_id,
            to_node_id=edge.to_node_id,
            edge_type=edge.edge_type.value,
            confidence=edge.confidence,
            created_at=edge.created_at,
        ))
    
    return EdgeListResponse(
        items=items,
        total=len(items),
    )


@router.get("/{doc_id}/source-manifest", response_model=SourceManifestResponse)
async def get_source_manifest(
    doc_id: str,
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> SourceManifestResponse:
    """Return source + selector artifact availability for a document."""
    settings = get_settings()
    if not settings.enable_cross_format_highlighting:
        raise HTTPException(status_code=404, detail="Cross-format highlighting is disabled")

    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    _check_doc_access(doc, entitlements)

    legacy_doc = find_legacy_for_graph(db, doc.doc_id, doc.version)
    mime_type = legacy_doc.mime_type if legacy_doc else None

    storage = get_storage_client()
    manifest = build_source_manifest(storage, doc, mime_type=mime_type)

    # Lazy backfill on first request if artifacts are missing.
    if manifest.get("backfill_needed"):
        try:
            ensure_highlight_artifacts(db=db, doc=doc, storage=storage)
            manifest = build_source_manifest(storage, doc, mime_type=mime_type)
        except Exception as e:
            logger.warning(f"[{doc_id}] Highlight artifact backfill failed: {e}")

    return SourceManifestResponse(**manifest)


@router.get("/{doc_id}/canonical")
async def get_canonical_document_view(
    doc_id: str,
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> Response:
    """Return canonical HTML view used for cross-format highlighting."""
    settings = get_settings()
    if not settings.enable_cross_format_highlighting:
        raise HTTPException(status_code=404, detail="Cross-format highlighting is disabled")

    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    _check_doc_access(doc, entitlements)

    storage = get_storage_client()
    if not storage.canonical_view_exists(doc.doc_id, str(doc.version)):
        try:
            ensure_highlight_artifacts(db=db, doc=doc, storage=storage)
        except Exception as e:
            logger.warning(f"[{doc_id}] Failed to backfill canonical view: {e}")

    if not storage.canonical_view_exists(doc.doc_id, str(doc.version)):
        raise HTTPException(status_code=404, detail="Canonical view not available for this document")

    html_view = storage.get_canonical_view(doc.doc_id, str(doc.version))
    return Response(
        content=html_view,
        media_type="text/html",
        headers={
            "Cache-Control": "public, max-age=300",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{doc_id}/source-map")
async def get_document_source_map(
    doc_id: str,
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> JSONResponse:
    """Return canonical source map for selector-based citation highlighting."""
    settings = get_settings()
    if not settings.enable_cross_format_highlighting:
        raise HTTPException(status_code=404, detail="Cross-format highlighting is disabled")

    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    _check_doc_access(doc, entitlements)

    storage = get_storage_client()
    if not storage.source_map_exists(doc.doc_id, str(doc.version)):
        try:
            ensure_highlight_artifacts(db=db, doc=doc, storage=storage)
        except Exception as e:
            logger.warning(f"[{doc_id}] Failed to backfill source map: {e}")

    if not storage.source_map_exists(doc.doc_id, str(doc.version)):
        raise HTTPException(status_code=404, detail="Source map not available for this document")

    source_map = storage.get_source_map(doc.doc_id, str(doc.version))
    return JSONResponse(content=source_map)


@router.get("/{doc_id}/raw")
async def get_raw_document(
    doc_id: str,
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> Response:
    """Get raw document bytes for viewing/highlighting.

    This endpoint enables the frontend PDF viewer to load and display
    the original document for citation highlighting.

    Returns:
        Raw file bytes with the best available content-type
    """
    # 1. Look up document
    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()

    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    # ACL check — raw document access is the "often-missed" vulnerability
    _check_doc_access(doc, entitlements)
    
    # 2. Try to get raw file bytes
    raw_bytes = None
    filename = "document.bin"
    content_type: Optional[str] = None
    
    # Strategy 1: Try local file path (for file:// URIs)
    if doc.source_uri and doc.source_uri.startswith("file://"):
        file_path = doc.source_uri.replace("file://", "")
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    raw_bytes = f.read()
                filename = Path(file_path).name
                content_type = _infer_media_type(filename, None)
                logger.info(f"[{doc_id}] Loaded raw file from local path: {file_path}")
            except Exception as e:
                logger.warning(f"[{doc_id}] Failed to read local file: {e}")
    
    # Strategy 2: Try MinIO storage with graph doc_id
    if raw_bytes is None:
        try:
            storage = get_storage_client()
            raw_files = storage.list_raw_files(doc_id, str(doc.version))
            if raw_files:
                filename = raw_files[0]
                raw_bytes, content_type = storage.get_raw_with_content_type(
                    doc_id,
                    str(doc.version),
                    filename,
                )
                logger.info(f"[{doc_id}] Loaded raw file from MinIO (graph identity): {filename}")
        except Exception as e:
            logger.warning(f"[{doc_id}] Failed to get from MinIO with graph doc_id: {e}")
    
    # Strategy 3: Try MinIO via explicit legacy mapping (preferred for uploads)
    if raw_bytes is None:
        try:
            legacy_doc = find_legacy_for_graph(db, doc.doc_id, doc.version)
            if not legacy_doc and doc.source_uri:
                legacy_doc = db.query(Document).filter(Document.source_uri == doc.source_uri).first()
            if legacy_doc:
                storage = get_storage_client()
                raw_files = storage.list_raw_files(legacy_doc.doc_id, legacy_doc.version_id)
                if raw_files:
                    filename = raw_files[0]
                    raw_bytes, stored_content_type = storage.get_raw_with_content_type(
                        legacy_doc.doc_id,
                        legacy_doc.version_id,
                        filename,
                    )
                    content_type = legacy_doc.mime_type or stored_content_type
                    logger.info(
                        f"[{doc_id}] Loaded raw file via legacy mapping: "
                        f"{legacy_doc.doc_id}/{legacy_doc.version_id}/{filename}"
                    )
        except Exception as e:
            logger.warning(f"[{doc_id}] Failed to get from MinIO via legacy mapping: {e}")
    
    # Strategy 4: Try upload:// URI pattern directly with graph doc_id
    if raw_bytes is None and doc.source_uri and doc.source_uri.startswith("upload://"):
        upload_filename = doc.source_uri.replace("upload://", "")
        try:
            storage = get_storage_client()
            raw_bytes, content_type = storage.get_raw_with_content_type(
                doc_id,
                str(doc.version),
                upload_filename,
            )
            filename = upload_filename
            logger.info(f"[{doc_id}] Loaded raw file from MinIO upload fallback: {filename}")
        except Exception as e:
            logger.warning(f"[{doc_id}] Failed to get upload from MinIO: {e}")
    
    if raw_bytes is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Raw file not found for document {doc_id}. Source: {doc.source_uri}"
        )
    
    content_type = _infer_media_type(filename, content_type)

    # 3. Return with type-aware headers
    return Response(
        content=raw_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
        }
    )


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> None:
    """Delete a document and all associated data.

    Removes data from:
    - PostgreSQL (graph tables + legacy tables)
    - Milvus (vector embeddings)
    - MinIO (file artifacts)
    - ContentRegistry (deduplication tracking)
    """
    # 1. Verify document exists and check ACL
    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    _check_doc_access(doc, entitlements)

    version = doc.version
    content_hash = doc.content_hash
    source_uri = doc.source_uri

    # 2. Delete from Milvus (all collection versions)
    for coll_version in ["v1", "v2", "v3"]:
        try:
            vector_index = GraphVectorIndex(collection_version=coll_version)
            vector_index.delete_by_doc(doc_id, version)
        except Exception as e:
            logger.warning(f"[{doc_id}] Milvus {coll_version} delete: {e}")

    # 3. Delete from MinIO
    storage = get_storage_client()
    try:
        storage.delete_document(doc_id, str(version))
    except Exception as e:
        logger.warning(f"[{doc_id}] MinIO delete: {e}")

    # 4. Delete legacy tables (prefer explicit graph identity mapping)
    legacy_doc = find_legacy_for_graph(db, doc_id, version)
    if not legacy_doc:
        legacy_doc = db.query(Document).filter(Document.source_uri == source_uri).first()

    # Always clean graph-keyed background job/index rows.
    db.query(VectorIndexVersion).filter(
        VectorIndexVersion.doc_id == doc_id,
        VectorIndexVersion.version_id == str(version),
    ).delete()
    db.query(EmbeddingJob).filter(EmbeddingJob.doc_id == doc_id).delete()
    db.query(IngestJob).filter(
        IngestJob.graph_doc_id == doc_id,
        IngestJob.graph_version == version,
    ).delete()

    if legacy_doc:
        legacy_id = legacy_doc.doc_id
        db.query(VectorIndexVersion).filter(VectorIndexVersion.doc_id == legacy_id).delete()
        db.query(EmbeddingJob).filter(EmbeddingJob.doc_id == legacy_id).delete()
        db.query(Chunk).filter(Chunk.doc_id == legacy_id).delete()
        db.query(DocumentIR).filter(DocumentIR.doc_id == legacy_id).delete()
        db.query(IngestJob).filter(IngestJob.doc_id == legacy_id).delete()
        db.delete(legacy_doc)
        # Also clean MinIO with legacy doc_id
        try:
            storage.delete_document(legacy_id, legacy_doc.version_id)
        except Exception:
            pass

    # 5. Delete DocumentGraph (CASCADE deletes nodes + edges)
    db.delete(doc)

    # 6. Update ContentRegistry
    registry = db.query(ContentRegistry).filter(
        ContentRegistry.content_hash == content_hash
    ).first()
    if registry:
        if registry.canonical_doc_id == doc_id:
            if registry.alias_count <= 1:
                db.delete(registry)
            else:
                # Find another doc with same content to become canonical
                other = db.query(DocumentGraph).filter(
                    DocumentGraph.content_hash == content_hash,
                    DocumentGraph.doc_id != doc_id
                ).first()
                if other:
                    registry.canonical_doc_id = other.doc_id
                    registry.alias_count -= 1
                else:
                    db.delete(registry)
        else:
            registry.alias_count = max(1, registry.alias_count - 1)

    db.commit()
    logger.info(f"[{doc_id}] Document deleted successfully")
