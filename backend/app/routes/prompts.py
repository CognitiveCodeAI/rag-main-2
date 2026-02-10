"""Prompts API routes for listing and viewing prompt templates."""

import re
import logging
from pathlib import Path
from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.prompts import PROMPTS_DIR, ACTIVE_VERSIONS, PromptRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/prompts", tags=["prompts"])


# ============================================
# Constants
# ============================================

# Prompt categories for organization
PROMPT_CATEGORIES = {
    "qa_pipeline": ["qa_answer", "planner", "verifier", "synthesizer", "reranker"],
    "query_processing": ["query_rewrite"],
    "ocr": ["ocr_full_page", "ocr_region", "ocr_caption"],
    "utilities": ["json_repair"],
}

CATEGORY_LABELS = {
    "qa_pipeline": "QA Pipeline",
    "query_processing": "Query Processing",
    "ocr": "OCR Processing",
    "utilities": "Utilities",
}


# ============================================
# Response Models
# ============================================

class PromptMetadata(BaseModel):
    """Metadata about a prompt."""
    name: str
    version: str
    category: str
    category_label: str
    filename: str
    template_variables: List[str] = Field(default_factory=list)


class PromptDetail(BaseModel):
    """Full prompt detail including content."""
    name: str
    version: str
    category: str
    category_label: str
    content: str
    template_variables: List[str]
    all_versions: List[str]


class PromptListResponse(BaseModel):
    """Response for listing prompts."""
    prompts: List[PromptMetadata]
    categories: Dict[str, str]


# ============================================
# Helper Functions
# ============================================

def extract_template_variables(content: str) -> List[str]:
    """Extract template variables like {question} from prompt content."""
    # Match {word} but not {{word}} (escaped braces)
    pattern = r'(?<!\{)\{(\w+)\}(?!\})'
    matches = re.findall(pattern, content)
    # Return unique variables in order of appearance
    seen = set()
    result = []
    for match in matches:
        if match not in seen:
            seen.add(match)
            result.append(match)
    return result


def get_category_for_prompt(name: str) -> tuple[str, str]:
    """Get the category key and label for a prompt name."""
    for category_key, prompt_names in PROMPT_CATEGORIES.items():
        if name in prompt_names:
            return category_key, CATEGORY_LABELS[category_key]
    return "utilities", CATEGORY_LABELS["utilities"]


def get_all_versions_for_prompt(name: str) -> List[str]:
    """Scan directory for all versions of a prompt."""
    versions = []
    pattern = re.compile(rf'^{re.escape(name)}_v(\d+)\.txt$')

    for filepath in PROMPTS_DIR.glob(f"{name}_v*.txt"):
        match = pattern.match(filepath.name)
        if match:
            versions.append(f"v{match.group(1)}")

    return sorted(versions, key=lambda v: int(v[1:]))


# ============================================
# Routes
# ============================================

@router.get("", response_model=PromptListResponse)
async def list_prompts() -> PromptListResponse:
    """List all available prompts with metadata."""

    prompts = []
    seen_names = set()

    # Scan prompts directory for .txt files
    for filepath in sorted(PROMPTS_DIR.glob("*.txt")):
        # Parse filename: {name}_v{version}.txt
        match = re.match(r'^(.+)_v(\d+)\.txt$', filepath.name)
        if not match:
            continue

        name = match.group(1)
        version = f"v{match.group(2)}"

        # Only include the active version in the list
        active_version = ACTIVE_VERSIONS.get(name, "v1")
        if version != active_version:
            continue

        # Skip if we've already processed this prompt
        if name in seen_names:
            continue
        seen_names.add(name)

        # Read content to extract template variables
        try:
            content = filepath.read_text(encoding="utf-8")
            template_vars = extract_template_variables(content)
        except Exception as e:
            logger.warning(f"Failed to read prompt {filepath}: {e}")
            template_vars = []

        category_key, category_label = get_category_for_prompt(name)

        prompts.append(PromptMetadata(
            name=name,
            version=version,
            category=category_key,
            category_label=category_label,
            filename=filepath.name,
            template_variables=template_vars,
        ))

    # Sort by category order, then by name
    category_order = list(PROMPT_CATEGORIES.keys())
    prompts.sort(key=lambda p: (
        category_order.index(p.category) if p.category in category_order else 999,
        p.name
    ))

    return PromptListResponse(
        prompts=prompts,
        categories=CATEGORY_LABELS,
    )


@router.get("/{name}", response_model=PromptDetail)
async def get_prompt(
    name: str,
    version: Optional[str] = Query(default=None, description="Specific version (e.g., v1, v2)"),
) -> PromptDetail:
    """Get a specific prompt by name with optional version."""

    # Determine version to use
    if version is None:
        version = ACTIVE_VERSIONS.get(name, "v1")

    # Normalize version format
    if not version.startswith("v"):
        version = f"v{version}"

    # Build filename
    filename = f"{name}_{version}.txt"
    filepath = PROMPTS_DIR / filename

    if not filepath.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Prompt '{name}' version '{version}' not found"
        )

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read prompt {filepath}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read prompt: {str(e)}"
        )

    template_vars = extract_template_variables(content)
    category_key, category_label = get_category_for_prompt(name)
    all_versions = get_all_versions_for_prompt(name)

    return PromptDetail(
        name=name,
        version=version,
        category=category_key,
        category_label=category_label,
        content=content,
        template_variables=template_vars,
        all_versions=all_versions,
    )


@router.get("/{name}/versions", response_model=List[str])
async def list_prompt_versions(name: str) -> List[str]:
    """List all versions available for a prompt."""

    versions = get_all_versions_for_prompt(name)

    if not versions:
        raise HTTPException(
            status_code=404,
            detail=f"No versions found for prompt '{name}'"
        )

    return versions
