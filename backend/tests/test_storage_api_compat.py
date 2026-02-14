"""Compatibility tests for storage client method names."""

from app.storage.minio_client import StorageClient


def test_storage_client_selector_methods_remain_compatible():
    """Keep both selector existence method names for backward compatibility."""
    assert hasattr(StorageClient, "selectors_exist")
    assert hasattr(StorageClient, "selectors_exists")
