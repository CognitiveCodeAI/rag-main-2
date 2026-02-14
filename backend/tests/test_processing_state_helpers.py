"""Unit tests for processing-state helper functions."""

from app.db.models import EmbeddingJob, IngestJob
from app.routes.documents import _resolve_processing_state
from app.tasks.embed_nodes import _resolve_final_status


def test_resolve_processing_state_prefers_active_ingest():
    ingest = IngestJob(status="processing", pipeline_stage="chunking", error=None)
    embed = EmbeddingJob(doc_id="doc-1", version_id="1", status="completed", pipeline_stage="indexing")

    status, stage, error = _resolve_processing_state(ingest_job=ingest, embed_job=embed)

    assert status == "processing"
    assert stage == "chunking"
    assert error is None


def test_resolve_processing_state_prefers_failed_ingest():
    ingest = IngestJob(status="failed", pipeline_stage="parsing", error="parse failure")
    embed = EmbeddingJob(doc_id="doc-1", version_id="1", status="completed", pipeline_stage="indexing")

    status, stage, error = _resolve_processing_state(ingest_job=ingest, embed_job=embed)

    assert status == "failed"
    assert stage == "parsing"
    assert error == "parse failure"


def test_resolve_processing_state_awaiting_embedding_when_ingest_completed_without_embed():
    ingest = IngestJob(status="completed", pipeline_stage="completed", error=None)

    status, stage, error = _resolve_processing_state(ingest_job=ingest, embed_job=None)

    assert status == "pending"
    assert stage == "awaiting_embedding"
    assert error is None


def test_resolve_processing_state_uses_embedding_after_ingest_completion():
    ingest = IngestJob(status="completed", pipeline_stage="completed", error=None)
    embed = EmbeddingJob(doc_id="doc-1", version_id="1", status="partial", pipeline_stage="indexing", error="1 node failed")

    status, stage, error = _resolve_processing_state(ingest_job=ingest, embed_job=embed)

    assert status == "partial"
    assert stage == "indexing"
    assert error == "1 node failed"


def test_resolve_processing_state_none_when_no_jobs():
    assert _resolve_processing_state(ingest_job=None, embed_job=None) == (None, None, None)


def test_resolve_final_status_failed_when_zero_indexed_even_without_errors():
    status, error = _resolve_final_status(total_indexed=0, errors=[])
    assert status == "failed"
    assert error == "No vectors were indexed for this document."


def test_resolve_final_status_partial_when_some_indexed_with_errors():
    status, error = _resolve_final_status(total_indexed=7, errors=["chunk_1 failed", "chunk_9 failed"])
    assert status == "partial"
    assert error == "chunk_1 failed; chunk_9 failed"


def test_resolve_final_status_completed_when_indexed_without_errors():
    status, error = _resolve_final_status(total_indexed=7, errors=[])
    assert status == "completed"
    assert error is None
