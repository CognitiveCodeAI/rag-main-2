"""Edge creation for graph RAG.

Creates edges between nodes:
- adjacent_prev/adjacent_next: Sequential chunk ordering
- references: Chunk references figure/table
- explained_by: Figure/table explained by chunk
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Set

from app.db.graph_models import Node, Edge, EdgeType, NodeType

logger = logging.getLogger(__name__)


@dataclass
class EdgeData:
    """Data for creating an edge."""
    from_node_id: str
    to_node_id: str
    edge_type: EdgeType
    confidence: float = 1.0


def create_adjacency_edges(nodes: List[Node]) -> List[EdgeData]:
    """Create adjacent_prev/adjacent_next edges for ordered chunks.
    
    Chunks are ordered by (page_no, chunk_index_in_page).
    Each chunk gets edges to its immediate neighbors.
    
    Args:
        nodes: List of Node objects
        
    Returns:
        List of EdgeData for adjacency edges
    """
    # Filter to chunks only and sort
    chunks = sorted(
        [n for n in nodes if n.node_type == NodeType.chunk],
        key=lambda n: (n.page_no or 0, n.chunk_index_in_page or 0)
    )
    
    if len(chunks) < 2:
        return []
    
    edges: List[EdgeData] = []
    
    for i, chunk in enumerate(chunks):
        # Previous edge (chunk -> prev)
        if i > 0:
            edges.append(EdgeData(
                from_node_id=chunk.node_id,
                to_node_id=chunks[i - 1].node_id,
                edge_type=EdgeType.adjacent_prev,
                confidence=1.0
            ))
        
        # Next edge (chunk -> next)
        if i < len(chunks) - 1:
            edges.append(EdgeData(
                from_node_id=chunk.node_id,
                to_node_id=chunks[i + 1].node_id,
                edge_type=EdgeType.adjacent_next,
                confidence=1.0
            ))
    
    logger.info(f"Created {len(edges)} adjacency edges for {len(chunks)} chunks")
    
    return edges


# Reference patterns for figure/table detection
REFERENCE_PATTERNS = [
    # Figure references
    (r'(?:Figure|Fig\.?)\s*(\d+(?:\.\d+)?)', 'Figure'),
    # Table references
    (r'(?:Table|Tab\.?)\s*(\d+(?:\.\d+)?)', 'Table'),
]


def detect_references(text: str) -> List[str]:
    """Detect figure/table references in text.
    
    Args:
        text: Text to search for references
        
    Returns:
        List of normalized labels: ['Figure 1.5', 'Table 2']
    """
    references: Set[str] = set()
    
    for pattern, label_type in REFERENCE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            number = match.group(1)
            normalized = f"{label_type} {number}"
            references.add(normalized)
    
    return list(references)


def create_reference_edges(
    chunks: List[Node],
    figures_tables: List[Node]
) -> List[EdgeData]:
    """Create reference edges from chunks to figures/tables.
    
    Scans chunk text for references like "Figure 1.5" and creates
    edges to the corresponding figure/table node.
    
    Args:
        chunks: List of chunk nodes
        figures_tables: List of figure and table nodes
        
    Returns:
        List of EdgeData for reference edges
    """
    # Build label -> node mapping
    label_to_node: Dict[str, Node] = {}
    for node in figures_tables:
        if node.label:
            label_to_node[node.label] = node
    
    if not label_to_node:
        return []
    
    edges: List[EdgeData] = []
    
    for chunk in chunks:
        if not chunk.text_plain:
            continue
        
        # Find references in chunk text
        refs = detect_references(chunk.text_plain)
        
        for ref_label in refs:
            if ref_label in label_to_node:
                target_node = label_to_node[ref_label]
                edges.append(EdgeData(
                    from_node_id=chunk.node_id,
                    to_node_id=target_node.node_id,
                    edge_type=EdgeType.references,
                    confidence=1.0  # High confidence for exact label match
                ))
    
    logger.info(f"Created {len(edges)} reference edges")
    
    return edges


# Explanation patterns (chunk explains figure)
EXPLANATION_PATTERNS = [
    r'(?:Figure|Fig\.?)\s*(\d+(?:\.\d+)?)\s+(?:shows?|illustrates?|depicts?|presents?|displays?)',
    r'(?:as\s+)?(?:shown|illustrated|depicted)\s+in\s+(?:Figure|Fig\.?)\s*(\d+(?:\.\d+)?)',
    r'(?:Table|Tab\.?)\s*(\d+(?:\.\d+)?)\s+(?:shows?|lists?|presents?|summarizes?|contains?)',
    r'(?:as\s+)?(?:shown|listed|presented)\s+in\s+(?:Table|Tab\.?)\s*(\d+(?:\.\d+)?)',
]


def create_explained_by_edges(
    chunks: List[Node],
    figures_tables: List[Node]
) -> List[EdgeData]:
    """Create explained_by edges from figures/tables to explaining chunks.
    
    Heuristic:
    1. High confidence: Chunk contains "Figure X shows/illustrates/depicts"
    2. Medium confidence: Nearest chunk after the figure on same page
    3. Low confidence: First chunk on next page if no chunk after on same page
    
    Args:
        chunks: List of chunk nodes, sorted by (page_no, chunk_index_in_page)
        figures_tables: List of figure and table nodes
        
    Returns:
        List of EdgeData for explained_by edges
    """
    # Sort chunks by position
    sorted_chunks = sorted(
        chunks,
        key=lambda n: (n.page_no or 0, n.chunk_index_in_page or 0)
    )
    
    # Build page -> chunks mapping
    page_chunks: Dict[int, List[Node]] = {}
    for chunk in sorted_chunks:
        page = chunk.page_no or 0
        if page not in page_chunks:
            page_chunks[page] = []
        page_chunks[page].append(chunk)
    
    edges: List[EdgeData] = []
    
    for fig_node in figures_tables:
        explaining_chunk = None
        confidence = 0.0
        
        fig_page = fig_node.page_no or 0
        fig_label = fig_node.label or ""
        
        # Strategy 1: Find explicit explanation
        for chunk in sorted_chunks:
            if not chunk.text_plain:
                continue
            
            for pattern in EXPLANATION_PATTERNS:
                match = re.search(pattern, chunk.text_plain, re.IGNORECASE)
                if match:
                    ref_number = match.group(1)
                    if fig_label.endswith(ref_number):
                        explaining_chunk = chunk
                        confidence = 1.0
                        break
            
            if confidence == 1.0:
                break
        
        # Strategy 2: Nearest chunk after figure on same page
        if not explaining_chunk and fig_page in page_chunks:
            page_chunk_list = page_chunks[fig_page]
            for chunk in page_chunk_list:
                # Chunk should be after the figure (heuristic based on chunk_index)
                explaining_chunk = chunk
                confidence = 0.7
                break  # Take first chunk on page as fallback
        
        # Strategy 3: First chunk on next page
        if not explaining_chunk:
            next_page = fig_page + 1
            if next_page in page_chunks and page_chunks[next_page]:
                explaining_chunk = page_chunks[next_page][0]
                confidence = 0.5
        
        if explaining_chunk:
            edges.append(EdgeData(
                from_node_id=fig_node.node_id,
                to_node_id=explaining_chunk.node_id,
                edge_type=EdgeType.explained_by,
                confidence=confidence
            ))
    
    logger.info(f"Created {len(edges)} explained_by edges")
    
    return edges


def create_all_edges(
    nodes: List[Node],
    doc_id: str,
    version: int
) -> List[Edge]:
    """Create all edges for a document.
    
    Args:
        nodes: All nodes in the document
        doc_id: Document ID
        version: Document version
        
    Returns:
        List of Edge objects ready for insertion
    """
    # Separate node types
    chunks = [n for n in nodes if n.node_type == NodeType.chunk]
    figures_tables = [n for n in nodes if n.node_type in (NodeType.figure, NodeType.table)]
    
    # Collect all edge data
    edge_data: List[EdgeData] = []
    
    # Adjacency edges
    edge_data.extend(create_adjacency_edges(nodes))
    
    # Reference edges
    edge_data.extend(create_reference_edges(chunks, figures_tables))
    
    # Explained_by edges
    edge_data.extend(create_explained_by_edges(chunks, figures_tables))
    
    # Convert to Edge objects
    edges = [
        Edge(
            doc_id=doc_id,
            version=version,
            from_node_id=ed.from_node_id,
            to_node_id=ed.to_node_id,
            edge_type=ed.edge_type,
            confidence=ed.confidence
        )
        for ed in edge_data
    ]
    
    logger.info(f"Created {len(edges)} total edges for doc {doc_id} v{version}")
    
    return edges
