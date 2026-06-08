"""E3: bounded-concurrency figure OCR + per-doc spend cap.

Covers the pure node builder and the create_figure_nodes orchestration (with
fitz / PageExtractor / OCR client mocked, no real PDF or network).
"""

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.graph.figure_detector import FigureData
from app.graph.nodes import _build_figure_node, create_figure_nodes


def _fig(page_no, label, ftype="figure"):
    return FigureData(
        page_no=page_no,
        label=label,
        caption=f"cap-{label}",
        bbox={"x0": 0, "y0": 0, "x1": 10, "y1": 10},
        figure_type=ftype,
    )


def test_build_figure_node_composition():
    fig = _fig(1, "Figure 1")
    node = _build_figure_node(fig, 0, "doc1", 1, ocr_text="OCRTEXT")
    assert "Figure 1" in node.text_md
    assert "cap-Figure 1" in node.text_md
    assert "OCRTEXT" in node.text_md
    assert node.meta["has_ocr"] is True

    no_ocr = _build_figure_node(fig, 0, "doc1", 1, ocr_text="")
    assert no_ocr.meta["has_ocr"] is False
    assert "OCRTEXT" not in no_ocr.text_md


def _mock_env(monkeypatch, ocr, *, max_calls=60, max_concurrency=4):
    monkeypatch.setattr(
        "app.graph.nodes.get_settings",
        lambda: Settings(ocr_max_calls_per_doc=max_calls, ocr_max_concurrency=max_concurrency),
    )
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 10
    mock_doc.__getitem__.return_value = MagicMock()  # a page
    monkeypatch.setattr("app.graph.nodes.fitz.open", lambda *a, **k: mock_doc)
    pe = MagicMock()
    pe.render_region_image.return_value = b"img-bytes"
    monkeypatch.setattr("app.graph.nodes.PageExtractor", lambda: pe)


def test_order_preserved_and_each_figure_ocrd(monkeypatch):
    ocr = MagicMock()
    ocr.ocr_region.side_effect = lambda image_bytes, doc_id, page_no, region_type: f"ocr-{page_no}-{region_type}"
    _mock_env(monkeypatch, ocr)

    figs = [_fig(1, "Figure 1"), _fig(1, "Figure 2"), _fig(2, "Table 1", "table")]
    out = create_figure_nodes(figs, b"%PDF", "doc1", 1, ocr_client=ocr, skip_ocr=False)

    assert [n.label for n in out] == ["Figure 1", "Figure 2", "Table 1"]  # document order
    assert ocr.ocr_region.call_count == 3
    assert "ocr-2-table" in out[2].text_md


def test_spend_cap_limits_ocr_deterministically(monkeypatch):
    ocr = MagicMock()
    ocr.ocr_region.side_effect = lambda **k: "OCR"
    _mock_env(monkeypatch, ocr, max_calls=1)

    figs = [_fig(1, "Figure 1"), _fig(1, "Figure 2"), _fig(1, "Figure 3")]
    out = create_figure_nodes(figs, b"%PDF", "doc1", 1, ocr_client=ocr, skip_ocr=False)

    assert ocr.ocr_region.call_count == 1            # only the first figure
    assert len(out) == 3                              # all nodes still built
    assert out[0].meta["has_ocr"] is True
    assert out[1].meta["has_ocr"] is False           # over the cap -> empty OCR
    assert out[2].meta["has_ocr"] is False


def test_single_ocr_failure_is_non_fatal(monkeypatch):
    calls = {"n": 0}

    def flaky(**k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("ocr boom")
        return "OCR"

    ocr = MagicMock()
    ocr.ocr_region.side_effect = flaky
    _mock_env(monkeypatch, ocr, max_concurrency=1)  # deterministic order for this test

    figs = [_fig(1, "Figure 1"), _fig(1, "Figure 2"), _fig(1, "Figure 3")]
    out = create_figure_nodes(figs, b"%PDF", "doc1", 1, ocr_client=ocr, skip_ocr=False)

    assert len(out) == 3                              # failure didn't drop the doc
    assert out[1].meta["has_ocr"] is False            # the failed one has empty OCR
    assert out[0].meta["has_ocr"] is True


def test_skip_ocr_builds_nodes_without_calls(monkeypatch):
    ocr = MagicMock()
    _mock_env(monkeypatch, ocr)
    figs = [_fig(1, "Figure 1"), _fig(2, "Table 1", "table")]
    out = create_figure_nodes(figs, b"%PDF", "doc1", 1, ocr_client=ocr, skip_ocr=True)
    assert len(out) == 2
    assert ocr.ocr_region.call_count == 0
