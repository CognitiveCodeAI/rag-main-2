"""Unit tests for monitor dedupe/backoff behavior."""

from app.monitor.state import DedupeBackoffGate


def test_backoff_suppresses_repeated_failure_until_window_elapses():
    state = {"version": 1, "checks": {}, "last_summary": {}}
    gate = DedupeBackoffGate(state, backoff_seconds=10, max_backoff_seconds=60)

    first = gate.evaluate(
        check_name="api_readiness",
        failing=True,
        fingerprint="fp-a",
        now_ts=100.0,
    )
    assert first.emit is True
    assert first.event_kind == "detection"
    assert first.failure_count == 1

    suppressed = gate.evaluate(
        check_name="api_readiness",
        failing=True,
        fingerprint="fp-a",
        now_ts=105.0,
    )
    assert suppressed.emit is False
    assert suppressed.reason == "suppressed"
    assert suppressed.suppressed_count == 1

    emitted_after_backoff = gate.evaluate(
        check_name="api_readiness",
        failing=True,
        fingerprint="fp-a",
        now_ts=110.0,
    )
    assert emitted_after_backoff.emit is True
    assert emitted_after_backoff.event_kind == "detection"
    assert emitted_after_backoff.failure_count == 2


def test_backoff_emits_immediately_when_diagnosis_changes():
    state = {"version": 1, "checks": {}, "last_summary": {}}
    gate = DedupeBackoffGate(state, backoff_seconds=20, max_backoff_seconds=60)

    gate.evaluate(
        check_name="infra_containers",
        failing=True,
        fingerprint="service-a",
        now_ts=200.0,
    )

    changed = gate.evaluate(
        check_name="infra_containers",
        failing=True,
        fingerprint="service-b",
        now_ts=201.0,
    )
    assert changed.emit is True
    assert changed.reason == "diagnosis_changed"
    assert changed.failure_count == 2


def test_backoff_emits_resolution_once_when_check_recovers():
    state = {"version": 1, "checks": {}, "last_summary": {}}
    gate = DedupeBackoffGate(state, backoff_seconds=10, max_backoff_seconds=60)

    gate.evaluate(
        check_name="db_connectivity",
        failing=True,
        fingerprint="db-down",
        now_ts=300.0,
    )

    resolved = gate.evaluate(
        check_name="db_connectivity",
        failing=False,
        fingerprint="",
        now_ts=302.0,
    )
    assert resolved.emit is True
    assert resolved.event_kind == "resolution"
    assert resolved.reason == "recovered"

    duplicate_resolution = gate.evaluate(
        check_name="db_connectivity",
        failing=False,
        fingerprint="",
        now_ts=303.0,
    )
    assert duplicate_resolution.emit is False
