"""Context packer for retrieval results.

Orders and formats expanded context for LLM consumption.
Includes citations with doc_id, page_no, node_id, bbox.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from app.db.graph_models import Node, NodeType
from .expander import ExpandedContext

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """Citation for a piece of context."""
    node_id: str
    doc_id: str
    page_no: Optional[int]
    label: Optional[str]  # For figures/tables
    bbox: Optional[dict]
    source_type: str  # seed, adjacent, referenced, explained_by
    
    def to_dict(self) -> dict:
        return {
            'node_id': self.node_id,
            'doc_id': self.doc_id,
            'page_no': self.page_no,
            'label': self.label,
            'bbox': self.bbox,
            'source_type': self.source_type,
        }


@dataclass
class ContextBlock:
    """A block of context with metadata."""
    text: str
    citation: Citation
    node_type: str
    order: int  # For sorting
    
    def to_dict(self) -> dict:
        return {
            'text': self.text,
            'citation': self.citation.to_dict(),
            'node_type': self.node_type,
        }


@dataclass
class PackedContext:
    """Packed context ready for LLM."""
    blocks: List[ContextBlock]
    total_chars: int
    total_tokens_estimate: int
    
    def to_text(self, include_citations: bool = True) -> str:
        """Convert to plain text for LLM.
        
        Args:
            include_citations: Include citation markers
            
        Returns:
            Formatted text
        """
        parts = []
        
        for block in self.blocks:
            if include_citations:
                citation = block.citation
                # Emit canonical citation key first so the model can copy exact
                # [node_id:page] references into answers.
                page_no = citation.page_no if citation.page_no is not None else 0
                marker = f"[{citation.node_id}:{page_no}]"

                # Keep auxiliary metadata outside [] so citation regexes stay simple.
                meta_parts = [f"source={citation.source_type}"]
                if citation.label:
                    meta_parts.append(f"label={citation.label}")

                meta_suffix = " ".join(meta_parts)
                parts.append(f"{marker} {meta_suffix}\n{block.text}")
            else:
                parts.append(block.text)
        
        return "\n\n---\n\n".join(parts)
    
    def to_dict(self) -> dict:
        return {
            'blocks': [b.to_dict() for b in self.blocks],
            'total_chars': self.total_chars,
            'total_tokens_estimate': self.total_tokens_estimate,
        }


class ContextPacker:
    """Packs expanded context into ordered blocks."""
    
    # Estimated tokens per character
    CHARS_PER_TOKEN = 4
    
    def __init__(
        self,
        max_tokens: int = 8000,
        include_empty: bool = False
    ):
        """Initialize packer.
        
        Args:
            max_tokens: Maximum tokens in packed context
            max_tokens: Maximum total tokens
            include_empty: Include nodes with empty text
        """
        self.max_tokens = max_tokens
        self.include_empty = include_empty
    
    def pack(
        self,
        expanded: ExpandedContext,
        query: Optional[str] = None
    ) -> PackedContext:
        """Pack expanded context into ordered blocks.
        
        Order:
        1. Seed chunks (ordered by page, then chunk_index)
        2. Adjacent chunks (prev before next)
        3. Referenced figures/tables
        4. Explained_by chunks
        
        Args:
            expanded: Expanded context from GraphExpander
            query: Optional query for relevance hints
            
        Returns:
            PackedContext with ordered blocks
        """
        blocks: List[ContextBlock] = []
        order = 0
        total_chars = 0
        max_chars = self.max_tokens * self.CHARS_PER_TOKEN
        
        # 1. Seed chunks
        for node in self._sort_chunks(expanded.seed_nodes):
            block = self._create_block(node, 'seed', order)
            if block and (self.include_empty or block.text.strip()):
                if total_chars + len(block.text) <= max_chars:
                    blocks.append(block)
                    total_chars += len(block.text)
                    order += 1
        
        # 2. Adjacent chunks
        for node in self._sort_chunks(expanded.adjacent_nodes):
            block = self._create_block(node, 'adjacent', order)
            if block and (self.include_empty or block.text.strip()):
                if total_chars + len(block.text) <= max_chars:
                    blocks.append(block)
                    total_chars += len(block.text)
                    order += 1
        
        # 3. Referenced figures/tables
        for node in expanded.referenced_nodes:
            block = self._create_block(node, 'referenced', order)
            if block and (self.include_empty or block.text.strip()):
                if total_chars + len(block.text) <= max_chars:
                    blocks.append(block)
                    total_chars += len(block.text)
                    order += 1
        
        # 4. Explained_by chunks
        for node in self._sort_chunks(expanded.explained_by_nodes):
            block = self._create_block(node, 'explained_by', order)
            if block and (self.include_empty or block.text.strip()):
                if total_chars + len(block.text) <= max_chars:
                    blocks.append(block)
                    total_chars += len(block.text)
                    order += 1
        
        # Estimate tokens
        tokens_estimate = total_chars // self.CHARS_PER_TOKEN
        
        logger.info(
            f"Packed {len(blocks)} blocks, ~{tokens_estimate} tokens "
            f"(max={self.max_tokens})"
        )
        
        return PackedContext(
            blocks=blocks,
            total_chars=total_chars,
            total_tokens_estimate=tokens_estimate
        )
    
    def _sort_chunks(self, nodes: List[Node]) -> List[Node]:
        """Sort chunk nodes by page and index.
        
        Args:
            nodes: List of nodes
            
        Returns:
            Sorted list
        """
        return sorted(
            nodes,
            key=lambda n: (n.page_no or 0, n.chunk_index_in_page or 0)
        )
    
    def _create_block(
        self,
        node: Node,
        source_type: str,
        order: int
    ) -> Optional[ContextBlock]:
        """Create a context block from a node.
        
        Args:
            node: Node object
            source_type: Source type for citation
            order: Order index
            
        Returns:
            ContextBlock or None
        """
        # Prefer text_plain, fall back to text_md
        text = node.text_plain or node.text_md or ""
        
        if not text and not self.include_empty:
            return None
        
        citation = Citation(
            node_id=node.node_id,
            doc_id=node.doc_id,
            page_no=node.page_no,
            label=node.label,
            bbox=node.bbox,
            source_type=source_type
        )
        
        return ContextBlock(
            text=text,
            citation=citation,
            node_type=node.node_type.value if node.node_type else 'unknown',
            order=order
        )
    
    def pack_for_api(
        self,
        expanded: ExpandedContext,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Pack context and return API-friendly format.
        
        Args:
            expanded: Expanded context
            query: Optional query
            
        Returns:
            Dict with context and citations
        """
        packed = self.pack(expanded, query)
        
        return {
            'context_text': packed.to_text(include_citations=True),
            'blocks': packed.to_dict()['blocks'],
            'stats': {
                'total_blocks': len(packed.blocks),
                'total_chars': packed.total_chars,
                'total_tokens_estimate': packed.total_tokens_estimate,
                'seed_count': len(expanded.seed_nodes),
                'adjacent_count': len(expanded.adjacent_nodes),
                'referenced_count': len(expanded.referenced_nodes),
                'explained_by_count': len(expanded.explained_by_nodes),
            }
        }
