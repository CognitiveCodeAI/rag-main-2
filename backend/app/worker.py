"""Celery worker configuration for NPR RAG."""

from celery import Celery
from celery.signals import after_setup_logger, task_prerun

from app.config import get_settings
from app.observability.request_id import bind_request_id, install_request_id_logging

settings = get_settings()

# Keep Celery broker/backend aligned with backend settings (.env-aware).
REDIS_URL = settings.redis_url
REDIS_BACKEND = settings.redis_backend

# Create Celery app
celery_app = Celery(
    "npr",
    broker=REDIS_URL,
    backend=REDIS_BACKEND,
    include=["app.tasks.ingest", "app.tasks.embed_nodes"],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3000,  # 50 minutes soft limit
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Be explicit about broker retry behavior during startup and transient outages.
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=None,
)


@after_setup_logger.connect
def _install_worker_request_id_logging(**_):
    """Inject the request id into worker log lines (E4)."""
    install_request_id_logging()


@task_prerun.connect
def _bind_task_request_id(task=None, **_):
    """Re-bind the correlation id propagated from the enqueuing request (E4).

    Falls back to a fresh id when a task was enqueued without one.
    """
    headers = {}
    try:
        headers = getattr(task.request, "headers", None) or {}
    except Exception:  # pragma: no cover - defensive
        headers = {}
    bind_request_id(headers.get("request_id", ""))
