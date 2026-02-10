"""Document ingestion API endpoints."""

import hashlib
import json
import mimetypes
import uuid
from datetime import datetime
from typing import Optional

import fitz  # PyMuPDF, used to pre-validate PDF uploads
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func as sa_func

from app.config import get_settings
from app.db.graph_models import ContentRegistry, DocumentGraph, Node
from app.db.models import Document, IngestJob
from app.db.session import session_scope
from app.graph.backend_selector import get_supported_types
from app.storage.minio_client import get_storage_client
from app.tasks.ingest import ingest_document_task

router = APIRouter(prefix="/v1/ingest", tags=["ingestion"])


# Request/Response models
class IngestResponse(BaseModel):
    """Response for document ingestion request."""
    job_id: str
    doc_id: str
    version_id: str
    status: str


class JobStatusResponse(BaseModel):
    """Response for job status query."""
    job_id: str
    doc_id: Optional[str]
    status: str
    pipeline_stage: Optional[str] = None
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


# Source type mapping from MIME types
MIME_TO_SOURCE_TYPE = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "docx",
    "text/html": "html",
    "text/markdown": "md",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.ms-powerpoint": "pptx",
}

# Extension mapping
EXT_TO_SOURCE_TYPE = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".html": "html",
    ".htm": "html",
    ".md": "md",
    ".markdown": "md",
    ".txt": "txt",
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".pptx": "pptx",
    ".ppt": "pptx",
}


def detect_source_type(filename: str, content_type: Optional[str]) -> str:
    """Detect document source type from filename and content type."""
    # Try extension first
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        if ext in EXT_TO_SOURCE_TYPE:
            return EXT_TO_SOURCE_TYPE[ext]
    
    # Try MIME type
    if content_type and content_type in MIME_TO_SOURCE_TYPE:
        return MIME_TO_SOURCE_TYPE[content_type]
    
    # Try guessing from filename
    guessed_type, _ = mimetypes.guess_type(filename)
    if guessed_type and guessed_type in MIME_TO_SOURCE_TYPE:
        return MIME_TO_SOURCE_TYPE[guessed_type]
    
    return "txt"  # Default to plain text


def generate_doc_id(content: bytes, filename: str) -> str:
    """Generate a stable document ID from content hash."""
    content_hash = hashlib.sha256(content).hexdigest()[:16]
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")[:32]
    return f"{safe_name}-{content_hash}"


def generate_version_id() -> str:
    """Generate a version ID (timestamp + random)."""
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    rand = uuid.uuid4().hex[:8]
    return f"v{ts}-{rand}"


@router.post("/document", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile = File(...),
    source_type: Optional[str] = Form(None),
    doc_id: Optional[str] = Form(None),
    ingestion_backend: Optional[str] = Form(None),
    # ACL fields (optional — used when ACL_ENABLED=true)
    tenant_id: Optional[str] = Form(None),
    visibility: Optional[str] = Form(None),
    allowed_roles: Optional[str] = Form(None),    # JSON array string e.g. '["analyst"]'
    allowed_groups: Optional[str] = Form(None),   # JSON array string
    allowed_users: Optional[str] = Form(None),    # JSON array string
) -> IngestResponse:
    """Ingest a document for processing.
    
    Accepts a file upload and queues it for async processing.
    
    Args:
        file: Uploaded document file
        source_type: Optional source type override (pdf, docx, pptx, html, md, txt, csv, xlsx)
        doc_id: Optional document ID override (auto-generated if not provided)
        ingestion_backend: Optional backend override ("native" or "docling")
    
    Returns:
        IngestResponse with job tracking info
    """
    # Read file content
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Fast fail on invalid PDF bytes (most common failure)
    if (file.content_type or "").lower() in ("application/pdf", "pdf") or (file.filename or "").lower().endswith(".pdf"):
        try:
            # Will raise if stream is not a valid PDF
            with fitz.open(stream=content, filetype="pdf"):
                pass
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF file. Please upload a valid, non-corrupted PDF.",
            )

    # Fail fast before writing any objects/rows when embedding prerequisites are missing.
    # The current product flow is ingest -> embed immediately, so missing embedding config
    # would create partial state (raw file + graph rows + failed embed job).
    settings = get_settings()
    missing = settings.validate_required_for_embeddings()
    if missing:
        raise HTTPException(
            status_code=503,
            detail=(
                "Embedding service is not configured. "
                f"Missing required settings: {', '.join(missing)}"
            ),
        )
    
    filename = file.filename or "document"
    
    # Detect source type
    detected_type = source_type or detect_source_type(filename, file.content_type)
    
    # Validate source type against currently-supported types
    supported = get_supported_types()
    if detected_type not in supported:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type: {detected_type}. "
                f"Currently supported: {sorted(supported)}. "
                "Enable the Docling backend for additional format support."
            ),
        )

    # Validate ingestion_backend if provided
    if ingestion_backend is not None and ingestion_backend not in ("native", "docling"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ingestion_backend: {ingestion_backend}. Must be 'native' or 'docling'."
        )
    
    # Generate IDs
    doc_id = doc_id or generate_doc_id(content, filename)
    version_id = generate_version_id()
    
    # Get checksum
    checksum = hashlib.sha256(content).hexdigest()

    # --- Duplicate detection: check if this content was already ingested ---
    with session_scope() as session:
        existing = session.query(ContentRegistry).filter_by(content_hash=checksum).first()
        if existing:
            # Fetch the canonical document's details
            canon_doc = session.query(DocumentGraph).filter_by(
                doc_id=existing.canonical_doc_id
            ).first()
            existing_info = {
                "doc_id": existing.canonical_doc_id,
                "content_hash": checksum,
            }
            if canon_doc:
                node_count = (
                    session.query(sa_func.count(Node.node_id))
                    .filter(Node.doc_id == canon_doc.doc_id)
                    .scalar() or 0
                )
                existing_info.update({
                    "source_uri": canon_doc.source_uri,
                    "ingested_at": canon_doc.ingested_at.isoformat() if canon_doc.ingested_at else None,
                    "node_count": node_count,
                    "doc_type": canon_doc.doc_type,
                })
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "duplicate",
                    "message": "This document has already been ingested.",
                    "existing_document": existing_info,
                },
            )

    # Store raw file in MinIO
    storage = get_storage_client()
    storage.put_raw(
        doc_id=doc_id,
        version_id=version_id,
        content=content,
        filename=filename,
        content_type=file.content_type,
    )
    
    # Create database records
    with session_scope() as session:
        # Create or update document record
        doc = Document(
            doc_id=doc_id,
            version_id=version_id,
            source_type=detected_type,
            source_uri=f"upload://{filename}",
            mime_type=file.content_type,
            checksum=checksum,
        )
        session.merge(doc)
        
        # Create ingest job
        job = IngestJob(
            doc_id=doc_id,
            status="pending",
        )
        session.add(job)
        session.flush()
        job_id = str(job.job_id)
    
    # Parse ACL JSON fields
    def _parse_json_list(raw: Optional[str]) -> Optional[list]:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    parsed_roles = _parse_json_list(allowed_roles)
    parsed_groups = _parse_json_list(allowed_groups)
    parsed_users = _parse_json_list(allowed_users)

    # Validate visibility if provided
    if visibility and visibility not in ("public", "internal", "restricted"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid visibility: {visibility}. Must be public, internal, or restricted."
        )

    # Queue Celery task
    ingest_document_task.delay(
        job_id=job_id,
        doc_id=doc_id,
        version_id=version_id,
        filename=filename,
        source_type=detected_type,
        ingestion_backend=ingestion_backend,
        tenant_id=tenant_id,
        visibility=visibility,
        allowed_roles=parsed_roles,
        allowed_groups=parsed_groups,
        allowed_users=parsed_users,
    )
    
    return IngestResponse(
        job_id=job_id,
        doc_id=doc_id,
        version_id=version_id,
        status="pending",
    )


@router.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get the status of an ingestion job.
    
    Args:
        job_id: Job UUID
    
    Returns:
        JobStatusResponse with current status
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    with session_scope() as session:
        job = session.query(IngestJob).filter_by(job_id=job_uuid).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return JobStatusResponse(
            job_id=str(job.job_id),
            doc_id=job.doc_id,
            status=job.status,
            pipeline_stage=job.pipeline_stage,
            error=job.error,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
        )


@router.get("/document/{doc_id}/versions")
async def list_document_versions(doc_id: str) -> list[dict]:
    """List all versions of a document.
    
    Args:
        doc_id: Document ID
    
    Returns:
        List of version info dicts
    """
    with session_scope() as session:
        docs = session.query(Document).filter_by(doc_id=doc_id).all()
        
        if not docs:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return [
            {
                "doc_id": doc.doc_id,
                "version_id": doc.version_id,
                "source_type": doc.source_type,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in docs
        ]


class IngestJobListResponse(BaseModel):
    """Response for job list query."""
    items: list[JobStatusResponse]
    total: int
    page: int
    limit: int
    has_more: bool


@router.get("/jobs", response_model=IngestJobListResponse)
async def list_ingest_jobs(
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) -> IngestJobListResponse:
    """List ingestion jobs with optional filtering.
    
    Args:
        status: Optional status filter (pending, processing, completed, failed)
        page: Page number (default 1)
        limit: Items per page (default 20, max 100)
    
    Returns:
        IngestJobListResponse with paginated jobs
    """
    if limit > 100:
        limit = 100
    
    with session_scope() as session:
        query = session.query(IngestJob)
        
        if status:
            query = query.filter(IngestJob.status == status)
        
        total = query.count()
        
        offset = (page - 1) * limit
        jobs = query.order_by(IngestJob.created_at.desc()).offset(offset).limit(limit).all()
        
        items = [
            JobStatusResponse(
                job_id=str(job.job_id),
                doc_id=job.doc_id,
                status=job.status,
                pipeline_stage=job.pipeline_stage,
                error=job.error,
                started_at=job.started_at,
                completed_at=job.completed_at,
                created_at=job.created_at,
            )
            for job in jobs
        ]
        
        return IngestJobListResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
            has_more=offset + len(jobs) < total,
        )
