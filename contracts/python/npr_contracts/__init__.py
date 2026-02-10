"""NPR Contracts - JSON Schema validation for NPR RAG system.

Runtime validation for:
- RetrievalPlan (planner output)
- Trace (flight recorder logs)

CI validation for:
- Golden set records
- Embedding templates and vector records
"""

from .validator import (
    validate_document_ref,
    validate_document_ir,
    validate_chunk_record,
    validate_retrieval_plan,
    validate_trace,
    validate_golden_record,
    validate_golden_set,
    validate_embedding_templates,
    validate_vector_record,
    SchemaValidationError,
    load_schema,
)

__version__ = "1.0.0"
__all__ = [
    "validate_document_ref",
    "validate_document_ir",
    "validate_chunk_record",
    "validate_retrieval_plan",
    "validate_trace",
    "validate_golden_record",
    "validate_golden_set",
    "validate_embedding_templates",
    "validate_vector_record",
    "SchemaValidationError",
    "load_schema",
]
