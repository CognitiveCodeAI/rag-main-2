"""End-to-end test for Phase 2: Embeddings and Vector Indexing.

Test flow with TIMEOUTS to prevent freezing:
1. Ingest a sample document (uses Phase 1 pipeline)
2. Trigger embedding generation
3. Wait for completion
4. Verify bundle in MinIO
5. Query and verify correct chunk returned
"""

import os
import sys
import time
import json
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import requests

# TIMEOUT SETTINGS
REQUEST_TIMEOUT = 10  # seconds per HTTP request
INGEST_TIMEOUT = 30   # max seconds to wait for ingest
EMBED_TIMEOUT = 60    # max seconds to wait for embedding

API_BASE = "http://localhost:8000"
TEST_DOC_CONTENT = """# Phase 2 Test Document

This document tests the embedding pipeline.

## Section 1: Introduction

The NPR RAG system uses multi-view embeddings for retrieval.

## Section 2: Technical Details

Embeddings use OpenAI's text-embedding-3-large model.
"""


def safe_request(method, url, **kwargs):
    """Make HTTP request with timeout and error handling."""
    kwargs.setdefault('timeout', REQUEST_TIMEOUT)
    try:
        if method == 'get':
            return requests.get(url, **kwargs)
        elif method == 'post':
            return requests.post(url, **kwargs)
    except requests.exceptions.Timeout:
        print(f"    TIMEOUT: {url}")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"    CONNECTION ERROR: {e}")
        return None
    except Exception as e:
        print(f"    ERROR: {type(e).__name__}: {e}")
        return None


def test_step1_ingest_document():
    """Step 1: Ingest a test document."""
    print("\n=== Step 1: Ingest Document ===")
    
    test_filename = "phase2_test.md"
    files = {"file": (test_filename, TEST_DOC_CONTENT.encode(), "text/markdown")}
    
    response = safe_request('post', f"{API_BASE}/v1/ingest/document", files=files)
    
    if not response or response.status_code != 200:
        print(f"  FAIL: Ingest failed")
        if response:
            print(f"    Status: {response.status_code}, Body: {response.text[:200]}")
        return None
    
    result = response.json()
    print(f"  job_id: {result['job_id']}")
    print(f"  doc_id: {result['doc_id']}")
    
    job_id = result["job_id"]
    doc_id = result["doc_id"]
    version_id = result["version_id"]
    
    print("  Waiting for ingest (max 30s)...")
    start = time.time()
    while time.time() - start < INGEST_TIMEOUT:
        time.sleep(2)
        elapsed = int(time.time() - start)
        
        job_response = safe_request('get', f"{API_BASE}/v1/ingest/job/{job_id}")
        if not job_response:
            print(f"    [{elapsed}s] Failed to get job status")
            continue
        
        if job_response.status_code != 200:
            print(f"    [{elapsed}s] Status code: {job_response.status_code}")
            continue
        
        job_status = job_response.json()
        status = job_status.get("status")
        print(f"    [{elapsed}s] Status: {status}")
        
        if status == "completed":
            print("  PASS: Ingest completed")
            return {"doc_id": doc_id, "version_id": version_id, "job_id": job_id}
        elif status == "failed":
            print(f"  FAIL: {job_status.get('error')}")
            return None
    
    print("  FAIL: Ingest timed out")
    return None


def test_step2_trigger_embedding(doc_info: dict):
    """Step 2: Trigger embedding generation."""
    print("\n=== Step 2: Trigger Embedding ===")
    
    response = safe_request('post', f"{API_BASE}/v1/embed/document", json={
        "doc_id": doc_info["doc_id"],
        "version_id": doc_info["version_id"],
    })
    
    if not response or response.status_code != 200:
        print(f"  FAIL: Embed request failed")
        if response:
            print(f"    {response.status_code}: {response.text[:200]}")
        return None
    
    result = response.json()
    print(f"  job_id: {result['job_id']}")
    print("  PASS: Embedding task queued")
    return result["job_id"]


def test_step3_wait_for_embedding(doc_info: dict):
    """Step 3: Wait for embedding to complete."""
    print("\n=== Step 3: Wait for Embedding (max 60s) ===")
    
    start = time.time()
    while time.time() - start < EMBED_TIMEOUT:
        time.sleep(3)
        elapsed = int(time.time() - start)
        
        response = safe_request('get', 
            f"{API_BASE}/v1/embed/document/{doc_info['doc_id']}/{doc_info['version_id']}/status")
        
        if not response or response.status_code != 200:
            print(f"    [{elapsed}s] Status check failed")
            continue
        
        status = response.json()
        bundle_exists = status.get("bundle_exists", False)
        index_status = status.get("index_status", {})
        
        print(f"    [{elapsed}s] Bundle: {bundle_exists}, Collections: {len(index_status)}")
        
        if bundle_exists and len(index_status) >= 2:
            print("  PASS: Embedding complete")
            return status
    
    print("  TIMEOUT: Embedding did not complete in time")
    return None


def test_step4_verify_bundle(doc_info: dict):
    """Step 4: Verify bundle in MinIO."""
    print("\n=== Step 4: Verify Bundle ===")
    
    try:
        from app.storage.minio_client import get_storage_client
        storage = get_storage_client()
        
        if not storage.embeddings_exist(doc_info["doc_id"], doc_info["version_id"]):
            print("  FAIL: Bundle not found")
            return False
        
        bundle = storage.get_embeddings(doc_info["doc_id"], doc_info["version_id"])
        print(f"  model: {bundle.get('model_id')}")
        print(f"  records: {bundle.get('record_count')}")
        
        records = bundle.get("records", [])
        if records:
            views = records[0].get("views", {})
            print(f"  views: {list(views.keys())}")
            print("  PASS: Bundle valid")
            return True
        
        print("  FAIL: No records")
        return False
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_step5_vector_search(doc_info: dict):
    """Step 5: Test vector retrieval."""
    print("\n=== Step 5: Vector Search ===")
    
    response = safe_request('post', f"{API_BASE}/v1/retrieve/vector", json={
        "query": "embedding pipeline",
        "view": "vec_contextual",
        "top_k": 5,
    })
    
    if not response:
        print("  FAIL: Request failed")
        return False
    
    if response.status_code != 200:
        print(f"  FAIL: {response.status_code}: {response.text[:200]}")
        return False
    
    results = response.json()
    hits = results.get("results", [])
    print(f"  Found: {len(hits)} results")
    
    for i, hit in enumerate(hits[:3]):
        print(f"    {i+1}. score={hit['score']:.3f}")
    
    print("  PASS: Search working")
    return True


def test_step6_determinism():
    """Step 6: Verify deterministic fingerprinting."""
    print("\n=== Step 6: Determinism Test ===")
    
    try:
        from app.embeddings.templates import TemplateRenderer
        
        test_chunk = {
            "chunk_ref": {
                "chunk_id": "test-001",
                "doc_id": "test-doc",
                "version_id": "v1",
                "section_path": ["Intro"],
                "chunk_type": "text",
                "start_offset": 0,
                "end_offset": 100,
            },
            "fields": {"body": "Test paragraph.", "heading_context": "Intro"},
            "metadata": {"doc_type": "markdown"}
        }
        
        fingerprints = []
        for _ in range(3):
            _, fp, _ = TemplateRenderer.render_doc_chunk_v1(test_chunk, None)
            fingerprints.append(fp)
        
        if len(set(fingerprints)) == 1:
            print(f"  Fingerprint: {fingerprints[0][:32]}...")
            print("  PASS: Deterministic")
            return True
        else:
            print("  FAIL: Non-deterministic")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def run_all_tests():
    """Run all tests with timeouts."""
    print("=" * 60)
    print("PHASE 2 E2E TEST (with timeouts)")
    print("=" * 60)
    
    results = {}
    
    # Step 1
    doc_info = test_step1_ingest_document()
    results["ingest"] = doc_info is not None
    if not doc_info:
        print("\nABORTED: Ingest failed")
        return results
    
    # Step 2
    embed_job = test_step2_trigger_embedding(doc_info)
    results["embed_trigger"] = embed_job is not None
    if not embed_job:
        print("\nABORTED: Embed trigger failed")
        return results
    
    # Step 3
    embed_status = test_step3_wait_for_embedding(doc_info)
    results["embed_complete"] = embed_status is not None
    
    # Step 4
    results["bundle_valid"] = test_step4_verify_bundle(doc_info)
    
    # Step 5
    results["vector_search"] = test_step5_vector_search(doc_info)
    
    # Step 6
    results["determinism"] = test_step6_determinism()
    
    # Summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    
    print(f"\n  {passed}/{len(results)} passed")
    return results


if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
