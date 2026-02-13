"""SQLAlchemy models for NPR RAG system."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Document(Base):
    """Documents table - system of record for ingested documents."""
    
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_checksum", "checksum"),
        Index("ix_documents_source_uri", "source_uri"),
        Index("ix_documents_graph_doc_version", "graph_doc_id", "graph_version"),
        Index("ix_documents_created_at", "created_at"),
    )
    
    doc_id = Column(String(256), primary_key=True)
    version_id = Column(String(256), nullable=False)
    source_type = Column(String(64), nullable=False)
    source_uri = Column(Text, nullable=False)
    mime_type = Column(String(128), nullable=True)
    # Canonical graph identity produced by GraphIngestionPipeline.
    graph_doc_id = Column(String(64), nullable=True)
    graph_version = Column(Integer, nullable=True)
    checksum = Column(String(128), nullable=False)
    owner = Column(String(256), nullable=True)
    team = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    ingest_jobs = relationship("IngestJob", back_populates="document")
    document_ir = relationship("DocumentIR", back_populates="document", uselist=False)
    chunks = relationship("Chunk", back_populates="document")
    
    def __repr__(self) -> str:
        return f"<Document(doc_id={self.doc_id}, version_id={self.version_id})>"


class IngestJob(Base):
    """Ingest jobs table - tracks document ingestion status."""
    
    __tablename__ = "ingest_jobs"
    __table_args__ = (
        Index("ix_ingest_jobs_status", "status"),
        Index("ix_ingest_jobs_doc_id", "doc_id"),
        Index("ix_ingest_jobs_graph_doc_version", "graph_doc_id", "graph_version"),
        Index("ix_ingest_jobs_created_at", "created_at"),
        Index("ix_ingest_jobs_status_created", "status", "created_at"),
    )
    
    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(String(256), ForeignKey("documents.doc_id"), nullable=True)
    # Canonical graph identity produced by GraphIngestionPipeline.
    graph_doc_id = Column(String(64), nullable=True)
    graph_version = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    pipeline_stage = Column(String(32), nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", back_populates="ingest_jobs")
    
    def __repr__(self) -> str:
        return f"<IngestJob(job_id={self.job_id}, status={self.status})>"


class DocumentIR(Base):
    """Document IR table - references to parsed intermediate representations."""
    
    __tablename__ = "document_ir"
    
    doc_id = Column(String(256), ForeignKey("documents.doc_id"), primary_key=True)
    version_id = Column(String(256), primary_key=True)
    ir_uri = Column(Text, nullable=False)
    parse_confidence = Column(Float, nullable=True)
    ocr_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="document_ir")
    
    def __repr__(self) -> str:
        return f"<DocumentIR(doc_id={self.doc_id}, version_id={self.version_id})>"


class Chunk(Base):
    """Chunks table - metadata for document chunks (content stored in MinIO)."""
    
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_doc_id", "doc_id"),
        Index("ix_chunks_doc_version", "doc_id", "version_id"),
        Index("ix_chunks_chunk_type", "chunk_type"),
        Index("ix_chunks_doc_type", "doc_id", "chunk_type"),
    )
    
    chunk_id = Column(String(256), primary_key=True)
    doc_id = Column(String(256), ForeignKey("documents.doc_id"), nullable=False)
    version_id = Column(String(256), nullable=False)
    section_path = Column(ARRAY(Text), nullable=True)
    chunk_type = Column(String(32), nullable=False)
    start_offset = Column(Integer, nullable=False)
    end_offset = Column(Integer, nullable=False)
    chunk_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    def __repr__(self) -> str:
        return f"<Chunk(chunk_id={self.chunk_id}, chunk_type={self.chunk_type})>"


class Trace(Base):
    """Traces table - references to flight recorder trace files."""
    
    __tablename__ = "traces"
    __table_args__ = (
        Index("ix_traces_request_id", "request_id"),
        Index("ix_traces_status", "status"),
        Index("ix_traces_created_at", "created_at"),
    )
    
    trace_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(String(256), nullable=False)
    status = Column(String(32), nullable=False)
    trace_uri = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self) -> str:
        return f"<Trace(trace_id={self.trace_id}, status={self.status})>"


class GoldenRecord(Base):
    """Golden records table - evaluation dataset records."""
    
    __tablename__ = "golden_records"
    
    record_id = Column(String(256), primary_key=True)
    label = Column(String(32), nullable=False)
    payload = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self) -> str:
        return f"<GoldenRecord(record_id={self.record_id}, label={self.label})>"


class VectorIndexVersion(Base):
    """Vector index versions - tracks which vectors are indexed in Milvus."""
    
    __tablename__ = "vector_index_versions"
    
    doc_id = Column(String(256), primary_key=True)
    version_id = Column(String(256), primary_key=True)
    collection_name = Column(String(128), primary_key=True)
    bundle_version = Column(String(32), nullable=False)
    vector_count = Column(Integer, nullable=False)
    indexed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self) -> str:
        return f"<VectorIndexVersion(doc_id={self.doc_id}, collection={self.collection_name})>"


class EmbeddingJob(Base):
    """Embedding jobs table - tracks embedding generation status."""
    
    __tablename__ = "embedding_jobs"
    __table_args__ = (
        Index("ix_embedding_jobs_status", "status"),
        Index("ix_embedding_jobs_doc_version", "doc_id", "version_id"),
        Index("ix_embedding_jobs_created_at", "created_at"),
        Index("ix_embedding_jobs_status_created", "status", "created_at"),
    )
    
    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(String(256), nullable=False)
    version_id = Column(String(256), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    pipeline_stage = Column(String(32), nullable=True)
    error = Column(Text, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    record_count = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    bundle_uri = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self) -> str:
        return f"<EmbeddingJob(job_id={self.job_id}, status={self.status})>"


class AppSettings(Base):
    """Application settings (singleton row).

    Stores runtime-configurable settings that can be changed via the UI
    without requiring server restarts or environment variable changes.
    """

    __tablename__ = "app_settings"
    __table_args__ = (
        # Ensure only one row can exist (singleton pattern)
        Index("ix_app_settings_singleton", "id", unique=True),
    )

    id = Column(Integer, primary_key=True, default=1)

    # QA Settings
    enable_llm_query_rewrite = Column(Boolean, default=False, nullable=False)
    retrieval_top_k = Column(Integer, default=5, nullable=False)
    enable_reranking = Column(Boolean, default=True, nullable=False)
    rerank_candidate_max = Column(Integer, default=15, nullable=False)
    max_context_tokens = Column(Integer, default=8000, nullable=False)

    # Ingestion Settings
    ocr_quality_threshold = Column(Float, default=0.3, nullable=False)
    target_chunk_tokens = Column(Integer, default=500, nullable=False)
    chunk_overlap_tokens = Column(Integer, default=50, nullable=False)

    # Timestamp
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<AppSettings(id={self.id}, updated_at={self.updated_at})>"


class IngestPreview(Base):
    """Staged upload preview for metadata review before processing."""

    __tablename__ = "ingest_previews"
    __table_args__ = (
        Index("ix_ingest_previews_status", "status"),
        Index("ix_ingest_previews_expires_at", "expires_at"),
        Index("ix_ingest_previews_created_at", "created_at"),
        Index("ix_ingest_previews_checksum", "checksum"),
    )

    preview_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(512), nullable=False)
    source_type = Column(String(64), nullable=False)
    mime_type = Column(String(128), nullable=True)
    preview_doc_id = Column(String(256), nullable=False)
    preview_version_id = Column(String(64), nullable=False, default="v1")
    checksum = Column(String(128), nullable=False)
    tenant_id = Column(String(64), nullable=True)

    # Extracted metadata payload (includes core fields)
    metadata_extracted = Column(JSONB, nullable=False, default=dict)
    metadata_provenance = Column(JSONB, nullable=False, default=dict)
    metadata_confidence = Column(JSONB, nullable=False, default=dict)

    status = Column(String(32), nullable=False, default="ready")  # ready|processed|expired
    expires_at = Column(DateTime(timezone=True), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<IngestPreview(preview_id={self.preview_id}, status={self.status})>"
