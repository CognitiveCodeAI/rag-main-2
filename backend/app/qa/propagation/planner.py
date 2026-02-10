"""Planner module for TRACK-inspired Propagation Safety Mode.

Decomposes complex questions into atomic sub-questions that can be
independently verified with citations.
"""

import json
import logging
import re
import time
from typing import List, Optional, Tuple, Set

from app.qa.propagation.types import SubQuestion, PropagationSafetyConfig

logger = logging.getLogger(__name__)


def _get_planner_prompt(question: str, min_subq: int, max_subq: int) -> str:
    """Get planner prompt from registry with fallback."""
    try:
        from app.prompts import get_prompt
        return get_prompt("planner", question=question, min_subq=min_subq, max_subq=max_subq)
    except Exception as e:
        logger.warning(f"[Planner] Failed to load prompt from registry: {e}, using fallback")
        # Fallback prompt
        return f"""You are a strict question planner. You do NOT answer questions.
Your ONLY job is to decompose a complex question into atomic sub-questions.

DECOMPOSITION RULES:
1. Produce {min_subq} to {max_subq} sub-questions.
2. Each sub-question must be answerable from a single document section.
3. Preserve ALL entities, constraints, dates, and negations from the original question.
4. Do NOT invent new entities or facts not mentioned in the question.

OUTPUT FORMAT:
Return ONLY valid JSON.

JSON SCHEMA:
{{
  "needs_clarification": false,
  "sub_questions": [
    {{"id": "sq1", "text": "...", "why_needed": "...", "must_answer": true}}
  ]
}}

QUESTION:
{question}"""


def _extract_entities(text: str) -> Set[str]:
    """Extract key entities from text for validation.
    
    Simple heuristic: extract capitalized words, quoted strings, numbers.
    """
    entities = set()
    
    # Capitalized words (likely proper nouns)
    caps = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    entities.update(caps)
    
    # Quoted strings
    quoted = re.findall(r'"([^"]+)"', text)
    entities.update(quoted)
    quoted = re.findall(r"'([^']+)'", text)
    entities.update(quoted)
    
    # Numbers and dates
    numbers = re.findall(r'\b\d{4}\b|\b\d+(?:\.\d+)?\b', text)
    entities.update(numbers)
    
    # Explicit table/figure references
    refs = re.findall(r'(?:Table|Figure|Appendix)\s+\d+', text, re.IGNORECASE)
    entities.update(refs)
    
    return entities


def _validate_sub_questions(
    sub_questions: List[SubQuestion],
    original_question: str,
    max_subq: int
) -> Tuple[bool, Optional[str]]:
    """Validate planner output.
    
    Returns:
        (is_valid, error_reason)
    """
    if not sub_questions:
        return False, "no_sub_questions"
    
    if len(sub_questions) > max_subq:
        return False, f"too_many_sub_questions ({len(sub_questions)} > {max_subq})"
    
    # Check for hallucinated entities
    original_entities = _extract_entities(original_question)
    
    for sq in sub_questions:
        sq_entities = _extract_entities(sq.text)
        
        # Allow sub-question entities that are subsets or slight variations
        # But flag if completely new major entities appear
        new_entities = sq_entities - original_entities
        
        # Filter out common words that might be false positives
        common_words = {"The", "What", "How", "Why", "When", "Where", "Which", "Does", "Did", "Is", "Are", "Was", "Were"}
        new_entities = new_entities - common_words
        
        # If there are many new capitalized entities, this might be hallucination
        if len(new_entities) > 3:
            logger.warning(f"[Planner] Potential hallucination in sq {sq.id}: new entities {new_entities}")
            # Don't fail, just warn - the entities might be valid elaborations
    
    return True, None


def _parse_planner_json(text: str) -> Optional[dict]:
    """Parse JSON from planner response with fallback."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Fallback: extract JSON substring
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            return json.loads(text[start:end+1])
    except json.JSONDecodeError:
        pass
    
    return None


class Planner:
    """Decomposes questions into atomic sub-questions."""
    
    def __init__(self, llm_client, config: PropagationSafetyConfig):
        """Initialize planner.
        
        Args:
            llm_client: OpenAI client instance
            config: Propagation safety configuration
        """
        self.llm_client = llm_client
        self.config = config
    
    def plan(self, question: str) -> Tuple[List[SubQuestion], bool, int]:
        """Decompose question into sub-questions.
        
        Args:
            question: Original user question
            
        Returns:
            Tuple of:
                - List of SubQuestion objects
                - needs_clarification flag
                - latency_ms
        """
        start_time = time.time()
        
        # Get prompt from registry (combines system + user instructions)
        prompt = _get_planner_prompt(
            question=question,
            min_subq=2,
            max_subq=self.config.max_sub_questions
        )
        
        try:
            # Call LLM with temperature=0 for deterministic output
            response = self.llm_client.client.responses.create(
                model=self.llm_client.model,
                instructions=prompt,
                input="",  # Prompt already contains the question
                max_output_tokens=1000,
                reasoning={"effort": "none"},
                temperature=0
            )
            
            # Extract response text
            response_text = self.llm_client._response_text(response)
            
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"[Planner] LLM call completed in {latency_ms}ms")
            
            # Parse JSON
            parsed = _parse_planner_json(response_text)
            if not parsed:
                logger.error(f"[Planner] Failed to parse JSON: {response_text[:500]}")
                return [], False, latency_ms
            
            needs_clarification = parsed.get("needs_clarification", False)
            
            # Extract sub-questions
            sub_questions = []
            for sq_data in parsed.get("sub_questions", []):
                sq = SubQuestion(
                    id=sq_data.get("id", f"sq{len(sub_questions)+1}"),
                    text=sq_data.get("text", ""),
                    why_needed=sq_data.get("why_needed", ""),
                    must_answer=sq_data.get("must_answer", True)
                )
                if sq.text:  # Only add if text is non-empty
                    sub_questions.append(sq)
            
            # Validate
            is_valid, error = _validate_sub_questions(
                sub_questions, 
                question, 
                self.config.max_sub_questions
            )
            
            if not is_valid:
                logger.warning(f"[Planner] Validation failed: {error}")
                return [], needs_clarification, latency_ms
            
            logger.info(f"[Planner] Generated {len(sub_questions)} sub-questions")
            return sub_questions, needs_clarification, latency_ms
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[Planner] Error: {e}")
            return [], False, latency_ms
