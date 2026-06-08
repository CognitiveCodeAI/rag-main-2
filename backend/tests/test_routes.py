"""Comprehensive API route tests for /v1/* endpoints.

Tests cover:
1. Request validation (invalid inputs, boundary conditions)
2. Error handling (404, 400, 500 scenarios)
3. Success scenarios with mock dependencies
"""

import uuid
from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================

class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_root_health(self):
        """Root endpoint should return API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data or "status" in data or "app_name" in data
    
    def test_health_endpoint(self):
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["ok", "healthy"]

    def test_health_live_endpoint(self):
        """Liveness endpoint should always be available without dependency checks."""
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
    
    def test_qa_health(self):
        """QA health endpoint should return ok status."""
        response = client.get("/v1/qa/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("service") == "qa"

    @patch("app.db.session.engine.connect")
    def test_health_service_checks_redact_internal_errors(self, mock_connect):
        """Service-health diagnostics should not expose raw backend exception text."""
        mock_connect.side_effect = Exception("postgres://secret-host")

        response = client.get("/health?check_services=true")
        assert response.status_code == 200
        data = response.json()
        postgres = data.get("services", {}).get("postgresql", {})
        message = postgres.get("message", "")

        assert postgres.get("status") == "unhealthy"
        assert "error_id=" in message
        assert "secret-host" not in message


# =============================================================================
# INGEST API TESTS
# =============================================================================

class TestIngestValidation:
    """Test /v1/ingest endpoint validation."""
    
    def test_empty_file_rejected(self):
        """Empty files should be rejected with 400."""
        response = client.post(
            "/v1/ingest/document",
            files={"file": ("test.pdf", b"", "application/pdf")}
        )
        assert response.status_code == 400
        assert "empty" in response.json().get("detail", "").lower()
    
    def test_unsupported_source_type_rejected(self):
        """Unsupported source types should be rejected."""
        response = client.post(
            "/v1/ingest/document",
            files={"file": ("test.xyz", b"test content", "application/octet-stream")},
            data={"source_type": "xyz"}
        )
        assert response.status_code == 415
        assert "unsupported" in response.json().get("detail", "").lower()

    @patch("app.routes.ingest.get_settings")
    def test_metadata_preview_rejects_oversized_file(self, mock_get_settings):
        """Metadata preview should return 413 before processing oversized files."""
        mock_get_settings.return_value = MagicMock(upload_max_file_size_mb=1)
        too_large = b"x" * (1024 * 1024 + 1)

        response = client.post(
            "/v1/ingest/metadata-preview",
            files={"file": ("too-large.txt", too_large, "text/plain")},
        )

        assert response.status_code == 413
        assert "exceeds" in response.json().get("detail", "").lower()

    @patch("app.routes.ingest.get_settings")
    def test_ingest_rejects_oversized_file(self, mock_get_settings):
        """Direct ingest should return 413 before worker/storage calls."""
        mock_get_settings.return_value = MagicMock(upload_max_file_size_mb=1)
        too_large = b"x" * (1024 * 1024 + 1)

        response = client.post(
            "/v1/ingest/document",
            files={"file": ("too-large.txt", too_large, "text/plain")},
        )

        assert response.status_code == 413
        assert "exceeds" in response.json().get("detail", "").lower()
    
    def test_invalid_job_id_format(self):
        """Invalid job ID format should return 400."""
        response = client.get("/v1/ingest/job/not-a-uuid")
        assert response.status_code == 400
        assert "invalid" in response.json().get("detail", "").lower()
    
    def test_nonexistent_job_returns_404(self):
        """Non-existent job ID should return 404."""
        fake_uuid = str(uuid.uuid4())
        response = client.get(f"/v1/ingest/job/{fake_uuid}")
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()
    
    def test_nonexistent_document_versions_returns_404(self):
        """Non-existent document should return 404."""
        response = client.get("/v1/ingest/document/nonexistent-doc-id/versions")
        assert response.status_code == 404

    def test_parse_json_list_rejects_invalid_json(self):
        """Malformed ACL JSON payloads should fail with 400."""
        from app.routes.ingest import _parse_json_list

        with pytest.raises(HTTPException) as exc:
            _parse_json_list("not-json", "allowed_roles")

        assert exc.value.status_code == 400
        assert "allowed_roles" in str(exc.value.detail)

    def test_parse_json_list_rejects_non_string_entries(self):
        """ACL list payload must contain only strings."""
        from app.routes.ingest import _parse_json_list

        with pytest.raises(HTTPException) as exc:
            _parse_json_list('["analyst", 123]', "allowed_roles")

        assert exc.value.status_code == 400
        assert "allowed_roles" in str(exc.value.detail)

    @patch("app.routes.ingest.fitz.open")
    @patch("app.routes.ingest.inspect_celery_workers")
    def test_ingest_rejected_when_worker_unavailable(self, mock_worker_status, mock_fitz_open):
        """Ingestion should fail fast when no Celery workers are responding."""
        from app.services.worker_health import CeleryWorkerStatus

        mock_fitz_open.return_value.__enter__.return_value = MagicMock()
        mock_worker_status.return_value = CeleryWorkerStatus(
            healthy=False,
            worker_count=0,
            message="No Celery workers responded to ping.",
        )

        response = client.post(
            "/v1/ingest/document",
            files={"file": ("test.pdf", b"%PDF-1.4 test content", "application/pdf")},
        )

        assert response.status_code == 503
        assert "queue is unavailable" in response.json().get("detail", "").lower()


class TestIngestSuccess:
    """Test successful ingestion scenarios."""
    
    @patch("app.routes.ingest.fitz.open")
    @patch("app.routes.ingest.inspect_celery_workers")
    @patch("app.routes.ingest.ingest_document_task")
    @patch("app.routes.ingest.get_storage_client")
    @patch("app.routes.ingest._require_embedding_config")
    def test_pdf_ingestion_success(
        self,
        mock_require_embedding,
        mock_storage,
        mock_task,
        mock_worker_status,
        mock_fitz_open,
    ):
        """PDF upload should succeed and return job info."""
        from app.services.worker_health import CeleryWorkerStatus

        mock_require_embedding.return_value = None
        mock_storage.return_value = MagicMock()
        mock_task.apply_async = MagicMock()
        mock_fitz_open.return_value.__enter__.return_value = MagicMock()
        mock_worker_status.return_value = CeleryWorkerStatus(
            healthy=True,
            worker_count=1,
            message="1 Celery worker responding.",
        )
        
        pdf_content = b"%PDF-1.4 test content"
        
        response = client.post(
            "/v1/ingest/document",
            files={"file": ("test.pdf", pdf_content, "application/pdf")}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "doc_id" in data
        assert "version_id" in data
        assert data["status"] == "pending"
        
        # Verify task was queued
        mock_task.apply_async.assert_called_once()
    
    @patch("app.routes.ingest.fitz.open")
    @patch("app.routes.ingest.inspect_celery_workers")
    @patch("app.routes.ingest.ingest_document_task")
    @patch("app.routes.ingest.get_storage_client")
    @patch("app.routes.ingest._require_embedding_config")
    def test_custom_doc_id_respected(
        self,
        mock_require_embedding,
        mock_storage,
        mock_task,
        mock_worker_status,
        mock_fitz_open,
    ):
        """Custom doc_id should be used when provided."""
        from app.services.worker_health import CeleryWorkerStatus

        mock_require_embedding.return_value = None
        mock_storage.return_value = MagicMock()
        mock_task.apply_async = MagicMock()
        mock_fitz_open.return_value.__enter__.return_value = MagicMock()
        mock_worker_status.return_value = CeleryWorkerStatus(
            healthy=True,
            worker_count=1,
            message="1 Celery worker responding.",
        )
        
        response = client.post(
            "/v1/ingest/document",
            files={"file": ("test.pdf", b"test content", "application/pdf")},
            data={"doc_id": "custom-doc-id-123"}
        )
        
        assert response.status_code == 200
        assert response.json()["doc_id"] == "custom-doc-id-123"

    @patch("app.routes.ingest.fitz.open")
    @patch("app.routes.ingest.get_storage_client")
    @patch("app.routes.ingest.MetadataExtractor.extract")
    def test_metadata_preview_success(self, mock_extract, mock_storage, mock_fitz_open):
        """Metadata preview endpoint should stage file and return extracted metadata."""
        from app.metadata.extractor import ExtractedMetadata

        mock_storage.return_value = MagicMock()
        mock_fitz_open.return_value.__enter__.return_value = MagicMock()
        mock_extract.return_value = ExtractedMetadata(
            year=2025,
            doc_type="policy",
            department="legal",
            authority_tier=1,
            provenance={
                "year": "filename",
                "doc_type": "filename",
                "department": "filename",
                "authority_tier": "derived",
            },
            confidence={
                "year": 0.8,
                "doc_type": 0.8,
                "department": 0.8,
                "authority_tier": 0.7,
            },
        )

        response = client.post(
            "/v1/ingest/metadata-preview",
            files={"file": ("policy.pdf", b"%PDF-1.4 test content", "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()
        assert "preview_id" in data
        assert data["filename"] == "policy.pdf"
        assert data["metadata_extracted"]["doc_type"] == "policy"
        assert data["metadata_extracted"]["department"] == "legal"

    @patch("app.routes.ingest.fitz.open")
    @patch("app.routes.ingest.inspect_celery_workers")
    @patch("app.routes.ingest.ingest_document_task")
    @patch("app.routes.ingest.get_storage_client")
    @patch("app.routes.ingest._require_embedding_config")
    def test_process_preview_queues_ingestion_with_metadata_overrides(
        self,
        mock_require_embedding,
        mock_storage,
        mock_task,
        mock_worker_status,
        mock_fitz_open,
    ):
        """Process endpoint should enqueue ingest task using staged preview + overrides."""
        from app.db.models import IngestPreview
        from app.db.session import session_scope
        from app.services.worker_health import CeleryWorkerStatus

        mock_require_embedding.return_value = None
        mock_fitz_open.return_value.__enter__.return_value = MagicMock()
        storage_client = MagicMock()
        storage_client.get_raw.return_value = b"%PDF-1.4 staged content"
        mock_storage.return_value = storage_client
        mock_task.apply_async = MagicMock()
        mock_worker_status.return_value = CeleryWorkerStatus(
            healthy=True,
            worker_count=1,
            message="1 Celery worker responding.",
        )

        preview_uuid = uuid.uuid4()
        with session_scope() as session:
            session.add(
                IngestPreview(
                    preview_id=preview_uuid,
                    filename="staged.pdf",
                    source_type="pdf",
                    mime_type="application/pdf",
                    preview_doc_id=f"preview-{preview_uuid.hex}",
                    preview_version_id="v-preview",
                    checksum=uuid.uuid4().hex,
                    metadata_extracted={
                        "doc_type": "policy",
                        "department": "legal",
                    },
                    metadata_provenance={
                        "doc_type": "filename",
                        "department": "filename",
                    },
                    metadata_confidence={
                        "doc_type": 0.8,
                        "department": 0.8,
                    },
                    status="ready",
                    expires_at=datetime.utcnow() + timedelta(minutes=30),
                )
            )

        response = client.post(
            "/v1/ingest/process",
            json={
                "preview_id": str(preview_uuid),
                "metadata_overrides": {"department": "engineering"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert "job_id" in data

        mock_task.apply_async.assert_called_once()
        _, call_kwargs = mock_task.apply_async.call_args
        # enqueue() forwards task kwargs under apply_async(kwargs=...)
        task_kwargs = call_kwargs["kwargs"]
        assert task_kwargs["metadata_overrides"] == {"department": "engineering"}


# =============================================================================
# QA API TESTS
# =============================================================================

class TestQAValidation:
    """Test /v1/qa endpoint validation."""
    
    @patch("app.routes.qa.QARunner")
    def test_missing_doc_id(self, mock_runner_class):
        """Missing doc_id is allowed (query can run across all docs)."""
        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "question": "What is the fee?",
            "doc_id": None,
            "seed_nodes": [],
            "expanded_nodes": [],
            "edge_traces": [],
            "packed_context": "",
            "context_node_ids": [],
            "total_context_tokens": 0,
            "answer": "Mock answer",
            "citations": [],
            "model_id": "mock-model",
            "timing": {"total_ms": 1},
            "metadata": {},
            "success": True,
            "error": None,
        }
        mock_runner.run.return_value = mock_result

        response = client.post(
            "/v1/qa/ask",
            json={"question": "What is the fee?"}
        )
        assert response.status_code == 200
    
    def test_missing_question(self):
        """Missing question should fail validation."""
        response = client.post(
            "/v1/qa/ask",
            json={"doc_id": "test-doc-123"}
        )
        assert response.status_code == 422
    
    def test_top_k_too_low(self):
        """top_k below minimum should fail validation."""
        response = client.post(
            "/v1/qa/ask",
            json={
                "doc_id": "test-doc-123",
                "question": "What is the fee?",
                "top_k": 0
            }
        )
        assert response.status_code == 422
    
    def test_top_k_too_high(self):
        """top_k above maximum should fail validation."""
        response = client.post(
            "/v1/qa/ask",
            json={
                "doc_id": "test-doc-123",
                "question": "What is the fee?",
                "top_k": 100
            }
        )
        assert response.status_code == 422
    
    def test_invalid_mode(self):
        """Invalid mode should fail validation."""
        response = client.post(
            "/v1/qa/ask",
            json={
                "doc_id": "test-doc-123",
                "question": "What is the fee?",
                "mode": "invalid_mode"
            }
        )
        assert response.status_code == 422


class TestQASuccess:
    """Test successful QA scenarios."""
    
    @patch("app.routes.qa.QARunner")
    def test_ask_returns_expected_structure(self, mock_runner_class):
        """Ask endpoint should return expected response structure."""
        # Setup mock
        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner
        
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "question": "What is the fee?",
            "doc_id": "test-doc-123",
            "seed_nodes": [],
            "expanded_nodes": [],
            "edge_traces": [],
            "packed_context": "Context text...",
            "context_node_ids": ["node1", "node2"],
            "total_context_tokens": 100,
            "answer": "The fee is $45,000.",
            "citations": [{"node_id": "node1", "page_no": 1}],
            "model_id": "gpt-5.2",
            "timing": {"total_ms": 1500},
            "metadata": {},
            "success": True,
            "error": None
        }
        mock_runner.run.return_value = mock_result
        
        response = client.post(
            "/v1/qa/ask",
            json={
                "doc_id": "test-doc-123",
                "question": "What is the fee?"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert data["question"] == "What is the fee?"
        assert data["doc_id"] == "test-doc-123"
        assert data["answer"] == "The fee is $45,000."
        assert data["success"] is True
        assert "timing" in data
        assert "citations" in data
    
    @patch("app.routes.qa.QARunner")
    def test_propagation_safety_mode_accepted(self, mock_runner_class):
        """propagation_safety mode should be accepted."""
        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner
        
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "question": "What is the fee?",
            "doc_id": "test-doc",
            "seed_nodes": [],
            "expanded_nodes": [],
            "edge_traces": [],
            "packed_context": "",
            "context_node_ids": [],
            "total_context_tokens": 0,
            "answer": "Answer",
            "citations": [],
            "model_id": "gpt-5.2",
            "timing": {},
            "metadata": {},
            "propagation_safety_mode": True,
            "propagation_safety_audit": {"sub_questions": []},
            "success": True,
            "error": None
        }
        mock_runner.run.return_value = mock_result
        
        response = client.post(
            "/v1/qa/ask",
            json={
                "doc_id": "test-doc",
                "question": "What is the fee?",
                "mode": "propagation_safety"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["propagation_safety_mode"] is True


class TestQAErrorHandling:
    """Test QA error handling."""
    
    @patch("app.routes.qa.QARunner")
    def test_runner_exception_returns_500(self, mock_runner_class):
        """Runner exceptions should return 500."""
        mock_runner = MagicMock()
        mock_runner_class.return_value = mock_runner
        mock_runner.run.side_effect = Exception("Database connection failed")
        
        response = client.post(
            "/v1/qa/ask",
            json={
                "doc_id": "test-doc",
                "question": "What is the fee?"
            }
        )
        
        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert "internal server error" in detail.lower()
        assert "error_id=" in detail


# =============================================================================
# RETRIEVE API TESTS
# =============================================================================

class TestRetrieveValidation:
    """Test /v1/retrieve endpoint validation."""
    
    def test_vector_search_missing_query(self):
        """Missing query should fail validation."""
        response = client.post(
            "/v1/retrieve/vector",
            json={"doc_id": "test-doc"}
        )
        assert response.status_code == 422
    
    def test_vector_search_invalid_top_k(self):
        """Invalid top_k should fail validation."""
        response = client.post(
            "/v1/retrieve/vector",
            json={
                "query": "test query",
                "doc_id": "test-doc",
                "top_k": 0
            }
        )
        assert response.status_code == 422
    
    def test_vector_search_top_k_too_high(self):
        """top_k above 100 should fail validation."""
        response = client.post(
            "/v1/retrieve/vector",
            json={
                "query": "test query",
                "doc_id": "test-doc",
                "top_k": 200
            }
        )
        assert response.status_code == 422

    @patch("app.routes.retrieve.GraphVectorIndex")
    @patch("app.routes.retrieve.get_embedding_client")
    def test_vector_search_accepts_top_level_doc_id_filter(
        self,
        mock_get_embedding_client,
        mock_vector_index_cls,
    ):
        """Top-level doc_id should be honored for backward compatibility."""
        mock_embed_client = MagicMock()
        mock_embed_client.embed_single.return_value = ([0.1, 0.2, 0.3], {})
        mock_get_embedding_client.return_value = mock_embed_client

        mock_vector_index = MagicMock()
        mock_vector_index.search.return_value = []
        mock_vector_index_cls.return_value = mock_vector_index

        response = client.post(
            "/v1/retrieve/vector",
            json={"query": "test query", "doc_id": "doc-123"},
        )

        assert response.status_code == 200
        assert response.json()["total"] == 0
        assert mock_vector_index.search.call_args.kwargs["doc_id_filter"] == "doc-123"

    @patch("app.routes.retrieve.get_embedding_client")
    def test_vector_search_redacts_internal_exception_detail(self, mock_get_embedding_client):
        """Internal retrieval exceptions should return stable error IDs."""
        mock_get_embedding_client.side_effect = Exception("sensitive-uri")

        response = client.post(
            "/v1/retrieve/vector",
            json={"query": "test query"},
        )

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert "internal server error" in detail.lower()
        assert "error_id=" in detail
        assert "sensitive-uri" not in detail


class TestSettingsErrorHandling:
    """Test /v1/settings error response hardening."""

    @patch("app.routes.settings.get_or_create_settings")
    def test_get_settings_redacts_internal_exception_detail(self, mock_get_settings):
        """Settings endpoint should not leak raw exception messages."""
        mock_get_settings.side_effect = Exception("db://secret")

        response = client.get("/v1/settings")

        assert response.status_code == 500
        detail = response.json().get("detail", "")
        assert "internal server error" in detail.lower()
        assert "error_id=" in detail
        assert "db://secret" not in detail


class TestACLRouteHardening:
    """Ensure ACL policy routes fail closed when ACL is disabled."""

    @patch("app.acl.dependencies.get_settings")
    def test_acl_policy_get_unavailable_when_acl_disabled(self, mock_get_settings):
        settings = MagicMock()
        settings.acl_enabled = False
        settings.auth_enabled = False
        mock_get_settings.return_value = settings

        response = client.get(f"/v1/acl/documents/{uuid.uuid4()}/policy")
        assert response.status_code == 503
        assert response.json().get("detail") == "ACL feature is disabled"

    @patch("app.acl.dependencies.get_settings")
    def test_acl_policy_update_unavailable_when_acl_disabled(self, mock_get_settings):
        settings = MagicMock()
        settings.acl_enabled = False
        settings.auth_enabled = False
        mock_get_settings.return_value = settings

        response = client.put(
            f"/v1/acl/documents/{uuid.uuid4()}/policy",
            json={"visibility": "public"},
        )
        assert response.status_code == 503
        assert response.json().get("detail") == "ACL feature is disabled"


# =============================================================================
# EMBED API TESTS
# =============================================================================

class TestEmbedValidation:
    """Test /v1/embed endpoint validation."""

    def test_embed_job_invalid_uuid(self):
        """Invalid job UUID should return 400."""
        response = client.get("/v1/embed/job/not-a-uuid")
        # May return 404 or 400 depending on implementation
        assert response.status_code in [400, 404, 422]


class TestEmbedSuccess:
    """Test successful embed scenarios."""

    @patch("app.routes.embed.get_storage_client")
    def test_get_document_embed_status_success(self, mock_storage):
        """Test embed status endpoint when bundle exists."""
        mock_client = MagicMock()
        mock_storage.return_value = mock_client
        mock_client.get_embeddings.return_value = {
            "bundle_version": "1.0",
            "record_count": 42,
            "model_id": "text-embedding-3-small",
            "created_at": "2026-01-01T00:00:00Z",
        }
        response = client.get("/v1/embed/document/test-doc/1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["bundle_exists"] is True
        assert data["doc_id"] == "test-doc"
        assert data["version_id"] == "1"
        assert data["bundle_info"]["bundle_version"] == "1.0"
        assert data["bundle_info"]["record_count"] == 42

    @patch("app.routes.embed.get_storage_client")
    def test_get_document_embed_status_no_bundle(self, mock_storage):
        """Test embed status endpoint when bundle does not exist."""
        mock_client = MagicMock()
        mock_storage.return_value = mock_client
        mock_client.get_embeddings.side_effect = Exception("Not found")
        response = client.get("/v1/embed/document/test-doc/1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["bundle_exists"] is False
        assert data["bundle_info"] is None


# =============================================================================
# RESPONSE FORMAT TESTS
# =============================================================================

class TestResponseFormats:
    """Test that responses follow expected formats."""
    
    def test_error_responses_have_detail(self):
        """Error responses should have 'detail' field."""
        response = client.get("/v1/ingest/job/invalid-uuid")
        assert response.status_code in [400, 422]
        # FastAPI standard error format
        assert "detail" in response.json()
    
    def test_validation_errors_have_detail(self):
        """Validation errors should have 'detail' field."""
        response = client.post("/v1/qa/ask", json={})
        assert response.status_code == 422
        assert "detail" in response.json()


# =============================================================================
# CONCURRENT REQUEST TESTS
# =============================================================================

class TestConcurrentRequests:
    """Test handling of concurrent requests."""
    
    def test_multiple_health_checks(self):
        """Multiple concurrent health checks should all succeed."""
        import concurrent.futures
        
        def make_request():
            return client.get("/v1/qa/health")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        assert all(r.status_code == 200 for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
