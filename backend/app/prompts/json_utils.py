"""JSON parsing utilities with validation and repair."""

import json
import logging
import re
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def extract_json_from_response(text: str) -> Optional[str]:
    """Extract JSON from a response that may contain markdown or other text.
    
    Args:
        text: Raw response text
        
    Returns:
        Extracted JSON string or None
    """
    if not text:
        return None
    
    text = text.strip()
    
    # Try to find JSON in markdown code blocks
    code_block_patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
    ]
    
    for pattern in code_block_patterns:
        match = re.search(pattern, text)
        if match:
            extracted = match.group(1).strip()
            if extracted.startswith("{") or extracted.startswith("["):
                return extracted
    
    # Try to find raw JSON (object or array)
    # Find first { or [ and last } or ]
    obj_start = text.find("{")
    arr_start = text.find("[")
    
    if obj_start == -1 and arr_start == -1:
        return None
    
    if obj_start >= 0 and (arr_start == -1 or obj_start < arr_start):
        # Object
        obj_end = text.rfind("}")
        if obj_end > obj_start:
            return text[obj_start:obj_end + 1]
    else:
        # Array
        arr_end = text.rfind("]")
        if arr_end > arr_start:
            return text[arr_start:arr_end + 1]
    
    return None


def parse_json_strict(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON strictly, returning None on failure.
    
    Args:
        text: JSON string
        
    Returns:
        Parsed dict or None
    """
    extracted = extract_json_from_response(text)
    if not extracted:
        return None
    
    try:
        return json.loads(extracted)
    except json.JSONDecodeError as e:
        logger.debug(f"JSON parse error: {e}")
        return None


def validate_with_schema(
    data: Dict[str, Any],
    schema_class: Type[T]
) -> Optional[T]:
    """Validate parsed JSON against a Pydantic schema.
    
    Args:
        data: Parsed JSON dict
        schema_class: Pydantic model class
        
    Returns:
        Validated model instance or None
    """
    try:
        return schema_class.model_validate(data)
    except ValidationError as e:
        logger.debug(f"Schema validation error: {e}")
        return None


def parse_and_validate(
    text: str,
    schema_class: Type[T]
) -> Optional[T]:
    """Parse JSON and validate against schema in one step.
    
    Args:
        text: Raw response text
        schema_class: Pydantic model class
        
    Returns:
        Validated model instance or None
    """
    parsed = parse_json_strict(text)
    if parsed is None:
        return None
    
    return validate_with_schema(parsed, schema_class)


def repair_json(raw_text: str, llm_client, schema_hint: str = "") -> Optional[str]:
    """Attempt to repair malformed JSON using LLM.
    
    Args:
        raw_text: Malformed JSON text
        llm_client: OpenAI client instance
        schema_hint: Optional schema description for repair guidance
        
    Returns:
        Repaired JSON string or None
    """
    from app.prompts import get_prompt
    
    repair_prompt = get_prompt(
        "json_repair",
        raw_json=raw_text[:2000],  # Limit length
        schema=schema_hint or "{...}"
    )
    
    try:
        response = llm_client.client.responses.create(
            model="gpt-4o-mini",  # Fast model for repair
            instructions="You are a JSON repair assistant. Output ONLY valid JSON.",
            input=repair_prompt,
            max_output_tokens=2000,
            reasoning={"effort": "none"},
            temperature=0
        )
        
        repaired_text = llm_client._response_text(response)
        
        # Verify the repair worked
        parsed = parse_json_strict(repaired_text)
        if parsed is not None:
            logger.info("JSON repair successful")
            return json.dumps(parsed)
        
        logger.warning("JSON repair failed to produce valid JSON")
        return None
        
    except Exception as e:
        logger.error(f"JSON repair LLM call failed: {e}")
        return None


def parse_with_retry(
    text: str,
    schema_class: Type[T],
    llm_client=None,
    schema_hint: str = ""
) -> Optional[T]:
    """Parse JSON with optional LLM repair retry.
    
    Args:
        text: Raw response text
        schema_class: Pydantic model class for validation
        llm_client: Optional LLM client for repair attempts
        schema_hint: Optional schema description for repair
        
    Returns:
        Validated model instance or None
    """
    # First attempt: direct parse
    result = parse_and_validate(text, schema_class)
    if result is not None:
        return result
    
    logger.warning("Initial JSON parse failed, attempting repair...")
    
    # Second attempt: repair if LLM client available
    if llm_client is not None:
        repaired = repair_json(text, llm_client, schema_hint)
        if repaired:
            result = parse_and_validate(repaired, schema_class)
            if result is not None:
                logger.info("JSON parse succeeded after repair")
                return result
    
    logger.error("JSON parse failed after repair attempt")
    return None


# Schema definitions for common structured outputs
class PlannerOutput(BaseModel):
    """Schema for planner output."""
    needs_clarification: bool = False
    sub_questions: list = []


class VerifierOutput(BaseModel):
    """Schema for verifier output."""
    answer: str
    citations: list = []
    confidence: float = 0.5
    insufficient_evidence: bool = False
    conflict_notes: str = ""


class SynthesizerOutput(BaseModel):
    """Schema for synthesizer output."""
    answer: str
    citations: list = []
    conflicts_summary: str = ""


class RerankerOutput(BaseModel):
    """Schema for reranker output."""
    ranked: list = []
