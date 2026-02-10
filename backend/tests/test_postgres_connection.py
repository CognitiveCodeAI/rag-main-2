"""Test PostgreSQL connection."""

import os
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL configuration (from environment, defaults match docker-compose.yml)
PG_HOST = os.getenv("DB_HOST", "localhost")
PG_PORT = int(os.getenv("DB_PORT", "5432"))
PG_DATABASE = os.getenv("DB_NAME", "ragdb")
PG_USER = os.getenv("DB_USER", "raguser")
PG_PASSWORD = os.getenv("DB_PASSWORD", "ragpass")


def get_connection():
    """Create PostgreSQL connection."""
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
    )


def test_connection():
    """Test basic connection to PostgreSQL."""
    print("Testing PostgreSQL connection...")
    print(f"  Host: {PG_HOST}:{PG_PORT}")
    print(f"  Database: {PG_DATABASE}")
    print(f"  User: {PG_USER}")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get version
    cursor.execute("SELECT version();")
    version = cursor.fetchone()[0]
    print(f"\n✓ Connected to PostgreSQL!")
    print(f"  Version: {version}")
    
    cursor.close()
    conn.close()
    return True


def test_database_info():
    """Get database information."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # List databases
    cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
    databases = cursor.fetchall()
    print(f"\nDatabases:")
    for db in databases:
        print(f"  - {db[0]}")
    
    # Current database size
    cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()));")
    size = cursor.fetchone()[0]
    print(f"\nCurrent database size: {size}")
    
    cursor.close()
    conn.close()
    return True


def test_table_operations():
    """Test table create/insert/query/delete operations."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create test table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS npr_test (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    print(f"\n✓ Created test table: npr_test")
    
    # Insert test data
    cursor.execute("INSERT INTO npr_test (name) VALUES (%s) RETURNING id;", ("test_record",))
    record_id = cursor.fetchone()[0]
    conn.commit()
    print(f"✓ Inserted test record: id={record_id}")
    
    # Query
    cursor.execute("SELECT * FROM npr_test WHERE id = %s;", (record_id,))
    row = cursor.fetchone()
    print(f"✓ Queried test record: {row}")
    
    # Cleanup
    cursor.execute("DROP TABLE npr_test;")
    conn.commit()
    print(f"✓ Cleaned up test table")
    
    cursor.close()
    conn.close()
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("PostgreSQL Connection Test")
    print("=" * 50)
    
    try:
        test_connection()
        test_database_info()
        test_table_operations()
        print("\n" + "=" * 50)
        print("All PostgreSQL tests passed! ✓")
        print("=" * 50)
    except psycopg2.Error as e:
        print(f"\n✗ PostgreSQL Error: {e}")
        raise
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        raise
