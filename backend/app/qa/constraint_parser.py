"""Request-time metadata constraint parser and query intent classifier.

Parses metadata constraints from user questions to enable:
- Hard filters (applied in Milvus when confidence >= threshold)
- Soft boosts (applied post-retrieval)
- Clarification prompts (when constraints are ambiguous)

Query Intent Classification (CLAM-inspired):
- SPECIFIC: Clear, answerable question with sufficient context
- OVERVIEW: Vague but can be answered with a summary
- AMBIGUOUS: Needs clarification before answering
- IMPOSSIBLE: Cannot be answered (no relevant data exists)

Example constraints detected:
- Year: "in 2020", "2021 policy", "between 2019 and 2021"
- Latest/current: "latest", "current", "most recent"
- Department: "marketing", "legal", "hr"
- Doc type: "policy", "procedure", "contract", "memo"
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Confidence threshold for applying hard Milvus filters
FILTER_CONFIDENCE_THRESHOLD = 0.8


@dataclass
class ParsedConstraints:
    """Parsed metadata constraints from a user question."""
    
    # Hard filters (applied in Milvus when confidence >= threshold)
    filters: Dict[str, Any] = field(default_factory=dict)
    # Possible keys: year, year_range, department, doc_type
    
    # Soft boosts (always applied post-retrieval)
    boosts: Dict[str, bool] = field(default_factory=dict)
    # Possible keys: prefer_latest, prefer_authority
    
    # Confidence per field (0.0 - 1.0)
    confidence: Dict[str, float] = field(default_factory=dict)
    
    # Clarification needed
    needs_clarification: bool = False
    clarify_options: List[str] = field(default_factory=list)
    clarify_prompt: Optional[str] = None
    
    def get_milvus_filter_expr(self) -> Optional[str]:
        """Build Milvus filter expression for EXPLICIT high-confidence filters.
        
        IMPORTANT: Only year constraints become hard filters.
        doc_type and department are ALWAYS treated as boosts (not filters)
        to avoid over-filtering on inferred metadata from question context.
        
        Returns:
            Milvus filter expression string or None
        """
        exprs = []
        
        # Year filter (exact) - only explicit year constraints become filters
        if self.confidence.get("year", 0) >= FILTER_CONFIDENCE_THRESHOLD:
            if "year" in self.filters:
                exprs.append(f"year == {self.filters['year']}")
            elif "year_range" in self.filters:
                yr = self.filters["year_range"]
                if isinstance(yr, (list, tuple)) and len(yr) == 2:
                    exprs.append(f"(year >= {yr[0]} && year <= {yr[1]})")
        
        # NOTE: doc_type and department are NEVER hard filters
        # They are moved to boosts to avoid over-filtering on inferred constraints
        # e.g., "according to the agreement" should not filter to doc_type="contract"
        
        return " && ".join(exprs) if exprs else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "filters": self.filters,
            "boosts": self.boosts,
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "clarify_options": self.clarify_options,
            "clarify_prompt": self.clarify_prompt,
            "filter_expr": self.get_milvus_filter_expr(),
        }


# =============================================================================
# DETECTION PATTERNS
# =============================================================================

# Year patterns with named groups
YEAR_PATTERNS = [
    # "in 2020", "from 2020"
    (re.compile(r'\b(?:in|from|of|for)\s+(\d{4})\b', re.IGNORECASE), 'explicit', 0.9),
    
    # "2020 policy", "2020 report"
    (re.compile(r'\b(\d{4})\s+(?:policy|report|document|memo|procedure|guideline)', re.IGNORECASE), 'prefix', 0.85),
    
    # "policy from 2020"
    (re.compile(r'(?:policy|report|document|memo|procedure|guideline)\s+(?:from|of)\s+(\d{4})', re.IGNORECASE), 'suffix', 0.85),
    
    # "as of 2020", "effective 2020"
    (re.compile(r'\b(?:as\s+of|effective)\s+(\d{4})\b', re.IGNORECASE), 'effective', 0.9),
    
    # Just a year number near relevant context
    (re.compile(r'\b(\d{4})\b'), 'standalone', 0.5),
]

# Year range patterns
YEAR_RANGE_PATTERNS = [
    # "between 2019 and 2021"
    (re.compile(r'\bbetween\s+(\d{4})\s+and\s+(\d{4})\b', re.IGNORECASE), 0.9),
    
    # "from 2019 to 2021"
    (re.compile(r'\bfrom\s+(\d{4})\s+to\s+(\d{4})\b', re.IGNORECASE), 0.9),
    
    # "2019-2021" or "2019 - 2021"
    (re.compile(r'\b(\d{4})\s*[-–—]\s*(\d{4})\b'), 0.85),
]

# Latest/current patterns
LATEST_PATTERNS = [
    (re.compile(r'\b(?:latest|current|newest|most\s+recent|up\s+to\s+date)\b', re.IGNORECASE), 0.9),
    (re.compile(r'\b(?:as\s+of\s+today|today\'s)\b', re.IGNORECASE), 0.85),
    (re.compile(r'\b(?:now|currently)\b', re.IGNORECASE), 0.6),
]

# Department patterns (keyword -> canonical name, confidence)
DEPARTMENT_PATTERNS: Dict[str, Tuple[str, float]] = {
    'marketing': ('marketing', 0.9),
    'legal': ('legal', 0.9),
    'hr': ('hr', 0.9),
    'human resources': ('hr', 0.9),
    'engineering': ('engineering', 0.9),
    'finance': ('finance', 0.9),
    'sales': ('sales', 0.9),
    'operations': ('operations', 0.9),
    'product': ('product', 0.9),
    'research': ('research', 0.9),
    'it': ('engineering', 0.7),
    'tech': ('engineering', 0.7),
}

# Doc type patterns (keyword -> canonical name, confidence)
DOC_TYPE_PATTERNS: Dict[str, Tuple[str, float]] = {
    'policy': ('policy', 0.9),
    'policies': ('policy', 0.9),
    'guideline': ('policy', 0.85),
    'guidelines': ('policy', 0.85),
    'procedure': ('procedure', 0.9),
    'procedures': ('procedure', 0.9),
    'process': ('procedure', 0.8),
    'sop': ('procedure', 0.9),
    'contract': ('contract', 0.9),
    'agreement': ('contract', 0.85),
    'memo': ('memo', 0.9),
    'memorandum': ('memo', 0.9),
    'notice': ('memo', 0.8),
    'report': ('report', 0.9),
    'paper': ('paper', 0.9),
    'article': ('paper', 0.85),
    'whitepaper': ('paper', 0.9),
}

# Authority patterns (trigger prefer_authority boost)
AUTHORITY_PATTERNS = [
    re.compile(r'\b(?:official|approved|mandatory|required|authoritative)\b', re.IGNORECASE),
    re.compile(r'\b(?:binding|final|executive)\b', re.IGNORECASE),
]


def parse_constraints(question: str) -> ParsedConstraints:
    """Parse metadata constraints from a user question.
    
    Args:
        question: User's question text
        
    Returns:
        ParsedConstraints with detected filters, boosts, and confidence
    """
    result = ParsedConstraints()
    question_lower = question.lower()
    
    # 1. Detect year range (check first, takes precedence if found)
    year_range = _detect_year_range(question)
    if year_range:
        result.filters["year_range"] = year_range
        result.confidence["year"] = 0.9
        logger.debug(f"Detected year range: {year_range}")
    
    # 2. Detect specific year (if no range found)
    if "year_range" not in result.filters:
        year, confidence = _detect_year(question)
        if year:
            result.filters["year"] = year
            result.confidence["year"] = confidence
            logger.debug(f"Detected year: {year} (confidence={confidence})")
    
    # 3. Detect latest/current preference
    if _detect_latest(question):
        result.boosts["prefer_latest"] = True
        logger.debug("Detected prefer_latest boost")
    
    # 4. Detect department
    dept, confidence = _detect_department(question_lower)
    if dept:
        result.filters["department"] = dept
        result.confidence["department"] = confidence
        logger.debug(f"Detected department: {dept} (confidence={confidence})")
    
    # 5. Detect doc type
    doc_type, confidence = _detect_doc_type(question_lower)
    if doc_type:
        result.filters["doc_type"] = doc_type
        result.confidence["doc_type"] = confidence
        logger.debug(f"Detected doc_type: {doc_type} (confidence={confidence})")
    
    # 6. Detect authority preference
    if _detect_authority_preference(question):
        result.boosts["prefer_authority"] = True
        logger.debug("Detected prefer_authority boost")
    
    # 7. Handle precedence: year takes priority over year_range
    if "year" in result.filters and "year_range" in result.filters:
        # Keep the more specific one (year)
        del result.filters["year_range"]
        logger.debug("Year takes precedence over year_range")
    
    logger.info(
        f"Parsed constraints: filters={result.filters}, "
        f"boosts={result.boosts}, confidence={result.confidence}"
    )
    
    return result


def _detect_year(question: str) -> Tuple[Optional[int], float]:
    """Detect a specific year from the question.
    
    Returns:
        (year, confidence) or (None, 0.0)
    """
    current_year = datetime.now().year
    
    for pattern, pattern_type, base_confidence in YEAR_PATTERNS:
        match = pattern.search(question)
        if match:
            try:
                year = int(match.group(1))
                # Validate year is reasonable (1990-2100)
                if 1990 <= year <= 2100:
                    # Standalone years near current year get lower confidence
                    if pattern_type == 'standalone':
                        if abs(year - current_year) <= 5:
                            return (year, 0.6)
                        return (year, base_confidence)
                    return (year, base_confidence)
            except (ValueError, IndexError):
                continue
    
    return (None, 0.0)


def _detect_year_range(question: str) -> Optional[Tuple[int, int]]:
    """Detect a year range from the question.
    
    Returns:
        (start_year, end_year) or None
    """
    for pattern, confidence in YEAR_RANGE_PATTERNS:
        match = pattern.search(question)
        if match:
            try:
                start_year = int(match.group(1))
                end_year = int(match.group(2))
                
                # Validate range
                if 1990 <= start_year <= 2100 and 1990 <= end_year <= 2100:
                    if start_year <= end_year:
                        return (start_year, end_year)
                    else:
                        # Swap if reversed
                        return (end_year, start_year)
            except (ValueError, IndexError):
                continue
    
    return None


def _detect_latest(question: str) -> bool:
    """Detect if question asks for latest/current version."""
    for pattern, confidence in LATEST_PATTERNS:
        if pattern.search(question):
            return True
    return False


def _detect_department(question_lower: str) -> Tuple[Optional[str], float]:
    """Detect department from question.
    
    Returns:
        (canonical_department, confidence) or (None, 0.0)
    """
    best_dept = None
    best_confidence = 0.0
    
    for keyword, (canonical, confidence) in DEPARTMENT_PATTERNS.items():
        if keyword in question_lower:
            if confidence > best_confidence:
                best_dept = canonical
                best_confidence = confidence
    
    return (best_dept, best_confidence)


def _detect_doc_type(question_lower: str) -> Tuple[Optional[str], float]:
    """Detect document type from question.
    
    Returns:
        (canonical_doc_type, confidence) or (None, 0.0)
    """
    best_type = None
    best_confidence = 0.0
    
    for keyword, (canonical, confidence) in DOC_TYPE_PATTERNS.items():
        if keyword in question_lower:
            if confidence > best_confidence:
                best_type = canonical
                best_confidence = confidence
    
    return (best_type, best_confidence)


def _detect_authority_preference(question: str) -> bool:
    """Detect if question implies preference for authoritative sources."""
    for pattern in AUTHORITY_PATTERNS:
        if pattern.search(question):
            return True
    return False


def get_constraint_parser():
    """Get constraint parser function (for dependency injection)."""
    return parse_constraints


# =============================================================================
# QUERY INTENT CLASSIFICATION (CLAM/CLARINET-inspired)
# =============================================================================

class QueryIntent(Enum):
    """Query intent classification for routing decisions.
    
    Based on CLAM (Selective Clarification) and CLARINET research:
    - SPECIFIC: Clear query that can be directly answered
    - OVERVIEW: Vague query but can provide summary (e.g., "tell me about X")
    - AMBIGUOUS: Query needs clarification (e.g., "the other fee", "that thing")
    - IMPOSSIBLE: Cannot answer - no relevant data or temporally invalid
    """
    SPECIFIC = "specific"
    OVERVIEW = "overview"
    AMBIGUOUS = "ambiguous"
    IMPOSSIBLE = "impossible"


# Patterns that indicate ambiguous references requiring clarification
AMBIGUOUS_REFERENCE_PATTERNS = [
    re.compile(r'\bthe\s+other\s+(?:one|fee|thing|item|part)\b', re.IGNORECASE),
    re.compile(r'\bthat\s+(?:thing|stuff|one|fee|part)\b', re.IGNORECASE),
    re.compile(r'\bthis\s+(?:thing|stuff|one)\b', re.IGNORECASE),
    re.compile(r'\bit\s+(?:says|mentions|states)\b', re.IGNORECASE),
    re.compile(r'\bwhat\s+about\s+(?:the|that|this)\b', re.IGNORECASE),
]

# Patterns that indicate vague overview requests (can still be answered)
OVERVIEW_REQUEST_PATTERNS = [
    re.compile(r'\b(?:tell\s+me\s+about|explain|describe)\s+', re.IGNORECASE),
    re.compile(r'\b(?:stuff|things?)\s*(?:and|$)', re.IGNORECASE),
    re.compile(r'\b(?:whats?\s+the\s+deal\s+with)\b', re.IGNORECASE),
    re.compile(r'\b(?:how\s+does|how\s+do)\s+', re.IGNORECASE),
    re.compile(r'\b(?:general|overview|summary)\b', re.IGNORECASE),
]

# Temporal ambiguity patterns (asking about years without specifics)
TEMPORAL_AMBIGUITY_PATTERNS = [
    re.compile(r'\blast\s+year(?:\'?s)?\b', re.IGNORECASE),
    re.compile(r'\bprevious\s+(?:year|version)\b', re.IGNORECASE),
    re.compile(r'\bbefore\s+(?:that|this|the)\b', re.IGNORECASE),
    re.compile(r'\bolder\s+(?:version|document)\b', re.IGNORECASE),
]

# Very vague single-word or fragment queries
FRAGMENT_QUERY_PATTERNS = [
    re.compile(r'^[a-zA-Z]+\s+(?:thing|stuff)$', re.IGNORECASE),
    re.compile(r'^what\'?s?\s+the\s+cost\??$', re.IGNORECASE),
    re.compile(r'^the\s+(?:newer|older)\s+version', re.IGNORECASE),
]


def classify_query_intent(
    query: str, 
    retrieved_count: int = 0,
    has_specific_entity: bool = False
) -> QueryIntent:
    """Classify query intent for routing decisions.
    
    Based on CLAM and CLARINET research, determines whether a query:
    - Can be answered directly (SPECIFIC)
    - Needs a summary/overview response (OVERVIEW)
    - Requires clarification (AMBIGUOUS)
    - Cannot be answered (IMPOSSIBLE)
    
    Args:
        query: The user's question
        retrieved_count: Number of retrieved chunks (0 = no results)
        has_specific_entity: Whether a specific entity was detected
        
    Returns:
        QueryIntent classification
    """
    query_lower = query.lower().strip()
    query_words = query_lower.split()
    
    # Very short queries (< 4 words) without specific entities are often ambiguous
    if len(query_words) < 4 and not has_specific_entity:
        # Check if it's a fragment query
        for pattern in FRAGMENT_QUERY_PATTERNS:
            if pattern.search(query):
                logger.debug(f"Fragment query detected: {query}")
                return QueryIntent.AMBIGUOUS
    
    # Check for unresolved references requiring clarification
    for pattern in AMBIGUOUS_REFERENCE_PATTERNS:
        if pattern.search(query):
            logger.debug(f"Ambiguous reference detected in: {query}")
            return QueryIntent.AMBIGUOUS
    
    # Check for temporal ambiguity (asking about past without specific year)
    for pattern in TEMPORAL_AMBIGUITY_PATTERNS:
        if pattern.search(query):
            # Check if a specific year is also mentioned (override ambiguity)
            if not re.search(r'\b20\d{2}\b', query):
                logger.debug(f"Temporal ambiguity detected in: {query}")
                return QueryIntent.AMBIGUOUS
    
    # Check for overview/summary requests (vague but answerable)
    for pattern in OVERVIEW_REQUEST_PATTERNS:
        if pattern.search(query):
            if retrieved_count > 0:
                logger.debug(f"Overview request detected: {query}")
                return QueryIntent.OVERVIEW
    
    # If no chunks retrieved, likely impossible
    if retrieved_count == 0:
        logger.debug(f"No results - impossible query: {query}")
        return QueryIntent.IMPOSSIBLE
    
    # Default to specific (can be answered)
    return QueryIntent.SPECIFIC


@dataclass
class QueryIntentResult:
    """Result of query intent classification with details."""
    intent: QueryIntent
    reason: str
    clarify_prompt: Optional[str] = None
    suggested_action: str = "answer"  # answer, clarify, abstain
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "reason": self.reason,
            "clarify_prompt": self.clarify_prompt,
            "suggested_action": self.suggested_action,
        }


def classify_query_with_details(
    query: str,
    retrieved_count: int = 0,
    has_specific_entity: bool = False
) -> QueryIntentResult:
    """Classify query intent with detailed reasoning.
    
    Returns a QueryIntentResult with the classification, reason, and
    suggested action (including a clarification prompt if needed).
    """
    intent = classify_query_intent(query, retrieved_count, has_specific_entity)
    
    if intent == QueryIntent.AMBIGUOUS:
        # Generate a clarification prompt
        clarify_prompt = _generate_clarify_prompt(query)
        return QueryIntentResult(
            intent=intent,
            reason="Query contains ambiguous references or temporal ambiguity",
            clarify_prompt=clarify_prompt,
            suggested_action="clarify"
        )
    
    if intent == QueryIntent.IMPOSSIBLE:
        return QueryIntentResult(
            intent=intent,
            reason="No relevant information found in the document",
            suggested_action="abstain"
        )
    
    if intent == QueryIntent.OVERVIEW:
        return QueryIntentResult(
            intent=intent,
            reason="Query requests general information - can provide overview",
            suggested_action="answer"
        )
    
    return QueryIntentResult(
        intent=intent,
        reason="Query is specific and can be answered directly",
        suggested_action="answer"
    )


def _generate_clarify_prompt(query: str) -> str:
    """Generate an appropriate clarification prompt based on the query.
    
    Returns a prompt asking the user to clarify their question.
    """
    query_lower = query.lower()
    
    # Check for fee-related ambiguity
    if "fee" in query_lower or "cost" in query_lower:
        return (
            "I found multiple fees mentioned in the document. Could you specify "
            "which fee you're asking about? For example: initial franchise fee, "
            "royalty fee, advertising fee, or another specific fee?"
        )
    
    # Check for temporal ambiguity
    if any(p.search(query) for p in TEMPORAL_AMBIGUITY_PATTERNS):
        return (
            "The document contains information for the current year. "
            "Could you clarify which specific year or time period you're asking about?"
        )
    
    # Check for "the other" pattern
    if re.search(r'\bthe\s+other\b', query_lower):
        return (
            "I'm not sure which specific item you're referring to with 'the other'. "
            "Could you please specify which one you'd like information about?"
        )
    
    # Generic clarification
    return (
        "Your question is a bit vague. Could you please provide more details "
        "about what specific information you're looking for?"
    )
