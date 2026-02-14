"""Monitor configuration loaded from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _to_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _to_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_repo_root() -> Path:
    """Resolve repository root from this module path."""
    # backend/app/monitor/config.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class MonitorConfig:
    """Runtime configuration for the active monitor."""

    enabled: bool
    mode: str
    dry_run: bool
    interval_seconds: int
    max_retries: int
    backoff_seconds: int
    circuit_breaker_threshold: int
    repo_root: Path
    compose_file: Path
    state_file: Path
    log_file: Path
    api_ready_url: str
    docker_services: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "MonitorConfig":
        repo_root = get_repo_root()
        mode = os.getenv("MONITOR_MODE", "observe").strip().lower()
        if mode not in {"observe", "heal"}:
            mode = "observe"

        default_services = (
            "postgres",
            "etcd",
            "minio-milvus",
            "milvus",
            "minio",
            "redis",
        )

        return cls(
            enabled=_to_bool(os.getenv("MONITOR_ENABLED"), False),
            mode=mode,
            dry_run=_to_bool(os.getenv("MONITOR_DRY_RUN"), False),
            interval_seconds=max(1, _to_int(os.getenv("MONITOR_INTERVAL_SECONDS"), 15)),
            max_retries=max(1, _to_int(os.getenv("MONITOR_MAX_RETRIES"), 3)),
            backoff_seconds=max(1, _to_int(os.getenv("MONITOR_BACKOFF_SECONDS"), 10)),
            circuit_breaker_threshold=max(
                1, _to_int(os.getenv("MONITOR_CIRCUIT_BREAKER_THRESHOLD"), 5)
            ),
            repo_root=repo_root,
            compose_file=repo_root / "docker-compose.yml",
            state_file=repo_root / ".monitor_state.json",
            log_file=repo_root / "logs" / "monitor.jsonl",
            api_ready_url=os.getenv("MONITOR_API_READY_URL", "http://localhost:8000/health/ready"),
            docker_services=default_services,
        )
