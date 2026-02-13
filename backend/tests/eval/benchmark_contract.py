"""Contract validation for benchmark/evaluation runs.

This module enforces a versioned benchmark contract before running evals.
It protects claim validity by freezing datasets and run-critical settings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONTRACT_PATH = Path(__file__).parent / "benchmark_contract.json"


class ContractValidationError(ValueError):
    """Raised when a run violates the benchmark contract."""


@dataclass(frozen=True)
class ContractRunInfo:
    """Resolved benchmark contract metadata for a single run."""

    contract_id: str
    contract_version: str
    contract_path: str
    contract_sha256: str
    mode: str


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_existing_path(path_str: str) -> Path:
    raw = Path(path_str).expanduser()
    candidates = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.extend(
            [
                (Path.cwd() / raw),
                (REPO_ROOT / raw),
                (Path(__file__).parent / raw),
            ]
        )

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved

    raise ContractValidationError(
        f"Path does not exist: {path_str}. Checked: {', '.join(str(c.resolve()) for c in candidates)}"
    )


def _load_contract(contract_path: Optional[str]) -> tuple[Dict[str, Any], Path]:
    path = DEFAULT_CONTRACT_PATH if not contract_path else _resolve_existing_path(contract_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ContractValidationError(f"Invalid contract JSON at {path}: {e}") from e

    for key in ("contract_id", "version", "global_constraints", "modes"):
        if key not in data:
            raise ContractValidationError(f"Contract missing required key: {key}")

    if not isinstance(data["modes"], dict) or not data["modes"]:
        raise ContractValidationError("Contract must define at least one mode under 'modes'")

    return data, path


def _enforce_top_k(contract: Dict[str, Any], top_k: int) -> None:
    allowed = contract.get("global_constraints", {}).get("allowed_top_k")
    if allowed and top_k not in allowed:
        raise ContractValidationError(
            f"top_k={top_k} violates contract. Allowed values: {allowed}"
        )


def _resolve_mode(contract: Dict[str, Any], mode: str) -> Dict[str, Any]:
    mode_cfg = contract["modes"].get(mode)
    if mode_cfg is None:
        raise ContractValidationError(f"Unknown contract mode: {mode}")
    if not isinstance(mode_cfg, dict):
        raise ContractValidationError(f"Contract mode '{mode}' must be an object")
    return mode_cfg


def _enforce_dataset_contract(
    mode_cfg: Dict[str, Any],
    dataset_path: Path,
    doc_path_override_provided: bool,
) -> None:
    expected_dataset = mode_cfg.get("dataset_path")
    if expected_dataset:
        expected_dataset_path = (REPO_ROOT / expected_dataset).resolve()
        if not mode_cfg.get("allow_question_file_override", False) and dataset_path.resolve() != expected_dataset_path:
            raise ContractValidationError(
                f"Dataset override blocked by contract. Expected {expected_dataset_path}, got {dataset_path.resolve()}"
            )

        expected_dataset_hash = mode_cfg.get("dataset_sha256")
        if expected_dataset_hash:
            actual_hash = _sha256_file(dataset_path.resolve())
            if actual_hash != expected_dataset_hash:
                raise ContractValidationError(
                    f"Dataset hash mismatch for {dataset_path.resolve()}. Expected {expected_dataset_hash}, got {actual_hash}"
                )

    if doc_path_override_provided and not mode_cfg.get("allow_doc_path_override", False):
        raise ContractValidationError("doc_path override is disabled by contract for this mode")

    required_questions = mode_cfg.get("required_question_count")
    if required_questions is not None:
        try:
            data = json.loads(dataset_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ContractValidationError(f"Dataset JSON parse failed: {dataset_path}: {e}") from e
        count = len(data.get("questions", []))
        if count != required_questions:
            raise ContractValidationError(
                f"Question count mismatch for {dataset_path}. Expected {required_questions}, got {count}"
            )


def _build_run_info(contract: Dict[str, Any], contract_path: Path, mode: str) -> ContractRunInfo:
    return ContractRunInfo(
        contract_id=str(contract["contract_id"]),
        contract_version=str(contract["version"]),
        contract_path=str(contract_path.resolve()),
        contract_sha256=_sha256_file(contract_path.resolve()),
        mode=mode,
    )


def enforce_report_contract_stamp(
    contract: Optional[ContractRunInfo],
    contract_path: Optional[str] = None,
) -> None:
    """Enforce that report includes contract stamp if required by contract.

    Call this when generating a report to ensure `require_report_contract_stamp`
    constraint is honored. Raises ContractValidationError if stamp is required
    but no contract info was provided for the run.

    Args:
        contract: ContractRunInfo from the run, or None if no contract was used
        contract_path: Path to contract file to check constraint (uses default if None)
    """
    contract_data, _ = _load_contract(contract_path)
    require_stamp = contract_data.get("global_constraints", {}).get("require_report_contract_stamp", False)

    if require_stamp and contract is None:
        raise ContractValidationError(
            "Report contract stamp is required by contract (require_report_contract_stamp: true), "
            "but no contract was provided for this run. Re-run with --contract flag."
        )


def enforce_qa_benchmark_contract(
    *,
    mode: str,
    dataset_path: str,
    top_k: int,
    doc_path_override_provided: bool,
    contract_path: Optional[str] = None,
) -> ContractRunInfo:
    """Enforce benchmark contract for QA evaluation modes."""
    contract, resolved_contract_path = _load_contract(contract_path)
    _enforce_top_k(contract, top_k)
    mode_cfg = _resolve_mode(contract, mode)
    _enforce_dataset_contract(
        mode_cfg=mode_cfg,
        dataset_path=_resolve_existing_path(dataset_path),
        doc_path_override_provided=doc_path_override_provided,
    )
    return _build_run_info(contract, resolved_contract_path, mode)


def enforce_retrieval_benchmark_contract(
    *,
    query_subset_requested: bool,
    queries_path: Optional[str] = None,
    fixtures_manifest_path: Optional[str] = None,
    contract_path: Optional[str] = None,
) -> ContractRunInfo:
    """Enforce benchmark contract for run_eval.py retrieval harness."""
    contract, resolved_contract_path = _load_contract(contract_path)
    mode_cfg = _resolve_mode(contract, "retrieval_harness")

    expected_queries = mode_cfg.get("queries_path")
    if expected_queries:
        expected_queries_path = (REPO_ROOT / expected_queries).resolve()
        resolved_queries_path = (
            _resolve_existing_path(queries_path)
            if queries_path
            else expected_queries_path
        )
        if resolved_queries_path != expected_queries_path:
            raise ContractValidationError(
                f"queries path override blocked by contract. Expected {expected_queries_path}, got {resolved_queries_path}"
            )

        expected_queries_hash = mode_cfg.get("queries_sha256")
        if expected_queries_hash:
            actual_queries_hash = _sha256_file(resolved_queries_path)
            if actual_queries_hash != expected_queries_hash:
                raise ContractValidationError(
                    f"queries hash mismatch for {resolved_queries_path}. Expected {expected_queries_hash}, got {actual_queries_hash}"
                )

    expected_manifest = mode_cfg.get("fixtures_manifest_path")
    if expected_manifest:
        expected_manifest_path = (REPO_ROOT / expected_manifest).resolve()
        resolved_manifest_path = (
            _resolve_existing_path(fixtures_manifest_path)
            if fixtures_manifest_path
            else expected_manifest_path
        )
        if resolved_manifest_path != expected_manifest_path:
            raise ContractValidationError(
                f"fixtures manifest override blocked by contract. Expected {expected_manifest_path}, got {resolved_manifest_path}"
            )

        expected_manifest_hash = mode_cfg.get("fixtures_manifest_sha256")
        if expected_manifest_hash:
            actual_manifest_hash = _sha256_file(resolved_manifest_path)
            if actual_manifest_hash != expected_manifest_hash:
                raise ContractValidationError(
                    f"fixtures manifest hash mismatch for {resolved_manifest_path}. Expected {expected_manifest_hash}, got {actual_manifest_hash}"
                )

    if query_subset_requested and not mode_cfg.get("allow_query_subset", False):
        raise ContractValidationError("Query subset runs are disabled by contract for retrieval_harness mode")

    return _build_run_info(contract, resolved_contract_path, "retrieval_harness")

