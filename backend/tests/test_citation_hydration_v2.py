"""QA citation hydration tests for the fail-closed Evidence V2 contract."""

from types import SimpleNamespace
from unittest.mock import patch

from app.db.graph_models import DocumentGraph, Node
from app.llm.openai_client import Citation
from app.qa.runner import QARunner


QUOTE = "The patient gave informed consent."


def _source_spans():
    words = QUOTE.split()
    spans = []
    x0 = 0.1
    for order, word in enumerate(words):
        x1 = x0 + 0.05
        spans.append(
            {
                "order": order,
                "text": word,
                "block_no": 0,
                "line_no": 0,
                "word_no": order,
                "normalized_bbox": {
                    "x0": x0,
                    "y0": 0.2,
                    "x1": x1,
                    "y1": 0.23,
                },
                "coordinate_system": "pdf_points_top_left",
                "verifiable": True,
            }
        )
        x0 = x1 + 0.01
    return spans


class FakeQuery:
    def __init__(self, model, node, graph):
        self.model = model
        self.node = node
        self.graph = graph

    def filter(self, *_args):
        return self

    def all(self):
        return [self.node] if self.model is Node and self.node is not None else []

    def first(self):
        return self.graph if self.model is DocumentGraph else None


class FakeDB:
    def __init__(self, node=None, graph=None):
        self.node = node
        self.graph = graph
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        return FakeQuery(model, self.node, self.graph)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeStorage:
    def __init__(self, source_map):
        self.source_map = source_map

    def canonical_view_exists(self, *_args):
        return True

    def source_map_exists(self, *_args):
        return True

    def selectors_exist(self, *_args):
        return True

    def get_source_map(self, *_args):
        return self.source_map


def test_hydration_returns_a_valid_verified_record_and_snapshot():
    selector = {
        "text_position": {"start": 0, "end": len(QUOTE)},
        "text_quote": {"exact": QUOTE, "prefix": "", "suffix": ""},
        "source_state": {"content_hash": "sha256:sourcehash"},
    }
    node = SimpleNamespace(
        node_id="clinical-node",
        doc_id="clinical-doc",
        version=2,
        page_no=1,
        label=None,
        bbox=None,
        text_plain=QUOTE,
        meta={
            "selector_bundle": selector,
            "source_spans": _source_spans(),
            "page_size": {"width": 612, "height": 792},
        },
    )
    graph = SimpleNamespace(
        doc_id="clinical-doc",
        version=2,
        content_hash="sourcehash",
        source_uri="upload://clinical.pdf",
    )
    source_map = {
        "doc_id": "clinical-doc",
        "version": 2,
        "content_hash": "sha256:sourcehash",
        "canonical_text": QUOTE,
        "nodes": [
            {
                "node_id": "clinical-node",
                "start": 0,
                "end": len(QUOTE),
                "page_no": 1,
                "page_rotation": 0,
                "page_size": {"width": 612, "height": 792},
                "source_spans": _source_spans(),
            }
        ],
    }
    db = FakeDB(node=node, graph=graph)
    runner = object.__new__(QARunner)
    runner.db = db

    with (
        patch(
            "app.qa.runner.get_settings",
            return_value=SimpleNamespace(enable_cross_format_highlighting=True),
        ),
        patch("app.qa.runner.get_storage_client", return_value=FakeStorage(source_map)),
        patch("app.qa.runner.find_legacy_for_graph", return_value=None),
    ):
        hydrated = runner._hydrate_citations(
            [
                Citation(
                    citation_id="C1",
                    node_id="clinical-node",
                    page_no=1,
                    exact_quote=QUOTE,
                )
            ],
            doc_id="clinical-doc",
            version=2,
            context_node_ids=["clinical-node"],
            answer_text="Consent was given [C1].",
            request_id="request-1",
        )

    assert len(hydrated) == 1
    record = hydrated[0]["evidence_records"][0]
    assert record["status"] == "verified"
    assert record["locator"]["type"] == "rects"
    assert record["document_version"] == 2
    assert db.added[0].evidence_record == record
    assert db.commits == 1
    assert db.rollbacks == 0


def test_hydration_never_substitutes_a_same_page_context_node():
    db = FakeDB()
    runner = object.__new__(QARunner)
    runner.db = db

    with patch(
        "app.qa.runner.get_settings",
        return_value=SimpleNamespace(enable_cross_format_highlighting=False),
    ):
        hydrated = runner._hydrate_citations(
            [
                Citation(
                    citation_id="C1",
                    node_id="invented-node",
                    page_no=14,
                    exact_quote="Invented quote.",
                )
            ],
            doc_id="legal-doc",
            version=1,
            context_node_ids=["real-node-on-page-14"],
        )

    assert hydrated == []
