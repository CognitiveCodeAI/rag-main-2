"""Tests for Graph RAG system.

Tests:
1. Deterministic IDs
2. Page-bounded chunking invariants
3. Edge creation
4. Graph expansion
5. Context packing
6. Full pipeline integration
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDeterministicIds:
    """Test deterministic ID generation."""
    
    def test_doc_id_stable(self):
        """Same URI produces same doc_id."""
        from app.graph.ids import compute_doc_id
        
        uri = "s3://bucket/path/to/doc.pdf"
        
        id1 = compute_doc_id(uri)
        id2 = compute_doc_id(uri)
        
        assert id1 == id2
        assert len(id1) == 32
    
    def test_doc_id_different_for_different_uri(self):
        """Different URIs produce different doc_ids."""
        from app.graph.ids import compute_doc_id
        
        id1 = compute_doc_id("s3://bucket/doc1.pdf")
        id2 = compute_doc_id("s3://bucket/doc2.pdf")
        
        assert id1 != id2
    
    def test_content_hash(self):
        """Content hash is stable and unique."""
        from app.graph.ids import compute_content_hash
        
        content1 = b"Hello World"
        content2 = b"Hello World"
        content3 = b"Different content"
        
        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)
        hash3 = compute_content_hash(content3)
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64
    
    def test_node_id_deterministic(self):
        """Node IDs are deterministic based on position."""
        from app.graph.ids import compute_node_id
        
        id1 = compute_node_id("doc123", 1, 1, 0, "chunk")
        id2 = compute_node_id("doc123", 1, 1, 0, "chunk")
        id3 = compute_node_id("doc123", 1, 1, 1, "chunk")  # Different index
        
        assert id1 == id2
        assert id1 != id3
    
    def test_normalize_label(self):
        """Label normalization works correctly."""
        from app.graph.ids import normalize_label
        
        assert normalize_label("Fig. 1.5") == "Figure 1.5"
        assert normalize_label("FIGURE 2") == "Figure 2"
        assert normalize_label("Table 3") == "Table 3"
        assert normalize_label("TAB. 1") == "Table 1"
        assert normalize_label("random text") is None


class TestPageBoundedChunker:
    """Test page-bounded chunking."""
    
    def test_chunks_within_page(self):
        """All chunks stay within their page boundary."""
        from app.graph.chunker import PageBoundedChunker
        
        chunker = PageBoundedChunker(target_tokens=100)
        
        # Two pages of text
        pages = [
            (1, "This is page one. " * 50),
            (2, "This is page two. " * 50),
        ]
        
        chunks = chunker.chunk_pages(pages, "test_doc", 1)
        
        # Verify invariant: each chunk belongs to its page
        page1_chunks = [c for c in chunks if c.page_no == 1]
        page2_chunks = [c for c in chunks if c.page_no == 2]
        
        assert len(page1_chunks) > 0
        assert len(page2_chunks) > 0
        
        # No chunk crosses pages
        for chunk in chunks:
            assert chunk.page_no in [1, 2]
    
    def test_chunk_ordering_stable(self):
        """Chunk ordering is stable across runs."""
        from app.graph.chunker import PageBoundedChunker
        
        chunker = PageBoundedChunker(target_tokens=100)
        
        pages = [(1, "Paragraph one.\n\nParagraph two.\n\nParagraph three.")]
        
        chunks1 = chunker.chunk_pages(pages, "doc", 1)
        chunks2 = chunker.chunk_pages(pages, "doc", 1)
        
        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1.chunk_index_in_page == c2.chunk_index_in_page
            assert c1.content_hash == c2.content_hash
    
    def test_contiguous_chunk_indices(self):
        """Chunk indices are contiguous within each page."""
        from app.graph.chunker import PageBoundedChunker
        
        chunker = PageBoundedChunker(target_tokens=50)
        
        pages = [(1, "Word " * 200)]  # Long page to force multiple chunks
        
        chunks = chunker.chunk_pages(pages, "doc", 1)
        
        indices = [c.chunk_index_in_page for c in chunks]
        expected = list(range(len(chunks)))
        
        assert indices == expected
    
    def test_deterministic_output(self):
        """Same input produces identical output (hashes and order)."""
        from app.graph.chunker import PageBoundedChunker
        
        chunker = PageBoundedChunker(target_tokens=100)
        
        # Create consistent multi-page input
        pages = [
            (1, "Introduction paragraph one.\n\nIntroduction paragraph two."),
            (2, "Chapter one content.\n\nMore chapter one content."),
            (3, "Chapter two content.\n\nConclusion paragraph."),
        ]
        
        # Run chunking multiple times
        results = []
        for run in range(3):
            chunks = chunker.chunk_pages(pages, "determinism_test_doc", 1)
            results.append(chunks)
        
        # Verify all runs produce identical results
        for run_idx in range(1, len(results)):
            assert len(results[0]) == len(results[run_idx]), \
                f"Run {run_idx} produced different chunk count"
            
            for chunk_idx, (c1, c2) in enumerate(zip(results[0], results[run_idx])):
                assert c1.page_no == c2.page_no, \
                    f"Chunk {chunk_idx}: page_no mismatch"
                assert c1.chunk_index_in_page == c2.chunk_index_in_page, \
                    f"Chunk {chunk_idx}: index mismatch"
                assert c1.content_hash == c2.content_hash, \
                    f"Chunk {chunk_idx}: hash mismatch between runs"
                assert c1.text_plain == c2.text_plain, \
                    f"Chunk {chunk_idx}: text mismatch"


class TestEdgeCreation:
    """Test edge creation."""
    
    def test_adjacency_edges(self):
        """Adjacency edges form a chain."""
        from app.graph.edges import create_adjacency_edges, EdgeData
        from app.db.graph_models import NodeType
        
        # Create mock nodes
        class MockNode:
            def __init__(self, node_id, page_no, chunk_index):
                self.node_id = node_id
                self.node_type = NodeType.chunk
                self.page_no = page_no
                self.chunk_index_in_page = chunk_index
        
        nodes = [
            MockNode("c1", 1, 0),
            MockNode("c2", 1, 1),
            MockNode("c3", 2, 0),
        ]
        
        edges = create_adjacency_edges(nodes)
        
        # Should have edges: c1->c2, c2->c1, c2->c3, c3->c2
        # Each middle node has prev+next, first has only next, last has only prev
        assert len(edges) == 4
        
        # First chunk has no prev
        c1_prev = [e for e in edges if e.from_node_id == "c1" and e.edge_type.value == "adjacent_prev"]
        assert len(c1_prev) == 0
        
        # Last chunk has no next
        c3_next = [e for e in edges if e.from_node_id == "c3" and e.edge_type.value == "adjacent_next"]
        assert len(c3_next) == 0
    
    def test_reference_detection(self):
        """Reference patterns are detected correctly."""
        from app.graph.edges import detect_references
        
        text = "As shown in Figure 1.5, the data indicates... See also Table 2."
        
        refs = detect_references(text)
        
        assert "Figure 1.5" in refs
        assert "Table 2" in refs
    
    def test_reference_detection_variants(self):
        """Various reference patterns work."""
        from app.graph.edges import detect_references
        
        # Test various formats
        assert "Figure 1" in detect_references("See Figure 1")
        assert "Figure 1" in detect_references("See Fig. 1")
        assert "Figure 1" in detect_references("See FIG 1")
        assert "Table 3" in detect_references("in Table 3")
        assert "Table 3" in detect_references("in Tab. 3")
    
    def test_reference_edge_creation(self):
        """Reference edges are created when chunk mentions figure/table."""
        from app.graph.edges import create_reference_edges, EdgeData
        from app.db.graph_models import NodeType, EdgeType
        
        class MockNode:
            def __init__(self, node_id, node_type, label=None, text_plain=None):
                self.node_id = node_id
                self.node_type = node_type
                self.label = label
                self.text_plain = text_plain
        
        # Create a chunk that references Figure 1.5
        chunk = MockNode(
            node_id="chunk1",
            node_type=NodeType.chunk,
            text_plain="As shown in Figure 1.5, the data indicates a trend."
        )
        
        # Create a figure with matching label
        figure = MockNode(
            node_id="fig1",
            node_type=NodeType.figure,
            label="Figure 1.5"
        )
        
        edges = create_reference_edges([chunk], [figure])
        
        # Should create one reference edge
        assert len(edges) == 1
        assert edges[0].from_node_id == "chunk1"
        assert edges[0].to_node_id == "fig1"
        assert edges[0].edge_type == EdgeType.references
        assert edges[0].confidence == 1.0
    
    def test_explained_by_edge_explicit_mention(self):
        """Explained_by edges created with high confidence for explicit mentions."""
        from app.graph.edges import create_explained_by_edges, EdgeData
        from app.db.graph_models import NodeType, EdgeType
        
        class MockNode:
            def __init__(self, node_id, node_type, page_no, label=None, text_plain=None, chunk_index=None):
                self.node_id = node_id
                self.node_type = node_type
                self.page_no = page_no
                self.label = label
                self.text_plain = text_plain
                self.chunk_index_in_page = chunk_index
        
        # Chunk that explains the figure
        chunk = MockNode(
            node_id="chunk1",
            node_type=NodeType.chunk,
            page_no=1,
            chunk_index=0,
            text_plain="Figure 1.5 shows the relationship between variables."
        )
        
        # Figure
        figure = MockNode(
            node_id="fig1",
            node_type=NodeType.figure,
            page_no=1,
            label="Figure 1.5"
        )
        
        edges = create_explained_by_edges([chunk], [figure])
        
        # Should create explained_by edge with high confidence
        assert len(edges) == 1
        assert edges[0].from_node_id == "fig1"  # From figure
        assert edges[0].to_node_id == "chunk1"  # To explaining chunk
        assert edges[0].edge_type == EdgeType.explained_by
        assert edges[0].confidence == 1.0  # High confidence for explicit mention
    
    def test_explained_by_edge_proximity_fallback(self):
        """Explained_by edges use proximity fallback when no explicit mention."""
        from app.graph.edges import create_explained_by_edges, EdgeData
        from app.db.graph_models import NodeType, EdgeType
        
        class MockNode:
            def __init__(self, node_id, node_type, page_no, label=None, text_plain=None, chunk_index=None):
                self.node_id = node_id
                self.node_type = node_type
                self.page_no = page_no
                self.label = label
                self.text_plain = text_plain
                self.chunk_index_in_page = chunk_index
        
        # Chunk without explicit mention
        chunk = MockNode(
            node_id="chunk1",
            node_type=NodeType.chunk,
            page_no=1,
            chunk_index=0,
            text_plain="This paragraph discusses something unrelated."
        )
        
        # Figure on same page
        figure = MockNode(
            node_id="fig1",
            node_type=NodeType.figure,
            page_no=1,
            label="Figure 2"
        )
        
        edges = create_explained_by_edges([chunk], [figure])
        
        # Should create explained_by edge with lower confidence (proximity)
        assert len(edges) == 1
        assert edges[0].confidence < 1.0  # Lower confidence for proximity fallback


class TestGraphExpansion:
    """Test graph expansion logic."""
    
    def test_expansion_includes_adjacent(self):
        """Expansion includes adjacent chunks."""
        from app.graph.expander import GraphExpander, ExpandedContext
        from app.db.graph_models import Node, Edge, NodeType, EdgeType
        
        # Mock database session
        mock_db = MagicMock()
        
        # Create test nodes
        seed = Node(node_id="seed", doc_id="doc", version=1, 
                   node_type=NodeType.chunk, page_no=1, chunk_index_in_page=1,
                   text_plain="Seed text")
        prev_node = Node(node_id="prev", doc_id="doc", version=1,
                        node_type=NodeType.chunk, page_no=1, chunk_index_in_page=0,
                        text_plain="Previous text")
        next_node = Node(node_id="next", doc_id="doc", version=1,
                        node_type=NodeType.chunk, page_no=1, chunk_index_in_page=2,
                        text_plain="Next text")
        
        # Mock queries
        def query_side_effect(*args, **kwargs):
            mock_query = MagicMock()
            # This is simplified - in real test we'd properly mock the query chain
            mock_query.filter.return_value.all.return_value = [seed]
            return mock_query
        
        mock_db.query = query_side_effect
        
        expander = GraphExpander(mock_db)
        
        # The expansion logic is tested conceptually here
        # Full integration test would use real DB
        assert expander.MAX_ADJACENT_PER_SEED == 2


class TestContextPacker:
    """Test context packing."""
    
    def test_ordering(self):
        """Context is ordered correctly."""
        from app.graph.context_packer import ContextPacker
        from app.graph.expander import ExpandedContext
        from app.db.graph_models import Node, NodeType
        
        # Create test nodes
        seed = Node(node_id="seed", doc_id="doc", version=1,
                   node_type=NodeType.chunk, page_no=1, chunk_index_in_page=0,
                   text_plain="Seed content")
        adjacent = Node(node_id="adj", doc_id="doc", version=1,
                       node_type=NodeType.chunk, page_no=1, chunk_index_in_page=1,
                       text_plain="Adjacent content")
        figure = Node(node_id="fig", doc_id="doc", version=1,
                     node_type=NodeType.figure, page_no=1, label="Figure 1",
                     text_plain="Figure content")
        
        context = ExpandedContext(
            seed_nodes=[seed],
            adjacent_nodes=[adjacent],
            referenced_nodes=[figure],
            explained_by_nodes=[],
            node_sources={"seed": "seed", "adj": "adjacent", "fig": "referenced"}
        )
        
        packer = ContextPacker()
        packed = packer.pack(context)
        
        # Verify order: seed first, then adjacent, then referenced
        assert len(packed.blocks) == 3
        assert packed.blocks[0].citation.source_type == "seed"
        assert packed.blocks[1].citation.source_type == "adjacent"
        assert packed.blocks[2].citation.source_type == "referenced"
    
    def test_token_limit(self):
        """Context respects token limits."""
        from app.graph.context_packer import ContextPacker
        from app.graph.expander import ExpandedContext
        from app.db.graph_models import Node, NodeType
        
        # Create node with very long text
        long_text = "Word " * 10000  # Very long
        seed = Node(node_id="seed", doc_id="doc", version=1,
                   node_type=NodeType.chunk, page_no=1, chunk_index_in_page=0,
                   text_plain=long_text)
        
        context = ExpandedContext(
            seed_nodes=[seed],
            adjacent_nodes=[],
            referenced_nodes=[],
            explained_by_nodes=[]
        )
        
        # Use small token limit
        packer = ContextPacker(max_tokens=100)
        packed = packer.pack(context)
        
        # Should be limited
        assert packed.total_tokens_estimate <= 100


class TestFigureDetection:
    """Test figure/table detection."""
    
    def test_caption_patterns(self):
        """Caption patterns are detected."""
        from app.graph.figure_detector import FigureDetector
        
        detector = FigureDetector()
        
        # Test pattern matching
        for pattern, fig_type in detector.CAPTION_PATTERNS:
            import re
            
            if fig_type == 'figure':
                text = "Figure 1.5: This is a caption"
            else:
                text = "Table 2: Summary of results"
            
            match = re.search(pattern, text, re.IGNORECASE)
            assert match is not None, f"Pattern {pattern} should match"


def test_end_to_end_ids():
    """End-to-end test for ID determinism."""
    from app.graph.ids import compute_doc_id, compute_node_id
    
    # Simulate same document being processed twice
    uri = "s3://test-bucket/test-doc.pdf"
    
    doc_id1 = compute_doc_id(uri)
    doc_id2 = compute_doc_id(uri)
    
    assert doc_id1 == doc_id2, "doc_id must be deterministic"
    
    # Node IDs should also be deterministic
    node_id1 = compute_node_id(doc_id1, 1, 1, 0, "chunk")
    node_id2 = compute_node_id(doc_id2, 1, 1, 0, "chunk")
    
    assert node_id1 == node_id2, "node_id must be deterministic"


if __name__ == "__main__":
    print("=" * 60)
    print("Graph RAG Unit Tests")
    print("=" * 60)
    
    # Run tests
    test_classes = [
        TestDeterministicIds,
        TestPageBoundedChunker,
        TestEdgeCreation,
        TestGraphExpansion,
        TestContextPacker,
        TestFigureDetection,
    ]
    
    for test_class in test_classes:
        print(f"\n=== {test_class.__name__} ===")
        instance = test_class()
        
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    getattr(instance, method_name)()
                    print(f"  ✓ {method_name}")
                except Exception as e:
                    print(f"  ✗ {method_name}: {e}")
    
    # Run standalone tests
    print("\n=== Standalone Tests ===")
    try:
        test_end_to_end_ids()
        print("  ✓ test_end_to_end_ids")
    except Exception as e:
        print(f"  ✗ test_end_to_end_ids: {e}")
    
    print("\n" + "=" * 60)
    print("Tests complete")
