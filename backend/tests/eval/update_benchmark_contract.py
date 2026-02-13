#!/usr/bin/env python
"""Update benchmark contract hashes and version.

Usage:
  python tests/eval/update_benchmark_contract.py
  python tests/eval/update_benchmark_contract.py --dry-run
  python tests/eval/update_benchmark_contract.py --mode standard --mode phase2 --bump minor
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONTRACT_PATH = Path(__file__).parent / "benchmark_contract.json"


@dataclass
class ModeUpdateResult:
    mode: str
    changed_fields: List[str]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_contract(contract_path: Path) -> Dict[str, Any]:
    return json.loads(contract_path.read_text(encoding="utf-8"))


def _save_contract(contract_path: Path, data: Dict[str, Any]) -> None:
    contract_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _parse_semver(version: str) -> Tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid semver '{version}'. Expected format: X.Y.Z")
    try:
        major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError as e:
        raise ValueError(f"Invalid semver '{version}'. Version parts must be integers") from e
    if major < 0 or minor < 0 or patch < 0:
        raise ValueError(f"Invalid semver '{version}'. Version parts must be non-negative")
    return major, minor, patch


def bump_version(version: str, bump: str) -> str:
    major, minor, patch = _parse_semver(version)
    if bump == "none":
        return version
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unsupported bump type: {bump}")


def _resolve_repo_path(path_str: str) -> Path:
    path = (REPO_ROOT / path_str).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path from contract does not exist: {path_str} -> {path}")
    return path


def _update_dataset_mode(mode_cfg: Dict[str, Any]) -> List[str]:
    changed: List[str] = []
    dataset_path = mode_cfg.get("dataset_path")
    if not dataset_path:
        return changed

    dataset_file = _resolve_repo_path(dataset_path)
    dataset_hash = _sha256_file(dataset_file)
    if mode_cfg.get("dataset_sha256") != dataset_hash:
        mode_cfg["dataset_sha256"] = dataset_hash
        changed.append("dataset_sha256")

    # Keep question count aligned for JSON files with a top-level "questions" array.
    try:
        data = json.loads(dataset_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in dataset file: {dataset_file}") from e
    if isinstance(data, dict) and isinstance(data.get("questions"), list):
        count = len(data["questions"])
        if mode_cfg.get("required_question_count") != count:
            mode_cfg["required_question_count"] = count
            changed.append("required_question_count")

    return changed


def _update_retrieval_mode(mode_cfg: Dict[str, Any]) -> List[str]:
    changed: List[str] = []

    queries_path = mode_cfg.get("queries_path")
    if queries_path:
        queries_file = _resolve_repo_path(queries_path)
        queries_hash = _sha256_file(queries_file)
        if mode_cfg.get("queries_sha256") != queries_hash:
            mode_cfg["queries_sha256"] = queries_hash
            changed.append("queries_sha256")

    fixtures_path = mode_cfg.get("fixtures_manifest_path")
    if fixtures_path:
        fixtures_file = _resolve_repo_path(fixtures_path)
        fixtures_hash = _sha256_file(fixtures_file)
        if mode_cfg.get("fixtures_manifest_sha256") != fixtures_hash:
            mode_cfg["fixtures_manifest_sha256"] = fixtures_hash
            changed.append("fixtures_manifest_sha256")

    return changed


def update_contract(
    contract: Dict[str, Any],
    selected_modes: List[str] | None = None,
) -> Tuple[Dict[str, Any], List[ModeUpdateResult]]:
    if "modes" not in contract or not isinstance(contract["modes"], dict):
        raise ValueError("Contract missing 'modes' object")

    modes = contract["modes"]
    mode_names = selected_modes or list(modes.keys())

    results: List[ModeUpdateResult] = []
    for mode in mode_names:
        if mode not in modes:
            raise ValueError(f"Mode not found in contract: {mode}")
        mode_cfg = modes[mode]
        if not isinstance(mode_cfg, dict):
            raise ValueError(f"Mode config must be an object: {mode}")

        changed_fields: List[str] = []
        changed_fields.extend(_update_dataset_mode(mode_cfg))
        changed_fields.extend(_update_retrieval_mode(mode_cfg))
        results.append(ModeUpdateResult(mode=mode, changed_fields=changed_fields))

    return contract, results


def main() -> int:
    parser = argparse.ArgumentParser(description="Update benchmark contract hashes/version")
    parser.add_argument(
        "--contract",
        default=str(DEFAULT_CONTRACT_PATH),
        help="Path to benchmark contract JSON",
    )
    parser.add_argument(
        "--mode",
        action="append",
        help="Contract mode to update (repeatable). Default: all modes",
    )
    parser.add_argument(
        "--bump",
        choices=["none", "patch", "minor", "major"],
        default="patch",
        help="Version bump level to apply if contract content changes (default: patch)",
    )
    parser.add_argument(
        "--force-bump",
        action="store_true",
        help="Apply version bump even when no file/hash changes are detected",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without writing file",
    )
    args = parser.parse_args()

    contract_path = Path(args.contract).expanduser().resolve()
    if not contract_path.exists():
        raise FileNotFoundError(f"Contract file not found: {contract_path}")

    contract = _load_contract(contract_path)
    original = json.loads(json.dumps(contract))  # deep copy via JSON
    old_version = str(contract.get("version", "0.0.0"))

    updated_contract, mode_results = update_contract(contract, selected_modes=args.mode)

    any_mode_changed = any(bool(r.changed_fields) for r in mode_results)
    content_changed = updated_contract != original

    if content_changed or args.force_bump:
        updated_contract["version"] = bump_version(old_version, args.bump)
    else:
        updated_contract["version"] = old_version

    if args.dry_run:
        print(f"[DRY RUN] Contract: {contract_path}")
    else:
        _save_contract(contract_path, updated_contract)
        print(f"Updated contract: {contract_path}")

    print(f"Version: {old_version} -> {updated_contract['version']}")
    for result in mode_results:
        fields = ", ".join(result.changed_fields) if result.changed_fields else "-"
        print(f"- {result.mode}: {fields}")

    if not any_mode_changed and not args.force_bump:
        print("No hash/count changes detected.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
