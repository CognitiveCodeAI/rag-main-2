"""Safe remediation actions for heal mode."""

from __future__ import annotations

import time
from typing import Callable

from app.monitor.checks import MonitorChecks, resolve_compose_cmd, run_command
from app.monitor.config import MonitorConfig
from app.monitor.types import CheckResult, RemediationResult

CommandRunner = Callable[[list[str], int, str | None], tuple[int, str, str]]


class HealRemediator:
    """Deterministic, conservative remediation executor."""

    # Infra dependency graph: dependency -> dependents
    _dependents: dict[str, list[str]] = {
        "etcd": ["milvus"],
        "minio-milvus": ["milvus"],
    }

    # Backend readiness check failure key -> compose service
    _api_service_map: dict[str, str] = {
        "postgresql": "postgres",
        "milvus": "milvus",
        "minio": "minio",
        "redis": "redis",
    }

    def __init__(
        self,
        config: MonitorConfig,
        checks: MonitorChecks,
        command_runner: CommandRunner | None = None,
        sleep_func: Callable[[float], None] | None = None,
        compose_cmd: list[str] | None = None,
    ):
        self.config = config
        self.checks = checks
        self.command_runner = command_runner or run_command
        self.sleep_func = sleep_func or time.sleep
        self.compose_cmd = compose_cmd if compose_cmd is not None else resolve_compose_cmd(str(config.compose_file))

    def remediate(self, result: CheckResult) -> RemediationResult:
        retry_outcome = self._retry_probe(result.name)
        if retry_outcome.resolved:
            return retry_outcome

        if result.name == "infra_containers":
            return self._remediate_infra(result)
        if result.name == "api_readiness":
            return self._remediate_api(result)
        if result.name == "db_connectivity":
            return self._remediate_db(result)

        return RemediationResult(
            action_type="none",
            description=f"No remediation strategy for {result.name}",
            commands=[],
            resolved=False,
            manual_step=result.next_step,
            details={"reason": "unknown_check"},
        )

    def _retry_probe(self, check_name: str) -> RemediationResult:
        """Safe first step: retry with short backoff."""
        details = {
            "check": check_name,
            "attempts": [],
        }

        for attempt in range(1, self.config.max_retries + 1):
            delay = self.config.backoff_seconds
            details["attempts"].append({"attempt": attempt, "sleep_seconds": delay})
            if not self.config.dry_run:
                self.sleep_func(delay)
            probe = self.checks.run_check(check_name)
            details["attempts"][-1]["healthy"] = probe.healthy
            details["attempts"][-1]["summary"] = probe.summary

            if probe.healthy:
                return RemediationResult(
                    action_type="retry_only",
                    description=f"Recovered after retry for check {check_name}",
                    commands=[],
                    resolved=True,
                    manual_step="No action required.",
                    details=details,
                )

        return RemediationResult(
            action_type="retry_only",
            description=f"Retry attempts exhausted for check {check_name}",
            commands=[],
            resolved=False,
            manual_step="No action yet; proceeding to conservative restart strategy.",
            details=details,
        )

    def _ordered_restart_targets(self, base_services: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []

        for service in base_services:
            if service not in seen:
                seen.add(service)
                ordered.append(service)

        for service in list(ordered):
            for dependent in self._dependents.get(service, []):
                if dependent not in seen:
                    seen.add(dependent)
                    ordered.append(dependent)

        return ordered

    def _restart_services(self, services: list[str]) -> tuple[list[str], list[str]]:
        commands: list[str] = []
        failures: list[str] = []

        if not services:
            return commands, failures

        if self.compose_cmd is None:
            failures.append("docker compose command unavailable")
            return commands, failures

        ordered = self._ordered_restart_targets(services)
        for service in ordered:
            cmd = [*self.compose_cmd, "restart", service]
            commands.append(" ".join(cmd))
            if self.config.dry_run:
                continue

            rc, stdout, stderr = self.command_runner(
                cmd,
                30,
                str(self.config.repo_root),
            )
            if rc != 0:
                failures.append(f"{service}: {stderr or stdout or 'restart failed'}")

        return commands, failures

    def _verify_resolution(self, check_name: str) -> CheckResult:
        return self.checks.run_check(check_name)

    def _remediate_infra(self, result: CheckResult) -> RemediationResult:
        failures = result.diagnosis.get("failures", {})
        targets = [svc for svc in failures.keys() if svc in self.config.docker_services]
        commands, restart_failures = self._restart_services(targets)
        post = self._verify_resolution(result.name)
        unresolved = (not post.healthy) or bool(restart_failures)

        return RemediationResult(
            action_type="restart_services",
            description="Restarted failed infrastructure services conservatively.",
            commands=commands,
            resolved=not unresolved,
            manual_step=(
                "Run ./dev logs infra and inspect unhealthy containers."
                if unresolved
                else "No action required."
            ),
            details={
                "targets": targets,
                "restart_failures": restart_failures,
                "post_check_summary": post.summary,
            },
        )

    def _remediate_api(self, result: CheckResult) -> RemediationResult:
        failing = result.diagnosis.get("failing_services", [])
        targets = []
        for key in failing:
            service = self._api_service_map.get(key)
            if service:
                targets.append(service)

        if not targets and "celery_worker" in failing:
            return RemediationResult(
                action_type="manual_required",
                description="Celery worker issue detected; monitor will not force worker restart.",
                commands=[],
                resolved=False,
                manual_step="Restart local app process (`./dev up`) to restore celery worker.",
                details={"failing_services": failing},
            )

        commands, restart_failures = self._restart_services(targets)
        post = self._verify_resolution(result.name)
        unresolved = (not post.healthy) or bool(restart_failures)
        migration_hint = ""
        if not post.healthy and any(svc == "postgresql" for svc in failing):
            migration_hint = " If issue persists, run ./dev migrate."

        return RemediationResult(
            action_type="restart_services",
            description="Restarted dependency services reported by backend readiness.",
            commands=commands,
            resolved=not unresolved,
            manual_step=(
                "Run ./dev status and ./dev logs backend."
                f"{migration_hint}"
                if unresolved
                else "No action required."
            ),
            details={
                "failing_services": failing,
                "targets": targets,
                "restart_failures": restart_failures,
                "post_check_summary": post.summary,
            },
        )

    def _remediate_db(self, result: CheckResult) -> RemediationResult:
        commands, restart_failures = self._restart_services(["postgres"])
        post = self._verify_resolution(result.name)
        unresolved = (not post.healthy) or bool(restart_failures)

        return RemediationResult(
            action_type="restart_db",
            description="Database remained unreachable after retries; restarted postgres service.",
            commands=commands,
            resolved=not unresolved,
            manual_step=(
                "Run ./dev logs infra. Do not auto-run migrations. If schema is behind, run ./dev migrate manually."
                if unresolved
                else "No action required."
            ),
            details={
                "restart_failures": restart_failures,
                "post_check_summary": post.summary,
                "original_summary": result.summary,
            },
        )
