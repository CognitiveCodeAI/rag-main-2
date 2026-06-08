"""Settings API endpoints for runtime configuration."""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.acl.dependencies import get_entitlements
from app.acl.models import Entitlements
from app.db.session import get_session
from app.settings_service import (
    get_or_create_settings,
    get_runtime_settings,
    update_settings,
    reset_settings,
)

logger = logging.getLogger(__name__)


def _require_admin(entitlements: Optional[Entitlements]) -> None:
    """Authorize an admin-only mutation.

    When authenticated (entitlements present), require the admin role.
    When entitlements is None (auth + ACL both off — local dev), allow, to
    preserve existing unauthenticated dev behavior.
    """
    if entitlements is not None and not entitlements.is_admin:
        raise HTTPException(status_code=403, detail="Admin role required")

router = APIRouter(prefix="/v1/settings", tags=["settings"])


class AppSettingsResponse(BaseModel):
    """Response model for settings endpoints."""

    # QA Settings
    enable_llm_query_rewrite: bool = Field(
        description="Enable LLM-based query rewriting for multi-turn conversations"
    )
    retrieval_top_k: int = Field(description="Number of results from vector search")
    enable_reranking: bool = Field(description="Enable cross-encoder reranking")
    rerank_candidate_max: int = Field(description="Maximum candidates for reranker")
    max_context_tokens: int = Field(description="Maximum tokens in LLM context")

    # Ingestion Settings
    ocr_quality_threshold: float = Field(
        description="Text quality threshold for OCR fallback (0.0-1.0)"
    )
    target_chunk_tokens: int = Field(description="Target tokens per chunk")
    chunk_overlap_tokens: int = Field(description="Overlap between chunks")

    # Metadata
    updated_at: Optional[datetime] = Field(
        default=None, description="Last update timestamp"
    )


class AppSettingsUpdate(BaseModel):
    """Request model for updating settings (partial update)."""

    # QA Settings
    enable_llm_query_rewrite: Optional[bool] = Field(
        default=None, description="Enable LLM-based query rewriting"
    )
    retrieval_top_k: Optional[int] = Field(
        default=None, ge=1, le=50, description="Number of results from vector search"
    )
    enable_reranking: Optional[bool] = Field(
        default=None, description="Enable cross-encoder reranking"
    )
    rerank_candidate_max: Optional[int] = Field(
        default=None, ge=5, le=50, description="Maximum candidates for reranker"
    )
    max_context_tokens: Optional[int] = Field(
        default=None, ge=1000, le=32000, description="Maximum tokens in LLM context"
    )

    # Ingestion Settings
    ocr_quality_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Text quality threshold for OCR fallback",
    )
    target_chunk_tokens: Optional[int] = Field(
        default=None, ge=100, le=2000, description="Target tokens per chunk"
    )
    chunk_overlap_tokens: Optional[int] = Field(
        default=None, ge=0, le=500, description="Overlap between chunks"
    )


def _model_to_response(settings_row) -> AppSettingsResponse:
    """Convert database model to response model."""
    return AppSettingsResponse(
        enable_llm_query_rewrite=settings_row.enable_llm_query_rewrite,
        retrieval_top_k=settings_row.retrieval_top_k,
        enable_reranking=settings_row.enable_reranking,
        rerank_candidate_max=settings_row.rerank_candidate_max,
        max_context_tokens=settings_row.max_context_tokens,
        ocr_quality_threshold=settings_row.ocr_quality_threshold,
        target_chunk_tokens=settings_row.target_chunk_tokens,
        chunk_overlap_tokens=settings_row.chunk_overlap_tokens,
        updated_at=settings_row.updated_at,
    )


@router.get("", response_model=AppSettingsResponse)
async def get_settings(
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> AppSettingsResponse:
    """Get current application settings.

    Requires authentication when auth is enabled (the dependency fails closed);
    open in unauthenticated dev mode.
    """
    try:
        settings_row = get_or_create_settings(db)
        return _model_to_response(settings_row)
    except Exception as e:
        error_id = str(uuid.uuid4())
        logger.error(
            f"Failed to get settings (error_id={error_id}): {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (error_id={error_id})",
        )


@router.put("", response_model=AppSettingsResponse)
async def update_app_settings(
    updates: AppSettingsUpdate,
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> AppSettingsResponse:
    """Update application settings (admin only when authenticated).

    Accepts partial updates - only provided fields will be changed.
    All updates take effect immediately (cache is invalidated).
    """
    _require_admin(entitlements)
    try:
        # Extract non-None values
        update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}

        if not update_dict:
            # No updates provided, just return current settings
            settings_row = get_or_create_settings(db)
            return _model_to_response(settings_row)

        logger.info(f"Updating settings: {list(update_dict.keys())}")
        settings_row = update_settings(db, update_dict)
        return _model_to_response(settings_row)

    except Exception as e:
        error_id = str(uuid.uuid4())
        logger.error(
            f"Failed to update settings (error_id={error_id}): {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (error_id={error_id})",
        )


@router.post("/reset", response_model=AppSettingsResponse)
async def reset_app_settings(
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> AppSettingsResponse:
    """Reset all settings to default values (admin only when authenticated).

    Restores all settings to their factory defaults.
    """
    _require_admin(entitlements)
    try:
        logger.info("Resetting all settings to defaults")
        settings_row = reset_settings(db)
        return _model_to_response(settings_row)

    except Exception as e:
        error_id = str(uuid.uuid4())
        logger.error(
            f"Failed to reset settings (error_id={error_id}): {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (error_id={error_id})",
        )
