"""Figure and table detection for graph RAG.

V1 Strategy (pragmatic):
1. Try PDF structure extraction first (PyMuPDF image/figure annotations)
2. Detect caption patterns in text
3. For each detected figure/table: extract bbox, label, caption
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

from .ids import normalize_label

logger = logging.getLogger(__name__)


@dataclass
class FigureData:
    """Detected figure or table data."""
    page_no: int
    label: Optional[str]  # Normalized: "Figure 1.5", "Table 2"
    caption: Optional[str]
    bbox: Optional[dict]  # {x0, y0, x1, y1}
    figure_type: str  # 'figure' or 'table'
    confidence: float = 1.0
    meta: dict = field(default_factory=dict)


class FigureDetector:
    """Detects figures and tables in PDF documents."""
    
    # Caption patterns
    CAPTION_PATTERNS = [
        # "Figure 1.5: Caption text" or "Figure 1.5. Caption text"
        (r'(Figure|Fig\.?)\s*(\d+(?:\.\d+)?)[:.]\s*(.+?)(?:\n|$)', 'figure'),
        # "Table 1: Caption text"
        (r'(Table|Tab\.?)\s*(\d+(?:\.\d+)?)[:.]\s*(.+?)(?:\n|$)', 'table'),
    ]
    
    # Stand-alone label patterns (no caption)
    LABEL_PATTERNS = [
        (r'(Figure|Fig\.?)\s*(\d+(?:\.\d+)?)\b', 'figure'),
        (r'(Table|Tab\.?)\s*(\d+(?:\.\d+)?)\b', 'table'),
    ]
    
    def __init__(self):
        """Initialize detector."""
        pass
    
    def detect_in_document(
        self,
        pdf_bytes: bytes,
        doc_id: str = "unknown"
    ) -> List[FigureData]:
        """Detect all figures and tables in a PDF document.
        
        Args:
            pdf_bytes: Raw PDF bytes
            doc_id: Document ID for logging
            
        Returns:
            List of FigureData for all detected figures/tables
        """
        figures: List[FigureData] = []
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        try:
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_no = page_idx + 1
                
                page_figures = self.detect_in_page(
                    page=page,
                    page_no=page_no,
                    doc_id=doc_id
                )
                figures.extend(page_figures)
                
        finally:
            doc.close()
        
        # Deduplicate by label
        figures = self._deduplicate(figures)
        
        # Detailed count logging
        fig_count = sum(1 for f in figures if f.figure_type == 'figure')
        table_count = sum(1 for f in figures if f.figure_type == 'table')
        with_bbox = sum(1 for f in figures if f.bbox is not None)
        with_caption = sum(1 for f in figures if f.caption)
        with_label = sum(1 for f in figures if f.label)
        
        logger.info(
            f"[{doc_id}] Figure/Table Detection Summary: "
            f"total={len(figures)} (figures={fig_count}, tables={table_count}), "
            f"with_bbox={with_bbox}, with_caption={with_caption}, with_label={with_label}"
        )
        
        # Log per-page breakdown
        pages_with_figs = {}
        for f in figures:
            if f.page_no not in pages_with_figs:
                pages_with_figs[f.page_no] = {'figures': 0, 'tables': 0}
            if f.figure_type == 'figure':
                pages_with_figs[f.page_no]['figures'] += 1
            else:
                pages_with_figs[f.page_no]['tables'] += 1
        
        if pages_with_figs:
            logger.debug(f"[{doc_id}] Per-page breakdown: {pages_with_figs}")
        
        return figures
    
    def detect_in_page(
        self,
        page: fitz.Page,
        page_no: int,
        doc_id: str = "unknown"
    ) -> List[FigureData]:
        """Detect figures and tables in a single page.
        
        Args:
            page: PyMuPDF page object
            page_no: Page number (1-indexed)
            doc_id: Document ID for logging
            
        Returns:
            List of FigureData for this page
        """
        figures: List[FigureData] = []
        
        # Strategy 1: Extract images from PDF structure
        image_figures = self._detect_from_images(page, page_no)
        figures.extend(image_figures)
        
        # Strategy 2: Detect captions in text
        text_figures = self._detect_from_captions(page, page_no)
        figures.extend(text_figures)
        
        # Merge overlapping detections
        figures = self._merge_detections(figures)
        
        logger.debug(f"[{doc_id}] Page {page_no}: {len(figures)} figures/tables")
        
        return figures
    
    def _detect_from_images(
        self,
        page: fitz.Page,
        page_no: int
    ) -> List[FigureData]:
        """Detect figures from embedded images.
        
        Args:
            page: PyMuPDF page object
            page_no: Page number
            
        Returns:
            List of FigureData
        """
        figures: List[FigureData] = []
        
        # Get image list from page
        image_list = page.get_images(full=True)
        
        for img_idx, img_info in enumerate(image_list):
            xref = img_info[0]
            
            # Try to get image bbox
            try:
                img_rects = page.get_image_rects(xref)
                if img_rects:
                    rect = img_rects[0]
                    bbox = {
                        'x0': rect.x0,
                        'y0': rect.y0,
                        'x1': rect.x1,
                        'y1': rect.y1
                    }
                    
                    # Filter out very small images (likely icons)
                    width = rect.x1 - rect.x0
                    height = rect.y1 - rect.y0
                    if width < 50 or height < 50:
                        continue
                    
                    figures.append(FigureData(
                        page_no=page_no,
                        label=None,  # Will try to match with caption
                        caption=None,
                        bbox=bbox,
                        figure_type='figure',
                        confidence=0.8,
                        meta={'source': 'image_extraction', 'img_idx': img_idx}
                    ))
            except Exception as e:
                logger.debug(f"Could not get rect for image {xref}: {e}")
        
        return figures
    
    def _detect_from_captions(
        self,
        page: fitz.Page,
        page_no: int
    ) -> List[FigureData]:
        """Detect figures/tables from caption text.
        
        Args:
            page: PyMuPDF page object
            page_no: Page number
            
        Returns:
            List of FigureData
        """
        figures: List[FigureData] = []
        text = page.get_text("text")
        
        # Try caption patterns first (has both label and caption text)
        for pattern, fig_type in self.CAPTION_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                prefix = match.group(1)
                number = match.group(2)
                caption_text = match.group(3).strip()
                
                # Normalize label
                if prefix.lower().startswith('fig'):
                    label = f"Figure {number}"
                else:
                    label = f"Table {number}"
                
                # Try to find bbox for the caption text
                bbox = self._find_text_bbox(page, match.group(0)[:50])
                
                figures.append(FigureData(
                    page_no=page_no,
                    label=label,
                    caption=caption_text,
                    bbox=bbox,
                    figure_type=fig_type,
                    confidence=0.9,
                    meta={'source': 'caption_detection'}
                ))
        
        return figures
    
    def _find_text_bbox(
        self,
        page: fitz.Page,
        search_text: str
    ) -> Optional[dict]:
        """Find bounding box for text on page.
        
        Args:
            page: PyMuPDF page object
            search_text: Text to search for
            
        Returns:
            Bounding box dict or None
        """
        try:
            instances = page.search_for(search_text[:30])  # Limit search length
            if instances:
                rect = instances[0]
                return {
                    'x0': rect.x0,
                    'y0': rect.y0,
                    'x1': rect.x1,
                    'y1': rect.y1
                }
        except Exception:
            pass
        return None
    
    def _merge_detections(
        self,
        figures: List[FigureData]
    ) -> List[FigureData]:
        """Merge overlapping detections.
        
        If we have both an image detection and a caption detection that
        likely refer to the same figure, merge them.
        
        Args:
            figures: List of detected figures
            
        Returns:
            Merged list
        """
        if len(figures) < 2:
            return figures
        
        # Separate by detection source
        image_figs = [f for f in figures if f.meta.get('source') == 'image_extraction']
        caption_figs = [f for f in figures if f.meta.get('source') == 'caption_detection']
        
        merged: List[FigureData] = []
        used_images = set()
        
        # Try to match caption figures with image figures
        for cap_fig in caption_figs:
            best_match = None
            best_distance = float('inf')
            
            if cap_fig.bbox:
                for i, img_fig in enumerate(image_figs):
                    if i in used_images:
                        continue
                    if img_fig.bbox:
                        # Check if bboxes are close (within 100 pixels)
                        dist = self._bbox_distance(cap_fig.bbox, img_fig.bbox)
                        if dist < 100 and dist < best_distance:
                            best_match = i
                            best_distance = dist
            
            if best_match is not None:
                # Merge: use caption's label/caption, image's bbox
                img_fig = image_figs[best_match]
                merged.append(FigureData(
                    page_no=cap_fig.page_no,
                    label=cap_fig.label,
                    caption=cap_fig.caption,
                    bbox=img_fig.bbox,  # Use image bbox (better)
                    figure_type=cap_fig.figure_type,
                    confidence=0.95,
                    meta={'source': 'merged'}
                ))
                used_images.add(best_match)
            else:
                merged.append(cap_fig)
        
        # Add unmatched images
        for i, img_fig in enumerate(image_figs):
            if i not in used_images:
                merged.append(img_fig)
        
        return merged
    
    def _bbox_distance(self, bbox1: dict, bbox2: dict) -> float:
        """Calculate distance between two bboxes.
        
        Args:
            bbox1: First bbox
            bbox2: Second bbox
            
        Returns:
            Distance (lower = closer)
        """
        # Use center-to-center distance
        cx1 = (bbox1['x0'] + bbox1['x1']) / 2
        cy1 = (bbox1['y0'] + bbox1['y1']) / 2
        cx2 = (bbox2['x0'] + bbox2['x1']) / 2
        cy2 = (bbox2['y0'] + bbox2['y1']) / 2
        
        return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
    
    def _deduplicate(
        self,
        figures: List[FigureData]
    ) -> List[FigureData]:
        """Remove duplicate figures by label.
        
        Args:
            figures: List of figures
            
        Returns:
            Deduplicated list
        """
        seen_labels = set()
        result: List[FigureData] = []
        
        for fig in figures:
            if fig.label:
                if fig.label in seen_labels:
                    continue
                seen_labels.add(fig.label)
            result.append(fig)
        
        return result
