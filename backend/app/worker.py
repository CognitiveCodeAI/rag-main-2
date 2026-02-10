"""Celery worker configuration for NPR RAG."""

import os

from celery import Celery

# Redis connection (defaults match docker-compose.yml for local development)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_BACKEND = os.getenv("REDIS_BACKEND", "redis://localhost:6379/1")

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
)
