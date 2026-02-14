"""Unit tests for monitor parser helpers."""

from app.monitor.parsers import parse_backend_health_payload, parse_docker_inspect_state


def test_parse_docker_inspect_state_running_healthy():
    state, health = parse_docker_inspect_state("running|healthy")
    assert state == "running"
    assert health == "healthy"


def test_parse_docker_inspect_state_invalid_payload():
    state, health = parse_docker_inspect_state("running healthy")
    assert state == "unknown"
    assert health == "unknown"


def test_parse_backend_health_payload_extracts_failures():
    payload = {
        "status": "degraded",
        "services": {
            "postgresql": {"status": "healthy"},
            "redis": {"status": "unhealthy"},
            "milvus": {"status": "unhealthy"},
        },
    }

    overall, failing, statuses = parse_backend_health_payload(payload)

    assert overall == "degraded"
    assert failing == ["milvus", "redis"]
    assert statuses["postgresql"] == "healthy"
