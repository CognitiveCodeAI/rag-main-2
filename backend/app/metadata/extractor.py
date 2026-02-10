"""Metadata extraction from documents.

Extracts document metadata using a priority-based approach:
1. PDF metadata (creation_date, mod_date)
2. Filename heuristics (year patterns, keywords)
3. First-page text heuristics (date patterns, department headers)
4. LLM classification (opt-in fallback, disabled by default)

All extraction stores provenance and confidence for auditability.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from .patterns import (
    DATE_PATTERNS,
    FILENAME_DATE_PATTERNS,
    MONTH_MAP,
    DEPARTMENT_KEYWORDS,
    DOC_TYPE_KEYWORDS,
    AUTHORITY_TIER_BY_DOC_TYPE,
    AUTHORITY_TIER_KEYWORDS,
    HEADER_PATTERNS,
    normalize_text,
    extract_first_n_chars,
    is_valid_year,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractedMetadata:
    """Extracted document metadata with provenance tracking."""
    
    doc_date: Optional[date] = None
    year: Optional[int] = None
    source_system: str = "upload"  # Default to "upload" for API uploads
    doc_type: Optional[str] = None
    department: Optional[str] = None
    authority_tier: Optional[int] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    
    # Provenance: maps field -> source (pdf_meta|filename|first_page|llm|none)
    provenance: Dict[str, str] = field(default_factory=dict)
    
    # Confidence: maps field -> confidence (0.0 - 1.0)
    confidence: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "doc_date": self.doc_date.isoformat() if self.doc_date else None,
            "year": self.year,
            "source_system": self.source_system,
            "doc_type": self.doc_type,
            "department": self.department,
            "authority_tier": self.authority_tier,
            "effective_from": self.effective_from.isoformat() if self.effective_from else None,
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "provenance": self.provenance,
            "confidence": self.confidence,
        }


class MetadataExtractor:
    """Extracts metadata from documents using deterministic methods.
    
    LLM fallback is opt-in and disabled by default for determinism.
    
    Extraction priority order:
    1. PDF metadata (highest confidence)
    2. Filename heuristics
    3. First-page text heuristics
    4. LLM classification (opt-in, lowest confidence)
    """
    
    # Confidence scores by extraction source
    CONFIDENCE_PDF_META = 0.95
    CONFIDENCE_FILENAME = 0.80
    CONFIDENCE_FIRST_PAGE = 0.70
    CONFIDENCE_LLM = 0.60
    CONFIDENCE_DEFAULT = 0.50
    
    def __init__(self, enable_llm_fallback: bool = False):
        """Initialize extractor.
        
        Args:
            enable_llm_fallback: Enable LLM classification for unknown fields.
                                Disabled by default for deterministic extraction.
        """
        self.enable_llm_fallback = enable_llm_fallback
        
    def extract(
        self,
        pdf_bytes: bytes,
        source_uri: str,
        filename: Optional[str] = None
    ) -> ExtractedMetadata:
        """Extract metadata from a PDF document.
        
        Args:
            pdf_bytes: Raw PDF bytes
            source_uri: Source URI of the document
            filename: Optional filename (extracted from source_uri if not provided)
            
        Returns:
            ExtractedMetadata with all extracted fields and provenance
        """
        result = ExtractedMetadata(source_system="upload")
        
        # Extract filename from source_uri if not provided
        if filename is None:
            filename = Path(source_uri).name
        
        # Open PDF
        try:
            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.warning(f"Failed to open PDF for metadata extraction: {e}")
            return result
        
        try:
            # 1. Extract from PDF metadata (highest priority)
            self._extract_from_pdf_metadata(pdf_doc, result)
            
            # 2. Extract from filename
            self._extract_from_filename(filename, result)
            
            # 3. Extract from first-page text
            first_page_text = self._get_first_page_text(pdf_doc)
            self._extract_from_first_page(first_page_text, result)
            
            # 4. Infer authority tier from doc_type (if not already set)
            self._infer_authority_tier(result)
            
            # 5. LLM fallback (opt-in)
            if self.enable_llm_fallback:
                self._extract_from_llm(first_page_text, result)
                
        finally:
            pdf_doc.close()
        
        logger.info(
            f"Extracted metadata: year={result.year}, doc_type={result.doc_type}, "
            f"department={result.department}, authority_tier={result.authority_tier}"
        )
        
        return result
    
    def _extract_from_pdf_metadata(
        self,
        pdf_doc: fitz.Document,
        result: ExtractedMetadata
    ) -> None:
        """Extract date from PDF metadata fields."""
        metadata = pdf_doc.metadata or {}
        
        # Try creation date first, then modification date
        for field in ['creationDate', 'modDate']:
            date_str = metadata.get(field)
            if date_str:
                parsed_date = self._parse_pdf_date(date_str)
                if parsed_date:
                    if result.doc_date is None:
                        result.doc_date = parsed_date
                        result.year = parsed_date.year
                        result.provenance['doc_date'] = 'pdf_meta'
                        result.provenance['year'] = 'pdf_meta'
                        result.confidence['doc_date'] = self.CONFIDENCE_PDF_META
                        result.confidence['year'] = self.CONFIDENCE_PDF_META
                        logger.debug(f"Extracted date from PDF {field}: {parsed_date}")
                    break
    
    def _parse_pdf_date(self, date_str: str) -> Optional[date]:
        """Parse PDF date format (D:YYYYMMDDHHmmSS)."""
        if not date_str:
            return None
        
        # Remove 'D:' prefix if present
        if date_str.startswith('D:'):
            date_str = date_str[2:]
        
        # Try to parse YYYYMMDD portion
        try:
            if len(date_str) >= 8:
                year = int(date_str[0:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                
                if is_valid_year(year) and 1 <= month <= 12 and 1 <= day <= 31:
                    return date(year, month, day)
        except (ValueError, IndexError):
            pass
        
        return None
    
    def _extract_from_filename(
        self,
        filename: str,
        result: ExtractedMetadata
    ) -> None:
        """Extract metadata from filename patterns."""
        if not filename:
            return
        
        filename_lower = normalize_text(filename)
        
        # Extract year/date from filename
        if result.year is None:
            for pattern, pattern_type in FILENAME_DATE_PATTERNS:
                match = pattern.search(filename)
                if match:
                    year = self._extract_year_from_filename_match(match, pattern_type)
                    if year and is_valid_year(year):
                        result.year = year
                        result.provenance['year'] = 'filename'
                        result.confidence['year'] = self.CONFIDENCE_FILENAME
                        
                        # Create approximate date (Jan 1 of year) if no exact date
                        if result.doc_date is None:
                            result.doc_date = date(year, 1, 1)
                            result.provenance['doc_date'] = 'filename'
                            result.confidence['doc_date'] = self.CONFIDENCE_FILENAME * 0.5
                        break
        
        # Extract department from filename
        if result.department is None:
            for keyword, dept in DEPARTMENT_KEYWORDS.items():
                if keyword in filename_lower:
                    result.department = dept
                    result.provenance['department'] = 'filename'
                    result.confidence['department'] = self.CONFIDENCE_FILENAME
                    break
        
        # Extract doc_type from filename
        if result.doc_type is None:
            for keyword, doc_type in DOC_TYPE_KEYWORDS.items():
                if keyword in filename_lower:
                    result.doc_type = doc_type
                    result.provenance['doc_type'] = 'filename'
                    result.confidence['doc_type'] = self.CONFIDENCE_FILENAME
                    break
    
    def _extract_year_from_filename_match(
        self,
        match: re.Match,
        pattern_type: str
    ) -> Optional[int]:
        """Extract year from regex match based on pattern type."""
        groups = match.groups()
        
        try:
            if pattern_type == 'full_date':
                return int(groups[0])
            elif pattern_type == 'year_month':
                return int(groups[0])
            elif pattern_type == 'quarter':
                # Q1_2024 or 2024_Q1
                if groups[1]:  # Q1_2024
                    return int(groups[1])
                elif groups[2]:  # 2024_Q1
                    return int(groups[2])
            elif pattern_type == 'fiscal_year':
                fy = int(groups[0])
                # Convert 2-digit FY to 4-digit
                if fy < 100:
                    return 2000 + fy if fy < 50 else 1900 + fy
                return fy
            elif pattern_type == 'year_only':
                return int(groups[0])
        except (ValueError, TypeError, IndexError):
            pass
        
        return None
    
    def _get_first_page_text(self, pdf_doc: fitz.Document) -> str:
        """Extract text from first page of PDF."""
        if len(pdf_doc) == 0:
            return ""
        
        try:
            first_page = pdf_doc[0]
            text = first_page.get_text("text")
            return extract_first_n_chars(text, 2000)
        except Exception as e:
            logger.warning(f"Failed to extract first page text: {e}")
            return ""
    
    def _extract_from_first_page(
        self,
        text: str,
        result: ExtractedMetadata
    ) -> None:
        """Extract metadata from first page text."""
        if not text:
            return
        
        text_lower = normalize_text(text)
        
        # Extract date from first page
        if result.doc_date is None:
            extracted_date = self._extract_date_from_text(text)
            if extracted_date:
                result.doc_date = extracted_date
                result.provenance['doc_date'] = 'first_page'
                result.confidence['doc_date'] = self.CONFIDENCE_FIRST_PAGE
                
                if result.year is None:
                    result.year = extracted_date.year
                    result.provenance['year'] = 'first_page'
                    result.confidence['year'] = self.CONFIDENCE_FIRST_PAGE
        
        # Extract department from first page headers
        if result.department is None:
            for keyword, dept in DEPARTMENT_KEYWORDS.items():
                # Look for department keywords in header area (first 500 chars)
                header_text = text_lower[:500]
                if keyword in header_text:
                    result.department = dept
                    result.provenance['department'] = 'first_page'
                    result.confidence['department'] = self.CONFIDENCE_FIRST_PAGE
                    break
        
        # Extract doc_type from first page
        if result.doc_type is None:
            # Look for doc type keywords with higher weight in title area
            header_text = text_lower[:300]
            for keyword, doc_type in DOC_TYPE_KEYWORDS.items():
                if keyword in header_text:
                    result.doc_type = doc_type
                    result.provenance['doc_type'] = 'first_page'
                    result.confidence['doc_type'] = self.CONFIDENCE_FIRST_PAGE
                    break
    
    def _extract_date_from_text(self, text: str) -> Optional[date]:
        """Extract date from text using various patterns."""
        for pattern, pattern_type in DATE_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    parsed = self._parse_date_match(match, pattern_type)
                    if parsed:
                        return parsed
                except (ValueError, IndexError):
                    continue
        return None
    
    def _parse_date_match(
        self,
        match: re.Match,
        pattern_type: str
    ) -> Optional[date]:
        """Parse a date regex match into a date object."""
        groups = match.groups()
        
        try:
            if pattern_type == 'iso':
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            elif pattern_type == 'us':
                month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
            elif pattern_type == 'long':
                month_name, day, year = groups[0], int(groups[1]), int(groups[2])
                month = MONTH_MAP.get(month_name.lower().rstrip('.'), 0)
            elif pattern_type == 'european':
                day, month_name, year = int(groups[0]), groups[1], int(groups[2])
                month = MONTH_MAP.get(month_name.lower().rstrip('.'), 0)
            elif pattern_type == 'month_year':
                month_name, year = groups[0], int(groups[1])
                month = MONTH_MAP.get(month_name.lower().rstrip('.'), 0)
                day = 1  # Default to first of month
            else:
                return None
            
            if is_valid_year(year) and 1 <= month <= 12 and 1 <= day <= 31:
                return date(year, month, day)
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _infer_authority_tier(self, result: ExtractedMetadata) -> None:
        """Infer authority tier from doc_type and keywords."""
        if result.authority_tier is not None:
            return
        
        # Infer from doc_type
        if result.doc_type:
            tier = AUTHORITY_TIER_BY_DOC_TYPE.get(result.doc_type)
            if tier:
                result.authority_tier = tier
                result.provenance['authority_tier'] = 'inferred_from_doc_type'
                result.confidence['authority_tier'] = self.CONFIDENCE_DEFAULT
    
    def _extract_from_llm(
        self,
        text: str,
        result: ExtractedMetadata
    ) -> None:
        """Use LLM for classification of unknown fields (opt-in only).
        
        NOTE: This is a stub. Full LLM integration would require:
        - A deterministic JSON schema output
        - Token limits to control costs
        - Proper error handling
        """
        if not self.enable_llm_fallback:
            return
        
        # Only use LLM if key fields are still unknown
        if result.doc_type is None or result.department is None:
            logger.info("LLM fallback enabled but not implemented - skipping")
            # TODO: Implement LLM classification with strict JSON schema
            # This would call the LLM to classify:
            # - doc_type (from predefined list)
            # - department (from predefined list)
            # Results would have lower confidence (0.6)
            pass


def get_metadata_extractor(enable_llm: bool = False) -> MetadataExtractor:
    """Factory function to get a MetadataExtractor instance.
    
    Args:
        enable_llm: Enable LLM fallback for unknown fields
        
    Returns:
        MetadataExtractor instance
    """
    return MetadataExtractor(enable_llm_fallback=enable_llm)
