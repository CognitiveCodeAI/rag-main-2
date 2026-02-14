"""Integration-style harness tests for heal mode behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.monitor.config import MonitorConfig
from app.monitor.observer import MonitorObserver
from app.monitor.remediation import HealRemediator
from app.monitor.types import CheckResult


def _make_config(tmp_path: Path, *, threshold: int = 5) -> MonitorConfig:
    return MonitorConfig(
        enabled=True,
        mode="heal",
        dry_run=False,
        interval_seconds=1,
        max_retries=1,
        backoff_seconds=1,
        circuit_breaker_threshold=threshold,
        repo_root=tmp_path,
        compose_file=tmp_path / "docker-compose.yml",
        state_file=tmp_path / ".monitor_state.json",
        log_file=tmp_path / "logs" / "monitor.jsonl",
        api_ready_url="http://localhost:8000/health/ready",
        docker_services=("postgres", "etcd", "minio-milvus", "milvus", "minio", "redis"),
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


@dataclass
class FakeCheckHarness:
    """Minimal check harness for observer/remediator tests."""

    failing_result: CheckResult
    healthy_result: CheckResult
    healthy_after_service: str
    restarted_services: set[str]

    def run_all(self) -> list[CheckResult]:
        return [self.failing_result]

    def run_check(self, check_name: str) -> CheckResult:
        if check_name != self.failing_result.name:
            raise ValueError(f"Unexpected check: {check_name}")
        if self.healthy_after_service in self.restarted_services:
            return self.healthy_result
        return self.failing_result


def _clock(start: datetime):
    current = {"value": start}

    def now_provider():
        value = current["value"]
        current["value"] = value + timedelta(seconds=2)
        return value

    return now_provider


def test_heal_simulated_container_down_restarts_and_recovers(tmp_path: Path):
    failing = CheckResult(
        name="infra_containers",
        healthy=False,
        summary="Infrastructure issues detected in 1 service(s)",
        diagnosis={"failures": {"redis": "container missing/not running"}, "services": {}},
        next_step="Run ./dev logs infra.",
        fingerprint="infra-redis-down",
    )
    healthy = CheckResult(
        name="infra_containers",
        healthy=True,
        summary="Infrastructure containers are running and healthy",
        diagnosis={"failures": {}, "services": {"redis": {"state": "running", "health": "healthy"}}},
        next_step="No action required.",
        fingerprint="infra-ok",
    )

    restarted: set[str] = set()
    harness = FakeCheckHarness(
        failing_result=failing,
        healthy_result=healthy,
        healthy_after_service="redis",
        restarted_services=restarted,
    )

    def command_runner(cmd, timeout_seconds, cwd):
        del timeout_seconds, cwd
        if cmd[-2:] == ["restart", "redis"]:
            restarted.add("redis")
        return 0, "ok", ""

    config = _make_config(tmp_path)
    remediator = HealRemediator(
        config=config,
        checks=harness,
        command_runner=command_runner,
        sleep_func=lambda _: None,
        compose_cmd=["docker", "compose", "-f", str(config.compose_file)],
    )
    observer = MonitorObserver(
        config=config,
        checks=harness,
        remediator=remediator,
        now_provider=_clock(datetime(2026, 2, 14, tzinfo=timezone.utc)),
    )

    observer.run_cycle()
    events = _read_jsonl(config.log_file)

    assert len(events) == 1
    event = events[0]
    assert event["check"] == "infra_containers"
    assert event["action"]["type"] == "restart_services"
    assert any(cmd.endswith("restart redis") for cmd in event["action"]["commands"])
    assert event["outcome"]["status"] == "resolved"


def test_heal_db_unreachable_restarts_postgres_and_recovers(tmp_path: Path):
    failing = CheckResult(
        name="db_connectivity",
        healthy=False,
        summary="PostgreSQL connectivity check failed",
        diagnosis={"error": "connection refused"},
        next_step="Run ./dev logs infra.",
        fingerprint="db-down",
    )
    healthy = CheckResult(
        name="db_connectivity",
        healthy=True,
        summary="PostgreSQL connectivity check passed",
        diagnosis={"latency_ms": 12.3},
        next_step="No action required.",
        fingerprint="db-ok",
    )

    restarted: set[str] = set()
    harness = FakeCheckHarness(
        failing_result=failing,
        healthy_result=healthy,
        healthy_after_service="postgres",
        restarted_services=restarted,
    )

    def command_runner(cmd, timeout_seconds, cwd):
        del timeout_seconds, cwd
        if cmd[-2:] == ["restart", "postgres"]:
            restarted.add("postgres")
        return 0, "ok", ""

    config = _make_config(tmp_path)
    remediator = HealRemediator(
        config=config,
        checks=harness,
        command_runner=command_runner,
        sleep_func=lambda _: None,
        compose_cmd=["docker", "compose", "-f", str(config.compose_file)],
    )
    observer = MonitorObserver(
        config=config,
        checks=harness,
        remediator=remediator,
        now_provider=_clock(datetime(2026, 2, 14, tzinfo=timezone.utc)),
    )

    observer.run_cycle()
    events = _read_jsonl(config.log_file)

    assert len(events) == 1
    event = events[0]
    assert event["check"] == "db_connectivity"
    assert event["action"]["type"] == "restart_db"
    assert any(cmd.endswith("restart postgres") for cmd in event["action"]["commands"])
    assert event["outcome"]["status"] == "resolved"


def test_heal_repeated_failure_engages_circuit_breaker(tmp_path: Path):
    failing = CheckResult(
        name="api_readiness",
        healthy=False,
        summary="Backend readiness degraded",
        diagnosis={"failing_services": ["redis"], "overall_status": "degraded"},
        next_step="Run ./dev status and inspect backend dependency failures.",
        fingerprint="api-redis-down",
    )

    class AlwaysFailChecks:
        def run_all(self):
            return [failing]

        def run_check(self, check_name: str):
            assert check_name == "api_readiness"
            return failing

    checks = AlwaysFailChecks()
    command_calls: list[list[str]] = []

    def command_runner(cmd, timeout_seconds, cwd):
        del timeout_seconds, cwd
        command_calls.append(cmd)
        return 0, "ok", ""

    config = _make_config(tmp_path, threshold=2)
    remediator = HealRemediator(
        config=config,
        checks=checks,
        command_runner=command_runner,
        sleep_func=lambda _: None,
        compose_cmd=["docker", "compose", "-f", str(config.compose_file)],
    )
    observer = MonitorObserver(
        config=config,
        checks=checks,
        remediator=remediator,
        now_provider=_clock(datetime(2026, 2, 14, tzinfo=timezone.utc)),
    )

    observer.run_cycle()
    observer.run_cycle()
    events = _read_jsonl(config.log_file)
    assert len(events) == 2

    # First failure attempts healing.
    assert events[0]["action"]["type"] == "restart_services"
    assert len(command_calls) == 1

    # Second repeated failure crosses threshold and engages circuit breaker.
    assert events[1]["action"]["type"] == "circuit_breaker_engaged"
    assert len(command_calls) == 1
    assert "manual intervention required" in events[1]["next_recommended_manual_step"].lower()

    status = observer.status_snapshot(run_live_checks=False)
    breaker = status["circuit_breakers"]["api_readiness"]
    assert breaker["engaged"] is True


def test_monitor_survives_remediation_exception(tmp_path: Path):
    failing = CheckResult(
        name="api_readiness",
        healthy=False,
        summary="Backend readiness degraded",
        diagnosis={"failing_services": ["redis"], "overall_status": "degraded"},
        next_step="Run ./dev status and inspect backend dependency failures.",
        fingerprint="api-redis-down",
    )

    class AlwaysFailChecks:
        def run_all(self):
            return [failing]

        def run_check(self, check_name: str):
            assert check_name == "api_readiness"
            return failing

    class BrokenRemediator:
        def remediate(self, result):
            del result
            raise RuntimeError("boom")

    config = _make_config(tmp_path, threshold=10)
    observer = MonitorObserver(
        config=config,
        checks=AlwaysFailChecks(),
        remediator=BrokenRemediator(),
        now_provider=_clock(datetime(2026, 2, 14, tzinfo=timezone.utc)),
    )

    cycle = observer.run_cycle()
    assert cycle.emitted_events == 1

    events = _read_jsonl(config.log_file)
    assert len(events) == 1
    assert events[0]["action"]["type"] == "remediation_error"
    assert events[0]["outcome"]["status"] == "unresolved"


def test_monitor_survives_check_exception(tmp_path: Path):
    class BrokenChecks:
        def run_all(self):
            raise RuntimeError("check failure")

        def run_check(self, check_name: str):
            del check_name
            raise RuntimeError("unused")

    class NoopRemediator:
        def remediate(self, result):
            del result
            raise AssertionError("Should not be called")

    config = _make_config(tmp_path, threshold=10)
    observer = MonitorObserver(
        config=config,
        checks=BrokenChecks(),
        remediator=NoopRemediator(),
        now_provider=_clock(datetime(2026, 2, 14, tzinfo=timezone.utc)),
    )

    cycle = observer.run_cycle()
    assert cycle.emitted_events == 1
    assert len(cycle.check_results) == 1
    assert cycle.check_results[0].name == "monitor_internal_checks"

    events = _read_jsonl(config.log_file)
    assert len(events) == 1
    assert events[0]["check"] == "monitor_internal_checks"
    assert events[0]["outcome"]["status"] == "unresolved"
