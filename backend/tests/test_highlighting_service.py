"""Unit tests for cross-format highlighting utilities."""

from types import SimpleNamespace

from app.services.highlighting import (
    build_selector_artifacts_for_nodes,
    normalize_text,
    resolve_citation_selector,
    resolve_selector_bundle,
)


def make_node(node_id: str, text: str, page_no: int = 1, chunk_index: int = 0):
    return SimpleNamespace(
        node_id=node_id,
        doc_id="doc-1",
        version=1,
        node_type=SimpleNamespace(value="chunk"),
        page_no=page_no,
        chunk_index_in_page=chunk_index,
        text_plain=text,
        caption_md=None,
        text_md=None,
        label=None,
        bbox=None,
        meta={},
    )


def make_doc():
    return SimpleNamespace(
        doc_id="doc-1",
        version=1,
        content_hash="sha256:testhash",
        source_uri="upload://sample.txt",
    )


def test_normalize_text_nfkc_and_whitespace():
    assert normalize_text("A\u00a0B   C") == "A B C"


def test_build_selector_artifacts_contains_dual_selectors():
    doc = make_doc()
    nodes = [make_node("n1", "Alpha beta"), make_node("n2", "Gamma delta", chunk_index=1)]

    artifacts = build_selector_artifacts_for_nodes(
        doc=doc,
        nodes=nodes,
        source_type="txt",
        mime_type="text/plain",
    )

    assert artifacts["nodes_with_selectors"] == 2
    selectors = artifacts["selectors"]
    first = selectors[0]
    assert first["text_position"]["start"] == 0
    assert first["text_quote"]["exact"] == "Alpha beta"
    assert first["normalization"] == "unicode_nfkc+ws_collapse"


def test_resolve_selector_bundle_strict_exact_success():
    canonical = "Alpha beta\n\nGamma delta"
    selector = {
        "text_position": {"start": 0, "end": 10},
        "text_quote": {"exact": "Alpha beta", "prefix": "", "suffix": ""},
    }

    status, exact_text, resolved_position, reason = resolve_selector_bundle(
        selector_bundle=selector,
        canonical_text=canonical,
        strict=True,
        allow_fuzzy=False,
    )
    assert status == "exact"
    assert exact_text == "Alpha beta"
    assert resolved_position == {"start": 0, "end": 10}
    assert reason == "position_and_quote_match"


def test_resolve_selector_bundle_strict_fail_closed_on_mismatch():
    canonical = "Alpha beta"
    selector = {
        "text_position": {"start": 0, "end": 5},
        "text_quote": {"exact": "Wrong", "prefix": "", "suffix": ""},
    }

    status, exact_text, resolved_position, reason = resolve_selector_bundle(
        selector_bundle=selector,
        canonical_text=canonical,
        strict=True,
        allow_fuzzy=False,
    )
    assert status == "unresolved"
    assert exact_text is None
    assert resolved_position is None
    assert reason == "quote_mismatch_strict_mode"


class FakeStorage:
    def __init__(self, source_map):
        self._source_map = source_map

    def source_map_exists(self, _doc_id, _version):
        return True

    def get_source_map(self, _doc_id, _version):
        return self._source_map


def test_resolve_citation_selector_fails_on_stale_content_hash():
    doc = SimpleNamespace(doc_id="doc-1", version=1, content_hash="sha256:new")
    selector = {
        "source_state": {"content_hash": "sha256:old"},
        "text_position": {"start": 0, "end": 5},
        "text_quote": {"exact": "Alpha", "prefix": "", "suffix": ""},
    }
    storage = FakeStorage({"canonical_text": "Alpha beta"})

    result = resolve_citation_selector(storage, doc, selector, strict=True, allow_fuzzy=False)
    assert result["resolve_status"] == "unresolved"
    assert result["reason"] == "stale_content_hash"

