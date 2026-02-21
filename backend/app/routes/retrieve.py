"""Vector retrieval API endpoints."""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.acl.dependencies import get_entitlements
from app.acl.enforcer import ACLEnforcer
from app.acl.models import Entitlements
from app.embeddings.client import get_embedding_client
from app.graph.vector_index import GraphVectorIndex
from app.db.session import get_session
from app.db.graph_models import Node

logger = logging.getLogger(__name__)

# Maximum length for text preview
TEXT_PREVIEW_MAX_LENGTH = 300

router = APIRouter(prefix="/v1/retrieve", tags=["retrieval"])


# View name to node type mapping
VIEW_NODE_TYPES = {
    "chunks": "chunk",
    "figures": "figure",
    "tables": "table",
}


class VectorRetrieveRequest(BaseModel):
    """Request for vector retrieval."""
    query: str = Field(..., min_length=1, description="Query text")
    view: str = Field(
        default="chunks",
        description="View to search (chunks, figures, or tables)"
    )
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results")
    doc_id: Optional[str] = Field(
        default=None,
        description="Deprecated top-level document filter (prefer filters.doc_id)",
    )
    filters: Optional[dict] = Field(
        default=None,
        description="Optional filters (e.g., {\"doc_id\": \"...\"})"
    )


class VectorRetrieveResult(BaseModel):
    """Single retrieval result."""
    chunk_id: str
    doc_id: str
    version_id: Optional[str] = None
    score: float
    page_no: Optional[int] = None
    text_preview: Optional[str] = None


class VectorRetrieveResponse(BaseModel):
    """Response for vector retrieval."""
    query: str
    view: str
    results: list[VectorRetrieveResult]
    total: int


@router.post("/vector", response_model=VectorRetrieveResponse)
async def retrieve_vectors(
    request: VectorRetrieveRequest,
    db: Session = Depends(get_session),
    entitlements: Optional[Entitlements] = Depends(get_entitlements),
) -> VectorRetrieveResponse:
    """Retrieve similar chunks via vector search.
    
    Args:
        request: Retrieval request with query, view, top_k, filters
        db: Database session
    
    Returns:
        List of matching chunks with scores and content previews
    """
    # Validate view
    if request.view not in VIEW_NODE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid view: {request.view}. Must be one of: {list(VIEW_NODE_TYPES.keys())}"
        )
    
    node_type = VIEW_NODE_TYPES[request.view]
    
    try:
        # Embed query
        embedding_client = get_embedding_client()
        query_vector, _ = embedding_client.embed_single(request.query)
        
        logger.info(f"Embedded query: {len(request.query)} chars")
        
        # Search using GraphVectorIndex
        vector_index = GraphVectorIndex()
        
        # Build doc_id filter if provided (prefer structured filters for compatibility).
        doc_id_filter = request.doc_id
        if request.filters and request.filters.get("doc_id"):
            doc_id_filter = request.filters.get("doc_id")
        
        results = vector_index.search(
            node_type=node_type,
            query_vector=query_vector,
            top_k=request.top_k,
            doc_id_filter=doc_id_filter,
        )

        # ACL enforcement: filter search results
        acl_enforcer = ACLEnforcer(db, entitlements)
        results = acl_enforcer.filter_search_results(results, stage="retrieve_vector")

        logger.info(f"Retrieved {len(results)} results for {node_type}")
        
        # Fetch node content from database for previews
        node_ids = [r["node_id"] for r in results]
        nodes_by_id = {}
        if node_ids:
            nodes = db.query(Node).filter(Node.node_id.in_(node_ids)).all()
            nodes_by_id = {n.node_id: n for n in nodes}
        
        # Format response with content previews
        formatted_results = []
        for r in results:
            node = nodes_by_id.get(r["node_id"])
            
            # Get text preview (truncated)
            text_preview = None
            if node and node.text_plain:
                text = node.text_plain.strip()
                if len(text) > TEXT_PREVIEW_MAX_LENGTH:
                    text_preview = text[:TEXT_PREVIEW_MAX_LENGTH] + "..."
                else:
                    text_preview = text
            
            formatted_results.append(
                VectorRetrieveResult(
                    chunk_id=r["node_id"],
                    doc_id=r["doc_id"],
                    version_id=str(r.get("version")) if r.get("version") else None,
                    score=r["score"],
                    page_no=node.page_no if node else r.get("page_no"),
                    text_preview=text_preview,
                )
            )
        
        return VectorRetrieveResponse(
            query=request.query,
            view=request.view,
            results=formatted_results,
            total=len(formatted_results),
        )
    
    except Exception as e:
        error_id = str(uuid.uuid4())
        logger.error(
            f"Vector retrieval failed (error_id={error_id}): {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (error_id={error_id})",
        )


@router.get("/collections")
async def list_collections() -> dict:
    """List available vector collections and their stats."""
    try:
        vector_index = GraphVectorIndex()
        
        stats = {}
        for view_name, node_type in VIEW_NODE_TYPES.items():
            try:
                collection_stats = vector_index.get_collection_stats(node_type)
                stats[view_name] = collection_stats
            except Exception as e:
                logger.warning(f"Failed to get stats for {view_name}: {e}")
                stats[view_name] = {"name": view_name, "num_entities": 0, "error": str(e)}
        
        return {
            "collections": stats,
        }
    
    except Exception as e:
        error_id = str(uuid.uuid4())
        logger.error(
            f"Failed to get collection stats (error_id={error_id}): {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (error_id={error_id})",
        )
