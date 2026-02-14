from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.eval.run_qa_eval import (  # noqa: E402
    _has_abstain_phrase,
    _is_abstain,
    check_evidence_grounded,
)


class _DummyQAResult:
    def __init__(self, packed_context: str):
        self.packed_context = packed_context


def test_check_evidence_grounded_matches_numeric_variants() -> None:
    qa_result = _DummyQAResult(
        packed_context="The estimated initial investment ranges from $425,100 to $899,000."
    )

    result = check_evidence_grounded(
        qa_result=qa_result,
        expected_keywords=[],
        expected_answer_contains=["425100", "899000"],
    )

    assert result.grounded is True
    assert result.passed is True


def test_is_abstain_detects_document_not_specified_language() -> None:
    answer = "The document does not specify an environmental compliance policy."
    assert _is_abstain(answer) is True


def test_is_abstain_detects_document_not_describe_language() -> None:
    answer = "The context does not describe a specific environmental compliance policy."
    assert _is_abstain(answer) is True


def test_has_abstain_phrase_detects_not_addressed_language() -> None:
    answer = "This topic is not addressed in the document text provided."
    assert _has_abstain_phrase(answer) is True
