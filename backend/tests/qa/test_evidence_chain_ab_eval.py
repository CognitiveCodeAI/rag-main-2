"""Release-gate coverage for the locked answer-level evidence-chain A/B set."""

import json

from tests.eval.run_evidence_chain_ab import evaluate, regrade_saved_report


def test_locked_answer_and_provenance_ab_evaluation_passes_all_ci_gates():
    report = evaluate()

    assert report["passed"] is True
    assert report["case_count"] == 12
    assert report["provider"] == "fixture"
    assert report["metrics"]["chain_answer_accuracy"] == 1.0
    assert report["metrics"]["routed_absolute_accuracy_improvement"] >= 0.05
    assert report["metrics"]["chain_citation_precision"] == 1.0
    assert report["metrics"]["chain_selected_evidence_recall"] == 1.0
    assert report["metrics"]["chain_verified_highlight_rate"] == 1.0
    assert report["metrics"]["wrong_locator_acceptances"] == 0
    assert report["metrics"]["unauthorized_node_leaks"] == 0
    assert report["metrics"]["single_hop_chain_accuracy"] == report["metrics"][
        "single_hop_baseline_accuracy"
    ]
    assert "total_request_p95_overhead_ratio" in report["metrics"]
    assert report["observations"]["total_request_latency_is_measured_not_gated"] is True
    assert all(report["gates"].values())


def test_qa_prompt_forbids_unverifiable_citations_on_pure_abstentions():
    from app.prompts import get_prompt

    prompt = get_prompt("qa_answer").casefold()
    assert "pure abstention" in prompt
    assert "empty citations array" in prompt
    assert "never cite irrelevant or generic text" in prompt


def test_saved_report_can_be_regraded_offline_without_provider_calls(tmp_path):
    original = evaluate()
    saved = tmp_path / "report.json"
    saved.write_text(json.dumps(original), encoding="utf-8")

    regraded = regrade_saved_report(saved)

    assert regraded["passed"] is True
    assert regraded["provider"] == original["provider"]
    assert regraded["metrics"] == original["metrics"]


def test_ab_report_keeps_sensitive_acl_evidence_out_of_answer_and_citations():
    report = evaluate()
    acl_case = next(
        case for case in report["cases"] if case["case_id"] == "legal_acl_restricted_amendment"
    )

    assert "l5_restricted" not in acl_case["chain"]["selected_node_ids"]
    assert "increases the liability cap" not in acl_case["chain"]["answer"].casefold()
    assert acl_case["chain"]["unauthorized_node_leaks"] == []
    assert acl_case["chain"]["unsupported_answer_safe"] is True
