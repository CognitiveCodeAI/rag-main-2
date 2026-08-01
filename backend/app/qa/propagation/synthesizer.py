"""Synthesizer module for TRACK-inspired Propagation Safety Mode.

Synthesizes final answer from verified sub-answers only,
ensuring no raw context leakage.
"""

import json
import logging
import re
import time
from typing import List, Optional, Dict, Any, Tuple

from app.qa.propagation.types import SubQuestion, SubAnswer, PropagationSafetyConfig

logger = logging.getLogger(__name__)


def _get_synthesizer_prompt(question: str, sub_answers_text: str) -> str:
    """Get synthesizer prompt from registry with fallback."""
    try:
        from app.prompts import get_prompt
        return get_prompt("synthesizer", question=question, sub_answers_text=sub_answers_text)
    except Exception as e:
        logger.warning(f"[Synthesizer] Failed to load prompt from registry: {e}, using fallback")
        # Fallback prompt
        return f"""You are a synthesis assistant. You combine verified sub-answers into a final answer.

SYNTHESIS RULES:
1. Synthesize a comprehensive answer using ONLY facts from the verified sub-answers.
2. If any sub-answer indicates "insufficient evidence", reflect that uncertainty.
3. PRESERVE all citations from the sub-answers.
4. Do NOT invent facts not present in the sub-answers.

OUTPUT FORMAT:
Return ONLY valid JSON.

JSON SCHEMA:
{{
  "answer": "your synthesized answer with preserved citations",
  "citations": [{{"citation_id": "C1", "node_id": "...", "page_no": 1, "label": "...", "exact_quote": "verbatim quote from a verified sub-answer"}}],
  "conflicts_summary": "brief summary of any conflicts, or empty string"
}}

ORIGINAL QUESTION:
{question}

VERIFIED SUB-ANSWERS:
{sub_answers_text}"""


def _format_sub_answers(sub_questions: List[SubQuestion], sub_answers: List[SubAnswer]) -> str:
    """Format sub-answers for the synthesizer prompt."""
    if not sub_answers:
        return "(No verified sub-answers provided)"
    
    # Build lookup for sub-questions
    sq_map = {sq.id: sq for sq in sub_questions}
    
    parts = []
    for sa in sub_answers:
        sq = sq_map.get(sa.subq_id)
        sq_text = sq.text if sq else sa.subq_id
        
        status = ""
        if sa.insufficient_evidence:
            status = " [INSUFFICIENT EVIDENCE]"
        elif sa.conflicts:
            status = " [HAS CONFLICTS]"
        
        citations_str = ""
        if sa.citations:
            citations_str = (
                "\nGrounded citations: "
                + json.dumps(sa.citations, ensure_ascii=False)
            )
        
        parts.append(
            f"Sub-question: {sq_text}\n"
            f"Answer{status}: {sa.answer}{citations_str}\n"
            f"Confidence: {sa.confidence}"
        )
    
    return "\n\n---\n\n".join(parts)


def _parse_synthesizer_json(text: str) -> Optional[dict]:
    """Parse JSON from synthesizer response with fallback."""
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


def _merge_citations(sub_answers: List[SubAnswer]) -> List[Dict[str, Any]]:
    """Merge and deduplicate citations from all sub-answers."""
    seen = set()
    merged = []
    
    for sa in sub_answers:
        for cite in sa.citations:
            # Create a key for deduplication
            key = (cite.get("node_id", ""), cite.get("page_no", 0), cite.get("label", ""))
            if key not in seen:
                seen.add(key)
                merged.append(cite)
    
    return merged


def _aggregate_conflicts(sub_answers: List[SubAnswer]) -> str:
    """Aggregate conflict notes from all sub-answers."""
    conflict_notes = []
    
    for sa in sub_answers:
        if sa.conflicts:
            for conflict in sa.conflicts:
                if isinstance(conflict, dict):
                    notes = conflict.get("notes", "")
                    if notes and notes not in conflict_notes:
                        conflict_notes.append(notes)
    
    return "; ".join(conflict_notes) if conflict_notes else ""


def _prepare_grounded_citations(
    answer: str,
    citations: List[Dict[str, Any]],
    sub_answers: List[SubAnswer],
) -> Tuple[str, List[Dict[str, Any]]]:
    """Attach stable IDs and verbatim quotes from verified sub-answers."""
    authoritative = {
        (cite.get("node_id"), cite.get("page_no")): cite
        for cite in _merge_citations(sub_answers)
        if cite.get("node_id") and cite.get("page_no") and cite.get("exact_quote")
    }
    candidates = citations or list(authoritative.values())
    grounded: List[Dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for cite in candidates:
        key = (cite.get("node_id"), cite.get("page_no"))
        source = authoritative.get(key)
        if source is None or key in seen:
            continue
        seen.add(key)
        citation_id = f"C{len(grounded) + 1}"
        grounded_cite = {
            "citation_id": citation_id,
            "node_id": source["node_id"],
            "page_no": source["page_no"],
            "label": source.get("label"),
            "exact_quote": source["exact_quote"],
        }
        grounded.append(grounded_cite)

        legacy_refs = [source["node_id"]]
        if source.get("label"):
            legacy_refs.append(source["label"])
        for ref in legacy_refs:
            answer = re.sub(
                rf"\[{re.escape(str(ref))}:\s*{source['page_no']}\]",
                f"[{citation_id}]",
                answer,
                flags=re.IGNORECASE,
            )

    return answer, grounded


class Synthesizer:
    """Synthesizes final answer from verified sub-answers."""
    
    def __init__(self, llm_client, config: PropagationSafetyConfig):
        """Initialize synthesizer.
        
        Args:
            llm_client: OpenAI client instance
            config: Propagation safety configuration
        """
        self.llm_client = llm_client
        self.config = config
    
    def synthesize(
        self,
        question: str,
        sub_questions: List[SubQuestion],
        sub_answers: List[SubAnswer]
    ) -> Tuple[str, List[Dict[str, Any]], str, int]:
        """Synthesize final answer from verified sub-answers.
        
        Args:
            question: Original user question
            sub_questions: List of sub-questions (for context)
            sub_answers: List of verified sub-answers
            
        Returns:
            Tuple of:
                - final_answer: str
                - citations: List of citation dicts
                - conflicts_summary: str
                - latency_ms: int
        """
        start_time = time.time()
        
        # Check if all must_answer sub-questions have insufficient evidence
        sq_map = {sq.id: sq for sq in sub_questions}
        all_must_insufficient = True
        for sa in sub_answers:
            sq = sq_map.get(sa.subq_id)
            if sq and sq.must_answer and not sa.insufficient_evidence:
                all_must_insufficient = False
                break
        
        if all_must_insufficient:
            # Don't call LLM if all required sub-questions failed
            latency_ms = int((time.time() - start_time) * 1000)
            return (
                "I cannot provide a complete answer because the required evidence was not found in the document.",
                [],
                "",
                latency_ms
            )
        
        # Format sub-answers for prompt
        sub_answers_text = _format_sub_answers(sub_questions, sub_answers)
        
        # Get prompt from registry (combines system + user instructions)
        prompt = _get_synthesizer_prompt(
            question=question,
            sub_answers_text=sub_answers_text
        )
        
        try:
            # Call LLM with temperature=0 for deterministic output
            response = self.llm_client.client.responses.create(
                model=self.llm_client.model,
                instructions=prompt,
                input="",  # Prompt already contains all inputs
                max_output_tokens=1500,
                reasoning={"effort": "none"},
                temperature=0
            )
            
            # Extract response text
            response_text = self.llm_client._response_text(response)
            
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"[Synthesizer] LLM call completed in {latency_ms}ms")
            
            # Parse JSON
            parsed = _parse_synthesizer_json(response_text)
            if not parsed:
                logger.warning(f"[Synthesizer] Failed to parse JSON, using raw text")
                # Fallback: use raw text as answer with merged citations
                return (
                    *_prepare_grounded_citations(
                        response_text,
                        _merge_citations(sub_answers),
                        sub_answers,
                    ),
                    _aggregate_conflicts(sub_answers),
                    latency_ms
                )
            
            # Extract results
            final_answer = parsed.get("answer", "")
            citations = parsed.get("citations", [])
            conflicts_summary = parsed.get("conflicts_summary", "")
            
            # If synthesizer didn't provide citations, merge from sub-answers
            if not citations:
                citations = _merge_citations(sub_answers)
            final_answer, citations = _prepare_grounded_citations(
                final_answer,
                citations,
                sub_answers,
            )
            
            # If synthesizer didn't note conflicts, aggregate from sub-answers
            if not conflicts_summary:
                conflicts_summary = _aggregate_conflicts(sub_answers)
            
            return final_answer, citations, conflicts_summary, latency_ms
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[Synthesizer] Error: {e}")
            
            # Fallback: construct basic answer from sub-answers
            parts = []
            for sa in sub_answers:
                if not sa.insufficient_evidence:
                    parts.append(sa.answer)
            
            fallback_answer = " ".join(parts) if parts else "Unable to synthesize answer due to error."
            
            fallback_answer, fallback_citations = _prepare_grounded_citations(
                fallback_answer,
                _merge_citations(sub_answers),
                sub_answers,
            )
            return (
                fallback_answer,
                fallback_citations,
                _aggregate_conflicts(sub_answers),
                latency_ms
            )
