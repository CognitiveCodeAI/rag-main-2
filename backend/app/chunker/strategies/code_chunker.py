"""Code chunking strategy."""

from typing import Any
import tiktoken

from ..config import ChunkingConfig
from ..utils import generate_chunk_id, create_chunk_record
from ...parsers.base import Block


def chunk_code_block(
    block: Block,
    doc_id: str,
    version_id: str,
    section_path: list[str],
    chunk_idx: int,
    config: ChunkingConfig,
    tokenizer: tiktoken.Encoding,
) -> list[dict[str, Any]]:
    """Chunk a code block.
    
    Code blocks are kept as single chunks when possible, or split by
    logical boundaries (functions, classes) if too large.
    
    Args:
        block: Code block
        doc_id: Document ID
        version_id: Version ID
        section_path: Current section path
        chunk_idx: Starting chunk index
        config: Chunking config
        tokenizer: tiktoken encoder
    
    Returns:
        List of ChunkRecord dicts
    """
    code_text = block.text or ""
    if not code_text.strip():
        return []
    
    chunks: list[dict[str, Any]] = []
    
    # Build heading context
    heading_context = None
    if config.include_heading_context and section_path:
        heading_context = " > ".join(section_path)
        if len(heading_context) > config.max_heading_context_chars:
            heading_context = heading_context[:config.max_heading_context_chars] + "..."
    
    tokens = tokenizer.encode(code_text)
    
    # If code fits in max tokens, keep as single chunk
    if len(tokens) <= config.max_tokens:
        chunk_id = generate_chunk_id(doc_id, version_id, chunk_idx)
        
        chunk = create_chunk_record(
            chunk_id=chunk_id,
            doc_id=doc_id,
            version_id=version_id,
            section_path=section_path,
            chunk_type="code",
            start_offset=block.start_offset,
            end_offset=block.end_offset,
            body=code_text,
            heading_context=heading_context,
            code_lang=block.code_lang,
        )
        return [chunk]
    
    # Split by lines, trying to respect function/class boundaries
    lines = code_text.split("\n")
    
    current_lines: list[str] = []
    current_tokens = 0
    
    for line in lines:
        line_tokens = len(tokenizer.encode(line + "\n"))
        
        # Check if adding this line would exceed limit
        if current_tokens + line_tokens > config.max_tokens and current_lines:
            # Try to find a good split point (blank line or function def)
            split_idx = len(current_lines)
            
            # Look backwards for a blank line or definition
            for i in range(len(current_lines) - 1, max(0, len(current_lines) - 20), -1):
                check_line = current_lines[i].strip()
                if not check_line:  # Blank line
                    split_idx = i
                    break
                if check_line.startswith("def ") or check_line.startswith("class "):
                    split_idx = i
                    break
                if check_line.startswith("function ") or check_line.startswith("const "):
                    split_idx = i
                    break
            
            # Create chunk
            if split_idx > 0:
                chunk_text = "\n".join(current_lines[:split_idx])
                remaining = current_lines[split_idx:]
            else:
                chunk_text = "\n".join(current_lines)
                remaining = []
            
            chunk_id = generate_chunk_id(doc_id, version_id, chunk_idx)
            
            chunk = create_chunk_record(
                chunk_id=chunk_id,
                doc_id=doc_id,
                version_id=version_id,
                section_path=section_path,
                chunk_type="code",
                start_offset=block.start_offset,
                end_offset=block.end_offset,
                body=chunk_text.strip(),
                heading_context=heading_context,
                code_lang=block.code_lang,
            )
            chunks.append(chunk)
            chunk_idx += 1
            
            # Reset with remaining lines
            current_lines = remaining
            current_tokens = sum(len(tokenizer.encode(l + "\n")) for l in remaining)
        
        current_lines.append(line)
        current_tokens += line_tokens
    
    # Add remaining lines
    if current_lines:
        chunk_text = "\n".join(current_lines)
        chunk_id = generate_chunk_id(doc_id, version_id, chunk_idx)
        
        chunk = create_chunk_record(
            chunk_id=chunk_id,
            doc_id=doc_id,
            version_id=version_id,
            section_path=section_path,
            chunk_type="code",
            start_offset=block.start_offset,
            end_offset=block.end_offset,
            body=chunk_text.strip(),
            heading_context=heading_context,
            code_lang=block.code_lang,
        )
        chunks.append(chunk)
    
    return chunks
