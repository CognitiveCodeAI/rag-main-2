"""Full pipeline test - ingest multiple documents and generate embeddings."""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test documents to ingest
TEST_DOCS = [
    "mln909001_2025_05_hipaa_basics_final.pdf",  # HIPAA document
    "contract_Data-Processing-Agreement-Template.pdf",  # Contract
    "change_nist.sp.800-218.pdf",  # NIST security
]


def ingest_documents():
    """Ingest multiple test documents."""
    from app.graph.pipeline import GraphIngestionPipeline
    from app.db.session import get_session
    
    docs_dir = Path(__file__).parent.parent / "tests" / "docs"
    db = next(get_session())
    
    results = []
    
    try:
        pipeline = GraphIngestionPipeline(db, skip_ocr=True)
        
        for filename in TEST_DOCS:
            pdf_path = docs_dir / filename
            
            if not pdf_path.exists():
                logger.warning(f"Document not found: {filename}")
                continue
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Ingesting: {filename}")
            logger.info(f"{'='*60}")
            
            with open(pdf_path, 'rb') as f:
                pdf_bytes = f.read()
            
            result = pipeline.ingest(
                pdf_bytes=pdf_bytes,
                source_uri=f"file://{pdf_path}"
            )
            
            logger.info(f"  Doc ID: {result.doc_id}")
            logger.info(f"  Pages: {result.total_pages}")
            logger.info(f"  Chunks: {result.total_chunks}")
            logger.info(f"  Figures: {result.total_figures}")
            logger.info(f"  Tables: {result.total_tables}")
            logger.info(f"  Duplicate: {result.is_content_duplicate}")
            
            results.append({
                "filename": filename,
                "doc_id": result.doc_id,
                "pages": result.total_pages,
                "chunks": result.total_chunks,
                "figures": result.total_figures,
                "tables": result.total_tables,
            })
        
        return results
        
    finally:
        db.close()


def generate_embeddings(doc_ids: list):
    """Generate embeddings for ingested documents."""
    from app.db.session import get_session
    from app.tasks.embed_nodes import embed_document_nodes_sync
    
    db = next(get_session())
    
    results = []
    
    try:
        for doc_id in doc_ids:
            logger.info(f"\n{'='*60}")
            logger.info(f"Embedding: {doc_id[:16]}...")
            logger.info(f"{'='*60}")
            
            result = embed_document_nodes_sync(
                doc_id=doc_id,
                version=1,
                db=db
            )
            
            logger.info(f"  Embedded: {result['embedded']}")
            logger.info(f"  Indexed: {result['indexed']}")
            logger.info(f"  Tokens: {result.get('tokens', 'N/A')}")
            
            results.append(result)
        
        return results
        
    finally:
        db.close()


def verify_vectors():
    """Verify vectors are in Milvus."""
    from pymilvus import connections, Collection, utility
    import os
    
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    
    connections.connect(alias="default", host=host, port=port)
    
    collections = ["graph_chunks_v2", "graph_figures_v2", "graph_tables_v2"]
    
    logger.info(f"\n{'='*60}")
    logger.info("Vector verification")
    logger.info(f"{'='*60}")
    
    total = 0
    for name in collections:
        if utility.has_collection(name):
            col = Collection(name)
            col.load()
            count = col.num_entities
            logger.info(f"  {name}: {count} vectors")
            total += count
    
    logger.info(f"  Total: {total} vectors")
    
    connections.disconnect("default")
    return total


def main():
    print("=" * 60)
    print("  Full Pipeline Test")
    print("=" * 60)
    
    # Step 1: Ingest documents
    print("\n[STEP 1] Ingesting documents...")
    ingest_results = ingest_documents()
    
    # Collect doc IDs
    doc_ids = [r["doc_id"] for r in ingest_results]
    
    # Add the first document we already ingested
    doc_ids.insert(0, "93e7889b428b7579d8221db3b57a93b6")  # 2404.08865v1.pdf
    
    # Step 2: Generate embeddings
    print("\n[STEP 2] Generating embeddings...")
    embed_results = generate_embeddings(doc_ids)
    
    # Step 3: Verify vectors
    print("\n[STEP 3] Verifying vectors...")
    total_vectors = verify_vectors()
    
    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"\n  Documents ingested: {len(ingest_results) + 1}")  # +1 for first doc
    print(f"  Total vectors: {total_vectors}")
    
    print("\n  Documents:")
    print(f"    - 2404.08865v1.pdf (already ingested)")
    for r in ingest_results:
        print(f"    - {r['filename']}: {r['chunks']} chunks, {r['figures']} figures")
    
    print("\n" + "=" * 60)
    print("  PIPELINE TEST COMPLETE")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
