"""Pytest configuration for deterministic local test runs.

By default, tests that require external infrastructure (e.g. Neo4j/OpenSearch/
OpenAI/Ollama or full end-to-end flows) are skipped unless explicitly enabled
with RUN_INTEGRATION_TESTS=1.
"""

import os
from pathlib import Path

import pytest


INTEGRATION_TEST_FILES = {
    "test_acl_canary.py",
    "test_acl_e2e.py",
    "test_all_connections.py",
    "test_embedding_e2e.py",
    "test_evidence_chain_integration.py",
    "test_graph_e2e.py",
    "test_graph_rag.py",
    "test_ingestion_e2e.py",
    "test_metadata_e2e.py",
    "test_milvus_connection.py",
    "test_milvus_flush.py",
    "test_minio_connection.py",
    "test_neo4j_connection.py",
    "test_ocr_golden.py",
    "test_ocr_smoke.py",
    "test_ollama_connection.py",
    "test_openai_connection.py",
    "test_openai_responses_api.py",
    "test_opensearch_connection.py",
    "test_postgres_connection.py",
}


def _env_truthy(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def pytest_configure(config):
    """Register custom markers used by this repository."""
    config.addinivalue_line(
        "markers",
        "integration: tests requiring external services or full end-to-end runtime",
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless explicitly enabled by environment flag."""
    if _env_truthy("RUN_INTEGRATION_TESTS"):
        return

    skip_integration = pytest.mark.skip(
        reason="Integration test skipped by default. Set RUN_INTEGRATION_TESTS=1 to run."
    )

    for item in items:
        filename = Path(str(item.fspath)).name
        if filename in INTEGRATION_TEST_FILES:
            item.add_marker("integration")
            item.add_marker(skip_integration)
