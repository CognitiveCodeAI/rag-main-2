"""Celery worker configuration for NPR RAG."""

from celery import Celery

from app.config import get_settings

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
