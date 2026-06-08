"""Unit tests for the OpenAI answer-call retry/backoff (D2 / audit H-3).

Pure unit tests: the client is mocked, no network or API key needed.
"""

from unittest.mock import MagicMock

import httpx
import pytest
from openai import RateLimitError

from app.llm.openai_client import OpenAIClient


def _make_client():
    client = OpenAIClient(api_key="test-key")
    client.RETRY_BASE_DELAY_S = 0  # no real sleeping in tests
    client.client = MagicMock()
    return client


def _rate_limit_error():
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(429, request=request)
    return RateLimitError("rate limited", response=response, body=None)


def test_retries_transient_error_then_succeeds():
    client = _make_client()
    inner = client.client.with_options.return_value
    sentinel = object()
    inner.responses.create.side_effect = [_rate_limit_error(), sentinel]

    result = client._responses_create_with_retry({"input": "hi"}, timeout_sec=5.0)

    assert result is sentinel
    assert inner.responses.create.call_count == 2  # one retry, then success


def test_gives_up_after_max_attempts():
    client = _make_client()
    inner = client.client.with_options.return_value
    inner.responses.create.side_effect = _rate_limit_error()

    with pytest.raises(RateLimitError):
        client._responses_create_with_retry({"input": "hi"}, timeout_sec=5.0)

    assert inner.responses.create.call_count == OpenAIClient.RETRY_ATTEMPTS


def test_non_retryable_error_raises_immediately():
    client = _make_client()
    inner = client.client.with_options.return_value
    inner.responses.create.side_effect = ValueError("boom")

    with pytest.raises(ValueError):
        client._responses_create_with_retry({"input": "hi"}, timeout_sec=5.0)

    assert inner.responses.create.call_count == 1  # no retry on non-transient
