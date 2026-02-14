"""Health probes for critical local services."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

from app.monitor.config import MonitorConfig
from app.monitor.parsers import parse_backend_health_payload, parse_docker_inspect_state
from app.monitor.types import CheckResult


def _stable_fingerprint(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(body).hexdigest()[:16]


def run_command(
    cmd: list[str],
    timeout_seconds: int = 15,
    cwd: str | None = None,
) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=cwd,
        )
        return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"command timed out after {timeout_seconds}s"


def resolve_compose_cmd(compose_file: str) -> list[str] | None:
    commands = (["docker", "compose"], ["docker-compose"])
    for candidate in commands:
        rc, _, _ = run_command([*candidate, "version"], timeout_seconds=10)
        if rc == 0:
            return [*candidate, "-f", compose_file]
    return None


def _build_database_url() -> tuple[str, dict[str, str]]:
    explicit_url = os.getenv("DATABASE_URL", "").strip()
    if explicit_url:
        return explicit_url, {"source": "DATABASE_URL"}

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    database = os.getenv("DB_NAME", "ragdb")
    user = os.getenv("DB_USER", "raguser")
    password = quote_plus(os.getenv("DB_PASSWORD", "ragpass"))
    url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return url, {"host": host, "port": port, "database": database, "user": user}


class MonitorChecks:
    """Probe runner for monitor checks."""

    def __init__(self, config: MonitorConfig):
        self.config = config
        self.compose_cmd = resolve_compose_cmd(str(config.compose_file))

    def run_all(self) -> list[CheckResult]:
        return [
            self.check_infra_containers(),
            self.check_api_ready(),
            self.check_db_connectivity(),
        ]

    def run_check(self, check_name: str) -> CheckResult:
        if check_name == "infra_containers":
            return self.check_infra_containers()
        if check_name == "api_readiness":
            return self.check_api_ready()
        if check_name == "db_connectivity":
            return self.check_db_connectivity()
        raise ValueError(f"Unknown check name: {check_name}")

    def check_infra_containers(self) -> CheckResult:
        name = "infra_containers"
        diagnosis: dict[str, Any] = {
            "compose_available": self.compose_cmd is not None,
            "services": {},
            "failures": {},
        }

        if self.compose_cmd is None:
            summary = "Docker compose command unavailable"
            diagnosis["failures"]["compose"] = "docker compose command not found"
            return CheckResult(
                name=name,
                healthy=False,
                summary=summary,
                diagnosis=diagnosis,
                next_step="Install/enable Docker Compose and run ./dev doctor.",
                fingerprint=_stable_fingerprint(diagnosis),
            )

        for service in self.config.docker_services:
            rc, stdout, stderr = run_command(
                [*self.compose_cmd, "ps", "-q", service],
                timeout_seconds=10,
            )
            if rc != 0:
                diagnosis["failures"][service] = stderr or stdout or "compose query failed"
                continue

            container_id = stdout.strip()
            if not container_id:
                diagnosis["failures"][service] = "container missing/not running"
                continue

            rc, inspect_out, inspect_err = run_command(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
                    container_id,
                ],
                timeout_seconds=10,
            )
            if rc != 0:
                diagnosis["failures"][service] = inspect_err or inspect_out or "docker inspect failed"
                continue

            state, health = parse_docker_inspect_state(inspect_out)
            diagnosis["services"][service] = {"state": state, "health": health}
            if state != "running":
                diagnosis["failures"][service] = f"state={state}"
            elif health not in {"healthy", "none"}:
                diagnosis["failures"][service] = f"health={health}"

        failures = diagnosis["failures"]
        if failures:
            summary = f"Infrastructure issues detected in {len(failures)} service(s)"
            healthy = False
        else:
            summary = "Infrastructure containers are running and healthy"
            healthy = True

        return CheckResult(
            name=name,
            healthy=healthy,
            summary=summary,
            diagnosis=diagnosis,
            next_step="Run ./dev logs infra and inspect docker compose ps output.",
            fingerprint=_stable_fingerprint(diagnosis),
        )

    def check_api_ready(self) -> CheckResult:
        name = "api_readiness"
        diagnosis: dict[str, Any] = {
            "url": self.config.api_ready_url,
            "http_status": None,
            "overall_status": "unknown",
            "service_statuses": {},
            "failing_services": [],
        }
        try:
            with urllib.request.urlopen(self.config.api_ready_url, timeout=8) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
                diagnosis["http_status"] = response.status
        except urllib.error.HTTPError as exc:
            diagnosis["http_status"] = exc.code
            diagnosis["error"] = f"http error: {exc}"
            summary = f"Backend readiness endpoint failed with HTTP {exc.code}"
            return CheckResult(
                name=name,
                healthy=False,
                summary=summary,
                diagnosis=diagnosis,
                next_step="Run ./dev logs backend and check /health/ready output.",
                fingerprint=_stable_fingerprint(diagnosis),
            )
        except Exception as exc:  # pragma: no cover - defensive path
            diagnosis["error"] = str(exc)
            summary = "Backend readiness endpoint unreachable"
            return CheckResult(
                name=name,
                healthy=False,
                summary=summary,
                diagnosis=diagnosis,
                next_step="Ensure backend is running (./dev up) and re-check ./dev status.",
                fingerprint=_stable_fingerprint(diagnosis),
            )

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            diagnosis["raw_body"] = raw_body[:300]
            summary = "Backend readiness returned non-JSON payload"
            return CheckResult(
                name=name,
                healthy=False,
                summary=summary,
                diagnosis=diagnosis,
                next_step="Inspect backend logs for /health/ready serialization errors.",
                fingerprint=_stable_fingerprint(diagnosis),
            )

        overall_status, failing_services, service_statuses = parse_backend_health_payload(payload)
        diagnosis["overall_status"] = overall_status
        diagnosis["service_statuses"] = service_statuses
        diagnosis["failing_services"] = failing_services
        diagnosis["config_warnings"] = payload.get("config_warnings", [])

        healthy = overall_status in {"healthy", "ok"} and len(failing_services) == 0
        if healthy:
            summary = "Backend readiness is healthy"
        else:
            summary = "Backend readiness degraded"

        return CheckResult(
            name=name,
            healthy=healthy,
            summary=summary,
            diagnosis=diagnosis,
            next_step="Run ./dev status and inspect backend dependency failures.",
            fingerprint=_stable_fingerprint(diagnosis),
        )

    def check_db_connectivity(self) -> CheckResult:
        name = "db_connectivity"
        url, db_meta = _build_database_url()
        started = time.perf_counter()
        diagnosis: dict[str, Any] = {
            "db_meta": db_meta,
            "query": "SELECT 1",
            "latency_ms": None,
        }
        engine = None

        try:
            engine = create_engine(url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            elapsed = (time.perf_counter() - started) * 1000
            diagnosis["latency_ms"] = round(elapsed, 2)
            return CheckResult(
                name=name,
                healthy=True,
                summary="PostgreSQL connectivity check passed",
                diagnosis=diagnosis,
                next_step="No action required.",
                fingerprint=_stable_fingerprint(diagnosis),
            )
        except Exception as exc:
            diagnosis["error"] = str(exc)
            return CheckResult(
                name=name,
                healthy=False,
                summary="PostgreSQL connectivity check failed",
                diagnosis=diagnosis,
                next_step="Run ./dev logs infra and verify PostgreSQL credentials/connectivity.",
                fingerprint=_stable_fingerprint(diagnosis),
            )
        finally:
            if engine is not None:
                engine.dispose()
