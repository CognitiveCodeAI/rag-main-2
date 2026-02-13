"""Configuration settings for the NPR backend."""
import logging
from datetime import datetime
from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings.
    
    All settings can be overridden via environment variables or .env file.
    Default values match docker-compose.yml for local development.
    """
    
    # App info
    app_name: str = "FDD - Document Intelligence"
    app_version: str = "0.1.0"
    debug: bool = True
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    # LLM settings (Ollama - local, no API key needed)
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2"
    
    # Database (defaults match docker-compose.yml)
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "ragdb"
    db_user: str = "raguser"
    db_password: str = "ragpass"
    
    # MinIO (defaults match docker-compose.yml)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    
    # Redis (defaults match docker-compose.yml)
    redis_url: str = "redis://localhost:6379/0"
    redis_backend: str = "redis://localhost:6379/1"
    
    # OpenAI Embedding settings
    openai_api_key: str = ""  # REQUIRED for embeddings - set via OPENAI_API_KEY in .env
    embedding_model: str = "text-embedding-3-large"
    embedding_dim: int = 3072  # Native dimension for text-embedding-3-large
    embedding_bundle_version: str = "1.0"
    
    # Milvus settings (defaults match docker-compose.yml)
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    
    # OCR settings
    ocr_provider: str = "openai"  # "openai" or "ollama"
    ocr_openai_model: str = "gpt-5-mini"  # OpenAI vision model for OCR
    ocr_timeout: int = 120  # seconds for full page OCR
    ocr_region_timeout: int = 60  # seconds for region OCR
    ocr_max_retries: int = 3

    # Ollama OCR settings (if ocr_provider="ollama")
    ollama_base_url: str = "http://localhost:11434"
    ollama_ocr_model: str = "deepseek-ocr:latest"
    
    # Page extraction settings
    text_quality_threshold: float = 0.3  # Below this, use OCR
    target_chunk_tokens: int = 500
    
    # LLM Query Rewriting (for multi-turn conversations)
    # Set ENABLE_LLM_QUERY_REWRITE=true in .env to enable
    enable_llm_query_rewrite: bool = False  # Disabled by default - enable for human chat
    llm_rewrite_model: str = "gpt-4o-mini"  # Fast model for rewrites
    llm_rewrite_timeout: int = 5  # seconds max for rewrite call
    llm_rewrite_max_history: int = 5  # max conversation turns to include

    # Docling ingestion backend (prototype)
    # When enabled, uses Docling for multi-format document conversion.
    # Requires: pip install docling>=2.72.0
    docling_enabled_default: bool = False
    docling_mode: str = "off"  # "off" | "non_pdf_only" | "all"
    docling_max_pages: int = 200
    docling_max_file_size_mb: int = 100

    # Access Control Layer (ACL)
    # When enabled, enforces tenant-scoped ABAC/RBAC at every pipeline stage.
    # Identity resolved from headers: X-Tenant-Id, X-User-Id, X-Roles, X-Groups
    acl_enabled: bool = False                    # Master feature flag
    acl_strict_mode: bool = True                 # Fail closed on missing entitlements
    acl_disclosure_mode: str = "opaque"          # "opaque" (404) | "explicit" (403)
    acl_default_visibility: str = "public"       # Default for docs ingested without ACL
    acl_admin_roles: list[str] = ["admin"]       # Roles that bypass ACL checks
    acl_default_tenant_id: str = "default"       # Tenant for pre-ACL data

    @field_validator("acl_disclosure_mode")
    @classmethod
    def validate_acl_disclosure_mode(cls, v: str) -> str:
        valid = {"opaque", "explicit"}
        if v not in valid:
            raise ValueError(f"acl_disclosure_mode must be one of {valid}, got '{v}'")
        return v

    @field_validator("docling_mode")
    @classmethod
    def validate_docling_mode(cls, v: str) -> str:
        valid = {"off", "non_pdf_only", "all"}
        if v not in valid:
            raise ValueError(f"docling_mode must be one of {valid}, got '{v}'")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore any extra environment variables
    
    def validate_required_for_embeddings(self) -> list[str]:
        """Check if required settings for embeddings are configured.
        
        Returns:
            List of missing required settings (empty if all configured)
        """
        missing = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        return missing
    
    def log_configuration_summary(self) -> None:
        """Log a summary of the current configuration for debugging."""
        logger.info("=== Configuration Summary ===")
        logger.info(f"  Database: {self.db_user}@{self.db_host}:{self.db_port}/{self.db_name}")
        logger.info(f"  Milvus: {self.milvus_host}:{self.milvus_port}")
        logger.info(f"  MinIO: {self.minio_endpoint}")
        logger.info(f"  Redis: {self.redis_url}")
        logger.info(f"  OpenAI API Key: {'configured' if self.openai_api_key else 'NOT SET (required for embeddings)'}")
        logger.info(f"  Docling: enabled={self.docling_enabled_default}, mode={self.docling_mode}")
        logger.info(f"  ACL: enabled={self.acl_enabled}, strict={self.acl_strict_mode}, disclosure={self.acl_disclosure_mode}")
        logger.info(f"  Debug mode: {self.debug}")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_current_datetime() -> str:
    """Get current date and time for LLM context."""
    return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
