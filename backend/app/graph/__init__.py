"""Graph RAG module for page-bounded chunking and figure/table extraction.

Main components:
- ids: Deterministic ID generation
- page_extractor: PDF page extraction with OCR fallback
- chunker: Page-bounded text chunking
- figure_detector: Figure/table detection
- nodes: Node creation
- edges: Edge creation (adjacency, references, explained_by)
- expander: Graph expansion at retrieval time
- context_packer: Context ordering for LLM
- pipeline: Full ingestion pipeline
"""

from .ids import (
    compute_doc_id,
    compute_content_hash,
    compute_node_id,
    compute_text_hash,
    normalize_label,
    IdempotencyChecker,
)

from .page_extractor import PageExtractor, PageData, ExtractionResult
from .chunker import PageBoundedChunker, ChunkData
from .figure_detector import FigureDetector, FigureData
from .nodes import create_chunk_nodes, create_figure_nodes
from .edges import (
    create_adjacency_edges,
    create_reference_edges,
    create_explained_by_edges,
    create_all_edges,
    detect_references,
    EdgeData,
)
from .expander import GraphExpander, ExpandedContext
from .context_packer import ContextPacker, PackedContext, ContextBlock, Citation
