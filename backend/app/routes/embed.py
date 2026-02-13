"""Embedding API endpoints.

This module provides API endpoints for embedding documents using the Graph Pipeline.
The Graph Pipeline creates embeddings for nodes (chunks, figures, tables) and indexes
them into Milvus for vector search.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.session import session_scope
from app.db.models import EmbeddingJob
from app.db.graph_models import DocumentGraph, Node
from app.services.document_identity import resolve_for_embed
from app.services.worker_health import inspect_celery_workers
from app.storage.minio_client import get_storage_client
from app.tasks.embed_nodes import embed_nodes_task

router = APIRouter(prefix="/v1/embed", tags=["embedding"])


class EmbedDocumentRequest(BaseModel):
    """Request to embed a document."""
    doc_id: str = Field(..., min_length=1, description="Document ID")
    version_id: str = Field(..., min_length=1, description="Version ID (e.g., 'v20240101' or '1')")


class EmbedDocumentResponse(BaseModel):
    """Response for embedding request."""
    job_id: str
    doc_id: str
    version_id: str
    status: str


class EmbedJobStatusResponse(BaseModel):
    """Response for embedding job status."""
    job_id: str
    doc_id: str
    version_id: str
    status: str
    pipeline_stage: Optional[str] = None
    error: Optional[str] = None
    chunk_count: Optional[int] = None
    record_count: Optional[int] = None
    total_tokens: Optional[int] = None
    bundle_uri: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


@router.post("/document", response_model=EmbedDocumentResponse)
async def embed_document(request: EmbedDocumentRequest) -> EmbedDocumentResponse:
    """Trigger embedding generation for a document.
    
    Queues an async task to generate embeddings for all nodes (chunks, figures, tables)
    in the specified document and index them into Milvus.
    
    Args:
        request: Embedding request with doc_id and version_id
    
    Returns:
        Job tracking info
    """
    # Resolve request identity to canonical graph doc/version.
    with session_scope() as session:
        resolved = resolve_for_embed(
            session,
            requested_doc_id=request.doc_id,
            requested_version_id=request.version_id,
        )
        if not resolved:
            raise HTTPException(
                status_code=404,
                detail=f"Document not found: {request.doc_id} version {request.version_id}. "
                       "Ingest the document first."
            )
        actual_doc_id = resolved.graph_doc_id
        version = resolved.graph_version

        doc = session.query(DocumentGraph).filter(
            DocumentGraph.doc_id == actual_doc_id,
            DocumentGraph.version == version
        ).first()
        if not doc:
            raise HTTPException(
                status_code=404,
                detail=f"Document not found: {actual_doc_id} version {version}. Ingest the document first."
            )

        node_count = session.query(Node).filter(
            Node.doc_id == actual_doc_id,
            Node.version == version
        ).count()
        
        if node_count == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No nodes found for {actual_doc_id} version {version}. "
                       "Ingest the document first."
            )

    worker_status = inspect_celery_workers(timeout=1.0)
    if not worker_status.healthy:
        raise HTTPException(
            status_code=503,
            detail=(
                "Embedding queue is unavailable. "
                f"{worker_status.message} Start a Celery worker and retry."
            ),
        )

    # Create embedding job record
    with session_scope() as session:
        job = EmbeddingJob(
            doc_id=actual_doc_id,
            version_id=str(version),
            status="pending",
        )
        session.add(job)
        session.flush()
        job_id = str(job.job_id)
    
    # Queue Graph embedding task with actual graph doc_id
    embed_nodes_task.delay(actual_doc_id, version, job_id=job_id)
    
    return EmbedDocumentResponse(
        job_id=job_id,
        doc_id=actual_doc_id,
        version_id=str(version),
        status="queued",
    )


@router.get("/job/{job_id}", response_model=EmbedJobStatusResponse)
async def get_embed_job_status(job_id: str) -> EmbedJobStatusResponse:
    """Get the status of an embedding job.
    
    Args:
        job_id: Job UUID
    
    Returns:
        Job status details
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    with session_scope() as session:
        job = session.query(EmbeddingJob).filter_by(job_id=job_uuid).first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return EmbedJobStatusResponse(
            job_id=str(job.job_id),
            doc_id=job.doc_id,
            version_id=job.version_id,
            status=job.status,
            pipeline_stage=job.pipeline_stage,
            error=job.error,
            chunk_count=job.chunk_count,
            record_count=job.record_count,
            total_tokens=job.total_tokens,
            bundle_uri=job.bundle_uri,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
        )


@router.get("/document/{doc_id}/{version_id}/status")
async def get_document_embed_status(doc_id: str, version_id: str) -> dict:
    """Get embedding status for a document version.
    
    Returns info about whether embeddings exist and are indexed.
    """
    storage = get_storage_client()
    
    # Check if bundle exists
    bundle_exists = False
    bundle_info = None
    try:
        bundle = storage.get_embeddings(doc_id, version_id)
        bundle_exists = True
        bundle_info = {
            "bundle_version": bundle.get("bundle_version"),
            "record_count": bundle.get("record_count"),
            "model_id": bundle.get("model_id"),
            "created_at": bundle.get("created_at"),
        }
    except Exception:
        pass
    
    # Check index status
    from app.db.models import VectorIndexVersion
    
    index_status = {}
    with session_scope() as session:
        records = session.query(VectorIndexVersion).filter_by(
            doc_id=doc_id,
            version_id=version_id,
        ).all()
        
        for record in records:
            index_status[record.collection_name] = {
                "bundle_version": record.bundle_version,
                "vector_count": record.vector_count,
                "indexed_at": record.indexed_at.isoformat() if record.indexed_at else None,
            }
    
    return {
        "doc_id": doc_id,
        "version_id": version_id,
        "bundle_exists": bundle_exists,
        "bundle_info": bundle_info,
        "index_status": index_status,
    }


class EmbedJobListResponse(BaseModel):
    """Response for embedding job list query."""
    items: list[EmbedJobStatusResponse]
    total: int
    page: int
    limit: int
    has_more: bool


@router.get("/jobs", response_model=EmbedJobListResponse)
async def list_embed_jobs(
    status: Optional[str] = None,
    doc_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) -> EmbedJobListResponse:
    """List embedding jobs with optional filtering.
    
    Args:
        status: Optional status filter (pending, queued, processing, completed, failed, partial, skipped_alias)
        doc_id: Optional document ID filter
        page: Page number (default 1)
        limit: Items per page (default 20, max 100)
    
    Returns:
        EmbedJobListResponse with paginated jobs
    """
    if limit > 100:
        limit = 100
    
    with session_scope() as session:
        query = session.query(EmbeddingJob)
        
        if status:
            query = query.filter(EmbeddingJob.status == status)
        if doc_id:
            query = query.filter(EmbeddingJob.doc_id == doc_id)
        
        total = query.count()
        
        offset = (page - 1) * limit
        jobs = query.order_by(EmbeddingJob.created_at.desc()).offset(offset).limit(limit).all()
        
        items = [
            EmbedJobStatusResponse(
                job_id=str(job.job_id),
                doc_id=job.doc_id,
                version_id=job.version_id,
                status=job.status,
                pipeline_stage=job.pipeline_stage,
                error=job.error,
                chunk_count=job.chunk_count,
                record_count=job.record_count,
                total_tokens=job.total_tokens,
                bundle_uri=job.bundle_uri,
                started_at=job.started_at,
                completed_at=job.completed_at,
                created_at=job.created_at,
            )
            for job in jobs
        ]
        
        return EmbedJobListResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
            has_more=offset + len(jobs) < total,
        )
