"""Chunking utility functions."""

import hashlib
from typing import Any


def generate_chunk_id(doc_id: str, version_id: str, chunk_idx: int) -> str:
    """Generate a stable chunk ID."""
    raw = f"{doc_id}:{version_id}:{chunk_idx}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def create_chunk_record(
    chunk_id: str,
    doc_id: str,
    version_id: str,
    section_path: list[str],
    chunk_type: str,
    start_offset: int,
    end_offset: int,
    body: str,
    heading_context: str | None = None,
    title: str | None = None,
    table_struct: list[list[str]] | None = None,
    code_lang: str | None = None,
) -> dict[str, Any]:
    """Create a ChunkRecord dict conforming to schema."""
    record = {
        "schema_version": "1.0",
        "chunk_ref": {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "version_id": version_id,
            "section_path": section_path,
            "chunk_type": chunk_type,
            "start_offset": start_offset,
            "end_offset": end_offset,
        },
        "fields": {
            "body": body,
        },
    }
    
    if heading_context:
        record["fields"]["heading_context"] = heading_context
    if title:
        record["fields"]["title"] = title
    if table_struct:
        record["fields"]["table_struct"] = table_struct
    if code_lang:
        record["fields"]["code_lang"] = code_lang
    
    return record
