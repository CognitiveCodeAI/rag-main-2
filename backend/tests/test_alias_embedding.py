"""Validation tests for content registry alias behavior and embedding.

Tests:
1. Ingest same PDF twice with different source_uri
2. Verify canonical_doc_id matches and is_content_duplicate=True
3. Confirm no duplicate nodes/edges (only alias record)
4. Run embed job, confirm only v2 collections used
5. Confirm embedded_collection_version="v2" on document
"""

import os
import pytest
from pathlib import Path

from app.db.session import get_session
from app.db.graph_models import DocumentGraph, Node, Edge, ContentRegistry
from app.graph.pipeline import GraphIngestionPipeline
from app.tasks.embed_nodes import embed_document_nodes_sync
from app.graph.vector_index import GraphVectorIndex


# Test file path
TEST_PDF = Path(__file__).parent / "docs" / "2404.08865v1.pdf"


class TestAliasEmbeddingBehavior:
    """Test suite for alias and embedding behavior."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.db = next(get_session())
        
        # Clean up any previous test data
        self._cleanup_test_data()
        
        yield
        
        # Cleanup after test
        self._cleanup_test_data()
        self.db.close()
    
    def _cleanup_test_data(self):
        """Remove test documents from previous runs."""
        from app.graph.ids import compute_content_hash
        
        # First, clean up content_registry for the test PDF
        if TEST_PDF.exists():
            test_content_hash = compute_content_hash(TEST_PDF.read_bytes())
            self.db.query(ContentRegistry).filter(
                ContentRegistry.content_hash == test_content_hash
            ).delete()
        
        # Delete test documents by source_uri pattern
        test_docs = self.db.query(DocumentGraph).filter(
            DocumentGraph.source_uri.like("%test_alias_%")
        ).all()
        
        for doc in test_docs:
            # Delete from content_registry (in case different content)
            self.db.query(ContentRegistry).filter(
                ContentRegistry.content_hash == doc.content_hash
            ).delete()
            
            # Delete edges
            self.db.query(Edge).filter(Edge.doc_id == doc.doc_id).delete()
            
            # Delete nodes
            self.db.query(Node).filter(Node.doc_id == doc.doc_id).delete()
            
            # Delete document
            self.db.delete(doc)
        
        self.db.commit()
    
    def test_same_content_different_uri_creates_alias(self):
        """Test that same content with different URI creates an alias, not duplicate."""
        
        if not TEST_PDF.exists():
            pytest.skip(f"Test PDF not found: {TEST_PDF}")
        
        pdf_bytes = TEST_PDF.read_bytes()
        
        # First ingestion - should be canonical
        pipeline1 = GraphIngestionPipeline(self.db, skip_ocr=True)
        result1 = pipeline1.ingest(
            pdf_bytes=pdf_bytes,
            source_uri="file:///test_alias_original.pdf"
        )
        
        print(f"\n=== First Ingestion ===")
        print(f"doc_id: {result1.doc_id}")
        print(f"canonical_doc_id: {result1.canonical_doc_id}")
        print(f"is_content_duplicate: {result1.is_content_duplicate}")
        print(f"total_chunks: {result1.total_chunks}")
        print(f"total_figures: {result1.total_figures}")
        print(f"total_edges: {result1.total_edges}")
        
        # Assertions for first ingestion
        assert result1.is_new is True
        assert result1.is_content_duplicate is False
        assert result1.doc_id == result1.canonical_doc_id  # First is its own canonical
        assert result1.total_chunks > 0
        
        # Second ingestion with different URI - should be alias
        # Use a fresh pipeline to simulate separate ingestion
        self.db.expire_all()  # Clear cache
        pipeline2 = GraphIngestionPipeline(self.db, skip_ocr=True)
        result2 = pipeline2.ingest(
            pdf_bytes=pdf_bytes,
            source_uri="file:///test_alias_copy.pdf"  # Different URI
        )
        
        print(f"\n=== Second Ingestion (Alias) ===")
        print(f"doc_id: {result2.doc_id}")
        print(f"canonical_doc_id: {result2.canonical_doc_id}")
        print(f"is_content_duplicate: {result2.is_content_duplicate}")
        print(f"total_chunks: {result2.total_chunks}")
        print(f"total_figures: {result2.total_figures}")
        print(f"total_edges: {result2.total_edges}")
        
        # Assertions for second ingestion (alias)
        assert result2.is_new is True  # The alias record is new
        assert result2.is_content_duplicate is True  # But content is duplicate
        assert result2.canonical_doc_id == result1.doc_id  # Points to original
        assert result2.doc_id != result1.doc_id  # Different doc_id (different URI)
        
        # CRITICAL: Alias should NOT create new nodes/edges
        assert result2.total_chunks == 0, "Alias should not create new chunks"
        assert result2.total_figures == 0, "Alias should not create new figures"
        assert result2.total_edges == 0, "Alias should not create new edges"
        
        # Verify database state
        nodes_for_alias = self.db.query(Node).filter(
            Node.doc_id == result2.doc_id
        ).count()
        assert nodes_for_alias == 0, f"Alias should have 0 nodes, found {nodes_for_alias}"
        
        edges_for_alias = self.db.query(Edge).filter(
            Edge.doc_id == result2.doc_id
        ).count()
        assert edges_for_alias == 0, f"Alias should have 0 edges, found {edges_for_alias}"
        
        # Verify alias document record exists with correct metadata
        alias_doc = self.db.query(DocumentGraph).filter(
            DocumentGraph.doc_id == result2.doc_id
        ).first()
        
        assert alias_doc is not None
        assert alias_doc.canonical_doc_id == result1.doc_id
        assert alias_doc.meta.get('is_alias') is True
        
        print("\n=== Alias Test PASSED ===")
        print(f"Canonical doc_id: {result1.doc_id}")
        print(f"Alias doc_id: {result2.doc_id}")
        print(f"Canonical nodes: {result1.total_chunks + result1.total_figures}")
        print(f"Alias nodes: 0 (reusing canonical)")
    
    def test_embedding_skips_alias_documents(self):
        """Test that embedding job skips alias documents."""
        
        if not TEST_PDF.exists():
            pytest.skip(f"Test PDF not found: {TEST_PDF}")
        
        pdf_bytes = TEST_PDF.read_bytes()
        
        # First ingestion - canonical
        pipeline = GraphIngestionPipeline(self.db, skip_ocr=True)
        result1 = pipeline.ingest(
            pdf_bytes=pdf_bytes,
            source_uri="file:///test_alias_embed_original.pdf"
        )
        
        # Second ingestion - alias
        self.db.expire_all()
        result2 = pipeline.ingest(
            pdf_bytes=pdf_bytes,
            source_uri="file:///test_alias_embed_copy.pdf"
        )
        
        assert result2.is_content_duplicate is True
        
        # Try to embed the alias document - should skip
        embed_result = embed_document_nodes_sync(
            doc_id=result2.doc_id,
            version=result2.version,
            db=self.db
        )
        
        print(f"\n=== Embedding Alias Result ===")
        print(f"Status: {embed_result['status']}")
        print(f"Result: {embed_result}")
        
        # Alias embedding should be skipped
        assert embed_result["status"] == "skipped_alias"
        assert embed_result["canonical_doc_id"] == result1.doc_id
        
        print("\n=== Embedding Skip Test PASSED ===")
    
    def test_canonical_embedding_uses_v2_collections(self):
        """Test that canonical document embedding uses v2 collections."""
        
        if not TEST_PDF.exists():
            pytest.skip(f"Test PDF not found: {TEST_PDF}")
        
        pdf_bytes = TEST_PDF.read_bytes()
        
        # Ingest canonical document
        pipeline = GraphIngestionPipeline(self.db, skip_ocr=True)
        result = pipeline.ingest(
            pdf_bytes=pdf_bytes,
            source_uri="file:///test_alias_v2_check.pdf"
        )
        
        assert result.is_content_duplicate is False
        
        # Embed the canonical document
        embed_result = embed_document_nodes_sync(
            doc_id=result.doc_id,
            version=result.version,
            db=self.db
        )
        
        print(f"\n=== Canonical Embedding Result ===")
        print(f"Status: {embed_result['status']}")
        print(f"Collection version: {embed_result.get('collection_version')}")
        print(f"Embedded: {embed_result.get('embedded')}")
        print(f"Indexed: {embed_result.get('indexed')}")
        
        # Should use v2 collections
        assert embed_result["status"] == "completed"
        assert embed_result["collection_version"] == "v2"
        
        # Verify document has embedded_collection_version set
        self.db.expire_all()
        doc = self.db.query(DocumentGraph).filter(
            DocumentGraph.doc_id == result.doc_id
        ).first()
        
        assert doc.embedded_collection_version == "v2", \
            f"Expected v2, got {doc.embedded_collection_version}"
        
        print("\n=== V2 Collection Test PASSED ===")
        print(f"embedded_collection_version: {doc.embedded_collection_version}")


def run_validation():
    """Run validation tests directly."""
    print("=" * 60)
    print("Content Registry + Alias + Embedding Validation")
    print("=" * 60)
    
    db = next(get_session())
    
    try:
        # Run tests
        test = TestAliasEmbeddingBehavior()
        test.db = db
        test._cleanup_test_data()
        
        print("\n1. Testing alias creation...")
        test.test_same_content_different_uri_creates_alias()
        test._cleanup_test_data()
        
        print("\n2. Testing embedding skip for aliases...")
        test.test_embedding_skips_alias_documents()
        test._cleanup_test_data()
        
        print("\n3. Testing v2 collection usage...")
        test.test_canonical_embedding_uses_v2_collections()
        test._cleanup_test_data()
        
        print("\n" + "=" * 60)
        print("ALL VALIDATION TESTS PASSED!")
        print("=" * 60)
        
    finally:
        db.close()


if __name__ == "__main__":
    run_validation()
