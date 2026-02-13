from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.eval.benchmark_contract import (
    ContractRunInfo,
    ContractValidationError,
    enforce_qa_benchmark_contract,
    enforce_retrieval_benchmark_contract,
    enforce_report_contract_stamp,
)


EVAL_DIR = Path(__file__).parent
CONTRACT_PATH = EVAL_DIR / "benchmark_contract.json"


def test_qa_contract_allows_standard_defaults() -> None:
    info = enforce_qa_benchmark_contract(
        mode="standard",
        dataset_path=str(EVAL_DIR / "golden_questions.json"),
        top_k=5,
        doc_path_override_provided=False,
        contract_path=str(CONTRACT_PATH),
    )
    assert info.contract_id == "rag_eval_contract"
    assert info.mode == "standard"


def test_qa_contract_rejects_top_k_drift() -> None:
    with pytest.raises(ContractValidationError, match="top_k=6"):
        enforce_qa_benchmark_contract(
            mode="standard",
            dataset_path=str(EVAL_DIR / "golden_questions.json"),
            top_k=6,
            doc_path_override_provided=False,
            contract_path=str(CONTRACT_PATH),
        )


def test_retrieval_contract_rejects_subset_runs() -> None:
    with pytest.raises(ContractValidationError, match="subset"):
        enforce_retrieval_benchmark_contract(
            query_subset_requested=True,
            contract_path=str(CONTRACT_PATH),
        )


def test_report_contract_stamp_required_without_contract() -> None:
    """When require_report_contract_stamp is true, None contract should fail."""
    with pytest.raises(ContractValidationError, match="stamp is required"):
        enforce_report_contract_stamp(
            contract=None,
            contract_path=str(CONTRACT_PATH),
        )


def test_report_contract_stamp_passes_with_contract() -> None:
    """When contract is provided, enforcement should pass."""
    mock_contract = ContractRunInfo(
        contract_id="test",
        contract_version="1.0.0",
        contract_path=str(CONTRACT_PATH),
        contract_sha256="abc123",
        mode="standard",
    )
    # Should not raise
    enforce_report_contract_stamp(
        contract=mock_contract,
        contract_path=str(CONTRACT_PATH),
    )
