"""Unit tests for the embedding-reconciliation predicate (D4 / audit H-5)."""

from app.services.embedding_reconciler import doc_needs_embedding


def test_canonical_doc_with_nodes_but_no_embedding_needs_it():
    assert doc_needs_embedding(
        embedded_collection_version=None, canonical_doc_id=None, has_nodes=True
    ) is True


def test_already_embedded_does_not_need_it():
    assert doc_needs_embedding(
        embedded_collection_version="v2", canonical_doc_id=None, has_nodes=True
    ) is False


def test_alias_does_not_need_embedding():
    # Aliases reuse the canonical doc's vectors.
    assert doc_needs_embedding(
        embedded_collection_version=None, canonical_doc_id="canon-123", has_nodes=True
    ) is False


def test_doc_without_nodes_does_not_need_embedding():
    assert doc_needs_embedding(
        embedded_collection_version=None, canonical_doc_id=None, has_nodes=False
    ) is False
