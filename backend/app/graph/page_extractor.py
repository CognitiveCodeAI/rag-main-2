"""Page text extraction with quality scoring and OCR fallback.

Extracts text from PDF pages using native text when available,
falling back to DeepSeek-OCR via Ollama when text quality is low.
"""

import io
import base64
import logging
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from pathlib import Path

import fitz  # PyMuPDF

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class TextSpan:
    """An ordered source word with display-oriented provenance.

    ``bbox`` uses page points with a top-left origin after page rotation.
    ``normalized_bbox`` uses the same orientation with values in 0..1 so the
    browser never has to mix PyMuPDF coordinates with PDF.js user space.
    """
    text: str
    bbox: tuple  # (x0, y0, x1, y1) in PDF points
    span_id: str = ""
    order: int = 0
    block_no: Optional[int] = None
    line_no: Optional[int] = None
    word_no: Optional[int] = None
    normalized_bbox: Optional[dict] = None
    coordinate_system: str = "pdf_points_top_left"
    extraction_source: str = "native_pdf"
    verifiable: bool = True
    
    def to_dict(self) -> dict:
        return {
            'span_id': self.span_id,
            'order': self.order,
            'text': self.text,
            'bbox': {'x0': self.bbox[0], 'y0': self.bbox[1], 'x1': self.bbox[2], 'y1': self.bbox[3]},
            'normalized_bbox': self.normalized_bbox,
            'block_no': self.block_no,
            'line_no': self.line_no,
            'word_no': self.word_no,
            'coordinate_system': self.coordinate_system,
            'extraction_source': self.extraction_source,
            'verifiable': self.verifiable,
        }


@dataclass
class PageData:
    """Extracted data for a single page."""
    page_no: int  # 1-indexed
    text_md: str
    text_plain: str
    has_text_layer: bool
    text_quality_score: float
    used_ocr: bool
    width: float
    height: float
    rotation: int = 0
    text_spans: List['TextSpan'] = field(default_factory=list)  # Text with bbox info
    meta: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Result of extracting all pages from a document."""
    pages: List[PageData]
    total_pages: int
    ocr_pages: int
    native_pages: int
    
    def to_meta(self) -> dict:
        """Convert to metadata dict for storage."""
        return {
            "total_pages": self.total_pages,
            "ocr_pages": self.ocr_pages,
            "native_pages": self.native_pages,
            "pages": [
                {
                    "page_no": p.page_no,
                    "has_text_layer": p.has_text_layer,
                    "text_quality_score": round(p.text_quality_score, 3),
                    "used_ocr": p.used_ocr,
                    "char_count": len(p.text_plain),
                }
                for p in self.pages
            ]
        }


class PageExtractor:
    """Extracts text from PDF pages with OCR fallback."""

    # Expected chars per page for quality scoring
    EXPECTED_CHARS_PER_PAGE = 2000

    def __init__(
        self,
        ocr_client=None,
        skip_ocr: bool = False,
        quality_threshold: Optional[float] = None
    ):
        """Initialize extractor.

        Args:
            ocr_client: Optional OCR client. If None, will create on demand.
            skip_ocr: If True, skip OCR even for low-quality pages (use native text).
            quality_threshold: OCR quality threshold override. If None, uses env config.
                              Set from runtime settings at call site if desired.
        """
        self.settings = get_settings()
        self._ocr_client = ocr_client
        self.skip_ocr = skip_ocr
        self._quality_threshold = quality_threshold
    
    @property
    def ocr_client(self):
        """Lazy-load OCR client."""
        if self._ocr_client is None:
            from app.ocr import get_ocr_client
            self._ocr_client = get_ocr_client()
        return self._ocr_client

    @property
    def quality_threshold(self) -> float:
        """Get OCR quality threshold (override or env default)."""
        if self._quality_threshold is not None:
            return self._quality_threshold
        return self.settings.text_quality_threshold
    
    def extract_pages(
        self,
        pdf_bytes: bytes,
        doc_id: str = "unknown",
        force_ocr: bool = False
    ) -> ExtractionResult:
        """Extract text from all pages in a PDF.
        
        Args:
            pdf_bytes: Raw PDF file bytes
            doc_id: Document ID for logging
            force_ocr: If True, always use OCR regardless of text quality
            
        Returns:
            ExtractionResult with all page data
        """
        pages: List[PageData] = []
        ocr_count = 0
        native_count = 0
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        try:
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_no = page_idx + 1  # 1-indexed
                
                logger.debug(f"[{doc_id}] Processing page {page_no}/{len(doc)}")
                
                page_data = self._extract_page(
                    page=page,
                    page_no=page_no,
                    doc_id=doc_id,
                    force_ocr=force_ocr
                )
                
                pages.append(page_data)
                
                if page_data.used_ocr:
                    ocr_count += 1
                else:
                    native_count += 1
                    
        finally:
            doc.close()
        
        return ExtractionResult(
            pages=pages,
            total_pages=len(pages),
            ocr_pages=ocr_count,
            native_pages=native_count
        )
    
    def _extract_page(
        self,
        page: fitz.Page,
        page_no: int,
        doc_id: str,
        force_ocr: bool
    ) -> PageData:
        """Extract text from a single page.
        
        Args:
            page: PyMuPDF page object
            page_no: Page number (1-indexed)
            doc_id: Document ID for logging
            force_ocr: Force OCR regardless of text quality
            
        Returns:
            PageData for this page
        """
        rect = page.rect
        width, height = rect.width, rect.height
        
        # Try native text extraction first
        native_text = page.get_text("text").strip()
        has_text_layer = len(native_text) > 0
        native_char_count = len(native_text)
        
        # Calculate quality score
        quality_score = self._compute_quality_score(native_text)
        
        # Extract text spans with bounding boxes for anchoring
        text_spans = self._extract_text_spans(page)
        
        # Decide whether to use OCR (unless skip_ocr is set)
        use_ocr = self._should_use_ocr(
            has_text_layer=has_text_layer,
            native_char_count=native_char_count,
            quality_score=quality_score,
            force_ocr=force_ocr,
        )

        if use_ocr:
            logger.info(f"[{doc_id}] Page {page_no}: Using OCR (quality={quality_score:.2f}, threshold={self.quality_threshold})")
            try:
                text_md, text_plain = self._ocr_page(page, page_no, doc_id)
                used_ocr = True
                # Note: OCR doesn't provide bbox, so text_spans will be from native extraction
                # This is still useful for fallback text search
            except Exception as e:
                # Fail open to native text so one OCR page cannot block the entire document ingest.
                logger.warning(
                    f"[{doc_id}] Page {page_no}: OCR failed, falling back to native text: {e}"
                )
                text_md = native_text
                text_plain = native_text
                used_ocr = False
        elif self.skip_ocr and quality_score < self.quality_threshold:
            logger.warning(f"[{doc_id}] Page {page_no}: Low quality but OCR skipped (quality={quality_score:.2f})")
            text_md = native_text
            text_plain = native_text
            used_ocr = False
        else:
            logger.debug(f"[{doc_id}] Page {page_no}: Using native text (quality={quality_score:.2f})")
            text_md = native_text
            text_plain = native_text
            used_ocr = False
        
        return PageData(
            page_no=page_no,
            text_md=text_md,
            text_plain=text_plain,
            has_text_layer=has_text_layer,
            text_quality_score=quality_score,
            used_ocr=used_ocr,
            width=width,
            height=height,
            rotation=int(page.rotation or 0),
            text_spans=text_spans,
            meta={
                "native_char_count": len(native_text),
                "final_char_count": len(text_plain),
                "text_span_count": len(text_spans),
                "coordinate_system": "normalized_top_left",
                "crop_box": {
                    "x0": float(page.cropbox.x0),
                    "y0": float(page.cropbox.y0),
                    "x1": float(page.cropbox.x1),
                    "y1": float(page.cropbox.y1),
                },
            }
        )

    def _should_use_ocr(
        self,
        *,
        has_text_layer: bool,
        native_char_count: int,
        quality_score: float,
        force_ocr: bool,
    ) -> bool:
        """Determine whether OCR should run for a page.

        Policy:
        - `force_ocr` always wins.
        - `skip_ocr` always disables OCR.
        - Pages with no text layer use OCR.
        - Text-layer pages default to native text unless explicit fallback is enabled.
        """
        if force_ocr:
            return True
        if self.skip_ocr:
            return False
        if not has_text_layer:
            return True

        if not self.settings.ocr_text_layer_fallback_enabled:
            return False

        # Only OCR short, low-quality text-layer pages when fallback is enabled.
        return (
            native_char_count < self.settings.ocr_text_layer_min_chars
            and quality_score < self.quality_threshold
        )
    
    def _extract_text_spans(self, page: fitz.Page) -> List[TextSpan]:
        """Extract ordered words with normalized display rectangles.

        Word-level provenance lets the verifier return only the lines supporting
        a claim. Font spans and merged chunk boxes are too coarse for legal or
        clinical review.
        
        Args:
            page: PyMuPDF page object
            
        Returns:
            List of TextSpan objects with text and bbox
        """
        spans: List[TextSpan] = []
        
        try:
            words = page.get_text("words", sort=True)
            display_width = max(float(page.rect.width), 1.0)
            display_height = max(float(page.rect.height), 1.0)
            rotation_matrix = page.rotation_matrix

            for order, word in enumerate(words):
                if len(word) < 8:
                    continue
                x0, y0, x1, y1, text, block_no, line_no, word_no = word[:8]
                text = unicodedata.normalize("NFKC", str(text)).strip()
                if not text:
                    continue

                source_rect = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
                display_rect = source_rect * rotation_matrix if page.rotation else source_rect
                display_rect.normalize()
                normalized_bbox = {
                    "x0": max(0.0, min(1.0, display_rect.x0 / display_width)),
                    "y0": max(0.0, min(1.0, display_rect.y0 / display_height)),
                    "x1": max(0.0, min(1.0, display_rect.x1 / display_width)),
                    "y1": max(0.0, min(1.0, display_rect.y1 / display_height)),
                }
                spans.append(
                    TextSpan(
                        text=text,
                        bbox=(
                            float(display_rect.x0),
                            float(display_rect.y0),
                            float(display_rect.x1),
                            float(display_rect.y1),
                        ),
                        span_id=f"p{page.number + 1}:w{order}",
                        order=order,
                        block_no=int(block_no),
                        line_no=int(line_no),
                        word_no=int(word_no),
                        normalized_bbox=normalized_bbox,
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to extract word provenance with bbox: {e}")
        
        return spans
    
    def _compute_quality_score(self, text: str) -> float:
        """Compute text quality score (0.0 to 1.0+).
        
        Higher is better. Score > 1.0 indicates more text than expected.
        
        Args:
            text: Extracted text
            
        Returns:
            Quality score
        """
        if not text:
            return 0.0
        
        char_count = len(text.strip())
        
        # Basic heuristic: ratio of chars to expected
        base_score = char_count / self.EXPECTED_CHARS_PER_PAGE
        
        # Penalize if mostly whitespace or special chars
        alpha_count = sum(1 for c in text if c.isalnum())
        alpha_ratio = alpha_count / max(len(text), 1)
        
        # Combined score
        score = base_score * alpha_ratio
        
        return min(score, 2.0)  # Cap at 2.0
    
    def _ocr_page(
        self,
        page: fitz.Page,
        page_no: int,
        doc_id: str
    ) -> Tuple[str, str]:
        """OCR a page using DeepSeek-OCR.
        
        Args:
            page: PyMuPDF page object
            page_no: Page number for logging
            doc_id: Document ID for logging
            
        Returns:
            (text_md, text_plain) tuple
        """
        # Render page to image
        zoom = 2.0  # Higher DPI for better OCR
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PNG bytes
        image_bytes = pix.tobytes("png")
        
        # Call OCR
        text_md = self.ocr_client.ocr_full_page(
            image_bytes=image_bytes,
            doc_id=doc_id,
            page_no=page_no
        )
        
        # Generate plain text by stripping markdown
        text_plain = self._strip_markdown(text_md)
        
        return text_md, text_plain
    
    def _strip_markdown(self, md_text: str) -> str:
        """Strip markdown formatting to get plain text.
        
        Args:
            md_text: Markdown text
            
        Returns:
            Plain text without markdown formatting
        """
        import re
        
        text = md_text
        
        # Remove headers
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        
        # Remove bold/italic
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        
        # Remove links but keep text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        
        # Remove inline code
        text = re.sub(r'`([^`]+)`', r'\1', text)
        
        # Remove table pipes but keep content
        text = re.sub(r'\|', ' ', text)
        text = re.sub(r'^[-:]+$', '', text, flags=re.MULTILINE)
        
        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        return text.strip()
    
    def render_page_image(
        self,
        page: fitz.Page,
        zoom: float = 2.0
    ) -> bytes:
        """Render page to PNG image.
        
        Args:
            page: PyMuPDF page object
            zoom: Zoom factor (higher = better quality)
            
        Returns:
            PNG image bytes
        """
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")
    
    def render_region_image(
        self,
        page: fitz.Page,
        bbox: dict,
        zoom: float = 2.0,
        padding: int = 10
    ) -> bytes:
        """Render a region of a page to PNG image.
        
        Args:
            page: PyMuPDF page object
            bbox: Bounding box {x0, y0, x1, y1}
            zoom: Zoom factor
            padding: Pixels of padding around region
            
        Returns:
            PNG image bytes
        """
        # Create clip rectangle with padding
        clip = fitz.Rect(
            bbox['x0'] - padding,
            bbox['y0'] - padding,
            bbox['x1'] + padding,
            bbox['y1'] + padding
        )
        
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, clip=clip)
        return pix.tobytes("png")
