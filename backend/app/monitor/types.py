"""Shared monitor data structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    """Result of a monitor check."""

    name: str
    healthy: bool
    summary: str
    diagnosis: dict[str, Any]
    next_step: str
    fingerprint: str


@dataclass(frozen=True)
class GateDecision:
    """Decision from dedupe/backoff state machine."""

    emit: bool
    event_kind: str | None
    failure_count: int
    suppressed_count: int
    next_emit_ts: float
    reason: str


@dataclass(frozen=True)
class RemediationResult:
    """Result from a heal-mode remediation attempt."""

    action_type: str
    description: str
    commands: list[str]
    resolved: bool
    manual_step: str
    details: dict[str, Any]
