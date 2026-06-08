"""Node creation for graph RAG.

Creates Node objects for:
- Chunks (from page-bounded chunking)
- Figures (from figure detection + OCR)
- Tables (from figure detection + OCR)
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import fitz  # PyMuPDF

from app.config import get_settings
from app.db.graph_models import Node, NodeType
from app.ocr import get_ocr_client, OCRClient
from .ids import compute_node_id, compute_text_hash
from .chunker import ChunkData
from .figure_detector import FigureData
from .page_extractor import PageExtractor

logger = logging.getLogger(__name__)


def create_chunk_nodes(
    chunks: List[ChunkData],
    doc_id: str,
    version: int
) -> List[Node]:
    """Create Node objects from ChunkData.
    
    Includes bbox and anchor_snippet from chunk metadata for citation anchoring.
    
    Args:
        chunks: List of ChunkData from chunker
        doc_id: Document ID
        version: Document version
        
    Returns:
        List of Node objects with bbox for highlighting support
    """
    nodes: List[Node] = []
    chunks_with_bbox = 0
    
    for chunk in chunks:
        node_id = compute_node_id(
            doc_id=doc_id,
            version=version,
            page_no=chunk.page_no,
            index=chunk.chunk_index_in_page,
            node_type='chunk'
        )
        
        # Extract bbox from chunk metadata if available
        chunk_bbox = chunk.meta.get("bbox") if chunk.meta else None
        if chunk_bbox:
            chunks_with_bbox += 1
        
        node = Node(
            node_id=node_id,
            doc_id=doc_id,
            version=version,
            node_type=NodeType.chunk,
            page_no=chunk.page_no,
            chunk_index_in_page=chunk.chunk_index_in_page,
            label=None,
            caption_md=None,
            text_md=chunk.text_md,
            text_plain=chunk.text_plain,
            bbox=chunk_bbox,  # Now populated from chunker!
            content_hash=chunk.content_hash,
            meta=chunk.meta  # Contains anchor_snippet and page_size
        )
        
        nodes.append(node)
    
    logger.info(
        f"Created {len(nodes)} chunk nodes for doc {doc_id} v{version} "
        f"({chunks_with_bbox} with bbox for highlighting)"
    )
    
    return nodes


def create_figure_nodes(
    figures: List[FigureData],
    pdf_bytes: bytes,
    doc_id: str,
    version: int,
    ocr_client: Optional[OCRClient] = None,
    skip_ocr: bool = False
) -> List[Node]:
    """Create Node objects from detected figures/tables.
    
    For each figure/table:
    1. Crop the region image
    2. Run OCR with DeepSeek-OCR (unless skip_ocr=True)
    3. Create node with label + caption + OCR text
    
    Args:
        figures: List of FigureData from detector
        pdf_bytes: Raw PDF bytes (for image cropping)
        doc_id: Document ID
        version: Document version
        ocr_client: Optional OCR client (will create if None)
        skip_ocr: If True, skip OCR for figure/table content
        
    Returns:
        List of Node objects
    """
    if not figures:
        return []
    
    # Initialize OCR client if needed (only if not skipping OCR)
    if ocr_client is None and not skip_ocr:
        ocr_client = get_ocr_client()
    
    # Initialize page extractor for image rendering
    page_extractor = PageExtractor()
    
    nodes: List[Node] = []

    settings = get_settings()
    max_concurrency = max(1, settings.ocr_max_concurrency)
    max_calls = settings.ocr_max_calls_per_doc  # 0 == unlimited

    # Open PDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    try:
        # Group figures by page (insertion order preserves document order).
        figures_by_page = {}
        for fig in figures:
            figures_by_page.setdefault(fig.page_no, []).append(fig)

        # --- Phase A (single-threaded): render region images in document order.
        # PyMuPDF pages are NOT thread-safe, so all fitz access stays here; the
        # per-doc spend cap is applied deterministically to the first N figures.
        work = []  # ordered: {"fig", "fig_index", "image_bytes"}
        ocr_calls_planned = 0
        over_cap = 0
        for page_no, page_figures in figures_by_page.items():
            page_idx = page_no - 1
            page = None
            if 0 <= page_idx < len(doc):
                page = doc[page_idx]
            else:
                logger.warning(f"Page {page_no} out of range for doc {doc_id}")
            for fig_idx, fig in enumerate(page_figures):
                image_bytes = None
                needs_ocr = bool(fig.bbox and not skip_ocr and ocr_client and page is not None)
                if needs_ocr and max_calls and ocr_calls_planned >= max_calls:
                    over_cap += 1  # beyond the spend cap -> no OCR (empty text)
                    needs_ocr = False
                if needs_ocr:
                    try:
                        image_bytes = page_extractor.render_region_image(
                            page=page, bbox=fig.bbox, zoom=2.0,
                        )
                        ocr_calls_planned += 1
                    except Exception as e:
                        logger.warning(f"Region render failed for {fig.label or 'figure'}: {e}")
                        image_bytes = None
                work.append({"fig": fig, "fig_index": fig_idx, "image_bytes": image_bytes})

        # --- Phase B (bounded concurrency): OCR the rendered regions. ocr_region
        # is a stateless, thread-safe HTTP call.
        ocr_text_by_item = {}  # id(work_item) -> ocr_text

        def _ocr(item):
            fig = item["fig"]
            return ocr_client.ocr_region(
                image_bytes=item["image_bytes"],
                doc_id=doc_id,
                page_no=fig.page_no,
                region_type=fig.figure_type,
            )

        ocr_items = [w for w in work if w["image_bytes"] is not None]
        if ocr_items:
            workers = min(max_concurrency, len(ocr_items))
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_ocr, w): w for w in ocr_items}
                    for fut in as_completed(futures):
                        w = futures[fut]
                        try:
                            ocr_text_by_item[id(w)] = fut.result() or ""
                        except Exception as e:
                            logger.warning(f"OCR failed for {w['fig'].label or 'figure'}: {e}")
                            ocr_text_by_item[id(w)] = ""
            else:
                for w in ocr_items:
                    try:
                        ocr_text_by_item[id(w)] = _ocr(w) or ""
                    except Exception as e:
                        logger.warning(f"OCR failed for {w['fig'].label or 'figure'}: {e}")
                        ocr_text_by_item[id(w)] = ""

        # --- Phase C (single-threaded, document order): build nodes.
        for w in work:
            node = _build_figure_node(
                fig=w["fig"],
                fig_index=w["fig_index"],
                doc_id=doc_id,
                version=version,
                ocr_text=ocr_text_by_item.get(id(w), ""),
            )
            if node:
                nodes.append(node)

    finally:
        doc.close()

    if over_cap:
        logger.warning(
            "OCR spend cap (%d) reached for doc %s; %d figure(s) left un-OCR'd",
            max_calls, doc_id, over_cap,
        )
    logger.info(
        "Created %d figure/table nodes for doc %s v%d (%d OCR calls, concurrency<=%d)",
        len(nodes), doc_id, version, ocr_calls_planned, max_concurrency,
    )

    return nodes


def create_figure_nodes_from_data(
    figures: List[FigureData],
    doc_id: str,
    version: int,
) -> List[Node]:
    """Create Node objects from FigureData using pre-extracted text.

    Unlike create_figure_nodes(), this does NOT open raw bytes with fitz.
    Used for the Docling backend where figure/table text is already extracted
    by Docling and stored in FigureData.caption/meta fields.

    Args:
        figures: List of FigureData (text already populated by Docling)
        doc_id: Document ID
        version: Document version

    Returns:
        List of Node objects
    """
    if not figures:
        return []

    nodes: List[Node] = []

    for fig_idx, fig in enumerate(figures):
        try:
            node_type = NodeType.figure if fig.figure_type == "figure" else NodeType.table

            # Generate node ID
            import re
            if fig.label:
                num_match = re.search(r'(\d+(?:\.\d+)?)', fig.label)
                index_for_id = int(float(num_match.group(1)) * 100) if num_match else fig_idx
            else:
                index_for_id = fig_idx

            node_id = compute_node_id(
                doc_id=doc_id,
                version=version,
                page_no=fig.page_no,
                index=index_for_id,
                node_type=fig.figure_type,
            )

            # Build text from FigureData fields (already extracted by Docling)
            text_parts = []
            if fig.label:
                text_parts.append(f"**{fig.label}**")
            if fig.caption:
                text_parts.append(fig.caption)
            # For tables, include markdown table from meta if available
            table_md = fig.meta.get("table_md") if fig.meta else None
            if table_md and table_md != fig.caption:
                text_parts.append(table_md)

            text_md = "\n\n".join(text_parts) if text_parts else ""
            text_plain = _strip_markdown(text_md)
            content_hash = compute_text_hash(text_plain) if text_plain else None

            node = Node(
                node_id=node_id,
                doc_id=doc_id,
                version=version,
                node_type=node_type,
                page_no=fig.page_no,
                chunk_index_in_page=None,
                label=fig.label,
                caption_md=fig.caption,
                text_md=text_md,
                text_plain=text_plain,
                bbox=fig.bbox,
                content_hash=content_hash,
                meta={
                    "confidence": fig.confidence,
                    "source": fig.meta.get("source", "docling"),
                    "has_ocr": False,
                },
            )
            nodes.append(node)

        except Exception as e:
            logger.error(f"Failed to create docling figure node for {fig.label or 'figure'}: {e}")

    logger.info(f"Created {len(nodes)} figure/table nodes (from data) for doc {doc_id} v{version}")
    return nodes


def _build_figure_node(
    fig: FigureData,
    fig_index: int,
    doc_id: str,
    version: int,
    ocr_text: str = "",
) -> Optional[Node]:
    """Build a single figure/table node from pre-computed OCR text.

    OCR (and the fitz rendering it needs) is performed by create_figure_nodes
    before this is called, so this is pure, fitz-free, and thread-safe to build.

    Args:
        fig: FigureData
        fig_index: Index of figure on this page
        doc_id: Document ID
        version: Document version
        ocr_text: OCR result for this region ("" if none/skipped/failed)

    Returns:
        Node object or None if creation fails
    """
    try:
        # Determine node type
        node_type = NodeType.figure if fig.figure_type == 'figure' else NodeType.table
        
        # Generate node ID
        # Use label if available, otherwise use page+index
        if fig.label:
            # Parse number from label for ID
            import re
            num_match = re.search(r'(\d+(?:\.\d+)?)', fig.label)
            index_for_id = int(float(num_match.group(1)) * 100) if num_match else fig_index
        else:
            index_for_id = fig_index
        
        node_id = compute_node_id(
            doc_id=doc_id,
            version=version,
            page_no=fig.page_no,
            index=index_for_id,
            node_type=fig.figure_type
        )
        
        # Build text_md: label + caption + OCR (ocr_text is pre-computed)
        text_parts = []
        if fig.label:
            text_parts.append(f"**{fig.label}**")
        if fig.caption:
            text_parts.append(fig.caption)
        if ocr_text:
            text_parts.append(ocr_text)
        
        text_md = "\n\n".join(text_parts) if text_parts else ""
        
        # Generate plain text
        text_plain = _strip_markdown(text_md)
        
        # Content hash
        content_hash = compute_text_hash(text_plain) if text_plain else None
        
        # Create node
        node = Node(
            node_id=node_id,
            doc_id=doc_id,
            version=version,
            node_type=node_type,
            page_no=fig.page_no,
            chunk_index_in_page=None,  # Not applicable for figures
            label=fig.label,
            caption_md=fig.caption,
            text_md=text_md,
            text_plain=text_plain,
            bbox=fig.bbox,
            content_hash=content_hash,
            meta={
                'confidence': fig.confidence,
                'source': fig.meta.get('source', 'unknown'),
                'has_ocr': bool(ocr_text),
            }
        )
        
        return node
        
    except Exception as e:
        logger.error(f"Failed to create node for {fig.label or 'figure'}: {e}")
        return None


def _strip_markdown(md_text: str) -> str:
    """Strip markdown formatting to get plain text.
    
    Args:
        md_text: Markdown text
        
    Returns:
        Plain text
    """
    import re
    
    text = md_text
    
    # Remove bold/italic markers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    
    # Remove headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # Remove links
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Remove inline code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove table formatting
    text = re.sub(r'\|', ' ', text)
    text = re.sub(r'^[-:]+$', '', text, flags=re.MULTILINE)
    
    # Clean whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    
    return text.strip()
