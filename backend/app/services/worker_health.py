"""Celery worker health utilities."""

from dataclasses import dataclass

from app.worker import celery_app


@dataclass(frozen=True)
class CeleryWorkerStatus:
    """Result of a Celery worker availability check."""

    healthy: bool
    worker_count: int
    message: str


def inspect_celery_workers(timeout: float = 1.0) -> CeleryWorkerStatus:
    """Ping Celery workers and return an availability snapshot."""
    try:
        inspector = celery_app.control.inspect(timeout=timeout)
        ping_response = inspector.ping() or {}
        worker_count = len(ping_response)

        if worker_count == 0:
            return CeleryWorkerStatus(
                healthy=False,
                worker_count=0,
                message="No Celery workers responded to ping.",
            )

        noun = "worker" if worker_count == 1 else "workers"
        return CeleryWorkerStatus(
            healthy=True,
            worker_count=worker_count,
            message=f"{worker_count} Celery {noun} responding.",
        )
    except Exception as exc:
        return CeleryWorkerStatus(
            healthy=False,
            worker_count=0,
            message=f"Celery worker check failed: {exc}",
        )
