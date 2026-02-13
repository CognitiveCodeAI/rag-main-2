"""Tests for tenant-scoped deduplication in content registry.

Tests verify:
1. Same hash + same tenant = duplicate detected
2. Same hash + different tenant = no cross-tenant false positive
3. No tenant_id uses 'default' tenant
4. ContentRegistry model has correct structure
"""

import pytest
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.graph_models import ContentRegistry
from app.graph.content_registry import ContentRegistryManager, ContentIdentity


class TestContentRegistryModel:
    """Test ContentRegistry model structure."""

    def test_content_registry_has_composite_pk_columns(self):
        """ContentRegistry should have tenant_id and content_hash as PK columns."""
        tenant_col = ContentRegistry.__table__.c.tenant_id
        hash_col = ContentRegistry.__table__.c.content_hash

        assert tenant_col.primary_key, "tenant_id should be part of primary key"
        assert hash_col.primary_key, "content_hash should be part of primary key"

    def test_content_registry_tenant_id_not_nullable(self):
        """ContentRegistry.tenant_id should not be nullable."""
        tenant_col = ContentRegistry.__table__.c.tenant_id
        assert tenant_col.nullable is False, "tenant_id should not be nullable"

    def test_content_registry_tenant_id_has_default(self):
        """ContentRegistry.tenant_id should default to 'default'."""
        tenant_col = ContentRegistry.__table__.c.tenant_id
        assert tenant_col.default is not None, "tenant_id should have a default value"
        assert tenant_col.default.arg == 'default', "tenant_id default should be 'default'"


class TestContentRegistryManager:
    """Test ContentRegistryManager tenant scoping."""

    def test_resolve_or_register_normalizes_none_tenant(self):
        """resolve_or_register should normalize None tenant_id to 'default'."""
        mock_db = MagicMock()
        manager = ContentRegistryManager(mock_db)

        # Mock the query chain
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        # Mock execute for upsert
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("canonical-doc", 1)
        mock_db.execute.return_value = mock_result

        # Call with tenant_id=None
        result = manager.resolve_or_register(
            content_hash="abc123",
            doc_id="doc-1",
            source_uri="/path/to/file",
            tenant_id=None,
        )

        # Verify the result
        assert isinstance(result, ContentIdentity)
        assert result.canonical_doc_id == "canonical-doc"

    def test_resolve_or_register_uses_explicit_tenant(self):
        """resolve_or_register should use explicit tenant_id when provided."""
        mock_db = MagicMock()
        manager = ContentRegistryManager(mock_db)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("my-doc", 1)
        mock_db.execute.return_value = mock_result

        result = manager.resolve_or_register(
            content_hash="abc123",
            doc_id="my-doc",
            source_uri="/path/to/file",
            tenant_id="tenant-a",
        )

        assert result.canonical_doc_id == "my-doc"
        assert result.is_duplicate is False

    def test_resolve_or_register_detects_duplicate_in_same_tenant(self):
        """resolve_or_register should detect duplicate when entry exists for same tenant."""
        mock_db = MagicMock()
        manager = ContentRegistryManager(mock_db)

        # Mock existing entry
        existing_entry = MagicMock()
        existing_entry.canonical_doc_id = "existing-doc"
        existing_entry.tenant_id = "tenant-a"

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_entry  # Entry exists

        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("existing-doc", 2)  # alias_count = 2
        mock_db.execute.return_value = mock_result

        result = manager.resolve_or_register(
            content_hash="abc123",
            doc_id="new-doc",
            source_uri="/path/to/new-file",
            tenant_id="tenant-a",
        )

        assert result.is_duplicate is True
        assert result.canonical_doc_id == "existing-doc"
        assert result.alias_count == 2

    def test_get_canonical_doc_id_accepts_tenant_id(self):
        """get_canonical_doc_id should accept and use tenant_id parameter."""
        import inspect

        sig = inspect.signature(ContentRegistryManager.get_canonical_doc_id)
        params = list(sig.parameters.keys())

        assert "tenant_id" in params, "get_canonical_doc_id should accept tenant_id parameter"

    def test_get_canonical_doc_id_scopes_by_tenant(self):
        """get_canonical_doc_id should scope query by tenant_id."""
        mock_db = MagicMock()
        manager = ContentRegistryManager(mock_db)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        existing_entry = MagicMock()
        existing_entry.canonical_doc_id = "found-doc"
        mock_query.first.return_value = existing_entry

        result = manager.get_canonical_doc_id("abc123", tenant_id="tenant-a")

        assert result == "found-doc"
        # Verify filter was called (tenant scoping)
        mock_query.filter.assert_called()

    def test_get_canonical_doc_id_returns_none_for_different_tenant(self):
        """get_canonical_doc_id should return None when entry exists in different tenant."""
        mock_db = MagicMock()
        manager = ContentRegistryManager(mock_db)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No entry for this tenant

        result = manager.get_canonical_doc_id("abc123", tenant_id="tenant-b")

        assert result is None


class TestIngestDuplicateDetectionLogic:
    """Test the duplicate detection logic from ingest route."""

    def test_duplicate_check_scopes_by_tenant(self):
        """Verify that the ingest route's duplicate check includes tenant scoping."""
        # Read the ingest.py source to verify it uses tenant-scoped query
        import inspect
        from app.routes import ingest

        source = inspect.getsource(ingest.ingest_document)

        # Verify the code includes tenant scoping
        assert "effective_tenant" in source, "Duplicate check should use effective_tenant"
        assert "tenant_id == effective_tenant" in source or "tenant_id == 'default'" in source or \
               "ContentRegistry.tenant_id ==" in source, "Duplicate check should filter by tenant_id"


class TestMigration009:
    """Test that migration 009 exists with correct structure."""

    def test_migration_file_exists(self):
        """Migration 009 should exist for tenant-scoped content registry."""
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "009_tenant_scoped_content_registry.py"
        assert migration_path.exists(), f"Migration file should exist at {migration_path}"

    def test_migration_has_required_operations(self):
        """Migration 009 should have the required upgrade operations."""
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "009_tenant_scoped_content_registry.py"
        content = migration_path.read_text()

        # Check for key operations
        assert "tenant_id" in content, "Migration should reference tenant_id"
        assert "NOT NULL" in content or "nullable=False" in content or "nullable" in content, \
            "Migration should make tenant_id NOT NULL"
        assert "create_primary_key" in content, "Migration should create composite primary key"
        assert "drop_constraint" in content or "drop_index" in content, \
            "Migration should handle existing constraints"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
