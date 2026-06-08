"""QA Runner - orchestrates the full RAG pipeline.

Performs:
1. Query normalization (generate multiple query variations)
2. Question embedding (embed all variations)
3. Vector search for seed chunks (merge results)
4. Section-aware boosting
5. [OPTIONAL] Rerank merged candidates (pre-expansion)
6. Select top-K seeds
7. Graph expansion
8. Context packing
9. Answer generation with citations
"""

import httpx
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.graph_models import Node, DocumentGraph
from app.db.models import CitationSnapshot
from app.embeddings.client import get_embedding_client
from app.graph.expander import GraphExpander, ExpandedContext
from app.graph.context_packer import ContextPacker, PackedContext
from app.graph.vector_index import GraphVectorIndex
from app.llm.openai_client import OpenAIClient, AnswerResult, Citation
from app.services.document_identity import find_legacy_for_graph
from app.services.highlighting import (
    ensure_highlight_artifacts,
    resolve_citation_selector,
    verify_evidence_span,
)
from app.storage.minio_client import get_storage_client
from .evidence_span import build_evidence_spans
from .normalizer import normalize_query, NormalizedQuery
from .section_booster import SectionBooster, SectionBoostResult
from .constraint_parser import parse_constraints, ParsedConstraints
from .metadata_booster import MetadataBooster, MetadataBoostResult
from .conflict_detector import detect_conflicts, ConflictDetectionResult

logger = logging.getLogger(__name__)


# =============================================================================
# RERANKER GATE - Metric-based eligibility for reranking
# =============================================================================

@dataclass
class RerankerGateContext:
    """Context for reranker gate decision."""
    # Baseline metrics (from recent evals)
    baseline_seed_precision_at_5: float = 0.0
    baseline_evidence_recall: float = 0.0
    
    # A/B comparison metrics
    rerank_seed_precision_at_5: float = 0.0
    rerank_evidence_recall: float = 0.0
    rerank_ab_improvement_at_5: float = 0.0
    
    # Performance metrics
    rerank_latency_overhead_pct: float = 0.0
    rerank_degeneracy_rate: float = 0.0  # % of questions with degenerate output
    
    # Baseline improvement trend (from N eval runs)
    baseline_precision_trend: float = 0.0  # Change in precision over recent runs


@dataclass
class RerankerGateResult:
    """Result of reranker gate evaluation."""
    allowed: bool = False
    reason: str = ""
    mode: str = "baseline"  # "baseline" | "gated" | "forced"
    
    # Individual gate checks
    baseline_plateau_check: bool = False
    ab_improvement_check: bool = False
    recall_regression_check: bool = False
    latency_check: bool = False
    stability_check: bool = False


class RerankerGate:
    """Metric-gated reranking eligibility checker.
    
    Reranking only runs when ALL conditions are met:
    1. Baseline plateau (precision improvement < +0.02)
    2. A/B improvement (rerank improves precision by ≥ +0.05)
    3. No recall regression
    4. Latency overhead ≤ 20%
    5. Stability (degeneracy rate ≤ 10%)
    """
    
    # Gate thresholds (from directive)
    BASELINE_PLATEAU_THRESHOLD = 0.02     # Max precision improvement before plateau
    AB_IMPROVEMENT_THRESHOLD = 0.05       # Min required rerank improvement
    LATENCY_OVERHEAD_MAX_PCT = 20.0       # Max latency overhead %
    DEGENERACY_RATE_MAX_PCT = 10.0        # Max degeneracy/fallback rate %
    
    # Fast mode limits (when gate passes)
    FAST_MODE_MAX_CANDIDATES = 12
    FAST_MODE_TIMEOUT_S = 2
    
    @classmethod
    def should_rerank(
        cls,
        context: Optional[RerankerGateContext] = None,
        force: bool = False
    ) -> RerankerGateResult:
        """Determine if reranking should run.
        
        Args:
            context: Gate context with metrics (None = use defaults/deny)
            force: Manual override via --rerank-force flag
            
        Returns:
            RerankerGateResult with decision and reasoning
        """
        result = RerankerGateResult()
        
        # Manual override
        if force:
            result.allowed = True
            result.mode = "forced"
            result.reason = "forced_by_flag"
            logger.warning("[RerankerGate] Reranking FORCED via --rerank-force flag")
            return result
        
        # No context = no metrics = deny
        if context is None:
            result.allowed = False
            result.mode = "baseline"
            result.reason = "no_gate_context"
            logger.info("[RerankerGate] Reranking DENIED: no gate context provided")
            return result
        
        # Check all gate conditions
        failures = []
        
        # 1. Baseline plateau check
        # Baseline is still improving if trend >= threshold
        if context.baseline_precision_trend >= cls.BASELINE_PLATEAU_THRESHOLD:
            failures.append(f"baseline_still_improving({context.baseline_precision_trend:.3f}>={cls.BASELINE_PLATEAU_THRESHOLD})")
        else:
            result.baseline_plateau_check = True
        
        # 2. A/B improvement check
        if context.rerank_ab_improvement_at_5 < cls.AB_IMPROVEMENT_THRESHOLD:
            failures.append(f"ab_improvement_too_low({context.rerank_ab_improvement_at_5:.3f}<{cls.AB_IMPROVEMENT_THRESHOLD})")
        else:
            result.ab_improvement_check = True
        
        # 3. No recall regression
        if context.rerank_evidence_recall < context.baseline_evidence_recall:
            failures.append(f"recall_regression({context.rerank_evidence_recall:.2f}<{context.baseline_evidence_recall:.2f})")
        else:
            result.recall_regression_check = True
        
        # 4. Latency overhead check
        if context.rerank_latency_overhead_pct > cls.LATENCY_OVERHEAD_MAX_PCT:
            failures.append(f"latency_too_high({context.rerank_latency_overhead_pct:.1f}%>{cls.LATENCY_OVERHEAD_MAX_PCT}%)")
        else:
            result.latency_check = True
        
        # 5. Stability check
        if context.rerank_degeneracy_rate > cls.DEGENERACY_RATE_MAX_PCT:
            failures.append(f"degeneracy_too_high({context.rerank_degeneracy_rate:.1f}%>{cls.DEGENERACY_RATE_MAX_PCT}%)")
        else:
            result.stability_check = True
        
        # All checks must pass
        if failures:
            result.allowed = False
            result.mode = "baseline"
            result.reason = "; ".join(failures)
            logger.info(f"[RerankerGate] Reranking DENIED: {result.reason}")
        else:
            result.allowed = True
            result.mode = "gated"
            result.reason = "all_gates_passed"
            logger.info("[RerankerGate] Reranking ALLOWED: all gate conditions met")
        
        return result
    
    @classmethod
    def get_fast_mode_config(cls) -> Dict[str, Any]:
        """Get fast mode configuration when gate passes."""
        return {
            "max_candidates": cls.FAST_MODE_MAX_CANDIDATES,
            "timeout_s": cls.FAST_MODE_TIMEOUT_S,
        }


@dataclass
class SeedNode:
    """A seed node from vector search."""
    node_id: str
    score: float
    page_no: Optional[int]
    node_type: str
    label: Optional[str]
    section_hint: Optional[str]
    text_preview: str  # First N chars


@dataclass
class ExpandedNode:
    """An expanded node with its edge trace."""
    node_id: str
    node_type: str
    page_no: Optional[int]
    label: Optional[str]
    text_preview: str
    expansion_type: str  # "seed", "adjacent", "referenced", "explained_by"


@dataclass
class EdgeTrace:
    """Trace of an edge traversal."""
    from_node_id: str
    to_node_id: str
    edge_type: str


@dataclass
class InjectedSeed:
    """A seed node injected via structured-object detection."""
    node_id: str
    node_type: str
    label: Optional[str]
    section_hint: Optional[str]
    match_reason: str  # e.g., "label_match:Figure 1", "section_match:Appendix"


@dataclass
class QAResult:
    """Full result from QA pipeline with audit trail."""
    question: str
    doc_id: Optional[str] = None  # None means all documents were searched
    
    # LLM Query Rewriting results (optional, for multi-turn conversations)
    llm_rewrite_result: Optional[Dict[str, Any]] = None
    original_question: Optional[str] = None  # Before rewriting
    
    # Query normalization results
    normalized_queries: List[str] = field(default_factory=list)
    normalization_debug: Dict[str, Any] = field(default_factory=dict)
    
    # Vector search results
    seed_nodes: List[SeedNode] = field(default_factory=list)
    
    # Structured-object seed injection results
    injected_seeds: List[InjectedSeed] = field(default_factory=list)
    injection_targets_detected: List[str] = field(default_factory=list)  # ["Figure 1", "Table 2"]
    
    # Section boosting results
    detected_intent: Optional[str] = None
    boost_applied: Dict[str, int] = field(default_factory=dict)
    
    # Query intent classification results (CLAM-inspired)
    query_intent: Optional[str] = None  # "specific", "overview", "ambiguous", "impossible"
    query_intent_reason: Optional[str] = None
    
    # Metadata constraint parsing results
    metadata_constraints: Optional[Dict[str, Any]] = None
    metadata_filter_expr: Optional[str] = None
    
    # Metadata boosting results
    metadata_boost_applied: Dict[str, int] = field(default_factory=dict)
    metadata_boost_time_ms: float = 0.0
    
    # Conflict detection results
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    has_conflicts: bool = False
    
    # Reranking gate results
    rerank_allowed: bool = False
    rerank_mode: str = "baseline"  # "baseline" | "gated" | "forced"
    rerank_gate_reason: str = ""
    rerank_forced: bool = False
    
    # Reranking execution results
    rerank_enabled: bool = False
    rerank_time_ms: float = 0.0
    rerank_failed: bool = False
    rerank_degenerate: bool = False  # True if rerank scores collapsed (fallback to boosted)
    rerank_error: Optional[str] = None
    rerank_top10_before: List[Dict[str, Any]] = field(default_factory=list)
    rerank_top10_after: List[Dict[str, Any]] = field(default_factory=list)
    rerank_baseline_seed_ids: List[str] = field(default_factory=list)
    rerank_seed_ids: List[str] = field(default_factory=list)
    rerank_changed_seeds: bool = False
    
    # Rerank performance metrics (for gate evaluation)
    seed_precision_baseline: float = 0.0
    seed_precision_rerank: float = 0.0
    latency_overhead_pct: float = 0.0
    
    # Graph expansion results
    expanded_nodes: List[ExpandedNode] = field(default_factory=list)
    edge_traces: List[EdgeTrace] = field(default_factory=list)
    
    # Context packing results
    packed_context: str = ""
    context_node_ids: List[str] = field(default_factory=list)
    total_context_tokens: int = 0
    
    # Answer generation results
    answer: str = ""
    citations: List[Dict[str, Any]] = field(default_factory=list)
    model_id: str = ""
    
    # Timing
    normalization_time_ms: float = 0.0
    embedding_time_ms: float = 0.0
    search_time_ms: float = 0.0
    boosting_time_ms: float = 0.0
    expansion_time_ms: float = 0.0
    packing_time_ms: float = 0.0
    generation_time_ms: float = 0.0
    total_time_ms: float = 0.0
    
    # Status
    success: bool = True
    error: Optional[str] = None
    
    # Propagation Safety Mode audit (TRACK-inspired)
    propagation_safety_mode: bool = False
    propagation_safety_audit: Optional[Dict[str, Any]] = None
    
    # Prompt versioning (for auditability)
    prompt_version: str = ""

    # ACL audit trail
    acl_audit: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "question": self.question,
            "original_question": self.original_question,
            "doc_id": self.doc_id,
            "llm_rewrite": self.llm_rewrite_result,
            "normalization": {
                "queries": self.normalized_queries,
                "debug": self.normalization_debug,
                "detected_intent": self.detected_intent,
            },
            "query_intent": {
                "intent": self.query_intent,
                "reason": self.query_intent_reason,
            },
            "seed_nodes": [vars(n) for n in self.seed_nodes],
            "injected_seeds": [vars(s) for s in self.injected_seeds],
            "injection_targets_detected": self.injection_targets_detected,
            "boost_applied": self.boost_applied,
            "metadata": {
                "constraints": self.metadata_constraints,
                "filter_expr": self.metadata_filter_expr,
                "boost_applied": self.metadata_boost_applied,
                "boost_time_ms": self.metadata_boost_time_ms,
            },
            "conflicts": self.conflicts,
            "has_conflicts": self.has_conflicts,
            "rerank": {
                "allowed": self.rerank_allowed,
                "mode": self.rerank_mode,
                "gate_reason": self.rerank_gate_reason,
                "forced": self.rerank_forced,
                "enabled": self.rerank_enabled,
                "time_ms": self.rerank_time_ms,
                "failed": self.rerank_failed,
                "degenerate": self.rerank_degenerate,
                "error": self.rerank_error,
                "top10_before": self.rerank_top10_before,
                "top10_after": self.rerank_top10_after,
                "baseline_seed_ids": self.rerank_baseline_seed_ids,
                "seed_ids": self.rerank_seed_ids,
                "changed_seeds": self.rerank_changed_seeds,
                "seed_precision_baseline": self.seed_precision_baseline,
                "seed_precision_rerank": self.seed_precision_rerank,
                "latency_overhead_pct": self.latency_overhead_pct,
            },
            "expanded_nodes": [vars(n) for n in self.expanded_nodes],
            "edge_traces": [vars(e) for e in self.edge_traces],
            "packed_context": self.packed_context,
            "context_node_ids": self.context_node_ids,
            "total_context_tokens": self.total_context_tokens,
            "answer": self.answer,
            "citations": self.citations,
            "model_id": self.model_id,
            "timing": {
                "normalization_ms": self.normalization_time_ms,
                "embedding_ms": self.embedding_time_ms,
                "search_ms": self.search_time_ms,
                "boosting_ms": self.boosting_time_ms,
                "expansion_ms": self.expansion_time_ms,
                "packing_ms": self.packing_time_ms,
                "generation_ms": self.generation_time_ms,
                "total_ms": self.total_time_ms,
            },
            "success": self.success,
            "error": self.error,
            "propagation_safety_mode": self.propagation_safety_mode,
            "propagation_safety_audit": self.propagation_safety_audit,
            "prompt_version": self.prompt_version,
            "acl_audit": self.acl_audit,
        }


class QARunner:
    """Orchestrates the full QA pipeline."""
    
    TEXT_PREVIEW_LEN = 100
    
    # RERANKING DISABLED BY DEFAULT - regressed seed precision 0.42→0.30
    # Only enable via explicit --rerank flag after fixing section_hint issue
    RERANK_ENABLED_DEFAULT = False
    
    # Reranking constants (reduced for latency)
    RERANK_CANDIDATE_MAX = 15   # Top post-boost candidates to rerank (was 40, too slow)
    RERANK_TIMEOUT_S = 5        # Max LLM rerank timeout (was 30s, too slow)
    RERANK_ALLOWED_TYPES = {"chunk", "figure", "table"}
    
    # Degeneracy detection thresholds
    RERANK_MIN_UNIQUE_SCORES = 4   # Minimum unique scores before fallback
    RERANK_MIN_STDDEV = 8.0        # Minimum stddev before fallback
    RERANK_MIN_RANGE = 15          # Minimum (max-min) score range before fallback
    
    # Reranker prompts (with must_include_hint support)
    RERANK_SYSTEM_PROMPT = """You are a strict relevance ranker.
You do not generate answers.
You only score how useful each candidate is for answering the question.
You must not infer or hallucinate information.
Score only based on the candidate text provided."""

    RERANK_USER_PROMPT_TEMPLATE = """Question:
{question}

Intent:
{intent}

Instructions:
- Score each candidate from 0 to 100 based on how directly it helps answer the question.
- Prefer candidates that explicitly contain the requested information.
- If the question refers to a specific section (e.g., conclusion, appendix), prefer candidates from that section.
- If the question refers to a specific table or figure, strongly prefer candidates whose label matches.
- IMPORTANT: If a candidate has "must_include_hint": true, you MUST score it ≥90 and set must_include=true.
- Do not reward general background text.
- Do not assume missing information.

Candidates:
{candidates_json}

Return JSON only in the following format:

{{
  "ranked": [
    {{
      "node_id": "<string>",
      "score": <integer 0-100>,
      "must_include": <true|false>,
      "why": "<one short sentence>"
    }}
  ]
}}"""
    
    def __init__(
        self,
        db: Session,
        llm_client: Optional[OpenAIClient] = None,
        vector_index: Optional[GraphVectorIndex] = None,
        max_context_tokens: int = 8000,
        enable_normalization: bool = True,
        enable_boosting: bool = True,
        enable_rerank: bool = False,
        rerank_force: bool = False,
        rerank_gate_context: Optional[RerankerGateContext] = None,
        propagation_safety_config: Optional[Dict[str, Any]] = None,
        enable_llm_rewrite: Optional[bool] = None,
        entitlements: Optional["Entitlements"] = None,
    ):
        """Initialize QA runner.

        Args:
            db: Database session
            llm_client: OpenAI client (creates default if None)
            vector_index: Milvus vector index (creates default if None)
            max_context_tokens: Maximum tokens for context
            enable_normalization: Enable query normalization
            enable_boosting: Enable section-aware boosting
            enable_rerank: Enable reranking (subject to gate check)
            rerank_force: Force reranking via --rerank-force (bypasses gate)
            rerank_gate_context: Metrics for gate evaluation
            propagation_safety_config: Config dict for propagation_safety mode
            enable_llm_rewrite: Enable LLM query rewriting (uses config if None)
            entitlements: User entitlements for ACL enforcement (None = ACL disabled)
        """
        from app.acl.enforcer import ACLEnforcer

        self.db = db
        self.llm_client = llm_client or OpenAIClient()
        self.vector_index = vector_index or GraphVectorIndex()
        self.embedding_client = get_embedding_client()
        # INVARIANT:
        # All retrieval paths must share this enforcer instance; bypassing it leaks cross-tenant evidence.
        self.acl_enforcer = ACLEnforcer(db, entitlements)
        self.expander = GraphExpander(db, acl_enforcer=self.acl_enforcer)
        self.packer = ContextPacker(max_tokens=max_context_tokens)
        self.section_booster = SectionBooster()
        self.metadata_booster = MetadataBooster()
        
        self.enable_normalization = enable_normalization
        self.enable_boosting = enable_boosting
        self.enable_rerank = enable_rerank
        self.rerank_force = rerank_force
        self.rerank_gate_context = rerank_gate_context
        self.propagation_safety_config = propagation_safety_config
        
        # LLM Query Rewriter (optional, for multi-turn conversations)
        from app.qa.llm_rewriter import LLMQueryRewriter
        self.llm_rewriter = LLMQueryRewriter(enabled=enable_llm_rewrite)
        self.enable_llm_rewrite = self.llm_rewriter.enabled
        
        logger.info(
            f"QA Runner initialized (normalization={enable_normalization}, "
            f"boosting={enable_boosting}, rerank={enable_rerank}, rerank_force={rerank_force}, "
            f"llm_rewrite={self.enable_llm_rewrite})"
        )
    
    @classmethod
    def create_with_gate(
        cls,
        db: Session,
        enable_rerank: bool = True,
        **kwargs
    ) -> "QARunner":
        """Create QARunner with gate context loaded from persisted metrics.
        
        This is the recommended way to create a QARunner for production use
        when reranking is enabled. It automatically loads the gate metrics
        from the last A/B evaluation.
        
        Args:
            db: Database session
            enable_rerank: Whether to enable reranking (default True)
            **kwargs: Additional arguments passed to __init__
            
        Returns:
            QARunner instance with gate context populated
        """
        from app.qa.gate_metrics import load_gate_context
        
        gate_context = load_gate_context() if enable_rerank else None
        return cls(
            db=db,
            enable_rerank=enable_rerank,
            rerank_gate_context=gate_context,
            **kwargs
        )
    
    def run(
        self,
        doc_id: Optional[str],
        question: str,
        top_k: int = 5,
        version: Optional[int] = None,
        mode: str = "standard",
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> QAResult:
        """Run the full QA pipeline.
        
        Args:
            doc_id: Document ID to query (optional - searches all documents if None)
            question: User's question
            top_k: Number of seed chunks to retrieve
            version: Optional document version (uses latest if None)
            mode: "standard" or "propagation_safety"
            chat_history: Optional conversation history for multi-turn context
                          Format: [{"role": "user"|"assistant", "content": "..."}]
            
        Returns:
            QAResult with full audit trail
        """
        # ORDER DEPENDENCY:
        # Propagation mode uses separate retrieval logic; security/ranking fixes in standard mode must be mirrored there.
        # Dispatch to propagation_safety mode if requested
        if mode == "propagation_safety":
            return self._run_propagation_safety(doc_id, question, top_k, version)
        
        total_start = time.time()
        
        result = QAResult(question=question, doc_id=doc_id)
        request_id = uuid.uuid4().hex
        result.rerank_enabled = self.enable_rerank
        
        # Set prompt version for auditability
        from app.prompts import get_prompt_version
        result.prompt_version = get_prompt_version()
        
        try:
            # 0. LLM Query Rewrite (optional, for multi-turn conversations)
            # This resolves pronouns, coreferences, and ambiguous queries
            # Now with document context support for entity resolution
            if chat_history or self.llm_rewriter.should_rewrite(question):
                rewrite_result = self.llm_rewriter.rewrite(
                    question, 
                    chat_history,
                    doc_id=doc_id,
                    db=self.db,
                )
                result.llm_rewrite_result = rewrite_result.to_dict()
                
                if rewrite_result.used_llm and rewrite_result.rewritten_query != question:
                    result.original_question = question
                    question = rewrite_result.rewritten_query
                    result.question = question  # Update the result with rewritten query
                    logger.info(
                        "[QA] Query rewritten (orig_len=%d, new_len=%d, context=%s)",
                        len(result.original_question or ""),
                        len(question),
                        rewrite_result.doc_context_used,
                    )

            # 1. Query normalization
            if self.enable_normalization:
                logger.info("[QA] Normalizing query (len=%d)", len(question))
                start = time.time()
                normalized: NormalizedQuery = normalize_query(question, doc_id)
                result.normalization_time_ms = (time.time() - start) * 1000
                result.normalized_queries = normalized.normalized_queries
                result.normalization_debug = normalized.debug
                result.detected_intent = normalized.detected_intent
                
                logger.info(
                    f"[QA] Normalized into {len(normalized.normalized_queries)} queries, "
                    f"intent={normalized.detected_intent} in {result.normalization_time_ms:.0f}ms"
                )
                queries_to_embed = normalized.normalized_queries
            else:
                queries_to_embed = [question]
                result.normalized_queries = [question]
            
            # 2. Parse metadata constraints from question
            logger.info("[QA] Parsing metadata constraints...")
            constraints: ParsedConstraints = parse_constraints(question)
            result.metadata_constraints = constraints.to_dict()
            
            # Build filter expression for high-confidence constraints
            filter_expr = constraints.get_milvus_filter_expr()
            result.metadata_filter_expr = filter_expr
            
            if filter_expr:
                logger.info(f"[QA] Metadata filter: {filter_expr}")
            
            # 3. Embed all query variations
            logger.info(f"[QA] Embedding {len(queries_to_embed)} query variations...")
            start = time.time()
            all_vectors = []
            for q in queries_to_embed:
                vec, _ = self.embedding_client.embed_single(q)
                all_vectors.append(vec)
            result.embedding_time_ms = (time.time() - start) * 1000
            logger.info(f"[QA] Embedding took {result.embedding_time_ms:.0f}ms")
            
            # 4. Vector search for each query variation and merge
            # Apply metadata filter_expr to ALL collection searches
            search_top_k = self.RERANK_CANDIDATE_MAX if self.enable_rerank else top_k * 3
            doc_scope = f"doc {doc_id}" if doc_id else "all documents"
            logger.info(f"[QA] Searching for top-{search_top_k} chunks in {doc_scope}")
            start = time.time()
            
            # Detect document's collection version and use appropriate index
            doc_collection_version = self._get_doc_collection_version(doc_id)
            use_fallback = False
            
            if doc_collection_version is None:
                # Unknown version - use fallback search to try both v1 and v2
                logger.info(
                    f"[QA] Document has no embedded_collection_version, will use fallback search"
                )
                query_index = self.vector_index
                use_fallback = True
            elif doc_collection_version != self.vector_index.collection_version:
                logger.info(
                    f"[QA] Document indexed in {doc_collection_version}, "
                    f"creating version-specific index (default was {self.vector_index.collection_version})"
                )
                query_index = GraphVectorIndex(collection_version=doc_collection_version)
            else:
                query_index = self.vector_index
            
            # Search with each query vector (with metadata filter)
            all_search_results: Dict[str, Dict[str, Any]] = {}  # node_id -> best result
            for i, query_vector in enumerate(all_vectors):
                if use_fallback:
                    # Use fallback search to try both collection versions
                    search_results = query_index.search_with_fallback(
                        node_type="chunk",
                        query_vector=query_vector,
                        top_k=search_top_k,
                        doc_id_filter=doc_id,
                        filter_expr=filter_expr
                    )
                else:
                    search_results = query_index.search(
                        node_type="chunk",
                        query_vector=query_vector,
                        top_k=search_top_k,
                        doc_id_filter=doc_id,
                        filter_expr=filter_expr  # Apply metadata filter
                    )
                
                # Merge results, keeping best score for each node
                for sr in search_results:
                    node_id = sr["node_id"]
                    if node_id not in all_search_results or sr["score"] > all_search_results[node_id]["score"]:
                        all_search_results[node_id] = sr
                        all_search_results[node_id]["source_query_idx"] = i
            
            # Convert to list and sort by score
            merged_results = list(all_search_results.values())
            merged_results.sort(key=lambda x: x["score"], reverse=True)

            # SECURITY ASSUMPTION:
            # Milvus filtering is advisory; this post-search gate is the first hard ACL boundary in standard QA flow.
            # ACL enforcement: post-vector-search filter
            merged_results = self.acl_enforcer.filter_search_results(
                merged_results, stage="vector_search"
            )

            result.search_time_ms = (time.time() - start) * 1000
            logger.info(
                f"[QA] Search returned {len(merged_results)} unique results "
                f"(from {len(queries_to_embed)} queries) in {result.search_time_ms:.0f}ms"
            )
            
            # 4b. FALLBACK LADDER when vector search returns 0 results
            if not merged_results:
                self._log_zero_results_diagnostic(
                    doc_id=doc_id,
                    queries=queries_to_embed,
                    filter_expr=filter_expr,
                    collection_version=doc_collection_version or self.vector_index.collection_version
                )
                
                # Fallback 1: Retry without metadata filter
                if filter_expr:
                    # WARNING:
                    # This branch intentionally trades precision for recall; ACL checks must remain after every fallback stage.
                    logger.warning(f"[QA] Fallback 1: Retrying without filter_expr")
                    merged_results = self._search_without_filter(
                        doc_id=doc_id,
                        all_vectors=all_vectors,
                        query_index=query_index,
                        use_fallback=use_fallback,
                        top_k=search_top_k
                    )
                    # ACL enforcement: post-fallback-1 filter
                    merged_results = self.acl_enforcer.filter_search_results(
                        merged_results, stage="fallback_no_filter"
                    )
                    logger.info(f"[QA] Fallback 1 returned {len(merged_results)} results")
                
                # Fallback 2: Keyword/BM25 search in Postgres
                if not merged_results:
                    logger.warning(f"[QA] Fallback 2: Trying keyword search in Postgres")
                    merged_results = self._keyword_fallback_search(
                        doc_id=doc_id,
                        queries=queries_to_embed,
                        top_k=search_top_k
                    )
                    # ACL enforcement: post-fallback-2 filter
                    merged_results = self.acl_enforcer.filter_search_results(
                        merged_results, stage="fallback_keyword"
                    )
                    logger.info(f"[QA] Fallback 2 returned {len(merged_results)} results")
            
            # 4c. INTENT CLASSIFICATION - Check if query needs clarification
            # Based on CLAM/CLARINET research: detect ambiguous queries early
            from app.qa.constraint_parser import classify_query_with_details, QueryIntent
            
            intent_result = classify_query_with_details(
                query=question,
                retrieved_count=len(merged_results),
                has_specific_entity=bool(result.detected_intent)
            )
            result.query_intent = intent_result.intent.value
            result.query_intent_reason = intent_result.reason
            
            # If query needs clarification, return early with clarification response
            if intent_result.intent == QueryIntent.AMBIGUOUS and intent_result.clarify_prompt:
                logger.info(f"[QA] Query classified as AMBIGUOUS - returning clarification")
                result.answer = intent_result.clarify_prompt
                result.success = True
                result.total_time_ms = (time.time() - total_start) * 1000
                return result
            
            # 5. Get node metadata for boosting (needed for both metadata and section boosting)
            search_node_ids = [sr["node_id"] for sr in merged_results]
            nodes_metadata = self._get_nodes_metadata(search_node_ids)
            
            # 6. Metadata-aware boosting (soft boosts, capped at +0.40)
            if merged_results:
                logger.info("[QA] Applying metadata-aware boosting")
                start = time.time()
                
                metadata_boost_result: MetadataBoostResult = self.metadata_booster.boost_results(
                    results=merged_results,
                    constraints=constraints,
                    nodes_metadata=nodes_metadata
                )
                
                merged_results = metadata_boost_result.boosted_results
                result.metadata_boost_applied = metadata_boost_result.boost_applied
                result.metadata_boost_time_ms = (time.time() - start) * 1000
                
                logger.info(
                    f"[QA] Metadata boost applied: {metadata_boost_result.total_boosted} boosted, "
                    f"boosts={metadata_boost_result.boost_applied} in {result.metadata_boost_time_ms:.0f}ms"
                )
            
            # 7. Section-aware boosting
            if self.enable_boosting and merged_results:
                logger.info("[QA] Applying section-aware boosting")
                start = time.time()
                
                # Get total pages for the document
                total_pages = self._get_doc_total_pages(doc_id)
                
                # Apply boosting
                boost_result: SectionBoostResult = self.section_booster.boost_results(
                    results=merged_results,
                    query=question,
                    total_pages=total_pages,
                    nodes_metadata=nodes_metadata
                )
                
                merged_results = boost_result.boosted_results
                result.detected_intent = boost_result.intent or result.detected_intent
                result.boost_applied = boost_result.boost_applied
                result.boosting_time_ms = (time.time() - start) * 1000
                
                logger.info(
                    f"[QA] Section boost applied: intent={boost_result.intent}, "
                    f"boosts={boost_result.boost_applied} in {result.boosting_time_ms:.0f}ms"
                )
            
            # STRUCTURED-OBJECT SEED INJECTION (deterministic, before rerank)
            # Force-inject Figure/Table/Appendix nodes when explicitly mentioned
            from app.db.graph_models import Node as NodeModel
            
            merged_results, injected_audit, detected_targets = self.inject_structured_seeds(
                question=question,
                merged_results=merged_results,
                doc_id=doc_id,
                top_k=top_k
            )
            result.injected_seeds = injected_audit
            result.injection_targets_detected = detected_targets

            # ORDER DEPENDENCY:
            # Structured injection can add high-priority nodes; always re-apply ACL before seed selection/rerank.
            # ACL enforcement: post-seed-injection filter
            merged_results = self.acl_enforcer.filter_search_results(
                merged_results, stage="seed_injection"
            )

            # Rerank merged candidates before selecting seeds
            baseline_seed_ids = [sr["node_id"] for sr in merged_results[:top_k]]
            result.rerank_baseline_seed_ids = baseline_seed_ids
            
            # RERANKER GATE CHECK - determine if reranking should run
            gate_result = RerankerGate.should_rerank(
                context=self.rerank_gate_context,
                force=self.rerank_force
            )
            result.rerank_allowed = gate_result.allowed
            result.rerank_mode = gate_result.mode
            result.rerank_gate_reason = gate_result.reason
            result.rerank_forced = self.rerank_force
            
            # Only run reranking if gate allows AND explicitly enabled
            should_run_rerank = (
                self.enable_rerank and 
                merged_results and 
                (gate_result.allowed or self.rerank_force)
            )
            
            if should_run_rerank:
                logger.info(f"[QA] Reranking merged candidates (mode={gate_result.mode})")
                start = time.time()
                
                # Use fast mode config if gated (not forced)
                if gate_result.mode == "gated":
                    fast_config = RerankerGate.get_fast_mode_config()
                    rerank_max_candidates = fast_config["max_candidates"]
                    rerank_timeout = fast_config["timeout_s"]
                else:
                    rerank_max_candidates = self.RERANK_CANDIDATE_MAX
                    rerank_timeout = self.RERANK_TIMEOUT_S
                
                # Load node metadata for all candidates
                all_candidate_ids = [sr["node_id"] for sr in merged_results]
                nodes_by_id = {}
                if all_candidate_ids:
                    nodes_from_db = self.db.query(NodeModel).filter(
                        NodeModel.node_id.in_(all_candidate_ids)
                    ).all()
                    nodes_by_id = {n.node_id: n for n in nodes_from_db}
                
                # FIX B: Compute deterministic must_include_hint signals
                # Extract requested labels from question (Table X, Figure X)
                query_lower = question.lower()
                requested_labels = set()
                label_matches = re.findall(r'(table|figure|fig\.?)\s*(\d+)', query_lower)
                for prefix, num in label_matches:
                    if prefix.startswith("fig"):
                        requested_labels.add(f"figure {num}")
                    else:
                        requested_labels.add(f"table {num}")
                
                # Map intent to target sections for must_include_hint
                detected_intent = result.detected_intent or ""
                intent_section_map = {
                    "conclusion": {"conclusion"},
                    "appendix": {"appendix"},
                    "methodology": {"methodology"},
                    "evaluation": {"evaluation", "scoring", "appendix"},
                    "results": {"results", "discussion"},
                }
                target_sections = intent_section_map.get(detected_intent.lower(), set())
                
                # Build candidate set: top N after merge+boosting (fast mode if gated)
                rerank_candidates = []
                for sr in merged_results[:rerank_max_candidates]:
                    node_id = sr["node_id"]
                    node_type = sr.get("node_type", "chunk")
                    if node_type not in self.RERANK_ALLOWED_TYPES:
                        continue
                    
                    node = nodes_by_id.get(node_id)
                    meta = node.meta if node and node.meta else {}
                    section_hint = meta.get("section_hint")
                    label = node.label if node else None
                    text = ""
                    if node:
                        text = node.text_plain or node.text_md or ""
                    
                    # Compute must_include_hint (deterministic)
                    must_include_hint = False
                    label_lower = (label or "").lower()
                    section_lower = (section_hint or "").lower()
                    
                    # Label match: question mentions Table X/Figure X and candidate label matches
                    if requested_labels and any(req in label_lower for req in requested_labels):
                        must_include_hint = True
                    
                    # Section match: intent is conclusion/appendix and section_hint matches exactly
                    if target_sections and section_lower in target_sections:
                        must_include_hint = True
                    
                    rerank_candidates.append({
                        "node_id": node_id,
                        "node_type": node_type,
                        "page_no": node.page_no if node else sr.get("page_no"),
                        "section_hint": section_hint,
                        "label": label,
                        "text": (text or "")[:1000],
                        "must_include_hint": must_include_hint,  # Pass to LLM
                        "_boosted_score": sr.get("score", 0.0),
                    })
                
                # Log top 10 before rerank (MANDATORY per directive)
                result.rerank_top10_before = [
                    {
                        "node_id": c["node_id"],
                        "boosted_score": c["_boosted_score"],
                        "node_type": c["node_type"],
                        "section_hint": c["section_hint"],
                        "must_include_hint": c["must_include_hint"],
                    }
                    for c in rerank_candidates[:10]
                ]
                
                rerank_failed = False
                rerank_degenerate = False
                rerank_error = None
                rerank_map: Dict[str, Dict[str, Any]] = {}
                
                # Call LLM reranker
                try:
                    rerank_map = self._call_llm_reranker(
                        question=question,
                        intent=result.detected_intent or "unknown",
                        candidates=rerank_candidates
                    )
                    
                    # FIX A: Degeneracy detection
                    if rerank_map:
                        scores = [item.get("score", 50) for item in rerank_map.values()]
                        unique_scores = len(set(scores))
                        score_range = max(scores) - min(scores) if scores else 0
                        
                        # Compute stddev
                        if len(scores) > 1:
                            mean_score = sum(scores) / len(scores)
                            variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
                            stddev = variance ** 0.5
                        else:
                            stddev = 0.0
                        
                        # Check for degenerate output
                        if (unique_scores <= self.RERANK_MIN_UNIQUE_SCORES or 
                            stddev < self.RERANK_MIN_STDDEV or 
                            score_range < self.RERANK_MIN_RANGE):
                            logger.warning(
                                f"[QA] Rerank degenerate: unique_scores={unique_scores}, "
                                f"stddev={stddev:.1f}, range={score_range}. Falling back to boosted."
                            )
                            rerank_degenerate = True
                    else:
                        rerank_degenerate = True
                        logger.warning("[QA] Rerank returned no scores. Falling back to boosted.")
                        
                except Exception as e:
                    logger.warning(f"[QA] Reranker LLM call failed: {e}, falling back to boosted ranking")
                    rerank_failed = True
                    rerank_error = str(e)
                
                result.rerank_degenerate = rerank_degenerate
                
                # If degenerate or failed, skip rerank scoring
                if rerank_failed or rerank_degenerate:
                    # Fall back to boosted ranking (don't apply rerank scores)
                    pass
                else:
                    # Normalize boosted scores for blending
                    boosted_scores = [c["_boosted_score"] for c in rerank_candidates]
                    norm_min = min(boosted_scores) if boosted_scores else 0
                    norm_max = max(boosted_scores) if boosted_scores else 1
                    norm_range = norm_max - norm_min if norm_max != norm_min else 1.0
                    
                    # Compute final scores per directive formula:
                    # final_score = 0.7 * rerank_score + 0.3 * normalized_boosted_retrieval_score
                    reranked_results = []
                    for c in rerank_candidates:
                        node_id = c["node_id"]
                        rerank_item = rerank_map.get(node_id, {})
                        rerank_score = int(rerank_item.get("score", 50))  # Default 50 if not ranked
                        must_include = bool(rerank_item.get("must_include", False))
                        
                        # Honor must_include_hint if LLM didn't respect it
                        if c.get("must_include_hint") and not must_include:
                            must_include = True
                            rerank_score = max(rerank_score, 90)
                        
                        boosted_score = c["_boosted_score"]
                        normalized_boosted = 100.0 * (boosted_score - norm_min) / norm_range
                        
                        # DIRECTIVE FORMULA: 0.7 * rerank + 0.3 * boosted
                        final_score = 0.7 * rerank_score + 0.3 * normalized_boosted
                        
                        reranked_results.append({
                            "node_id": node_id,
                            "node_type": c["node_type"],
                            "page_no": c["page_no"],
                            "score": boosted_score,
                            "rerank_score": rerank_score,
                            "must_include": must_include,
                            "final_score": final_score,
                            "why": rerank_item.get("why", ""),
                        })
                    
                    # Sort by directive tie-breakers:
                    # 1. must_include=true first
                    # 2. higher final_score
                    # 3. higher rerank score
                    # 4. original boosted retrieval score
                    # 5. stable node_id sort
                    # FRAGILE COUPLING:
                    # Eval traces and rerank A/B comparisons assume this deterministic ordering contract.
                    reranked_results.sort(
                        key=lambda x: (
                            -int(x["must_include"]),
                            -x["final_score"],
                            -x["rerank_score"],
                            -x["score"],
                            x["node_id"]
                        )
                    )
                    merged_results = reranked_results
                
                result.rerank_time_ms = (time.time() - start) * 1000
                result.rerank_failed = rerank_failed
                result.rerank_error = rerank_error
                
                # Log top 10 after rerank (MANDATORY per directive)
                result.rerank_top10_after = [
                    {
                        "node_id": r["node_id"],
                        "rerank_score": r.get("rerank_score", 0),
                        "must_include": r.get("must_include", False),
                        "final_score": r.get("final_score", 0),
                        "why": r.get("why", ""),
                    }
                    for r in merged_results[:10]
                ]
                
                logger.info(
                    f"[QA] Reranking complete: {len(rerank_candidates)} candidates, "
                    f"failed={rerank_failed}, time={result.rerank_time_ms:.0f}ms"
                )
            else:
                # Reranking skipped - log reason
                if self.enable_rerank and not gate_result.allowed:
                    logger.info(
                        f"[QA] Reranking SKIPPED by gate: {gate_result.reason}"
                    )
                elif not self.enable_rerank:
                    logger.debug("[QA] Reranking disabled")
            
            # DATA INTEGRITY:
            # Truncating seeds here defines the expansion frontier; moving this cut earlier silently changes citations.
            # Take top_k after boosting/rerank
            merged_results = merged_results[:top_k]
            result.rerank_seed_ids = [sr["node_id"] for sr in merged_results]
            if result.rerank_baseline_seed_ids:
                result.rerank_changed_seeds = result.rerank_seed_ids != result.rerank_baseline_seed_ids
            
            # Fetch node texts from database
            search_node_ids = [sr["node_id"] for sr in merged_results]
            node_texts = {}
            node_labels = {}
            node_section_hints = {}
            if search_node_ids:
                nodes_from_db = self.db.query(NodeModel).filter(
                    NodeModel.node_id.in_(search_node_ids)
                ).all()
                for n in nodes_from_db:
                    node_texts[n.node_id] = n.text_plain or n.text_md or ""
                    node_labels[n.node_id] = n.label
                    node_section_hints[n.node_id] = (n.meta or {}).get("section_hint")
            
            # Convert to SeedNode objects
            seed_chunk_ids = []
            for sr in merged_results:
                node_id = sr["node_id"]
                text = node_texts.get(node_id, "")
                seed_node = SeedNode(
                    node_id=node_id,
                    score=sr.get("score", 0.0),
                    page_no=sr.get("page_no"),
                    node_type=sr.get("node_type", "chunk"),
                    label=node_labels.get(node_id),
                    section_hint=node_section_hints.get(node_id),
                    text_preview=text[:self.TEXT_PREVIEW_LEN]
                )
                result.seed_nodes.append(seed_node)
                seed_chunk_ids.append(node_id)
            
            if not seed_chunk_ids:
                result.success = False
                result.error = "No matching chunks found for question"
                result.total_time_ms = (time.time() - total_start) * 1000
                return result
            
            # 5. Graph expansion
            logger.info(f"[QA] Expanding {len(seed_chunk_ids)} seed chunks")
            start = time.time()
            expanded: ExpandedContext = self.expander.expand(
                seed_chunk_ids=seed_chunk_ids,
                doc_id=doc_id,
                version=version
            )
            result.expansion_time_ms = (time.time() - start) * 1000
            logger.info(
                f"[QA] Expansion: {len(expanded.seed_nodes)} seeds, "
                f"{len(expanded.adjacent_nodes)} adjacent, "
                f"{len(expanded.referenced_nodes)} refs, "
                f"{len(expanded.explained_by_nodes)} explained_by "
                f"in {result.expansion_time_ms:.0f}ms"
            )
            
            # Build expanded nodes and edge traces
            result.expanded_nodes, result.edge_traces = self._build_expansion_audit(expanded)
            
            # Conflict detection (threshold-gated) on expanded nodes
            # Collect all expanded nodes with their metadata
            expanded_node_dicts = self._collect_expanded_nodes_metadata(expanded)
            conflict_result: ConflictDetectionResult = detect_conflicts(
                cited_nodes=expanded_node_dicts,
                constraints=constraints
            )
            result.conflicts = [c.to_dict() for c in conflict_result.conflicts]
            result.has_conflicts = conflict_result.has_conflicts
            
            if conflict_result.has_conflicts:
                logger.info(
                    f"[QA] Detected {len(conflict_result.conflicts)} conflicts in cited sources"
                )
            
            # 6. Context packing
            logger.info("[QA] Packing context")
            start = time.time()
            packed: PackedContext = self.packer.pack(expanded, query=question)
            result.packing_time_ms = (time.time() - start) * 1000
            
            result.packed_context = packed.to_text(include_citations=True)
            result.context_node_ids = [b.citation.node_id for b in packed.blocks]
            result.total_context_tokens = packed.total_tokens_estimate
            logger.info(
                f"[QA] Packed {len(packed.blocks)} blocks, "
                f"~{packed.total_tokens_estimate} tokens in {result.packing_time_ms:.0f}ms"
            )
            
            # 7. Answer generation
            logger.info("[QA] Generating answer")
            start = time.time()
            answer_result: AnswerResult = self.llm_client.generate_answer(
                context=result.packed_context,
                question=question
            )
            result.generation_time_ms = (time.time() - start) * 1000
            
            result.answer = answer_result.answer
            
            # Hydrate citations with provenance anchoring data
            # Pass context_node_ids so we can look up doc_id from context nodes
            result.citations = self._hydrate_citations(
                citations=answer_result.citations,
                doc_id=doc_id,
                version=1,  # Default version, could be passed from document lookup
                context_node_ids=result.context_node_ids,
                answer_text=answer_result.answer,
                request_id=request_id,
            )
            # ACL enforcement: final citation filter (last line of defense)
            result.citations = self.acl_enforcer.filter_citations(result.citations)
            result.model_id = answer_result.model_id
            
            logger.info(
                f"[QA] Generated answer: {len(result.answer)} chars, "
                f"{len(result.citations)} citations in {result.generation_time_ms:.0f}ms"
            )
            
        except Exception as e:
            logger.error(f"[QA] Pipeline failed: {e}", exc_info=True)
            result.success = False
            result.error = str(e)

        # Attach ACL audit log to result
        acl_log = self.acl_enforcer.get_audit_log()
        if acl_log:
            result.acl_audit = acl_log

        result.total_time_ms = (time.time() - total_start) * 1000
        logger.info(f"[QA] Total pipeline time: {result.total_time_ms:.0f}ms")

        return result
    
    def _hydrate_citations(
        self,
        citations: List['Citation'],
        doc_id: Optional[str],
        version: int = 1,
        context_node_ids: Optional[List[str]] = None,
        answer_text: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Hydrate citations with provenance anchoring data from nodes.
        
        Looks up each cited node to add bbox, page_size, and anchor_snippet
        for enabling "click citation → open doc → highlight" in the frontend.
        
        Args:
            citations: List of Citation objects from LLM
            doc_id: Document ID for raw_url generation (None if searching all docs)
            version: Document version
            context_node_ids: Node IDs from the context (for fallback lookup by page)
            answer_text: Final answer text (used to create immutable citation snapshots)
            request_id: Request correlation ID for snapshot records
            
        Returns:
            List of citation dicts with full anchoring data
        """
        if not citations:
            return []
        
        # Batch fetch all cited nodes by their node_id
        node_ids = [c.node_id for c in citations]
        nodes = self.db.query(Node).filter(Node.node_id.in_(node_ids)).all()
        node_map = {n.node_id: n for n in nodes}
        
        # Also fetch context nodes for fallback page-based lookup
        # This handles cases where LLM outputs [seed:14] instead of actual node_id
        context_nodes = []
        page_to_node: Dict[int, 'Node'] = {}
        if context_node_ids:
            context_nodes = self.db.query(Node).filter(Node.node_id.in_(context_node_ids)).all()
            for n in context_nodes:
                if n.page_no and n.page_no not in page_to_node:
                    page_to_node[n.page_no] = n
        
        highlighting_enabled = get_settings().enable_cross_format_highlighting
        storage = get_storage_client() if highlighting_enabled else None
        graph_doc_cache: Dict[str, Optional[DocumentGraph]] = {}
        legacy_cache: Dict[str, Any] = {}
        selectors_cache: Dict[str, Dict[str, dict]] = {}
        source_map_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        attempted_backfill: set[str] = set()

        answer_hash = hashlib.sha256((answer_text or "").encode("utf-8")).hexdigest()
        request_id = request_id or uuid.uuid4().hex

        exact_count = 0
        unresolved_count = 0
        dropped_ungrounded = 0
        # D1 (audit H-4): citations must be grounded in the retrieved context.
        # When context node IDs are known, drop any citation the model emitted
        # that does not correspond to a packed-context node (hallucinated cite).
        context_id_set = set(context_node_ids or [])
        enforce_grounding = bool(context_id_set)
        resolve_latency_ms = 0.0
        snapshot_count = 0

        def infer_source_type(source_uri: Optional[str]) -> str:
            if not source_uri:
                return "txt"
            lower = source_uri.lower()
            ext_to_type = {
                ".pdf": "pdf",
                ".docx": "docx",
                ".pptx": "pptx",
                ".xlsx": "xlsx",
                ".html": "html",
                ".htm": "html",
                ".md": "md",
                ".markdown": "md",
                ".csv": "csv",
                ".txt": "txt",
            }
            for ext, src_type in ext_to_type.items():
                if lower.endswith(ext):
                    return src_type
            return "txt"

        hydrated_citations = []
        for c in citations:
            node = node_map.get(c.node_id)
            
            # DATA INTEGRITY:
            # Page-based fallback is heuristic only; node_id remains the authoritative citation identity.
            # Fallback: if node_id didn't match (e.g., "seed"), look up by page_no
            if not node and c.page_no and c.page_no in page_to_node:
                node = page_to_node[c.page_no]

            # D1 (audit H-4): a citation is grounded only if its node_id is in the
            # packed context, or its page maps to a context node. Otherwise the
            # model cited evidence that was never retrieved — drop it.
            if enforce_grounding and c.node_id not in context_id_set and (
                c.page_no is None or c.page_no not in page_to_node
            ):
                dropped_ungrounded += 1
                logger.warning(
                    "[QA] Dropping ungrounded citation node_id=%r page=%s "
                    "(not in retrieved context)",
                    c.node_id,
                    c.page_no,
                )
                continue

            # Use doc_id from node if not provided (searching all documents)
            citation_doc_id = doc_id
            citation_version = version
            citation_page_no = c.page_no
            if node:
                citation_doc_id = node.doc_id
                citation_version = node.version
                citation_page_no = c.page_no or node.page_no

            graph_doc: Optional[DocumentGraph] = None
            graph_key = f"{citation_doc_id}:{citation_version}" if citation_doc_id else ""
            if citation_doc_id:
                if graph_key not in graph_doc_cache:
                    graph_doc_cache[graph_key] = (
                        self.db.query(DocumentGraph)
                        .filter(
                            DocumentGraph.doc_id == citation_doc_id,
                            DocumentGraph.version == citation_version,
                        )
                        .first()
                    )
                graph_doc = graph_doc_cache.get(graph_key)

            if highlighting_enabled and graph_doc and graph_key not in attempted_backfill:
                attempted_backfill.add(graph_key)
                try:
                    # SIDE EFFECT:
                    # QA read path can trigger artifact writes; callers must tolerate backfill latency and partial failures.
                    if not (
                        storage.canonical_view_exists(graph_doc.doc_id, str(graph_doc.version))
                        and storage.source_map_exists(graph_doc.doc_id, str(graph_doc.version))
                        and storage.selectors_exist(graph_doc.doc_id, str(graph_doc.version))
                    ):
                        ensure_highlight_artifacts(self.db, graph_doc, storage=storage)
                        logger.info(f"[QA] selector_backfill_count +1 doc={graph_doc.doc_id}")
                except Exception as e:
                    logger.warning(f"[QA] Failed to backfill highlight artifacts for {graph_key}: {e}")

            legacy_doc = None
            source_type: Optional[str] = None
            mime_type: Optional[str] = None
            if graph_doc:
                if graph_key not in legacy_cache:
                    legacy_cache[graph_key] = find_legacy_for_graph(
                        self.db,
                        graph_doc.doc_id,
                        graph_doc.version,
                    )
                legacy_doc = legacy_cache.get(graph_key)
                source_type = legacy_doc.source_type if legacy_doc else infer_source_type(graph_doc.source_uri)
                mime_type = legacy_doc.mime_type if legacy_doc else None

            selector_bundle = None
            if node and node.meta:
                selector_bundle = node.meta.get("selector_bundle")

            if highlighting_enabled and not selector_bundle and graph_doc and node:
                selector_key = f"{graph_doc.doc_id}:{graph_doc.version}"
                if selector_key not in selectors_cache:
                    selectors_cache[selector_key] = {}
                    if storage.selectors_exist(graph_doc.doc_id, str(graph_doc.version)):
                        try:
                            selectors = storage.get_selectors(graph_doc.doc_id, str(graph_doc.version))
                            selectors_cache[selector_key] = {
                                s.get("node_id"): s for s in selectors if s.get("node_id")
                            }
                        except Exception as e:
                            logger.warning(
                                f"[QA] Failed to load selector cache for {selector_key}: {e}"
                            )
                selector_bundle = selectors_cache.get(selector_key, {}).get(node.node_id)

            resolve_result = {
                "resolve_status": "unresolved",
                "exact_text": None,
                "resolved_position": None,
                "reason": "missing_selector_bundle",
            }
            if highlighting_enabled and graph_doc and selector_bundle:
                start_resolve = time.time()
                # SECURITY ASSUMPTION:
                # strict=True and allow_fuzzy=False enforce fail-closed citation anchoring for audit/legal workflows.
                resolve_result = resolve_citation_selector(
                    storage=storage,
                    doc=graph_doc,
                    selector_bundle=selector_bundle,
                    strict=True,     # legal-grade fail-closed default
                    allow_fuzzy=False,
                )
                resolve_latency_ms += (time.time() - start_resolve) * 1000
            else:
                unresolved_count += 1

            if resolve_result.get("resolve_status") == "exact":
                exact_count += 1
            elif graph_doc and selector_bundle:
                unresolved_count += 1

            resolve_status = resolve_result.get("resolve_status", "unresolved")
            confidence_by_status = {
                "exact": 1.0,
                "fuzzy": 0.8,
                "unresolved": 0.0,
            }
            evidence_confidence = confidence_by_status.get(resolve_status, 0.0)
            
            citation_dict = {
                "node_id": c.node_id,
                "doc_id": citation_doc_id,
                "version": citation_version,
                "page_no": citation_page_no,
                "label": c.label,
                "raw_url": f"/v1/documents/{citation_doc_id}/raw" if citation_doc_id else None,
                "source_type": source_type,
                "mime_type": mime_type,
                "selector_bundle": selector_bundle,
                "resolve_status": resolve_status,
                "resolve_reason": resolve_result.get("reason"),
                "canonical_view_url": (
                    f"/v1/documents/{citation_doc_id}/canonical"
                    if (citation_doc_id and highlighting_enabled)
                    else None
                ),
                "source_map_url": (
                    f"/v1/documents/{citation_doc_id}/source-map"
                    if (citation_doc_id and highlighting_enabled)
                    else None
                ),
            }
            
            # Add anchoring data from node if found
            if node:
                # bbox from node (populated during ingestion for chunks with text spans)
                if node.bbox:
                    citation_dict["bbox"] = node.bbox
                
                # Get page_size and anchor_snippet from node.meta
                if node.meta:
                    if node.meta.get("page_size"):
                        citation_dict["page_size"] = node.meta["page_size"]
                    if node.meta.get("anchor_snippet"):
                        citation_dict["anchor_snippet"] = node.meta["anchor_snippet"]
                    if node.meta.get("normalization"):
                        citation_dict["normalization"] = node.meta["normalization"]
                
                # Fallback: generate anchor_snippet from text_plain if not in meta
                if "anchor_snippet" not in citation_dict and node.text_plain:
                    citation_dict["anchor_snippet"] = node.text_plain[:150].strip()

            # Keep text_quote exact snippet available for frontend fallback.
            if selector_bundle and selector_bundle.get("text_quote", {}).get("exact"):
                citation_dict["text"] = selector_bundle["text_quote"]["exact"]
                if "anchor_snippet" not in citation_dict:
                    citation_dict["anchor_snippet"] = selector_bundle["text_quote"]["exact"][:150]

            citation_dict["evidence_spans"] = build_evidence_spans(
                provided_spans=getattr(c, "evidence_spans", None),
                doc_id=citation_doc_id,
                page_index=citation_page_no,
                quote_text=(
                    citation_dict.get("text")
                    or c.text_snippet
                    or citation_dict.get("anchor_snippet")
                ),
                selector_bundle=selector_bundle,
                bbox=citation_dict.get("bbox"),
                page_size=citation_dict.get("page_size"),
                confidence=evidence_confidence,
                source_section=node.label if node and node.label else c.label,
            )

            evidence_verification: List[Dict[str, Any]] = []
            if highlighting_enabled and graph_doc and citation_dict["evidence_spans"]:
                source_map_key = f"{graph_doc.doc_id}:{graph_doc.version}"
                if source_map_key not in source_map_cache:
                    source_map_cache[source_map_key] = None
                    if storage.source_map_exists(graph_doc.doc_id, str(graph_doc.version)):
                        try:
                            source_map_cache[source_map_key] = storage.get_source_map(
                                graph_doc.doc_id,
                                str(graph_doc.version),
                            )
                        except Exception as e:
                            logger.warning(
                                f"[QA] Failed to load source map for evidence verification {source_map_key}: {e}"
                            )
                source_map = source_map_cache.get(source_map_key)
                if source_map:
                    for span in citation_dict["evidence_spans"]:
                        try:
                            verification = verify_evidence_span(
                                doc_id=str(span.get("doc_id") or citation_doc_id or ""),
                                page_index=int(span.get("page_index") or citation_page_no or 0),
                                quote_text=str(span.get("quote_text") or ""),
                                locator=span.get("locator"),
                                source_map=source_map,
                                allow_fuzzy=False,
                            )
                        except Exception as e:
                            verification = {
                                "status": "NOT_FOUND",
                                "matched_locator": None,
                                "confidence": 0.0,
                                "reason": f"verification_error:{type(e).__name__}",
                            }
                        evidence_verification.append(verification)
                else:
                    evidence_verification.append(
                        {
                            "status": "NOT_FOUND",
                            "matched_locator": None,
                            "confidence": 0.0,
                            "reason": "missing_source_map",
                        }
                    )

            citation_dict["evidence_verification"] = evidence_verification

            found_verification = next(
                (v for v in evidence_verification if v.get("status") == "FOUND"),
                None,
            )
            if highlighting_enabled and not found_verification:
                citation_dict["resolve_status"] = "unresolved"
                citation_dict["resolve_reason"] = "Evidence not found on cited page"
                citation_dict.pop("bbox", None)
                citation_dict.pop("page_size", None)
                citation_dict.pop("anchor_snippet", None)
                citation_dict.pop("text", None)
            elif found_verification:
                matched_locator = found_verification.get("matched_locator") or {}
                if (
                    selector_bundle
                    and matched_locator.get("type") == "text_offsets"
                    and isinstance(matched_locator.get("start"), int)
                    and isinstance(matched_locator.get("end"), int)
                ):
                    updated_bundle = dict(selector_bundle)
                    updated_bundle["text_position"] = {
                        "start": matched_locator["start"],
                        "end": matched_locator["end"],
                    }
                    citation_dict["selector_bundle"] = updated_bundle

            snapshot_id: Optional[str] = None
            if highlighting_enabled and graph_doc and selector_bundle:
                try:
                    snapshot_uuid = uuid.uuid4()
                    # DATA INTEGRITY:
                    # Snapshot hash tuple (answer_hash/content_hash) is used for replayability and tamper detection.
                    snapshot = CitationSnapshot(
                        snapshot_id=snapshot_uuid,
                        request_id=request_id,
                        doc_id=graph_doc.doc_id,
                        version=graph_doc.version,
                        node_id=node.node_id if node else c.node_id,
                        selector_bundle=selector_bundle,
                        exact_text=resolve_result.get("exact_text"),
                        answer_hash=answer_hash,
                        content_hash=graph_doc.content_hash,
                    )
                    self.db.add(snapshot)
                    snapshot_id = str(snapshot_uuid)
                    snapshot_count += 1
                except Exception as e:
                    logger.warning(f"[QA] Failed to create citation snapshot for {c.node_id}: {e}")
            citation_dict["snapshot_id"] = snapshot_id
            
            hydrated_citations.append(citation_dict)

        if snapshot_count > 0:
            try:
                # SIDE EFFECT:
                # Snapshot persistence is best-effort and must not block answer delivery on commit failures.
                self.db.commit()
            except Exception as e:
                logger.warning(f"[QA] Failed to commit citation snapshots: {e}")
                self.db.rollback()

        with_bbox = sum(1 for item in hydrated_citations if item.get("bbox"))
        with_snippet = sum(1 for item in hydrated_citations if item.get("anchor_snippet"))
        logger.info(
            f"[QA] Hydrated {len(hydrated_citations)} citations: "
            f"{with_bbox} with bbox, {with_snippet} with anchor_snippet, "
            f"{dropped_ungrounded} dropped as ungrounded"
        )
        logger.info(
            "[QA] Highlight metrics: "
            f"highlight_resolve_exact_count={exact_count}, "
            f"highlight_resolve_unresolved_count={unresolved_count}, "
            f"highlight_resolve_latency_ms={resolve_latency_ms:.2f}, "
            f"citation_snapshot_created_count={snapshot_count}"
        )
        
        return hydrated_citations
    
    def _log_zero_results_diagnostic(
        self,
        doc_id: Optional[str],
        queries: List[str],
        filter_expr: Optional[str],
        collection_version: str
    ):
        """Log diagnostic info when vector search returns 0 results."""
        from pymilvus import connections, Collection, utility
        import os
        
        logger.warning("=" * 60)
        logger.warning("[QA] ZERO RESULTS DIAGNOSTIC")
        logger.warning("=" * 60)
        logger.warning(f"  doc_id: {doc_id}")
        logger.warning(f"  collection_version: {collection_version}")
        logger.warning(f"  filter_expr: {filter_expr}")
        logger.warning(f"  queries: {queries}")
        
        # Count vectors in Milvus for this doc
        try:
            host = os.getenv("MILVUS_HOST", "localhost")
            port = os.getenv("MILVUS_PORT", "19530")

            alias = "diag_zero"
            # Always (re)connect this alias to avoid stale/disconnected handles.
            connections.connect(alias, host=host, port=port, timeout=5)
            
            coll_name = f"graph_chunks_{collection_version}"
            if coll_name in utility.list_collections(using=alias):
                col = Collection(coll_name, using=alias)
                col.load()
                if doc_id:
                    res = col.query(
                        expr=f'doc_id == "{doc_id}"',
                        output_fields=["node_id"],
                        limit=10000,
                        consistency_level="Eventually"
                    )
                    logger.warning(f"  Milvus vectors for doc: {len(res)}")
                else:
                    logger.warning(f"  Milvus vectors total in collection: {col.num_entities}")
            
            connections.disconnect(alias)
        except Exception as e:
            logger.warning(f"  Milvus diagnostic failed: {e}")
        
        # Count nodes in Postgres
        try:
            from app.db.graph_models import Node
            query = self.db.query(Node).filter(Node.node_type == "chunk")
            if doc_id:
                query = query.filter(Node.doc_id == doc_id)
                chunks = query.count()
                logger.warning(f"  Postgres chunks for doc: {chunks}")
            else:
                chunks = query.count()
                logger.warning(f"  Postgres chunks total: {chunks}")
        except Exception as e:
            logger.warning(f"  Postgres diagnostic failed: {e}")
        
        logger.warning("=" * 60)
    
    def _search_without_filter(
        self,
        doc_id: Optional[str],
        all_vectors: List[List[float]],
        query_index: GraphVectorIndex,
        use_fallback: bool,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """Retry vector search without metadata filter_expr."""
        all_search_results: Dict[str, Dict[str, Any]] = {}
        
        for i, query_vector in enumerate(all_vectors):
            if use_fallback:
                search_results = query_index.search_with_fallback(
                    node_type="chunk",
                    query_vector=query_vector,
                    top_k=top_k,
                    doc_id_filter=doc_id,
                    filter_expr=None  # No filter
                )
            else:
                search_results = query_index.search(
                    node_type="chunk",
                    query_vector=query_vector,
                    top_k=top_k,
                    doc_id_filter=doc_id,
                    filter_expr=None  # No filter
                )
            
            for sr in search_results:
                node_id = sr["node_id"]
                if node_id not in all_search_results or sr["score"] > all_search_results[node_id]["score"]:
                    all_search_results[node_id] = sr
                    all_search_results[node_id]["source_query_idx"] = i
        
        results = list(all_search_results.values())
        results.sort(key=lambda x: x["score"], reverse=True)
        return results
    
    def _keyword_fallback_search(
        self,
        doc_id: Optional[str],
        queries: List[str],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """Keyword/BM25 fallback search in Postgres when vector search fails.
        
        Uses simple ILIKE matching on text_plain.
        """
        from app.db.graph_models import Node
        from sqlalchemy import or_, func
        
        # Extract keywords from queries (simple tokenization)
        keywords = set()
        for q in queries:
            # Split on whitespace and filter short words
            words = [w.strip().lower() for w in q.split() if len(w.strip()) >= 4]
            keywords.update(words)
        
        if not keywords:
            return []
        
        # Build ILIKE conditions
        conditions = [
            Node.text_plain.ilike(f"%{kw}%") for kw in list(keywords)[:10]  # Limit to 10 keywords
        ]
        
        # PERFORMANCE COUPLING:
        # Keyword fallback is full-text scan-like; keep keyword cap and top_k bounds to protect tail latency.
        # Build query with ACL scoping
        query = self.db.query(Node).filter(
            Node.node_type == "chunk",
            or_(*conditions)
        )
        if doc_id:
            query = query.filter(Node.doc_id == doc_id)
        # Scope by accessible doc_ids when ACL is enabled
        accessible = self.acl_enforcer.get_accessible_doc_ids()
        if accessible is not None:
            query = query.filter(Node.doc_id.in_(accessible))
        nodes = query.limit(top_k).all()
        
        # Convert to search result format
        results = []
        for node in nodes:
            # Count keyword matches for scoring
            text_lower = (node.text_plain or "").lower()
            match_count = sum(1 for kw in keywords if kw in text_lower)
            
            results.append({
                "node_id": node.node_id,
                "score": 0.5 + (match_count * 0.1),  # Base score + keyword bonus
                "page_no": node.page_no,
                "node_type": node.node_type,
                "section_hint": (node.meta or {}).get("section_hint"),
                "label": node.label,
                "text": (node.text_plain or node.text_md or "")[:500],
                "fallback_source": "keyword"
            })
        
        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"[QA] Keyword fallback found {len(results)} results with keywords: {list(keywords)[:5]}")
        
        return results
    
    def _call_llm_reranker(
        self,
        question: str,
        intent: str,
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Call LLM to rerank candidates using exact directive prompt.
        
        Args:
            question: Original user question (not rewritten)
            intent: Detected intent from normalizer
            candidates: List of candidate dicts with node_id, node_type, page_no,
                       section_hint, label, text
        
        Returns:
            Dict mapping node_id -> {score, must_include, why}
        
        Raises:
            Exception if LLM call fails or returns invalid JSON
        """
        from app.config import get_settings
        
        settings = get_settings()
        
        # Build candidates JSON for prompt (per directive contract + must_include_hint)
        candidates_for_prompt = []
        for c in candidates:
            candidates_for_prompt.append({
                "node_id": c["node_id"],
                "node_type": c["node_type"],
                "page_no": c["page_no"],
                "section_hint": c["section_hint"],
                "label": c["label"],
                "text": c["text"],
                "must_include_hint": c.get("must_include_hint", False)  # Deterministic anchor
            })
        
        candidates_json = json.dumps(candidates_for_prompt, indent=2)
        
        user_prompt = self.RERANK_USER_PROMPT_TEMPLATE.format(
            question=question,
            intent=intent,
            candidates_json=candidates_json
        )
        
        # FRAGILE COUPLING:
        # Reranker relies on strict JSON output schema; prompt/field changes require coordinated parser updates.
        # Call OpenAI API directly with timeout
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4o-mini",  # Fast model for reranking
            "messages": [
                {"role": "system", "content": self.RERANK_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"}
        }
        
        with httpx.Client(timeout=self.RERANK_TIMEOUT_S) as client:
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        # Parse JSON response
        parsed = json.loads(content)
        ranked_list = parsed.get("ranked", [])
        
        # Build mapping
        rerank_map = {}
        for item in ranked_list:
            node_id = item.get("node_id")
            if node_id:
                rerank_map[node_id] = {
                    "score": int(item.get("score", 50)),
                    "must_include": bool(item.get("must_include", False)),
                    "why": item.get("why", "")
                }
        
        logger.info(f"[QA] LLM reranker returned scores for {len(rerank_map)} candidates")
        return rerank_map
    
    def _get_doc_total_pages(self, doc_id: str) -> int:
        """Get total pages for a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Total pages (0 if unknown)
        """
        from app.db.graph_models import DocumentGraph
        doc = self.db.query(DocumentGraph).filter(
            DocumentGraph.doc_id == doc_id
        ).first()
        
        if doc and doc.meta:
            return doc.meta.get("total_pages", 0)
        return 0
    
    def _get_doc_collection_version(self, doc_id: Optional[str]) -> Optional[str]:
        """Get the Milvus collection version used when document was embedded.
        
        This enables querying the correct collection (v1 or v2) based on
        where the document's vectors were actually stored.
        
        Args:
            doc_id: Document ID (None means search all documents)
            
        Returns:
            Collection version ("v1" or "v2") or None if unknown/all docs
        """
        if not doc_id:
            # Searching all documents - use default collection (v2)
            return None
            
        from app.db.graph_models import DocumentGraph
        doc = self.db.query(DocumentGraph).filter(
            DocumentGraph.doc_id == doc_id
        ).first()
        
        if doc and doc.embedded_collection_version:
            return doc.embedded_collection_version
        return None
    
    def _get_nodes_metadata(self, node_ids: List[str]) -> Dict[str, Dict]:
        """Get metadata for nodes.
        
        Args:
            node_ids: List of node IDs
            
        Returns:
            Dict of node_id -> meta dict
        """
        from app.db.graph_models import Node as NodeModel
        
        if not node_ids:
            return {}
        
        nodes = self.db.query(NodeModel).filter(
            NodeModel.node_id.in_(node_ids)
        ).all()
        
        return {n.node_id: n.meta or {} for n in nodes}
    
    # ==========================================================================
    # STRUCTURED-OBJECT SEED INJECTION (deterministic, no LLM)
    # ==========================================================================
    
    # Max injected seeds to force into top-K
    MAX_INJECTED_SEEDS = 2
    
    # Regex patterns for structured object mentions
    FIGURE_PATTERN = re.compile(r'(?:Figure|Fig\.?)\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
    TABLE_PATTERN = re.compile(r'(?:Table|Tab\.?)\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
    APPENDIX_PATTERN = re.compile(r'Appendix\s*([A-Za-z])', re.IGNORECASE)
    SECTION_PATTERN = re.compile(
        r'\b(Conclusion|Methodology|Introduction|Discussion|Evaluation|Results|Appendix)\b',
        re.IGNORECASE
    )
    
    def _detect_structured_targets(self, question: str) -> Dict[str, List[str]]:
        """Detect Figure/Table/Appendix/Section mentions in question.
        
        Args:
            question: User question text
            
        Returns:
            Dict with keys 'figures', 'tables', 'appendices', 'sections'
            containing normalized target strings
        """
        targets = {
            "figures": [],
            "tables": [],
            "appendices": [],
            "sections": []
        }
        
        # Detect Figure X
        for match in self.FIGURE_PATTERN.finditer(question):
            num = match.group(1)
            targets["figures"].append(f"Figure {num}")
        
        # Detect Table X
        for match in self.TABLE_PATTERN.finditer(question):
            num = match.group(1)
            targets["tables"].append(f"Table {num}")
        
        # Detect Appendix X
        for match in self.APPENDIX_PATTERN.finditer(question):
            letter = match.group(1).upper()
            targets["appendices"].append(f"Appendix {letter}")
        
        # Detect section mentions
        for match in self.SECTION_PATTERN.finditer(question):
            section = match.group(1).title()  # "conclusion" -> "Conclusion"
            if section not in targets["sections"]:
                targets["sections"].append(section)
        
        return targets
    
    def _query_nodes_by_label(
        self,
        doc_id: str,
        labels: List[str],
        node_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Query nodes by label (exact or fuzzy match).
        
        Args:
            doc_id: Document ID to filter
            labels: List of labels to search for (e.g., ["Figure 1", "Table 2"])
            node_types: Optional node type filter
            
        Returns:
            List of matching node dicts with node_id, node_type, label, section_hint
        """
        from app.db.graph_models import Node as NodeModel
        from sqlalchemy import or_, func
        
        if not labels:
            return []
        
        # Build query
        query = self.db.query(NodeModel).filter(NodeModel.doc_id == doc_id)
        
        if node_types:
            from app.db.graph_models import NodeType
            type_enums = [NodeType(t) for t in node_types if t in [e.value for e in NodeType]]
            if type_enums:
                query = query.filter(NodeModel.node_type.in_(type_enums))
        
        # Build OR conditions for label matching
        label_conditions = []
        for label in labels:
            # Exact match (case-insensitive)
            label_conditions.append(func.lower(NodeModel.label) == label.lower())
            # Also try without spaces (e.g., "Figure1" vs "Figure 1")
            label_no_space = label.replace(" ", "")
            label_conditions.append(func.lower(NodeModel.label) == label_no_space.lower())
        
        query = query.filter(or_(*label_conditions))
        
        nodes = query.all()
        
        results = []
        for node in nodes:
            meta = node.meta or {}
            results.append({
                "node_id": node.node_id,
                "node_type": node.node_type.value if hasattr(node.node_type, 'value') else str(node.node_type),
                "label": node.label,
                "section_hint": meta.get("section_hint"),
                "page_no": node.page_no,
            })
        
        return results
    
    def _query_nodes_by_section(
        self,
        doc_id: str,
        sections: List[str],
        appendix_letters: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Query chunk nodes by section_hint.
        
        Args:
            doc_id: Document ID to filter
            sections: List of section names (e.g., ["Conclusion", "Methodology"])
            appendix_letters: Optional appendix letters (e.g., ["A", "B", "C"])
            
        Returns:
            List of matching node dicts (ordered by relevance)
        """
        from app.db.graph_models import Node as NodeModel, NodeType
        from sqlalchemy import or_, func
        
        if not sections and not appendix_letters:
            return []
        
        # Query chunk nodes with matching section_hint
        query = self.db.query(NodeModel).filter(
            NodeModel.doc_id == doc_id,
            NodeModel.node_type == NodeType.chunk
        )
        
        # Build section conditions
        conditions = []
        for section in sections:
            # meta.section_hint contains section name (case-insensitive)
            conditions.append(
                func.lower(NodeModel.meta['section_hint'].astext) == section.lower()
            )
        
        # For appendix letters, look for "Appendix" in section_hint AND letter in text
        if appendix_letters:
            for letter in appendix_letters:
                # Appendix section + text contains "Appendix X"
                conditions.append(
                    NodeModel.meta['section_hint'].astext.ilike('%appendix%')
                )
        
        if conditions:
            query = query.filter(or_(*conditions))
        
        # Order by page number (earlier sections often have more context)
        query = query.order_by(NodeModel.page_no)
        
        # Limit to prevent huge result sets
        nodes = query.limit(10).all()
        
        results = []
        for node in nodes:
            meta = node.meta or {}
            text_preview = (node.text_plain or "")[:200]
            
            # For appendix letters, verify text actually contains "Appendix X"
            if appendix_letters:
                has_appendix = any(
                    f"Appendix {letter}" in (node.text_plain or "") or
                    f"Appendix {letter}" in (node.text_md or "")
                    for letter in appendix_letters
                )
                if not has_appendix and "appendix" not in text_preview.lower():
                    continue  # Skip if doesn't mention the specific appendix
            
            results.append({
                "node_id": node.node_id,
                "node_type": "chunk",
                "label": node.label,
                "section_hint": meta.get("section_hint"),
                "page_no": node.page_no,
            })
        
        return results
    
    def inject_structured_seeds(
        self,
        question: str,
        merged_results: List[Dict[str, Any]],
        doc_id: str,
        top_k: int = 5
    ) -> tuple[List[Dict[str, Any]], List[InjectedSeed], List[str]]:
        """Inject structured-object seeds (Figure/Table/Appendix) into results.
        
        When a question explicitly mentions Figure X, Table Y, or Appendix Z,
        force-inject matching nodes into the seed set to guarantee retrieval.
        
        Args:
            question: User question
            merged_results: Current merged/boosted results list
            doc_id: Document ID
            top_k: Number of seeds to select
            
        Returns:
            Tuple of:
            - Modified merged_results with injected seeds at high priority
            - List of InjectedSeed objects for audit trail
            - List of detected target strings
        """
        # 1. Detect structured targets in question
        targets = self._detect_structured_targets(question)
        
        detected_targets = []
        detected_targets.extend(targets["figures"])
        detected_targets.extend(targets["tables"])
        detected_targets.extend([f"Appendix {a.split()[-1]}" for a in targets["appendices"]])
        detected_targets.extend([f"Section: {s}" for s in targets["sections"]])
        
        if not any(targets.values()):
            logger.debug("[QA] No structured targets detected in question")
            return merged_results, [], []
        
        logger.info(f"[QA] Detected structured targets: {detected_targets}")
        
        # 2. Query for matching nodes
        injected_nodes: List[Dict[str, Any]] = []
        injected_audit: List[InjectedSeed] = []
        
        # Track existing node_ids to avoid duplicates
        existing_ids = {r["node_id"] for r in merged_results}
        
        # Query Figure/Table nodes by label
        figure_table_labels = targets["figures"] + targets["tables"]
        if figure_table_labels:
            label_matches = self._query_nodes_by_label(
                doc_id=doc_id,
                labels=figure_table_labels,
                node_types=["figure", "table"]
            )
            for match in label_matches:
                if match["node_id"] not in existing_ids and len(injected_nodes) < self.MAX_INJECTED_SEEDS:
                    # Add with very high score to ensure inclusion
                    match["score"] = 10.0  # High priority
                    match["injected"] = True
                    injected_nodes.append(match)
                    existing_ids.add(match["node_id"])
                    
                    injected_audit.append(InjectedSeed(
                        node_id=match["node_id"],
                        node_type=match["node_type"],
                        label=match["label"],
                        section_hint=match["section_hint"],
                        match_reason=f"label_match:{match['label']}"
                    ))
                    logger.info(f"[QA] Injecting {match['node_type']} node: {match['label']} ({match['node_id'][:8]})")
        
        # Query Section/Appendix chunks
        appendix_letters = [a.split()[-1] for a in targets["appendices"]] if targets["appendices"] else []
        if targets["sections"] or appendix_letters:
            section_matches = self._query_nodes_by_section(
                doc_id=doc_id,
                sections=targets["sections"],
                appendix_letters=appendix_letters
            )
            for match in section_matches:
                if match["node_id"] not in existing_ids and len(injected_nodes) < self.MAX_INJECTED_SEEDS:
                    match["score"] = 9.0  # High priority (slightly lower than label matches)
                    match["injected"] = True
                    injected_nodes.append(match)
                    existing_ids.add(match["node_id"])
                    
                    reason = f"section_match:{match['section_hint']}"
                    if appendix_letters:
                        reason = f"appendix_match:Appendix {appendix_letters[0]}"
                    
                    injected_audit.append(InjectedSeed(
                        node_id=match["node_id"],
                        node_type=match["node_type"],
                        label=match["label"],
                        section_hint=match["section_hint"],
                        match_reason=reason
                    ))
                    logger.info(f"[QA] Injecting section chunk: {match['section_hint']} ({match['node_id'][:8]})")
        
        if not injected_nodes:
            logger.warning(f"[QA] No matching nodes found for targets: {detected_targets}")
            return merged_results, [], detected_targets
        
        # ORDER DEPENDENCY:
        # Injected seeds must be prepended to reserve top-K slots for explicit Figure/Table/Appendix requests.
        # 3. Merge injected nodes at the front of results
        # Injected nodes get priority slots (up to MAX_INJECTED_SEEDS)
        final_results = injected_nodes.copy()
        
        # Add remaining results, skipping any that were injected
        injected_ids = {n["node_id"] for n in injected_nodes}
        for r in merged_results:
            if r["node_id"] not in injected_ids:
                final_results.append(r)
        
        logger.info(
            f"[QA] Structured seed injection: {len(injected_nodes)} nodes injected, "
            f"{len(final_results)} total candidates"
        )
        
        return final_results, injected_audit, detected_targets
    
    def _build_expansion_audit(
        self,
        expanded: ExpandedContext
    ) -> tuple[List[ExpandedNode], List[EdgeTrace]]:
        """Build expanded nodes and edge traces from expansion result.
        
        Args:
            expanded: Expansion result
            
        Returns:
            Tuple of (expanded_nodes, edge_traces)
        """
        expanded_nodes: List[ExpandedNode] = []
        edge_traces: List[EdgeTrace] = []
        # WARNING:
        # Edge traces here are inferred audit artifacts, not canonical persisted graph edges.
        
        def get_node_type_str(node) -> str:
            if hasattr(node.node_type, 'value'):
                return node.node_type.value
            return str(node.node_type)
        
        # Process seed nodes
        for node in expanded.seed_nodes:
            expanded_nodes.append(ExpandedNode(
                node_id=node.node_id,
                node_type=get_node_type_str(node),
                page_no=node.page_no,
                label=node.label,
                text_preview=(node.text_plain or "")[:self.TEXT_PREVIEW_LEN],
                expansion_type="seed"
            ))
        
        # Process adjacent nodes and infer edges
        seed_ids = {n.node_id for n in expanded.seed_nodes}
        for node in expanded.adjacent_nodes:
            expanded_nodes.append(ExpandedNode(
                node_id=node.node_id,
                node_type=get_node_type_str(node),
                page_no=node.page_no,
                label=node.label,
                text_preview=(node.text_plain or "")[:self.TEXT_PREVIEW_LEN],
                expansion_type="adjacent"
            ))
            # Infer adjacent edge - connected to some seed
            for seed_id in seed_ids:
                edge_traces.append(EdgeTrace(
                    from_node_id=seed_id,
                    to_node_id=node.node_id,
                    edge_type="adjacent"
                ))
                break  # Just one trace per adjacent node
        
        # Process referenced nodes (figures/tables)
        for node in expanded.referenced_nodes:
            expanded_nodes.append(ExpandedNode(
                node_id=node.node_id,
                node_type=get_node_type_str(node),
                page_no=node.page_no,
                label=node.label,
                text_preview=(node.text_plain or "")[:self.TEXT_PREVIEW_LEN],
                expansion_type="referenced"
            ))
            # Infer reference edge - some seed references this figure/table
            for seed_id in seed_ids:
                edge_traces.append(EdgeTrace(
                    from_node_id=seed_id,
                    to_node_id=node.node_id,
                    edge_type="references"
                ))
                break
        
        # Process explained_by nodes
        ref_ids = {n.node_id for n in expanded.referenced_nodes}
        for node in expanded.explained_by_nodes:
            expanded_nodes.append(ExpandedNode(
                node_id=node.node_id,
                node_type=get_node_type_str(node),
                page_no=node.page_no,
                label=node.label,
                text_preview=(node.text_plain or "")[:self.TEXT_PREVIEW_LEN],
                expansion_type="explained_by"
            ))
            # Infer explained_by edge - some figure explains this chunk
            for ref_id in ref_ids:
                edge_traces.append(EdgeTrace(
                    from_node_id=ref_id,
                    to_node_id=node.node_id,
                    edge_type="explained_by"
                ))
                break
        
        return expanded_nodes, edge_traces
    
    def _collect_expanded_nodes_metadata(
        self,
        expanded: ExpandedContext
    ) -> List[Dict[str, Any]]:
        """Collect metadata from all expanded nodes for conflict detection.
        
        Args:
            expanded: Expansion result
            
        Returns:
            List of node dicts with metadata (year, doc_type, department, authority_tier, doc_id)
        """
        from app.db.graph_models import Node as NodeModel
        
        all_nodes = (
            list(expanded.seed_nodes) +
            list(expanded.adjacent_nodes) +
            list(expanded.referenced_nodes) +
            list(expanded.explained_by_nodes)
        )
        
        if not all_nodes:
            return []
        
        # Get node IDs
        node_ids = [n.node_id for n in all_nodes]
        
        # Query nodes from DB to get metadata
        nodes_from_db = self.db.query(NodeModel).filter(
            NodeModel.node_id.in_(node_ids)
        ).all()
        
        node_dicts = []
        for node in nodes_from_db:
            meta = node.meta or {}
            node_dicts.append({
                "node_id": node.node_id,
                "doc_id": node.doc_id,
                "year": meta.get("year"),
                "doc_type": meta.get("doc_type"),
                "department": meta.get("department"),
                "authority_tier": meta.get("authority_tier"),
                "effective_from": meta.get("effective_from"),
                "effective_to": meta.get("effective_to"),
            })
        
        return node_dicts
    
    def _run_propagation_safety(
        self,
        doc_id: str,
        question: str,
        top_k: int = 5,
        version: Optional[int] = None
    ) -> QAResult:
        """Run TRACK-inspired propagation safety mode.
        
        Decomposes question into sub-questions, retrieves and verifies
        each independently, then synthesizes final answer.
        
        Args:
            doc_id: Document ID to query
            question: User's question
            top_k: Number of seed chunks per sub-question
            version: Optional document version
            
        Returns:
            QAResult with propagation_safety_audit
        """
        from app.qa.propagation import (
            PropagationSafetyConfig,
            PropagationSafetyAudit,
            SubQuestion,
            EvidencePacket,
            EvidenceSnippet,
            SubAnswer,
            Planner,
            Verifier,
            Synthesizer,
        )
        
        total_start = time.time()
        
        result = QAResult(question=question, doc_id=doc_id)
        request_id = uuid.uuid4().hex
        result.propagation_safety_mode = True
        
        # Set prompt version for auditability
        from app.prompts import get_prompt_version
        result.prompt_version = get_prompt_version()
        
        # Initialize config
        config = PropagationSafetyConfig.from_dict(self.propagation_safety_config)
        
        # Initialize audit
        audit = PropagationSafetyAudit()
        total_llm_calls = 0
        
        try:
            # ===== PHASE 1: Plan =====
            logger.info("[PropSafety] Planning (len=%d)", len(question))
            planner = Planner(self.llm_client, config)
            sub_questions, needs_clarification, planner_latency = planner.plan(question)
            total_llm_calls += 1
            
            if not sub_questions:
                # Fallback to standard mode
                logger.warning("[PropSafety] Planner failed, falling back to standard mode")
                audit.fallback_used = True
                audit.fallback_reason = "planner_failed"
                audit.total_llm_calls = total_llm_calls
                audit.total_latency_ms = int((time.time() - total_start) * 1000)
                result.propagation_safety_audit = audit.to_dict()
                
                # Run standard pipeline
                return self._run_standard_fallback(doc_id, question, top_k, version, result)
            
            audit.plan = sub_questions
            logger.info(f"[PropSafety] Generated {len(sub_questions)} sub-questions")
            
            # Check budget after planner
            elapsed = time.time() - total_start
            if elapsed > config.total_budget_s * 0.3:  # 30% budget for planning
                logger.warning(f"[PropSafety] Planner took too long ({elapsed:.1f}s), continuing...")
            
            # ===== PHASE 2: Retrieve per sub-question =====
            logger.info("[PropSafety] Retrieving evidence for sub-questions...")
            evidence_packets = []
            
            for sq in sub_questions:
                # Check budget
                if time.time() - total_start > config.total_budget_s:
                    logger.warning("[PropSafety] Budget exceeded during retrieval")
                    break
                
                packet = self._retrieve_for_subquestion(
                    doc_id=doc_id,
                    sub_question=sq,
                    config=config,
                    version=version
                )
                evidence_packets.append(packet)
                logger.info(f"[PropSafety] {sq.id}: retrieved {len(packet.snippets)} snippets")
            
            audit.sub_packets = evidence_packets
            
            # ===== PHASE 3: Verify =====
            logger.info("[PropSafety] Verifying sub-answers...")
            verifier = Verifier(self.llm_client, config)
            sub_answers = verifier.verify_all(sub_questions, evidence_packets)
            total_llm_calls += len(sub_questions)  # One call per sub-question
            
            audit.sub_answers = sub_answers
            
            # ===== PHASE 4: Synthesize =====
            logger.info("[PropSafety] Synthesizing final answer...")
            synthesizer = Synthesizer(self.llm_client, config)
            final_answer, citations, conflicts_summary, synth_latency = synthesizer.synthesize(
                question, sub_questions, sub_answers
            )
            total_llm_calls += 1
            
            # ===== Build result =====
            result.answer = final_answer
            hydrated_input: List[Citation] = []
            for cite in citations:
                if isinstance(cite, Citation):
                    hydrated_input.append(cite)
                elif isinstance(cite, dict):
                    hydrated_input.append(
                        Citation(
                            node_id=str(cite.get("node_id", "")),
                            page_no=cite.get("page_no"),
                            label=cite.get("label"),
                            evidence_spans=list(cite.get("evidence_spans") or []),
                        )
                    )

            result.citations = self._hydrate_citations(
                citations=hydrated_input,
                doc_id=doc_id,
                version=version or 1,
                answer_text=final_answer,
                request_id=request_id,
            )
            result.citations = self.acl_enforcer.filter_citations(result.citations)
            result.model_id = self.llm_client.model
            
            # Aggregate conflicts from all sub-answers
            all_conflicts = []
            for sa in sub_answers:
                all_conflicts.extend(sa.conflicts)
            result.conflicts = all_conflicts
            result.has_conflicts = len(all_conflicts) > 0
            
            # Build audit
            audit.synthesis_citations = citations
            audit.conflicts_summary = conflicts_summary
            audit.total_llm_calls = total_llm_calls
            audit.total_latency_ms = int((time.time() - total_start) * 1000)
            audit.fallback_used = False
            
            result.propagation_safety_audit = audit.to_dict()
            result.success = True
            
            logger.info(
                f"[PropSafety] Complete: {len(sub_questions)} sub-Qs, "
                f"{total_llm_calls} LLM calls, {audit.total_latency_ms}ms"
            )
            
        except Exception as e:
            logger.error(f"[PropSafety] Error: {e}", exc_info=True)
            
            # Try fallback to standard mode
            if config.fallback_on_timeout:
                audit.fallback_used = True
                audit.fallback_reason = f"error: {str(e)}"
                audit.total_llm_calls = total_llm_calls
                audit.total_latency_ms = int((time.time() - total_start) * 1000)
                result.propagation_safety_audit = audit.to_dict()
                
                return self._run_standard_fallback(doc_id, question, top_k, version, result)
            else:
                result.success = False
                result.error = str(e)
                audit.total_llm_calls = total_llm_calls
                audit.total_latency_ms = int((time.time() - total_start) * 1000)
                result.propagation_safety_audit = audit.to_dict()
        
        result.total_time_ms = (time.time() - total_start) * 1000
        return result
    
    def _retrieve_for_subquestion(
        self,
        doc_id: str,
        sub_question: "SubQuestion",
        config: "PropagationSafetyConfig",
        version: Optional[int] = None
    ) -> "EvidencePacket":
        """Run simplified retrieval pipeline for a sub-question.
        
        Pipeline: normalize → search → boost → inject → expand → conflict detect
        Note: Skips reranking for sub-questions.
        """
        from app.qa.propagation.types import EvidencePacket, EvidenceSnippet
        
        packet = EvidencePacket(
            subq_id=sub_question.id,
            subq_text=sub_question.text,
            snippets=[],
            conflicts=[],
            retrieval_audit={}
        )
        
        try:
            # 1. Normalize sub-question
            normalized = normalize_query(sub_question.text, doc_id)
            queries_to_embed = normalized.normalized_queries or [sub_question.text]
            
            # 2. Parse constraints
            constraints = parse_constraints(sub_question.text)
            filter_expr = constraints.get_milvus_filter_expr()
            
            # 3. Embed
            all_vectors = []
            for q in queries_to_embed:
                vec, _ = self.embedding_client.embed_single(q)
                all_vectors.append(vec)
            
            # 4. Vector search (doc-scoped)
            all_search_results = {}
            doc_collection_version = self._get_doc_collection_version(doc_id)
            use_fallback = doc_collection_version is None
            
            if doc_collection_version and doc_collection_version != self.vector_index.collection_version:
                query_index = GraphVectorIndex(collection_version=doc_collection_version)
            else:
                query_index = self.vector_index
            
            for query_vector in all_vectors:
                if use_fallback:
                    search_results = query_index.search_with_fallback(
                        node_type="chunk",
                        query_vector=query_vector,
                        top_k=config.subq_top_k,
                        doc_id_filter=doc_id,
                        filter_expr=filter_expr
                    )
                else:
                    search_results = query_index.search(
                        node_type="chunk",
                        query_vector=query_vector,
                        top_k=config.subq_top_k,
                        doc_id_filter=doc_id,
                        filter_expr=filter_expr
                    )
                
                for sr in search_results:
                    node_id = sr["node_id"]
                    if node_id not in all_search_results or sr["score"] > all_search_results[node_id]["score"]:
                        all_search_results[node_id] = sr
            
            merged_results = list(all_search_results.values())
            merged_results.sort(key=lambda x: x["score"], reverse=True)
            
            if not merged_results:
                packet.retrieval_audit = {"status": "no_results"}
                return packet
            
            # 5. Metadata boosting (simplified)
            boosted = self.metadata_booster.boost_results(merged_results, constraints)
            
            # 6. Section boosting
            total_pages = self._get_doc_total_pages(doc_id)
            section_boosted = self.section_booster.boost_results(
                boosted.boosted_results,
                sub_question.text,
                total_pages
            )
            
            # 7. Seed injection (keep deterministic anchors)
            injection_targets = self._detect_structured_targets(sub_question.text)
            injected_seeds: List[InjectedSeed] = []
            detected_targets_list: List[str] = []

            if any(injection_targets.values()):
                section_boosted_results, injected_seeds, detected_targets_list = self.inject_structured_seeds(
                    sub_question.text,
                    section_boosted.boosted_results,
                    doc_id,
                    top_k=config.subq_top_k
                )
            else:
                section_boosted_results = section_boosted.boosted_results
            
            # 8. Select top seeds
            top_seeds = section_boosted_results[:config.subq_top_k]
            seed_node_ids = [s["node_id"] for s in top_seeds]
            
            # 9. Graph expansion
            expanded = self.expander.expand(seed_node_ids)
            # SECURITY ASSUMPTION:
            # Sub-question evidence inherits ACL guarantees from expander; exporting pre-expansion seeds would require explicit ACL filtering.
            
            # 10. Conflict detection
            expanded_nodes_meta = self._collect_expanded_nodes_metadata(expanded)
            conflict_result = detect_conflicts(expanded_nodes_meta, constraints)
            packet.conflicts = conflict_result.conflicts
            
            # 11. Build snippets from expanded context
            all_expanded_nodes = (
                list(expanded.seed_nodes) +
                list(expanded.adjacent_nodes)[:2] +  # Limit adjacent
                list(expanded.referenced_nodes)[:2] +
                list(expanded.explained_by_nodes)[:1]
            )
            
            # Get node texts from DB
            node_ids = [n.node_id for n in all_expanded_nodes]
            from app.db.graph_models import Node as NodeModel
            nodes_db = self.db.query(NodeModel).filter(
                NodeModel.node_id.in_(node_ids)
            ).all()
            node_text_map = {n.node_id: n.text_plain or n.text_md or "" for n in nodes_db}
            node_meta_map = {n.node_id: n.meta or {} for n in nodes_db}
            node_label_map = {n.node_id: n.label for n in nodes_db}
            
            for node in all_expanded_nodes[:config.max_snippets_per_subq]:
                text = node_text_map.get(node.node_id, "")[:config.snippet_max_chars]
                meta = node_meta_map.get(node.node_id, {})
                
                snippet = EvidenceSnippet(
                    node_id=node.node_id,
                    page_no=node.page_no or 0,
                    text=text,
                    label=node_label_map.get(node.node_id),
                    section_hint=meta.get("section_hint"),
                    year=meta.get("year"),
                    authority_tier=meta.get("authority_tier")
                )
                packet.snippets.append(snippet)
            
            packet.retrieval_audit = {
                "status": "ok",
                "seed_count": len(top_seeds),
                "expanded_count": len(all_expanded_nodes),
                "snippet_count": len(packet.snippets),
                "filter_expr": filter_expr,
                "detected_intent": normalized.detected_intent,
                "injected_count": len(injected_seeds),
                "detected_targets": detected_targets_list
            }
            
        except Exception as e:
            logger.error(f"[PropSafety] Retrieval error for {sub_question.id}: {e}")
            packet.retrieval_audit = {"status": "error", "error": str(e)}
        
        return packet
    
    def _run_standard_fallback(
        self,
        doc_id: str,
        question: str,
        top_k: int,
        version: Optional[int],
        result: QAResult
    ) -> QAResult:
        """Run standard pipeline as fallback, preserving audit from propagation safety attempt."""
        logger.info("[PropSafety] Running standard fallback...")
        
        # INVARIANT:
        # Explicit mode override prevents recursive fallback loops.
        # Run standard pipeline (mode="standard" to avoid recursion)
        standard_result = self.run(doc_id, question, top_k, version, mode="standard")
        
        # ORDER DEPENDENCY:
        # Preserve existing propagation audit before copying standard-mode fields.
        # Copy standard results but keep propagation safety audit
        audit = result.propagation_safety_audit
        
        # Update result with standard pipeline output
        result.answer = standard_result.answer
        result.citations = standard_result.citations
        result.model_id = standard_result.model_id
        result.seed_nodes = standard_result.seed_nodes
        result.expanded_nodes = standard_result.expanded_nodes
        result.edge_traces = standard_result.edge_traces
        result.packed_context = standard_result.packed_context
        result.context_node_ids = standard_result.context_node_ids
        result.total_context_tokens = standard_result.total_context_tokens
        result.conflicts = standard_result.conflicts
        result.has_conflicts = standard_result.has_conflicts
        result.success = standard_result.success
        result.error = standard_result.error
        result.total_time_ms = standard_result.total_time_ms
        
        # Keep audit
        result.propagation_safety_audit = audit
        
        return result
    
    def run_batch(
        self,
        doc_id: str,
        questions: List[str],
        top_k: int = 5
    ) -> List[QAResult]:
        """Run QA pipeline for multiple questions.
        
        Args:
            doc_id: Document ID
            questions: List of questions
            top_k: Number of seed chunks per question
            
        Returns:
            List of QAResult objects
        """
        results = []
        for i, question in enumerate(questions):
            logger.info(f"[QA] Processing question {i+1}/{len(questions)}")
            result = self.run(doc_id, question, top_k)
            results.append(result)
        return results
