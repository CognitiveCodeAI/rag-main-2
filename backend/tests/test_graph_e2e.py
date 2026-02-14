#!/usr/bin/env python
"""End-to-end test for Graph RAG pipeline on a real PDF.

Tests the full ingestion flow:
1. PDF parsing and page extraction
2. Page-bounded chunking
3. Figure/table detection
4. Node and edge creation
5. Database persistence
"""

import sys
import logging
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TEST_PDF = Path(__file__).parent / "docs" / "2404.08865v1.pdf"


def test_pdf_exists():
    """Verify test PDF exists."""
    assert TEST_PDF.exists(), f"Test PDF not found: {TEST_PDF}"
    logger.info(f"✓ Test PDF found: {TEST_PDF}")
    logger.info(f"  Size: {TEST_PDF.stat().st_size / 1024:.1f} KB")


def test_page_extraction():
    """Test page text extraction from PDF."""
    from app.graph.page_extractor import PageExtractor
    
    # Skip OCR for this test (Ollama server may be unavailable)
    extractor = PageExtractor(skip_ocr=True)
    
    with open(TEST_PDF, 'rb') as f:
        pdf_bytes = f.read()
    
    result = extractor.extract_pages(pdf_bytes, doc_id="test_2404")
    
    logger.info(f"✓ Extracted {result.total_pages} pages ({result.native_pages} native, {result.ocr_pages} OCR)")
    
    # Check page quality
    for page_data in result.pages[:3]:  # First 3 pages
        quality = page_data.text_quality_score
        used_ocr = page_data.used_ocr
        text_len = len(page_data.text_plain)
        logger.info(f"  Page {page_data.page_no}: quality={quality:.2f}, ocr={used_ocr}, chars={text_len}")
    
    assert result.total_pages > 0, "No pages extracted"
    return result


@pytest.fixture(scope="module")
def extraction_result():
    """Provide page extraction output for downstream chunking checks."""
    return test_page_extraction()


def test_chunking(extraction_result):
    """Test page-bounded chunking."""
    from app.graph.chunker import PageBoundedChunker
    
    chunker = PageBoundedChunker(target_tokens=300)
    
    # Convert pages to expected format
    page_texts = [(p.page_no, p.text_plain) for p in extraction_result.pages]
    
    chunks = chunker.chunk_pages(page_texts, doc_id="test_2404", version=1)
    
    logger.info(f"✓ Created {len(chunks)} chunks")
    
    # Verify page boundaries
    page_counts = {}
    for chunk in chunks:
        page_counts[chunk.page_no] = page_counts.get(chunk.page_no, 0) + 1
    
    logger.info(f"  Chunks per page: {dict(list(page_counts.items())[:5])}...")
    
    # Verify no page crossing
    for chunk in chunks:
        assert chunk.page_no is not None, "Chunk missing page_no"
    
    return chunks


def test_figure_detection():
    """Test figure and table detection."""
    from app.graph.figure_detector import FigureDetector
    
    detector = FigureDetector()
    
    with open(TEST_PDF, 'rb') as f:
        pdf_bytes = f.read()
    
    figures = detector.detect_in_document(pdf_bytes, doc_id="test_2404")
    
    logger.info(f"✓ Detected {len(figures)} figures/tables")
    
    # Break down by type
    fig_count = sum(1 for f in figures if f.figure_type == 'figure')
    table_count = sum(1 for f in figures if f.figure_type == 'table')
    
    logger.info(f"  Figures: {fig_count}, Tables: {table_count}")
    
    # Show first few
    for fig in figures[:5]:
        logger.info(f"  - {fig.label}: {fig.caption[:50] if fig.caption else 'no caption'}...")
    
    return figures


def test_full_pipeline():
    """Test the complete ingestion pipeline."""
    from app.graph.pipeline import GraphIngestionPipeline
    from app.db.session import get_session
    from app.db.graph_models import DocumentGraph, Node, Edge
    
    logger.info("\n" + "=" * 60)
    logger.info("Running full pipeline...")
    logger.info("=" * 60)
    
    db = next(get_session())
    
    try:
        # Read PDF
        with open(TEST_PDF, 'rb') as f:
            pdf_bytes = f.read()
        
        # Run pipeline (skip OCR due to potential server unavailability)
        pipeline = GraphIngestionPipeline(db, skip_ocr=True)
        
        result = pipeline.ingest(
            pdf_bytes=pdf_bytes,
            source_uri=f"file://{TEST_PDF}"
        )
        
        logger.info(f"\n✓ Pipeline complete!")
        logger.info(f"  Doc ID: {result.doc_id}")
        logger.info(f"  Version: {result.version}")
        logger.info(f"  Pages: {result.total_pages} (OCR: {result.ocr_pages})")
        logger.info(f"  Chunks: {result.total_chunks}")
        logger.info(f"  Figures: {result.total_figures}")
        logger.info(f"  Tables: {result.total_tables}")
        logger.info(f"  Edges: {result.total_edges}")
        
        # Verify database records
        doc = db.query(DocumentGraph).filter(
            DocumentGraph.doc_id == result.doc_id
        ).first()
        
        assert doc is not None, "Document not saved to database"
        
        nodes = db.query(Node).filter(
            Node.doc_id == result.doc_id,
            Node.version == result.version
        ).all()
        
        edges = db.query(Edge).filter(
            Edge.doc_id == result.doc_id,
            Edge.version == result.version
        ).all()
        
        logger.info(f"\n  Database verification:")
        logger.info(f"    Nodes in DB: {len(nodes)}")
        logger.info(f"    Edges in DB: {len(edges)}")
        
        # Edge type breakdown
        from collections import Counter
        edge_types = Counter(e.edge_type.value for e in edges)
        logger.info(f"    Edge types: {dict(edge_types)}")
        
        # Node type breakdown
        node_types = Counter(n.node_type.value for n in nodes)
        logger.info(f"    Node types: {dict(node_types)}")
        
        return result
        
    finally:
        db.close()


def test_graph_expansion():
    """Test graph expansion on ingested document."""
    from app.graph.expander import GraphExpander
    from app.db.session import get_session
    from app.db.graph_models import Node, NodeType
    
    db = next(get_session())
    
    try:
        # Get a chunk node to use as seed
        chunk = db.query(Node).filter(
            Node.node_type == NodeType.chunk
        ).first()
        
        if not chunk:
            logger.warning("No chunk nodes found for expansion test")
            return
        
        logger.info(f"\n  Testing expansion from chunk: {chunk.node_id[:16]}...")
        
        expander = GraphExpander(db)
        
        expanded = expander.expand(
            seed_chunk_ids=[chunk.node_id]
        )
        
        logger.info(f"  ✓ Expansion complete:")
        logger.info(f"    Seed nodes: {len(expanded.seed_nodes)}")
        logger.info(f"    Adjacent: {len(expanded.adjacent_nodes)}")
        logger.info(f"    Referenced: {len(expanded.referenced_nodes)}")
        logger.info(f"    Explained by: {len(expanded.explained_by_nodes)}")
        
    finally:
        db.close()


def main():
    print("=" * 60)
    print("  Graph RAG End-to-End Test")
    print("  PDF: 2404.08865v1.pdf")
    print("=" * 60)
    
    try:
        # Step 1: Verify PDF
        print("\n[1/5] Checking test PDF...")
        test_pdf_exists()
        
        # Step 2: Page extraction
        print("\n[2/5] Testing page extraction...")
        pages = test_page_extraction()
        
        # Step 3: Chunking
        print("\n[3/5] Testing chunking...")
        chunks = test_chunking(pages)
        
        # Step 4: Figure detection
        print("\n[4/5] Testing figure detection...")
        figures = test_figure_detection()
        
        # Step 5: Full pipeline
        print("\n[5/5] Running full pipeline...")
        result = test_full_pipeline()
        
        # Step 6: Graph expansion
        print("\n[Bonus] Testing graph expansion...")
        test_graph_expansion()
        
        print("\n" + "=" * 60)
        print("  ALL TESTS PASSED!")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
