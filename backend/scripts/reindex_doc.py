"""Re-index a document's chunks into Milvus with timeout and debug."""
import logging
import sys
import time
import httpx
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Add parent to path
sys.path.insert(0, '.')

from app.db.session import session_scope
from app.db.graph_models import Node, NodeType, DocumentGraph
from app.config import get_settings
from app.graph.vector_index import ACTIVE_COLLECTION_VERSION, NODE_TYPE_COLLECTIONS

DOC_ID = '93e7889b428b7579d8221db3b57a93b6'
BATCH_SIZE = 5  # Small batches to avoid timeout
TIMEOUT = 30  # 30 second timeout per batch

def embed_batch(texts: list, settings) -> list:
    """Embed a batch of texts with explicit timeout."""
    logger.info(f"  Embedding batch of {len(texts)} texts...")
    
    client = httpx.Client(timeout=TIMEOUT)
    
    try:
        response = client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": settings.embedding_model,
                "input": texts
            }
        )
        response.raise_for_status()
        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]
        logger.info(f"  Got {len(embeddings)} embeddings")
        return embeddings
    except httpx.TimeoutException as e:
        logger.error(f"  Timeout: {e}")
        raise
    except Exception as e:
        logger.error(f"  Error: {e}")
        raise
    finally:
        client.close()

def flush_with_timeout(collection, timeout_sec=10):
    """Flush with timeout - returns True if successful, False if timed out."""
    result = [None]
    error = [None]
    
    def do_flush():
        try:
            collection.flush()
            result[0] = True
        except Exception as e:
            error[0] = e
    
    thread = threading.Thread(target=do_flush)
    thread.start()
    thread.join(timeout=timeout_sec)
    
    if thread.is_alive():
        logger.warning(f"Flush timed out after {timeout_sec}s - continuing anyway")
        return False
    
    if error[0]:
        logger.warning(f"Flush error: {error[0]} - continuing anyway")
        return False
    
    return True

def main():
    logger.info(f"Re-indexing document: {DOC_ID}")
    settings = get_settings()
    
    logger.info(f"Using embedding model: {settings.embedding_model}")
    
    with session_scope() as db:
        # Get all chunk nodes
        logger.info("Querying chunks from database...")
        chunks = db.query(Node).filter(
            Node.doc_id == DOC_ID,
            Node.node_type == NodeType.chunk
        ).all()
        
        logger.info(f"Found {len(chunks)} chunks")
        
        if not chunks:
            logger.error("No chunks found!")
            return
        
        # Process in batches
        all_embeddings = []
        texts = [c.text_plain or c.text_md or "" for c in chunks]
        
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i+BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE
            
            logger.info(f"Processing batch {batch_num}/{total_batches}...")
            start = time.time()
            
            embeddings = embed_batch(batch, settings)
            all_embeddings.extend(embeddings)
            
            elapsed = time.time() - start
            logger.info(f"  Batch took {elapsed:.1f}s")
        
        logger.info(f"Total embeddings: {len(all_embeddings)}")
        
        # Now insert into Milvus DIRECTLY using pymilvus
        logger.info("Connecting to Milvus directly...")
        from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
        
        connections.connect(host=settings.milvus_host, port=settings.milvus_port, timeout=10)
        logger.info(f"Connected to Milvus at {settings.milvus_host}:{settings.milvus_port}")
        
        # Use active collection version instead of hardcoded v1
        collection_name = NODE_TYPE_COLLECTIONS["chunk"]
        logger.info(f"Using collection: {collection_name} (version: {ACTIVE_COLLECTION_VERSION})")
        
        # Check if collection exists
        if utility.has_collection(collection_name):
            logger.info(f"Collection {collection_name} exists")
            collection = Collection(collection_name)
            logger.info(f"Collection has {collection.num_entities} entities")
        else:
            # Create collection if not exists
            logger.info(f"Creating collection {collection_name}...")
            fields = [
                FieldSchema(name="node_id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
                FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="version", dtype=DataType.INT64),
                FieldSchema(name="page_no", dtype=DataType.INT64),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=settings.embedding_dim),
            ]
            schema = CollectionSchema(fields=fields)
            collection = Collection(name=collection_name, schema=schema)
            logger.info(f"Created collection")
        
        # Build data for insert
        logger.info("Building insert data...")
        node_ids = [c.node_id for c in chunks]
        doc_ids = [c.doc_id for c in chunks]
        versions = [c.version for c in chunks]
        page_nos = [c.page_no or 0 for c in chunks]
        
        data = [
            node_ids,
            doc_ids,
            versions,
            page_nos,
            all_embeddings
        ]
        
        logger.info(f"Inserting {len(node_ids)} vectors...")
        start = time.time()
        result = collection.insert(data)
        elapsed = time.time() - start
        logger.info(f"Insert took {elapsed:.1f}s, result: {result}")
        
        # Skip flush - Milvus auto-flushes and it's blocking
        logger.info("Skipping explicit flush (Milvus auto-flushes)...")
        
        # Check entity count (may not reflect insert immediately without flush)
        logger.info(f"Collection entity count (may be stale): {collection.num_entities}")
        
        # Create index if not exists
        if not collection.indexes:
            logger.info("Creating index...")
            start = time.time()
            collection.create_index(
                field_name="vector",
                index_params={"index_type": "IVF_FLAT", "metric_type": "IP", "params": {"nlist": 128}}
            )
            elapsed = time.time() - start
            logger.info(f"Index creation took {elapsed:.1f}s")
        else:
            logger.info("Index already exists")
        
        # Load collection for search
        logger.info("Loading collection for search...")
        collection.load()
        logger.info("Collection loaded")
        
        # Update document's embedded_collection_version
        logger.info(f"Updating document's embedded_collection_version to {ACTIVE_COLLECTION_VERSION}...")
        doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == DOC_ID).first()
        if doc:
            doc.embedded_collection_version = ACTIVE_COLLECTION_VERSION
            db.commit()
            logger.info(f"Document {DOC_ID} marked as indexed in {ACTIVE_COLLECTION_VERSION}")
        else:
            logger.warning(f"Document {DOC_ID} not found in database")
        
    logger.info("Done! Vectors inserted successfully.")

if __name__ == "__main__":
    main()
