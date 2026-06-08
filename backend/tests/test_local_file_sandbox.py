"""Unit tests for the file:// path-traversal sandbox (C4 / audit H-8)."""

import os

from app.routes.documents import _resolve_sandboxed_local_path


def test_disabled_when_no_root_configured():
    assert _resolve_sandboxed_local_path("file:///etc/passwd", "") is None


def test_rejects_path_outside_root(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    # A real file that exists but is outside the allowed root.
    outside = tmp_path / "secret.txt"
    outside.write_text("nope")
    assert _resolve_sandboxed_local_path(f"file://{outside}", str(root)) is None


def test_rejects_traversal_escape(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")
    # ../secret.txt from inside root escapes the sandbox.
    traversal = f"file://{root}/../secret.txt"
    assert _resolve_sandboxed_local_path(traversal, str(root)) is None


def test_allows_file_inside_root(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    f = root / "report.pdf"
    f.write_bytes(b"%PDF-1.4")
    resolved = _resolve_sandboxed_local_path(f"file://{f}", str(root))
    assert resolved == os.path.realpath(str(f))


def test_missing_file_returns_none(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    missing = root / "nope.pdf"
    assert _resolve_sandboxed_local_path(f"file://{missing}", str(root)) is None
