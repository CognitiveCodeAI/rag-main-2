import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.eval.update_benchmark_contract import bump_version, update_contract


def test_bump_version_semver_levels() -> None:
    assert bump_version("1.2.3", "patch") == "1.2.4"
    assert bump_version("1.2.3", "minor") == "1.3.0"
    assert bump_version("1.2.3", "major") == "2.0.0"
    assert bump_version("1.2.3", "none") == "1.2.3"


def test_update_contract_refreshes_hash_and_question_count() -> None:
    contract = {
        "contract_id": "x",
        "version": "1.0.0",
        "global_constraints": {},
        "modes": {
            "standard": {
                "dataset_path": "backend/tests/eval/golden_questions.json",
                "dataset_sha256": "stale",
                "required_question_count": 0,
            }
        },
    }
    updated, results = update_contract(contract, selected_modes=["standard"])
    mode = updated["modes"]["standard"]
    assert len(mode["dataset_sha256"]) == 64
    assert mode["required_question_count"] > 0
    assert "dataset_sha256" in results[0].changed_fields
    assert "required_question_count" in results[0].changed_fields


def test_update_contract_accepts_retrieval_mode() -> None:
    contract = {
        "contract_id": "x",
        "version": "1.0.0",
        "global_constraints": {},
        "modes": {
            "retrieval_harness": {
                "queries_path": "backend/tests/eval/queries.json",
                "queries_sha256": "stale",
                "fixtures_manifest_path": "backend/tests/eval/fixtures/manifest.json",
                "fixtures_manifest_sha256": "stale",
            }
        },
    }
    updated, results = update_contract(contract, selected_modes=["retrieval_harness"])
    mode = updated["modes"]["retrieval_harness"]
    assert len(mode["queries_sha256"]) == 64
    assert len(mode["fixtures_manifest_sha256"]) == 64
    assert "queries_sha256" in results[0].changed_fields
    assert "fixtures_manifest_sha256" in results[0].changed_fields
