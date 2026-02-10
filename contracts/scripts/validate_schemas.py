#!/usr/bin/env python3
"""CI script to validate golden sets and embedding records against schemas.

Usage:
    python validate_schemas.py --golden path/to/golden.json
    python validate_schemas.py --embeddings path/to/embeddings.json
    python validate_schemas.py --all  # validate all known files
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from npr_contracts import (
    validate_golden_set,
    validate_golden_record,
    validate_embedding_templates,
    validate_vector_record,
    SchemaValidationError,
)


def validate_golden_file(filepath: Path) -> bool:
    """Validate a golden set JSON file."""
    print(f"Validating golden set: {filepath}")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if "records" in data:
            validate_golden_set(data)
            print(f"  ✓ Valid ({len(data['records'])} records)")
        else:
            validate_golden_record(data)
            print(f"  ✓ Valid (single record)")
        return True
    except SchemaValidationError as e:
        print(f"  ✗ FAILED: {e}")
        return False
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False


def validate_embedding_file(filepath: Path) -> bool:
    """Validate an embedding templates or vector records file."""
    print(f"Validating embedding file: {filepath}")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if "embedding_templates_spec" in data:
            templates = data["embedding_templates_spec"].get("defaults", {})
            validate_embedding_templates(templates)
            print(f"  ✓ Valid embedding templates")
        elif "views" in data:
            validate_vector_record(data)
            print(f"  ✓ Valid vector record")
        else:
            print(f"  ? Unknown embedding file format")
            return False
        return True
    except SchemaValidationError as e:
        print(f"  ✗ FAILED: {e}")
        return False
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Validate NPR schema files")
    parser.add_argument("--golden", type=Path, nargs="*", help="Golden set files to validate")
    parser.add_argument("--embeddings", type=Path, nargs="*", help="Embedding files to validate")
    parser.add_argument("--all", action="store_true", help="Validate all known schema files")
    args = parser.parse_args()

    results = []
    
    if args.golden:
        for f in args.golden:
            results.append(validate_golden_file(f))
    
    if args.embeddings:
        for f in args.embeddings:
            results.append(validate_embedding_file(f))
    
    if args.all:
        # Look for files in contracts/schemas/v1/
        schema_dir = Path(__file__).parent.parent / "schemas" / "v1"
        golden_example = schema_dir / "golden-example.json"
        if golden_example.exists():
            results.append(validate_golden_file(golden_example))
        
        embedding_file = schema_dir / "embedding.schema.json"
        if embedding_file.exists():
            results.append(validate_embedding_file(embedding_file))

    if not results:
        parser.print_help()
        sys.exit(1)
    
    # Summary
    print()
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} passed")
    
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
