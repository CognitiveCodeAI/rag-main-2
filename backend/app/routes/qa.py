"""QA API endpoints for question answering."""

import logging
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.acl.dependencies import get_entitlements
from app.acl.models import Entitlements
from app.db.session import get_session
from app.qa.runner import QARunner
from app.settings_service import get_runtime_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/qa", tags=["qa"])


class PropagationSafetyConfigModel(BaseModel):
    """Configuration for propagation_safety mode."""
    max_sub_questions: int = Field(default=4, ge=2, le=6, description="Maximum sub-questions to generate")
    verifier_timeout_s: float = Field(default=5.0, ge=1.0, le=30.0, description="Timeout per verifier call")
    parallel_verifiers: bool = Field(default=True, description="Run verifiers in parallel")
    total_budget_s: float = Field(default=30.0, ge=10.0, le=120.0, description="Total time budget")
    fallback_on_timeout: bool = Field(default=True, description="Fall back to standard mode on timeout")


class ChatMessage(BaseModel):
    """A single chat message for conversation history."""
    role: Literal["user", "assistant"] = Field(..., description="Role of the message sender")
    content: str = Field(..., description="Message content")


class AskRequest(BaseModel):
    """Request body for ask endpoint."""
    doc_id: Optional[str] = Field(default=None, description="Document ID to query (optional - searches all documents if not provided)")
    question: str = Field(..., description="Question to answer")
    top_k: Optional[int] = Field(default=None, ge=1, le=50, description="Number of seed chunks to retrieve (uses runtime setting if not specified)")
    chat_history: Optional[List[ChatMessage]] = Field(default=None, description="Previous conversation history for context")
    mode: Literal["standard", "propagation_safety"] = Field(
        default="standard",
        description="QA mode: standard or propagation_safety (TRACK-inspired)"
    )
    propagation_safety_config: Optional[PropagationSafetyConfigModel] = Field(
        default=None,
        description="Configuration for propagation_safety mode (optional)"
    )
    evidence_chain_mode: Optional[Literal["off", "auto", "on"]] = Field(
        default=None,
        description=(
            "Query-aware evidence-chain routing. The server feature flag remains authoritative; "
            "clients may disable it or choose the configured routing behavior."
        ),
    )


class AskResponse(BaseModel):
    """Response from ask endpoint."""
    question: str
    doc_id: Optional[str] = None  # None means all documents were searched
    
    # Search results
    seed_nodes: list
    
    # Expansion results
    expanded_nodes: list
    edge_traces: list
    
    # Context
    packed_context: str
    context_node_ids: list
    total_context_tokens: int
    
    # Answer
    answer: str
    citations: list
    model_id: str
    
    # Timing
    timing: dict
    
    # Metadata-aware retrieval
    metadata_constraints: Optional[dict] = None
    metadata_filter_applied: Optional[str] = None
    metadata_boosts: Optional[dict] = None
    
    # Conflicts
    conflicts: Optional[List[dict]] = None
    has_conflicts: bool = False
    
    # Clarification (for ambiguous constraints)
    needs_clarification: bool = False
    clarify_prompt: Optional[str] = None
    clarify_options: Optional[List[str]] = None
    
    # Propagation Safety Mode (TRACK-inspired)
    propagation_safety_mode: bool = False
    propagation_safety_audit: Optional[dict] = None

    # Query-aware evidence-chain audit (relevance, never factual confidence)
    evidence_chain: Optional[dict] = None
    
    # LLM Query Rewriting (for multi-turn conversations)
    original_question: Optional[str] = None  # Original query before rewriting
    llm_rewrite: Optional[dict] = None  # Rewrite details (used_llm, rewritten_query, etc.)

    # ACL audit trail
    acl_audit: Optional[List[dict]] = None

    # Status
    success: bool
    error: Optional[str] = None


@router.post("/ask", response_model=AskResponse)
def ask_question(
    request: AskRequest,
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
):
    """Answer a question about a document.
    
    This endpoint performs the full RAG pipeline:
    1. Embeds the question
    2. Searches for relevant chunks via vector similarity
    3. Expands context using graph relationships
    4. Generates an answer with citations
    
    When mode="propagation_safety", uses TRACK-inspired pipeline:
    1. Decomposes question into atomic sub-questions
    2. Retrieves and verifies each sub-question independently
    3. Synthesizes final answer from verified sub-answers only
    
    Returns a detailed audit trail of the entire process.
    """
    logger.info(f"[API] Ask: doc={request.doc_id}, mode={request.mode}, question={request.question[:50]}...")

    try:
        # Load runtime settings for defaults
        runtime = get_runtime_settings(db)

        # Use runtime settings for defaults when not explicitly specified
        top_k = request.top_k if request.top_k is not None else runtime.retrieval_top_k

        # Build config dict for propagation_safety mode
        prop_safety_config = None
        if request.propagation_safety_config:
            prop_safety_config = request.propagation_safety_config.model_dump()

        runner = QARunner(
            db=db,
            propagation_safety_config=prop_safety_config,
            entitlements=entitlements,
            max_context_tokens=runtime.max_context_tokens,
            enable_rerank=runtime.enable_reranking,
            enable_llm_rewrite=runtime.enable_llm_query_rewrite,
            evidence_chain_mode=request.evidence_chain_mode,
        )

        # Convert chat history to list of dicts for the runner
        chat_history = None
        if request.chat_history:
            chat_history = [{"role": msg.role, "content": msg.content} for msg in request.chat_history]

        result = runner.run(
            doc_id=request.doc_id,
            question=request.question,
            top_k=top_k,
            mode=request.mode,
            chat_history=chat_history
        )
        
        response_data = result.to_dict()
        
        # Extract metadata info
        metadata_info = response_data.get("metadata", {})
        
        return AskResponse(
            question=response_data["question"],
            doc_id=response_data["doc_id"],
            seed_nodes=response_data["seed_nodes"],
            expanded_nodes=response_data["expanded_nodes"],
            edge_traces=response_data["edge_traces"],
            packed_context=response_data["packed_context"],
            context_node_ids=response_data["context_node_ids"],
            total_context_tokens=response_data["total_context_tokens"],
            answer=response_data["answer"],
            citations=response_data["citations"],
            model_id=response_data["model_id"],
            timing=response_data["timing"],
            # Metadata-aware retrieval
            metadata_constraints=metadata_info.get("constraints"),
            metadata_filter_applied=metadata_info.get("filter_expr"),
            metadata_boosts=metadata_info.get("boost_applied"),
            # Conflicts
            conflicts=response_data.get("conflicts"),
            has_conflicts=response_data.get("has_conflicts", False),
            # Propagation Safety Mode
            propagation_safety_mode=response_data.get("propagation_safety_mode", False),
            propagation_safety_audit=response_data.get("propagation_safety_audit"),
            evidence_chain=response_data.get("evidence_chain"),
            # LLM Query Rewriting
            original_question=response_data.get("original_question"),
            llm_rewrite=response_data.get("llm_rewrite"),
            # ACL
            acl_audit=response_data.get("acl_audit"),
            # Status
            success=response_data["success"],
            error=response_data["error"]
        )
        
    except Exception as e:
        error_id = str(uuid.uuid4())
        logger.error(f"[API] Ask failed (error_id={error_id}): {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (error_id={error_id})",
        )


@router.get("/health")
def qa_health():
    """Health check for QA service."""
    return {"status": "ok", "service": "qa"}
