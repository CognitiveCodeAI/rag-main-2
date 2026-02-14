"""Unit tests for OpenAIOCRClient timeout/error behavior."""

from types import SimpleNamespace

import pytest

from app.ocr.openai_client import OCRError, OpenAIOCRClient


class _FakeResponses:
    def __init__(self, should_raise: bool = False):
        self.should_raise = should_raise
        self.last_payload = None

    def create(self, **kwargs):
        self.last_payload = kwargs
        if self.should_raise:
            raise RuntimeError("boom")
        return SimpleNamespace(output_text="OCR text")


class _FakeClientWithOptions:
    def __init__(self, responses: _FakeResponses):
        self.responses = responses


class _FakeOpenAI:
    def __init__(self, should_raise: bool = False):
        self.responses_impl = _FakeResponses(should_raise=should_raise)
        self.last_timeout = None
        self.with_opts = _FakeClientWithOptions(self.responses_impl)

    def with_options(self, **kwargs):
        self.last_timeout = kwargs.get("timeout")
        return self.with_opts


def test_openai_ocr_uses_configured_timeout(monkeypatch):
    fake = _FakeOpenAI()
    monkeypatch.setattr("app.ocr.openai_client.OpenAI", lambda: fake)

    client = OpenAIOCRClient(timeout=17)
    result = client.ocr_full_page(image_bytes=b"fake-image", doc_id="doc-1", page_no=1)

    assert result == "OCR text"
    assert fake.last_timeout is not None
    assert fake.responses_impl.last_payload is not None
    assert fake.responses_impl.last_payload["model"] == client.model


def test_openai_ocr_raises_oc_error_on_failure(monkeypatch):
    fake = _FakeOpenAI(should_raise=True)
    monkeypatch.setattr("app.ocr.openai_client.OpenAI", lambda: fake)

    client = OpenAIOCRClient(timeout=5)
    with pytest.raises(OCRError):
        client.ocr_full_page(image_bytes=b"fake-image", doc_id="doc-1", page_no=2)
