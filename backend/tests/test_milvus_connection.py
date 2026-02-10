"""Test Milvus connection."""

from pymilvus import connections, utility, Collection, FieldSchema, CollectionSchema, DataType
import numpy as np

# Milvus configuration
MILVUS_HOST = "192.168.100.25"
MILVUS_PORT = 19530
MILVUS_ALIAS = "default"


def connect_milvus():
    """Connect to Milvus."""
    connections.connect(
        alias=MILVUS_ALIAS,
        host=MILVUS_HOST,
        port=MILVUS_PORT,
    )


def test_connection():
    """Test basic connection to Milvus."""
    print("Testing Milvus connection...")
    print(f"  Host: {MILVUS_HOST}:{MILVUS_PORT}")
    
    connect_milvus()
    
    # Check server version
    version = utility.get_server_version()
    print(f"\n✓ Connected to Milvus!")
    print(f"  Server version: {version}")
    
    return True


def test_list_collections():
    """List all collections."""
    collections = utility.list_collections()
    
    print(f"\nCollections ({len(collections)}):")
    for coll_name in collections[:10]:
        print(f"  - {coll_name}")
    if len(collections) > 10:
        print(f"  ... and {len(collections) - 10} more")
    
    return True


def test_collection_operations():
    """Test collection create/insert/search/delete operations."""
    test_collection = "npr_test_collection"
    dim = 384  # Embedding dimension
    
    # Drop if exists
    if utility.has_collection(test_collection):
        utility.drop_collection(test_collection)
        print(f"\nDropped existing test collection")
    
    # Define schema
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    schema = CollectionSchema(fields, description="NPR test collection")
    
    # Create collection
    collection = Collection(name=test_collection, schema=schema)
    print(f"\n✓ Created test collection: {test_collection}")
    
    # Insert test data
    test_data = [
        ["doc-001", "doc-002", "doc-003"],  # doc_id
        np.random.rand(3, dim).tolist(),     # embedding vectors
    ]
    collection.insert(test_data)
    print(f"✓ Inserted 3 test vectors")
    
    # Create index
    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    print(f"✓ Created vector index")
    
    # Load collection for search
    collection.load()
    print(f"✓ Loaded collection")
    
    # Search
    search_vectors = np.random.rand(1, dim).tolist()
    results = collection.search(
        data=search_vectors,
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"nprobe": 10}},
        limit=3,
        output_fields=["doc_id"],
    )
    print(f"✓ Search returned {len(results[0])} results")
    
    # Cleanup
    collection.release()
    utility.drop_collection(test_collection)
    print(f"✓ Cleaned up test collection")
    
    return True


def disconnect_milvus():
    """Disconnect from Milvus."""
    connections.disconnect(MILVUS_ALIAS)


if __name__ == "__main__":
    print("=" * 50)
    print("Milvus Connection Test")
    print("=" * 50)
    
    try:
        test_connection()
        test_list_collections()
        test_collection_operations()
        disconnect_milvus()
        print("\n" + "=" * 50)
        print("All Milvus tests passed! ✓")
        print("=" * 50)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        raise
