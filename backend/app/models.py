"""Data models for the NPR API."""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ResponseMode(str, Enum):
    """Response modes based on evidence sufficiency."""
    ANSWER = "ANSWER"
    ASK_CLARIFYING = "ASK_CLARIFYING"
    ABSTAIN_NO_EVIDENCE = "ABSTAIN_NO_EVIDENCE"
    ANSWER_WITH_CONFLICTS = "ANSWER_WITH_CONFLICTS"


class Citation(BaseModel):
    """A citation reference to a source document."""
    doc_id: str
    version_id: str
    source_uri: str
    title: str
    start_offset: int
    end_offset: int
    text: str


class Claim(BaseModel):
    """A factual claim with supporting citations."""
    text: str
    citations: list[Citation] = Field(default_factory=list)


class QueryRequest(BaseModel):
    """Incoming query request."""
    query: str
    context: Optional[str] = None
    filters: Optional[dict] = None


class QueryResponse(BaseModel):
    """Response to a query with grounded citations."""
    query_id: str
    final_text: str
    claims: list[Claim] = Field(default_factory=list)
    mode: ResponseMode
    confidence: float = Field(ge=0.0, le=1.0)
    followups: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ServiceStatus(BaseModel):
    """Status of an individual service."""
    status: str  # "healthy", "unhealthy", "unknown"
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str  # "healthy", "unhealthy", "degraded"
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    config_warnings: list[str] = Field(default_factory=list)
    services: Optional[dict[str, ServiceStatus]] = None
    features: Optional[dict] = None


class FileUploadResponse(BaseModel):
    """Response after file upload."""
    file_id: str
    filename: str
    size: int
    status: str
    message: str
