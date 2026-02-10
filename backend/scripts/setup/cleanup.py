"""Cleanup script to remove application data for fresh install testing.

WARNING: This removes ALL data for this application:
- PostgreSQL: Downgrades Alembic migrations (drops tables)
- Milvus: Drops our vector collections
- MinIO: Removes our buckets and all objects

Does NOT affect other applications or databases.
"""

import os
import sys
from pathlib import Path
import subprocess

# Add backend to path for imports
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")


# Our Milvus collections
OUR_MILVUS_COLLECTIONS = [
    "graph_chunks_v2",
    "graph_figures_v2", 
    "graph_tables_v2",
    "graph_chunks_v1",
    "graph_figures_v1",
    "graph_tables_v1",
    "chunks_vec_content_v1",
    "chunks_vec_contextual_v1",
]

# Our MinIO buckets
OUR_MINIO_BUCKETS = [
    "npr-corpus",
    "npr-traces",
]


def cleanup_postgres() -> bool:
    """Downgrade all Alembic migrations."""
    print("\n[PostgreSQL] Downgrading migrations...")
    
    try:
        result = subprocess.run(
            ["alembic", "downgrade", "base"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("  [OK] All migrations downgraded")
            return True
        else:
            print(f"  [ERROR] {result.stderr}")
            return False
            
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def cleanup_milvus() -> bool:
    """Drop our Milvus collections."""
    from pymilvus import connections, utility
    
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    
    print(f"\n[Milvus] Dropping collections...")
    
    try:
        connections.connect(alias="default", host=host, port=port)
        
        existing = utility.list_collections()
        
        for name in OUR_MILVUS_COLLECTIONS:
            if name in existing:
                utility.drop_collection(name)
                print(f"  [OK] Dropped: {name}")
            else:
                print(f"  [SKIP] Not found: {name}")
        
        connections.disconnect("default")
        return True
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def cleanup_minio() -> bool:
    """Remove our MinIO buckets and objects."""
    from minio import Minio
    
    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "admin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "")
    
    print(f"\n[MinIO] Removing buckets...")
    
    try:
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False,
        )
        
        for bucket in OUR_MINIO_BUCKETS:
            if client.bucket_exists(bucket):
                # Remove all objects first
                objects = list(client.list_objects(bucket, recursive=True))
                for obj in objects:
                    client.remove_object(bucket, obj.object_name)
                
                # Remove bucket
                client.remove_bucket(bucket)
                print(f"  [OK] Removed: {bucket} ({len(objects)} objects deleted)")
            else:
                print(f"  [SKIP] Not found: {bucket}")
        
        return True
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def show_current_state():
    """Show what currently exists."""
    from pymilvus import connections, utility
    from minio import Minio
    
    print("=" * 60)
    print("Current State (before cleanup)")
    print("=" * 60)
    
    # Milvus
    try:
        connections.connect(
            alias="default",
            host=os.getenv("MILVUS_HOST"),
            port=os.getenv("MILVUS_PORT")
        )
        existing = utility.list_collections()
        our_existing = [c for c in existing if c in OUR_MILVUS_COLLECTIONS]
        print(f"\nMilvus: {len(our_existing)} of our collections exist")
        for c in our_existing:
            print(f"  - {c}")
        connections.disconnect("default")
    except Exception as e:
        print(f"\nMilvus: ERROR - {e}")
    
    # MinIO
    try:
        client = Minio(
            os.getenv("MINIO_ENDPOINT"),
            access_key=os.getenv("MINIO_ACCESS_KEY"),
            secret_key=os.getenv("MINIO_SECRET_KEY"),
            secure=False,
        )
        buckets = [b.name for b in client.list_buckets()]
        our_existing = [b for b in buckets if b in OUR_MINIO_BUCKETS]
        print(f"\nMinIO: {len(our_existing)} of our buckets exist")
        for b in our_existing:
            objects = list(client.list_objects(b, recursive=True))
            print(f"  - {b} ({len(objects)} objects)")
    except Exception as e:
        print(f"\nMinIO: ERROR - {e}")
    
    # PostgreSQL - check alembic version
    try:
        result = subprocess.run(
            ["alembic", "current"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True
        )
        version = result.stdout.strip() if result.returncode == 0 else "unknown"
        print(f"\nPostgreSQL Alembic: {version if version else 'no migrations applied'}")
    except Exception as e:
        print(f"\nPostgreSQL: ERROR - {e}")


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("CLEANUP - Remove Application Data")
    print("=" * 60)
    print()
    print("This will remove ALL data for the NPR RAG application:")
    print("  - PostgreSQL: Drop all tables (via Alembic downgrade)")
    print("  - Milvus: Drop our vector collections")
    print("  - MinIO: Remove our buckets and objects")
    print()
    print("Other databases and applications will NOT be affected.")
    print()
    
    show_current_state()
    
    print()
    print("=" * 60)
    print("Starting cleanup...")
    print("=" * 60)
    
    results = {
        "PostgreSQL": cleanup_postgres(),
        "Milvus": cleanup_milvus(),
        "MinIO": cleanup_minio(),
    }
    
    print()
    print("=" * 60)
    print("Cleanup Summary")
    print("=" * 60)
    
    all_ok = True
    for service, ok in results.items():
        status = "[OK]" if ok else "[FAILED]"
        print(f"  {status} {service}")
        if not ok:
            all_ok = False
    
    print()
    
    if all_ok:
        print("[SUCCESS] Cleanup complete - ready for fresh install")
        return 0
    else:
        print("[WARNING] Some cleanup steps failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
