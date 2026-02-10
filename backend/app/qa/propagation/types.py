"""Type definitions for TRACK-inspired Propagation Safety Mode.

This module defines dataclasses for:
- Sub-question decomposition (Planner output)
- Evidence packets (Retrieval output)
- Sub-answers (Verifier output)
- Final audit trail (PropagationSafetyAudit)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class SubQuestion:
    """Atomic sub-question produced by the Planner."""
    id: str
    text: str
    why_needed: str
    must_answer: bool = True


@dataclass
class EvidenceSnippet:
    """A single evidence snippet with metadata for verification."""
    node_id: str
    page_no: int
    text: str  # Truncated snippet (max ~600 chars)
    label: Optional[str] = None
    section_hint: Optional[str] = None
    year: Optional[int] = None
    authority_tier: Optional[int] = None


@dataclass
class EvidencePacket:
    """Evidence collected for a single sub-question."""
    subq_id: str
    subq_text: str
    snippets: List[EvidenceSnippet] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_audit: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubAnswer:
    """Verified answer for a single sub-question."""
    subq_id: str
    answer: str
    citations: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    insufficient_evidence: bool = False
    verifier_latency_ms: int = 0


@dataclass
class PropagationSafetyAudit:
    """Complete audit trail for propagation_safety mode."""
    plan: List[SubQuestion] = field(default_factory=list)
    sub_packets: List[EvidencePacket] = field(default_factory=list)
    sub_answers: List[SubAnswer] = field(default_factory=list)
    synthesis_citations: List[Dict[str, Any]] = field(default_factory=list)
    conflicts_summary: str = ""
    total_llm_calls: int = 0
    total_latency_ms: int = 0
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "plan": [
                {
                    "id": sq.id,
                    "text": sq.text,
                    "why_needed": sq.why_needed,
                    "must_answer": sq.must_answer
                }
                for sq in self.plan
            ],
            "sub_packets": [
                {
                    "subq_id": sp.subq_id,
                    "subq_text": sp.subq_text,
                    "snippets": [
                        {
                            "node_id": s.node_id,
                            "page_no": s.page_no,
                            "label": s.label,
                            "section_hint": s.section_hint,
                            "year": s.year,
                            "authority_tier": s.authority_tier,
                            "text_preview": s.text[:200] + "..." if len(s.text) > 200 else s.text
                        }
                        for s in sp.snippets
                    ],
                    "conflicts": sp.conflicts,
                    "retrieval_audit": sp.retrieval_audit
                }
                for sp in self.sub_packets
            ],
            "sub_answers": [
                {
                    "subq_id": sa.subq_id,
                    "answer": sa.answer,
                    "citations": sa.citations,
                    "confidence": sa.confidence,
                    "conflicts": sa.conflicts,
                    "insufficient_evidence": sa.insufficient_evidence,
                    "verifier_latency_ms": sa.verifier_latency_ms
                }
                for sa in self.sub_answers
            ],
            "synthesis_citations": self.synthesis_citations,
            "conflicts_summary": self.conflicts_summary,
            "total_llm_calls": self.total_llm_calls,
            "total_latency_ms": self.total_latency_ms,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason
        }


@dataclass
class PropagationSafetyConfig:
    """Configuration for propagation_safety mode."""
    max_sub_questions: int = 4
    verifier_timeout_s: float = 5.0
    parallel_verifiers: bool = True
    total_budget_s: float = 30.0
    fallback_on_timeout: bool = True
    max_snippets_per_subq: int = 8
    snippet_max_chars: int = 600
    subq_top_k: int = 4
    subq_max_context_tokens: int = 3000
    
    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "PropagationSafetyConfig":
        """Create config from dictionary, using defaults for missing keys."""
        if data is None:
            return cls()
        return cls(
            max_sub_questions=data.get("max_sub_questions", 4),
            verifier_timeout_s=data.get("verifier_timeout_s", 5.0),
            parallel_verifiers=data.get("parallel_verifiers", True),
            total_budget_s=data.get("total_budget_s", 30.0),
            fallback_on_timeout=data.get("fallback_on_timeout", True),
            max_snippets_per_subq=data.get("max_snippets_per_subq", 8),
            snippet_max_chars=data.get("snippet_max_chars", 600),
            subq_top_k=data.get("subq_top_k", 4),
            subq_max_context_tokens=data.get("subq_max_context_tokens", 3000),
        )
