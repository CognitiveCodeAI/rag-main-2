"""JSON Schema validation for NPR contracts."""

import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator, ValidationError

# Schema directory relative to this file
SCHEMA_DIR = Path(__file__).parent.parent.parent / "schemas" / "v1"


class SchemaValidationError(Exception):
    """Raised when schema validation fails."""

    def __init__(self, message: str, errors: list[ValidationError] | None = None):
        super().__init__(message)
        self.errors = errors or []


def load_schema(schema_name: str) -> dict[str, Any]:
    """Load a schema by name from the schemas directory."""
    schema_path = SCHEMA_DIR / f"{schema_name}.schema.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _validate(data: dict[str, Any], schema: dict[str, Any], name: str) -> None:
    """Validate data against a schema."""
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    if errors:
        error_messages = [f"  - {e.json_path}: {e.message}" for e in errors[:10]]
        msg = f"{name} validation failed:\n" + "\n".join(error_messages)
        if len(errors) > 10:
            msg += f"\n  ... and {len(errors) - 10} more errors"
        raise SchemaValidationError(msg, errors)


# =============================================================================
# Runtime Validators (Backend)
# =============================================================================


def validate_document_ref(doc_ref: dict[str, Any]) -> None:
    """Validate a DocumentRef object."""
    schema = load_schema("document-ref")
    _validate(doc_ref, schema, "DocumentRef")


def validate_document_ir(document_ir: dict[str, Any]) -> None:
    """Validate a DocumentIR object.
    
    Use this after parsing to ensure IR conforms to contract.
    """
    schema = load_schema("document-ir")
    _validate(document_ir, schema, "DocumentIR")


def validate_chunk_record(chunk: dict[str, Any]) -> None:
    """Validate a ChunkRecord object.
    
    Use this after chunking to ensure chunks conform to contract.
    """
    schema = load_schema("chunk-record")
    _validate(chunk, schema, "ChunkRecord")


def validate_retrieval_plan(plan: dict[str, Any]) -> None:
    """Validate a RetrievalPlan from the planner.
    
    Use this at runtime to validate planner output before execution.
    """
    schema = load_schema("retrieval-plan")
    _validate(plan, schema, "RetrievalPlan")


def validate_trace(trace: dict[str, Any]) -> None:
    """Validate a Trace object before writing to logs.
    
    Use this at runtime before persisting flight recorder traces.
    """
    schema = load_schema("trace")
    _validate(trace, schema, "Trace")


# =============================================================================
# CI Validators (Golden Sets, Embeddings)
# =============================================================================


def validate_golden_record(record: dict[str, Any]) -> None:
    """Validate a single golden set record."""
    schema = load_schema("golden-record")
    _validate(record, schema, "GoldenRecord")


def validate_golden_set(golden_set: dict[str, Any]) -> None:
    """Validate a golden set file with multiple records."""
    if "records" not in golden_set:
        raise SchemaValidationError("Golden set must have 'records' array")
    
    schema = load_schema("golden-record")
    errors = []
    
    for i, record in enumerate(golden_set["records"]):
        try:
            _validate(record, schema, f"GoldenRecord[{i}]")
        except SchemaValidationError as e:
            errors.extend(e.errors)
    
    if errors:
        raise SchemaValidationError(
            f"Golden set validation failed with {len(errors)} errors",
            errors
        )


def validate_embedding_templates(templates: dict[str, Any]) -> None:
    """Validate embedding templates spec."""
    # The embedding.schema.json contains nested schemas
    schema_file = SCHEMA_DIR / "embedding.schema.json"
    with open(schema_file, "r", encoding="utf-8") as f:
        full_schema = json.load(f)
    
    if "embedding_templates_spec" in full_schema:
        schema = full_schema["embedding_templates_spec"]["schema"]
        _validate(templates, schema, "EmbeddingTemplates")
    else:
        raise SchemaValidationError("Invalid embedding schema structure")


def validate_vector_record(record: dict[str, Any]) -> None:
    """Validate a multi-view vector record."""
    schema_file = SCHEMA_DIR / "embedding.schema.json"
    with open(schema_file, "r", encoding="utf-8") as f:
        full_schema = json.load(f)
    
    if "multi_view_vector_record_spec" in full_schema:
        schema = full_schema["multi_view_vector_record_spec"]["schema"]
        _validate(record, schema, "MultiViewVectorRecord")
    else:
        raise SchemaValidationError("Invalid embedding schema structure")
