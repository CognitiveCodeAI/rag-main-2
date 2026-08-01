"""Unit and security tests for query-aware evidence chains."""

from __future__ import annotations

from typing import Iterable

import pytest

from app.db.graph_models import Edge, EdgeType, Node, NodeType
from app.graph.context_packer import ContextPacker
from app.graph.expander import ExpandedContext
from app.qa.evidence_chain import (
    EvidenceChainConfig,
    EvidenceChainEngine,
    MultiHopRouter,
)


def make_node(node_id: str, page: int, text: str, doc_id: str = "doc-1") -> Node:
    return Node(
        node_id=node_id,
        doc_id=doc_id,
        version=1,
        node_type=NodeType.chunk,
        page_no=page,
        chunk_index_in_page=0,
        text_plain=text,
        meta={},
    )


def make_edge(
    edge_id: int,
    left: str,
    right: str,
    edge_type: EdgeType = EdgeType.adjacent_next,
    confidence: float | None = 1.0,
    doc_id: str = "doc-1",
) -> Edge:
    return Edge(
        id=edge_id,
        doc_id=doc_id,
        version=1,
        from_node_id=left,
        to_node_id=right,
        edge_type=edge_type,
        confidence=confidence,
    )


class FakeQuery:
    def __init__(self, records: Iterable[object]):
        self.records = list(records)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, count):
        self.records = self.records[:count]
        return self

    def all(self):
        return list(self.records)


class FakeDB:
    def __init__(self, nodes: list[Node], edges: list[Edge]):
        self.nodes = nodes
        self.edges = edges
        self.query_calls: list[type] = []

    def query(self, model):
        self.query_calls.append(model)
        if model is Node:
            return FakeQuery(self.nodes)
        if model is Edge:
            return FakeQuery(self.edges)
        raise AssertionError(f"unexpected query model: {model}")


class RecordingACL:
    def __init__(self, denied_node_ids: set[str] | None = None):
        self.denied_node_ids = denied_node_ids or set()
        self.stages: list[str] = []

    def filter_nodes(self, nodes, stage="expansion"):
        self.stages.append(stage)
        return [node for node in nodes if node.node_id not in self.denied_node_ids]


def make_context(seed: Node, adjacent: Node | None = None) -> ExpandedContext:
    adjacent_nodes = [adjacent] if adjacent is not None else []
    sources = {seed.node_id: "seed"}
    if adjacent is not None:
        sources[adjacent.node_id] = "adjacent"
    return ExpandedContext(
        seed_nodes=[seed],
        adjacent_nodes=adjacent_nodes,
        referenced_nodes=[],
        explained_by_nodes=[],
        node_sources=sources,
    )


class TestMultiHopRouter:
    def test_routes_explicit_legal_multi_hop_question(self):
        decision = MultiHopRouter.decide(
            "Compare the amendment's effective date with the governing law and explain how it affects termination.",
            mode="auto",
        )

        assert decision.applied is True
        assert decision.score >= 0.55
        assert "comparison" in decision.reasons
        assert "temporal_or_versioned" in decision.reasons

    def test_does_not_route_simple_lookup(self):
        decision = MultiHopRouter.decide(
            "What is the termination fee?",
            mode="auto",
        )

        assert decision.applied is False
        assert decision.reasons == ("below_threshold",)

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [("off", False), ("on", True)],
    )
    def test_explicit_modes_are_authoritative(self, mode, expected):
        assert MultiHopRouter.decide("simple question", mode=mode).applied is expected


class TestEvidenceChainConfig:
    def test_rejects_unbounded_or_invalid_configuration(self):
        with pytest.raises(ValueError):
            EvidenceChainConfig(max_hops=0)
        with pytest.raises(ValueError):
            EvidenceChainConfig(max_nodes=2, max_selected_nodes=3)
        with pytest.raises(ValueError):
            EvidenceChainConfig(restart_probability=0.0)


class TestEvidenceChainEngine:
    def _build_fixture(self, denied: set[str] | None = None):
        seed = make_node("seed", 1, "The patient has renal impairment.")
        adjacent = make_node("adjacent", 2, "The guideline discusses Drug A.")
        bridge = make_node("bridge", 3, "Drug A is cleared through the kidneys.")
        target = make_node(
            "target",
            4,
            "Renal impairment is a contraindication for Drug A under the current guideline.",
        )
        nodes = [seed, adjacent, bridge, target]
        edges = [
            make_edge(1, "seed", "adjacent"),
            make_edge(2, "adjacent", "bridge", confidence=0.8),
            make_edge(3, "bridge", "target", EdgeType.references, confidence=0.9),
            # Cycle must not make path reconstruction or propagation unstable.
            make_edge(4, "target", "adjacent", EdgeType.explained_by, confidence=0.7),
        ]
        acl = RecordingACL(denied)
        engine = EvidenceChainEngine(
            FakeDB(nodes, edges),
            acl,
            EvidenceChainConfig(
                mode="on",
                max_hops=3,
                max_nodes=10,
                max_selected_nodes=4,
                max_chains=4,
                propagation_steps=25,
            ),
        )
        return engine, acl, seed, adjacent, target

    def test_expands_scores_and_assembles_auditable_paths(self):
        engine, acl, seed, adjacent, target = self._build_fixture()

        result = engine.build(
            make_context(seed, adjacent),
            question="How does renal impairment affect Drug A under the current guideline?",
            seed_scores={"seed": 0.9},
            doc_id="doc-1",
            version=1,
        )

        assert result.applied is True
        assert result.candidate_count == 4
        assert result.edge_count == 4
        assert result.iterations <= 25
        assert result.selected_node_ids == {"seed", "adjacent", "bridge", "target"}
        assert {node.node_id for node in result.additional_nodes} == {"bridge", "target"}
        assert any(path.node_ids[0] == "seed" and path.node_ids[-1] == "target" for path in result.paths)
        assert all(0.0 <= score.final_score <= 1.0 for score in result.selected_scores)
        assert "evidence_chain_hop_1" in acl.stages

        audit = result.to_audit_dict()
        assert audit["scoring_version"] == "document-chain-v1"
        assert "text" not in str(audit).lower()
        assert audit["ordered_node_ids"] == result.ordered_node_ids

    def test_denied_node_cannot_affect_selected_graph_or_audit(self):
        engine, acl, seed, adjacent, _ = self._build_fixture(denied={"target"})

        result = engine.build(
            make_context(seed, adjacent),
            question="How does renal impairment affect Drug A under the current guideline?",
            seed_scores={"seed": 0.9},
            doc_id="doc-1",
            version=1,
        )

        audit = result.to_audit_dict()
        assert result.candidate_count == 3
        assert "target" not in result.selected_node_ids
        assert "target" not in result.ordered_node_ids
        assert "target" not in str(audit)
        assert all(
            edge.from_node_id != "target" and edge.to_node_id != "target"
            for path in result.paths
            for edge in path.edges
        )
        assert any(stage.startswith("evidence_chain_hop_") for stage in acl.stages)

    def test_invalid_edge_confidence_is_clamped_and_deterministic(self):
        seed = make_node("seed", 1, "Source clause")
        target = make_node("target", 2, "Amended clause")
        edge = make_edge(1, "seed", "target", confidence=float("nan"))
        engine = EvidenceChainEngine(
            FakeDB([seed, target], [edge]),
            RecordingACL(),
            EvidenceChainConfig(mode="on", max_selected_nodes=2),
        )

        first = engine.build(
            make_context(seed), "Compare the source and amended clause", {"seed": 1.0}
        )
        second = engine.build(
            make_context(seed), "Compare the source and amended clause", {"seed": 1.0}
        )

        assert first.ordered_node_ids == second.ordered_node_ids
        assert first.to_audit_dict() == second.to_audit_dict()
        assert first.paths[0].edges[0].weight == pytest.approx(0.325)

    def test_empty_authorized_candidate_set_falls_back(self):
        seed = make_node("seed", 1, "Source")
        engine = EvidenceChainEngine(
            FakeDB([seed], []),
            RecordingACL({"seed"}),
            EvidenceChainConfig(mode="on"),
        )

        result = engine.build(make_context(seed), "Compare the sources", {"seed": 1.0})

        assert result.applied is False
        assert result.fallback_used is True
        assert result.fallback_reason == "no_authorized_candidates"

    def test_doc_scope_filters_initial_and_neighbor_nodes(self):
        seed = make_node("seed", 1, "Original agreement", doc_id="doc-1")
        foreign = make_node("foreign", 2, "Restricted other document", doc_id="doc-2")
        cross_doc_edge = make_edge(1, "seed", "foreign", doc_id="doc-2")
        engine = EvidenceChainEngine(
            FakeDB([seed, foreign], [cross_doc_edge]),
            RecordingACL(),
            EvidenceChainConfig(mode="on", max_selected_nodes=2),
        )
        expanded = make_context(seed)
        expanded.chain_nodes = [foreign]

        result = engine.build(
            expanded,
            "Compare the original and amended agreement",
            {"seed": 1.0},
            doc_id="doc-1",
            version=1,
        )

        assert result.candidate_count == 1
        assert result.selected_node_ids == {"seed"}
        assert "foreign" not in str(result.to_audit_dict())

    def test_all_seed_nodes_keep_a_nonzero_restart_prior(self):
        normalized = EvidenceChainEngine._normalize_seed_scores(
            {"strong", "weak"},
            {"strong": 0.9, "weak": 0.1},
        )

        assert normalized["strong"] == 1.0
        assert normalized["weak"] >= 0.10

    def test_high_degree_graph_respects_hard_candidate_cap(self):
        seed = make_node("seed", 1, "Compare the policy changes")
        neighbors = [
            make_node(f"neighbor-{index:03d}", index + 2, "Policy change detail")
            for index in range(100)
        ]
        edges = [
            make_edge(index + 1, "seed", node.node_id, confidence=1.0)
            for index, node in enumerate(neighbors)
        ]
        engine = EvidenceChainEngine(
            FakeDB([seed] + neighbors, edges),
            RecordingACL(),
            EvidenceChainConfig(
                mode="on",
                max_nodes=10,
                max_selected_nodes=8,
            ),
        )

        result = engine.build(
            make_context(seed),
            "Compare the policy changes",
            {"seed": 1.0},
        )

        assert result.candidate_count == 10
        assert len(result.selected_node_ids) <= 8

    def test_database_query_count_is_bounded_by_two_queries_per_hop(self):
        engine, _, seed, adjacent, _ = self._build_fixture()

        result = engine.build(
            make_context(seed, adjacent),
            "How does renal impairment affect Drug A under the current guideline?",
            {"seed": 1.0},
            doc_id="doc-1",
            version=1,
        )

        assert result.applied is True
        assert len(engine.db.query_calls) <= 2 * engine.config.max_hops
        assert engine.db.query_calls.count(Edge) <= engine.config.max_hops
        assert engine.db.query_calls.count(Node) <= engine.config.max_hops

    def test_path_reconstruction_does_not_exceed_hop_budget(self):
        engine = EvidenceChainEngine(
            FakeDB([], []),
            RecordingACL(),
            EvidenceChainConfig(mode="on", max_hops=2),
        )
        adjacency = {
            "seed": {"a": 1.0},
            "a": {"seed": 1.0, "b": 1.0},
            "b": {"a": 1.0, "target": 1.0},
            "target": {"b": 1.0},
        }

        assert engine._shortest_path_to_seed(
            "target",
            {"seed"},
            adjacency,
            {node_id: 1.0 for node_id in adjacency},
            allowed_node_ids=set(adjacency),
        ) == []


def test_chain_aware_packer_preserves_explicit_order_and_canonical_citations():
    seed = make_node("seed", 1, "Seed evidence")
    target = make_node("target", 4, "Target evidence")
    expanded = make_context(seed)
    expanded.chain_nodes = [target]
    expanded.node_sources["target"] = "chain"

    packed = ContextPacker(max_tokens=100).pack(
        expanded,
        node_order=["target", "seed"],
        allowed_node_ids={"target", "seed"},
    )

    assert [block.citation.node_id for block in packed.blocks] == ["target", "seed"]
    assert packed.to_text().startswith(
        "[target:4] node_id=target page_no=4 source=chain\nTarget evidence"
    )
    assert (
        "[seed:1] node_id=seed page_no=1 source=seed\nSeed evidence"
        in packed.to_text()
    )
