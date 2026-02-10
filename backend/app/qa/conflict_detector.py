"""Conflict detection for metadata-aware retrieval.

Detects conflicts in cited sources that may affect trust:
- Year mismatches (sources from different years)
- Authority tier mismatches (policy vs notes)
- Doc type incompatibilities (policy vs memo)
- Effective date conflicts (overlapping or contradicting validity periods)

Conflicts are only flagged when they exceed thresholds ("why it matters").
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .constraint_parser import ParsedConstraints

logger = logging.getLogger(__name__)


@dataclass
class ConflictThresholds:
    """Thresholds for conflict detection.
    
    Only flag conflicts that exceed these thresholds to avoid noise.
    """
    # Year difference must be >= this to flag (or if user asked for "latest")
    year_diff_min: int = 1
    
    # Authority tier difference must be >= this to flag
    # (tier 1=policy vs tier 3=notes = diff of 2)
    authority_tier_diff_min: int = 2
    
    # Doc types that are considered incompatible when cited together
    incompatible_doc_types: Set[Tuple[str, str]] = field(default_factory=lambda: {
        ("policy", "memo"),
        ("policy", "notes"),
        ("contract", "memo"),
        ("procedure", "notes"),
    })


@dataclass
class Conflict:
    """A detected conflict in cited sources."""
    type: str  # year_mismatch, authority_mismatch, doc_type_mismatch, effective_date_conflict
    details: str
    sources: List[Dict[str, Any]]  # [{doc_id, year, authority_tier, ...}]
    recommendation: str
    severity: str = "warning"  # "info", "warning", "error"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "details": self.details,
            "sources": self.sources,
            "recommendation": self.recommendation,
            "severity": self.severity,
        }


@dataclass
class ConflictDetectionResult:
    """Result of conflict detection."""
    conflicts: List[Conflict]
    has_conflicts: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflicts": [c.to_dict() for c in self.conflicts],
            "has_conflicts": self.has_conflicts,
            "conflict_count": len(self.conflicts),
        }


def detect_conflicts(
    cited_nodes: List[Dict[str, Any]],
    constraints: ParsedConstraints,
    thresholds: Optional[ConflictThresholds] = None
) -> ConflictDetectionResult:
    """Detect conflicts in cited sources.
    
    Only flags conflicts that exceed thresholds or are contextually relevant
    (e.g., year mismatch when user asked for "latest").
    
    Args:
        cited_nodes: List of node dicts with metadata (year, doc_type, authority_tier, doc_id)
        constraints: Parsed constraints from query
        thresholds: Optional custom thresholds (uses defaults if None)
        
    Returns:
        ConflictDetectionResult with list of conflicts
    """
    if thresholds is None:
        thresholds = ConflictThresholds()
    
    conflicts: List[Conflict] = []
    
    # Group nodes by document to get unique doc metadata
    docs_by_id = _group_by_doc(cited_nodes)
    
    if len(docs_by_id) < 2:
        # No conflicts possible with single document
        return ConflictDetectionResult(conflicts=[], has_conflicts=False)
    
    # 1. Check year mismatch
    year_conflict = _check_year_mismatch(docs_by_id, constraints, thresholds)
    if year_conflict:
        conflicts.append(year_conflict)
    
    # 2. Check authority tier mismatch
    authority_conflict = _check_authority_mismatch(docs_by_id, thresholds)
    if authority_conflict:
        conflicts.append(authority_conflict)
    
    # 3. Check doc type incompatibility
    doc_type_conflict = _check_doc_type_incompatibility(docs_by_id, thresholds)
    if doc_type_conflict:
        conflicts.append(doc_type_conflict)
    
    # 4. Check effective date conflicts (future-proof)
    effective_conflict = _check_effective_date_conflict(docs_by_id)
    if effective_conflict:
        conflicts.append(effective_conflict)
    
    if conflicts:
        logger.info(f"Detected {len(conflicts)} conflicts in cited sources")
    
    return ConflictDetectionResult(
        conflicts=conflicts,
        has_conflicts=len(conflicts) > 0
    )


def _group_by_doc(nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Group nodes by document ID and extract doc metadata.
    
    Returns:
        Dict of doc_id -> {year, doc_type, department, authority_tier, node_count}
    """
    docs = {}
    
    for node in nodes:
        doc_id = node.get("doc_id")
        if not doc_id:
            continue
        
        if doc_id not in docs:
            docs[doc_id] = {
                "doc_id": doc_id,
                "year": node.get("year"),
                "doc_type": node.get("doc_type"),
                "department": node.get("department"),
                "authority_tier": node.get("authority_tier"),
                "effective_from": node.get("effective_from"),
                "effective_to": node.get("effective_to"),
                "node_count": 0,
            }
        
        docs[doc_id]["node_count"] += 1
        
        # Update metadata if not set (use first non-null value)
        for key in ["year", "doc_type", "department", "authority_tier", "effective_from", "effective_to"]:
            if docs[doc_id].get(key) is None and node.get(key) is not None:
                docs[doc_id][key] = node.get(key)
    
    return docs


def _check_year_mismatch(
    docs: Dict[str, Dict[str, Any]],
    constraints: ParsedConstraints,
    thresholds: ConflictThresholds
) -> Optional[Conflict]:
    """Check for year mismatch across documents."""
    years = []
    doc_years = []
    
    for doc_id, doc in docs.items():
        year = doc.get("year")
        if year and year > 0:
            years.append(year)
            doc_years.append({"doc_id": doc_id, "year": year})
    
    if len(years) < 2:
        return None
    
    min_year = min(years)
    max_year = max(years)
    year_diff = max_year - min_year
    
    # Check if conflict should be flagged
    should_flag = False
    
    # Always flag if user asked for "latest" and there's any difference
    if constraints.boosts.get("prefer_latest"):
        should_flag = year_diff >= 1
    # Otherwise only flag if diff exceeds threshold
    elif year_diff >= thresholds.year_diff_min:
        # For larger differences (>= 2 years), always flag
        should_flag = year_diff >= 2 or (
            year_diff >= thresholds.year_diff_min and 
            constraints.filters.get("year") is not None
        )
    
    if not should_flag:
        return None
    
    return Conflict(
        type="year_mismatch",
        details=f"Sources span {min_year}-{max_year} ({year_diff} year difference)",
        sources=doc_years,
        recommendation=f"Prefer {max_year} (newer) unless you specifically need historical information.",
        severity="warning" if year_diff >= 2 else "info"
    )


def _check_authority_mismatch(
    docs: Dict[str, Dict[str, Any]],
    thresholds: ConflictThresholds
) -> Optional[Conflict]:
    """Check for authority tier mismatch across documents."""
    tiers = []
    doc_tiers = []
    
    for doc_id, doc in docs.items():
        tier = doc.get("authority_tier")
        if tier and tier > 0:
            tiers.append(tier)
            doc_tiers.append({
                "doc_id": doc_id, 
                "authority_tier": tier,
                "doc_type": doc.get("doc_type")
            })
    
    if len(tiers) < 2:
        return None
    
    min_tier = min(tiers)  # Lower tier = higher authority
    max_tier = max(tiers)
    tier_diff = max_tier - min_tier
    
    if tier_diff < thresholds.authority_tier_diff_min:
        return None
    
    # Translate tiers to human-readable
    tier_names = {1: "policy/official", 2: "procedure/guideline", 3: "notes/informal"}
    
    return Conflict(
        type="authority_mismatch",
        details=f"Sources have different authority levels (tier {min_tier} vs tier {max_tier})",
        sources=doc_tiers,
        recommendation=f"For authoritative information, prefer {tier_names.get(min_tier, f'tier {min_tier}')} sources.",
        severity="warning"
    )


def _check_doc_type_incompatibility(
    docs: Dict[str, Dict[str, Any]],
    thresholds: ConflictThresholds
) -> Optional[Conflict]:
    """Check for incompatible document types being cited together."""
    doc_types = []
    doc_type_info = []
    
    for doc_id, doc in docs.items():
        doc_type = doc.get("doc_type")
        if doc_type:
            doc_types.append(doc_type.lower())
            doc_type_info.append({"doc_id": doc_id, "doc_type": doc_type})
    
    if len(doc_types) < 2:
        return None
    
    # Check for incompatible pairs
    unique_types = list(set(doc_types))
    incompatible_found = None
    
    for i, type1 in enumerate(unique_types):
        for type2 in unique_types[i+1:]:
            pair = (type1, type2)
            pair_reversed = (type2, type1)
            
            if pair in thresholds.incompatible_doc_types or pair_reversed in thresholds.incompatible_doc_types:
                incompatible_found = (type1, type2)
                break
        if incompatible_found:
            break
    
    if not incompatible_found:
        return None
    
    return Conflict(
        type="doc_type_mismatch",
        details=f"Sources include both {incompatible_found[0]} and {incompatible_found[1]} documents",
        sources=doc_type_info,
        recommendation=f"For official guidance, prefer {incompatible_found[0]} over {incompatible_found[1]}.",
        severity="info"
    )


def _check_effective_date_conflict(docs: Dict[str, Dict[str, Any]]) -> Optional[Conflict]:
    """Check for effective date conflicts (future-proof).
    
    This checks for:
    - Documents with non-overlapping effective periods
    - Documents where one supersedes another
    """
    # For now, this is a placeholder for future implementation
    # Would need effective_from/effective_to and supersedes_doc_id to be populated
    
    docs_with_dates = []
    for doc_id, doc in docs.items():
        if doc.get("effective_from") or doc.get("effective_to"):
            docs_with_dates.append({
                "doc_id": doc_id,
                "effective_from": doc.get("effective_from"),
                "effective_to": doc.get("effective_to"),
            })
    
    if len(docs_with_dates) < 2:
        return None
    
    # TODO: Implement actual overlap/conflict detection
    # For now, just log that we have multiple docs with dates
    logger.debug(f"Found {len(docs_with_dates)} docs with effective dates (conflict check not yet implemented)")
    
    return None


def get_conflict_detector():
    """Get conflict detection function (for dependency injection)."""
    return detect_conflicts
