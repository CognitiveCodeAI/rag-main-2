"""Parsers for monitor probe output."""

from __future__ import annotations

from typing import Any


def parse_docker_inspect_state(raw: str) -> tuple[str, str]:
    """Parse docker inspect state string in format '<state>|<health>'."""
    value = (raw or "").strip()
    if "|" not in value:
        return "unknown", "unknown"

    state, health = value.split("|", 1)
    state = state.strip().lower() or "unknown"
    health = health.strip().lower() or "unknown"
    return state, health


def parse_backend_health_payload(payload: dict[str, Any]) -> tuple[str, list[str], dict[str, str]]:
    """Extract overall status and failing services from backend health payload."""
    overall_status = str(payload.get("status", "unknown")).strip().lower()
    services_raw = payload.get("services") or {}
    service_statuses: dict[str, str] = {}
    failing_services: list[str] = []

    if isinstance(services_raw, dict):
        for name, detail in services_raw.items():
            status = "unknown"
            if isinstance(detail, dict):
                status = str(detail.get("status", "unknown")).strip().lower()
            service_statuses[name] = status
            if status not in {"healthy", "ok"}:
                failing_services.append(name)

    return overall_status, sorted(failing_services), service_statuses
