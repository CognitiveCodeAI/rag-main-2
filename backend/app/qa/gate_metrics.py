"""Gate metrics persistence for reranker eligibility.

Stores and loads A/B evaluation metrics that the RerankerGate uses to decide
whether reranking should run in production.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default path relative to backend directory
GATE_METRICS_FILENAME = "gate_metrics.json"
GATE_METRICS_DIR = Path(__file__).parent.parent.parent / "tests" / "eval"


def get_gate_metrics_path() -> Path:
    """Get the path to gate_metrics.json."""
    return GATE_METRICS_DIR / GATE_METRICS_FILENAME


def save_gate_metrics(metrics: Dict[str, Any]) -> Path:
    """Save gate metrics from A/B evaluation.
    
    Args:
        metrics: Dict containing gate metrics:
            - baseline_seed_precision_at_5: float
            - baseline_evidence_recall: float
            - rerank_seed_precision_at_5: float
            - rerank_evidence_recall: float
            - rerank_ab_improvement_at_5: float
            - rerank_latency_overhead_pct: float
            - rerank_degeneracy_rate: float
            - baseline_precision_trend: float (optional)
            - timestamp: str (ISO format)
    
    Returns:
        Path to saved file
    """
    path = get_gate_metrics_path()
    
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Add timestamp if not present
    if "timestamp" not in metrics:
        metrics["timestamp"] = datetime.utcnow().isoformat()
    
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)
    
    logger.info(f"[GateMetrics] Saved gate metrics to {path}")
    return path


def load_gate_metrics() -> Optional[Dict[str, Any]]:
    """Load gate metrics from file.
    
    Returns:
        Dict of metrics or None if file doesn't exist
    """
    path = get_gate_metrics_path()
    
    if not path.exists():
        logger.warning(f"[GateMetrics] No gate metrics file found at {path}")
        return None
    
    try:
        with open(path, "r") as f:
            metrics = json.load(f)
        logger.info(f"[GateMetrics] Loaded gate metrics from {path}")
        return metrics
    except Exception as e:
        logger.error(f"[GateMetrics] Failed to load gate metrics: {e}")
        return None


def load_gate_context() -> Optional["RerankerGateContext"]:
    """Load gate context from persisted metrics.
    
    Returns:
        RerankerGateContext populated from saved metrics, or None if unavailable
    """
    # Import here to avoid circular imports
    from app.qa.runner import RerankerGateContext
    
    metrics = load_gate_metrics()
    if metrics is None:
        return None
    
    try:
        context = RerankerGateContext(
            baseline_seed_precision_at_5=metrics.get("baseline_seed_precision_at_5", 0.0),
            baseline_evidence_recall=metrics.get("baseline_evidence_recall", 0.0),
            rerank_seed_precision_at_5=metrics.get("rerank_seed_precision_at_5", 0.0),
            rerank_evidence_recall=metrics.get("rerank_evidence_recall", 0.0),
            rerank_ab_improvement_at_5=metrics.get("rerank_ab_improvement_at_5", 0.0),
            rerank_latency_overhead_pct=metrics.get("rerank_latency_overhead_pct", 0.0),
            rerank_degeneracy_rate=metrics.get("rerank_degeneracy_rate", 0.0),
            baseline_precision_trend=metrics.get("baseline_precision_trend", 0.0),
        )
        logger.info(
            f"[GateMetrics] Built gate context: "
            f"baseline_prec={context.baseline_seed_precision_at_5:.3f}, "
            f"rerank_prec={context.rerank_seed_precision_at_5:.3f}, "
            f"improvement={context.rerank_ab_improvement_at_5:.3f}"
        )
        return context
    except Exception as e:
        logger.error(f"[GateMetrics] Failed to build gate context: {e}")
        return None
