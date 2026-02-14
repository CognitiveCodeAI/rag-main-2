"""Test OpenSearch connection."""

import os
import urllib3
import pytest
from dotenv import load_dotenv
from opensearchpy import OpenSearch

# Suppress InsecureRequestWarning for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()


def get_opensearch_client() -> OpenSearch:
    """Create OpenSearch client from environment variables."""
    url = os.getenv("OPENSEARCH_URL", "https://localhost:9200")
    username = os.getenv("OPENSEARCH_USERNAME", "admin")
    password = os.getenv("OPENSEARCH_PASSWORD", "")
    verify_certs = os.getenv("OPENSEARCH_TLS_REJECT_UNAUTHORIZED", "false").lower() == "true"
    
    # Parse host and port from URL
    # Remove protocol prefix
    host_port = url.replace("https://", "").replace("http://", "")
    host, port = host_port.split(":") if ":" in host_port else (host_port, 9200)
    
    client = OpenSearch(
        hosts=[{"host": host, "port": int(port)}],
        http_auth=(username, password),
        use_ssl=url.startswith("https"),
        verify_certs=verify_certs,
        ssl_show_warn=False,
    )
    return client


def _require_opensearch() -> OpenSearch:
    """Return a verified OpenSearch client or skip if cluster unavailable."""
    client = get_opensearch_client()
    try:
        client.info()
        return client
    except Exception as e:
        pytest.skip(f"OpenSearch unavailable at {os.getenv('OPENSEARCH_URL', 'https://localhost:9200')}: {e}")


def test_connection():
    """Test basic connection to OpenSearch."""
    print("Testing OpenSearch connection...")
    print(f"  URL: {os.getenv('OPENSEARCH_URL')}")
    print(f"  User: {os.getenv('OPENSEARCH_USERNAME')}")
    
    client = _require_opensearch()
    info = client.info()
    print(f"\n✓ Connected to OpenSearch!")
    print(f"  Cluster name: {info['cluster_name']}")
    print(f"  Version: {info['version']['number']}")
    print(f"  Distribution: {info['version'].get('distribution', 'unknown')}")
    
    return True


def test_cluster_health():
    """Test cluster health."""
    client = _require_opensearch()
    health = client.cluster.health()
    
    print(f"\nCluster Health:")
    print(f"  Status: {health['status']}")
    print(f"  Nodes: {health['number_of_nodes']}")
    print(f"  Data nodes: {health['number_of_data_nodes']}")
    print(f"  Active shards: {health['active_shards']}")
    
    return health["status"] in ["green", "yellow"]


def test_list_indices():
    """List all indices."""
    client = _require_opensearch()
    indices = client.cat.indices(format="json")
    
    print(f"\nIndices ({len(indices)}):")
    for idx in indices[:10]:  # Show first 10
        print(f"  - {idx['index']} ({idx.get('docs.count', '?')} docs, {idx.get('store.size', '?')})")
    if len(indices) > 10:
        print(f"  ... and {len(indices) - 10} more")
    
    return True


def test_create_test_index():
    """Create a test index to verify write access."""
    client = _require_opensearch()
    test_index = "npr-test-connection"
    
    # Delete if exists
    if client.indices.exists(index=test_index):
        client.indices.delete(index=test_index)
        print(f"\nDeleted existing test index: {test_index}")
    
    # Create index
    client.indices.create(
        index=test_index,
        body={
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 384,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "lucene",
                        },
                    },
                }
            },
        },
    )
    print(f"\n✓ Created test index: {test_index}")
    
    # Index a test document
    doc = {
        "title": "Test document for NPR RAG",
        "embedding": [0.1] * 384,  # Dummy embedding
    }
    response = client.index(index=test_index, body=doc, refresh=True)
    print(f"✓ Indexed test document: {response['_id']}")
    
    # Search
    results = client.search(
        index=test_index,
        body={"query": {"match": {"title": "NPR"}}},
    )
    print(f"✓ Search returned {results['hits']['total']['value']} hits")
    
    # Cleanup
    client.indices.delete(index=test_index)
    print(f"✓ Cleaned up test index")
    
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("OpenSearch Connection Test")
    print("=" * 50)
    
    try:
        test_connection()
        test_cluster_health()
        test_list_indices()
        test_create_test_index()
        print("\n" + "=" * 50)
        print("All tests passed! ✓")
        print("=" * 50)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        raise
