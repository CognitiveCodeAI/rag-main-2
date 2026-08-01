"""Deterministic Phase 1 evidence-chain evaluation and release-gate check.

This harness intentionally avoids an LLM judge. Expected evidence is a locked,
human-authored node set. It measures routing accuracy, baseline/chain evidence
recall, forbidden-node leakage, determinism, and local scoring latency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.graph_models import Edge, EdgeType, Node, NodeType
from app.graph.expander import ExpandedContext
from app.qa.evidence_chain import EvidenceChainConfig, EvidenceChainEngine


HERE = Path(__file__).resolve().parent
DATASET_PATH = HERE / "questions_evidence_chain.json"
CONTRACT_PATH = HERE / "benchmark_contract.json"


class FixtureQuery:
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


class FixtureDB:
    def __init__(self, nodes: list[Node], edges: list[Edge]):
        self.nodes = nodes
        self.edges = edges

    def query(self, model):
        if model is Node:
            return FixtureQuery(self.nodes)
        if model is Edge:
            return FixtureQuery(self.edges)
        raise AssertionError(f"unexpected model: {model}")


class FixtureACL:
    def __init__(self, denied_ids: set[str]):
        self.denied_ids = denied_ids

    def filter_nodes(self, nodes, stage="expansion"):
        return [node for node in nodes if node.node_id not in self.denied_ids]


@dataclass
class CaseResult:
    case_id: str
    domain: str
    route_expected: bool
    route_actual: bool
    baseline_recall: float
    chain_recall: float
    forbidden_leaks: list[str]
    deterministic: bool
    latency_ms: float
    selected_node_ids: list[str]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    mode = contract["modes"].get("evidence_chain")
    if mode is None:
        raise RuntimeError("benchmark contract has no evidence_chain mode")
    actual_hash = _sha256(DATASET_PATH)
    if actual_hash != mode["dataset_sha256"]:
        raise RuntimeError(
            f"evidence-chain dataset hash mismatch: expected {mode['dataset_sha256']}, got {actual_hash}"
        )
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    if len(dataset["cases"]) != mode["required_question_count"]:
        raise RuntimeError("evidence-chain dataset count violates benchmark contract")
    return dataset


def _make_case_graph(case: dict[str, Any]):
    nodes = [
        Node(
            node_id=item["id"],
            doc_id="fixture-doc",
            version=1,
            node_type=NodeType.chunk,
            page_no=item["page"],
            chunk_index_in_page=index,
            text_plain=item["text"],
            meta={},
        )
        for index, item in enumerate(case["nodes"])
    ]
    edges = [
        Edge(
            id=index,
            doc_id="fixture-doc",
            version=1,
            from_node_id=item["from"],
            to_node_id=item["to"],
            edge_type=EdgeType(item["type"]),
            confidence=item.get("confidence", 1.0),
        )
        for index, item in enumerate(case["edges"], start=1)
    ]
    by_id = {node.node_id: node for node in nodes}
    seeds = [by_id[node_id] for node_id in case["seeds"]]
    expanded = ExpandedContext(
        seed_nodes=seeds,
        adjacent_nodes=[],
        referenced_nodes=[],
        explained_by_nodes=[],
        node_sources={node.node_id: "seed" for node in seeds},
    )
    return nodes, edges, expanded


def _recall(selected: set[str], expected: set[str]) -> float:
    return len(selected & expected) / len(expected) if expected else 1.0


def run_case(case: dict[str, Any]) -> CaseResult:
    nodes, edges, expanded = _make_case_graph(case)
    denied = set(case.get("denied_nodes", []))
    engine = EvidenceChainEngine(
        FixtureDB(nodes, edges),
        FixtureACL(denied),
        EvidenceChainConfig(mode="auto"),
    )

    started = time.perf_counter()
    first = engine.build(
        expanded,
        case["question"],
        case["seeds"],
        doc_id="fixture-doc",
        version=1,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    second = engine.build(
        expanded,
        case["question"],
        case["seeds"],
        doc_id="fixture-doc",
        version=1,
    )

    baseline_ids = set(case["seeds"])
    selected_ids = first.selected_node_ids if first.applied else baseline_ids
    expected = set(case["expected_evidence"])
    forbidden = set(case.get("forbidden_evidence", []))
    deterministic = first.to_audit_dict() == second.to_audit_dict()

    return CaseResult(
        case_id=case["id"],
        domain=case["domain"],
        route_expected=case["expect_route"],
        route_actual=first.route.applied,
        baseline_recall=_recall(baseline_ids, expected),
        chain_recall=_recall(selected_ids, expected),
        forbidden_leaks=sorted(selected_ids & forbidden),
        deterministic=deterministic,
        latency_ms=latency_ms,
        selected_node_ids=sorted(selected_ids),
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile)))
    return ordered[index]


def evaluate() -> dict[str, Any]:
    dataset = validate_contract()
    cases = [run_case(case) for case in dataset["cases"]]
    route_accuracy = sum(case.route_actual == case.route_expected for case in cases) / len(cases)
    baseline_recall = sum(case.baseline_recall for case in cases) / len(cases)
    chain_recall = sum(case.chain_recall for case in cases) / len(cases)
    total_leaks = sum(len(case.forbidden_leaks) for case in cases)
    deterministic_rate = sum(case.deterministic for case in cases) / len(cases)
    p95_ms = _percentile([case.latency_ms for case in cases], 0.95)

    gates = {
        "route_accuracy": route_accuracy == 1.0,
        "chain_recall_no_regression": chain_recall >= baseline_recall,
        "chain_recall_target": chain_recall == 1.0,
        "forbidden_leakage_zero": total_leaks == 0,
        "deterministic": deterministic_rate == 1.0,
        "local_p95_under_50ms": p95_ms <= 50.0,
    }
    return {
        "contract_id": "rag_eval_contract",
        "mode": "evidence_chain",
        "dataset_sha256": _sha256(DATASET_PATH),
        "case_count": len(cases),
        "metrics": {
            "route_accuracy": route_accuracy,
            "baseline_evidence_recall": baseline_recall,
            "chain_evidence_recall": chain_recall,
            "absolute_recall_improvement": chain_recall - baseline_recall,
            "forbidden_leaks": total_leaks,
            "deterministic_rate": deterministic_rate,
            "local_p95_ms": p95_ms,
        },
        "gates": gates,
        "passed": all(gates.values()),
        "cases": [asdict(case) for case in cases],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate()
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
