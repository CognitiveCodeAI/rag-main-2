"""Setup Milvus vector database collections.

This script creates the required collections:
- graph_chunks_v2: Chunk node embeddings with metadata
- graph_figures_v2: Figure node embeddings with metadata
- graph_tables_v2: Table node embeddings with metadata

Optional legacy collections (v1):
- chunks_vec_content_v1: Semantic body similarity
- chunks_vec_contextual_v1: Structure-aware retrieval
"""

import os
import sys
from pathlib import Path

# Add backend to path for imports
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

# Load environment
load_dotenv(backend_dir / ".env")


def test_connection() -> bool:
    """Test Milvus connection."""
    from pymilvus import connections, utility
    
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    
    print(f"Connecting to Milvus at {host}:{port}...")
    
    try:
        connections.connect(alias="default", host=host, port=port)
        version = utility.get_server_version()
        print(f"  [OK] Connected to Milvus")
        print(f"  [OK] Server version: {version}")
        return True
    except Exception as e:
        print(f"  [ERROR] Connection failed: {e}")
        return False


def create_v2_collections() -> bool:
    """Create v2 collections with metadata fields."""
    from pymilvus import (
        Collection,
        CollectionSchema,
        FieldSchema,
        DataType,
        utility,
    )
    
    dim = int(os.getenv("EMBEDDING_DIM", "3072"))
    
    # V2 collection names
    collections = {
        "graph_chunks_v2": "Chunk node embeddings",
        "graph_figures_v2": "Figure node embeddings",
        "graph_tables_v2": "Table node embeddings",
    }
    
    print(f"\nCreating v2 collections (dim={dim})...")
    
    success = True
    
    for name, description in collections.items():
        print(f"\n  {name}:")
        
        if utility.has_collection(name):
            print(f"    [SKIP] Already exists")
            collection = Collection(name)
            print(f"    [INFO] Entities: {collection.num_entities}")
            continue
        
        try:
            # V2 schema with metadata fields
            fields = [
                FieldSchema(name="node_id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="version", dtype=DataType.INT32),
                FieldSchema(name="page_no", dtype=DataType.INT32),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
                # Metadata fields for filtered search
                FieldSchema(name="year", dtype=DataType.INT32),
                FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="department", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="authority_tier", dtype=DataType.INT32),
            ]
            
            schema = CollectionSchema(
                fields=fields,
                description=f"Graph RAG v2 - {description}"
            )
            
            collection = Collection(name=name, schema=schema)
            print(f"    [OK] Created collection")
            
            # Create index
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            
            collection.create_index(field_name="vector", index_params=index_params)
            print(f"    [OK] Created IVF_FLAT index (COSINE)")
            
            # Load collection
            collection.load()
            print(f"    [OK] Collection loaded")
            
        except Exception as e:
            print(f"    [ERROR] Failed: {e}")
            success = False
    
    return success


def create_v1_collections(skip_if_exists: bool = True) -> bool:
    """Create legacy v1 collections."""
    from pymilvus import (
        Collection,
        CollectionSchema,
        FieldSchema,
        DataType,
        utility,
    )
    
    dim = int(os.getenv("EMBEDDING_DIM", "3072"))
    
    # V1 collection names
    collections = {
        "chunks_vec_content_v1": "Semantic body similarity",
        "chunks_vec_contextual_v1": "Structure-aware retrieval",
    }
    
    print(f"\nCreating v1 legacy collections (dim={dim})...")
    
    success = True
    
    for name, description in collections.items():
        print(f"\n  {name}:")
        
        if utility.has_collection(name):
            if skip_if_exists:
                print(f"    [SKIP] Already exists")
                continue
        
        try:
            # V1 schema
            fields = [
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=256, is_primary=True),
                FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="version_id", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="authority_tier", dtype=DataType.VARCHAR, max_length=32),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
            ]
            
            schema = CollectionSchema(
                fields=fields,
                description=f"NPR v1 - {description}"
            )
            
            collection = Collection(name=name, schema=schema)
            print(f"    [OK] Created collection")
            
            # Create index
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 256}
            }
            
            collection.create_index(field_name="embedding", index_params=index_params)
            print(f"    [OK] Created IVF_FLAT index (COSINE)")
            
        except Exception as e:
            print(f"    [ERROR] Failed: {e}")
            success = False
    
    return success


def list_collections() -> None:
    """List all collections and their stats."""
    from pymilvus import utility, Collection
    
    print("\nExisting collections:")
    
    collections = utility.list_collections()
    
    if not collections:
        print("  (none)")
        return
    
    for name in sorted(collections):
        try:
            collection = Collection(name)
            print(f"  - {name}: {collection.num_entities} entities")
        except Exception as e:
            print(f"  - {name}: (error: {e})")


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("Milvus Setup")
    print("=" * 60)
    print()
    
    # Test connection
    if not test_connection():
        print("\n[FAILED] Cannot proceed without Milvus connection")
        print("\nTroubleshooting:")
        print("  1. Verify Milvus is running")
        print("  2. Check .env file has correct MILVUS_HOST, MILVUS_PORT")
        return 1
    
    # Create v2 collections (primary)
    if not create_v2_collections():
        print("\n[WARNING] Some v2 collections failed to create")
    
    # Create v1 collections (optional legacy)
    create_v1_collections(skip_if_exists=True)
    
    # List all collections
    list_collections()
    
    print()
    print("=" * 60)
    print("[SUCCESS] Milvus setup complete")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
