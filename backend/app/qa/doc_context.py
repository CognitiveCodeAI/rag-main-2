"""Document context provider for LLM query rewriting.

Extracts and caches document metadata, entities, and structural hints
to improve query rewriting accuracy.
"""

import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.db.graph_models import DocumentGraph, Node, NodeType

logger = logging.getLogger(__name__)


# Cache settings
CACHE_TTL_SECONDS = 3600  # 1 hour
MAX_CACHE_SIZE = 100


@dataclass
class DocumentContext:
    """Context extracted from a document for query rewriting."""
    
    doc_id: str
    doc_title: str = ""
    doc_type: str = "general"  # "fdd", "contract", "policy", "general"
    year: Optional[int] = None
    primary_entity: str = ""  # Main company/franchisor name
    key_entities: List[str] = field(default_factory=list)  # Top entities
    sections: List[str] = field(default_factory=list)  # Available sections
    domain_terms: List[str] = field(default_factory=list)  # Domain vocabulary
    token_estimate: int = 0  # Estimated tokens for this context
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def is_expired(self) -> bool:
        """Check if context has expired."""
        now = datetime.now(timezone.utc)
        # Ensure extracted_at is timezone-aware for comparison
        if self.extracted_at.tzinfo is None:
            extracted_at = self.extracted_at.replace(tzinfo=timezone.utc)
        else:
            extracted_at = self.extracted_at
        age = now - extracted_at
        return age.total_seconds() > CACHE_TTL_SECONDS
    
    def to_prompt_block(self) -> str:
        """Format context as a prompt block for the LLM."""
        lines = []
        
        # Document identity
        doc_info = f"Document: {self.doc_title}" if self.doc_title else "Document: (untitled)"
        if self.doc_type != "general":
            doc_info += f" ({self.doc_type.upper()}"
            if self.year:
                doc_info += f", {self.year}"
            doc_info += ")"
        elif self.year:
            doc_info += f" ({self.year})"
        lines.append(doc_info)
        
        # Primary entity
        if self.primary_entity:
            lines.append(f"Primary Entity: {self.primary_entity}")
        
        # Key entities
        if self.key_entities:
            entities_str = ", ".join(self.key_entities[:10])
            lines.append(f"Key Entities: {entities_str}")
        
        # Sections
        if self.sections:
            sections_str = ", ".join(self.sections[:15])
            lines.append(f"Available Sections: {sections_str}")
        
        # Domain terms (only if not obvious from doc_type)
        if self.domain_terms and self.doc_type == "general":
            terms_str = ", ".join(self.domain_terms[:10])
            lines.append(f"Key Terms: {terms_str}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "doc_type": self.doc_type,
            "year": self.year,
            "primary_entity": self.primary_entity,
            "key_entities": self.key_entities,
            "sections": self.sections,
            "domain_terms": self.domain_terms,
            "token_estimate": self.token_estimate,
        }


# FDD-specific patterns
FDD_ITEM_PATTERN = re.compile(r'\bItem\s+(\d+)\b', re.IGNORECASE)
FDD_EXHIBIT_PATTERN = re.compile(r'\bExhibit\s+([A-Z])\b', re.IGNORECASE)
FDD_SECTION_PATTERNS = [
    (re.compile(r'\bItem\s+1\b.*?\bFranchisor', re.IGNORECASE), "Item 1 - The Franchisor"),
    (re.compile(r'\bItem\s+5\b.*?\bInitial\s+Fee', re.IGNORECASE), "Item 5 - Initial Fees"),
    (re.compile(r'\bItem\s+6\b.*?\bOther\s+Fee', re.IGNORECASE), "Item 6 - Other Fees"),
    (re.compile(r'\bItem\s+7\b.*?\bEstimated\s+Initial', re.IGNORECASE), "Item 7 - Estimated Initial Investment"),
    (re.compile(r'\bItem\s+19\b.*?\bFinancial', re.IGNORECASE), "Item 19 - Financial Performance"),
    (re.compile(r'\bItem\s+21\b.*?\bFinancial\s+Statement', re.IGNORECASE), "Item 21 - Financial Statements"),
]

# Entity extraction patterns
PROPER_NOUN_PATTERN = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b')
COMPANY_SUFFIX_PATTERN = re.compile(
    r'\b([A-Z][A-Za-z\s]+(?:Inc|LLC|Corp|Corporation|Company|Co|Ltd|LP|LLP|International|Holdings|Group)\.?)\b',
    re.IGNORECASE
)


class DocumentContextCache:
    """LRU cache for document contexts."""
    
    def __init__(self, max_size: int = MAX_CACHE_SIZE):
        self._cache: Dict[str, DocumentContext] = {}
        self._access_times: Dict[str, datetime] = {}
        self.max_size = max_size
    
    def get(self, doc_id: str) -> Optional[DocumentContext]:
        """Get context from cache if valid."""
        if doc_id not in self._cache:
            return None
        
        context = self._cache[doc_id]
        if context.is_expired():
            del self._cache[doc_id]
            del self._access_times[doc_id]
            return None
        
        # Update access time
        self._access_times[doc_id] = datetime.now(timezone.utc)
        return context
    
    def put(self, context: DocumentContext) -> None:
        """Add context to cache, evicting oldest if necessary."""
        # Evict if at capacity
        if len(self._cache) >= self.max_size and context.doc_id not in self._cache:
            self._evict_oldest()
        
        self._cache[context.doc_id] = context
        self._access_times[context.doc_id] = datetime.now(timezone.utc)
    
    def _evict_oldest(self) -> None:
        """Evict the least recently accessed entry."""
        if not self._access_times:
            return
        
        oldest_id = min(self._access_times, key=self._access_times.get)
        del self._cache[oldest_id]
        del self._access_times[oldest_id]
    
    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._access_times.clear()


# Global cache instance
_context_cache = DocumentContextCache()


def get_document_context(
    db: Session,
    doc_id: str,
    force_refresh: bool = False
) -> Optional[DocumentContext]:
    """Get document context, using cache if available.
    
    Args:
        db: Database session
        doc_id: Document ID
        force_refresh: Force re-extraction even if cached
        
    Returns:
        DocumentContext or None if document not found
    """
    # Check cache first
    if not force_refresh:
        cached = _context_cache.get(doc_id)
        if cached:
            logger.debug(f"[DocContext] Cache hit for {doc_id}")
            return cached
    
    # Extract fresh context
    logger.info(f"[DocContext] Extracting context for {doc_id}")
    start_time = time.time()
    
    context = _extract_document_context(db, doc_id)
    
    if context:
        _context_cache.put(context)
        latency_ms = (time.time() - start_time) * 1000
        logger.info(
            f"[DocContext] Extracted context for {doc_id} in {latency_ms:.0f}ms "
            f"(~{context.token_estimate} tokens)"
        )
    
    return context


def _extract_document_context(db: Session, doc_id: str) -> Optional[DocumentContext]:
    """Extract context from document graph.
    
    Args:
        db: Database session
        doc_id: Document ID
        
    Returns:
        DocumentContext or None if document not found
    """
    # Get document metadata
    doc = db.query(DocumentGraph).filter_by(doc_id=doc_id).first()
    if not doc:
        logger.warning(f"[DocContext] Document not found: {doc_id}")
        return None
    
    # Start building context
    context = DocumentContext(doc_id=doc_id)
    
    # Extract document title from source_uri
    context.doc_title = _extract_title_from_uri(doc.source_uri)
    
    # Get document type and year from metadata
    context.doc_type = _classify_doc_type(doc)
    context.year = doc.year
    
    # Get nodes for entity and section extraction
    nodes = db.query(Node).filter_by(
        doc_id=doc_id,
        version=doc.version
    ).all()
    
    # Extract entities
    context.primary_entity, context.key_entities = _extract_entities(doc, nodes)
    
    # Extract sections/structure
    context.sections = _extract_sections(doc, nodes)
    
    # Extract domain terms
    context.domain_terms = _extract_domain_terms(doc, nodes)
    
    # Estimate token count
    context.token_estimate = _estimate_tokens(context)
    
    return context


def _extract_title_from_uri(source_uri: str) -> str:
    """Extract document title from source URI."""
    if not source_uri:
        return ""
    
    # Remove scheme
    path = source_uri.split("://")[-1]
    
    # Get filename
    filename = path.split("/")[-1]
    
    # Remove extension
    if "." in filename:
        filename = filename.rsplit(".", 1)[0]
    
    # Clean up
    filename = filename.replace("_", " ").replace("-", " ")
    
    # Title case if all lowercase/uppercase
    if filename.islower() or filename.isupper():
        filename = filename.title()
    
    return filename


def _classify_doc_type(doc: DocumentGraph) -> str:
    """Classify document type from metadata and content."""
    # Check explicit doc_type
    if doc.doc_type:
        doc_type = doc.doc_type.lower()
        if "fdd" in doc_type or "franchise" in doc_type:
            return "fdd"
        if "contract" in doc_type or "agreement" in doc_type:
            return "contract"
        if "policy" in doc_type or "procedure" in doc_type:
            return "policy"
        return doc_type
    
    # Check title for hints
    title = _extract_title_from_uri(doc.source_uri).lower()
    if "fdd" in title or "franchise disclosure" in title:
        return "fdd"
    if "contract" in title or "agreement" in title:
        return "contract"
    if "policy" in title or "procedure" in title:
        return "policy"
    
    return "general"


def _extract_entities(
    doc: DocumentGraph,
    nodes: List[Node]
) -> tuple[str, List[str]]:
    """Extract primary entity and key entities from document.
    
    Returns:
        Tuple of (primary_entity, key_entities)
    """
    # Collect text from first few pages for entity extraction
    early_text = ""
    for node in sorted(nodes, key=lambda n: (n.page_no or 0, n.chunk_index_in_page or 0))[:20]:
        if node.text_plain:
            early_text += " " + node.text_plain
    
    # Find company names (high priority)
    company_matches = COMPANY_SUFFIX_PATTERN.findall(early_text)
    companies = [c.strip() for c in company_matches if len(c) > 3]
    
    # Find proper nouns
    proper_nouns = PROPER_NOUN_PATTERN.findall(early_text)
    
    # Count occurrences
    entity_counts = Counter()
    for company in companies:
        entity_counts[company] += 5  # Boost company names
    for noun in proper_nouns:
        if len(noun) > 2 and noun not in ("The", "This", "That", "Item", "Section", "Page"):
            entity_counts[noun] += 1
    
    # Get top entities
    top_entities = [e for e, _ in entity_counts.most_common(15)]
    
    # Primary entity is first company or most common entity
    primary = ""
    if companies:
        primary = companies[0]
    elif top_entities:
        primary = top_entities[0]
    
    # Key entities (exclude primary to avoid duplication)
    key_entities = [e for e in top_entities if e != primary][:10]
    
    return primary, key_entities


def _extract_sections(doc: DocumentGraph, nodes: List[Node]) -> List[str]:
    """Extract available sections from document structure."""
    sections = []
    doc_type = _classify_doc_type(doc)
    
    if doc_type == "fdd":
        # Look for FDD Items and Exhibits
        all_text = " ".join(n.text_plain or "" for n in nodes)
        
        # Find Items
        items_found = set(FDD_ITEM_PATTERN.findall(all_text))
        if items_found:
            item_nums = sorted(int(i) for i in items_found)
            if len(item_nums) > 3:
                sections.append(f"Items {min(item_nums)}-{max(item_nums)}")
            else:
                sections.extend([f"Item {n}" for n in item_nums])
        
        # Find Exhibits
        exhibits_found = set(FDD_EXHIBIT_PATTERN.findall(all_text))
        if exhibits_found:
            exhibit_letters = sorted(exhibits_found)
            if len(exhibit_letters) > 3:
                sections.append(f"Exhibits {exhibit_letters[0]}-{exhibit_letters[-1]}")
            else:
                sections.extend([f"Exhibit {e}" for e in exhibit_letters])
    
    else:
        # Generic section extraction from node labels or headings
        for node in nodes:
            if node.label and node.label not in sections:
                sections.append(node.label)
            
            # Look for heading patterns in text
            if node.text_plain:
                # Check for numbered sections like "1.0", "2.1"
                heading_match = re.match(r'^(\d+\.?\d*)\s+([A-Z][^.]{5,50})', node.text_plain)
                if heading_match:
                    section = f"{heading_match.group(1)} {heading_match.group(2)}"
                    if section not in sections:
                        sections.append(section)
        
        # Limit sections
        sections = sections[:15]
    
    return sections


def _extract_domain_terms(doc: DocumentGraph, nodes: List[Node]) -> List[str]:
    """Extract domain-specific terms from document."""
    doc_type = _classify_doc_type(doc)
    
    # FDD-specific terms
    if doc_type == "fdd":
        return [
            "franchise fee", "royalty", "advertising fee", "territory",
            "initial investment", "franchisor", "franchisee",
            "training", "proprietary marks", "renewal"
        ]
    
    # Contract terms
    if doc_type == "contract":
        return [
            "party", "agreement", "term", "termination", "liability",
            "indemnification", "confidential", "jurisdiction"
        ]
    
    # Policy terms
    if doc_type == "policy":
        return [
            "policy", "procedure", "compliance", "effective date",
            "scope", "responsibility", "exception"
        ]
    
    # Generic: extract high-frequency terms from content
    all_text = " ".join(n.text_plain or "" for n in nodes[:30])
    words = re.findall(r'\b[a-z]{4,15}\b', all_text.lower())
    
    # Filter common words
    stopwords = {
        "that", "this", "with", "from", "have", "been", "will", "would",
        "could", "should", "their", "there", "which", "about", "into",
        "than", "then", "more", "some", "such", "only", "other"
    }
    
    word_counts = Counter(w for w in words if w not in stopwords)
    return [w for w, _ in word_counts.most_common(10)]


def _estimate_tokens(context: DocumentContext) -> int:
    """Estimate token count for the context block."""
    # Rough estimation: ~4 chars per token
    prompt_block = context.to_prompt_block()
    return len(prompt_block) // 4 + 10  # Add buffer


def clear_context_cache() -> None:
    """Clear the document context cache."""
    _context_cache.clear()
    logger.info("[DocContext] Cache cleared")
