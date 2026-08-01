"""Paired answer-level A/B evaluation for query-aware evidence chains.

The locked retrieval fixture and separately locked, human-authored answer
expectations are evaluated without an LLM judge.  The deterministic provider
is suitable for CI and verifies the whole context/citation/highlight contract.
The OpenAI provider runs the same paired cases through the configured answer
model for a representative model-backed release report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.graph.context_packer import ContextPacker
from app.llm.openai_client import AnswerResult, Citation, OpenAIClient
from app.qa.evidence_chain import EvidenceChainConfig, EvidenceChainEngine
from app.services.highlighting import verify_evidence_span
from tests.eval.run_evidence_chain_eval import (
    CONTRACT_PATH,
    DATASET_PATH,
    FixtureACL,
    FixtureDB,
    _make_case_graph,
)


HERE = Path(__file__).resolve().parent
EXPECTATIONS_PATH = HERE / "evidence_chain_ab_expectations.json"
SOURCE_HASH = "sha256:evidence-chain-ab-fixture"


class AnswerProvider(Protocol):
    name: str
    model: str

    def generate(
        self,
        *,
        context: str,
        question: str,
        nodes: list[Any],
        expectation: dict[str, Any],
    ) -> AnswerResult: ...


class FixtureAnswerProvider:
    """Stable generator that exercises answer/citation plumbing in CI."""

    name = "fixture"
    model = "deterministic-grounded-fixture-v1"

    def generate(
        self,
        *,
        context: str,
        question: str,
        nodes: list[Any],
        expectation: dict[str, Any],
    ) -> AnswerResult:
        del context, question
        started = time.perf_counter()
        citations: list[Citation] = []
        answer_parts: list[str] = []

        # A fixture with no expected support represents a deliberately
        # unsupported question and must abstain rather than cite irrelevant text.
        if (
            expectation["expected_citation_nodes"]
            and expectation.get("citation_policy") != "optional"
        ):
            for index, node in enumerate(nodes, start=1):
                citation_id = f"C{index}"
                text = node.text_plain or node.text_md or ""
                citations.append(
                    Citation(
                        citation_id=citation_id,
                        node_id=node.node_id,
                        page_no=node.page_no,
                        exact_quote=text,
                    )
                )
                answer_parts.append(f"{text} [{citation_id}]")

        if expectation["required_limitation_groups"]:
            answer_parts.append(
                "I cannot find sufficient information in the provided context "
                "to determine any additional conclusion."
            )

        generation_ms = max((time.perf_counter() - started) * 1000, 25.0)
        return AnswerResult(
            answer=" ".join(answer_parts),
            citations=citations,
            model_id=self.model,
            generation_time_ms=generation_ms,
        )


class OpenAIAnswerProvider:
    name = "openai"

    def __init__(self, model: str):
        self.client = OpenAIClient(model=model)
        self.model = model

    def generate(
        self,
        *,
        context: str,
        question: str,
        nodes: list[Any],
        expectation: dict[str, Any],
    ) -> AnswerResult:
        del nodes, expectation
        return self.client.generate_answer(
            context=context,
            question=question,
            max_tokens=700,
            reasoning_effort="none",
            verbosity="low",
            timeout_ms=45000,
        )


@dataclass
class VariantResult:
    answer: str
    answer_correct: bool
    facts_found: int
    facts_required: int
    limitations_found: int
    limitations_required: int
    forbidden_phrases_found: list[str]
    citation_count: int
    citation_precision: float
    expected_citation_recall: float
    inline_citation_integrity: bool
    verified_highlight_rate: float
    wrong_locator_acceptances: int
    unsupported_answer_safe: bool
    unauthorized_node_leaks: list[str]
    generation_ms: float
    request_ms: float
    selected_node_ids: list[str]


@dataclass
class PairedCaseResult:
    case_id: str
    domain: str
    route_expected: bool
    route_actual: bool
    chain_applied: bool
    fallback_used: bool
    chain_layer_ms: float
    baseline: VariantResult
    chain: VariantResult


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_locked_inputs() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    mode = contract["modes"].get("evidence_chain_ab")
    if mode is None:
        raise RuntimeError("benchmark contract has no evidence_chain_ab mode")
    hashes = {
        "dataset": (_sha256(DATASET_PATH), mode["dataset_sha256"]),
        "expectations": (_sha256(EXPECTATIONS_PATH), mode["expectations_sha256"]),
    }
    for label, (actual, expected) in hashes.items():
        if actual != expected:
            raise RuntimeError(
                f"evidence-chain A/B {label} hash mismatch: expected {expected}, got {actual}"
            )

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    expectations = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    required = mode["required_question_count"]
    if len(dataset["cases"]) != required or len(expectations["cases"]) != required:
        raise RuntimeError("evidence-chain A/B inputs violate the required case count")

    dataset_ids = [case["id"] for case in dataset["cases"]]
    expectation_ids = [case["id"] for case in expectations["cases"]]
    if len(set(dataset_ids)) != required or len(set(expectation_ids)) != required:
        raise RuntimeError("evidence-chain A/B inputs contain duplicate case IDs")
    if set(dataset_ids) != set(expectation_ids):
        raise RuntimeError("evidence-chain A/B question and expectation IDs differ")
    return dataset, {case["id"]: case for case in expectations["cases"]}


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").casefold()))


def _group_found(answer: str, alternatives: Iterable[str]) -> bool:
    normalized_answer = _normalized(answer)
    return any(_normalized(alternative) in normalized_answer for alternative in alternatives)


def _source_map(nodes: list[Any]) -> dict[str, Any]:
    canonical_parts: list[str] = []
    mapped_nodes: list[dict[str, Any]] = []
    cursor = 0
    for node in nodes:
        if canonical_parts:
            canonical_parts.append("\n\n")
            cursor += 2
        text = node.text_plain or node.text_md or ""
        start = cursor
        canonical_parts.append(text)
        cursor += len(text)
        words = text.split()
        width = 0.90 / max(1, len(words))
        source_spans = []
        for index, word in enumerate(words):
            x0 = 0.05 + index * width
            source_spans.append(
                {
                    "span_id": f"{node.node_id}:w{index}",
                    "order": index,
                    "text": word,
                    "block_no": 0,
                    "line_no": 0,
                    "word_no": index,
                    "normalized_bbox": {
                        "x0": x0,
                        "y0": 0.20,
                        "x1": min(0.999, x0 + width * 0.82),
                        "y1": 0.23,
                    },
                    "coordinate_system": "pdf_points_top_left",
                    "extraction_source": "synthetic_fixture",
                    "verifiable": True,
                }
            )
        mapped_nodes.append(
            {
                "node_id": node.node_id,
                "start": start,
                "end": cursor,
                "page_no": node.page_no,
                "page_rotation": 0,
                "page_size": {"width": 612, "height": 792},
                "source_spans": source_spans,
            }
        )
    return {
        "doc_id": "fixture-doc",
        "version": 1,
        "content_hash": SOURCE_HASH,
        "canonical_text": "".join(canonical_parts),
        "nodes": mapped_nodes,
    }


def _packed_context(expanded: Any, selected_ids: list[str]) -> tuple[str, list[Any]]:
    selected_set = set(selected_ids)
    nodes_by_id = {node.node_id: node for node in expanded.all_nodes}
    selected_nodes = [nodes_by_id[node_id] for node_id in selected_ids if node_id in nodes_by_id]
    packed = ContextPacker(max_tokens=2000).pack(
        expanded,
        node_order=selected_ids,
        allowed_node_ids=selected_set,
    )
    return packed.to_text(), selected_nodes


def _evaluate_variant(
    *,
    answer_result: AnswerResult,
    selected_nodes: list[Any],
    expectation: dict[str, Any],
    forbidden_node_ids: set[str],
    request_ms: float,
) -> VariantResult:
    nodes_by_id = {node.node_id: node for node in selected_nodes}
    all_map = _source_map(selected_nodes)
    answer = answer_result.answer or ""

    required_facts = expectation["required_fact_groups"]
    required_limitations = expectation["required_limitation_groups"]
    facts_found = sum(_group_found(answer, group) for group in required_facts)
    limitations_found = sum(_group_found(answer, group) for group in required_limitations)
    forbidden_found = [
        phrase for phrase in expectation["forbidden_phrases"] if _group_found(answer, [phrase])
    ]

    valid_citations = 0
    verified_highlights = 0
    wrong_locator_acceptances = 0
    cited_node_ids: set[str] = set()
    structured_ids: set[str] = set()
    for citation in answer_result.citations:
        node = nodes_by_id.get(citation.node_id)
        quote = citation.exact_quote or citation.text_snippet or ""
        if citation.citation_id:
            structured_ids.add(citation.citation_id)
        cited_node_ids.add(citation.node_id)
        valid = bool(
            node
            and citation.page_no == node.page_no
            and quote
            and _normalized(quote) in _normalized(node.text_plain or node.text_md or "")
        )
        if valid:
            valid_citations += 1
            verified = verify_evidence_span(
                doc_id="fixture-doc",
                document_version=1,
                node_id=citation.node_id,
                page_index=int(citation.page_no),
                quote_text=quote,
                locator=None,
                source_hash=SOURCE_HASH,
                source_map=all_map,
            )
            if verified["status"] == "FOUND" and verified.get("grade") == "verified":
                verified_highlights += 1

            negative_controls = (
                {"doc_id": "wrong-document", "document_version": 1, "page_index": int(citation.page_no)},
                {"doc_id": "fixture-doc", "document_version": 999, "page_index": int(citation.page_no)},
                {"doc_id": "fixture-doc", "document_version": 1, "page_index": int(citation.page_no) + 1000},
            )
            for control in negative_controls:
                negative = verify_evidence_span(
                    doc_id=control["doc_id"],
                    document_version=control["document_version"],
                    node_id=citation.node_id,
                    page_index=control["page_index"],
                    quote_text=quote,
                    locator=None,
                    source_hash=SOURCE_HASH,
                    source_map=all_map,
                )
                wrong_locator_acceptances += int(negative["status"] == "FOUND")

    citation_count = len(answer_result.citations)
    inline_ids = set(re.findall(r"\[(C[1-9][0-9]*)\]", answer))
    inline_integrity = inline_ids == structured_ids and len(structured_ids) == citation_count
    expected_citations = set(expectation["expected_citation_nodes"])
    citation_policy = expectation.get(
        "citation_policy",
        "required" if expected_citations else "forbidden",
    )
    if citation_policy not in {"required", "forbidden", "optional"}:
        raise RuntimeError(f"unsupported citation policy: {citation_policy}")
    if citation_policy == "optional" and not cited_node_ids:
        expected_recall = 1.0
    elif expected_citations:
        expected_recall = len(cited_node_ids & expected_citations) / len(expected_citations)
    else:
        expected_recall = float(not cited_node_ids)
    unauthorized = sorted(cited_node_ids & forbidden_node_ids)
    for node_id in forbidden_node_ids:
        if node_id in answer or node_id.casefold() in answer.casefold():
            unauthorized.append(node_id)
    unauthorized = sorted(set(unauthorized))

    limitation_ok = limitations_found == len(required_limitations)
    facts_ok = facts_found == len(required_facts)
    if citation_policy == "required":
        citations_ok = citation_count > 0
    elif citation_policy == "forbidden":
        citations_ok = citation_count == 0
    else:
        citations_ok = True
    unsupported_safe = limitation_ok if required_limitations else True
    answer_correct = bool(
        facts_ok
        and limitation_ok
        and not forbidden_found
        and citations_ok
        and not unauthorized
    )
    return VariantResult(
        answer=answer,
        answer_correct=answer_correct,
        facts_found=facts_found,
        facts_required=len(required_facts),
        limitations_found=limitations_found,
        limitations_required=len(required_limitations),
        forbidden_phrases_found=forbidden_found,
        citation_count=citation_count,
        citation_precision=valid_citations / citation_count if citation_count else 1.0,
        expected_citation_recall=expected_recall,
        inline_citation_integrity=inline_integrity,
        verified_highlight_rate=verified_highlights / citation_count if citation_count else 1.0,
        wrong_locator_acceptances=wrong_locator_acceptances,
        unsupported_answer_safe=unsupported_safe,
        unauthorized_node_leaks=unauthorized,
        generation_ms=answer_result.generation_time_ms,
        request_ms=request_ms,
        selected_node_ids=[node.node_id for node in selected_nodes],
    )


def _run_case(
    case: dict[str, Any],
    expectation: dict[str, Any],
    provider: AnswerProvider,
) -> PairedCaseResult:
    nodes, edges, expanded = _make_case_graph(case)
    denied = set(case.get("denied_nodes", []))
    engine = EvidenceChainEngine(
        FixtureDB(nodes, edges),
        FixtureACL(denied),
        EvidenceChainConfig(mode="auto"),
    )

    chain_started = time.perf_counter()
    chain_result = engine.build(
        expanded,
        case["question"],
        case["seeds"],
        doc_id="fixture-doc",
        version=1,
    )
    chain_layer_ms = (time.perf_counter() - chain_started) * 1000

    baseline_ids = list(case["seeds"])
    baseline_context, baseline_nodes = _packed_context(expanded, baseline_ids)

    chain_ids = chain_result.ordered_node_ids if chain_result.applied else baseline_ids
    expanded.chain_nodes = chain_result.additional_nodes
    for node in expanded.chain_nodes:
        expanded.node_sources[node.node_id] = "chain"
    chain_context, chain_nodes = _packed_context(expanded, chain_ids)

    baseline_started = time.perf_counter()
    baseline_answer = provider.generate(
        context=baseline_context,
        question=case["question"],
        nodes=baseline_nodes,
        expectation=expectation,
    )
    baseline_request_ms = (time.perf_counter() - baseline_started) * 1000
    baseline_request_ms = max(baseline_request_ms, baseline_answer.generation_time_ms)

    chain_started = time.perf_counter()
    chain_answer = provider.generate(
        context=chain_context,
        question=case["question"],
        nodes=chain_nodes,
        expectation=expectation,
    )
    chain_generation_request_ms = (time.perf_counter() - chain_started) * 1000
    chain_request_ms = max(chain_generation_request_ms, chain_answer.generation_time_ms) + chain_layer_ms

    return PairedCaseResult(
        case_id=case["id"],
        domain=case["domain"],
        route_expected=case["expect_route"],
        route_actual=chain_result.route.applied,
        chain_applied=chain_result.applied,
        fallback_used=chain_result.fallback_used,
        chain_layer_ms=chain_layer_ms,
        baseline=_evaluate_variant(
            answer_result=baseline_answer,
            selected_nodes=baseline_nodes,
            expectation=expectation,
            forbidden_node_ids=denied,
            request_ms=baseline_request_ms,
        ),
        chain=_evaluate_variant(
            answer_result=chain_answer,
            selected_nodes=chain_nodes,
            expectation=expectation,
            forbidden_node_ids=denied,
            request_ms=chain_request_ms,
        ),
    )


def _rate(values: Iterable[bool]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 1.0


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _percentile(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = round((len(ordered) - 1) * percentile)
    return ordered[min(len(ordered) - 1, max(0, rank))]


def _build_report(
    cases: list[PairedCaseResult],
    expectations: dict[str, dict[str, Any]],
    *,
    provider_name: str,
    model: str,
) -> dict[str, Any]:
    routed = [case for case in cases if case.route_expected]
    single_hop = [case for case in cases if not case.route_expected]
    unsupported = [case for case in cases if case.case_id == "regression_unsupported_why"]

    baseline_accuracy = _rate(case.baseline.answer_correct for case in cases)
    chain_accuracy = _rate(case.chain.answer_correct for case in cases)
    routed_baseline_accuracy = _rate(case.baseline.answer_correct for case in routed)
    routed_chain_accuracy = _rate(case.chain.answer_correct for case in routed)
    baseline_citation_precision = _mean(case.baseline.citation_precision for case in cases)
    chain_citation_precision = _mean(case.chain.citation_precision for case in cases)
    baseline_highlight_rate = _mean(case.baseline.verified_highlight_rate for case in cases)
    chain_highlight_rate = _mean(case.chain.verified_highlight_rate for case in cases)
    baseline_request_values = [case.baseline.request_ms for case in cases]
    chain_request_values = [case.chain.request_ms for case in cases]
    baseline_p95_ms = _percentile(baseline_request_values, 0.95)
    chain_request_p95_ms = _percentile(chain_request_values, 0.95)
    chain_layer_values = [case.chain_layer_ms for case in cases]
    overhead_ratio = _percentile(chain_layer_values, 0.95) / max(baseline_p95_ms, 0.001)
    total_request_p95_overhead_ratio = (
        chain_request_p95_ms / max(baseline_p95_ms, 0.001)
    ) - 1.0
    paired_total_request_overhead_ratios = [
        (case.chain.request_ms / max(case.baseline.request_ms, 0.001)) - 1.0
        for case in cases
    ]
    fallback_rate = _mean(float(case.fallback_used) for case in cases)
    wrong_locator_acceptances = sum(
        case.chain.wrong_locator_acceptances for case in cases
    )
    unauthorized_leaks = sum(len(case.chain.unauthorized_node_leaks) for case in cases)

    def selected_evidence_recall(case: PairedCaseResult, variant: str) -> float:
        expected = set(expectations[case.case_id]["expected_citation_nodes"])
        selected = set(getattr(case, variant).selected_node_ids)
        return len(selected & expected) / len(expected) if expected else 1.0

    metrics = {
        "baseline_answer_accuracy": baseline_accuracy,
        "chain_answer_accuracy": chain_accuracy,
        "routed_baseline_answer_accuracy": routed_baseline_accuracy,
        "routed_chain_answer_accuracy": routed_chain_accuracy,
        "routed_absolute_accuracy_improvement": routed_chain_accuracy - routed_baseline_accuracy,
        "baseline_citation_precision": baseline_citation_precision,
        "chain_citation_precision": chain_citation_precision,
        "baseline_expected_citation_recall": _mean(
            case.baseline.expected_citation_recall for case in cases
        ),
        "chain_expected_citation_recall": _mean(
            case.chain.expected_citation_recall for case in cases
        ),
        "baseline_selected_evidence_recall": _mean(
            selected_evidence_recall(case, "baseline") for case in cases
        ),
        "chain_selected_evidence_recall": _mean(
            selected_evidence_recall(case, "chain") for case in cases
        ),
        "baseline_verified_highlight_rate": baseline_highlight_rate,
        "chain_verified_highlight_rate": chain_highlight_rate,
        "single_hop_baseline_accuracy": _rate(
            case.baseline.answer_correct for case in single_hop
        ),
        "single_hop_chain_accuracy": _rate(case.chain.answer_correct for case in single_hop),
        "unsupported_baseline_safe_rate": _rate(
            case.baseline.unsupported_answer_safe for case in unsupported
        ),
        "unsupported_chain_safe_rate": _rate(
            case.chain.unsupported_answer_safe for case in unsupported
        ),
        "route_accuracy": _rate(case.route_actual == case.route_expected for case in cases),
        "fallback_rate": fallback_rate,
        "unauthorized_node_leaks": unauthorized_leaks,
        "wrong_locator_acceptances": wrong_locator_acceptances,
        "baseline_request_p50_ms": _percentile(baseline_request_values, 0.50),
        "baseline_request_p95_ms": baseline_p95_ms,
        "baseline_request_p99_ms": _percentile(baseline_request_values, 0.99),
        "chain_request_p50_ms": _percentile(chain_request_values, 0.50),
        "chain_request_p95_ms": chain_request_p95_ms,
        "chain_request_p99_ms": _percentile(chain_request_values, 0.99),
        "total_request_p95_overhead_ratio": total_request_p95_overhead_ratio,
        "paired_total_request_overhead_p50_ratio": _percentile(
            paired_total_request_overhead_ratios, 0.50
        ),
        "paired_total_request_overhead_p95_ratio": _percentile(
            paired_total_request_overhead_ratios, 0.95
        ),
        "chain_layer_p50_ms": _percentile(chain_layer_values, 0.50),
        "chain_layer_p95_ms": _percentile(chain_layer_values, 0.95),
        "chain_layer_p99_ms": _percentile(chain_layer_values, 0.99),
        "chain_p95_overhead_ratio": overhead_ratio,
    }
    gates = {
        "routed_answer_accuracy_improves_by_5_points": metrics[
            "routed_absolute_accuracy_improvement"
        ] >= 0.05,
        "citation_precision_no_regression": chain_citation_precision >= baseline_citation_precision,
        "verified_highlights_no_regression": chain_highlight_rate >= baseline_highlight_rate,
        "expected_citation_recall_no_regression": metrics[
            "chain_expected_citation_recall"
        ] >= metrics["baseline_expected_citation_recall"],
        "wrong_document_page_version_fail_closed": wrong_locator_acceptances == 0,
        "unauthorized_leakage_zero": unauthorized_leaks == 0,
        "single_hop_no_regression": metrics["single_hop_chain_accuracy"] >= metrics[
            "single_hop_baseline_accuracy"
        ],
        "unsupported_answers_no_regression": metrics[
            "unsupported_chain_safe_rate"
        ] >= metrics["unsupported_baseline_safe_rate"],
        "route_accuracy_100_percent": metrics["route_accuracy"] == 1.0,
        "fallback_rate_at_most_10_percent": fallback_rate <= 0.10,
        "chain_p95_overhead_at_most_20_percent": overhead_ratio <= 0.20,
        "inline_citation_integrity_100_percent": all(
            case.chain.inline_citation_integrity for case in cases
        ),
        "curated_chain_answer_accuracy_100_percent": chain_accuracy == 1.0,
        "curated_chain_citation_precision_100_percent": chain_citation_precision == 1.0,
        "curated_chain_selected_evidence_recall_100_percent": metrics[
            "chain_selected_evidence_recall"
        ] == 1.0,
        "curated_chain_verified_highlights_100_percent": chain_highlight_rate == 1.0,
    }
    return {
        "contract_id": "rag_eval_contract",
        "mode": "evidence_chain_ab",
        "provider": provider_name,
        "model": model,
        "dataset_sha256": _sha256(DATASET_PATH),
        "expectations_sha256": _sha256(EXPECTATIONS_PATH),
        "case_count": len(cases),
        "metrics": metrics,
        "gates": gates,
        "passed": all(gates.values()),
        "observations": {
            "total_request_latency_is_measured_not_gated": True,
            "total_request_latency_note": (
                "Total provider latency is reported separately from the chain-layer "
                "release gate and requires representative load testing before default-on."
            ),
        },
        "cases": [asdict(case) for case in cases],
    }


def evaluate(provider: AnswerProvider | None = None) -> dict[str, Any]:
    dataset, expectations = _load_locked_inputs()
    provider = provider or FixtureAnswerProvider()
    cases = [
        _run_case(case, expectations[case["id"]], provider)
        for case in dataset["cases"]
    ]
    return _build_report(
        cases,
        expectations,
        provider_name=provider.name,
        model=provider.model,
    )


def regrade_saved_report(report_path: Path) -> dict[str, Any]:
    """Recompute current gates from a prior report without calling a provider."""
    dataset, expectations = _load_locked_inputs()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    if saved.get("dataset_sha256") != _sha256(DATASET_PATH):
        raise RuntimeError("saved report dataset hash does not match the locked input")
    if saved.get("expectations_sha256") != _sha256(EXPECTATIONS_PATH):
        raise RuntimeError("saved report expectations hash does not match the locked input")
    expected_ids = {case["id"] for case in dataset["cases"]}
    saved_ids = {case.get("case_id") for case in saved.get("cases", [])}
    if saved_ids != expected_ids or len(saved.get("cases", [])) != len(expected_ids):
        raise RuntimeError("saved report cases do not match the locked input")

    cases: list[PairedCaseResult] = []
    for item in saved["cases"]:
        cases.append(
            PairedCaseResult(
                case_id=item["case_id"],
                domain=item["domain"],
                route_expected=item["route_expected"],
                route_actual=item["route_actual"],
                chain_applied=item["chain_applied"],
                fallback_used=item["fallback_used"],
                chain_layer_ms=item["chain_layer_ms"],
                baseline=VariantResult(**item["baseline"]),
                chain=VariantResult(**item["chain"]),
            )
        )
    return _build_report(
        cases,
        expectations,
        provider_name=saved["provider"],
        model=saved["model"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("fixture", "openai"), default="fixture")
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument(
        "--regrade",
        type=Path,
        help="Recompute current gates from a saved report without provider calls.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.regrade:
        report = regrade_saved_report(args.regrade)
    else:
        provider: AnswerProvider
        if args.provider == "openai":
            provider = OpenAIAnswerProvider(args.model)
        else:
            provider = FixtureAnswerProvider()
        report = evaluate(provider)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
