"""Metadata extraction module for document metadata-aware retrieval."""

from .extractor import MetadataExtractor, ExtractedMetadata
from .patterns import (
    DATE_PATTERNS,
    FILENAME_DATE_PATTERNS,
    DEPARTMENT_KEYWORDS,
    DOC_TYPE_KEYWORDS,
    AUTHORITY_TIER_KEYWORDS,
)

__all__ = [
    "MetadataExtractor",
    "ExtractedMetadata",
    "DATE_PATTERNS",
    "FILENAME_DATE_PATTERNS",
    "DEPARTMENT_KEYWORDS",
    "DOC_TYPE_KEYWORDS",
    "AUTHORITY_TIER_KEYWORDS",
]
