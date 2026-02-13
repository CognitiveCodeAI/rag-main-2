"""Tests for Celery worker health checks."""

from unittest.mock import MagicMock, patch

from app.services.worker_health import inspect_celery_workers


def test_inspect_celery_workers_reports_healthy():
    """Worker check should be healthy when at least one worker responds."""
    inspect_mock = MagicMock()
    inspect_mock.ping.return_value = {"worker@localhost": {"ok": "pong"}}

    with patch("app.services.worker_health.celery_app.control.inspect", return_value=inspect_mock):
        status = inspect_celery_workers(timeout=0.1)

    assert status.healthy is True
    assert status.worker_count == 1
    assert "responding" in status.message.lower()


def test_inspect_celery_workers_reports_unhealthy_without_workers():
    """Worker check should be unhealthy when ping returns no workers."""
    inspect_mock = MagicMock()
    inspect_mock.ping.return_value = {}

    with patch("app.services.worker_health.celery_app.control.inspect", return_value=inspect_mock):
        status = inspect_celery_workers(timeout=0.1)

    assert status.healthy is False
    assert status.worker_count == 0
    assert "no celery workers" in status.message.lower()
