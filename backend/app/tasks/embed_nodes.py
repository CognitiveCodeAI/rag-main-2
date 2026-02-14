"""Celery task for embedding and indexing graph nodes.

Generates embeddings for nodes (chunks, figures, tables) and indexes them
into the appropriate Milvus collections.

IMPORTANT: Collection version is EXPLICIT - v2 is the default and required.
Do not change this without understanding the schema differences.
V1 collections do not have metadata fields (year, doc_type, department, authority_tier).
V2 collections have these fields and are required for metadata-aware retrieval.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from celery import shared_task
from sqlalchemy.orm import Session

from app.worker import celery_app
from app.db.session import get_session, session_scope
from app.db.models import EmbeddingJob
from app.db.graph_models import DocumentGraph, Node, NodeType
from app.embeddings.client import EmbeddingClient
from app.graph.vector_index import GraphVectorIndex, VectorRecord, ACTIVE_COLLECTION_VERSION

logger = logging.getLogger(__name__)

# EXPLICIT: Default collection version for all embedding tasks
# Do not change to v1 - it lacks metadata fields required for filtering
EMBED_COLLECTION_VERSION = "v2"

# Guard: v1 is not allowed without explicit override
ALLOWED_COLLECTION_VERSIONS = {"v2"}


class CollectionVersionError(Exception):
    """Raised when an invalid collection version is used."""
    pass


def _validate_collection_version(version: str, allow_v1_override: bool = False) -> None:
    """Validate collection version.
    
    Args:
        version: Collection version to validate
        allow_v1_override: If True, allow v1 (for migration only)
        
    Raises:
        CollectionVersionError: If version is invalid
    """
    allowed = ALLOWED_COLLECTION_VERSIONS.copy()
    if allow_v1_override:
        allowed.add("v1")
    
    if version not in allowed:
        raise CollectionVersionError(
            f"Invalid collection version: {version}. "
            f"Allowed: {allowed}. "
            f"V1 requires explicit --allow-v1-override flag."
        )


def _update_doc_embedding_metadata(
    db: Session,
    doc_id: str,
    version: int,
    collection_version: str,
    embedding_model: str,
    embedding_dim: int
) -> None:
    """Update document with embedding metadata.
    
    Args:
        db: Database session
        doc_id: Document ID
        version: Document version
        collection_version: Milvus collection version used
        embedding_model: Embedding model name
        embedding_dim: Embedding dimension
    """
    doc = db.query(DocumentGraph).filter(
        DocumentGraph.doc_id == doc_id,
        DocumentGraph.version == version
    ).first()
    
    if doc:
        doc.embedded_collection_version = collection_version
        
        # Also store in meta for full audit trail
        if doc.meta is None:
            doc.meta = {}
        
        doc.meta["embedding_info"] = {
            "collection_version": collection_version,
            "embedding_model": embedding_model,
            "embedding_dim": embedding_dim,
        }
        
        db.commit()
        logger.info(
            f"[{doc_id}] Updated embedding metadata: "
            f"collection={collection_version}, model={embedding_model}, dim={embedding_dim}"
        )


def _resolve_final_status(total_indexed: int, errors: list[str]) -> tuple[str, Optional[str]]:
    """Resolve final embedding job status from indexed count and collected errors."""
    if total_indexed == 0:
        return "failed", "No vectors were indexed for this document."
    if errors:
        return "partial", "; ".join(errors)
    return "completed", None


@dataclass
class EmbedNodeResult:
    """Result from embedding a node."""
    node_id: str
    node_type: str
    success: bool
    error: Optional[str] = None


def get_node_text(node: Node) -> str:
    """Get the text to embed for a node.
    
    Args:
        node: Node object
        
    Returns:
        Text string to embed
    """
    # Use text_plain if available, otherwise text_md
    text = node.text_plain or node.text_md or ""
    
    # For figures/tables, include label and caption
    if node.node_type in (NodeType.figure, NodeType.table):
        parts = []
        if node.label:
            parts.append(node.label)
        if node.caption_md:
            parts.append(node.caption_md)
        if text:
            parts.append(text)
        text = "\n".join(parts)
    
    return text.strip()


@celery_app.task(bind=True, name="embed_nodes_task")
def embed_nodes_task(
    self,
    doc_id: str,
    version: int,
    node_types: Optional[List[str]] = None,
    collection_version: str = EMBED_COLLECTION_VERSION,
    allow_v1_override: bool = False,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Embed and index nodes for a document.

    Args:
        doc_id: Document ID
        version: Document version
        node_types: Node types to embed (default: all)
        collection_version: Milvus collection version (default: v2, EXPLICIT)
        allow_v1_override: Allow v1 collections (migration only, not recommended)
        job_id: Optional EmbeddingJob UUID for status tracking

    Returns:
        Dict with results summary

    Raises:
        CollectionVersionError: If collection_version is invalid
    """
    job_uuid = uuid.UUID(job_id) if job_id else None

    def _update_job(
        status: Optional[str] = None,
        stage: Optional[str] = None,
        error: Optional[str] = None,
        **extra_fields,
    ) -> None:
        """Update EmbeddingJob status and stage (best-effort)."""
        if not job_uuid:
            return
        try:
            with session_scope() as session:
                job = session.query(EmbeddingJob).filter_by(job_id=job_uuid).first()
                if job:
                    if status:
                        job.status = status
                    if stage:
                        job.pipeline_stage = stage
                    if error:
                        job.error = error
                    if status == "processing" and not job.started_at:
                        job.started_at = datetime.utcnow()
                    if status in ("completed", "failed", "partial", "skipped_alias"):
                        job.completed_at = datetime.utcnow()
                    for k, v in extra_fields.items():
                        if hasattr(job, k):
                            setattr(job, k, v)
        except Exception:
            logger.debug(f"[{doc_id}] Failed to update embed job (non-fatal)")

    # GUARD: Validate collection version before anything else
    _validate_collection_version(collection_version, allow_v1_override)

    logger.info(
        f"[{doc_id}] Starting node embedding task for version {version}, "
        f"collection_version={collection_version}, job_id={job_id}"
    )

    _update_job(status="processing", stage="loading_nodes")

    db = next(get_session())

    try:
        # GUARD: Check if this is an alias document (should reuse canonical embeddings)
        doc = db.query(DocumentGraph).filter(
            DocumentGraph.doc_id == doc_id,
            DocumentGraph.version == version
        ).first()

        if doc and doc.canonical_doc_id and doc.canonical_doc_id != doc_id:
            # This is an alias - skip embedding, should use canonical's embeddings
            logger.info(
                f"[{doc_id}] Skipping embedding - this is an alias of canonical_doc_id={doc.canonical_doc_id}. "
                f"Embeddings are reused from canonical document."
            )
            _update_job(status="skipped_alias", stage="complete")
            return {
                "status": "skipped_alias",
                "doc_id": doc_id,
                "canonical_doc_id": doc.canonical_doc_id,
                "reason": "Alias documents reuse embeddings from canonical document"
            }

        # Filter node types
        if node_types is None:
            types_to_embed = [NodeType.chunk, NodeType.figure, NodeType.table]
        else:
            types_to_embed = [NodeType(t) for t in node_types]

        # Get nodes
        nodes = db.query(Node).filter(
            Node.doc_id == doc_id,
            Node.version == version,
            Node.node_type.in_(types_to_embed)
        ).all()

        if not nodes:
            logger.warning(f"[{doc_id}] No nodes found to embed")
            _update_job(status="failed", stage="complete", error="No nodes found to embed")
            return {"status": "no_nodes", "doc_id": doc_id}

        logger.info(f"[{doc_id}] Found {len(nodes)} nodes to embed")
        _update_job(stage="generating_embeddings", chunk_count=len(nodes))

        # Group nodes by type
        nodes_by_type: Dict[NodeType, List[Node]] = {}
        for node in nodes:
            if node.node_type not in nodes_by_type:
                nodes_by_type[node.node_type] = []
            nodes_by_type[node.node_type].append(node)

        # Initialize clients with EXPLICIT collection version
        embed_client = EmbeddingClient()
        vector_index = GraphVectorIndex(collection_version=collection_version)

        # HEALTH CHECK: Verify v2 schema before embedding (fail fast if misconfigured)
        if collection_version == "v2":
            vector_index.verify_v2_schema()

        vector_index.ensure_collections()

        results = {
            "doc_id": doc_id,
            "version": version,
            "collection_version": collection_version,  # EXPLICIT tracking
            "total_nodes": len(nodes),
            "embedded": {},
            "indexed": {},
            "errors": []
        }

        total_tokens = 0

        # Process each node type
        for node_type, type_nodes in nodes_by_type.items():
            type_name = node_type.value

            logger.info(f"[{doc_id}] Embedding {len(type_nodes)} {type_name} nodes")

            # Get texts to embed
            texts = []
            valid_nodes = []

            for node in type_nodes:
                text = get_node_text(node)
                if text:
                    texts.append(text)
                    valid_nodes.append(node)
                else:
                    logger.warning(f"[{doc_id}] Skipping empty node {node.node_id}")

            if not texts:
                logger.warning(f"[{doc_id}] No valid texts for {type_name}")
                continue

            # Generate embeddings
            try:
                embeddings, embed_meta = embed_client.embed_texts(texts)
                results["embedded"][type_name] = len(embeddings)
                if embed_meta and isinstance(embed_meta, dict):
                    total_tokens += embed_meta.get("total_tokens", 0)
                logger.info(f"[{doc_id}] Generated {len(embeddings)} {type_name} embeddings, tokens={embed_meta.get('total_tokens', 0) if isinstance(embed_meta, dict) else embed_meta}")
            except Exception as e:
                logger.error(f"[{doc_id}] Embedding failed for {type_name}: {e}")
                results["errors"].append(f"Embedding {type_name}: {str(e)}")
                continue

            # Update progress
            total_embedded_so_far = sum(results["embedded"].values())
            _update_job(record_count=total_embedded_so_far, total_tokens=total_tokens)

            # Create vector records with metadata fields
            _update_job(stage="indexing_vectors")
            records = []
            for node, embedding in zip(valid_nodes, embeddings):
                # Extract metadata from node.meta (populated during ingestion)
                meta = node.meta or {}

                records.append(VectorRecord(
                    node_id=node.node_id,
                    doc_id=doc_id,
                    version=version,
                    page_no=node.page_no,
                    vector=embedding,
                    # V2 metadata fields (use sentinels if not present)
                    year=meta.get('year') or -1,
                    doc_type=meta.get('doc_type') or "",
                    department=meta.get('department') or "",
                    authority_tier=meta.get('authority_tier') or 0,
                ))

            # Index vectors
            try:
                indexed = vector_index.insert(type_name, records)
                results["indexed"][type_name] = indexed
                logger.info(f"[{doc_id}] Indexed {indexed} {type_name} vectors")
            except Exception as e:
                logger.error(f"[{doc_id}] Indexing failed for {type_name}: {e}")
                results["errors"].append(f"Indexing {type_name}: {str(e)}")

        # Summary
        total_embedded = sum(results["embedded"].values())
        total_indexed = sum(results["indexed"].values())

        logger.info(
            f"[{doc_id}] Node embedding complete: "
            f"embedded={total_embedded}, indexed={total_indexed}, "
            f"collection_version={collection_version}, "
            f"errors={len(results['errors'])}"
        )

        final_status, final_error = _resolve_final_status(total_indexed, results["errors"])
        if final_status == "failed":
            if not results["errors"] and final_error:
                results["errors"].append(final_error)
            logger.error(f"[{doc_id}] {final_error}")
        else:
            # Persist embedding metadata only when at least one vector has been indexed.
            _update_doc_embedding_metadata(
                db=db,
                doc_id=doc_id,
                version=version,
                collection_version=collection_version,
                embedding_model=embed_client.model,
                embedding_dim=embed_client.dim
            )
        results["status"] = final_status
        results["embedding_model"] = embed_client.model
        results["embedding_dim"] = embed_client.dim

        _update_job(
            status=final_status,
            stage="complete",
            error=final_error,
            record_count=total_embedded,
            total_tokens=total_tokens,
        )

        return results

    except Exception as e:
        logger.error(f"[{doc_id}] Node embedding task failed: {e}")
        _update_job(status="failed", stage="failed", error=str(e))
        raise

    finally:
        db.close()


def embed_document_nodes_sync(
    doc_id: str,
    version: int,
    db: Optional[Session] = None,
    collection_version: str = EMBED_COLLECTION_VERSION,
    allow_v1_override: bool = False
) -> Dict[str, Any]:
    """Synchronous version for testing/direct calls.
    
    Args:
        doc_id: Document ID
        version: Document version
        db: Optional database session
        collection_version: Milvus collection version (default: v2, EXPLICIT)
        allow_v1_override: Allow v1 collections (migration only, not recommended)
        
    Returns:
        Results dict
        
    Raises:
        CollectionVersionError: If collection_version is invalid
    """
    logger.info(f"[{doc_id}] embed_document_nodes_sync START")
    
    # GUARD: Validate collection version before anything else
    logger.info(f"[{doc_id}] Step 1: Validating collection version={collection_version}")
    _validate_collection_version(collection_version, allow_v1_override)
    
    should_close = False
    if db is None:
        logger.info(f"[{doc_id}] Step 2: Creating new DB session")
        db = next(get_session())
        should_close = True
    else:
        logger.info(f"[{doc_id}] Step 2: Using provided DB session")
    
    try:
        # GUARD: Check if this is an alias document (should reuse canonical embeddings)
        logger.info(f"[{doc_id}] Step 3: Checking for alias document")
        doc = db.query(DocumentGraph).filter(
            DocumentGraph.doc_id == doc_id,
            DocumentGraph.version == version
        ).first()
        
        if doc and doc.canonical_doc_id and doc.canonical_doc_id != doc_id:
            # This is an alias - skip embedding, should use canonical's embeddings
            logger.info(
                f"[{doc_id}] Skipping embedding - this is an alias of canonical_doc_id={doc.canonical_doc_id}. "
                f"Embeddings are reused from canonical document."
            )
            return {
                "status": "skipped_alias",
                "doc_id": doc_id,
                "canonical_doc_id": doc.canonical_doc_id,
                "reason": "Alias documents reuse embeddings from canonical document"
            }
        
        logger.info(f"[{doc_id}] Step 4: Querying nodes")
        nodes = db.query(Node).filter(
            Node.doc_id == doc_id,
            Node.version == version
        ).all()
        logger.info(f"[{doc_id}] Step 4: Found {len(nodes)} nodes")
        
        if not nodes:
            logger.info(f"[{doc_id}] No nodes found, returning early")
            return {"status": "no_nodes", "doc_id": doc_id}
        
        # Group by type
        logger.info(f"[{doc_id}] Step 5: Grouping nodes by type")
        nodes_by_type = {}
        for node in nodes:
            type_name = node.node_type.value
            if type_name not in nodes_by_type:
                nodes_by_type[type_name] = []
            nodes_by_type[type_name].append(node)
        logger.info(f"[{doc_id}] Step 5: Types found: {[(k, len(v)) for k, v in nodes_by_type.items()]}")
        
        # EXPLICIT: Use specified collection version
        logger.info(f"[{doc_id}] Step 6: Initializing EmbeddingClient")
        embed_client = EmbeddingClient()
        logger.info(f"[{doc_id}] Step 6: EmbeddingClient ready (model={embed_client.model})")
        
        logger.info(f"[{doc_id}] Step 7: Initializing GraphVectorIndex")
        vector_index = GraphVectorIndex(collection_version=collection_version)
        logger.info(f"[{doc_id}] Step 7: GraphVectorIndex ready")
        
        # HEALTH CHECK: Verify v2 schema before embedding (fail fast if misconfigured)
        if collection_version == "v2":
            logger.info(f"[{doc_id}] Step 8: Verifying v2 schema")
            vector_index.verify_v2_schema()
            logger.info(f"[{doc_id}] Step 8: v2 schema verified")
        
        logger.info(f"[{doc_id}] Step 9: Ensuring collections exist")
        vector_index.ensure_collections()
        logger.info(f"[{doc_id}] Step 9: Collections ensured")
        
        results = {
            "doc_id": doc_id,
            "version": version,
            "collection_version": collection_version,  # EXPLICIT tracking
            "embedded": {},
            "indexed": {},
        }
        
        for type_name, type_nodes in nodes_by_type.items():
            logger.info(f"[{doc_id}] Step 10: Processing type={type_name} ({len(type_nodes)} nodes)")
            
            texts = [get_node_text(n) for n in type_nodes if get_node_text(n)]
            valid_nodes = [n for n in type_nodes if get_node_text(n)]
            logger.info(f"[{doc_id}] Step 10a: {len(texts)} valid texts for {type_name}")
            
            if not texts:
                logger.info(f"[{doc_id}] Step 10b: No texts for {type_name}, skipping")
                continue
            
            logger.info(f"[{doc_id}] Step 11: Embedding {len(texts)} texts for {type_name}")
            embeddings, _ = embed_client.embed_texts(texts)
            results["embedded"][type_name] = len(embeddings)
            logger.info(f"[{doc_id}] Step 11: Got {len(embeddings)} embeddings")
            
            logger.info(f"[{doc_id}] Step 12: Creating VectorRecords for {type_name}")
            records = []
            for n, emb in zip(valid_nodes, embeddings):
                meta = n.meta or {}
                records.append(VectorRecord(
                    node_id=n.node_id,
                    doc_id=doc_id,
                    version=version,
                    page_no=n.page_no,
                    vector=emb,
                    # V2 metadata fields (required for v2 collections)
                    year=meta.get('year') or -1,
                    doc_type=meta.get('doc_type') or "",
                    department=meta.get('department') or "",
                    authority_tier=meta.get('authority_tier') or 0,
                ))
            logger.info(f"[{doc_id}] Step 12: Created {len(records)} records")
            
            logger.info(f"[{doc_id}] Step 13: Inserting into Milvus for {type_name}")
            indexed = vector_index.insert(type_name, records)
            results["indexed"][type_name] = indexed
            logger.info(f"[{doc_id}] Step 13: Indexed {indexed} vectors")
        
        total_indexed = sum(results["indexed"].values())
        errors = results.get("errors", [])
        final_status, final_error = _resolve_final_status(total_indexed, errors)
        if final_status == "failed":
            results.setdefault("errors", [])
            if final_error and final_error not in results["errors"]:
                results["errors"].append(final_error)
            logger.error(f"[{doc_id}] Step 14: {final_error}")
        else:
            # Persist embedding metadata to document only on successful index writes.
            logger.info(f"[{doc_id}] Step 14: Updating document embedding metadata")
            _update_doc_embedding_metadata(
                db=db,
                doc_id=doc_id,
                version=version,
                collection_version=collection_version,
                embedding_model=embed_client.model,
                embedding_dim=embed_client.dim
            )
            logger.info(f"[{doc_id}] Step 14: Metadata updated")

        results["status"] = final_status

        results["embedding_model"] = embed_client.model
        results["embedding_dim"] = embed_client.dim
        
        logger.info(f"[{doc_id}] embed_document_nodes_sync COMPLETE: {results}")
        return results
        
    except Exception as e:
        logger.error(f"[{doc_id}] embed_document_nodes_sync FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise
        
    finally:
        if should_close:
            logger.info(f"[{doc_id}] Closing DB session")
            db.close()
