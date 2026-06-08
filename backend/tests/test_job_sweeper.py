"""Unit tests for the stale-job staleness predicate (D3 / audit H-6)."""

from datetime import datetime, timedelta, timezone

from app.services.job_sweeper import is_job_stale

NOW = datetime(2026, 6, 8, 12, 0, 0, tzinfo=timezone.utc)


def test_fresh_heartbeat_is_not_stale():
    hb = NOW - timedelta(minutes=2)
    assert is_job_stale("processing", hb, NOW - timedelta(hours=1), NOW, 30) is False


def test_old_heartbeat_is_stale():
    hb = NOW - timedelta(minutes=45)
    assert is_job_stale("processing", hb, NOW - timedelta(hours=2), NOW, 30) is True


def test_terminal_status_never_stale():
    old = NOW - timedelta(hours=5)
    assert is_job_stale("completed", old, old, NOW, 30) is False
    assert is_job_stale("failed", old, old, NOW, 30) is False


def test_falls_back_to_created_at_when_no_heartbeat():
    created_old = NOW - timedelta(minutes=40)
    assert is_job_stale("pending", None, created_old, NOW, 30) is True
    created_fresh = NOW - timedelta(minutes=5)
    assert is_job_stale("pending", None, created_fresh, NOW, 30) is False


def test_no_timestamps_is_not_stale():
    assert is_job_stale("processing", None, None, NOW, 30) is False
