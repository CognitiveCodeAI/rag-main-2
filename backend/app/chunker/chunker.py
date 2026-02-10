"""Structure-aware document chunker."""

from typing import Any

import tiktoken

from .config import ChunkingConfig
from .utils import generate_chunk_id, create_chunk_record
from ..parsers.base import DocumentIR, Block, Section


# Import strategies here to avoid circular imports
from .strategies.text_chunker import chunk_text_blocks
from .strategies.table_chunker import chunk_table_block
from .strategies.code_chunker import chunk_code_block


def chunk_document(
    document_ir: DocumentIR,
    config: ChunkingConfig | None = None,
) -> list[dict[str, Any]]:
    """Split DocumentIR into ChunkRecords.
    
    Args:
        document_ir: Parsed document IR
        config: Chunking configuration (uses defaults if not provided)
    
    Returns:
        List of ChunkRecord dicts conforming to chunk-record.schema.json
    """
    config = config or ChunkingConfig()
    
    # Initialize tokenizer
    try:
        tokenizer = tiktoken.get_encoding(config.tokenizer_model)
    except Exception:
        tokenizer = tiktoken.get_encoding("cl100k_base")
    
    doc_ref = document_ir.doc_ref
    doc_id = doc_ref.get("doc_id", "unknown")
    version_id = doc_ref.get("version_id", "unknown")
    
    # Build section path lookup from sections
    block_to_section_path: dict[int, list[str]] = {}
    for section in document_ir.sections:
        for block_ref in section.block_refs:
            block_to_section_path[block_ref] = section.section_path
    
    chunks: list[dict[str, Any]] = []
    chunk_idx = 0
    
    # Flatten all blocks from all pages with their indices
    all_blocks: list[tuple[int, Block]] = []
    for page in document_ir.pages:
        for block in page.blocks:
            all_blocks.append((len(all_blocks), block))
    
    # Group consecutive text blocks
    i = 0
    while i < len(all_blocks):
        block_idx, block = all_blocks[i]
        section_path = block_to_section_path.get(block_idx, [])
        
        # Handle tables separately
        if block.type == "table" and config.separate_tables:
            table_chunks = chunk_table_block(
                block=block,
                doc_id=doc_id,
                version_id=version_id,
                section_path=section_path,
                chunk_idx=chunk_idx,
                config=config,
                tokenizer=tokenizer,
            )
            chunks.extend(table_chunks)
            chunk_idx += len(table_chunks)
            i += 1
            continue
        
        # Handle code separately
        if block.type == "code" and config.separate_code:
            code_chunks = chunk_code_block(
                block=block,
                doc_id=doc_id,
                version_id=version_id,
                section_path=section_path,
                chunk_idx=chunk_idx,
                config=config,
                tokenizer=tokenizer,
            )
            chunks.extend(code_chunks)
            chunk_idx += len(code_chunks)
            i += 1
            continue
        
        # Collect consecutive text-like blocks
        text_blocks: list[tuple[int, Block]] = []
        while i < len(all_blocks):
            idx, blk = all_blocks[i]
            if blk.type == "table" and config.separate_tables:
                break
            if blk.type == "code" and config.separate_code:
                break
            
            # Check section boundary
            blk_section = block_to_section_path.get(idx, [])
            if config.respect_section_boundaries and text_blocks:
                prev_idx = text_blocks[-1][0]
                prev_section = block_to_section_path.get(prev_idx, [])
                if blk_section != prev_section:
                    break
            
            text_blocks.append((idx, blk))
            i += 1
        
        if text_blocks:
            # Determine section path for this group
            first_idx = text_blocks[0][0]
            group_section_path = block_to_section_path.get(first_idx, [])
            
            text_chunks = chunk_text_blocks(
                blocks=text_blocks,
                doc_id=doc_id,
                version_id=version_id,
                section_path=group_section_path,
                chunk_idx=chunk_idx,
                config=config,
                tokenizer=tokenizer,
            )
            chunks.extend(text_chunks)
            chunk_idx += len(text_chunks)
    
    return chunks
