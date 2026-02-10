"""File upload routes."""
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.models import FileUploadResponse

router = APIRouter(prefix="/api", tags=["upload"])

# Allowed file types
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".xlsx"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)) -> FileUploadResponse:
    """
    Upload a document for ingestion into the corpus.
    
    Supported formats: PDF, DOC, DOCX, TXT, MD, CSV, XLSX
    """
    # Validate file extension
    if file.filename:
        ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )
    
    # Read file to get size
    content = await file.read()
    size = len(content)
    
    if size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    
    # Generate file ID
    file_id = str(uuid.uuid4())
    
    # TODO: Actually process and ingest the file
    # For now, return success response
    return FileUploadResponse(
        file_id=file_id,
        filename=file.filename or "unknown",
        size=size,
        status="queued",
        message="File received and queued for processing. Ingestion will begin shortly."
    )


@router.get("/upload/{file_id}/status")
async def get_upload_status(file_id: str):
    """Get the processing status of an uploaded file."""
    # Placeholder - will be implemented with actual status tracking
    return {
        "file_id": file_id,
        "status": "processing",
        "progress": 50,
        "message": "Extracting document structure..."
    }
