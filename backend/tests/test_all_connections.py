"""Run all connection tests and report summary."""

import sys
import traceback


def run_test(name: str, test_module: str) -> bool:
    """Run a test module and return success status."""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    
    try:
        # Import and run the test module
        module = __import__(test_module)
        
        # Run standard test functions
        if hasattr(module, 'test_connection'):
            module.test_connection()
        if hasattr(module, 'test_database_info'):
            module.test_database_info()
        if hasattr(module, 'test_cluster_health'):
            module.test_cluster_health()
        if hasattr(module, 'test_list_indices'):
            module.test_list_indices()
        if hasattr(module, 'test_bucket_operations'):
            module.test_bucket_operations()
        if hasattr(module, 'test_table_operations'):
            module.test_table_operations()
        if hasattr(module, 'test_graph_operations'):
            module.test_graph_operations()
        if hasattr(module, 'test_create_test_index'):
            module.test_create_test_index()
        
        print(f"\n✓ {name}: PASSED")
        return True
    except Exception as e:
        print(f"\n✗ {name}: FAILED")
        print(f"  Error: {e}")
        return False


def main():
    print("\n" + "="*60)
    print("  NPR RAG - Infrastructure Connection Tests")
    print("="*60)
    
    results = {}
    
    # OpenSearch
    results["OpenSearch"] = run_test("OpenSearch (Search + Vector)", "test_opensearch_connection")
    
    # MinIO
    results["MinIO"] = run_test("MinIO (S3 Object Storage)", "test_minio_connection")
    
    # PostgreSQL
    results["PostgreSQL"] = run_test("PostgreSQL (Relational DB)", "test_postgres_connection")
    
    # Neo4j
    results["Neo4j"] = run_test("Neo4j (Graph DB)", "test_neo4j_connection")
    
    # Milvus
    results["Milvus"] = run_test("Milvus (Vector DB)", "test_milvus_connection")
    
    # Summary
    print("\n" + "="*60)
    print("  SUMMARY")
    print("="*60)
    
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name:20} {status}")
    
    passed_count = sum(results.values())
    total_count = len(results)
    
    print(f"\n  Results: {passed_count}/{total_count} passed")
    print("="*60 + "\n")
    
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
