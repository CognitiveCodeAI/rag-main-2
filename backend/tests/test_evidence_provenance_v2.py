"""Tests for word-level ingestion and chunk provenance."""

from types import SimpleNamespace

import fitz
import pytest

from app.graph.chunker import PageBoundedChunker
from app.graph.ids import compute_content_hash
from app.graph.nodes import create_chunk_nodes
from app.graph.page_extractor import PageExtractor, TextSpan
from app.services.highlighting import (
    backfill_pdf_source_provenance,
    build_selector_artifacts_for_nodes,
    verify_evidence_span,
)


def _word(text: str, order: int, x0: float) -> TextSpan:
    return TextSpan(
        text=text,
        bbox=(x0, 10.0, x0 + 20.0, 20.0),
        span_id=f"p1:w{order}",
        order=order,
        block_no=0,
        line_no=0,
        word_no=order,
        normalized_bbox={
            "x0": x0 / 200.0,
            "y0": 0.1,
            "x1": (x0 + 20.0) / 200.0,
            "y1": 0.2,
        },
    )


def test_chunk_provenance_resolves_one_exact_source_sequence():
    page = SimpleNamespace(
        page_no=1,
        width=200.0,
        height=100.0,
        text_spans=[
            _word("The", 0, 10),
            _word("fee", 1, 35),
            _word("is", 2, 60),
            _word("$45,000.", 3, 85),
        ],
    )
    chunker = PageBoundedChunker(target_tokens=100)
    spans, status = chunker._compute_chunk_source_spans("The fee is $45,000.", page)

    assert status == "exact_source_words"
    assert [span["span_id"] for span in spans] == [
        "p1:w0",
        "p1:w1",
        "p1:w2",
        "p1:w3",
    ]


def test_chunk_provenance_rejects_ambiguous_repeated_text():
    page = SimpleNamespace(
        page_no=1,
        width=200.0,
        height=100.0,
        text_spans=[
            _word("Fee", 0, 10),
            _word("due.", 1, 35),
            _word("Fee", 2, 70),
            _word("due.", 3, 95),
        ],
    )
    chunker = PageBoundedChunker(target_tokens=100)
    spans, status = chunker._compute_chunk_source_spans("Fee due.", page)

    assert spans == []
    assert status == "ambiguous_chunk_in_source_words"


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdf_word_extraction_normalizes_rotated_page_coordinates(rotation):
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((30, 50), "Verified evidence")
    page.set_rotation(rotation)
    pdf_bytes = doc.tobytes()
    doc.close()

    reopened = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        rotated_page = reopened[0]
        spans = PageExtractor(skip_ocr=True)._extract_text_spans(rotated_page)
    finally:
        reopened.close()

    assert [span.text for span in spans] == ["Verified", "evidence"]
    assert all(span.coordinate_system == "pdf_points_top_left" for span in spans)
    assert all(span.verifiable for span in spans)
    for span in spans:
        rect = span.normalized_bbox
        assert rect is not None
        assert 0 <= rect["x0"] < rect["x1"] <= 1
        assert 0 <= rect["y0"] < rect["y1"] <= 1


def test_real_pdf_ingestion_to_verified_rectangles():
    """Exercise PDF extraction → chunk provenance → source map → verification."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(
        (72, 100),
        "The initial franchise fee is $45,000.",
        fontsize=12,
    )
    page.insert_text(
        (72, 130),
        "Payment is due when the agreement is signed.",
        fontsize=12,
    )
    pdf_bytes = doc.tobytes()
    doc.close()

    extraction = PageExtractor(skip_ocr=True).extract_pages(
        pdf_bytes,
        doc_id="fixture-doc",
    )
    chunks = PageBoundedChunker(target_tokens=200).chunk_pages(
        pages=[(p.page_no, p.text_plain) for p in extraction.pages],
        doc_id="fixture-doc",
        version=1,
        page_data_list=extraction.pages,
    )
    nodes = create_chunk_nodes(chunks, doc_id="fixture-doc", version=1)
    graph_doc = SimpleNamespace(
        doc_id="fixture-doc",
        version=1,
        content_hash="fixturehash",
        source_uri="upload://fixture.pdf",
    )
    artifacts = build_selector_artifacts_for_nodes(
        graph_doc,
        nodes,
        source_type="pdf",
        mime_type="application/pdf",
    )

    result = verify_evidence_span(
        doc_id="fixture-doc",
        node_id=nodes[0].node_id,
        page_index=1,
        quote_text="The initial franchise fee is $45,000.",
        locator=None,
        source_hash="sha256:fixturehash",
        source_map=artifacts["source_map"],
    )

    assert chunks[0].meta["source_span_resolution"] == "exact_source_words"
    assert result["status"] == "FOUND"
    assert result["grade"] == "verified"
    assert result["matched_locator"]["rects"]


def test_legal_and_clinical_evidence_remains_bound_to_its_original_page():
    """Curated two-page fixture for the high-risk review use cases."""
    doc = fitz.open()
    legal_page = doc.new_page(width=612, height=792)
    legal_page.insert_text(
        (72, 100),
        "The tenant may terminate this agreement with thirty days written notice.",
        fontsize=11,
    )
    clinical_page = doc.new_page(width=612, height=792)
    clinical_page.insert_text(
        (72, 100),
        "The patient gave informed consent before the procedure began.",
        fontsize=11,
    )
    pdf_bytes = doc.tobytes()
    doc.close()

    extraction = PageExtractor(skip_ocr=True).extract_pages(
        pdf_bytes,
        doc_id="risk-review-fixture",
    )
    chunks = PageBoundedChunker(target_tokens=200).chunk_pages(
        pages=[(p.page_no, p.text_plain) for p in extraction.pages],
        doc_id="risk-review-fixture",
        version=3,
        page_data_list=extraction.pages,
    )
    nodes = create_chunk_nodes(chunks, doc_id="risk-review-fixture", version=3)
    graph_doc = SimpleNamespace(
        doc_id="risk-review-fixture",
        version=3,
        content_hash=compute_content_hash(pdf_bytes),
        source_uri="upload://risk-review-fixture.pdf",
    )
    source_map = build_selector_artifacts_for_nodes(
        graph_doc,
        nodes,
        source_type="pdf",
        mime_type="application/pdf",
    )["source_map"]
    clinical_node = next(node for node in nodes if node.page_no == 2)
    quote = "The patient gave informed consent before the procedure began."

    verified = verify_evidence_span(
        doc_id=graph_doc.doc_id,
        document_version=3,
        node_id=clinical_node.node_id,
        page_index=2,
        quote_text=quote,
        locator=None,
        source_hash=graph_doc.content_hash,
        source_map=source_map,
    )
    wrong_page = verify_evidence_span(
        doc_id=graph_doc.doc_id,
        document_version=3,
        node_id=clinical_node.node_id,
        page_index=1,
        quote_text=quote,
        locator=None,
        source_hash=graph_doc.content_hash,
        source_map=source_map,
    )

    assert verified["status"] == "FOUND"
    assert verified["grade"] == "verified"
    assert verified["page_index"] == 2
    assert wrong_page["status"] == "NOT_FOUND"
    assert wrong_page["reason"] == "evidence_not_found_on_cited_page"


def test_legacy_native_pdf_can_be_backfilled_without_changing_node_identity():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "The consent form must be signed.", fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()

    graph_doc = SimpleNamespace(
        doc_id="legacy-doc",
        version=1,
        content_hash=compute_content_hash(pdf_bytes),
        source_uri="upload://legacy.pdf",
    )
    node = SimpleNamespace(
        node_id="stable-node-id",
        doc_id="legacy-doc",
        version=1,
        node_type=SimpleNamespace(value="chunk"),
        page_no=1,
        chunk_index_in_page=0,
        text_plain="The consent form must be signed.",
        text_md=None,
        caption_md=None,
        label=None,
        bbox=None,
        meta={},
    )

    class FakeQuery:
        def filter(self, *_args):
            return self

        def all(self):
            return [node]

    class FakeDB:
        flushed = False

        def query(self, _model):
            return FakeQuery()

        def flush(self):
            self.flushed = True

    class FakeStorage:
        canonical = None
        source_map = None
        selectors = None

        def put_canonical_view(self, _doc_id, _version, value):
            self.canonical = value

        def put_source_map(self, _doc_id, _version, value):
            self.source_map = value

        def put_selectors(self, _doc_id, _version, value):
            self.selectors = value

    fake_db = FakeDB()
    fake_storage = FakeStorage()
    result = backfill_pdf_source_provenance(
        fake_db,
        graph_doc,
        pdf_bytes,
        storage=fake_storage,
    )

    assert node.node_id == "stable-node-id"
    assert node.meta["source_span_resolution"] == "exact_source_words"
    assert result["exact_nodes"] == 1
    assert fake_db.flushed is True
    assert fake_storage.source_map["nodes"][0]["source_spans"]
