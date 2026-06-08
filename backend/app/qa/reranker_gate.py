"""Metric-gated reranking eligibility (E2 extraction from QARunner).

Relocated verbatim from app/qa/runner.py — these classes had no QARunner
instance coupling. Re-exported from runner.py for backward-compatible imports.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class RerankerGateContext:
    """Context for reranker gate decision."""
    # Baseline metrics (from recent evals)
    baseline_seed_precision_at_5: float = 0.0
    baseline_evidence_recall: float = 0.0

    # A/B comparison metrics
    rerank_seed_precision_at_5: float = 0.0
    rerank_evidence_recall: float = 0.0
    rerank_ab_improvement_at_5: float = 0.0

    # Performance metrics
    rerank_latency_overhead_pct: float = 0.0
    rerank_degeneracy_rate: float = 0.0  # % of questions with degenerate output

    # Baseline improvement trend (from N eval runs)
    baseline_precision_trend: float = 0.0  # Change in precision over recent runs


@dataclass
class RerankerGateResult:
    """Result of reranker gate evaluation."""
    allowed: bool = False
    reason: str = ""
    mode: str = "baseline"  # "baseline" | "gated" | "forced"

    # Individual gate checks
    baseline_plateau_check: bool = False
    ab_improvement_check: bool = False
    recall_regression_check: bool = False
    latency_check: bool = False
    stability_check: bool = False


class RerankerGate:
    """Metric-gated reranking eligibility checker.

    Reranking only runs when ALL conditions are met:
    1. Baseline plateau (precision improvement < +0.02)
    2. A/B improvement (rerank improves precision by ≥ +0.05)
    3. No recall regression
    4. Latency overhead ≤ 20%
    5. Stability (degeneracy rate ≤ 10%)
    """

    # Gate thresholds (from directive)
    BASELINE_PLATEAU_THRESHOLD = 0.02     # Max precision improvement before plateau
    AB_IMPROVEMENT_THRESHOLD = 0.05       # Min required rerank improvement
    LATENCY_OVERHEAD_MAX_PCT = 20.0       # Max latency overhead %
    DEGENERACY_RATE_MAX_PCT = 10.0        # Max degeneracy/fallback rate %

    # Fast mode limits (when gate passes)
    FAST_MODE_MAX_CANDIDATES = 12
    FAST_MODE_TIMEOUT_S = 2

    @classmethod
    def should_rerank(
        cls,
        context: Optional[RerankerGateContext] = None,
        force: bool = False
    ) -> RerankerGateResult:
        """Determine if reranking should run.

        Args:
            context: Gate context with metrics (None = use defaults/deny)
            force: Manual override via --rerank-force flag

        Returns:
            RerankerGateResult with decision and reasoning
        """
        result = RerankerGateResult()

        # Manual override
        if force:
            result.allowed = True
            result.mode = "forced"
            result.reason = "forced_by_flag"
            logger.warning("[RerankerGate] Reranking FORCED via --rerank-force flag")
            return result

        # No context = no metrics = deny
        if context is None:
            result.allowed = False
            result.mode = "baseline"
            result.reason = "no_gate_context"
            logger.info("[RerankerGate] Reranking DENIED: no gate context provided")
            return result

        # Check all gate conditions
        failures = []

        # 1. Baseline plateau check
        # Baseline is still improving if trend >= threshold
        if context.baseline_precision_trend >= cls.BASELINE_PLATEAU_THRESHOLD:
            failures.append(f"baseline_still_improving({context.baseline_precision_trend:.3f}>={cls.BASELINE_PLATEAU_THRESHOLD})")
        else:
            result.baseline_plateau_check = True

        # 2. A/B improvement check
        if context.rerank_ab_improvement_at_5 < cls.AB_IMPROVEMENT_THRESHOLD:
            failures.append(f"ab_improvement_too_low({context.rerank_ab_improvement_at_5:.3f}<{cls.AB_IMPROVEMENT_THRESHOLD})")
        else:
            result.ab_improvement_check = True

        # 3. No recall regression
        if context.rerank_evidence_recall < context.baseline_evidence_recall:
            failures.append(f"recall_regression({context.rerank_evidence_recall:.2f}<{context.baseline_evidence_recall:.2f})")
        else:
            result.recall_regression_check = True

        # 4. Latency overhead check
        if context.rerank_latency_overhead_pct > cls.LATENCY_OVERHEAD_MAX_PCT:
            failures.append(f"latency_too_high({context.rerank_latency_overhead_pct:.1f}%>{cls.LATENCY_OVERHEAD_MAX_PCT}%)")
        else:
            result.latency_check = True

        # 5. Stability check
        if context.rerank_degeneracy_rate > cls.DEGENERACY_RATE_MAX_PCT:
            failures.append(f"degeneracy_too_high({context.rerank_degeneracy_rate:.1f}%>{cls.DEGENERACY_RATE_MAX_PCT}%)")
        else:
            result.stability_check = True

        # All checks must pass
        if failures:
            result.allowed = False
            result.mode = "baseline"
            result.reason = "; ".join(failures)
            logger.info(f"[RerankerGate] Reranking DENIED: {result.reason}")
        else:
            result.allowed = True
            result.mode = "gated"
            result.reason = "all_gates_passed"
            logger.info("[RerankerGate] Reranking ALLOWED: all gate conditions met")

        return result

    @classmethod
    def get_fast_mode_config(cls) -> Dict[str, Any]:
        """Get fast mode configuration when gate passes."""
        return {
            "max_candidates": cls.FAST_MODE_MAX_CANDIDATES,
            "timeout_s": cls.FAST_MODE_TIMEOUT_S,
        }
