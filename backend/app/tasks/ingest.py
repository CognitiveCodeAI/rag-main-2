"""Document ingestion task.

This module provides Celery tasks for document ingestion using the Graph Pipeline.
The Graph Pipeline creates DocumentGraph, Node, and Edge entries that are used
by the QA system for retrieval and citation.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from app.worker import celery_app
from app.db.session import session_scope
from app.db.models import IngestJob
from app.storage.minio_client import get_storage_client
from app.graph.pipeline import GraphIngestionPipeline

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def ingest_document_task(
    self,
    job_id: str,
    doc_id: str,
    version_id: str,
    filename: str,
    source_type: str,
    ingestion_backend: str | None = None,
    # ACL fields (passed through to pipeline)
    tenant_id: str | None = None,
    visibility: str | None = None,
    allowed_roles: list[str] | None = None,
    allowed_groups: list[str] | None = None,
    allowed_users: list[str] | None = None,
) -> dict[str, Any]:
    """Process a document through the Graph Ingestion Pipeline.

    This task uses GraphIngestionPipeline which:
    1. Parses documents with bbox extraction for highlighting
    2. Creates chunks with bounding box metadata
    3. Creates DocumentGraph, Node, Edge entries for QA system
    4. Supports content deduplication
    5. Optionally uses Docling for multi-format conversion

    Args:
        job_id: Ingest job UUID
        doc_id: Document ID (used as hint, pipeline may generate different canonical ID)
        version_id: Version ID
        filename: Original filename
        source_type: Document type (pdf, docx, pptx, etc.)
        ingestion_backend: Optional backend override ("native" or "docling")

    Returns:
        Dict with job status and results
    """
    storage = get_storage_client()
    job_uuid = uuid.UUID(job_id)

    def _update_stage(stage: str) -> None:
        """Update pipeline_stage on the IngestJob for granular progress."""
        try:
            with session_scope() as session:
                job = session.query(IngestJob).filter_by(job_id=job_uuid).first()
                if job:
                    job.pipeline_stage = stage
        except Exception:
            logger.debug(f"Failed to update stage to {stage} (non-fatal)")

    try:
        # Update job status to processing
        with session_scope() as session:
            job = session.query(IngestJob).filter_by(job_id=job_uuid).first()
            if job:
                job.status = "processing"
                job.pipeline_stage = "retrieving_file"
                job.started_at = datetime.utcnow()

        logger.info(f"Starting Graph ingestion: job={job_id}, doc={doc_id}")

        # 1. Get raw document from MinIO
        raw_bytes = storage.get_raw(doc_id, version_id, filename)
        logger.info(f"Retrieved raw document: {len(raw_bytes)} bytes")

        # 2. Build source URI for the document
        source_uri = f"upload://{filename}"

        # 2b. Resolve ingestion backend
        _update_stage("resolving_backend")
        from app.graph.backend_selector import resolve_backend
        resolved_backend = resolve_backend(
            source_type=source_type,
            request_override=ingestion_backend,
        )
        logger.info(f"Resolved ingestion backend: {resolved_backend} (request={ingestion_backend})")

        # 3. Run Graph Ingestion Pipeline
        with session_scope() as db:
            pipeline = GraphIngestionPipeline(
                db,
                skip_ocr=True,
                ingestion_backend=resolved_backend,
                filename=filename,
                source_type=source_type,
                tenant_id=tenant_id,
                visibility=visibility,
                allowed_roles=allowed_roles,
                allowed_groups=allowed_groups,
                allowed_users=allowed_users,
            )

            result = pipeline.ingest(
                pdf_bytes=raw_bytes,
                source_uri=source_uri,
                stage_callback=_update_stage,
            )
            
            logger.info(f"Graph ingestion complete: doc_id={result.doc_id}")
            logger.info(f"  Pages: {result.total_pages}")
            logger.info(f"  Chunks: {result.total_chunks}")
            logger.info(f"  Figures: {result.total_figures}")
            logger.info(f"  Tables: {result.total_tables}")
            logger.info(f"  Is duplicate: {result.is_content_duplicate}")
            
            # Store the actual doc_id from the pipeline (may differ from input)
            actual_doc_id = result.doc_id
        
        # 4. Update job status to completed
        # NOTE: We don't update job.doc_id because ingest_jobs has FK to legacy 'documents' table
        # The actual_doc_id is stored in DocumentGraph, not documents
        with session_scope() as session:
            job = session.query(IngestJob).filter_by(job_id=job_uuid).first()
            if job:
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                if job.doc_id != actual_doc_id:
                    logger.info(f"Graph doc_id differs from job doc_id: {job.doc_id} -> {actual_doc_id} (not updating job due to FK constraint)")
        
        logger.info(f"Ingestion completed: job={job_id}")
        
        return {
            "status": "completed",
            "job_id": job_id,
            "doc_id": actual_doc_id,
            "version_id": version_id,
            "chunk_count": result.total_chunks,
            "page_count": result.total_pages,
            "figure_count": result.total_figures,
            "table_count": result.total_tables,
            "is_duplicate": result.is_content_duplicate,
        }
    
    except Exception as e:
        logger.error(f"Ingestion failed: job={job_id}, error={e}", exc_info=True)
        
        # Update job status to failed
        try:
            with session_scope() as session:
                job = session.query(IngestJob).filter_by(job_id=job_uuid).first()
                if job:
                    job.status = "failed"
                    job.error = str(e)
                    job.completed_at = datetime.utcnow()
        except Exception:
            pass
        
        # Retry with exponential backoff
        try:
            self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            return {
                "status": "failed",
                "job_id": job_id,
                "error": str(e),
            }
