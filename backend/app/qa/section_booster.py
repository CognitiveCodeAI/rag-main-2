"""Section-aware boosting for RAG retrieval.

Boosts search results based on detected query intent (conclusion, methodology, etc.)
and node metadata (section_hint, page position).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# Intent patterns: query terms that signal targeting a specific section
INTENT_PATTERNS = {
    "conclusion": [
        "recommendations", "future work", "implications", "conclusion",
        "takeaway", "summary", "main findings", "suggest", "recommend",
        "what can improve", "what affects"
    ],
    "methodology": [
        "method", "haystack", "prompt structure", "distributions",
        "sigmoid", "linear", "experimental", "setup", "how do they",
        "how did they", "vary", "approach", "procedure"
    ],
    "evaluation": [
        "scoring", "judge", "criteria", "scale", "rubric", "grading",
        "rating", "1-5", "evaluate", "assessment", "Table 4"
    ],
    "appendix": [
        "prompt template", "appendix", "llama template", "mistral template",
        "Table 6", "Appendix A", "Appendix B", "Appendix C"
    ],
    "results": [
        "results", "findings", "performance", "accuracy", "comparison",
        "Table 1", "Table 2", "Table 3", "Figure"
    ]
}

# Section hints that should match intent
SECTION_BOOST_MAP = {
    "conclusion": ["Conclusion", "Discussion", "Section 6"],
    "methodology": ["Methodology", "Section 3", "Experimental"],
    "evaluation": ["Evaluation", "Scoring", "Appendix C"],
    "appendix": ["Appendix", "Appendix A", "Appendix B"],
    "results": ["Results", "Section 4", "Section 5"]
}

# Boost weights
BOOST_WEIGHTS = {
    "section_match": 0.25,      # Exact section hint match
    "last_pages": 0.15,         # Last 20% of doc for conclusion intent
    "figure_table_query": 0.20, # Boost figure/table nodes for those queries
}


@dataclass
class SectionBoostResult:
    """Result of section boosting."""
    intent: Optional[str]
    boosted_results: List[Dict[str, Any]]
    boost_applied: Dict[str, int]  # section -> count of boosted nodes
    debug: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "boost_applied": self.boost_applied,
            "debug": self.debug,
        }


class SectionBooster:
    """Applies section-aware boosting to search results."""
    
    def __init__(
        self,
        section_boost: float = BOOST_WEIGHTS["section_match"],
        last_pages_boost: float = BOOST_WEIGHTS["last_pages"],
        figure_table_boost: float = BOOST_WEIGHTS["figure_table_query"]
    ):
        """Initialize booster.
        
        Args:
            section_boost: Weight for section hint match
            last_pages_boost: Weight for last pages heuristic
            figure_table_boost: Weight for figure/table queries
        """
        self.section_boost = section_boost
        self.last_pages_boost = last_pages_boost
        self.figure_table_boost = figure_table_boost
    
    def detect_intent(self, query: str) -> Optional[str]:
        """Detect section intent from query.
        
        Args:
            query: Query text
            
        Returns:
            Intent string or None
        """
        query_lower = query.lower()
        
        best_intent = None
        best_score = 0
        
        for intent, patterns in INTENT_PATTERNS.items():
            score = sum(1 for p in patterns if p.lower() in query_lower)
            if score > best_score:
                best_score = score
                best_intent = intent
        
        return best_intent if best_score > 0 else None
    
    def detect_figure_table_query(self, query: str) -> bool:
        """Check if query is targeting figures or tables.
        
        Args:
            query: Query text
            
        Returns:
            True if figure/table query
        """
        query_lower = query.lower()
        patterns = ["figure", "table", "fig.", "tab."]
        return any(p in query_lower for p in patterns)
    
    def boost_results(
        self,
        results: List[Dict[str, Any]],
        query: str,
        total_pages: Optional[int] = None,
        nodes_metadata: Optional[Dict[str, Dict]] = None
    ) -> SectionBoostResult:
        """Apply section-aware boosting to search results.
        
        Args:
            results: Search results with node_id, score, page_no, node_type
            query: Original query
            total_pages: Total pages in document (for last-pages heuristic)
            nodes_metadata: Optional dict of node_id -> node.meta for section_hint
            
        Returns:
            SectionBoostResult with boosted results
        """
        intent = self.detect_intent(query)
        is_figure_table_query = self.detect_figure_table_query(query)
        
        boost_applied = {"section": 0, "last_pages": 0, "figure_table": 0}
        
        boosted_results = []
        for r in results:
            node_id = r.get("node_id")
            base_score = r.get("score", 0.0)
            page_no = r.get("page_no")
            node_type = r.get("node_type", "chunk")
            
            boost_factor = 1.0
            reasons = []
            
            # 1. Section hint match
            if intent and nodes_metadata and node_id in nodes_metadata:
                meta = nodes_metadata[node_id]
                section_hint = meta.get("section_hint", "")
                
                target_sections = SECTION_BOOST_MAP.get(intent, [])
                if section_hint and any(s.lower() in section_hint.lower() for s in target_sections):
                    boost_factor += self.section_boost
                    boost_applied["section"] += 1
                    reasons.append(f"section:{section_hint}")
            
            # 2. Last pages heuristic for conclusion intent
            if intent == "conclusion" and total_pages and page_no:
                last_page_threshold = total_pages * 0.8
                if page_no >= last_page_threshold:
                    boost_factor += self.last_pages_boost
                    boost_applied["last_pages"] += 1
                    reasons.append(f"last_pages:{page_no}/{total_pages}")
            
            # 3. Figure/table query boost
            if is_figure_table_query and node_type in ("figure", "table"):
                boost_factor += self.figure_table_boost
                boost_applied["figure_table"] += 1
                reasons.append(f"fig_tab:{node_type}")
            
            # Apply boost
            final_score = base_score * boost_factor
            
            boosted_result = dict(r)
            boosted_result["score"] = final_score
            boosted_result["original_score"] = base_score
            boosted_result["boost_factor"] = boost_factor
            boosted_result["boost_reasons"] = reasons
            
            boosted_results.append(boosted_result)
        
        # Re-sort by boosted score
        boosted_results.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(
            f"Section boost: intent={intent}, "
            f"section_boosts={boost_applied['section']}, "
            f"last_page_boosts={boost_applied['last_pages']}, "
            f"fig_tab_boosts={boost_applied['figure_table']}"
        )
        
        return SectionBoostResult(
            intent=intent,
            boosted_results=boosted_results,
            boost_applied=boost_applied,
            debug={
                "is_figure_table_query": is_figure_table_query,
                "total_pages": total_pages,
            }
        )


def get_section_booster() -> SectionBooster:
    """Get default section booster instance."""
    return SectionBooster()
