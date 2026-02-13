"""Docling adapter for the ingestion pipeline.

Converts documents using Docling and maps the output to the pipeline's
ExtractionResult and FigureData types. All Docling imports are lazy
so this module can be imported without Docling installed.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

from .page_extractor import ExtractionResult, PageData, TextSpan
from .figure_detector import FigureData

logger = logging.getLogger(__name__)

# Approximate chars per synthetic page for formats without page numbers (DOCX, PPTX)
SYNTHETIC_PAGE_CHARS = 3000


def convert_with_docling(
    raw_bytes: bytes,
    filename: str,
    source_type: str,
    doc_id: str,
    max_pages: int = 200,
    max_file_size_mb: int = 100,
) -> Tuple[ExtractionResult, List[FigureData], Dict[str, Any]]:
    """Convert a document using Docling and map to pipeline types.

    Args:
        raw_bytes: Raw document bytes
        filename: Original filename
        source_type: Document source type (pdf, docx, pptx, etc.)
        doc_id: Document ID for logging
        max_pages: Maximum pages to process (memory guard)
        max_file_size_mb: Maximum file size in MB (memory guard)

    Returns:
        Tuple of (ExtractionResult, List[FigureData], provenance_dict)

    Raises:
        ImportError: If docling is not installed
        ValueError: If file exceeds size limits
        RuntimeError: If Docling conversion fails
    """
    # Memory guard: check file size before importing Docling
    file_size_mb = len(raw_bytes) / (1024 * 1024)
    if file_size_mb > max_file_size_mb:
        raise ValueError(
            f"File size {file_size_mb:.1f}MB exceeds limit of {max_file_size_mb}MB"
        )

    # Lazy import Docling
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
    except ImportError:
        raise ImportError(
            "Docling is not installed. Install with: pip install docling>=2.72.0"
        )

    logger.info(
        f"[{doc_id}] Starting Docling conversion: "
        f"filename={filename}, source_type={source_type}, "
        f"size={file_size_mb:.1f}MB"
    )

    # Configure Docling pipeline
    pdf_pipeline_options = PdfPipelineOptions()
    pdf_pipeline_options.do_ocr = True
    pdf_pipeline_options.do_table_structure = True

    format_options = {
        InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_options),
    }

    # Create converter (per-call, not shared, for thread safety)
    converter = DocumentConverter(format_options=format_options)

    # Write to temp file for Docling (it expects a file path)
    import tempfile
    import os
    suffix = f".{source_type}" if not filename.endswith(f".{source_type}") else ""
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=suffix or os.path.splitext(filename)[1]
    ) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        result = converter.convert(tmp_path, max_num_pages=max_pages)
        doc = result.document
    except Exception as e:
        raise RuntimeError(f"Docling conversion failed: {e}") from e
    finally:
        os.unlink(tmp_path)

    # Build page data from Docling document
    pages, figures, provenance = _map_docling_output(doc, source_type, doc_id)

    extraction = ExtractionResult(
        pages=pages,
        total_pages=len(pages),
        ocr_pages=0,  # Docling handles OCR internally
        native_pages=len(pages),
    )

    logger.info(
        f"[{doc_id}] Docling conversion complete: "
        f"pages={len(pages)}, figures={len([f for f in figures if f.figure_type == 'figure'])}, "
        f"tables={len([f for f in figures if f.figure_type == 'table'])}"
    )

    return extraction, figures, provenance


def _map_docling_output(
    doc: Any,
    source_type: str,
    doc_id: str,
) -> Tuple[List[PageData], List[FigureData], Dict[str, Any]]:
    """Map Docling document to pipeline types.

    Args:
        doc: Docling DoclingDocument
        source_type: Source type for synthetic page numbering
        doc_id: Document ID for logging

    Returns:
        Tuple of (pages, figures, provenance)
    """
    # Collect text by page
    page_texts: Dict[int, List[str]] = {}
    page_spans: Dict[int, List[TextSpan]] = {}
    page_md_parts: Dict[int, List[str]] = {}
    page_structural_refs: Dict[int, str] = {}

    # Track if this format has real page numbers
    has_real_pages = source_type in {"pdf"}

    # Iterate over document items
    for item, _level in doc.iterate_items():
        item_type = type(item).__name__

        # Get page number from provenance
        page_no = _get_page_no(item, has_real_pages)

        if page_no not in page_texts:
            page_texts[page_no] = []
            page_spans[page_no] = []
            page_md_parts[page_no] = []

        # Preserve stable structural provenance handles when available.
        if page_no not in page_structural_refs:
            self_ref = getattr(item, "self_ref", None)
            if self_ref is not None:
                page_structural_refs[page_no] = str(self_ref)

        # Map different item types
        if item_type == "SectionHeaderItem":
            level = getattr(item, "level", 1)
            prefix = "#" * min(level, 6)
            text = _get_item_text(item)
            page_md_parts[page_no].append(f"{prefix} {text}")
            page_texts[page_no].append(text)

        elif item_type == "TableItem":
            text = _get_table_text(item, doc)
            page_md_parts[page_no].append(text)
            page_texts[page_no].append(text)

        elif item_type == "TextItem":
            text = _get_item_text(item)
            page_md_parts[page_no].append(text)
            page_texts[page_no].append(text)

            # Extract bbox spans if available
            span = _get_text_span(item)
            if span:
                page_spans[page_no].append(span)

        elif item_type == "ListItem":
            text = _get_item_text(item)
            page_md_parts[page_no].append(f"- {text}")
            page_texts[page_no].append(text)

    # For non-paged formats, apply synthetic page numbering
    if not has_real_pages and len(page_texts) == 1 and 1 in page_texts:
        page_texts, page_spans, page_md_parts = _apply_synthetic_pages(
            page_texts[1], page_spans.get(1, []), page_md_parts[1]
        )

    # Build PageData list
    pages: List[PageData] = []
    for page_no in sorted(page_texts.keys()):
        text_plain = "\n".join(page_texts[page_no])
        text_md = "\n\n".join(page_md_parts.get(page_no, []))

        pages.append(PageData(
            page_no=page_no,
            text_md=text_md,
            text_plain=text_plain,
            has_text_layer=True,
            text_quality_score=1.0,  # Docling handles quality internally
            used_ocr=False,
            width=612.0,  # Default US Letter
            height=792.0,
            text_spans=page_spans.get(page_no, []),
            meta={
                "source": "docling",
                "docling_self_ref": page_structural_refs.get(page_no),
            },
        ))

    # Extract figures and tables
    figures = _extract_figures(doc, has_real_pages)

    # Build provenance dict
    provenance = {
        "converter": "docling",
        "source_type": source_type,
        "total_items": sum(len(v) for v in page_texts.values()),
        "total_figures": len([f for f in figures if f.figure_type == "figure"]),
        "total_tables": len([f for f in figures if f.figure_type == "table"]),
    }

    return pages, figures, provenance


def _get_page_no(item: Any, has_real_pages: bool) -> int:
    """Extract page number from a Docling item's provenance."""
    if has_real_pages:
        prov = getattr(item, "prov", None)
        if prov and len(prov) > 0:
            page_no = getattr(prov[0], "page_no", None)
            if page_no is not None:
                return page_no
    return 1  # Default to page 1


def _get_item_text(item: Any) -> str:
    """Extract text from a Docling item."""
    text = getattr(item, "text", None)
    if text:
        return str(text)
    return ""


def _get_table_text(item: Any, doc: Any = None) -> str:
    """Extract markdown table text from a Docling TableItem."""
    # Try export_to_markdown first (pass doc to avoid deprecation warning)
    export_fn = getattr(item, "export_to_markdown", None)
    if export_fn:
        try:
            if doc is not None:
                return export_fn(doc)
            return export_fn()
        except Exception:
            pass

    # Fall back to text attribute
    return _get_item_text(item)


def _get_text_span(item: Any) -> Optional[TextSpan]:
    """Extract a TextSpan with bbox from a Docling item's provenance."""
    text = _get_item_text(item)
    if not text:
        return None

    prov = getattr(item, "prov", None)
    if not prov or len(prov) == 0:
        return None

    bbox = getattr(prov[0], "bbox", None)
    if bbox is None:
        return None

    # Docling bbox format: (l, t, r, b) → we need (x0, y0, x1, y1)
    try:
        l = getattr(bbox, "l", None) or getattr(bbox, "x0", None) or 0
        t = getattr(bbox, "t", None) or getattr(bbox, "y0", None) or 0
        r = getattr(bbox, "r", None) or getattr(bbox, "x1", None) or 0
        b = getattr(bbox, "b", None) or getattr(bbox, "y1", None) or 0
        return TextSpan(text=text, bbox=(l, t, r, b))
    except Exception:
        return None


def _apply_synthetic_pages(
    texts: List[str],
    spans: List[TextSpan],
    md_parts: List[str],
) -> Tuple[Dict[int, List[str]], Dict[int, List[TextSpan]], Dict[int, List[str]]]:
    """Apply synthetic page numbering for formats without real pages.

    Groups content into pages of ~SYNTHETIC_PAGE_CHARS characters each.

    Returns:
        Tuple of (page_texts, page_spans, page_md_parts) dicts keyed by page_no
    """
    page_texts: Dict[int, List[str]] = {}
    page_spans: Dict[int, List[TextSpan]] = {}
    page_md_parts: Dict[int, List[str]] = {}

    current_page = 1
    current_chars = 0

    for i, text in enumerate(texts):
        if current_chars >= SYNTHETIC_PAGE_CHARS and text:
            current_page += 1
            current_chars = 0

        if current_page not in page_texts:
            page_texts[current_page] = []
            page_spans[current_page] = []
            page_md_parts[current_page] = []

        page_texts[current_page].append(text)
        if i < len(md_parts):
            page_md_parts[current_page].append(md_parts[i])

        current_chars += len(text)

    # Assign spans to pages based on text position
    span_idx = 0
    char_count = 0
    page = 1
    for text in texts:
        if char_count >= SYNTHETIC_PAGE_CHARS and text:
            page += 1
            char_count = 0
        while span_idx < len(spans) and spans[span_idx].text == text:
            if page not in page_spans:
                page_spans[page] = []
            page_spans[page].append(spans[span_idx])
            span_idx += 1
            break
        char_count += len(text)

    return page_texts, page_spans, page_md_parts


def _extract_figures(doc: Any, has_real_pages: bool) -> List[FigureData]:
    """Extract figures and tables from a Docling document.

    Args:
        doc: Docling DoclingDocument
        has_real_pages: Whether the format has real page numbers

    Returns:
        List of FigureData
    """
    figures: List[FigureData] = []

    # Extract pictures
    pictures = getattr(doc, "pictures", None)
    if pictures:
        for i, pic in enumerate(pictures):
            page_no = _get_page_no(pic, has_real_pages)
            caption = _get_item_text(pic) or None
            bbox = _extract_bbox_dict(pic)

            figures.append(FigureData(
                page_no=page_no,
                label=f"Figure {i + 1}",
                caption=caption,
                bbox=bbox,
                figure_type="figure",
                confidence=0.8,
                meta={"source": "docling"},
            ))

    # Extract tables
    tables = getattr(doc, "tables", None)
    if tables:
        for i, table in enumerate(tables):
            page_no = _get_page_no(table, has_real_pages)
            text = _get_table_text(table, doc)
            bbox = _extract_bbox_dict(table)

            figures.append(FigureData(
                page_no=page_no,
                label=f"Table {i + 1}",
                caption=text or None,
                bbox=bbox,
                figure_type="table",
                confidence=0.8,
                meta={"source": "docling", "table_md": text},
            ))

    return figures


def _extract_bbox_dict(item: Any) -> Optional[dict]:
    """Extract bbox as dict from a Docling item."""
    prov = getattr(item, "prov", None)
    if not prov or len(prov) == 0:
        return None

    bbox = getattr(prov[0], "bbox", None)
    if bbox is None:
        return None

    try:
        l = getattr(bbox, "l", None) or getattr(bbox, "x0", None) or 0
        t = getattr(bbox, "t", None) or getattr(bbox, "y0", None) or 0
        r = getattr(bbox, "r", None) or getattr(bbox, "x1", None) or 0
        b = getattr(bbox, "b", None) or getattr(bbox, "y1", None) or 0
        return {"x0": l, "y0": t, "x1": r, "y1": b}
    except Exception:
        return None
