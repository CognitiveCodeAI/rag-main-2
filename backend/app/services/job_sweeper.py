"""Stale-job sweeper (D3 / audit H-6).

A worker can die mid-job (e.g. the macOS prefork crash) leaving an ingest or
embedding job stuck in an active state forever. The worker updates
``last_heartbeat_at`` as it progresses; this module fails jobs whose heartbeat
(or, absent one, creation time) is older than a threshold.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Statuses that represent an in-flight job which should make progress.
ACTIVE_STATUSES = ("pending", "queued", "processing")

DEFAULT_STALE_MINUTES = 30


def is_job_stale(
    status: str,
    last_heartbeat_at: Optional[datetime],
    created_at: Optional[datetime],
    now: datetime,
    threshold_minutes: int = DEFAULT_STALE_MINUTES,
) -> bool:
    """Pure predicate: is an active job past its no-progress deadline?

    Uses ``last_heartbeat_at`` when present, otherwise ``created_at``. A job
    with neither timestamp is treated as not-stale (insufficient information).
    """
    if status not in ACTIVE_STATUSES:
        return False
    reference = last_heartbeat_at or created_at
    if reference is None:
        return False
    return reference < (now - timedelta(minutes=threshold_minutes))


def sweep_stale_jobs(
    db,
    threshold_minutes: int = DEFAULT_STALE_MINUTES,
    now: Optional[datetime] = None,
) -> int:
    """Mark active jobs with no recent heartbeat as failed. Returns the count.

    Best-effort: never raises into the caller (a failed sweep must not break a
    list/status request); errors are logged and the transaction rolled back.
    """
    # Imported lazily to keep this module import-light.
    from app.db.models import IngestJob, EmbeddingJob

    now = now or datetime.now(timezone.utc)
    swept = 0
    try:
        for model in (IngestJob, EmbeddingJob):
            rows = db.query(model).filter(model.status.in_(ACTIVE_STATUSES)).all()
            for job in rows:
                if is_job_stale(
                    job.status, job.last_heartbeat_at, job.created_at, now, threshold_minutes
                ):
                    job.status = "failed"
                    job.error = job.error or "Job timed out: no progress heartbeat"
                    job.completed_at = now
                    swept += 1
        if swept:
            db.commit()
            logger.warning("Stale-job sweeper failed %d stuck job(s)", swept)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Stale-job sweep failed: %s", exc)
        db.rollback()
    return swept
