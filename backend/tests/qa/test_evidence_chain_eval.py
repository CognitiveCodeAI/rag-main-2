"""Contract test for the locked evidence-chain evaluation harness."""

from tests.eval.run_evidence_chain_eval import evaluate


def test_locked_evidence_chain_evaluation_passes_all_local_gates():
    report = evaluate()

    assert report["passed"] is True
    assert report["case_count"] == 12
    assert report["metrics"]["route_accuracy"] == 1.0
    assert report["metrics"]["chain_evidence_recall"] == 1.0
    assert report["metrics"]["absolute_recall_improvement"] > 0.0
    assert report["metrics"]["forbidden_leaks"] == 0
    assert report["metrics"]["deterministic_rate"] == 1.0
