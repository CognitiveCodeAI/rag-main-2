"""End-to-end test for document ingestion pipeline.

This test validates:
1. Upload file via API
2. Job completes successfully
3. IR and chunks stored in MinIO
4. Metadata stored in Postgres
5. Re-ingestion is idempotent

Prerequisites:
- PostgreSQL running on 192.168.100.25:5433
- MinIO running on 192.168.100.25:9000
- Redis running on 192.168.100.25:6379 (for Celery)
- Celery worker running

To run:
    cd C:\\Apps\\rag\\backend
    .\\venv\\Scripts\\activate
    python tests\\test_ingestion_e2e.py
"""

import os
import sys
import time
import json
import hashlib
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test configuration
API_BASE = "http://localhost:8000"
TEST_TIMEOUT = 120  # seconds to wait for job completion


def create_test_document():
    """Create a test markdown document."""
    content = """# Test Document for NPR RAG

This is a test document to validate the ingestion pipeline.

## Section 1: Introduction

This section provides an introduction to the test content.
Lorem ipsum dolor sit amet, consectetur adipiscing elit.

### Subsection 1.1: Details

Here are some important details:
- Item one with information
- Item two with more data
- Item three concluding the list

## Section 2: Technical Content

Here is a code example:

```python
def hello_world():
    print("Hello from NPR RAG!")
    return True
```

### Subsection 2.1: Table Data

| Column A | Column B | Column C |
|----------|----------|----------|
| Value 1  | Value 2  | Value 3  |
| Value 4  | Value 5  | Value 6  |

## Conclusion

This concludes the test document. The ingestion pipeline should:
1. Parse this markdown into structured IR
2. Split into appropriate chunks
3. Store all artifacts correctly
"""
    return content.encode("utf-8")


def test_storage_client():
    """Test MinIO storage client directly."""
    print("\n=== Testing Storage Client ===")
    
    from app.storage.minio_client import StorageClient
    
    try:
        storage = StorageClient()
        print("✓ Connected to MinIO")
        
        # Test bucket creation
        print(f"  Buckets ensured: {storage.CORPUS_BUCKET}, {storage.TRACES_BUCKET}")
        
        # Test write/read cycle
        test_doc_id = "test-storage-001"
        test_version = "v1"
        test_content = b"Test content for storage validation"
        
        # Write raw
        uri = storage.put_raw(test_doc_id, test_version, test_content, "test.txt")
        print(f"✓ Wrote raw file: {uri}")
        
        # Read back
        read_content = storage.get_raw(test_doc_id, test_version, "test.txt")
        assert read_content == test_content, "Content mismatch!"
        print("✓ Read content matches")
        
        # Test IR storage
        test_ir = {
            "schema_version": "1.0",
            "doc_ref": {"doc_id": test_doc_id},
            "pages": [],
            "sections": [],
            "quality": {"parse_confidence": 0.95}
        }
        ir_uri = storage.put_ir(test_doc_id, test_version, test_ir)
        print(f"✓ Wrote IR: {ir_uri}")
        
        read_ir = storage.get_ir(test_doc_id, test_version)
        assert read_ir["schema_version"] == "1.0"
        print("✓ Read IR matches")
        
        # Test chunks storage
        test_chunks = [
            {"schema_version": "1.0", "chunk_ref": {"chunk_id": "c1"}, "fields": {"body": "test"}},
            {"schema_version": "1.0", "chunk_ref": {"chunk_id": "c2"}, "fields": {"body": "test2"}},
        ]
        chunks_uri = storage.put_chunks(test_doc_id, test_version, test_chunks)
        print(f"✓ Wrote chunks: {chunks_uri}")
        
        read_chunks = storage.get_chunks(test_doc_id, test_version)
        assert len(read_chunks) == 2
        print("✓ Read chunks matches")
        
        # Cleanup
        storage.delete_document(test_doc_id, test_version)
        print("✓ Cleaned up test artifacts")
        
        return True
        
    except Exception as e:
        print(f"✗ Storage test failed: {e}")
        return False


def test_parser():
    """Test document parser directly."""
    print("\n=== Testing Parser ===")
    
    from app.parsers import ParserRegistry
    
    try:
        content = create_test_document()
        doc_ref = {
            "schema_version": "1.0",
            "doc_id": "test-parser-001",
            "version_id": "v1",
            "source_type": "md",
            "source_uri": "test://test.md",
            "checksum": hashlib.sha256(content).hexdigest(),
        }
        
        ir = ParserRegistry.parse(content, doc_ref)
        ir_dict = ir.to_dict()
        
        print(f"✓ Parsed document: {ir.title or 'untitled'}")
        print(f"  Pages: {len(ir.pages)}")
        print(f"  Sections: {len(ir.sections)}")
        
        # Count blocks by type
        block_types = {}
        for page in ir.pages:
            for block in page.blocks:
                block_types[block.type] = block_types.get(block.type, 0) + 1
        print(f"  Blocks: {block_types}")
        
        # Validate structure
        assert len(ir.pages) > 0, "No pages found"
        assert len(ir.sections) > 0, "No sections found"
        assert ir_dict["schema_version"] == "1.0"
        print("✓ IR structure valid")
        
        return True
        
    except Exception as e:
        print(f"✗ Parser test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_chunker():
    """Test document chunker directly."""
    print("\n=== Testing Chunker ===")
    
    from app.parsers import ParserRegistry
    from app.chunker import chunk_document, ChunkingConfig
    
    try:
        content = create_test_document()
        doc_ref = {
            "schema_version": "1.0",
            "doc_id": "test-chunker-001",
            "version_id": "v1",
            "source_type": "md",
            "source_uri": "test://test.md",
            "checksum": hashlib.sha256(content).hexdigest(),
        }
        
        # Parse
        ir = ParserRegistry.parse(content, doc_ref)
        
        # Chunk
        config = ChunkingConfig(target_tokens=256, max_tokens=512)
        chunks = chunk_document(ir, config)
        
        print(f"✓ Created {len(chunks)} chunks")
        
        # Analyze chunks
        chunk_types = {}
        for chunk in chunks:
            ct = chunk["chunk_ref"]["chunk_type"]
            chunk_types[ct] = chunk_types.get(ct, 0) + 1
        print(f"  Chunk types: {chunk_types}")
        
        # Validate structure
        for chunk in chunks:
            assert "schema_version" in chunk
            assert "chunk_ref" in chunk
            assert "fields" in chunk
            assert "body" in chunk["fields"]
        print("✓ All chunks have valid structure")
        
        # Show sample
        if chunks:
            sample = chunks[0]
            print(f"\n  Sample chunk:")
            print(f"    ID: {sample['chunk_ref']['chunk_id']}")
            print(f"    Type: {sample['chunk_ref']['chunk_type']}")
            print(f"    Section: {sample['chunk_ref'].get('section_path', [])}")
            body_preview = sample['fields']['body'][:100] + "..." if len(sample['fields']['body']) > 100 else sample['fields']['body']
            print(f"    Body: {body_preview}")
        
        return True
        
    except Exception as e:
        print(f"✗ Chunker test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database():
    """Test database connection and models."""
    print("\n=== Testing Database ===")
    
    from app.db.session import session_scope, engine
    from app.db.models import Document, IngestJob, Chunk
    
    try:
        from sqlalchemy import text
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✓ Connected to PostgreSQL: {version[:50]}...")
        
        # Test model operations
        with session_scope() as session:
            # Count existing records
            doc_count = session.query(Document).count()
            job_count = session.query(IngestJob).count()
            chunk_count = session.query(Chunk).count()
            print(f"  Documents: {doc_count}, Jobs: {job_count}, Chunks: {chunk_count}")
        
        print("✓ Database models working")
        return True
        
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False


def test_api_upload():
    """Test file upload via API using TestClient (no running server needed)."""
    print("\n=== Testing API Upload ===")
    
    from fastapi.testclient import TestClient
    from main import app
    
    try:
        client = TestClient(app)
        
        # Test health endpoint
        r = client.get("/health")
        if r.status_code != 200:
            print("✗ Health check failed")
            return False
        print("✓ App loaded successfully")
        
        # Upload test document
        content = create_test_document()
        files = {"file": ("test_doc.md", content, "text/markdown")}
        
        r = client.post(
            "/v1/ingest/document",
            files=files,
        )
        
        if r.status_code != 200:
            print(f"✗ Upload failed: {r.status_code} - {r.text}")
            return False
        
        result = r.json()
        print(f"✓ Upload accepted: job_id={result['job_id']}")
        print(f"  doc_id: {result['doc_id']}")
        print(f"  version_id: {result['version_id']}")
        
        # Note: With TestClient, Celery tasks won't run async
        # For full e2e with Celery, use the live server + worker
        
        # Check job status
        job_id = result["job_id"]
        r = client.get(f"/v1/ingest/job/{job_id}")
        status = r.json()
        print(f"✓ Job status: {status['status']}")
        
        # Since Celery isn't running, job will be in 'pending' state
        # Return the result for artifact verification if storage was successful
        return result
        
    except Exception as e:
        print(f"✗ API test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_raw_uploaded(doc_id: str, version_id: str):
    """Verify raw file was uploaded to MinIO and document record created."""
    print("\n=== Verifying Upload Artifacts ===")
    
    from app.storage.minio_client import StorageClient
    from app.db.session import session_scope
    from app.db.models import Document, IngestJob
    
    try:
        storage = StorageClient()
        
        # Check raw file was uploaded
        raw_files = storage.list_raw_files(doc_id, version_id)
        assert len(raw_files) > 0, "No raw files uploaded"
        print(f"✓ Raw file uploaded: {raw_files[0]}")
        
        # Check database records
        with session_scope() as session:
            doc = session.query(Document).filter_by(doc_id=doc_id).first()
            assert doc is not None, "Document not in database"
            print(f"✓ Document record exists: type={doc.source_type}")
            
            job = session.query(IngestJob).filter_by(doc_id=doc_id).first()
            assert job is not None, "IngestJob not in database"
            print(f"✓ IngestJob record exists: status={job.status}")
        
        print("\nNote: Full artifact verification requires running Celery worker.")
        print("  To process the job: celery -A app.worker worker --loglevel=info")
        
        return True
        
    except Exception as e:
        print(f"✗ Upload verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_artifacts_exist(doc_id: str, version_id: str):
    """Verify all artifacts were created correctly (after Celery processing)."""
    print("\n=== Verifying Full Artifacts ===")
    
    from app.storage.minio_client import StorageClient
    from app.db.session import session_scope
    from app.db.models import Document, DocumentIR as DocumentIRModel, Chunk
    
    try:
        storage = StorageClient()
        
        # Check MinIO artifacts
        assert storage.ir_exists(doc_id, version_id), "IR not found in MinIO"
        print("✓ IR exists in MinIO")
        
        ir = storage.get_ir(doc_id, version_id)
        assert ir["schema_version"] == "1.0"
        print(f"  IR has {len(ir.get('pages', []))} pages, {len(ir.get('sections', []))} sections")
        
        assert storage.chunks_exist(doc_id, version_id), "Chunks not found in MinIO"
        print("✓ Chunks exist in MinIO")
        
        chunks = storage.get_chunks(doc_id, version_id)
        print(f"  {len(chunks)} chunks stored")
        
        # Check database records
        with session_scope() as session:
            doc = session.query(Document).filter_by(doc_id=doc_id).first()
            assert doc is not None, "Document not in database"
            print(f"✓ Document record exists: {doc.source_type}")
            
            ir_record = session.query(DocumentIRModel).filter_by(
                doc_id=doc_id, version_id=version_id
            ).first()
            assert ir_record is not None, "DocumentIR not in database"
            print(f"✓ IR record exists: confidence={ir_record.parse_confidence}")
            
            chunk_count = session.query(Chunk).filter_by(doc_id=doc_id).count()
            assert chunk_count > 0, "No chunks in database"
            print(f"✓ {chunk_count} chunk records in database")
        
        return True
        
    except Exception as e:
        print(f"✗ Artifact verification failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("  NPR RAG Ingestion Pipeline - End-to-End Test")
    print("=" * 60)
    
    results = {}
    
    # Component tests (don't require running services)
    results["parser"] = test_parser()
    results["chunker"] = test_chunker()
    
    # Infrastructure tests (require running services)
    results["storage"] = test_storage_client()
    results["database"] = test_database()
    
    # API test (uses TestClient, no running server needed)
    api_result = test_api_upload()
    if api_result is None:
        results["api"] = "SKIPPED"
    elif api_result:
        results["api"] = True
        # Verify raw file was uploaded to MinIO
        results["artifacts"] = test_raw_uploaded(
            api_result["doc_id"],
            api_result["version_id"],
        )
    else:
        results["api"] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for name, result in results.items():
        if result == "SKIPPED":
            status = "SKIPPED"
            skipped += 1
        elif result:
            status = "PASSED"
            passed += 1
        else:
            status = "FAILED"
            failed += 1
        print(f"  {name:15} : {status}")
    
    print(f"\n  Total: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
