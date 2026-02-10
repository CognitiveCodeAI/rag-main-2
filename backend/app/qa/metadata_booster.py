"""Metadata-aware boosting for RAG retrieval.

Boosts search results based on metadata constraints parsed from the query.
Similar pattern to section_booster.py but for document-level metadata.

CRITICAL: Total metadata boost is capped at MAX_TOTAL_BOOST to prevent
swamping semantic similarity scores.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .constraint_parser import ParsedConstraints

logger = logging.getLogger(__name__)


# =============================================================================
# BOOST WEIGHTS
# =============================================================================

# Individual boost weights (tuned to sum safely under the cap)
BOOST_WEIGHTS = {
    "year_match": 0.20,        # Exact year match
    "year_range_match": 0.15,  # Year within range
    "prefer_latest": 0.15,     # Newer docs when "current/latest" requested
    "prefer_authority": 0.15,  # Higher authority tier
    "department_match": 0.15,  # Department filter match
    "doc_type_match": 0.10,    # Doc type filter match
}

# CRITICAL: Maximum total boost from metadata (prevents swamping semantic scores)
MAX_TOTAL_BOOST = 0.40


@dataclass
class MetadataBoostResult:
    """Result of metadata boosting."""
    boosted_results: List[Dict[str, Any]]
    boost_applied: Dict[str, int]  # boost_type -> count of boosted nodes
    total_boosted: int
    debug: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "boost_applied": self.boost_applied,
            "total_boosted": self.total_boosted,
            "debug": self.debug,
        }


class MetadataBooster:
    """Applies metadata-aware boosting to search results.
    
    Boosts are capped at MAX_TOTAL_BOOST to ensure semantic similarity
    remains the primary ranking signal.
    """
    
    def __init__(
        self,
        year_match_boost: float = BOOST_WEIGHTS["year_match"],
        year_range_boost: float = BOOST_WEIGHTS["year_range_match"],
        latest_boost: float = BOOST_WEIGHTS["prefer_latest"],
        authority_boost: float = BOOST_WEIGHTS["prefer_authority"],
        department_boost: float = BOOST_WEIGHTS["department_match"],
        doc_type_boost: float = BOOST_WEIGHTS["doc_type_match"],
        max_total_boost: float = MAX_TOTAL_BOOST
    ):
        """Initialize booster.
        
        Args:
            year_match_boost: Weight for exact year match
            year_range_boost: Weight for year within range
            latest_boost: Weight for newer docs
            authority_boost: Weight for higher authority
            department_boost: Weight for department match
            doc_type_boost: Weight for doc type match
            max_total_boost: Maximum total boost (default 0.40)
        """
        self.year_match_boost = year_match_boost
        self.year_range_boost = year_range_boost
        self.latest_boost = latest_boost
        self.authority_boost = authority_boost
        self.department_boost = department_boost
        self.doc_type_boost = doc_type_boost
        self.max_total_boost = max_total_boost
    
    def boost_results(
        self,
        results: List[Dict[str, Any]],
        constraints: ParsedConstraints,
        nodes_metadata: Optional[Dict[str, Dict]] = None
    ) -> MetadataBoostResult:
        """Apply metadata-aware boosting to search results.
        
        Args:
            results: Search results with node_id, score, and optionally metadata
            constraints: Parsed constraints from query
            nodes_metadata: Optional dict of node_id -> metadata (if not in results)
            
        Returns:
            MetadataBoostResult with boosted results
        """
        boost_applied = {
            "year_match": 0,
            "year_range": 0,
            "prefer_latest": 0,
            "prefer_authority": 0,
            "department_match": 0,
            "doc_type_match": 0,
        }
        
        # Track highest year seen (for prefer_latest boost)
        max_year = self._find_max_year(results, nodes_metadata)
        
        boosted_results = []
        total_boosted = 0
        
        for r in results:
            node_id = r.get("node_id")
            base_score = r.get("score", 0.0)
            
            # Get metadata for this node
            meta = self._get_node_metadata(r, node_id, nodes_metadata)
            
            # Calculate individual boosts
            boosts = []
            reasons = []
            
            # 1. Year match (exact)
            if "year" in constraints.filters:
                target_year = constraints.filters["year"]
                node_year = meta.get("year")
                
                if node_year and node_year == target_year:
                    boosts.append(("year_match", self.year_match_boost))
                    boost_applied["year_match"] += 1
                    reasons.append(f"year_match:{node_year}")
            
            # 2. Year range match
            if "year_range" in constraints.filters:
                yr_range = constraints.filters["year_range"]
                node_year = meta.get("year")
                
                if node_year and isinstance(yr_range, (list, tuple)) and len(yr_range) == 2:
                    if yr_range[0] <= node_year <= yr_range[1]:
                        boosts.append(("year_range", self.year_range_boost))
                        boost_applied["year_range"] += 1
                        reasons.append(f"year_range:{node_year}∈{yr_range}")
            
            # 3. Prefer latest (boost newer docs)
            if constraints.boosts.get("prefer_latest") and max_year:
                node_year = meta.get("year")
                
                if node_year and node_year > 0:
                    # Graduated boost: full boost for max_year, decreasing for older
                    years_behind = max_year - node_year
                    if years_behind == 0:
                        boosts.append(("prefer_latest", self.latest_boost))
                        boost_applied["prefer_latest"] += 1
                        reasons.append(f"latest:{node_year}")
                    elif years_behind <= 2:
                        # Partial boost for within 2 years
                        partial = self.latest_boost * (1 - years_behind * 0.3)
                        if partial > 0:
                            boosts.append(("prefer_latest_partial", partial))
                            reasons.append(f"latest_partial:{node_year}")
            
            # 4. Prefer authority (boost higher authority tier)
            if constraints.boosts.get("prefer_authority"):
                authority_tier = meta.get("authority_tier")
                
                if authority_tier and authority_tier > 0:
                    # Tier 1 = full boost, tier 2 = partial, tier 3 = none
                    if authority_tier == 1:
                        boosts.append(("prefer_authority", self.authority_boost))
                        boost_applied["prefer_authority"] += 1
                        reasons.append(f"authority:tier{authority_tier}")
                    elif authority_tier == 2:
                        partial = self.authority_boost * 0.5
                        boosts.append(("prefer_authority_partial", partial))
                        reasons.append(f"authority_partial:tier{authority_tier}")
            
            # 5. Department match
            if "department" in constraints.filters:
                target_dept = constraints.filters["department"]
                node_dept = meta.get("department")
                
                if node_dept and node_dept.lower() == target_dept.lower():
                    boosts.append(("department_match", self.department_boost))
                    boost_applied["department_match"] += 1
                    reasons.append(f"dept_match:{node_dept}")
            
            # 6. Doc type match
            if "doc_type" in constraints.filters:
                target_type = constraints.filters["doc_type"]
                node_type = meta.get("doc_type")
                
                if node_type and node_type.lower() == target_type.lower():
                    boosts.append(("doc_type_match", self.doc_type_boost))
                    boost_applied["doc_type_match"] += 1
                    reasons.append(f"type_match:{node_type}")
            
            # Sum boosts and cap at MAX_TOTAL_BOOST
            total_boost = sum(b[1] for b in boosts)
            capped_boost = min(total_boost, self.max_total_boost)
            
            # Apply boost as multiplier: final_score = base_score * (1 + capped_boost)
            final_score = base_score * (1 + capped_boost)
            
            # Track if any boost was applied
            if total_boost > 0:
                total_boosted += 1
            
            # Create boosted result
            boosted_result = dict(r)
            boosted_result["score"] = final_score
            boosted_result["original_score"] = base_score
            boosted_result["metadata_boost"] = capped_boost
            boosted_result["metadata_boost_uncapped"] = total_boost
            boosted_result["metadata_boost_reasons"] = reasons
            
            boosted_results.append(boosted_result)
        
        # Re-sort by boosted score
        boosted_results.sort(key=lambda x: x["score"], reverse=True)
        
        logger.info(
            f"Metadata boost: {total_boosted}/{len(results)} results boosted, "
            f"applied={boost_applied}"
        )
        
        return MetadataBoostResult(
            boosted_results=boosted_results,
            boost_applied=boost_applied,
            total_boosted=total_boosted,
            debug={
                "max_year_seen": max_year,
                "max_total_boost": self.max_total_boost,
            }
        )
    
    def _get_node_metadata(
        self,
        result: Dict[str, Any],
        node_id: str,
        nodes_metadata: Optional[Dict[str, Dict]]
    ) -> Dict[str, Any]:
        """Get metadata for a node from result or external dict.
        
        Args:
            result: Search result dict
            node_id: Node ID
            nodes_metadata: Optional external metadata dict
            
        Returns:
            Metadata dict
        """
        # Check if metadata is already in result (from Milvus v2)
        meta = {
            "year": result.get("year"),
            "doc_type": result.get("doc_type"),
            "department": result.get("department"),
            "authority_tier": result.get("authority_tier"),
        }
        
        # Also check nodes_metadata dict (from Postgres)
        if nodes_metadata and node_id in nodes_metadata:
            external_meta = nodes_metadata[node_id]
            for key in ["year", "doc_type", "department", "authority_tier"]:
                if meta.get(key) is None and key in external_meta:
                    meta[key] = external_meta[key]
        
        return meta
    
    def _find_max_year(
        self,
        results: List[Dict[str, Any]],
        nodes_metadata: Optional[Dict[str, Dict]]
    ) -> Optional[int]:
        """Find the maximum year across all results.
        
        Args:
            results: Search results
            nodes_metadata: Optional external metadata
            
        Returns:
            Maximum year or None
        """
        max_year = None
        
        for r in results:
            node_id = r.get("node_id")
            meta = self._get_node_metadata(r, node_id, nodes_metadata)
            year = meta.get("year")
            
            if year and year > 0:
                if max_year is None or year > max_year:
                    max_year = year
        
        return max_year


def get_metadata_booster() -> MetadataBooster:
    """Get default MetadataBooster instance."""
    return MetadataBooster()
