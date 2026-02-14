"""Integration smoke test for OpenAI Responses API client.

This test is optional and skips cleanly when OPENAI_API_KEY is not configured.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


pytestmark = pytest.mark.integration


def _load_env() -> None:
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path, override=False)


def _require_openai_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not configured; skipping OpenAI integration test")


def test_openai_responses_api_smoke():
    """Verify OpenAI client can generate an answer with citations."""
    _load_env()
    _require_openai_key()

    from app.llm.openai_client import OpenAIClient

    client = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))

    context = (
        "The study examined the effects of temperature on plant growth. "
        "Results showed plants grew best at 22C [study_001:3]. "
        "Figure 1 [Figure 1:4] illustrates the growth patterns."
    )
    question = "What temperature is best for plant growth?"

    result = client.generate_answer(context=context, question=question)

    assert result.answer
    assert isinstance(result.citations, list)
    assert result.model_id
    assert result.total_tokens >= 0
