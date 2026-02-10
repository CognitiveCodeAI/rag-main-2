"""Semantic query normalizer for RAG retrieval.

Generates multiple query variations to handle terminology mismatches
while preserving intent and maintaining auditability.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Load synonyms from JSON file
_SYNONYMS_PATH = Path(__file__).parent / "synonyms_v1.json"
_SYNONYMS: Optional[Dict] = None


def _load_synonyms() -> Dict:
    """Load synonym rules from JSON file."""
    global _SYNONYMS
    if _SYNONYMS is None:
        with open(_SYNONYMS_PATH, 'r') as f:
            _SYNONYMS = json.load(f)
        logger.info(f"Loaded synonym rules v{_SYNONYMS.get('version', 'unknown')}")
    return _SYNONYMS


@dataclass
class NormalizedQuery:
    """Result of query normalization."""
    original: str
    normalized_queries: List[str]  # 2-4 variations
    must_keep: List[str]           # Entities/constraints to preserve
    expanded_terms: List[str]      # Synonyms/canonical terms added
    detected_intent: Optional[str] = None  # section intent
    debug: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original": self.original,
            "normalized_queries": self.normalized_queries,
            "must_keep": self.must_keep,
            "expanded_terms": self.expanded_terms,
            "detected_intent": self.detected_intent,
            "debug": self.debug,
        }


def extract_preserved_entities(text: str, patterns: List[str]) -> List[str]:
    """Extract entities that should be preserved (model names, table/figure refs, quoted strings).
    
    Args:
        text: Input text
        patterns: Regex patterns for entities to preserve
        
    Returns:
        List of preserved entity strings
    """
    entities = []
    for pattern in patterns:
        try:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities.extend(matches)
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
    return list(set(entities))


def extract_key_terms(text: str) -> List[str]:
    """Extract key terms from text (simple approach - noun phrases / significant words).
    
    Args:
        text: Input text
        
    Returns:
        List of key terms
    """
    # Remove punctuation except hyphens
    cleaned = re.sub(r'[^\w\s\-]', ' ', text.lower())
    
    # Split into words
    words = cleaned.split()
    
    # Filter out common stop words
    stop_words = {
        'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these',
        'those', 'what', 'which', 'who', 'whom', 'whose', 'when', 'where',
        'why', 'how', 'and', 'or', 'but', 'if', 'then', 'so', 'for', 'of',
        'to', 'in', 'on', 'at', 'by', 'with', 'from', 'as', 'about', 'into',
        'through', 'during', 'before', 'after', 'above', 'below', 'between',
        'under', 'again', 'further', 'once', 'here', 'there', 'all', 'each',
        'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
        'only', 'own', 'same', 'than', 'too', 'very', 'just', 'also', 'now',
        'it', 'its', 'they', 'them', 'their', 'he', 'she', 'him', 'her', 'his',
        'i', 'me', 'my', 'we', 'us', 'our', 'you', 'your', 'paper', 'study',
        'according', 'used', 'use', 'using'
    }
    
    key_terms = [w for w in words if w not in stop_words and len(w) > 2]
    
    # Also extract bigrams
    bigrams = []
    for i in range(len(words) - 1):
        if words[i] not in stop_words or words[i+1] not in stop_words:
            bigram = f"{words[i]} {words[i+1]}"
            bigrams.append(bigram)
    
    return key_terms + bigrams[:3]  # Top 3 bigrams


def detect_section_intent(text: str, section_hints: Dict[str, List[str]]) -> Optional[str]:
    """Detect which section the query is targeting.
    
    Args:
        text: Query text
        section_hints: Mapping of section -> trigger terms
        
    Returns:
        Section name or None
    """
    text_lower = text.lower()
    
    best_match = None
    best_count = 0
    
    for section, triggers in section_hints.items():
        count = sum(1 for t in triggers if t.lower() in text_lower)
        if count > best_count:
            best_count = count
            best_match = section
    
    return best_match if best_count > 0 else None


def apply_synonym_expansion(
    text: str,
    rules: Dict[str, List[str]],
    max_expansions: int = 6
) -> tuple[str, List[str], List[str]]:
    """Apply synonym expansions to query.
    
    Args:
        text: Original query
        rules: Synonym rules
        max_expansions: Maximum number of terms to add
        
    Returns:
        Tuple of (expanded_text, applied_rules, expanded_terms)
    """
    text_lower = text.lower()
    applied_rules = []
    expanded_terms = []
    
    for trigger, synonyms in rules.items():
        if trigger.lower() in text_lower:
            # Don't add synonyms that are already in the text
            new_synonyms = [s for s in synonyms if s.lower() not in text_lower]
            if new_synonyms:
                applied_rules.append(trigger)
                expanded_terms.extend(new_synonyms[:2])  # Max 2 per rule
                
                if len(expanded_terms) >= max_expansions:
                    break
    
    # Truncate to max
    expanded_terms = expanded_terms[:max_expansions]
    
    # Build expanded query
    if expanded_terms:
        expanded_text = f"{text} ({', '.join(expanded_terms)})"
    else:
        expanded_text = text
    
    return expanded_text, applied_rules, expanded_terms


def generate_section_hinted_query(text: str, intent: Optional[str]) -> Optional[str]:
    """Generate query with section hint appended.
    
    Args:
        text: Original query
        intent: Detected section intent
        
    Returns:
        Query with section hint or None
    """
    if not intent:
        return None
    
    section_hints = {
        "conclusion": "Conclusion Discussion findings takeaways",
        "methodology": "Methodology experimental setup method",
        "evaluation": "evaluation scoring criteria rubric",
        "appendix": "Appendix prompt templates"
    }
    
    hint = section_hints.get(intent)
    if hint:
        return f"{text} {hint}"
    return None


def generate_keyword_query(text: str, preserved: List[str], key_terms: List[str]) -> str:
    """Generate a keyword-only query for broad recall.
    
    Args:
        text: Original query
        preserved: Preserved entities
        key_terms: Extracted key terms
        
    Returns:
        Keyword-focused query
    """
    # Combine preserved entities and top key terms
    all_keywords = list(set(preserved + key_terms[:5]))
    return " ".join(all_keywords)


def normalize_query(question: str, doc_id: Optional[str] = None) -> NormalizedQuery:
    """Normalize a query into multiple retrieval-friendly variations.
    
    Pipeline:
    1. Extract preserved entities (model names, table/figure refs, quoted strings)
    2. Extract key terms
    3. Detect section intent
    4. Apply synonym expansion
    5. Generate 2-4 query variations
    
    Args:
        question: Original question
        doc_id: Optional document ID (for future doc-specific rules)
        
    Returns:
        NormalizedQuery with variations and audit trail
    """
    synonyms = _load_synonyms()
    rules = synonyms.get("rules", {})
    section_hints = synonyms.get("section_hints", {})
    preserve_patterns = synonyms.get("preserve_patterns", [])
    max_expansions = synonyms.get("max_expansions", 6)
    
    # 1. Extract preserved entities
    preserved = extract_preserved_entities(question, preserve_patterns)
    
    # 2. Extract key terms
    key_terms = extract_key_terms(question)
    
    # 3. Detect section intent
    intent = detect_section_intent(question, section_hints)
    
    # 4. Apply synonym expansion
    expanded_query, applied_rules, expanded_terms = apply_synonym_expansion(
        question, rules, max_expansions
    )
    
    # 5. Generate query variations
    queries = [question]  # Q0: Original
    
    # Q1: Synonym expanded (if different from original)
    if expanded_query != question:
        queries.append(expanded_query)
    
    # Q2: Section hinted (if intent detected)
    section_query = generate_section_hinted_query(question, intent)
    if section_query and section_query not in queries:
        queries.append(section_query)
    
    # Q3: Keyword-only (optional, for broad recall)
    if len(queries) < 3 and (preserved or key_terms):
        keyword_query = generate_keyword_query(question, preserved, key_terms)
        if keyword_query and keyword_query not in queries:
            queries.append(keyword_query)
    
    # Ensure we have at least 2 queries (original + one variation)
    if len(queries) < 2:
        # Add a minimal variation
        queries.append(f"{question} context information")
    
    result = NormalizedQuery(
        original=question,
        normalized_queries=queries[:4],  # Max 4 queries
        must_keep=preserved,
        expanded_terms=expanded_terms,
        detected_intent=intent,
        debug={
            "applied_rules": applied_rules,
            "key_terms": key_terms[:10],
            "preserved_entities": preserved,
            "section_intent": intent,
        }
    )
    
    logger.info(
        f"Normalized query: {len(queries)} variations, "
        f"intent={intent}, expansions={len(expanded_terms)}"
    )
    
    return result
