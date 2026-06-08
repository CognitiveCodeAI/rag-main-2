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
    debug: bool = False
    vendor_name: str = "Cognitive Code"
    vendor_website: str = "https://cognitiveCode.ai"
    vendor_developer: str = "Larry Stewart"
    
    # Deployment profile: "development" (default) or "production".
    # In production the app refuses to start with insecure defaults
    # (ACL disabled, built-in credentials) — see validate_production_security().
    environment: str = "development"

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

    # Upload guardrails
    upload_max_file_size_mb: int = 50

    # Local file reads (C4 / audit H-8): documents with a file:// source_uri are
    # only readable when their canonical path is under this allow-listed root.
    # Empty (default) disables local file:// reads entirely — the safe default,
    # since normal ingestion stores blobs in object storage, not the local FS.
    allowed_local_file_root: str = ""

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
    # Figure-OCR throughput/cost controls (E3). Region OCR calls are I/O-bound
    # HTTP requests, run with bounded concurrency; the per-doc cap bounds spend.
    ocr_max_concurrency: int = 4          # parallel region-OCR HTTP calls per doc
    ocr_max_calls_per_doc: int = 60       # 0 = unlimited; beyond it, figures get empty OCR
    ocr_text_layer_fallback_enabled: bool = False  # OCR low-quality pages even when text layer exists
    ocr_text_layer_min_chars: int = 200  # Only OCR text-layer pages below this char count

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

    # Cross-format selector highlighting
    enable_cross_format_highlighting: bool = True

    # Access Control Layer (ACL)
    # When enabled, enforces tenant-scoped ABAC/RBAC at every pipeline stage.
    # Identity resolved from headers: X-Tenant-Id, X-User-Id, X-Roles, X-Groups
    acl_enabled: bool = False                    # Master feature flag
    acl_strict_mode: bool = True                 # Fail closed on missing entitlements
    acl_disclosure_mode: str = "opaque"          # "opaque" (404) | "explicit" (403)
    acl_default_visibility: str = "public"       # Default for docs ingested without ACL
    acl_admin_roles: list[str] = ["admin"]       # Roles that bypass ACL checks
    acl_default_tenant_id: str = "default"       # Tenant for pre-ACL data

    # JWT/OIDC authentication (C2/C3 — replaces trusted-header identity).
    # When auth_enabled, identity is taken from a verified Bearer token instead
    # of X-* headers, and write routes require a valid token. Default OFF so
    # local dev and the default test suite keep working with no token.
    auth_enabled: bool = False
    oidc_issuer: str = ""                         # expected `iss` (also used to derive JWKS if jwks_url empty)
    oidc_audience: str = ""                       # expected `aud`
    oidc_jwks_url: str = ""                       # JWKS endpoint; if empty, derived from issuer
    jwt_algorithms: list[str] = ["RS256"]         # ASYMMETRIC allow-list only (never HS*/none)
    jwt_leeway_seconds: int = 30                  # clock-skew tolerance for exp/nbf
    jwt_jwks_timeout_seconds: float = 5.0         # JWKS fetch timeout (fail closed)
    jwt_tenant_claim: str = "tenant_id"           # claim -> Entitlements.tenant_id
    jwt_user_claim: str = "sub"                   # claim -> Entitlements.user_id
    jwt_roles_claim: str = "roles"                # claim (list or comma-string) -> roles
    jwt_groups_claim: str = "groups"              # claim (list or comma-string) -> groups

    @field_validator("acl_disclosure_mode")
    @classmethod
    def validate_acl_disclosure_mode(cls, v: str) -> str:
        valid = {"opaque", "explicit"}
        if v not in valid:
            raise ValueError(f"acl_disclosure_mode must be one of {valid}, got '{v}'")
        return v

    @field_validator("jwt_algorithms")
    @classmethod
    def validate_jwt_algorithms(cls, v: list[str]) -> list[str]:
        # Asymmetric only. Symmetric (HS*) algorithms enable key-confusion
        # attacks against a public JWKS, and "none" disables verification.
        allowed = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512", "EdDSA"}
        if not v:
            raise ValueError("jwt_algorithms must not be empty")
        bad = [a for a in v if a not in allowed]
        if bad:
            raise ValueError(
                f"jwt_algorithms must be asymmetric; rejected {bad}. Allowed: {sorted(allowed)}"
            )
        return v

    @property
    def effective_jwks_url(self) -> str:
        """JWKS endpoint: explicit oidc_jwks_url, else derived from the issuer."""
        if self.oidc_jwks_url:
            return self.oidc_jwks_url
        if self.oidc_issuer:
            return self.oidc_issuer.rstrip("/") + "/.well-known/jwks.json"
        return ""

    @field_validator("docling_mode")
    @classmethod
    def validate_docling_mode(cls, v: str) -> str:
        valid = {"off", "non_pdf_only", "all"}
        if v not in valid:
            raise ValueError(f"docling_mode must be one of {valid}, got '{v}'")
        return v

    @field_validator("upload_max_file_size_mb")
    @classmethod
    def validate_upload_max_file_size_mb(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("upload_max_file_size_mb must be > 0")
        return v

    @field_validator("ocr_text_layer_min_chars")
    @classmethod
    def validate_ocr_text_layer_min_chars(cls, v: int) -> int:
        if v < 0:
            raise ValueError("ocr_text_layer_min_chars must be >= 0")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore any extra environment variables
    
    @property
    def is_production(self) -> bool:
        """True when running under the production deployment profile."""
        return self.environment.strip().lower() in ("production", "prod")

    def validate_required_for_embeddings(self) -> list[str]:
        """Check if required settings for embeddings are configured.

        Returns:
            List of missing required settings (empty if all configured)
        """
        missing = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        return missing

    def validate_production_security(self) -> list[str]:
        """Return production security violations (empty list if safe).

        Only meaningful when ``is_production`` is True. Closes the two
        fail-open defaults flagged in the audit: ACL disabled (C-1/H-1)
        and weak built-in credentials (M-1). The caller refuses to start
        the app if this returns a non-empty list in production.
        """
        problems: list[str] = []
        if not self.acl_enabled:
            problems.append(
                "ACL_ENABLED is false — authorization is bypassed. Set ACL_ENABLED=true."
            )
        if self.db_password in ("", "ragpass"):
            problems.append("DB_PASSWORD is empty or the insecure default 'ragpass'.")
        if self.minio_access_key in ("", "minioadmin"):
            problems.append("MINIO_ACCESS_KEY is empty or the insecure default 'minioadmin'.")
        if self.minio_secret_key in ("", "minioadmin"):
            problems.append("MINIO_SECRET_KEY is empty or the insecure default 'minioadmin'.")
        if not self.auth_enabled:
            problems.append(
                "AUTH_ENABLED is false — in-app token verification is bypassed and "
                "unsigned X-* identity headers would be trusted. Set AUTH_ENABLED=true."
            )
        else:
            if not self.oidc_issuer:
                problems.append("AUTH_ENABLED is true but OIDC_ISSUER is not configured.")
            if not self.oidc_audience:
                problems.append("AUTH_ENABLED is true but OIDC_AUDIENCE is not configured.")
            if not self.effective_jwks_url:
                problems.append("AUTH_ENABLED is true but no JWKS URL is configured or derivable.")
        return problems
    
    def log_configuration_summary(self) -> None:
        """Log a summary of the current configuration for debugging."""
        logger.info("=== Configuration Summary ===")
        logger.info(f"  Environment: {self.environment}")
        logger.info(f"  Database: {self.db_user}@{self.db_host}:{self.db_port}/{self.db_name}")
        logger.info(f"  Milvus: {self.milvus_host}:{self.milvus_port}")
        logger.info(f"  MinIO: {self.minio_endpoint}")
        logger.info(f"  Redis: {self.redis_url}")
        logger.info(f"  Upload max file size: {self.upload_max_file_size_mb} MB")
        logger.info(f"  OpenAI API Key: {'configured' if self.openai_api_key else 'NOT SET (required for embeddings)'}")
        logger.info(f"  Docling: enabled={self.docling_enabled_default}, mode={self.docling_mode}")
        logger.info(f"  Cross-format highlighting: enabled={self.enable_cross_format_highlighting}")
        logger.info(f"  ACL: enabled={self.acl_enabled}, strict={self.acl_strict_mode}, disclosure={self.acl_disclosure_mode}")
        if not self.acl_enabled:
            logger.warning(
                "ACL is disabled. Authorization checks are bypassed until ACL_ENABLED=true."
            )
        logger.info(f"  Debug mode: {self.debug}")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_current_datetime() -> str:
    """Get current date and time for LLM context."""
    return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
