"""Characterization tests for the extracted metadata query helpers (E2 2/3)."""

from unittest.mock import MagicMock

from app.qa.metadata_queries import (
    get_doc_collection_version,
    get_doc_total_pages,
    get_nodes_metadata,
)


def _db_first(obj):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = obj
    return db


def test_total_pages_from_meta():
    doc = MagicMock(meta={"total_pages": 7})
    assert get_doc_total_pages(_db_first(doc), "d") == 7


def test_total_pages_defaults_zero():
    assert get_doc_total_pages(_db_first(None), "d") == 0
    assert get_doc_total_pages(_db_first(MagicMock(meta=None)), "d") == 0


def test_collection_version_none_short_circuits_without_query():
    db = MagicMock()
    assert get_doc_collection_version(db, None) is None
    db.query.assert_not_called()  # search-all must not hit the DB


def test_collection_version_returns_stored():
    doc = MagicMock(embedded_collection_version="v2")
    assert get_doc_collection_version(_db_first(doc), "d") == "v2"
    assert get_doc_collection_version(_db_first(None), "d") is None


def test_nodes_metadata_empty_short_circuits():
    db = MagicMock()
    assert get_nodes_metadata(db, []) == {}
    db.query.assert_not_called()


def test_nodes_metadata_maps_ids_to_meta():
    n1 = MagicMock(node_id="a", meta={"x": 1})
    n2 = MagicMock(node_id="b", meta=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [n1, n2]
    assert get_nodes_metadata(db, ["a", "b"]) == {"a": {"x": 1}, "b": {}}
