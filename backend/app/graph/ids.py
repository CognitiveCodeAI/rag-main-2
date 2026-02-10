"""Deterministic ID generation for graph RAG.

All IDs are deterministic based on content/position to ensure:
- Idempotent ingestion (same content = same IDs)
- Stable references across re-ingestion
- No duplicate nodes on retry
"""

import hashlib
from typing import Optional


def compute_doc_id(source_uri: str) -> str:
    """Generate stable doc_id from source_uri.
    
    Args:
        source_uri: Original document location (file path, URL, etc.)
        
    Returns:
        32-char hex string (first 32 chars of SHA256)
    """
    return hashlib.sha256(source_uri.encode('utf-8')).hexdigest()[:32]


def compute_content_hash(content: bytes) -> str:
    """Generate content hash for deduplication.
    
    Args:
        content: Raw file bytes
        
    Returns:
        64-char hex string (full SHA256)
    """
    return hashlib.sha256(content).hexdigest()


def compute_node_id(
    doc_id: str,
    version: int,
    page_no: int,
    index: int,
    node_type: str
) -> str:
    """Generate deterministic node_id.
    
    Args:
        doc_id: Document ID
        version: Document version number
        page_no: Page number (1-indexed)
        index: Index within the page (0-indexed for chunks, figure/table number)
        node_type: Type of node (chunk, figure, table)
        
    Returns:
        32-char hex string
    """
    key = f"{doc_id}:{version}:{page_no}:{index}:{node_type}"
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:32]


def compute_text_hash(text: str) -> str:
    """Generate hash of text content for change detection.
    
    Args:
        text: Text content
        
    Returns:
        32-char hex string
    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]


def normalize_label(raw_label: str) -> Optional[str]:
    """Normalize figure/table labels to canonical form.
    
    Examples:
        "Fig. 1.5" -> "Figure 1.5"
        "TABLE 2" -> "Table 2"
        "figure1" -> "Figure 1"
        
    Args:
        raw_label: Raw label text
        
    Returns:
        Normalized label or None if not a valid label
    """
    import re
    
    # Normalize whitespace and case
    label = raw_label.strip()
    
    # Figure patterns
    fig_match = re.match(r'(?:fig(?:ure)?\.?\s*)(\d+(?:\.\d+)?)', label, re.IGNORECASE)
    if fig_match:
        return f"Figure {fig_match.group(1)}"
    
    # Table patterns
    tab_match = re.match(r'(?:tab(?:le)?\.?\s*)(\d+(?:\.\d+)?)', label, re.IGNORECASE)
    if tab_match:
        return f"Table {tab_match.group(1)}"
    
    return None


class IdempotencyChecker:
    """Helper for checking if content already exists."""
    
    def __init__(self, db_session):
        self.db = db_session
    
    def document_exists(self, doc_id: str, content_hash: str) -> tuple[bool, Optional[int]]:
        """Check if document with same content already exists.
        
        Args:
            doc_id: Document ID
            content_hash: Content hash of the document
            
        Returns:
            (exists, version) - If exists, returns the existing version number
        """
        from app.db.graph_models import DocumentGraph
        
        existing = self.db.query(DocumentGraph).filter(
            DocumentGraph.doc_id == doc_id,
            DocumentGraph.content_hash == content_hash
        ).first()
        
        if existing:
            return True, existing.version
        return False, None
    
    def get_next_version(self, doc_id: str) -> int:
        """Get next version number for a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Next version number (1 if no existing versions)
        """
        from sqlalchemy import func
        from app.db.graph_models import DocumentGraph
        
        max_version = self.db.query(func.max(DocumentGraph.version)).filter(
            DocumentGraph.doc_id == doc_id
        ).scalar()
        
        return (max_version or 0) + 1
