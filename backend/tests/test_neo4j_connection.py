"""Test Neo4j connection."""

import os
import pytest
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

# Neo4j configuration (from environment, defaults for local development)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")


def get_driver():
    """Create Neo4j driver."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def _require_neo4j():
    """Return a verified driver or skip if Neo4j is unavailable."""
    driver = get_driver()
    try:
        driver.verify_connectivity()
        return driver
    except Exception as e:
        try:
            driver.close()
        except Exception:
            pass
        pytest.skip(f"Neo4j unavailable at {NEO4J_URI}: {e}")


def test_connection():
    """Test basic connection to Neo4j."""
    print("Testing Neo4j connection...")
    print(f"  URI: {NEO4J_URI}")
    print(f"  User: {NEO4J_USER}")
    
    driver = _require_neo4j()
    print(f"\n✓ Connected to Neo4j!")
    
    # Get server info
    with driver.session() as session:
        result = session.run("CALL dbms.components() YIELD name, versions, edition")
        record = result.single()
        print(f"  Name: {record['name']}")
        print(f"  Version: {record['versions'][0]}")
        print(f"  Edition: {record['edition']}")
    
    driver.close()
    return True


def test_database_info():
    """Get database information."""
    driver = _require_neo4j()
    
    with driver.session() as session:
        # Count nodes
        result = session.run("MATCH (n) RETURN count(n) as count")
        node_count = result.single()["count"]
        print(f"\nDatabase Stats:")
        print(f"  Total nodes: {node_count}")
        
        # Count relationships
        result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
        rel_count = result.single()["count"]
        print(f"  Total relationships: {rel_count}")
        
        # List labels
        result = session.run("CALL db.labels()")
        labels = [record["label"] for record in result]
        print(f"  Labels: {labels if labels else '(none)'}")
    
    driver.close()
    return True


def test_graph_operations():
    """Test node/relationship create/query/delete operations."""
    driver = _require_neo4j()
    
    with driver.session() as session:
        # Create test nodes
        session.run("""
            CREATE (d:NPRTestDoc {id: 'doc-001', title: 'Test Document'})
            CREATE (c:NPRTestChunk {id: 'chunk-001', text: 'Test chunk content'})
            CREATE (d)-[:HAS_CHUNK]->(c)
        """)
        print(f"\n✓ Created test nodes and relationship")
        
        # Query
        result = session.run("""
            MATCH (d:NPRTestDoc)-[r:HAS_CHUNK]->(c:NPRTestChunk)
            RETURN d.title as doc_title, c.text as chunk_text, type(r) as rel_type
        """)
        record = result.single()
        print(f"✓ Queried graph: {record['doc_title']} -[{record['rel_type']}]-> {record['chunk_text']}")
        
        # Cleanup
        session.run("MATCH (n:NPRTestDoc) DETACH DELETE n")
        session.run("MATCH (n:NPRTestChunk) DETACH DELETE n")
        print(f"✓ Cleaned up test nodes")
    
    driver.close()
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("Neo4j Connection Test")
    print("=" * 50)
    
    try:
        test_connection()
        test_database_info()
        test_graph_operations()
        print("\n" + "=" * 50)
        print("All Neo4j tests passed! ✓")
        print("=" * 50)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        raise
