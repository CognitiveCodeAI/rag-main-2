"""Document ingestion API endpoints."""

import hashlib
import json
import mimetypes
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import fitz  # PyMuPDF, used to pre-validate PDF uploads
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func, or_

from app.acl.dependencies import get_entitlements
from app.acl.models import Entitlements
from app.acl.postgres_filter import ACLPostgresFilter
from app.config import get_settings
from app.db.graph_models import ContentRegistry, DocumentGraph, Node
from app.db.models import Document, IngestJob, IngestPreview
from app.db.session import session_scope
from app.graph.backend_selector import get_supported_types
from app.metadata.extractor import MetadataExtractor
from app.services.worker_health import inspect_celery_workers
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
    graph_doc_id: Optional[str] = None
    graph_version: Optional[int] = None
    status: str
    pipeline_stage: Optional[str] = None
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class MetadataPreviewResponse(BaseModel):
    """Response for metadata preview extraction."""
    preview_id: str
    filename: str
    source_type: str
    mime_type: Optional[str] = None
    expires_at: datetime
    metadata_extracted: dict[str, Any]
    metadata_provenance: dict[str, str]
    metadata_confidence: dict[str, float]
    warnings: list[str] = Field(default_factory=list)


class ProcessPreviewRequest(BaseModel):
    """Request payload to process a staged preview."""
    preview_id: str
    doc_id: Optional[str] = None
    ingestion_backend: Optional[str] = None
    metadata_overrides: dict[str, Any] = Field(default_factory=dict)
    tenant_id: Optional[str] = None
    visibility: Optional[str] = None
    allowed_roles: Optional[list[str]] = None
    allowed_groups: Optional[list[str]] = None
    allowed_users: Optional[list[str]] = None


PREVIEW_TTL_MINUTES = 30
UPLOAD_READ_CHUNK_SIZE = 1024 * 1024
METADATA_FIELDS = {
    "doc_date",
    "year",
    "source_system",
    "doc_type",
    "department",
    "authority_tier",
    "effective_from",
    "effective_to",
}


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
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand = uuid.uuid4().hex[:8]
    return f"v{ts}-{rand}"


def _parse_json_list(raw: Optional[str], field_name: str) -> Optional[list[str]]:
    """Parse and validate a JSON array-of-strings from multipart form fields."""
    if raw is None or raw == "":
        return None

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: expected JSON array of strings.",
        )

    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: expected JSON array of strings.",
        )

    normalized: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {field_name}: expected JSON array of strings.",
            )
        stripped = item.strip()
        if stripped:
            normalized.append(stripped)

    return normalized


def _raise_acl_access_denied(resource_name: str) -> None:
    """Raise ACL denial with disclosure mode semantics."""
    settings = get_settings()
    if settings.acl_disclosure_mode == "opaque":
        raise HTTPException(status_code=404, detail=f"{resource_name} not found")
    raise HTTPException(status_code=403, detail="Access denied")


def _validate_pdf_if_needed(content: bytes, filename: str, content_type: Optional[str]) -> None:
    """Fast-fail on invalid PDF payloads."""
    is_pdf = (content_type or "").lower() in ("application/pdf", "pdf") or filename.lower().endswith(".pdf")
    if not is_pdf:
        return
    try:
        with fitz.open(stream=content, filetype="pdf"):
            pass
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF file. Please upload a valid, non-corrupted PDF.",
        )


def _upload_size_limit_bytes() -> int:
    """Resolve configured upload size limit in bytes."""
    settings = get_settings()
    return settings.upload_max_file_size_mb * 1024 * 1024


async def _read_upload_content(file: UploadFile) -> bytes:
    """Read multipart upload with server-side max size enforcement."""
    max_bytes = _upload_size_limit_bytes()
    max_mb = max(1, max_bytes // (1024 * 1024))

    declared_size = getattr(file, "size", None)
    if isinstance(declared_size, int) and declared_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds {max_mb}MB limit",
        )

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds {max_mb}MB limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _require_embedding_config() -> None:
    """Ensure embedding prerequisites are configured before ingestion work."""
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


def _validate_source_type(filename: str, content_type: Optional[str], source_type: Optional[str]) -> str:
    """Detect and validate source_type against enabled backends."""
    detected_type = source_type or detect_source_type(filename, content_type)
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
    return detected_type


def _validate_ingestion_backend(ingestion_backend: Optional[str]) -> None:
    """Validate explicit backend override value."""
    if ingestion_backend is not None and ingestion_backend not in ("native", "docling"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ingestion_backend: {ingestion_backend}. Must be 'native' or 'docling'.",
        )


def _validate_visibility(visibility: Optional[str]) -> None:
    """Validate ACL visibility value."""
    if visibility and visibility not in ("public", "internal", "restricted"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid visibility: {visibility}. Must be public, internal, or restricted.",
        )


def _cleanup_expired_previews(session) -> None:
    """Expire stale preview rows and remove staged objects from storage."""
    now = datetime.now(timezone.utc)
    expired = (
        session.query(IngestPreview)
        .filter(IngestPreview.status == "ready", IngestPreview.expires_at < now)
        .all()
    )
    if not expired:
        return

    storage = get_storage_client()
    for preview in expired:
        try:
            storage.delete_document(preview.preview_doc_id, preview.preview_version_id)
        except Exception:
            # Best effort cleanup; row status still transitions to expired.
            pass
        # SIDE EFFECT:
        # Expiration status is authoritative even if blob deletion fails; object-store janitor paths must handle residual staged files.
        preview.status = "expired"


def _is_preview_expired(expires_at: datetime) -> bool:
    """Safely compare aware/naive preview timestamps against current UTC time."""
    if expires_at.tzinfo is None:
        return expires_at < datetime.now(timezone.utc)
    return expires_at < datetime.now(timezone.utc)


def _to_iso_date(value: Any) -> Optional[str]:
    """Normalize date-like values to ISO date strings."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10]).isoformat()
        except ValueError:
            return None
    return None


def _normalize_metadata_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep supported keys and coerce values to expected primitive types."""
    normalized: dict[str, Any] = {}

    for key, value in raw.items():
        if key not in METADATA_FIELDS:
            continue

        if key in {"doc_date", "effective_from", "effective_to"}:
            normalized[key] = _to_iso_date(value)
            continue

        if key in {"year", "authority_tier"}:
            if value is None or value == "":
                normalized[key] = None
            else:
                try:
                    normalized[key] = int(value)
                except (TypeError, ValueError):
                    continue
            continue

        if value is None:
            normalized[key] = None
            continue

        if isinstance(value, str):
            stripped = value.strip()
            normalized[key] = stripped or None
            continue

        normalized[key] = str(value)

    return normalized


def _merge_metadata_payload(
    extracted: dict[str, Any],
    provenance: dict[str, str],
    confidence: dict[str, float],
    overrides: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str], dict[str, float]]:
    """Merge metadata according to precedence: user > extracted > null."""
    merged = {field: extracted.get(field) for field in METADATA_FIELDS}
    merged_provenance = {field: provenance.get(field, "none") for field in METADATA_FIELDS}
    merged_confidence = {field: float(confidence.get(field, 0.0)) for field in METADATA_FIELDS}

    for field, value in overrides.items():
        if field not in METADATA_FIELDS:
            continue
        merged[field] = value
        merged_provenance[field] = "user"
        merged_confidence[field] = 1.0 if value is not None else 0.0

    if merged.get("year") is None and merged.get("doc_date"):
        parsed = _to_iso_date(merged.get("doc_date"))
        if parsed:
            merged["year"] = int(parsed[:4])
            if "year" not in overrides:
                merged_provenance["year"] = merged_provenance.get("doc_date", "derived")
                merged_confidence["year"] = merged_confidence.get("doc_date", 0.5)

    return merged, merged_provenance, merged_confidence


def _build_preview_warnings(metadata: dict[str, Any], confidence: dict[str, float]) -> list[str]:
    """Generate user-facing review warnings for metadata step."""
    warnings: list[str] = []
    for field in ("doc_type", "department", "authority_tier"):
        if metadata.get(field) is None:
            warnings.append(f"{field} is missing and should be reviewed before processing.")

    for field in ("doc_type", "department", "authority_tier", "year"):
        if metadata.get(field) is not None and confidence.get(field, 0.0) < 0.7:
            warnings.append(f"{field} has low confidence ({confidence.get(field, 0.0):.2f}).")

    return warnings


def _build_duplicate_response(session, checksum: str, tenant_id: Optional[str]) -> Optional[JSONResponse]:
    """Return duplicate conflict response if content already exists."""
    # SECURITY ASSUMPTION:
    # Duplicate identity is tenant-scoped; changing default tenant semantics can expose cross-tenant existence signals.
    effective_tenant = tenant_id if tenant_id else "default"
    existing = (
        session.query(ContentRegistry)
        .filter(
            ContentRegistry.content_hash == checksum,
            ContentRegistry.tenant_id == effective_tenant,
        )
        .first()
    )
    if not existing:
        return None

    canon_doc = session.query(DocumentGraph).filter_by(doc_id=existing.canonical_doc_id).first()
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
        existing_info.update(
            {
                "source_uri": canon_doc.source_uri,
                "ingested_at": canon_doc.ingested_at.isoformat() if canon_doc.ingested_at else None,
                "node_count": node_count,
                "doc_type": canon_doc.doc_type,
            }
        )
    return JSONResponse(
        status_code=409,
        content={
            "detail": "duplicate",
            "message": "This document has already been ingested.",
            "existing_document": existing_info,
        },
    )


@router.post("/metadata-preview", response_model=MetadataPreviewResponse)
async def metadata_preview(
    file: UploadFile = File(...),
    source_type: Optional[str] = Form(None),
    tenant_id: Optional[str] = Form(None),
) -> MetadataPreviewResponse:
    """Upload and stage a file, then return extracted metadata for user review."""
    content = await _read_upload_content(file)
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    filename = file.filename or "document"
    _validate_pdf_if_needed(content, filename, file.content_type)
    detected_type = _validate_source_type(filename, file.content_type, source_type)

    extractor = MetadataExtractor(enable_llm_fallback=False)
    extracted = extractor.extract(
        pdf_bytes=content,
        source_uri=f"upload://{filename}",
        filename=filename,
    )
    extracted_dict = extracted.to_dict()
    metadata_extracted = {field: extracted_dict.get(field) for field in METADATA_FIELDS}
    metadata_provenance = dict(extracted.provenance)
    metadata_confidence = {k: float(v) for k, v in extracted.confidence.items()}

    preview_doc_id = f"preview-{uuid.uuid4().hex}"
    preview_version_id = generate_version_id()
    checksum = hashlib.sha256(content).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=PREVIEW_TTL_MINUTES)

    storage = get_storage_client()
    # SIDE EFFECT:
    # Object is written before preview row commit; failed DB transactions can leave orphan preview blobs.
    storage.put_raw(
        doc_id=preview_doc_id,
        version_id=preview_version_id,
        content=content,
        filename=filename,
        content_type=file.content_type,
    )

    with session_scope() as session:
        _cleanup_expired_previews(session)
        preview = IngestPreview(
            filename=filename,
            source_type=detected_type,
            mime_type=file.content_type,
            preview_doc_id=preview_doc_id,
            preview_version_id=preview_version_id,
            checksum=checksum,
            tenant_id=tenant_id,
            metadata_extracted=metadata_extracted,
            metadata_provenance=metadata_provenance,
            metadata_confidence=metadata_confidence,
            status="ready",
            expires_at=expires_at,
        )
        session.add(preview)
        session.flush()
        preview_id = str(preview.preview_id)

    warnings = _build_preview_warnings(metadata_extracted, metadata_confidence)
    return MetadataPreviewResponse(
        preview_id=preview_id,
        filename=filename,
        source_type=detected_type,
        mime_type=file.content_type,
        expires_at=expires_at,
        metadata_extracted=metadata_extracted,
        metadata_provenance=metadata_provenance,
        metadata_confidence=metadata_confidence,
        warnings=warnings,
    )


@router.post("/process", response_model=IngestResponse)
async def process_metadata_preview(req: ProcessPreviewRequest) -> IngestResponse:
    """Process a previously staged preview after metadata review/editing."""
    _validate_ingestion_backend(req.ingestion_backend)
    _validate_visibility(req.visibility)

    try:
        preview_uuid = uuid.UUID(req.preview_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid preview ID format")

    normalized_overrides = _normalize_metadata_overrides(req.metadata_overrides or {})
    effective_tenant: Optional[str] = None

    with session_scope() as session:
        _cleanup_expired_previews(session)
        preview = session.query(IngestPreview).filter(IngestPreview.preview_id == preview_uuid).first()
        if not preview:
            raise HTTPException(status_code=404, detail="Preview not found")
        if preview.status == "processed":
            raise HTTPException(status_code=409, detail="Preview has already been processed")
        if preview.status == "expired" or _is_preview_expired(preview.expires_at):
            preview.status = "expired"
            raise HTTPException(status_code=410, detail="Preview has expired. Re-upload to continue.")

        effective_tenant = req.tenant_id or preview.tenant_id
        duplicate = _build_duplicate_response(
            session=session,
            checksum=preview.checksum,
            tenant_id=effective_tenant,
        )
        if duplicate is not None:
            return duplicate

        merged_meta, merged_provenance, merged_confidence = _merge_metadata_payload(
            extracted=preview.metadata_extracted or {},
            provenance=preview.metadata_provenance or {},
            confidence=preview.metadata_confidence or {},
            overrides=normalized_overrides,
        )
        preview.metadata_extracted = merged_meta
        preview.metadata_provenance = merged_provenance
        preview.metadata_confidence = merged_confidence
        preview_filename = preview.filename
        preview_doc_id = preview.preview_doc_id
        preview_version_id = preview.preview_version_id
        preview_source_type = preview.source_type
        preview_mime_type = preview.mime_type
        preview_checksum = preview.checksum

    worker_status = inspect_celery_workers(timeout=1.0)
    if not worker_status.healthy:
        raise HTTPException(
            status_code=503,
            detail=(
                "Document processing queue is unavailable. "
                f"{worker_status.message} Start a Celery worker and retry."
            ),
        )
    _require_embedding_config()

    storage = get_storage_client()
    try:
        content = storage.get_raw(preview_doc_id, preview_version_id, preview_filename)
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Staged file not found for preview {req.preview_id}: {e}",
        )

    final_doc_id = req.doc_id or generate_doc_id(content, preview_filename)
    final_version_id = generate_version_id()
    # ORDER DEPENDENCY:
    # Final raw blob must exist before task enqueue; worker consumes this exact (doc_id, version_id, filename) tuple.
    storage.put_raw(
        doc_id=final_doc_id,
        version_id=final_version_id,
        content=content,
        filename=preview_filename,
        content_type=preview_mime_type,
    )

    with session_scope() as session:
        preview = session.query(IngestPreview).filter(IngestPreview.preview_id == preview_uuid).first()
        if not preview or preview.status != "ready":
            raise HTTPException(status_code=409, detail="Preview state changed. Re-upload to continue.")

        # DATA INTEGRITY:
        # This second duplicate check closes TOCTOU between preview read and final row creation; removing it enables duplicate canonical claims.
        # Repeat duplicate check to avoid race windows between preview read and final write.
        duplicate = _build_duplicate_response(
            session=session,
            checksum=preview_checksum,
            tenant_id=effective_tenant,
        )
        if duplicate is not None:
            return duplicate

        doc = Document(
            doc_id=final_doc_id,
            version_id=final_version_id,
            source_type=preview_source_type,
            source_uri=f"upload://{preview_filename}",
            mime_type=preview_mime_type,
            graph_doc_id=None,
            graph_version=None,
            checksum=preview_checksum,
        )
        session.merge(doc)

        job = IngestJob(doc_id=final_doc_id, status="pending")
        session.add(job)
        session.flush()
        job_id = str(job.job_id)

        preview.status = "processed"
        preview.processed_at = datetime.now(timezone.utc)
        preview.tenant_id = effective_tenant

    ingest_document_task.delay(
        job_id=job_id,
        doc_id=final_doc_id,
        version_id=final_version_id,
        filename=preview_filename,
        source_type=preview_source_type,
        ingestion_backend=req.ingestion_backend,
        tenant_id=effective_tenant,
        visibility=req.visibility,
        allowed_roles=req.allowed_roles,
        allowed_groups=req.allowed_groups,
        allowed_users=req.allowed_users,
        metadata_overrides=normalized_overrides,
    )

    try:
        storage.delete_document(preview_doc_id, preview_version_id)
    except Exception:
        pass

    return IngestResponse(
        job_id=job_id,
        doc_id=final_doc_id,
        version_id=final_version_id,
        status="pending",
    )


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
    content = await _read_upload_content(file)
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    filename = file.filename or "document"

    _validate_pdf_if_needed(content, filename, file.content_type)
    detected_type = _validate_source_type(filename, file.content_type, source_type)
    _validate_ingestion_backend(ingestion_backend)
    _validate_visibility(visibility)
    
    # Generate IDs
    doc_id = doc_id or generate_doc_id(content, filename)
    version_id = generate_version_id()
    
    # Get checksum
    checksum = hashlib.sha256(content).hexdigest()

    # --- Duplicate detection: check if this content was already ingested ---
    # SECURITY ASSUMPTION:
    # Duplicate detection and downstream content registry must use the same tenant resolution to preserve isolation.
    # Scope by tenant_id to prevent cross-tenant false positives
    effective_tenant = tenant_id if tenant_id else "default"
    # _build_duplicate_response enforces tenant filter:
    # ContentRegistry.tenant_id == effective_tenant
    with session_scope() as session:
        duplicate = _build_duplicate_response(session, checksum, effective_tenant)
        if duplicate is not None:
            return duplicate

    worker_status = inspect_celery_workers(timeout=1.0)
    if not worker_status.healthy:
        raise HTTPException(
            status_code=503,
            detail=(
                "Document processing queue is unavailable. "
                f"{worker_status.message} Start a Celery worker and retry."
            ),
        )
    _require_embedding_config()

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
            graph_doc_id=None,
            graph_version=None,
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
    
    parsed_roles = _parse_json_list(allowed_roles, "allowed_roles")
    parsed_groups = _parse_json_list(allowed_groups, "allowed_groups")
    parsed_users = _parse_json_list(allowed_users, "allowed_users")

    # SIDE EFFECT:
    # DB state is committed before broker publish; enqueue failures leave pending jobs requiring explicit recovery/retry tooling.
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
async def get_job_status(
    job_id: str,
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> JobStatusResponse:
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

        if entitlements is not None:
            accessible_doc_ids = ACLPostgresFilter.get_accessible_doc_ids(
                session, entitlements
            )
            candidate_doc_ids = {
                candidate
                for candidate in (job.graph_doc_id, job.doc_id)
                if candidate
            }
            if not candidate_doc_ids or not (candidate_doc_ids & accessible_doc_ids):
                _raise_acl_access_denied("Job")
        
        return JobStatusResponse(
            job_id=str(job.job_id),
            doc_id=job.doc_id,
            graph_doc_id=job.graph_doc_id,
            graph_version=job.graph_version,
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
        # Preferred path: canonical graph versions
        graph_docs = (
            session.query(DocumentGraph)
            .filter(DocumentGraph.doc_id == doc_id)
            .order_by(DocumentGraph.version.desc())
            .all()
        )

        legacy_doc = session.query(Document).filter(Document.doc_id == doc_id).first()
        if not graph_docs and legacy_doc and legacy_doc.graph_doc_id:
            graph_docs = (
                session.query(DocumentGraph)
                .filter(DocumentGraph.doc_id == legacy_doc.graph_doc_id)
                .order_by(DocumentGraph.version.desc())
                .all()
            )

        # Backward-compatible fallback for older rows not yet mapped.
        if not graph_docs and legacy_doc and legacy_doc.source_uri:
            # FRAGILE COUPLING:
            # source_uri fallback is legacy compatibility only; non-unique URIs can misassociate versions across migrated records.
            graph_docs = (
                session.query(DocumentGraph)
                .filter(DocumentGraph.source_uri == legacy_doc.source_uri)
                .order_by(DocumentGraph.version.desc())
                .all()
            )

        if graph_docs:
            canonical_graph_doc_id = graph_docs[0].doc_id
            linked_legacy = (
                session.query(Document)
                .filter(Document.graph_doc_id == canonical_graph_doc_id)
                .all()
            )
            legacy_by_graph_version = {
                d.graph_version: d for d in linked_legacy if d.graph_version is not None
            }
            return [
                {
                    "doc_id": g.doc_id,
                    "graph_doc_id": g.doc_id,
                    "graph_version": g.version,
                    "version_id": (
                        legacy_by_graph_version[g.version].version_id
                        if g.version in legacy_by_graph_version
                        else str(g.version)
                    ),
                    "legacy_doc_id": (
                        legacy_by_graph_version[g.version].doc_id
                        if g.version in legacy_by_graph_version
                        else None
                    ),
                    "source_type": (
                        legacy_by_graph_version[g.version].source_type
                        if g.version in legacy_by_graph_version
                        else None
                    ),
                    "created_at": g.ingested_at.isoformat() if g.ingested_at else None,
                }
                for g in graph_docs
            ]

        # Last-resort fallback: legacy row only
        if not legacy_doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return [
            {
                "doc_id": legacy_doc.doc_id,
                "graph_doc_id": legacy_doc.graph_doc_id,
                "graph_version": legacy_doc.graph_version,
                "version_id": legacy_doc.version_id,
                "source_type": legacy_doc.source_type,
                "created_at": legacy_doc.created_at.isoformat() if legacy_doc.created_at else None,
            }
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
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
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

        accessible_doc_ids = ACLPostgresFilter.get_accessible_doc_ids(session, entitlements)
        if accessible_doc_ids is not None:
            if not accessible_doc_ids:
                return IngestJobListResponse(
                    items=[],
                    total=0,
                    page=page,
                    limit=limit,
                    has_more=False,
                )
            query = query.filter(
                or_(
                    IngestJob.graph_doc_id.in_(accessible_doc_ids),
                    IngestJob.doc_id.in_(accessible_doc_ids),
                )
            )
        
        if status:
            query = query.filter(IngestJob.status == status)
        
        total = query.count()
        
        offset = (page - 1) * limit
        jobs = query.order_by(IngestJob.created_at.desc()).offset(offset).limit(limit).all()
        
        items = [
            JobStatusResponse(
                job_id=str(job.job_id),
                doc_id=job.doc_id,
                graph_doc_id=job.graph_doc_id,
                graph_version=job.graph_version,
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
