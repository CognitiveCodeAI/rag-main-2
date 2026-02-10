"""Page-bounded chunker for graph RAG.

Chunks text WITHIN each page only - never crosses page boundaries.
This ensures citations always point to a specific page.

Captures bounding box information for citation anchoring:
- Each chunk stores a merged bbox covering all its text spans
- Anchor snippets enable text search fallback for highlighting
- Page dimensions stored for coordinate normalization
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any, TYPE_CHECKING

import tiktoken

from app.config import get_settings
from .ids import compute_node_id, compute_text_hash

if TYPE_CHECKING:
    from .page_extractor import TextSpan, PageData

logger = logging.getLogger(__name__)


# Section detection patterns
SECTION_HEADER_PATTERNS = [
    # "3 Methodology", "4 Discussion", "6 Conclusion"
    (r'^\s*(\d+(?:\.\d+)?)\s+(Methodology|Method|Methods)\b', 'Methodology'),
    (r'^\s*(\d+(?:\.\d+)?)\s+(Discussion)\b', 'Discussion'),
    (r'^\s*(\d+(?:\.\d+)?)\s+(Conclusion|Conclusions)\b', 'Conclusion'),
    (r'^\s*(\d+(?:\.\d+)?)\s+(Results)\b', 'Results'),
    (r'^\s*(\d+(?:\.\d+)?)\s+(Evaluation)\b', 'Evaluation'),
    (r'^\s*(\d+(?:\.\d+)?)\s+(Introduction)\b', 'Introduction'),
    (r'^\s*(\d+(?:\.\d+)?)\s+(Related Work)\b', 'Related Work'),
    (r'^\s*(\d+(?:\.\d+)?)\s+(Background)\b', 'Background'),
    (r'^\s*(\d+(?:\.\d+)?)\s+(Experiments?)\b', 'Experiments'),
    (r'^\s*(\d+(?:\.\d+)?)\s+(Analysis)\b', 'Analysis'),
    # Appendix patterns
    (r'\b(Appendix)\s+([A-Z])\b', 'Appendix'),
    # Keyword patterns (without numbers)
    (r'^(Conclusion|Conclusions)\s*$', 'Conclusion'),
    (r'^(Discussion)\s*$', 'Discussion'),
    (r'^(Methodology|Methods?)\s*$', 'Methodology'),
]

# Keywords that strongly indicate a section even without header format
SECTION_KEYWORDS = {
    'Conclusion': ['conclusion', 'concluding', 'in conclusion', 'summary', 'final remarks'],
    'Discussion': ['discussion', 'we discuss', 'implications'],
    'Methodology': ['methodology', 'our method', 'experimental setup', 'we propose'],
    'Appendix': ['appendix', 'supplementary'],
    'Results': ['results', 'findings', 'we found', 'our results'],
    'Evaluation': ['evaluation', 'scoring', 'rubric', 'assessment'],
}


def detect_section_hint(
    text: str,
    page_no: int,
    total_pages: int,
    last_section_hint: Optional[str] = None
) -> Optional[str]:
    """Detect section hint from chunk text.
    
    Args:
        text: Chunk text content
        page_no: Current page number (1-indexed)
        total_pages: Total pages in document
        last_section_hint: Previous section hint for carry-forward
        
    Returns:
        Section hint string or None
    """
    # 1. Check for explicit section headers
    for pattern, section in SECTION_HEADER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            logger.debug(f"Section header detected: {section} on page {page_no}")
            return section
    
    # 2. Check for section keywords
    text_lower = text.lower()
    for section, keywords in SECTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                # Only return if keyword appears prominently (e.g., in first 200 chars)
                if keyword in text_lower[:200]:
                    logger.debug(f"Section keyword detected: {section} on page {page_no}")
                    return section
    
    # 3. Last pages heuristic for conclusion
    if total_pages > 0 and page_no > 0:
        relative_position = page_no / total_pages
        if relative_position >= 0.85:  # Last 15% of document
            # Strong hint toward conclusion if no other section detected
            if last_section_hint in (None, 'Discussion', 'Results'):
                return 'Conclusion'
    
    # 4. Carry forward from previous section
    if last_section_hint:
        return last_section_hint
    
    return None


@dataclass
class ChunkData:
    """Data for a single chunk."""
    page_no: int
    chunk_index_in_page: int
    text_md: str
    text_plain: str
    content_hash: str
    meta: dict = field(default_factory=dict)
    
    @property
    def token_count(self) -> int:
        """Approximate token count."""
        return self.meta.get("token_count", len(self.text_plain) // 4)
    
    @property
    def bbox(self) -> Optional[dict]:
        """Get bounding box if available."""
        return self.meta.get("bbox")
    
    @property
    def anchor_snippet(self) -> Optional[str]:
        """Get anchor snippet for text search fallback."""
        return self.meta.get("anchor_snippet")
    
    @property
    def page_size(self) -> Optional[dict]:
        """Get page dimensions if available."""
        return self.meta.get("page_size")


class PageBoundedChunker:
    """Chunks document text within page boundaries.
    
    Key invariant: NO chunk ever spans multiple pages.
    """
    
    # Sentence-ending patterns
    SENTENCE_END = re.compile(r'[.!?]\s+')
    
    # Paragraph break pattern
    PARAGRAPH_BREAK = re.compile(r'\n\s*\n')
    
    def __init__(
        self,
        target_tokens: Optional[int] = None,
        min_tokens: int = 50,
        overlap_tokens: int = 0
    ):
        """Initialize chunker.
        
        Args:
            target_tokens: Target tokens per chunk (default from config)
            min_tokens: Minimum tokens for a chunk
            overlap_tokens: Token overlap between chunks (0 for no overlap)
        """
        settings = get_settings()
        self.target_tokens = target_tokens or settings.target_chunk_tokens
        self.min_tokens = min_tokens
        self.overlap_tokens = overlap_tokens
        
        # Use cl100k_base tokenizer (GPT-4/text-embedding-3)
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None
            logger.warning("tiktoken not available, using char-based estimation")
    
    def chunk_pages(
        self,
        pages: List[Tuple[int, str]],
        doc_id: str,
        version: int,
        total_pages: Optional[int] = None,
        page_data_list: Optional[List[Any]] = None
    ) -> List[ChunkData]:
        """Chunk multiple pages.
        
        Args:
            pages: List of (page_no, text) tuples
            doc_id: Document ID for node ID generation
            version: Document version
            total_pages: Total pages in document (for section detection)
            page_data_list: Optional list of PageData objects with bbox info
            
        Returns:
            List of ChunkData for all chunks across all pages
        """
        all_chunks: List[ChunkData] = []
        last_section_hint: Optional[str] = None
        
        # Build page_no -> PageData lookup for bbox info
        page_data_map: dict = {}
        if page_data_list:
            for pd in page_data_list:
                page_data_map[pd.page_no] = pd
        
        # Determine total pages if not provided
        if total_pages is None:
            total_pages = max(p[0] for p in pages) if pages else 0
        
        for page_no, text in pages:
            # Get page data with spans if available
            page_data = page_data_map.get(page_no)
            
            page_chunks = self.chunk_page(
                page_no=page_no,
                text=text,
                doc_id=doc_id,
                version=version,
                total_pages=total_pages,
                last_section_hint=last_section_hint,
                page_data=page_data
            )
            all_chunks.extend(page_chunks)
            
            # Update last section hint from this page's chunks
            if page_chunks:
                last_section_hint = page_chunks[-1].meta.get("section_hint", last_section_hint)
            
            # Verify invariant
            for chunk in page_chunks:
                assert chunk.page_no == page_no, \
                    f"Chunk page mismatch: {chunk.page_no} != {page_no}"
        
        logger.info(
            f"Chunked {len(pages)} pages into {len(all_chunks)} chunks "
            f"(target={self.target_tokens} tokens)"
        )
        
        return all_chunks
    
    def chunk_page(
        self,
        page_no: int,
        text: str,
        doc_id: str,
        version: int,
        total_pages: int = 0,
        last_section_hint: Optional[str] = None,
        page_data: Optional[Any] = None
    ) -> List[ChunkData]:
        """Chunk a single page.
        
        Args:
            page_no: Page number (1-indexed)
            text: Page text content
            doc_id: Document ID
            version: Document version
            total_pages: Total pages in document (for section detection)
            last_section_hint: Section hint from previous page
            page_data: Optional PageData with text spans and dimensions
            
        Returns:
            List of ChunkData for this page
        """
        if not text.strip():
            logger.debug(f"Page {page_no}: empty, skipping")
            return []
        
        # Split into initial segments (paragraphs or sentences)
        segments = self._split_into_segments(text)
        
        # Merge segments into chunks of target size
        chunks: List[ChunkData] = []
        current_segments: List[str] = []
        current_tokens = 0
        current_section_hint = last_section_hint
        
        for segment in segments:
            segment_tokens = self._count_tokens(segment)
            
            # If single segment exceeds target, split it
            if segment_tokens > self.target_tokens * 1.5:
                # Flush current
                if current_segments:
                    chunks.append(self._create_chunk(
                        page_no=page_no,
                        chunk_index=len(chunks),
                        segments=current_segments,
                        doc_id=doc_id,
                        version=version,
                        total_pages=total_pages,
                        last_section_hint=current_section_hint,
                        page_data=page_data
                    ))
                    # Update section hint from created chunk
                    current_section_hint = chunks[-1].meta.get("section_hint", current_section_hint)
                    current_segments = []
                    current_tokens = 0
                
                # Split large segment
                sub_chunks = self._split_large_segment(
                    segment=segment,
                    page_no=page_no,
                    start_index=len(chunks),
                    doc_id=doc_id,
                    version=version,
                    total_pages=total_pages,
                    last_section_hint=current_section_hint,
                    page_data=page_data
                )
                chunks.extend(sub_chunks)
                if sub_chunks:
                    current_section_hint = sub_chunks[-1].meta.get("section_hint", current_section_hint)
                continue
            
            # Check if adding this segment would exceed target
            if current_tokens + segment_tokens > self.target_tokens and current_segments:
                # Create chunk from current segments
                chunks.append(self._create_chunk(
                    page_no=page_no,
                    chunk_index=len(chunks),
                    segments=current_segments,
                    doc_id=doc_id,
                    version=version,
                    total_pages=total_pages,
                    last_section_hint=current_section_hint,
                    page_data=page_data
                ))
                # Update section hint from created chunk
                current_section_hint = chunks[-1].meta.get("section_hint", current_section_hint)
                current_segments = []
                current_tokens = 0
            
            current_segments.append(segment)
            current_tokens += segment_tokens
        
        # Flush remaining
        if current_segments:
            # Don't create very small trailing chunks, merge with previous
            if current_tokens < self.min_tokens and chunks:
                # Merge with last chunk
                last_chunk = chunks[-1]
                combined_text = last_chunk.text_plain + "\n\n" + "\n\n".join(current_segments)
                chunks[-1] = self._create_chunk(
                    page_no=page_no,
                    chunk_index=len(chunks) - 1,
                    segments=[combined_text],
                    doc_id=doc_id,
                    version=version,
                    total_pages=total_pages,
                    last_section_hint=current_section_hint,
                    page_data=page_data
                )
            else:
                chunks.append(self._create_chunk(
                    page_no=page_no,
                    chunk_index=len(chunks),
                    segments=current_segments,
                    doc_id=doc_id,
                    version=version,
                    total_pages=total_pages,
                    last_section_hint=current_section_hint,
                    page_data=page_data
                ))
        
        logger.debug(f"Page {page_no}: {len(chunks)} chunks")
        
        return chunks
    
    def _split_into_segments(self, text: str) -> List[str]:
        """Split text into paragraph-level segments.
        
        Args:
            text: Page text
            
        Returns:
            List of text segments
        """
        # First split by paragraphs
        paragraphs = self.PARAGRAPH_BREAK.split(text)
        
        segments = []
        for para in paragraphs:
            para = para.strip()
            if para:
                segments.append(para)
        
        return segments
    
    def _split_large_segment(
        self,
        segment: str,
        page_no: int,
        start_index: int,
        doc_id: str,
        version: int,
        total_pages: int = 0,
        last_section_hint: Optional[str] = None,
        page_data: Optional[Any] = None
    ) -> List[ChunkData]:
        """Split a large segment into multiple chunks.
        
        Args:
            segment: Large text segment
            page_no: Page number
            start_index: Starting chunk index
            doc_id: Document ID
            version: Document version
            total_pages: Total pages in document
            last_section_hint: Section hint from previous chunk
            page_data: Optional PageData with text spans
            
        Returns:
            List of ChunkData
        """
        # Split by sentences
        sentences = self.SENTENCE_END.split(segment)
        
        chunks: List[ChunkData] = []
        current_sentences: List[str] = []
        current_tokens = 0
        current_section_hint = last_section_hint
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            sentence_tokens = self._count_tokens(sentence)
            
            if current_tokens + sentence_tokens > self.target_tokens and current_sentences:
                chunks.append(self._create_chunk(
                    page_no=page_no,
                    chunk_index=start_index + len(chunks),
                    segments=current_sentences,
                    doc_id=doc_id,
                    version=version,
                    total_pages=total_pages,
                    last_section_hint=current_section_hint,
                    page_data=page_data
                ))
                current_section_hint = chunks[-1].meta.get("section_hint", current_section_hint)
                current_sentences = []
                current_tokens = 0
            
            current_sentences.append(sentence)
            current_tokens += sentence_tokens
        
        if current_sentences:
            chunks.append(self._create_chunk(
                page_no=page_no,
                chunk_index=start_index + len(chunks),
                segments=current_sentences,
                doc_id=doc_id,
                version=version,
                total_pages=total_pages,
                last_section_hint=current_section_hint,
                page_data=page_data
            ))
        
        return chunks
    
    def _create_chunk(
        self,
        page_no: int,
        chunk_index: int,
        segments: List[str],
        doc_id: str,
        version: int,
        total_pages: int = 0,
        last_section_hint: Optional[str] = None,
        page_data: Optional[Any] = None
    ) -> ChunkData:
        """Create a ChunkData object with bbox and anchor snippet.
        
        Args:
            page_no: Page number
            chunk_index: Index within page
            segments: Text segments to combine
            doc_id: Document ID
            version: Document version
            total_pages: Total pages in document
            last_section_hint: Section hint from previous chunk
            page_data: Optional PageData with text spans and dimensions
            
        Returns:
            ChunkData object with bbox and anchor_snippet in meta
        """
        text = "\n\n".join(segments)
        text_plain = text.strip()
        text_md = text_plain  # For now, same as plain
        
        content_hash = compute_text_hash(text_plain)
        token_count = self._count_tokens(text_plain)
        
        # Detect section hint for this chunk
        section_hint = detect_section_hint(
            text=text_plain,
            page_no=page_no,
            total_pages=total_pages,
            last_section_hint=last_section_hint
        )
        
        # Create anchor snippet (first ~150 chars for text search fallback)
        anchor_snippet = text_plain[:150].strip() if text_plain else None
        
        # Build metadata
        meta = {
            "token_count": token_count,
            "char_count": len(text_plain),
            "segment_count": len(segments),
            "section_hint": section_hint,
            "anchor_snippet": anchor_snippet,
        }
        
        # Add bbox and page_size if page_data available
        if page_data:
            # Store page dimensions for coordinate normalization
            meta["page_size"] = {
                "width": page_data.width,
                "height": page_data.height
            }
            
            # Compute merged bbox from matching text spans
            bbox = self._compute_chunk_bbox(text_plain, page_data)
            if bbox:
                meta["bbox"] = bbox
        
        return ChunkData(
            page_no=page_no,
            chunk_index_in_page=chunk_index,
            text_md=text_md,
            text_plain=text_plain,
            content_hash=content_hash,
            meta=meta
        )
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text.
        
        Args:
            text: Text to count
            
        Returns:
            Token count
        """
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Fallback: ~4 chars per token
            return len(text) // 4
    
    def _compute_chunk_bbox(
        self,
        chunk_text: str,
        page_data: Any
    ) -> Optional[dict]:
        """Compute merged bounding box for chunk text from page spans.
        
        Finds text spans that overlap with chunk content and merges their
        bounding boxes into a single encompassing box.
        
        Args:
            chunk_text: The chunk's text content
            page_data: PageData with text_spans
            
        Returns:
            Merged bbox dict {x0, y0, x1, y1} or None if no spans found
        """
        if not page_data or not hasattr(page_data, 'text_spans') or not page_data.text_spans:
            return None
        
        # Normalize chunk text for matching
        chunk_text_normalized = ' '.join(chunk_text.split()).lower()
        
        # Find spans that appear in the chunk text
        matching_bboxes = []
        
        for span in page_data.text_spans:
            span_text_normalized = span.text.strip().lower()
            
            # Check if this span's text appears in the chunk
            if span_text_normalized and span_text_normalized in chunk_text_normalized:
                matching_bboxes.append(span.bbox)
        
        if not matching_bboxes:
            # Fallback: try to find spans by word overlap
            chunk_words = set(chunk_text_normalized.split())
            for span in page_data.text_spans:
                span_words = set(span.text.strip().lower().split())
                # If significant word overlap (>50% of span words)
                if span_words and len(chunk_words & span_words) > len(span_words) * 0.5:
                    matching_bboxes.append(span.bbox)
        
        if not matching_bboxes:
            return None
        
        # Merge all bounding boxes into one encompassing box
        x0 = min(bbox[0] for bbox in matching_bboxes)
        y0 = min(bbox[1] for bbox in matching_bboxes)
        x1 = max(bbox[2] for bbox in matching_bboxes)
        y1 = max(bbox[3] for bbox in matching_bboxes)
        
        return {
            "x0": round(x0, 2),
            "y0": round(y0, 2),
            "x1": round(x1, 2),
            "y1": round(y1, 2)
        }
