"""Unit tests for ingestion components (no external services required).

Run with: python tests/test_components.py
"""

import sys
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_parser():
    """Test document parser."""
    print("Testing Parser...")
    
    from app.parsers import ParserRegistry
    
    content = b"""# Test Document

This is a test paragraph.

## Section 1

Some content here.

```python
def hello():
    print("Hello")
```

| A | B |
|---|---|
| 1 | 2 |
"""
    
    doc_ref = {
        "schema_version": "1.0",
        "doc_id": "test-001",
        "version_id": "v1",
        "source_type": "md",
        "source_uri": "test://test.md",
        "checksum": hashlib.sha256(content).hexdigest(),
    }
    
    ir = ParserRegistry.parse(content, doc_ref)
    ir_dict = ir.to_dict()
    
    assert ir_dict["schema_version"] == "1.0"
    assert len(ir.pages) > 0
    print(f"  ✓ Parsed: {len(ir.pages)} pages, {len(ir.sections)} sections")
    
    # Count block types
    types = {}
    for page in ir.pages:
        for block in page.blocks:
            types[block.type] = types.get(block.type, 0) + 1
    print(f"  ✓ Blocks: {types}")
    
    return True


def test_chunker():
    """Test document chunker."""
    print("Testing Chunker...")
    
    from app.parsers import ParserRegistry
    from app.chunker import chunk_document, ChunkingConfig
    
    content = b"""# Main Title

Introduction paragraph with some text.

## First Section

This section has detailed content that should be chunked appropriately.
It contains multiple sentences to ensure proper chunking behavior.

## Second Section

Another section with different content.

```python
def example():
    return "code"
```

| Header1 | Header2 |
|---------|---------|
| Data1   | Data2   |
"""
    
    doc_ref = {
        "schema_version": "1.0",
        "doc_id": "test-chunker",
        "version_id": "v1",
        "source_type": "md",
        "source_uri": "test://test.md",
        "checksum": hashlib.sha256(content).hexdigest(),
    }
    
    ir = ParserRegistry.parse(content, doc_ref)
    config = ChunkingConfig(target_tokens=128, max_tokens=256)
    chunks = chunk_document(ir, config)
    
    assert len(chunks) > 0
    print(f"  ✓ Created {len(chunks)} chunks")
    
    # Validate chunk structure
    for chunk in chunks:
        assert "schema_version" in chunk
        assert "chunk_ref" in chunk
        assert "fields" in chunk
        assert "body" in chunk["fields"]
    print("  ✓ All chunks have valid structure")
    
    # Show types
    types = {}
    for chunk in chunks:
        t = chunk["chunk_ref"]["chunk_type"]
        types[t] = types.get(t, 0) + 1
    print(f"  ✓ Chunk types: {types}")
    
    return True


def test_schemas():
    """Test JSON schema loading."""
    print("Testing Schemas...")
    
    import json
    from pathlib import Path
    
    schema_dir = Path(__file__).parent.parent.parent / "contracts" / "schemas" / "v1"
    
    schemas = [
        "document-ref.schema.json",
        "document-ir.schema.json",
        "chunk-record.schema.json",
        "retrieval-plan.schema.json",
        "trace.schema.json",
        "golden-record.schema.json",
    ]
    
    for schema_name in schemas:
        path = schema_dir / schema_name
        assert path.exists(), f"Schema not found: {schema_name}"
        with open(path) as f:
            schema = json.load(f)
        assert "$schema" in schema
        print(f"  ✓ {schema_name}")
    
    return True


def test_models():
    """Test SQLAlchemy models load correctly."""
    print("Testing Models...")
    
    from app.db.models import Document, IngestJob, DocumentIR, Chunk, Trace, GoldenRecord
    
    # Just verify they can be imported
    assert Document.__tablename__ == "documents"
    assert IngestJob.__tablename__ == "ingest_jobs"
    assert DocumentIR.__tablename__ == "document_ir"
    assert Chunk.__tablename__ == "chunks"
    assert Trace.__tablename__ == "traces"
    assert GoldenRecord.__tablename__ == "golden_records"
    
    print("  ✓ All models load correctly")
    return True


def test_routes():
    """Test FastAPI routes load correctly."""
    print("Testing Routes...")
    
    from main import app
    
    routes = [r.path for r in app.routes]
    
    required = [
        "/v1/ingest/document",
        "/v1/ingest/job/{job_id}",
        "/health",
    ]
    
    for r in required:
        assert r in routes, f"Missing route: {r}"
        print(f"  ✓ {r}")
    
    print(f"  Total routes: {len(routes)}")
    return True


def main():
    """Run all unit tests."""
    print("=" * 50)
    print("  NPR RAG - Component Unit Tests")
    print("=" * 50)
    print()
    
    tests = [
        ("Schemas", test_schemas),
        ("Models", test_models),
        ("Parser", test_parser),
        ("Chunker", test_chunker),
        ("Routes", test_routes),
    ]
    
    results = {}
    for name, test_fn in tests:
        try:
            results[name] = test_fn()
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            results[name] = False
        print()
    
    # Summary
    print("=" * 50)
    print("  SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)
    
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {name:15} : {status}")
    
    print()
    print(f"  {passed} passed, {failed} failed")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
