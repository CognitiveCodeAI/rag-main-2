"""Table chunking strategy."""

from typing import Any
import tiktoken

from ..config import ChunkingConfig
from ..utils import generate_chunk_id, create_chunk_record
from ...parsers.base import Block


def chunk_table_block(
    block: Block,
    doc_id: str,
    version_id: str,
    section_path: list[str],
    chunk_idx: int,
    config: ChunkingConfig,
    tokenizer: tiktoken.Encoding,
) -> list[dict[str, Any]]:
    """Chunk a table block.
    
    Tables are kept as single chunks when possible, or split by rows
    if too large.
    
    Args:
        block: Table block
        doc_id: Document ID
        version_id: Version ID  
        section_path: Current section path
        chunk_idx: Starting chunk index
        config: Chunking config
        tokenizer: tiktoken encoder
    
    Returns:
        List of ChunkRecord dicts
    """
    if not block.cells:
        return []
    
    chunks: list[dict[str, Any]] = []
    
    # Build heading context
    heading_context = None
    if config.include_heading_context and section_path:
        heading_context = " > ".join(section_path)
        if len(heading_context) > config.max_heading_context_chars:
            heading_context = heading_context[:config.max_heading_context_chars] + "..."
    
    # Convert table to text representation
    table_text = _table_to_text(block.cells)
    tokens = tokenizer.encode(table_text)
    
    # If table fits in max tokens, keep as single chunk
    if len(tokens) <= config.max_tokens:
        chunk_id = generate_chunk_id(doc_id, version_id, chunk_idx)
        
        chunk = create_chunk_record(
            chunk_id=chunk_id,
            doc_id=doc_id,
            version_id=version_id,
            section_path=section_path,
            chunk_type="table",
            start_offset=block.start_offset,
            end_offset=block.end_offset,
            body=table_text,
            heading_context=heading_context,
            table_struct=block.cells,
        )
        return [chunk]
    
    # Split table by rows, keeping header
    header_row = block.cells[0] if block.cells else []
    data_rows = block.cells[1:] if len(block.cells) > 1 else []
    
    if not data_rows:
        # Just header, return as is
        chunk_id = generate_chunk_id(doc_id, version_id, chunk_idx)
        chunk = create_chunk_record(
            chunk_id=chunk_id,
            doc_id=doc_id,
            version_id=version_id,
            section_path=section_path,
            chunk_type="table",
            start_offset=block.start_offset,
            end_offset=block.end_offset,
            body=table_text,
            heading_context=heading_context,
            table_struct=block.cells,
        )
        return [chunk]
    
    # Split into chunks of rows
    header_text = "\t".join(header_row)
    header_tokens = len(tokenizer.encode(header_text + "\n"))
    max_row_tokens = config.max_tokens - header_tokens - 10  # Buffer
    
    current_rows: list[list[str]] = []
    current_tokens = 0
    
    for row in data_rows:
        row_text = "\t".join(row)
        row_tokens = len(tokenizer.encode(row_text + "\n"))
        
        if current_tokens + row_tokens > max_row_tokens and current_rows:
            # Create chunk with current rows
            chunk_cells = [header_row] + current_rows
            chunk_text = _table_to_text(chunk_cells)
            chunk_id = generate_chunk_id(doc_id, version_id, chunk_idx)
            
            chunk = create_chunk_record(
                chunk_id=chunk_id,
                doc_id=doc_id,
                version_id=version_id,
                section_path=section_path,
                chunk_type="table",
                start_offset=block.start_offset,
                end_offset=block.end_offset,
                body=chunk_text,
                heading_context=heading_context,
                table_struct=chunk_cells,
            )
            chunks.append(chunk)
            chunk_idx += 1
            
            current_rows = []
            current_tokens = 0
        
        current_rows.append(row)
        current_tokens += row_tokens
    
    # Add remaining rows
    if current_rows:
        chunk_cells = [header_row] + current_rows
        chunk_text = _table_to_text(chunk_cells)
        chunk_id = generate_chunk_id(doc_id, version_id, chunk_idx)
        
        chunk = create_chunk_record(
            chunk_id=chunk_id,
            doc_id=doc_id,
            version_id=version_id,
            section_path=section_path,
            chunk_type="table",
            start_offset=block.start_offset,
            end_offset=block.end_offset,
            body=chunk_text,
            heading_context=heading_context,
            table_struct=chunk_cells,
        )
        chunks.append(chunk)
    
    return chunks


def _table_to_text(cells: list[list[str]]) -> str:
    """Convert table cells to text representation."""
    if not cells:
        return ""
    
    # Markdown-style table
    lines = []
    
    # Header
    if cells:
        lines.append("| " + " | ".join(cells[0]) + " |")
        lines.append("| " + " | ".join(["---"] * len(cells[0])) + " |")
    
    # Data rows
    for row in cells[1:]:
        lines.append("| " + " | ".join(row) + " |")
    
    return "\n".join(lines)
