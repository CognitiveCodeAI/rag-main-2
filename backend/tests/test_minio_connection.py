"""Test MinIO (S3-compatible) connection."""

import os
import io
from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

load_dotenv()

# MinIO configuration (from environment, defaults match docker-compose.yml)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"


def get_minio_client() -> Minio:
    """Create MinIO client."""
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def test_connection():
    """Test basic connection to MinIO."""
    print("Testing MinIO connection...")
    print(f"  Endpoint: {MINIO_ENDPOINT}")
    print(f"  Access Key: {MINIO_ACCESS_KEY}")
    
    client = get_minio_client()
    
    # List buckets to verify connection
    buckets = client.list_buckets()
    print(f"\n✓ Connected to MinIO!")
    print(f"  Buckets: {len(buckets)}")
    for bucket in buckets:
        print(f"    - {bucket.name} (created: {bucket.creation_date})")
    
    return True


def test_bucket_operations():
    """Test bucket create/delete operations."""
    client = get_minio_client()
    test_bucket = "npr-test-bucket"
    
    # Create bucket
    if not client.bucket_exists(test_bucket):
        client.make_bucket(test_bucket)
        print(f"\n✓ Created test bucket: {test_bucket}")
    else:
        print(f"\n  Test bucket already exists: {test_bucket}")
    
    # Upload test object
    test_data = b"Hello from NPR RAG test!"
    client.put_object(
        test_bucket,
        "test-object.txt",
        io.BytesIO(test_data),
        len(test_data),
        content_type="text/plain",
    )
    print(f"✓ Uploaded test object")
    
    # Download and verify
    response = client.get_object(test_bucket, "test-object.txt")
    downloaded = response.read()
    response.close()
    response.release_conn()
    
    assert downloaded == test_data, "Data mismatch!"
    print(f"✓ Downloaded and verified test object")
    
    # List objects
    objects = list(client.list_objects(test_bucket))
    print(f"✓ Listed objects: {len(objects)}")
    
    # Cleanup
    client.remove_object(test_bucket, "test-object.txt")
    client.remove_bucket(test_bucket)
    print(f"✓ Cleaned up test bucket")
    
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("MinIO Connection Test")
    print("=" * 50)
    
    try:
        test_connection()
        test_bucket_operations()
        print("\n" + "=" * 50)
        print("All MinIO tests passed! ✓")
        print("=" * 50)
    except S3Error as e:
        print(f"\n✗ S3 Error: {e}")
        raise
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        raise
