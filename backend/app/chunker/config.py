"""Chunking configuration."""

from dataclasses import dataclass


@dataclass
class ChunkingConfig:
    """Configuration for document chunking."""
    
    # Token targets
    target_tokens: int = 512
    max_tokens: int = 1024
    min_tokens: int = 64
    overlap_tokens: int = 50
    
    # Structure options
    respect_section_boundaries: bool = True
    separate_tables: bool = True
    separate_code: bool = True
    
    # Heading context
    include_heading_context: bool = True
    max_heading_context_chars: int = 200
    
    # Tokenizer model
    tokenizer_model: str = "cl100k_base"  # GPT-4 tokenizer
