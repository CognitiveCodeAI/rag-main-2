"""State persistence and dedupe/backoff behavior."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.monitor.types import GateDecision


def _default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "checks": {},
        "last_summary": {},
        "circuit_breakers": {},
    }


class MonitorStateStore:
    """JSON state storage for monitor suppression/backoff bookkeeping."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return _default_state()

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return _default_state()

        if not isinstance(data, dict):
            return _default_state()

        data.setdefault("version", 1)
        data.setdefault("checks", {})
        data.setdefault("last_summary", {})
        data.setdefault("circuit_breakers", {})
        return data

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.path)


class DedupeBackoffGate:
    """Emit incident events with dedupe + exponential backoff."""

    def __init__(
        self,
        state: dict[str, Any],
        backoff_seconds: int,
        max_backoff_seconds: int = 300,
    ):
        self.state = state
        self.backoff_seconds = max(1, backoff_seconds)
        self.max_backoff_seconds = max(1, max_backoff_seconds)

    def _entry(self, check_name: str) -> dict[str, Any]:
        checks = self.state.setdefault("checks", {})
        entry = checks.setdefault(
            check_name,
            {
                "active_failure": False,
                "failure_count": 0,
                "fingerprint": "",
                "last_emit_ts": 0.0,
                "next_emit_ts": 0.0,
                "suppressed_count": 0,
                "last_status": "unknown",
                "last_observed_ts": 0.0,
            },
        )
        return entry

    def _next_backoff_delay(self, failure_count: int) -> int:
        exponent = max(0, failure_count - 1)
        delay = self.backoff_seconds * int(math.pow(2, exponent))
        return min(delay, self.max_backoff_seconds)

    def evaluate(
        self,
        check_name: str,
        failing: bool,
        fingerprint: str,
        now_ts: float,
    ) -> GateDecision:
        entry = self._entry(check_name)
        entry["last_observed_ts"] = now_ts

        if not failing:
            if entry.get("active_failure"):
                failure_count = int(entry.get("failure_count", 0))
                suppressed_count = int(entry.get("suppressed_count", 0))
                entry.update(
                    {
                        "active_failure": False,
                        "failure_count": 0,
                        "fingerprint": "",
                        "last_emit_ts": now_ts,
                        "next_emit_ts": 0.0,
                        "suppressed_count": 0,
                        "last_status": "healthy",
                    }
                )
                return GateDecision(
                    emit=True,
                    event_kind="resolution",
                    failure_count=failure_count,
                    suppressed_count=suppressed_count,
                    next_emit_ts=0.0,
                    reason="recovered",
                )

            entry["last_status"] = "healthy"
            return GateDecision(
                emit=False,
                event_kind=None,
                failure_count=0,
                suppressed_count=0,
                next_emit_ts=0.0,
                reason="healthy",
            )

        # Failing path.
        entry["last_status"] = "unhealthy"
        active_failure = bool(entry.get("active_failure"))
        previous_fingerprint = str(entry.get("fingerprint", ""))
        failure_count = int(entry.get("failure_count", 0))

        if not active_failure:
            failure_count = 1
            delay = self._next_backoff_delay(failure_count)
            entry.update(
                {
                    "active_failure": True,
                    "failure_count": failure_count,
                    "fingerprint": fingerprint,
                    "last_emit_ts": now_ts,
                    "next_emit_ts": now_ts + delay,
                    "suppressed_count": 0,
                }
            )
            return GateDecision(
                emit=True,
                event_kind="detection",
                failure_count=failure_count,
                suppressed_count=0,
                next_emit_ts=entry["next_emit_ts"],
                reason="new_failure",
            )

        if fingerprint != previous_fingerprint:
            failure_count += 1
            delay = self._next_backoff_delay(failure_count)
            entry.update(
                {
                    "failure_count": failure_count,
                    "fingerprint": fingerprint,
                    "last_emit_ts": now_ts,
                    "next_emit_ts": now_ts + delay,
                    "suppressed_count": 0,
                }
            )
            return GateDecision(
                emit=True,
                event_kind="detection",
                failure_count=failure_count,
                suppressed_count=0,
                next_emit_ts=entry["next_emit_ts"],
                reason="diagnosis_changed",
            )

        next_emit_ts = float(entry.get("next_emit_ts", 0.0))
        if now_ts >= next_emit_ts:
            failure_count += 1
            delay = self._next_backoff_delay(failure_count)
            suppressed_count = int(entry.get("suppressed_count", 0))
            entry.update(
                {
                    "failure_count": failure_count,
                    "last_emit_ts": now_ts,
                    "next_emit_ts": now_ts + delay,
                    "suppressed_count": 0,
                }
            )
            return GateDecision(
                emit=True,
                event_kind="detection",
                failure_count=failure_count,
                suppressed_count=suppressed_count,
                next_emit_ts=entry["next_emit_ts"],
                reason="backoff_elapsed",
            )

        entry["suppressed_count"] = int(entry.get("suppressed_count", 0)) + 1
        return GateDecision(
            emit=False,
            event_kind=None,
            failure_count=failure_count,
            suppressed_count=int(entry["suppressed_count"]),
            next_emit_ts=next_emit_ts,
            reason="suppressed",
        )
