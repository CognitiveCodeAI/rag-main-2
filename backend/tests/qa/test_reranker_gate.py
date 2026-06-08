"""Characterization tests for RerankerGate (E2 extraction safety net).

These did not exist before the extraction; they pin should_rerank()'s decision
logic so the relocation to app/qa/reranker_gate.py is provably behavior-preserving.
"""

from app.qa.reranker_gate import RerankerGate, RerankerGateContext
# The re-export path must keep working (gate_metrics.py + run() rely on it).
from app.qa.runner import RerankerGate as RG_via_runner
from app.qa.runner import RerankerGateContext as RGC_via_runner


def _passing_ctx():
    return RerankerGateContext(
        baseline_precision_trend=0.0,        # < 0.02 plateau -> pass
        rerank_ab_improvement_at_5=0.10,     # >= 0.05 -> pass
        baseline_evidence_recall=0.5,
        rerank_evidence_recall=0.6,          # no regression
        rerank_latency_overhead_pct=10.0,    # <= 20 -> pass
        rerank_degeneracy_rate=5.0,          # <= 10 -> pass
    )


def test_reexport_is_identical_object():
    assert RG_via_runner is RerankerGate
    assert RGC_via_runner is RerankerGateContext


def test_force_allows():
    r = RerankerGate.should_rerank(force=True)
    assert r.allowed and r.mode == "forced" and r.reason == "forced_by_flag"


def test_no_context_denies():
    r = RerankerGate.should_rerank(context=None)
    assert not r.allowed and r.reason == "no_gate_context"


def test_all_gates_pass_allows():
    r = RerankerGate.should_rerank(context=_passing_ctx())
    assert r.allowed and r.mode == "gated" and r.reason == "all_gates_passed"


def test_baseline_still_improving_denies():
    ctx = _passing_ctx()
    ctx.baseline_precision_trend = 0.05  # >= 0.02 plateau threshold
    r = RerankerGate.should_rerank(context=ctx)
    assert not r.allowed and "baseline_still_improving" in r.reason


def test_ab_improvement_too_low_denies():
    ctx = _passing_ctx()
    ctx.rerank_ab_improvement_at_5 = 0.01  # < 0.05
    r = RerankerGate.should_rerank(context=ctx)
    assert not r.allowed and "ab_improvement_too_low" in r.reason


def test_recall_regression_denies():
    ctx = _passing_ctx()
    ctx.rerank_evidence_recall = 0.4  # < baseline 0.5
    r = RerankerGate.should_rerank(context=ctx)
    assert not r.allowed and "recall_regression" in r.reason


def test_latency_too_high_denies():
    ctx = _passing_ctx()
    ctx.rerank_latency_overhead_pct = 30.0  # > 20
    r = RerankerGate.should_rerank(context=ctx)
    assert not r.allowed and "latency_too_high" in r.reason


def test_degeneracy_too_high_denies():
    ctx = _passing_ctx()
    ctx.rerank_degeneracy_rate = 50.0  # > 10
    r = RerankerGate.should_rerank(context=ctx)
    assert not r.allowed and "degeneracy_too_high" in r.reason


def test_fast_mode_config():
    cfg = RerankerGate.get_fast_mode_config()
    assert cfg == {"max_candidates": 12, "timeout_s": 2}
