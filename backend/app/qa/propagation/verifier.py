"""Verifier module for TRACK-inspired Propagation Safety Mode.

Verifies sub-answers with strict grounding in evidence snippets.
Supports parallel execution for multiple sub-questions.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import List, Optional, Dict, Any

from app.qa.propagation.types import (
    SubQuestion, 
    EvidencePacket, 
    EvidenceSnippet,
    SubAnswer,
    PropagationSafetyConfig
)

logger = logging.getLogger(__name__)


def _get_verifier_prompt(sub_question: str, snippets_text: str) -> str:
    """Get verifier prompt from registry with fallback."""
    try:
        from app.prompts import get_prompt
        return get_prompt("verifier", sub_question=sub_question, snippets_text=snippets_text)
    except Exception as e:
        logger.warning(f"[Verifier] Failed to load prompt from registry: {e}, using fallback")
        # Fallback prompt
        return f"""You are a strict evidence verifier. You answer ONLY using provided evidence snippets.

VERIFICATION RULES:
1. Answer ONLY using information from the evidence snippets below.
2. You MUST cite at least 1 snippet if you provide an answer.
3. If evidence is insufficient, set insufficient_evidence=true.
4. Set confidence between 0.0 and 1.0.

OUTPUT FORMAT:
Return ONLY valid JSON.

JSON SCHEMA:
{{
  "answer": "your answer based on evidence",
  "citations": [{{"node_id": "...", "page_no": 1, "label": "..."}}],
  "confidence": 0.8,
  "insufficient_evidence": false,
  "conflict_notes": ""
}}

SUB-QUESTION:
{sub_question}

EVIDENCE SNIPPETS:
{snippets_text}"""


def _format_snippets(snippets: List[EvidenceSnippet]) -> str:
    """Format evidence snippets for the verifier prompt."""
    if not snippets:
        return "(No evidence snippets provided)"
    
    parts = []
    for i, s in enumerate(snippets, 1):
        meta_parts = [f"page {s.page_no}"]
        if s.label:
            meta_parts.append(f"label: {s.label}")
        if s.section_hint:
            meta_parts.append(f"section: {s.section_hint}")
        if s.year:
            meta_parts.append(f"year: {s.year}")
        if s.authority_tier:
            meta_parts.append(f"authority: {s.authority_tier}")
        
        meta_str = ", ".join(meta_parts)
        parts.append(f"[{i}] node_id={s.node_id} ({meta_str})\n{s.text}")
    
    return "\n\n".join(parts)


def _parse_verifier_json(text: str) -> Optional[dict]:
    """Parse JSON from verifier response with fallback."""
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


class Verifier:
    """Verifies sub-answers with strict evidence grounding."""
    
    def __init__(self, llm_client, config: PropagationSafetyConfig):
        """Initialize verifier.
        
        Args:
            llm_client: OpenAI client instance
            config: Propagation safety configuration
        """
        self.llm_client = llm_client
        self.config = config
    
    def verify_single(
        self,
        sub_question: SubQuestion,
        evidence_packet: EvidencePacket
    ) -> SubAnswer:
        """Verify a single sub-question with its evidence.
        
        Args:
            sub_question: The sub-question to verify
            evidence_packet: Evidence collected for this sub-question
            
        Returns:
            SubAnswer with verified answer and citations
        """
        start_time = time.time()
        
        # Format snippets for prompt
        snippets_text = _format_snippets(evidence_packet.snippets)
        
        # Get prompt from registry (combines system + user instructions)
        prompt = _get_verifier_prompt(
            sub_question=sub_question.text,
            snippets_text=snippets_text
        )
        
        try:
            # Call LLM with temperature=0 for deterministic output
            response = self.llm_client.client.responses.create(
                model=self.llm_client.model,
                instructions=prompt,
                input="",  # Prompt already contains all inputs
                max_output_tokens=800,
                reasoning={"effort": "none"},
                temperature=0
            )
            
            # Extract response text
            response_text = self.llm_client._response_text(response)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Parse JSON
            parsed = _parse_verifier_json(response_text)
            if not parsed:
                logger.warning(f"[Verifier] Failed to parse JSON for {sub_question.id}")
                return SubAnswer(
                    subq_id=sub_question.id,
                    answer="Failed to parse verifier response",
                    citations=[],
                    confidence=0.0,
                    conflicts=evidence_packet.conflicts,
                    insufficient_evidence=True,
                    verifier_latency_ms=latency_ms
                )
            
            # Build SubAnswer
            citations = parsed.get("citations", [])
            conflict_notes = parsed.get("conflict_notes", "")
            
            # Add conflict notes to conflicts list if present
            conflicts = evidence_packet.conflicts.copy()
            if conflict_notes:
                conflicts.append({"type": "verifier_noted", "notes": conflict_notes})
            
            return SubAnswer(
                subq_id=sub_question.id,
                answer=parsed.get("answer", ""),
                citations=citations,
                confidence=parsed.get("confidence", 0.0),
                conflicts=conflicts,
                insufficient_evidence=parsed.get("insufficient_evidence", False),
                verifier_latency_ms=latency_ms
            )
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[Verifier] Error for {sub_question.id}: {e}")
            return SubAnswer(
                subq_id=sub_question.id,
                answer=f"Verification error: {str(e)}",
                citations=[],
                confidence=0.0,
                conflicts=evidence_packet.conflicts,
                insufficient_evidence=True,
                verifier_latency_ms=latency_ms
            )
    
    def verify_all(
        self,
        sub_questions: List[SubQuestion],
        evidence_packets: List[EvidencePacket]
    ) -> List[SubAnswer]:
        """Verify all sub-questions, optionally in parallel.
        
        Args:
            sub_questions: List of sub-questions
            evidence_packets: List of evidence packets (same order as sub_questions)
            
        Returns:
            List of SubAnswers (same order)
        """
        if len(sub_questions) != len(evidence_packets):
            raise ValueError("sub_questions and evidence_packets must have same length")
        
        if not sub_questions:
            return []
        
        # Build lookup for evidence packets
        packet_map = {ep.subq_id: ep for ep in evidence_packets}
        
        if self.config.parallel_verifiers and len(sub_questions) > 1:
            return self._verify_parallel(sub_questions, packet_map)
        else:
            return self._verify_sequential(sub_questions, packet_map)
    
    def _verify_sequential(
        self,
        sub_questions: List[SubQuestion],
        packet_map: Dict[str, EvidencePacket]
    ) -> List[SubAnswer]:
        """Verify sub-questions sequentially."""
        results = []
        for sq in sub_questions:
            ep = packet_map.get(sq.id)
            if not ep:
                logger.warning(f"[Verifier] No evidence packet for {sq.id}")
                results.append(SubAnswer(
                    subq_id=sq.id,
                    answer="No evidence collected",
                    citations=[],
                    confidence=0.0,
                    conflicts=[],
                    insufficient_evidence=True,
                    verifier_latency_ms=0
                ))
                continue
            
            result = self.verify_single(sq, ep)
            results.append(result)
            logger.info(f"[Verifier] {sq.id} verified in {result.verifier_latency_ms}ms")
        
        return results
    
    def _verify_parallel(
        self,
        sub_questions: List[SubQuestion],
        packet_map: Dict[str, EvidencePacket]
    ) -> List[SubAnswer]:
        """Verify sub-questions in parallel with timeout."""
        results = [None] * len(sub_questions)
        
        def verify_with_index(args):
            idx, sq = args
            ep = packet_map.get(sq.id)
            if not ep:
                return idx, SubAnswer(
                    subq_id=sq.id,
                    answer="No evidence collected",
                    citations=[],
                    confidence=0.0,
                    conflicts=[],
                    insufficient_evidence=True,
                    verifier_latency_ms=0
                )
            return idx, self.verify_single(sq, ep)
        
        # Use ThreadPoolExecutor for parallel execution
        max_workers = min(len(sub_questions), 4)  # Cap at 4 concurrent verifiers
        
        logger.info(f"[Verifier] Starting parallel verification of {len(sub_questions)} sub-questions")
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(verify_with_index, (i, sq)): i 
                for i, sq in enumerate(sub_questions)
            }
            
            for future in futures:
                idx = futures[future]
                sq = sub_questions[idx]
                try:
                    # Apply per-verifier timeout
                    result_idx, result = future.result(timeout=self.config.verifier_timeout_s)
                    results[result_idx] = result
                    logger.info(f"[Verifier] {sq.id} completed in {result.verifier_latency_ms}ms")
                except FuturesTimeoutError:
                    logger.warning(f"[Verifier] Timeout for {sq.id}")
                    results[idx] = SubAnswer(
                        subq_id=sq.id,
                        answer="Verification timed out",
                        citations=[],
                        confidence=0.0,
                        conflicts=[],
                        insufficient_evidence=True,
                        verifier_latency_ms=int(self.config.verifier_timeout_s * 1000)
                    )
                except Exception as e:
                    logger.error(f"[Verifier] Error for {sq.id}: {e}")
                    results[idx] = SubAnswer(
                        subq_id=sq.id,
                        answer=f"Verification error: {str(e)}",
                        citations=[],
                        confidence=0.0,
                        conflicts=[],
                        insufficient_evidence=True,
                        verifier_latency_ms=0
                    )
        
        total_time = int((time.time() - start_time) * 1000)
        logger.info(f"[Verifier] Parallel verification completed in {total_time}ms")
        
        return results
