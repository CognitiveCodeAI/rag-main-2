"""Text chunking strategy with overlap and token limits."""

from typing import Any
import tiktoken

from ..config import ChunkingConfig
from ..utils import generate_chunk_id, create_chunk_record
from ...parsers.base import Block


def chunk_text_blocks(
    blocks: list[tuple[int, Block]],
    doc_id: str,
    version_id: str,
    section_path: list[str],
    chunk_idx: int,
    config: ChunkingConfig,
    tokenizer: tiktoken.Encoding,
) -> list[dict[str, Any]]:
    """Chunk consecutive text blocks with token limits.
    
    Args:
        blocks: List of (block_idx, Block) tuples
        doc_id: Document ID
        version_id: Version ID
        section_path: Current section path
        chunk_idx: Starting chunk index
        config: Chunking config
        tokenizer: tiktoken encoder
    
    Returns:
        List of ChunkRecord dicts
    """
    if not blocks:
        return []
    
    chunks: list[dict[str, Any]] = []
    
    # Build heading context from section path
    heading_context = None
    if config.include_heading_context and section_path:
        heading_context = " > ".join(section_path)
        if len(heading_context) > config.max_heading_context_chars:
            heading_context = heading_context[:config.max_heading_context_chars] + "..."
    
    # Collect all text content
    all_text_parts: list[tuple[str, int, int]] = []  # (text, start, end)
    
    for _, block in blocks:
        text = _get_block_text(block)
        if text.strip():
            all_text_parts.append((text, block.start_offset, block.end_offset))
    
    if not all_text_parts:
        return []
    
    # Combine into one text stream with offset tracking
    combined_text = ""
    offset_mapping: list[tuple[int, int, int, int]] = []  # (text_start, text_end, orig_start, orig_end)
    
    for text, orig_start, orig_end in all_text_parts:
        text_start = len(combined_text)
        combined_text += text + "\n\n"
        text_end = len(combined_text) - 2
        offset_mapping.append((text_start, text_end, orig_start, orig_end))
    
    combined_text = combined_text.strip()
    
    # Tokenize
    tokens = tokenizer.encode(combined_text)
    total_tokens = len(tokens)
    
    # If short enough, return as single chunk
    if total_tokens <= config.max_tokens:
        chunk_id = generate_chunk_id(doc_id, version_id, chunk_idx)
        start_offset = all_text_parts[0][1]
        end_offset = all_text_parts[-1][2]
        
        chunk = create_chunk_record(
            chunk_id=chunk_id,
            doc_id=doc_id,
            version_id=version_id,
            section_path=section_path,
            chunk_type="text",
            start_offset=start_offset,
            end_offset=end_offset,
            body=combined_text,
            heading_context=heading_context,
        )
        return [chunk]
    
    # Split into chunks with overlap
    chunk_start_token = 0
    
    while chunk_start_token < total_tokens:
        # Calculate chunk end
        chunk_end_token = min(chunk_start_token + config.target_tokens, total_tokens)
        
        # Try to extend to a natural boundary (sentence/paragraph)
        if chunk_end_token < total_tokens:
            chunk_text = tokenizer.decode(tokens[chunk_start_token:chunk_end_token])
            
            # Look for sentence boundary in last 20% of chunk
            boundary_search_start = int(len(chunk_text) * 0.8)
            boundary_text = chunk_text[boundary_search_start:]
            
            # Find last sentence boundary
            best_boundary = -1
            for char in ["\n\n", ".\n", ". ", "?\n", "? ", "!\n", "! "]:
                idx = boundary_text.rfind(char)
                if idx > best_boundary:
                    best_boundary = idx
            
            if best_boundary > 0:
                # Adjust chunk_text to end at boundary
                chunk_text = chunk_text[:boundary_search_start + best_boundary + 1].strip()
                chunk_end_token = chunk_start_token + len(tokenizer.encode(chunk_text))
        
        # Get final chunk text
        chunk_tokens = tokens[chunk_start_token:chunk_end_token]
        chunk_text = tokenizer.decode(chunk_tokens).strip()
        
        if chunk_text:
            # Calculate approximate original offsets
            start_offset = all_text_parts[0][1]
            end_offset = all_text_parts[-1][2]
            
            chunk_id = generate_chunk_id(doc_id, version_id, chunk_idx)
            
            chunk = create_chunk_record(
                chunk_id=chunk_id,
                doc_id=doc_id,
                version_id=version_id,
                section_path=section_path,
                chunk_type="text",
                start_offset=start_offset,
                end_offset=end_offset,
                body=chunk_text,
                heading_context=heading_context,
            )
            chunks.append(chunk)
            chunk_idx += 1
        
        # Move start with overlap
        if chunk_end_token >= total_tokens:
            break
        
        chunk_start_token = chunk_end_token - config.overlap_tokens
        if chunk_start_token >= chunk_end_token:
            chunk_start_token = chunk_end_token
    
    return chunks


def _get_block_text(block: Block) -> str:
    """Extract text from a block."""
    if block.text:
        return block.text
    if block.list_items:
        return "\n".join(f"• {item}" for item in block.list_items)
    return ""
