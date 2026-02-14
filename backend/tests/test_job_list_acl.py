"""Regression tests for ACL filtering on ingest/embed job listing endpoints."""

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.models import Document, EmbeddingJob, IngestJob
from app.db.session import session_scope
from main import app

client = TestClient(app)


def _make_document(doc_id: str) -> Document:
    return Document(
        doc_id=doc_id,
        version_id="v1",
        source_type="pdf",
        source_uri=f"upload://{doc_id}.pdf",
        mime_type="application/pdf",
        checksum=uuid.uuid4().hex,
    )


def test_list_ingest_jobs_applies_acl_filter_to_doc_and_graph_ids():
    doc_allow = f"acl-ingest-allow-{uuid.uuid4().hex[:8]}"
    doc_deny = f"acl-ingest-deny-{uuid.uuid4().hex[:8]}"
    graph_allow = f"graph-allow-{uuid.uuid4().hex[:8]}"
    graph_deny = f"graph-deny-{uuid.uuid4().hex[:8]}"
    job_allow_id = uuid.uuid4()
    job_deny_id = uuid.uuid4()

    with session_scope() as session:
        session.merge(_make_document(doc_allow))
        session.merge(_make_document(doc_deny))
        session.add(
            IngestJob(
                job_id=job_allow_id,
                doc_id=doc_allow,
                graph_doc_id=graph_allow,
                status="pending",
            )
        )
        session.add(
            IngestJob(
                job_id=job_deny_id,
                doc_id=doc_deny,
                graph_doc_id=graph_deny,
                status="pending",
            )
        )

    try:
        with patch("app.routes.ingest.ACLPostgresFilter.get_accessible_doc_ids", return_value={graph_allow}):
            response = client.get("/v1/ingest/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["job_id"] == str(job_allow_id)
    finally:
        with session_scope() as session:
            session.query(IngestJob).filter(IngestJob.job_id.in_([job_allow_id, job_deny_id])).delete(
                synchronize_session=False
            )
            session.query(Document).filter(Document.doc_id.in_([doc_allow, doc_deny])).delete(
                synchronize_session=False
            )


def test_list_embed_jobs_applies_acl_filter_to_doc_ids():
    doc_allow = f"acl-embed-allow-{uuid.uuid4().hex[:8]}"
    doc_deny = f"acl-embed-deny-{uuid.uuid4().hex[:8]}"
    job_allow_id = uuid.uuid4()
    job_deny_id = uuid.uuid4()

    with session_scope() as session:
        session.add(
            EmbeddingJob(
                job_id=job_allow_id,
                doc_id=doc_allow,
                version_id="1",
                status="pending",
            )
        )
        session.add(
            EmbeddingJob(
                job_id=job_deny_id,
                doc_id=doc_deny,
                version_id="1",
                status="pending",
            )
        )

    try:
        with patch("app.routes.embed.ACLPostgresFilter.get_accessible_doc_ids", return_value={doc_allow}):
            response = client.get("/v1/embed/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["job_id"] == str(job_allow_id)
    finally:
        with session_scope() as session:
            session.query(EmbeddingJob).filter(EmbeddingJob.job_id.in_([job_allow_id, job_deny_id])).delete(
                synchronize_session=False
            )
