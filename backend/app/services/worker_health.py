"""Celery worker health utilities."""

from dataclasses import dataclass
import time

from app.worker import celery_app


@dataclass(frozen=True)
class CeleryWorkerStatus:
    """Result of a Celery worker availability check."""

    healthy: bool
    worker_count: int
    message: str


def inspect_celery_workers(timeout: float = 1.0) -> CeleryWorkerStatus:
    """Ping Celery workers and return an availability snapshot."""
    last_error: Exception | None = None

    # Retry once to reduce false negatives from brief broker/control-plane jitter.
    for attempt in range(2):
        try:
            inspector = celery_app.control.inspect(timeout=timeout)
            ping_response = inspector.ping() or {}
            worker_count = len(ping_response)

            if worker_count > 0:
                noun = "worker" if worker_count == 1 else "workers"
                return CeleryWorkerStatus(
                    healthy=True,
                    worker_count=worker_count,
                    message=f"{worker_count} Celery {noun} responding.",
                )

            # Fallback: for loaded workers, ping can occasionally miss. If stats are
            # available, treat the worker process as reachable.
            stats_response = inspector.stats() or {}
            stats_count = len(stats_response)
            if stats_count > 0:
                noun = "worker" if stats_count == 1 else "workers"
                return CeleryWorkerStatus(
                    healthy=True,
                    worker_count=stats_count,
                    message=(
                        f"{stats_count} Celery {noun} reachable via stats "
                        "(ping timed out)."
                    ),
                )
        except Exception as exc:
            last_error = exc

        if attempt == 0:
            time.sleep(0.2)

    if last_error:
        return CeleryWorkerStatus(
            healthy=False,
            worker_count=0,
            message=f"Celery worker check failed: {last_error}",
        )

    return CeleryWorkerStatus(
        healthy=False,
        worker_count=0,
        message="No Celery workers responded to ping.",
    )
