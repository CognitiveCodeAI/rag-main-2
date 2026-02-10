"""Ingest the trap PDF for adversarial testing."""

import sys
import logging
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Ingest the trap PDF and generate embeddings."""
    from app.graph.pipeline import GraphIngestionPipeline
    from app.db.session import session_scope
    from app.tasks.embed_nodes import embed_document_nodes_sync
    
    # Trap PDF path
    pdf_path = Path(__file__).parent.parent / "tests" / "eval" / "fixtures" / "trap_injection_test.pdf"
    
    if not pdf_path.exists():
        logger.error(f"Trap PDF not found: {pdf_path}")
        return 1
    
    logger.info("=" * 60)
    logger.info("  Trap PDF Ingestion (Adversarial Testing)")
    logger.info("=" * 60)
    
    doc_id = None
    ingest_result = None
    embed_result = None
    
    # Step 1: Ingest document
    logger.info(f"\n[STEP 1] Ingesting: {pdf_path.name}")
    
    with session_scope() as db:
        pipeline = GraphIngestionPipeline(db, skip_ocr=True)
        
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        ingest_result = pipeline.ingest(
            pdf_bytes=pdf_bytes,
            source_uri=f"file://{pdf_path}"
        )
        
        logger.info(f"  Doc ID: {ingest_result.doc_id}")
        logger.info(f"  Pages: {ingest_result.total_pages}")
        logger.info(f"  Chunks: {ingest_result.total_chunks}")
        logger.info(f"  Duplicate: {ingest_result.is_content_duplicate}")
        
        doc_id = ingest_result.doc_id
    
    logger.info("  Session closed after ingestion.")
    
    # Step 2: Generate embeddings
    logger.info(f"\n[STEP 2] Generating embeddings for {doc_id[:16]}...")
    
    with session_scope() as db:
        embed_result = embed_document_nodes_sync(
            doc_id=doc_id,
            version=1,
            db=db
        )
        
        logger.info(f"  Embedded: {embed_result['embedded']}")
        logger.info(f"  Indexed: {embed_result['indexed']}")
    
    logger.info("  Session closed after embedding.")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("  TRAP PDF INGESTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"\n  Document: {pdf_path.name}")
    logger.info(f"  Doc ID: {doc_id}")
    logger.info(f"  Chunks: {ingest_result.total_chunks}")
    logger.info(f"  Vectors indexed: {embed_result['indexed']}")
    logger.info(f"\n  Use this doc_id for adversarial questions in questions_finalboss.json")
    
    # Write doc_id to file for reference
    doc_id_file = pdf_path.parent / "trap_doc_id.txt"
    with open(doc_id_file, 'w') as f:
        f.write(doc_id)
    logger.info(f"  Doc ID saved to: {doc_id_file}")
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    logger.info(f"Exiting with code {exit_code}")
    sys.exit(exit_code)
