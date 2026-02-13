"""Tests for document identity/version mapping contract."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.models import Document, IngestJob
from app.routes.documents import _infer_media_type
from app.services.document_identity import parse_graph_version, resolve_for_embed


class TestIdentityColumns:
    """Model-level contract for explicit graph identity mapping."""

    def test_document_has_graph_identity_columns(self):
        assert "graph_doc_id" in Document.__table__.c
        assert "graph_version" in Document.__table__.c

    def test_ingest_job_has_graph_identity_columns(self):
        assert "graph_doc_id" in IngestJob.__table__.c
        assert "graph_version" in IngestJob.__table__.c


class TestMigration010:
    """Ensure migration file exists for the new contract."""

    def test_migration_file_exists(self):
        migration_path = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "010_graph_identity_mapping.py"
        )
        assert migration_path.exists(), f"Missing migration: {migration_path}"

    def test_migration_contains_required_operations(self):
        migration_path = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "010_graph_identity_mapping.py"
        )
        content = migration_path.read_text()
        assert "graph_doc_id" in content
        assert "graph_version" in content
        assert "documents" in content
        assert "ingest_jobs" in content


class TestIdentityResolution:
    """Behavior checks for identity resolver helpers."""

    def test_parse_graph_version(self):
        assert parse_graph_version("3") == 3
        assert parse_graph_version("v202601") is None
        assert parse_graph_version(None) is None

    def test_resolve_for_embed_uses_legacy_mapping(self):
        db = MagicMock()
        legacy_doc = SimpleNamespace(
            doc_id="legacy-123",
            version_id="v20260213010101-abcd1234",
            graph_doc_id="graph-abc",
            graph_version=2,
            source_uri="upload://sample.pdf",
        )
        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = legacy_doc

        resolved = resolve_for_embed(db, "legacy-123", legacy_doc.version_id)

        assert resolved is not None
        assert resolved.graph_doc_id == "graph-abc"
        assert resolved.graph_version == 2
        assert resolved.legacy_doc_id == "legacy-123"
        assert resolved.legacy_version_id == legacy_doc.version_id

    def test_resolve_for_embed_direct_graph_identity(self):
        db = MagicMock()
        graph_doc = SimpleNamespace(doc_id="graph-xyz", version=7)
        query = MagicMock()
        db.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = graph_doc

        resolved = resolve_for_embed(db, "graph-xyz", "7")

        assert resolved is not None
        assert resolved.graph_doc_id == "graph-xyz"
        assert resolved.graph_version == 7
        assert resolved.legacy_doc_id is None


class TestRawMediaType:
    """Raw endpoint media type helpers should be format-aware."""

    def test_infer_media_type_prefers_explicit_type(self):
        assert _infer_media_type("report.pdf", "application/pdf") == "application/pdf"

    def test_infer_media_type_from_filename(self):
        assert _infer_media_type("report.docx", None) == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_infer_media_type_falls_back_to_octet_stream(self):
        assert _infer_media_type("no_extension_file", None) == "application/octet-stream"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
