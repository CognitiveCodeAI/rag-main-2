"""Monitor runner with observe and safe-heal modes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from app.monitor.checks import MonitorChecks
from app.monitor.config import MonitorConfig
from app.monitor.jsonl_logger import JsonlEventLogger
from app.monitor.remediation import HealRemediator
from app.monitor.state import DedupeBackoffGate, MonitorStateStore
from app.monitor.types import CheckResult, RemediationResult


@dataclass(frozen=True)
class CycleSummary:
    """Result summary of one observe cycle."""

    timestamp: str
    check_results: list[CheckResult]
    emitted_events: int
    event_details: list[dict[str, str]]


class MonitorObserver:
    """Monitor with dedupe/backoff incident logging and optional healing."""

    def __init__(
        self,
        config: MonitorConfig,
        checks: MonitorChecks | None = None,
        remediator: HealRemediator | None = None,
        now_provider: Any | None = None,
    ):
        self.config = config
        self.checks = checks or MonitorChecks(config)
        self.state_store = MonitorStateStore(config.state_file)
        self.state = self.state_store.load()
        self.gate = DedupeBackoffGate(
            self.state,
            backoff_seconds=config.backoff_seconds,
        )
        self.event_logger = JsonlEventLogger(config.log_file)
        self.remediator = remediator or HealRemediator(config=config, checks=self.checks)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _internal_failure_result(where: str, exc: Exception) -> CheckResult:
        payload = {"where": where, "error": str(exc), "error_type": type(exc).__name__}
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return CheckResult(
            name=f"monitor_internal_{where}",
            healthy=False,
            summary=f"Monitor internal error while executing {where}",
            diagnosis=payload,
            next_step="Inspect logs/monitor.jsonl and monitor daemon logs.",
            fingerprint=fingerprint,
        )

    def _circuit_entry(self, check_name: str) -> dict[str, Any]:
        breakers = self.state.setdefault("circuit_breakers", {})
        return breakers.setdefault(
            check_name,
            {
                "engaged": False,
                "engaged_at": None,
                "reason": "",
                "failure_count": 0,
            },
        )

    def _engage_circuit(self, check_name: str, failure_count: int, now_iso: str, reason: str) -> None:
        entry = self._circuit_entry(check_name)
        entry["engaged"] = True
        entry["engaged_at"] = now_iso
        entry["reason"] = reason
        entry["failure_count"] = failure_count

    def _clear_circuit(self, check_name: str) -> None:
        entry = self._circuit_entry(check_name)
        entry["engaged"] = False
        entry["engaged_at"] = None
        entry["reason"] = ""
        entry["failure_count"] = 0

    def _is_circuit_engaged(self, check_name: str) -> bool:
        return bool(self._circuit_entry(check_name).get("engaged"))

    def _build_event_payload(
        self,
        result: CheckResult,
        event_kind: str,
        now_iso: str,
        decision: dict[str, Any],
        action_payload: dict[str, Any],
        outcome_status: str,
        next_manual_step: str,
    ) -> dict[str, Any]:
        return {
            "timestamp": now_iso,
            "event_type": f"incident_{event_kind}",
            "monitor_mode": "heal" if self.config.mode == "heal" else "observe",
            "requested_mode": self.config.mode,
            "dry_run": self.config.dry_run,
            "check": result.name,
            "detection": {
                "what_failed": result.summary,
                "when": now_iso,
                "check_failed": not result.healthy,
            },
            "diagnosis": result.diagnosis,
            "action": action_payload,
            "outcome": {
                "status": outcome_status,
            },
            "next_recommended_manual_step": next_manual_step,
            "dedupe": {
                "failure_count": decision["failure_count"],
                "suppressed_count": decision["suppressed_count"],
                "next_emit_ts": decision["next_emit_ts"],
                "reason": decision["reason"],
            },
        }

    def run_cycle(self) -> CycleSummary:
        now = self.now_provider()
        now_iso = now.isoformat()
        now_ts = now.timestamp()
        emitted_events = 0
        event_details: list[dict[str, str]] = []

        try:
            check_results = self.checks.run_all()
        except Exception as exc:  # pragma: no cover - fail-safe path
            check_results = [self._internal_failure_result("checks", exc)]
        last_summary = self.state.setdefault("last_summary", {})

        for result in check_results:
            gate_decision = self.gate.evaluate(
                check_name=result.name,
                failing=not result.healthy,
                fingerprint=result.fingerprint,
                now_ts=now_ts,
            )

            last_summary[result.name] = {
                "healthy": result.healthy,
                "summary": result.summary,
                "last_checked_ts": now_ts,
                "last_checked_at": now_iso,
            }

            if gate_decision.emit and gate_decision.event_kind is not None:
                action_payload = {
                    "type": "none",
                    "description": "Observe mode only; no automated remediation executed.",
                }
                outcome_status = "resolved" if gate_decision.event_kind == "resolution" else "unresolved"
                next_manual_step = (
                    "No action required."
                    if gate_decision.event_kind == "resolution"
                    else result.next_step
                )

                if gate_decision.event_kind == "resolution":
                    self._clear_circuit(result.name)
                elif self.config.mode == "heal":
                    if self._is_circuit_engaged(result.name):
                        action_payload = {
                            "type": "circuit_breaker_skip",
                            "description": "Circuit breaker engaged; auto-remediation skipped.",
                            "commands": [],
                        }
                        next_manual_step = (
                            "Manual intervention required. Review logs/monitor.jsonl and run ./dev doctor."
                        )
                    elif gate_decision.failure_count >= self.config.circuit_breaker_threshold:
                        self._engage_circuit(
                            check_name=result.name,
                            failure_count=gate_decision.failure_count,
                            now_iso=now_iso,
                            reason="failure_threshold_exceeded",
                        )
                        action_payload = {
                            "type": "circuit_breaker_engaged",
                            "description": (
                                "Auto-remediation paused after repeated failures "
                                f"({gate_decision.failure_count} >= "
                                f"{self.config.circuit_breaker_threshold})."
                            ),
                            "commands": [],
                        }
                        next_manual_step = (
                            "Manual intervention required. Resolve root cause, then run monitor again."
                        )
                    else:
                        try:
                            remediation: RemediationResult = self.remediator.remediate(result)
                        except Exception as exc:  # pragma: no cover - fail-safe path
                            remediation = RemediationResult(
                                action_type="remediation_error",
                                description=f"Auto-remediation failed with error: {exc}",
                                commands=[],
                                resolved=False,
                                manual_step=(
                                    "Manual intervention required. Inspect monitor logs and run ./dev doctor."
                                ),
                                details={
                                    "error": str(exc),
                                    "error_type": type(exc).__name__,
                                },
                            )
                        action_payload = {
                            "type": remediation.action_type,
                            "description": remediation.description,
                            "commands": remediation.commands,
                            "details": remediation.details,
                        }
                        outcome_status = "resolved" if remediation.resolved else "unresolved"
                        next_manual_step = remediation.manual_step

                event_payload = self._build_event_payload(
                    result=result,
                    event_kind=gate_decision.event_kind,
                    now_iso=now_iso,
                    decision={
                        "failure_count": gate_decision.failure_count,
                        "suppressed_count": gate_decision.suppressed_count,
                        "next_emit_ts": gate_decision.next_emit_ts,
                        "reason": gate_decision.reason,
                    },
                    action_payload=action_payload,
                    outcome_status=outcome_status,
                    next_manual_step=next_manual_step,
                )
                self.event_logger.log(event_payload)
                emitted_events += 1
                commands = action_payload.get("commands", [])
                command_preview = ""
                if isinstance(commands, list) and commands:
                    command_preview = ",".join(commands[:2])
                event_details.append(
                    {
                        "check": result.name,
                        "event_kind": gate_decision.event_kind,
                        "action_type": str(action_payload.get("type", "none")),
                        "outcome": outcome_status,
                        "command_preview": command_preview,
                    }
                )

        self.state["last_cycle_ts"] = now_ts
        self.state["last_cycle_iso"] = now_iso
        self.state_store.save(self.state)

        return CycleSummary(
            timestamp=now_iso,
            check_results=check_results,
            emitted_events=emitted_events,
            event_details=event_details,
        )

    @staticmethod
    def format_cycle_summary(cycle: CycleSummary) -> str:
        parts = []
        for check in cycle.check_results:
            status = "ok" if check.healthy else "fail"
            parts.append(f"{check.name}={status}")
        statuses = " ".join(parts)
        base = (
            f"[monitor] {cycle.timestamp} {statuses} "
            f"events_emitted={cycle.emitted_events}"
        )
        if not cycle.event_details:
            return base

        details = []
        for event in cycle.event_details:
            segment = (
                f"{event['check']}:{event['event_kind']}:{event['action_type']}:"
                f"{event['outcome']}"
            )
            if event.get("command_preview"):
                segment = f"{segment}({event['command_preview']})"
            details.append(segment)
        return f"{base} actions={' ; '.join(details)}"

    def status_snapshot(self, run_live_checks: bool = True) -> dict[str, Any]:
        # Refresh on-disk state so status can be called from a separate process.
        self.state = self.state_store.load()
        if run_live_checks:
            try:
                live_checks = self.checks.run_all()
            except Exception as exc:  # pragma: no cover - fail-safe path
                live_checks = [self._internal_failure_result("status_checks", exc)]
        else:
            live_checks = []

        active_incidents: dict[str, Any] = {}
        for name, entry in self.state.get("checks", {}).items():
            if entry.get("active_failure"):
                active_incidents[name] = {
                    "failure_count": entry.get("failure_count", 0),
                    "suppressed_count": entry.get("suppressed_count", 0),
                    "next_emit_ts": entry.get("next_emit_ts", 0.0),
                }

        return {
            "enabled": self.config.enabled,
            "mode": self.config.mode,
            "effective_mode": "heal" if self.config.mode == "heal" else "observe",
            "dry_run": self.config.dry_run,
            "state_file": str(self.config.state_file),
            "log_file": str(self.config.log_file),
            "last_cycle_iso": self.state.get("last_cycle_iso"),
            "active_incidents": active_incidents,
            "circuit_breakers": self.state.get("circuit_breakers", {}),
            "live_checks": [
                {
                    "name": check.name,
                    "healthy": check.healthy,
                    "summary": check.summary,
                }
                for check in live_checks
            ],
        }

    @staticmethod
    def format_status(snapshot: dict[str, Any]) -> str:
        lines = [
            f"monitor_enabled={snapshot['enabled']}",
            f"configured_mode={snapshot['mode']}",
            f"effective_mode={snapshot['effective_mode']}",
            f"dry_run={snapshot['dry_run']}",
            f"state_file={snapshot['state_file']}",
            f"log_file={snapshot['log_file']}",
            f"last_cycle={snapshot.get('last_cycle_iso') or 'never'}",
        ]

        active_incidents = snapshot.get("active_incidents", {})
        lines.append(f"active_incidents={len(active_incidents)}")
        for name, detail in active_incidents.items():
            lines.append(
                f"  - {name}: failures={detail['failure_count']} "
                f"suppressed={detail['suppressed_count']}"
            )

        circuit_breakers = snapshot.get("circuit_breakers", {})
        engaged = [
            (name, detail)
            for name, detail in circuit_breakers.items()
            if isinstance(detail, dict) and detail.get("engaged")
        ]
        lines.append(f"engaged_circuit_breakers={len(engaged)}")
        for name, detail in engaged:
            lines.append(
                f"  - {name}: failure_count={detail.get('failure_count', 0)} "
                f"reason={detail.get('reason', 'unknown')}"
            )

        live_checks = snapshot.get("live_checks", [])
        if live_checks:
            lines.append("live_checks:")
            for check in live_checks:
                status = "ok" if check["healthy"] else "fail"
                lines.append(f"  - {check['name']}: {status} ({check['summary']})")

        return "\n".join(lines)
