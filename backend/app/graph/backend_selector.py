"""Backend selector for ingestion pipeline.

Resolves whether to use the native (PyMuPDF) or Docling backend
for document ingestion based on configuration, source type, and
request-level overrides.
"""

import logging
from typing import Literal, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# Source types each backend can handle
NATIVE_SUPPORTED_TYPES = {"pdf"}
DOCLING_SUPPORTED_TYPES = {"pdf", "docx", "pptx", "xlsx", "html", "md", "csv"}


def get_supported_types() -> set[str]:
    """Return the set of file types currently supported based on docling config."""
    settings = get_settings()
    if not settings.docling_enabled_default:
        return set(NATIVE_SUPPORTED_TYPES)
    mode = settings.docling_mode
    if mode == "off":
        return set(NATIVE_SUPPORTED_TYPES)
    # non_pdf_only and all both support the full docling set
    return set(DOCLING_SUPPORTED_TYPES)


def resolve_backend(
    source_type: str,
    request_override: Optional[str] = None,
) -> Literal["native", "docling"]:
    """Resolve which ingestion backend to use.

    Priority order:
    1. Request-level override (highest) — but only honored if docling is enabled
    2. docling_mode + source_type from settings
    3. Falls back to "native"

    Args:
        source_type: Document source type (pdf, docx, pptx, etc.)
        request_override: Optional per-request override ("native" or "docling")

    Returns:
        "native" or "docling"
    """
    settings = get_settings()

    # If request explicitly asks for native, always honor it
    if request_override == "native":
        return "native"

    # If request asks for docling, check if it's allowed
    if request_override == "docling":
        if not settings.docling_enabled_default:
            logger.warning(
                "Request asked for docling backend but docling_enabled_default=False. "
                "Falling back to native."
            )
            return "native"
        if source_type not in DOCLING_SUPPORTED_TYPES:
            logger.warning(
                f"Request asked for docling but source_type='{source_type}' is not supported. "
                f"Supported: {DOCLING_SUPPORTED_TYPES}. Falling back to native."
            )
            return "native"
        return "docling"

    # No request override — use config-based resolution
    if not settings.docling_enabled_default:
        return "native"

    mode = settings.docling_mode

    if mode == "off":
        return "native"

    if source_type not in DOCLING_SUPPORTED_TYPES:
        return "native"

    if mode == "non_pdf_only":
        if source_type == "pdf":
            return "native"
        return "docling"

    if mode == "all":
        return "docling"

    # Unknown mode (shouldn't happen with validator, but be safe)
    logger.warning(f"Unknown docling_mode='{mode}', falling back to native")
    return "native"
