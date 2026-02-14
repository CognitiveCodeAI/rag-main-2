"""Tests for EvidenceSpan parsing and normalization contract."""

from app.qa.evidence_span import (
    EvidenceSpan,
    build_evidence_spans,
    normalize_page_index,
    parse_evidence_span,
)


def test_parse_evidence_span_text_offsets_schema():
    span = parse_evidence_span(
        {
            "doc_id": "doc-1",
            "page_index": 4,
            "page_index_base": 1,
            "quote_text": "Alpha beta",
            "locator": {"type": "text_offsets", "start": 10, "end": 20},
            "confidence": 1.0,
        }
    )
    assert span.doc_id == "doc-1"
    assert span.page_index == 4
    assert span.page_index_base == 1
    assert span.quote_text == "Alpha beta"
    assert span.locator.type == "text_offsets"


def test_parse_evidence_span_bbox_schema():
    span = parse_evidence_span(
        {
            "doc_id": "doc-2",
            "page_index": 2,
            "quote_text": "Clause text",
            "locator": {
                "type": "bbox",
                "bbox": {"x0": 10.0, "y0": 20.0, "x1": 80.0, "y1": 40.0},
                "page_size": {"width": 612.0, "height": 792.0},
            },
            "confidence": 0.9,
        }
    )
    assert span.locator.type == "bbox"
    assert span.locator.bbox.x0 == 10.0
    assert span.locator.page_size.width == 612.0


def test_normalize_page_index_from_zero_based_input():
    assert normalize_page_index(0, page_index_base=0) == 1
    assert normalize_page_index(14, page_index_base=0) == 15
    assert normalize_page_index(15, page_index_base=1) == 15


def test_evidence_span_serialization_round_trip():
    original = EvidenceSpan.model_validate(
        {
            "doc_id": "doc-3",
            "page_index": 9,
            "quote_text": "Verbatim quote",
            "locator": {"type": "text_offsets", "start": 100, "end": 114},
            "confidence": 0.8,
            "source_section": "Fees",
        }
    )
    payload = original.model_dump()
    restored = EvidenceSpan.model_validate(payload)
    assert restored == original


def test_build_evidence_spans_synthesizes_from_selector_bundle():
    spans = build_evidence_spans(
        provided_spans=None,
        doc_id="doc-4",
        page_index=6,
        quote_text="Initial Franchise Fee",
        selector_bundle={
            "text_position": {"start": 200, "end": 221},
            "text_quote": {"exact": "Initial Franchise Fee", "prefix": "", "suffix": ""},
        },
        bbox=None,
        page_size=None,
        confidence=1.0,
        source_section="Item 5",
    )
    assert len(spans) == 1
    span = spans[0]
    assert span["doc_id"] == "doc-4"
    assert span["page_index"] == 6
    assert span["page_index_base"] == 1
    assert span["locator"]["type"] == "text_offsets"
    assert span["quote_text"] == "Initial Franchise Fee"


def test_build_evidence_spans_accepts_and_normalizes_provided_spans():
    spans = build_evidence_spans(
        provided_spans=[
            {
                "page_index": 0,
                "page_index_base": 0,
                "quote_text": "Provided quote",
                "locator": {"type": "text_offsets", "start": 5, "end": 19},
            }
        ],
        doc_id="doc-5",
        page_index=3,
        quote_text="Fallback quote",
        selector_bundle=None,
        bbox=None,
        page_size=None,
        confidence=0.6,
        source_section="Item 6",
    )
    assert len(spans) == 1
    span = spans[0]
    assert span["doc_id"] == "doc-5"
    assert span["page_index"] == 1
    assert span["page_index_base"] == 1
    assert span["quote_text"] == "Provided quote"
    assert span["confidence"] == 0.6
