# Benchmark Contract Plan

## Goal
Define and enforce a benchmark contract before any evaluation run so benchmark claims are reproducible, auditable, and resistant to accidental drift.

## Scope
- QA evaluation entrypoint: `/Users/stewie/Downloads/rag-main-2/backend/tests/eval/run_qa_eval.py`
- Retrieval harness entrypoint: `/Users/stewie/Downloads/rag-main-2/backend/tests/eval/run_eval.py`
- Report generator: `/Users/stewie/Downloads/rag-main-2/backend/tests/eval/report.py`

## Contract Requirements
1. Freeze benchmark datasets and fixture manifests by path and SHA256.
2. Freeze run-critical parameters (`top_k`) for claim-valid runs.
3. Disallow local run-time overrides that change benchmark meaning (`--doc-path`, ad-hoc question files, query subset runs).
4. Fail fast before any benchmark logic executes.
5. Stamp every generated report with contract identity and hash.

## Implementation Plan
1. Add a versioned contract file:
- `/Users/stewie/Downloads/rag-main-2/backend/tests/eval/benchmark_contract.json`

2. Add contract validator module:
- `/Users/stewie/Downloads/rag-main-2/backend/tests/eval/benchmark_contract.py`
- Responsibilities:
  - Contract JSON loading and structural validation
  - File identity and SHA256 verification
  - Mode-specific policy checks
  - Standardized `ContractRunInfo` metadata for report stamping

3. Enforce in entrypoints before run:
- `run_qa_eval.py` validates mode (`standard`, `phase2`, `rerank_ab`, `propagation_safety`, `track_like`, `finalboss`) and exits with code `2` on violations.
- `run_eval.py` validates `retrieval_harness` mode and blocks subset query runs unless explicitly allowed by contract.
- `report.py` validates contract before launching baseline/graph comparison runs.

4. Add report provenance:
- Include contract ID, version, SHA256, and contract file path in all generated markdown/HTML/JSON reports.

## Acceptance Criteria
1. Any contract violation aborts before evaluation execution starts.
2. All benchmark outputs include contract provenance fields.
3. Default evaluation commands run successfully with default contract.
4. Reproducibility checks are deterministic via frozen hashes.

## Maintenance Workflow
When benchmark assets intentionally change:
1. Update benchmark files.
2. Recompute hashes + refresh counts + bump version in one step:
- `python /Users/stewie/Downloads/rag-main-2/backend/tests/eval/update_benchmark_contract.py`
3. Review diff for `/Users/stewie/Downloads/rag-main-2/backend/tests/eval/benchmark_contract.json`.
4. Re-run benchmark and keep report with updated contract stamp.
