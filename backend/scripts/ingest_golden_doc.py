"""Ingest the golden questions test document for evaluation."""

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
    """Ingest the golden questions document and generate embeddings."""
    from app.graph.pipeline import GraphIngestionPipeline
    from app.db.session import session_scope
    from app.tasks.embed_nodes import embed_document_nodes_sync
    
    # Document path - use 2025 FDD.pdf for final testing
    pdf_path = Path(__file__).parent.parent.parent / "2025 FDD.pdf"
    
    if not pdf_path.exists():
        logger.error(f"Document not found: {pdf_path}")
        return 1
    
    logger.info("=" * 60)
    logger.info("  Golden Document Ingestion")
    logger.info("=" * 60)
    
    doc_id = None
    ingest_result = None
    embed_result = None
    
    # Step 1: Ingest document (separate session)
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
        logger.info(f"  Figures: {ingest_result.total_figures}")
        logger.info(f"  Tables: {ingest_result.total_tables}")
        logger.info(f"  Duplicate: {ingest_result.is_content_duplicate}")
        
        doc_id = ingest_result.doc_id
    
    logger.info("  Session closed after ingestion.")
    
    # Step 2: Generate embeddings (separate session)
    logger.info(f"\n[STEP 2] Generating embeddings for {doc_id[:16]}...")
    
    with session_scope() as db:
        embed_result = embed_document_nodes_sync(
            doc_id=doc_id,
            version=1,
            db=db
        )
        
        logger.info(f"  Embedded: {embed_result['embedded']}")
        logger.info(f"  Indexed: {embed_result['indexed']}")
        logger.info(f"  Tokens: {embed_result.get('tokens', 'N/A')}")
    
    logger.info("  Session closed after embedding.")
    
    # Step 3: Verify vectors (direct pymilvus, no ORM)
    logger.info(f"\n[STEP 3] Verifying vectors in Milvus...")
    
    from pymilvus import connections, Collection, utility
    
    host = os.getenv("MILVUS_HOST", "192.168.100.25")
    port = os.getenv("MILVUS_PORT", "19530")
    
    connections.connect(alias="verify", host=host, port=port, timeout=10)
    
    collections = ["graph_chunks_v2", "graph_figures_v2", "graph_tables_v2"]
    total = 0
    
    for name in collections:
        try:
            if utility.has_collection(name, using="verify"):
                col = Collection(name, using="verify")
                col.load()
                count = col.num_entities
                logger.info(f"  {name}: {count} vectors")
                total += count
        except Exception as e:
            logger.warning(f"  {name}: error - {e}")
    
    logger.info(f"  Total: {total} vectors")
    
    connections.disconnect("verify")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("  INGESTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"\n  Document: {pdf_path.name}")
    logger.info(f"  Doc ID: {doc_id}")
    logger.info(f"  Chunks: {ingest_result.total_chunks}")
    logger.info(f"  Vectors indexed: {embed_result['indexed']}")
    logger.info(f"  Total vectors in Milvus: {total}")
    logger.info("\n  Next step: Run A/B evaluation")
    logger.info("  Command: .\\venv\\Scripts\\python.exe -m tests.eval.run_qa_eval --rerank-ab")
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    logger.info(f"Exiting with code {exit_code}")
    sys.exit(exit_code)
