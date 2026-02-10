"""Query routes for the RAG API."""
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.models import (
    QueryRequest,
    QueryResponse,
    ResponseMode,
    Claim,
    Citation,
)
from app.config import get_current_datetime

router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    """
    Process a query and return a grounded response with citations.
    
    This is a placeholder implementation that demonstrates the response structure.
    The full implementation will include:
    - Query planning
    - Multi-modal retrieval
    - Evidence fusion
    - Answer generation with citations
    - Verification
    """
    query_id = str(uuid.uuid4())
    current_time = get_current_datetime()
    
    # Demo response - will be replaced with actual RAG pipeline
    if "hello" in request.query.lower() or "hi" in request.query.lower():
        return QueryResponse(
            query_id=query_id,
            final_text=f"Hello! I'm the NPR (Near-Perfect RAG) assistant. The current date and time is {current_time}. I provide evidence-first answers grounded in your document corpus. How can I help you today?",
            claims=[],
            mode=ResponseMode.ANSWER,
            confidence=1.0,
            followups=[
                "What documents do you want to query?",
                "Would you like to upload some files to search?"
            ],
            timestamp=datetime.utcnow(),
        )
    
    # Demo response with citations for other queries
    demo_citation = Citation(
        doc_id="demo-doc-001",
        version_id="v1",
        source_uri="corpus://demo/lighthouse.md",
        title="NPR Lighthouse Specification",
        start_offset=0,
        end_offset=100,
        text="Evidence-first: generation can only use evidence spans from the corpus (EvidencePack)."
    )
    
    demo_claim = Claim(
        text="The NPR system follows an evidence-first approach where generation can only use evidence spans from the corpus.",
        citations=[demo_citation]
    )
    
    return QueryResponse(
        query_id=query_id,
        final_text=f"""Based on the corpus, I found relevant information for your query.

**Query:** {request.query}

The NPR (Near-Perfect RAG) system is designed with these core principles:

1. **Evidence-first approach**: Generation can only use evidence spans from the corpus
2. **Claim-citation completeness**: Every factual claim must have at least one citation
3. **Answerability**: If insufficient evidence exists, the system will ask clarifying questions or abstain rather than guess

Current system time: {current_time}

*Note: This is a demo response. Connect your document corpus to get real answers.*""",
        claims=[demo_claim],
        mode=ResponseMode.ANSWER,
        confidence=0.85,
        followups=[
            "Would you like more details about any of these principles?",
            "Do you have specific documents you'd like to search?"
        ],
        timestamp=datetime.utcnow(),
    )


@router.post("/clarify")
async def clarify(query_id: str, clarification: str):
    """Handle a clarification response from the user."""
    # Placeholder for clarification handling
    return {
        "status": "received",
        "query_id": query_id,
        "message": "Clarification received. Processing with additional context."
    }
