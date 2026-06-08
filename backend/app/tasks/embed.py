"""Embedding Celery task."""

import logging
from datetime import datetime
from typing import Any

from app.worker import celery_app
from app.observability.tasking import enqueue
from app.storage.minio_client import get_storage_client
from app.embeddings.client import EmbeddingClient
from app.embeddings.vector_record import MultiViewVectorRecordBuilder

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def embed_chunks_task(
    self,
    doc_id: str,
    version_id: str,
    chunk_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Generate embeddings for document chunks.
    
    Steps:
    1. Load chunks from MinIO
    2. Optionally load IR for context
    3. Render all 4 views per chunk
    4. Batch embed via OpenAI
    5. Build MultiViewVectorRecords
    6. Save bundle to MinIO
    7. Queue index task
    
    Args:
        doc_id: Document ID
        version_id: Version ID
        chunk_ids: Optional list of specific chunk IDs (all if None)
    
    Returns:
        Dict with status and results
    """
    storage = get_storage_client()
    
    try:
        logger.info(f"Starting embedding: doc={doc_id}, version={version_id}")
        
        # 1. Load chunks from MinIO
        if not storage.chunks_exist(doc_id, version_id):
            raise ValueError(f"Chunks not found: {doc_id}/{version_id}")
        
        all_chunks = storage.get_chunks(doc_id, version_id)
        logger.info(f"Loaded {len(all_chunks)} chunks")
        
        # Filter to specific chunk_ids if provided
        if chunk_ids:
            chunks = [
                c for c in all_chunks 
                if c.get("chunk_ref", {}).get("chunk_id") in chunk_ids
            ]
            logger.info(f"Filtered to {len(chunks)} chunks")
        else:
            chunks = all_chunks
        
        if not chunks:
            return {
                "status": "completed",
                "doc_id": doc_id,
                "version_id": version_id,
                "chunk_count": 0,
                "message": "No chunks to embed",
            }
        
        # 2. Optionally load IR for context
        ir = None
        if storage.ir_exists(doc_id, version_id):
            ir = storage.get_ir(doc_id, version_id)
            logger.info("Loaded IR for context")
        
        # 3-5. Build embedding bundle (renders, embeds, builds records)
        builder = MultiViewVectorRecordBuilder()
        bundle = builder.build_bundle(chunks, ir)
        
        # 6. Save bundle to MinIO
        bundle_uri = storage.put_embeddings(doc_id, version_id, bundle)
        logger.info(f"Stored bundle: {bundle_uri}")
        
        # 7. Queue index task
        from app.tasks.index import index_vectors_task
        enqueue(index_vectors_task, doc_id, version_id)
        logger.info("Queued index task")
        
        return {
            "status": "completed",
            "doc_id": doc_id,
            "version_id": version_id,
            "chunk_count": len(chunks),
            "record_count": bundle.get("record_count", 0),
            "total_tokens": bundle.get("total_tokens", 0),
            "bundle_uri": bundle_uri,
        }
    
    except Exception as e:
        logger.error(f"Embedding failed: doc={doc_id}, error={e}")
        
        # Retry with exponential backoff
        try:
            self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            return {
                "status": "failed",
                "doc_id": doc_id,
                "version_id": version_id,
                "error": str(e),
            }


@celery_app.task(bind=True)
def embed_document_task(
    self,
    doc_id: str,
    version_id: str,
) -> dict[str, Any]:
    """Wrapper task to embed all chunks for a document.
    
    This is the main entry point for document embedding.
    """
    return embed_chunks_task(doc_id, version_id, chunk_ids=None)
