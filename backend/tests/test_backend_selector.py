"""Unit tests for backend_selector.resolve_backend()."""

import unittest
from unittest.mock import patch, MagicMock


def _make_settings(**overrides):
    """Create a mock settings object with defaults."""
    defaults = {
        "docling_enabled_default": False,
        "docling_mode": "off",
        "docling_max_pages": 200,
        "docling_max_file_size_mb": 100,
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


class TestResolveBackend(unittest.TestCase):
    """Tests for resolve_backend()."""

    def _call(self, source_type, request_override=None, **settings_kwargs):
        settings = _make_settings(**settings_kwargs)
        with patch("app.graph.backend_selector.get_settings", return_value=settings):
            from app.graph.backend_selector import resolve_backend
            return resolve_backend(source_type=source_type, request_override=request_override)

    # --- docling_mode="off" always returns native ---

    def test_mode_off_pdf(self):
        result = self._call("pdf", docling_enabled_default=True, docling_mode="off")
        self.assertEqual(result, "native")

    def test_mode_off_docx(self):
        result = self._call("docx", docling_enabled_default=True, docling_mode="off")
        self.assertEqual(result, "native")

    # --- docling_mode="non_pdf_only" ---

    def test_non_pdf_only_pdf_returns_native(self):
        result = self._call("pdf", docling_enabled_default=True, docling_mode="non_pdf_only")
        self.assertEqual(result, "native")

    def test_non_pdf_only_docx_returns_docling(self):
        result = self._call("docx", docling_enabled_default=True, docling_mode="non_pdf_only")
        self.assertEqual(result, "docling")

    def test_non_pdf_only_pptx_returns_docling(self):
        result = self._call("pptx", docling_enabled_default=True, docling_mode="non_pdf_only")
        self.assertEqual(result, "docling")

    def test_non_pdf_only_xlsx_returns_docling(self):
        result = self._call("xlsx", docling_enabled_default=True, docling_mode="non_pdf_only")
        self.assertEqual(result, "docling")

    # --- docling_mode="all" ---

    def test_mode_all_pdf_returns_docling(self):
        result = self._call("pdf", docling_enabled_default=True, docling_mode="all")
        self.assertEqual(result, "docling")

    def test_mode_all_docx_returns_docling(self):
        result = self._call("docx", docling_enabled_default=True, docling_mode="all")
        self.assertEqual(result, "docling")

    # --- Unsupported source type ---

    def test_unsupported_source_type_returns_native(self):
        result = self._call("xyz", docling_enabled_default=True, docling_mode="all")
        self.assertEqual(result, "native")

    # --- docling_enabled_default=False ---

    def test_disabled_returns_native(self):
        result = self._call("docx", docling_enabled_default=False, docling_mode="all")
        self.assertEqual(result, "native")

    # --- Request overrides ---

    def test_request_override_native_always_wins(self):
        result = self._call(
            "docx", request_override="native",
            docling_enabled_default=True, docling_mode="all"
        )
        self.assertEqual(result, "native")

    def test_request_override_docling_with_enabled(self):
        result = self._call(
            "pdf", request_override="docling",
            docling_enabled_default=True, docling_mode="non_pdf_only"
        )
        self.assertEqual(result, "docling")

    def test_request_override_docling_with_disabled_falls_back(self):
        """Request asks for docling but it's disabled globally → native."""
        result = self._call(
            "docx", request_override="docling",
            docling_enabled_default=False, docling_mode="off"
        )
        self.assertEqual(result, "native")

    def test_request_override_docling_unsupported_type_falls_back(self):
        result = self._call(
            "xyz", request_override="docling",
            docling_enabled_default=True, docling_mode="all"
        )
        self.assertEqual(result, "native")

    # --- No override, no enabled → native ---

    def test_default_returns_native(self):
        result = self._call("pdf")
        self.assertEqual(result, "native")


if __name__ == "__main__":
    unittest.main()
