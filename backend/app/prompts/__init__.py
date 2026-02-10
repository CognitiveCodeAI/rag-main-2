"""Prompt registry for versioned prompt management.

All prompts are stored as text files in this directory with format:
{name}_v{version}.txt

The registry provides:
- Centralized prompt loading
- Version tracking for auditability
- Template variable substitution
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# Directory containing prompt files
PROMPTS_DIR = Path(__file__).parent

# Current active versions (can be changed for A/B testing)
# v2 prompts include: few-shot examples, calibration scales, edge case handling
ACTIVE_VERSIONS = {
    "qa_answer": "v2",
    "planner": "v2",
    "verifier": "v2",
    "synthesizer": "v2",
    "reranker": "v2",
    "query_rewrite": "v1",  # v1 already has good examples; v2 adds document context
    "ocr_full_page": "v2",
    "ocr_region": "v2",
    "ocr_caption": "v2",
    "json_repair": "v1",
}


class PromptRegistry:
    """Registry for loading and managing versioned prompts."""
    
    _cache: Dict[str, str] = {}
    
    @classmethod
    def get(
        cls,
        name: str,
        version: Optional[str] = None,
        **kwargs
    ) -> str:
        """Get a prompt by name, optionally with variable substitution.
        
        Args:
            name: Prompt name (e.g., "qa_answer", "planner")
            version: Optional version override (defaults to ACTIVE_VERSIONS)
            **kwargs: Template variables to substitute
            
        Returns:
            Prompt text with variables substituted
            
        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        if version is None:
            version = ACTIVE_VERSIONS.get(name, "v1")
        
        cache_key = f"{name}_{version}"
        
        # Load from cache or file
        if cache_key not in cls._cache:
            filename = f"{name}_{version}.txt"
            filepath = PROMPTS_DIR / filename
            
            if not filepath.exists():
                raise FileNotFoundError(f"Prompt file not found: {filepath}")
            
            with open(filepath, "r", encoding="utf-8") as f:
                cls._cache[cache_key] = f.read()
            
            logger.debug(f"Loaded prompt: {cache_key}")
        
        prompt = cls._cache[cache_key]
        
        # Substitute template variables if provided
        if kwargs:
            try:
                prompt = prompt.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing template variable in {name}: {e}")
        
        return prompt
    
    @classmethod
    def get_version(cls, name: str) -> str:
        """Get the active version for a prompt name."""
        return ACTIVE_VERSIONS.get(name, "v1")
    
    @classmethod
    def get_version_string(cls) -> str:
        """Get a composite version string for all active prompts.
        
        Returns:
            String like "qa_answer:v1,planner:v1,..."
        """
        parts = [f"{k}:{v}" for k, v in sorted(ACTIVE_VERSIONS.items())]
        return ",".join(parts)
    
    @classmethod
    def set_version(cls, name: str, version: str) -> None:
        """Override the active version for a prompt (for A/B testing).
        
        Args:
            name: Prompt name
            version: Version to use (e.g., "v2")
        """
        ACTIVE_VERSIONS[name] = version
        logger.info(f"Set {name} prompt version to {version}")
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear the prompt cache (for hot-reloading)."""
        cls._cache.clear()
        logger.info("Prompt cache cleared")
    
    @classmethod
    def list_prompts(cls) -> Dict[str, str]:
        """List all available prompts and their active versions."""
        return dict(ACTIVE_VERSIONS)


# Convenience function
def get_prompt(name: str, version: Optional[str] = None, **kwargs) -> str:
    """Get a prompt by name with optional variable substitution."""
    return PromptRegistry.get(name, version, **kwargs)


def get_prompt_version() -> str:
    """Get the current prompt version string for audit logging."""
    return PromptRegistry.get_version_string()
