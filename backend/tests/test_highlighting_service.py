"""Unit tests for cross-format highlighting utilities."""

from types import SimpleNamespace

from app.services.highlighting import (
    build_selector_artifacts_for_nodes,
    normalize_text,
    resolve_citation_selector,
    resolve_selector_bundle,
    verify_evidence_span,
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


def test_verify_evidence_span_found_on_cited_page():
    source_map = {
        "canonical_text": "Intro page one text.\n\nInitial Franchise Fee is due at signing.\n\nPage two unrelated text.",
        "nodes": [
            {"node_id": "n1", "start": 0, "end": 20, "page_no": 1},
            {"node_id": "n2", "start": 22, "end": 63, "page_no": 1},
            {"node_id": "n3", "start": 65, "end": 88, "page_no": 2},
        ],
    }

    result = verify_evidence_span(
        doc_id="doc-1",
        page_index=1,
        quote_text="Initial Franchise Fee is due at signing.",
        locator=None,
        source_map=source_map,
        allow_fuzzy=False,
    )
    assert result["status"] == "FOUND"
    assert result["matched_locator"]["type"] == "text_offsets"
    assert result["confidence"] == 1.0


def test_verify_evidence_span_not_found_on_cited_page():
    source_map = {
        "canonical_text": "Intro page one text.\n\nInitial Franchise Fee is due at signing.\n\nPage two unrelated text.",
        "nodes": [
            {"node_id": "n1", "start": 0, "end": 20, "page_no": 1},
            {"node_id": "n2", "start": 22, "end": 63, "page_no": 1},
            {"node_id": "n3", "start": 65, "end": 88, "page_no": 2},
        ],
    }

    result = verify_evidence_span(
        doc_id="doc-1",
        page_index=1,
        quote_text="Page two unrelated text.",
        locator=None,
        source_map=source_map,
        allow_fuzzy=False,
    )
    assert result["status"] == "NOT_FOUND"
    assert result["matched_locator"] is None
    assert result["reason"] == "evidence_not_found_on_cited_page"


def _v2_source_map(quote: str = "Initial Franchise Fee is due"):
    words = quote.split()
    spans = []
    x = 0.1
    for order, word in enumerate(words):
        width = 0.04 + len(word) * 0.003
        spans.append(
            {
                "span_id": f"p1:w{order}",
                "order": order,
                "text": word,
                "block_no": 0,
                "line_no": 0 if order < 3 else 1,
                "word_no": order,
                "normalized_bbox": {
                    "x0": x,
                    "y0": 0.20 if order < 3 else 0.24,
                    "x1": min(0.98, x + width),
                    "y1": 0.22 if order < 3 else 0.26,
                },
                "coordinate_system": "pdf_points_top_left",
                "extraction_source": "native_pdf",
                "verifiable": True,
            }
        )
        x = x + width + 0.01 if order != 2 else 0.1
    return {
        "doc_id": "doc-1",
        "version": 1,
        "content_hash": "sha256:testhash",
        "canonical_text": quote,
        "nodes": [
            {
                "node_id": "n1",
                "start": 0,
                "end": len(quote),
                "page_no": 1,
                "page_rotation": 0,
                "page_size": {"width": 612, "height": 792},
                "source_spans": spans,
            }
        ],
    }


def test_verify_v2_evidence_returns_precise_normalized_line_rectangles():
    source_map = _v2_source_map()
    result = verify_evidence_span(
        doc_id="doc-1",
        node_id="n1",
        page_index=1,
        quote_text="Initial Franchise Fee is due",
        locator=None,
        source_hash="sha256:testhash",
        source_map=source_map,
    )

    assert result["status"] == "FOUND"
    assert result["grade"] == "verified"
    assert result["matched_locator"]["type"] == "rects"
    assert result["matched_locator"]["coordinate_system"] == "normalized_top_left"
    assert len(result["matched_locator"]["rects"]) == 2


def test_verify_v2_evidence_fails_closed_on_ambiguous_quote():
    source_map = _v2_source_map("Fee Fee")
    result = verify_evidence_span(
        doc_id="doc-1",
        node_id="n1",
        page_index=1,
        quote_text="Fee",
        locator=None,
        source_hash="sha256:testhash",
        source_map=source_map,
    )

    assert result["status"] == "NOT_FOUND"
    assert result["grade"] == "unavailable"
    assert result["reason"] == "ambiguous_exact_quote_in_cited_node"


def test_verify_v2_evidence_rejects_stale_source_map_hash():
    result = verify_evidence_span(
        doc_id="doc-1",
        node_id="n1",
        page_index=1,
        quote_text="Initial Franchise Fee is due",
        locator=None,
        source_hash="sha256:changed",
        source_map=_v2_source_map(),
    )

    assert result["status"] == "NOT_FOUND"
    assert result["reason"] == "source_map_content_hash_mismatch"


def test_verify_v2_evidence_rejects_wrong_document_version():
    result = verify_evidence_span(
        doc_id="doc-1",
        document_version=2,
        node_id="n1",
        page_index=1,
        quote_text="Initial Franchise Fee is due",
        locator=None,
        source_hash="sha256:testhash",
        source_map=_v2_source_map(),
    )

    assert result["status"] == "NOT_FOUND"
    assert result["reason"] == "source_map_version_mismatch"


def test_verify_v2_evidence_without_renderable_coordinates_is_unavailable():
    source_map = _v2_source_map()
    for span in source_map["nodes"][0]["source_spans"]:
        span["verifiable"] = False
        span["normalized_bbox"] = None
        span["extraction_source"] = "ocr_text_only"

    result = verify_evidence_span(
        doc_id="doc-1",
        document_version=1,
        node_id="n1",
        page_index=1,
        quote_text="Initial Franchise Fee is due",
        locator=None,
        source_hash="sha256:testhash",
        source_map=source_map,
    )

    assert result["status"] == "NOT_FOUND"
    assert result["grade"] == "unavailable"
    assert result["reason"] == "source_coordinates_not_verifiable"
