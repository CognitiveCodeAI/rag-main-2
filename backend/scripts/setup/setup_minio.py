"""Setup MinIO buckets for document storage.

This script creates the required buckets:
- npr-corpus: Documents, chunks, embeddings, IR files
- npr-traces: Flight recorder trace logs
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


# Bucket configuration
BUCKETS = {
    "npr-corpus": "Documents, chunks, and embeddings",
    "npr-traces": "Flight recorder trace logs",
}


def test_connection():
    """Test MinIO connection and return client."""
    from minio import Minio
    from minio.error import S3Error
    
    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "admin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    
    print(f"Connecting to MinIO at {endpoint}...")
    
    try:
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        
        # Test connection by listing buckets
        buckets = client.list_buckets()
        print(f"  [OK] Connected to MinIO")
        print(f"  [OK] Found {len(buckets)} existing bucket(s)")
        
        return client
        
    except S3Error as e:
        print(f"  [ERROR] S3 error: {e}")
        return None
    except Exception as e:
        print(f"  [ERROR] Connection failed: {e}")
        return None


def create_buckets(client) -> bool:
    """Create required buckets."""
    from minio.error import S3Error
    
    print("\nCreating buckets...")
    
    success = True
    
    for bucket_name, description in BUCKETS.items():
        print(f"\n  {bucket_name} ({description}):")
        
        try:
            if client.bucket_exists(bucket_name):
                print(f"    [SKIP] Already exists")
                
                # List object count
                objects = list(client.list_objects(bucket_name, recursive=True))
                print(f"    [INFO] Objects: {len(objects)}")
            else:
                client.make_bucket(bucket_name)
                print(f"    [OK] Created bucket")
                
        except S3Error as e:
            print(f"    [ERROR] S3 error: {e}")
            success = False
        except Exception as e:
            print(f"    [ERROR] Failed: {e}")
            success = False
    
    return success


def list_buckets(client) -> None:
    """List all buckets."""
    print("\nExisting buckets:")
    
    try:
        buckets = client.list_buckets()
        
        if not buckets:
            print("  (none)")
            return
        
        for bucket in buckets:
            objects = list(client.list_objects(bucket.name, recursive=True))
            print(f"  - {bucket.name}: {len(objects)} objects")
            
    except Exception as e:
        print(f"  [ERROR] Could not list buckets: {e}")


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("MinIO Setup")
    print("=" * 60)
    print()
    
    # Test connection
    client = test_connection()
    
    if not client:
        print("\n[FAILED] Cannot proceed without MinIO connection")
        print("\nTroubleshooting:")
        print("  1. Verify MinIO is running")
        print("  2. Check .env file has correct MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY")
        return 1
    
    # Create buckets
    if not create_buckets(client):
        print("\n[WARNING] Some buckets failed to create")
    
    # List all buckets
    list_buckets(client)
    
    print()
    print("=" * 60)
    print("[SUCCESS] MinIO setup complete")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
