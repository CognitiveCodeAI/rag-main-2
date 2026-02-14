"""Runtime settings service with in-memory caching.

Provides cached access to runtime settings stored in the database.
Falls back to environment defaults if no database row exists.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AppSettings

logger = logging.getLogger(__name__)

# Cache TTL in seconds
CACHE_TTL_SECONDS = 60

# In-memory cache
# PERFORMANCE COUPLING:
# Cache is process-local; multi-worker deployments require explicit invalidation strategy for cross-process consistency.
_cached_settings: Optional["RuntimeSettings"] = None
_cache_timestamp: float = 0


@dataclass
class RuntimeSettings:
    """Runtime settings dataclass for type-safe access."""

    # QA Settings
    enable_llm_query_rewrite: bool = False
    retrieval_top_k: int = 5
    enable_reranking: bool = True
    rerank_candidate_max: int = 15
    max_context_tokens: int = 8000

    # Ingestion Settings
    ocr_quality_threshold: float = 0.3
    target_chunk_tokens: int = 500
    chunk_overlap_tokens: int = 50

    @classmethod
    def from_env_defaults(cls) -> "RuntimeSettings":
        """Create settings from environment defaults."""
        env = get_settings()
        return cls(
            enable_llm_query_rewrite=env.enable_llm_query_rewrite,
            retrieval_top_k=5,  # Default, not in env
            enable_reranking=True,  # Default
            rerank_candidate_max=15,  # Default
            max_context_tokens=8000,  # Default
            ocr_quality_threshold=env.text_quality_threshold,
            target_chunk_tokens=env.target_chunk_tokens,
            chunk_overlap_tokens=50,  # Default
        )

    @classmethod
    def from_db_model(cls, model: AppSettings) -> "RuntimeSettings":
        """Create settings from database model."""
        return cls(
            enable_llm_query_rewrite=model.enable_llm_query_rewrite,
            retrieval_top_k=model.retrieval_top_k,
            enable_reranking=model.enable_reranking,
            rerank_candidate_max=model.rerank_candidate_max,
            max_context_tokens=model.max_context_tokens,
            ocr_quality_threshold=model.ocr_quality_threshold,
            target_chunk_tokens=model.target_chunk_tokens,
            chunk_overlap_tokens=model.chunk_overlap_tokens,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "enable_llm_query_rewrite": self.enable_llm_query_rewrite,
            "retrieval_top_k": self.retrieval_top_k,
            "enable_reranking": self.enable_reranking,
            "rerank_candidate_max": self.rerank_candidate_max,
            "max_context_tokens": self.max_context_tokens,
            "ocr_quality_threshold": self.ocr_quality_threshold,
            "target_chunk_tokens": self.target_chunk_tokens,
            "chunk_overlap_tokens": self.chunk_overlap_tokens,
        }


def get_runtime_settings(db: Session) -> RuntimeSettings:
    """Get runtime settings with caching.

    Args:
        db: Database session

    Returns:
        RuntimeSettings instance (from cache if fresh, otherwise from DB)
    """
    global _cached_settings, _cache_timestamp

    now = time.time()

    # Return cached if still fresh
    # ORDER DEPENDENCY:
    # Settings updates are eventually visible up to TTL unless invalidate_settings_cache() is called on the same process.
    if _cached_settings is not None and (now - _cache_timestamp) < CACHE_TTL_SECONDS:
        return _cached_settings

    # Fetch from database
    try:
        settings_row = db.query(AppSettings).filter(AppSettings.id == 1).first()

        if settings_row is None:
            logger.info("No app_settings row found, using env defaults")
            _cached_settings = RuntimeSettings.from_env_defaults()
        else:
            _cached_settings = RuntimeSettings.from_db_model(settings_row)
            logger.debug("Loaded runtime settings from database")

        _cache_timestamp = now
        return _cached_settings

    except Exception as e:
        # WARNING:
        # DB read failures fail open to env defaults; this can silently revert runtime tuning during outages.
        logger.warning(f"Failed to load runtime settings from DB: {e}, using defaults")
        return RuntimeSettings.from_env_defaults()


def invalidate_settings_cache() -> None:
    """Invalidate the settings cache.

    Call this after updating settings to ensure changes are immediately visible.
    """
    global _cached_settings, _cache_timestamp
    _cached_settings = None
    _cache_timestamp = 0
    logger.info("Settings cache invalidated")


def get_or_create_settings(db: Session) -> AppSettings:
    """Get or create the singleton settings row.

    Args:
        db: Database session

    Returns:
        AppSettings model instance
    """
    # INVARIANT:
    # id=1 is the singleton row contract; changing key semantics requires coordinated migration and API updates.
    settings_row = db.query(AppSettings).filter(AppSettings.id == 1).first()

    if settings_row is None:
        logger.info("Creating default app_settings row")
        settings_row = AppSettings(id=1)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)

    return settings_row


def update_settings(db: Session, updates: dict) -> AppSettings:
    """Update settings with partial data.

    Args:
        db: Database session
        updates: Dictionary of setting name -> new value

    Returns:
        Updated AppSettings model instance
    """
    settings_row = get_or_create_settings(db)

    # Apply updates
    for key, value in updates.items():
        if hasattr(settings_row, key):
            setattr(settings_row, key, value)
        else:
            # DATA INTEGRITY:
            # Unknown keys are ignored by design; callers must validate payloads to avoid false-success config writes.
            logger.warning(f"Unknown setting key: {key}")

    db.commit()
    db.refresh(settings_row)

    # Invalidate cache
    invalidate_settings_cache()

    logger.info(f"Updated settings: {list(updates.keys())}")
    return settings_row


def reset_settings(db: Session) -> AppSettings:
    """Reset all settings to defaults.

    Args:
        db: Database session

    Returns:
        Reset AppSettings model instance
    """
    settings_row = get_or_create_settings(db)

    # Reset to defaults
    settings_row.enable_llm_query_rewrite = False
    settings_row.retrieval_top_k = 5
    settings_row.enable_reranking = True
    settings_row.rerank_candidate_max = 15
    settings_row.max_context_tokens = 8000
    settings_row.ocr_quality_threshold = 0.3
    settings_row.target_chunk_tokens = 500
    settings_row.chunk_overlap_tokens = 50

    db.commit()
    db.refresh(settings_row)

    # Invalidate cache
    invalidate_settings_cache()

    logger.info("Settings reset to defaults")
    return settings_row
