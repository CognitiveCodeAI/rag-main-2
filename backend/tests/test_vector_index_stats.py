"""Tests for GraphVectorIndex collection stats counting."""

from unittest.mock import MagicMock

from app.graph.vector_index import GraphVectorIndex


def test_collection_stats_prefers_count_query(monkeypatch):
    """Use count(*) query result when available."""
    index = GraphVectorIndex(collection_version="v2")
    fake_collection = MagicMock()
    fake_collection.num_entities = 0
    fake_collection.indexes = [MagicMock()]
    fake_collection.query.return_value = [{"count(*)": 42}]

    monkeypatch.setattr(index, "connect", lambda: None)
    monkeypatch.setattr(index, "_ensure_collection", lambda *_args, **_kwargs: fake_collection)

    stats = index.get_collection_stats("chunk")

    assert stats["name"] == "graph_chunks_v2"
    assert stats["num_entities"] == 42
    assert stats["index_status"] == "indexed"
    assert stats["version"] == "v2"


def test_collection_stats_falls_back_to_num_entities(monkeypatch):
    """Fallback to num_entities when count(*) query fails."""
    index = GraphVectorIndex(collection_version="v2")
    fake_collection = MagicMock()
    fake_collection.num_entities = 7
    fake_collection.indexes = []
    fake_collection.query.side_effect = RuntimeError("query failed")

    monkeypatch.setattr(index, "connect", lambda: None)
    monkeypatch.setattr(index, "_ensure_collection", lambda *_args, **_kwargs: fake_collection)

    stats = index.get_collection_stats("chunk")

    assert stats["num_entities"] == 7
    assert stats["index_status"] == "no_index"
