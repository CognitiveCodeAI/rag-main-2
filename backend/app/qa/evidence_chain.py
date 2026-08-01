"""Query-aware evidence-chain retrieval over the authorized document graph.

This module adopts the useful online portion of HyCE-RAG without conflating a
structural relevance score with factual confidence.  It is deliberately
deterministic, bounded, feature-gated, and provenance preserving.
"""

from __future__ import annotations

import logging
import math
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.graph_models import Edge, EdgeType, Node
from app.graph.expander import ExpandedContext

logger = logging.getLogger(__name__)


SCORING_VERSION = "document-chain-v1"


@dataclass(frozen=True)
class EvidenceChainConfig:
    """Bounded configuration for query-aware graph propagation."""

    mode: str = "auto"  # off | auto | on
    route_threshold: float = 0.55
    max_hops: int = 3
    max_nodes: int = 30
    max_selected_nodes: int = 15
    max_chains: int = 6
    propagation_steps: int = 10
    restart_probability: float = 0.35
    convergence_tolerance: float = 1e-7
    propagation_weight: float = 0.50
    query_weight: float = 0.30
    seed_weight: float = 0.20
    path_overlap_threshold: float = 0.80

    def __post_init__(self) -> None:
        if self.mode not in {"off", "auto", "on"}:
            raise ValueError("evidence-chain mode must be off, auto, or on")
        if not 0.0 <= self.route_threshold <= 1.0:
            raise ValueError("route_threshold must be in [0, 1]")
        if not 1 <= self.max_hops <= 6:
            raise ValueError("max_hops must be in [1, 6]")
        if self.max_nodes < 1 or self.max_selected_nodes < 1 or self.max_chains < 1:
            raise ValueError("node and chain budgets must be positive")
        if self.max_selected_nodes > self.max_nodes:
            raise ValueError("max_selected_nodes cannot exceed max_nodes")
        if not 1 <= self.propagation_steps <= 100:
            raise ValueError("propagation_steps must be in [1, 100]")
        if not 0.0 < self.restart_probability <= 1.0:
            raise ValueError("restart_probability must be in (0, 1]")
        total_weight = self.propagation_weight + self.query_weight + self.seed_weight
        if not math.isclose(total_weight, 1.0, abs_tol=1e-9):
            raise ValueError("evidence-chain scoring weights must sum to 1")


@dataclass(frozen=True)
class RouteDecision:
    applied: bool
    mode: str
    score: float
    reasons: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applied": self.applied,
            "mode": self.mode,
            "score": round(self.score, 6),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ChainEdge:
    from_node_id: str
    to_node_id: str
    edge_type: str
    weight: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "edge_type": self.edge_type,
            "weight": round(self.weight, 6),
        }


@dataclass(frozen=True)
class ChainNodeScore:
    node_id: str
    final_score: float
    propagation_score: float
    query_relevance: float
    seed_relevance: float
    is_seed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "final_score": round(self.final_score, 6),
            "propagation_score": round(self.propagation_score, 6),
            "query_relevance": round(self.query_relevance, 6),
            "seed_relevance": round(self.seed_relevance, 6),
            "is_seed": self.is_seed,
        }


@dataclass(frozen=True)
class EvidencePath:
    path_id: str
    node_ids: Tuple[str, ...]
    edges: Tuple[ChainEdge, ...]
    relevance_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "node_ids": list(self.node_ids),
            "edges": [edge.to_dict() for edge in self.edges],
            "relevance_score": round(self.relevance_score, 6),
        }


@dataclass
class EvidenceChainResult:
    """Result and safe audit data for an evidence-chain attempt."""

    route: RouteDecision
    applied: bool = False
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    candidate_count: int = 0
    edge_count: int = 0
    iterations: int = 0
    converged: bool = False
    selected_scores: List[ChainNodeScore] = field(default_factory=list)
    paths: List[EvidencePath] = field(default_factory=list)
    ordered_node_ids: List[str] = field(default_factory=list)
    selected_node_ids: Set[str] = field(default_factory=set)
    additional_nodes: List[Node] = field(default_factory=list, repr=False)

    @classmethod
    def skipped(cls, route: RouteDecision) -> "EvidenceChainResult":
        return cls(route=route, applied=False)

    @classmethod
    def fallback(cls, route: RouteDecision, reason: str) -> "EvidenceChainResult":
        return cls(
            route=route,
            applied=False,
            fallback_used=True,
            fallback_reason=reason,
        )

    def to_audit_dict(self) -> Dict[str, Any]:
        """Serialize without text, denied identifiers, or unselected candidates."""
        return {
            "scoring_version": SCORING_VERSION,
            "route": self.route.to_dict(),
            "applied": self.applied,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "candidate_count": self.candidate_count,
            "edge_count": self.edge_count,
            "iterations": self.iterations,
            "converged": self.converged,
            "selected_nodes": [score.to_dict() for score in self.selected_scores],
            "paths": [path.to_dict() for path in self.paths],
            "ordered_node_ids": self.ordered_node_ids,
        }

    def restrict_to_authorized(self, authorized_node_ids: Set[str]) -> None:
        """Scrub final audit/packing selections after the shared ACL choke point."""
        self.selected_scores = [
            score
            for score in self.selected_scores
            if score.node_id in authorized_node_ids
        ]
        self.selected_node_ids.intersection_update(authorized_node_ids)
        self.ordered_node_ids = [
            node_id
            for node_id in self.ordered_node_ids
            if node_id in authorized_node_ids
        ]
        self.additional_nodes = [
            node
            for node in self.additional_nodes
            if node.node_id in authorized_node_ids
        ]
        self.paths = [
            path
            for path in self.paths
            if all(node_id in authorized_node_ids for node_id in path.node_ids)
        ]


class MultiHopRouter:
    """Conservative deterministic router for evidence-chain processing."""

    _COMPARISON_RE = re.compile(
        r"\b(compare|comparison|contrast|versus|vs\.?|difference|differ|better|worse)\b",
        re.IGNORECASE,
    )
    _RELATION_RE = re.compile(
        r"\b(relationship|relate[sd]?|connection|affect(?:s|ed)?|impact(?:s|ed)?|"
        r"because|why|lead(?:s|ing)? to|result(?:s|ed)? in)\b",
        re.IGNORECASE,
    )
    _TEMPORAL_RE = re.compile(
        r"\b(amend(?:ed|ment)?|supersed(?:e|ed|es)|effective date|current|latest|"
        r"before|after|subsequent|prior|timeline)\b",
        re.IGNORECASE,
    )
    _PROFESSIONAL_CHAIN_RE = re.compile(
        r"\b(contraindication|interaction|governing law|statute|regulation|amendment|"
        r"guideline|diagnosis|treatment|authority|precedent)\b",
        re.IGNORECASE,
    )
    _SYNTHESIS_RE = re.compile(
        r"\b(based on|taking into account|together with|across (?:the )?(?:documents|sources)|"
        r"how does .+ (?:compare|relate)|what .+ and (?:how|why|what))\b",
        re.IGNORECASE,
    )

    @classmethod
    def decide(cls, question: str, mode: str, threshold: float = 0.55) -> RouteDecision:
        if mode == "off":
            return RouteDecision(False, mode, 0.0, ("mode_off",))
        if mode == "on":
            return RouteDecision(True, mode, 1.0, ("forced_on",))

        normalized = " ".join((question or "").split())
        if not normalized:
            return RouteDecision(False, mode, 0.0, ("empty_question",))

        score = 0.0
        reasons: List[str] = []
        signals = (
            (cls._COMPARISON_RE, 0.35, "comparison"),
            (cls._RELATION_RE, 0.25, "causal_or_relational"),
            (cls._TEMPORAL_RE, 0.30, "temporal_or_versioned"),
            (cls._PROFESSIONAL_CHAIN_RE, 0.20, "professional_chain_term"),
            (cls._SYNTHESIS_RE, 0.35, "explicit_synthesis"),
        )
        for pattern, weight, reason in signals:
            if pattern.search(normalized):
                score += weight
                reasons.append(reason)

        # Multiple clauses are supporting evidence only; they cannot route alone.
        clause_count = len(re.findall(r"\b(?:and|then|while|whereas|but)\b|[;?]", normalized, re.I))
        if clause_count >= 2 and reasons:
            score += 0.15
            reasons.append("multiple_clauses")

        score = min(score, 1.0)
        applied = score >= threshold
        if not applied:
            reasons.append("below_threshold")
        return RouteDecision(applied, mode, score, tuple(reasons))


class EvidenceChainEngine:
    """Expands and ranks an ACL-authorized document-graph neighborhood."""

    _EDGE_TYPE_WEIGHTS: Mapping[EdgeType, float] = {
        EdgeType.adjacent_prev: 0.65,
        EdgeType.adjacent_next: 0.65,
        EdgeType.references: 0.90,
        EdgeType.explained_by: 0.85,
    }
    _TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.%/-]*")
    _STOPWORDS = {
        "about", "after", "also", "and", "are", "based", "before", "does",
        "from", "have", "into", "that", "the", "their", "then", "this", "what",
        "when", "where", "which", "while", "with", "would", "your", "how", "why",
    }

    def __init__(self, db: Session, acl_enforcer: Any, config: EvidenceChainConfig):
        self.db = db
        self.acl_enforcer = acl_enforcer
        self.config = config

    def build(
        self,
        expanded: ExpandedContext,
        question: str,
        seed_scores: Mapping[str, float],
        doc_id: Optional[str] = None,
        version: Optional[int] = None,
    ) -> EvidenceChainResult:
        route = MultiHopRouter.decide(
            question,
            mode=self.config.mode,
            threshold=self.config.route_threshold,
        )
        if not route.applied:
            return EvidenceChainResult.skipped(route)

        initial_nodes = self._dedupe_nodes(expanded.all_nodes)
        initial_nodes = self.acl_enforcer.filter_nodes(
            initial_nodes, stage="evidence_chain_initial"
        )
        initial_nodes = [
            node
            for node in initial_nodes
            if (doc_id is None or node.doc_id == doc_id)
            and (version is None or node.version == version)
        ]
        if not initial_nodes:
            return EvidenceChainResult.fallback(route, "no_authorized_candidates")

        nodes_by_id, edges = self._expand_authorized_neighborhood(
            initial_nodes, doc_id=doc_id, version=version
        )
        if not nodes_by_id:
            return EvidenceChainResult.fallback(route, "no_authorized_candidates")

        seed_ids = {node_id for node_id in seed_scores if node_id in nodes_by_id}
        if not seed_ids:
            seed_ids = {
                node.node_id for node in expanded.seed_nodes if node.node_id in nodes_by_id
            }
        if not seed_ids:
            return EvidenceChainResult.fallback(route, "no_authorized_seeds")

        normalized_seed = self._normalize_seed_scores(seed_ids, seed_scores)
        query_scores = {
            node_id: self._query_relevance(question, node)
            for node_id, node in nodes_by_id.items()
        }
        propagation, iterations, converged, adjacency = self._propagate(
            node_ids=set(nodes_by_id),
            edges=edges,
            restart_scores=normalized_seed,
        )

        scored = []
        for node_id in nodes_by_id:
            final = (
                self.config.propagation_weight * propagation.get(node_id, 0.0)
                + self.config.query_weight * query_scores[node_id]
                + self.config.seed_weight * normalized_seed.get(node_id, 0.0)
            )
            scored.append(
                ChainNodeScore(
                    node_id=node_id,
                    final_score=final,
                    propagation_score=propagation.get(node_id, 0.0),
                    query_relevance=query_scores[node_id],
                    seed_relevance=normalized_seed.get(node_id, 0.0),
                    is_seed=node_id in seed_ids,
                )
            )
        scored.sort(key=lambda item: (-item.final_score, item.node_id))

        selected = self._select_with_seed_preservation(scored, seed_ids)
        selected_ids = {item.node_id for item in selected}
        paths = self._assemble_paths(
            selected,
            seed_ids,
            adjacency,
            edges,
        )
        ordered_ids = self._order_nodes(paths, selected)
        initial_ids = {node.node_id for node in initial_nodes}

        return EvidenceChainResult(
            route=route,
            applied=True,
            candidate_count=len(nodes_by_id),
            edge_count=len(edges),
            iterations=iterations,
            converged=converged,
            selected_scores=selected,
            paths=paths,
            ordered_node_ids=ordered_ids,
            selected_node_ids=selected_ids,
            additional_nodes=[
                nodes_by_id[node_id]
                for node_id in ordered_ids
                if node_id not in initial_ids
            ],
        )

    def _expand_authorized_neighborhood(
        self,
        initial_nodes: Sequence[Node],
        doc_id: Optional[str],
        version: Optional[int],
    ) -> Tuple[Dict[str, Node], List[Edge]]:
        nodes_by_id = {node.node_id: node for node in initial_nodes[: self.config.max_nodes]}
        frontier = set(nodes_by_id)
        candidate_edges: List[Edge] = []

        for hop in range(1, self.config.max_hops + 1):
            if not frontier or len(nodes_by_id) >= self.config.max_nodes:
                break

            edge_query = self.db.query(Edge).filter(
                or_(Edge.from_node_id.in_(frontier), Edge.to_node_id.in_(frontier))
            )
            if doc_id is not None:
                edge_query = edge_query.filter(Edge.doc_id == doc_id)
            if version is not None:
                edge_query = edge_query.filter(Edge.version == version)
            hop_edges = (
                edge_query.order_by(Edge.confidence.desc(), Edge.id.asc())
                .limit(self.config.max_nodes * 8)
                .all()
            )
            hop_edges = [
                edge
                for edge in hop_edges
                if (edge.from_node_id in frontier or edge.to_node_id in frontier)
                and (doc_id is None or edge.doc_id == doc_id)
                and (version is None or edge.version == version)
            ]
            candidate_edges.extend(hop_edges)

            neighbor_ids: Set[str] = set()
            for edge in hop_edges:
                if edge.from_node_id in frontier:
                    neighbor_ids.add(edge.to_node_id)
                if edge.to_node_id in frontier:
                    neighbor_ids.add(edge.from_node_id)
            neighbor_ids.difference_update(nodes_by_id)
            if not neighbor_ids:
                frontier = set()
                continue

            node_query = self.db.query(Node).filter(Node.node_id.in_(neighbor_ids))
            if doc_id is not None:
                node_query = node_query.filter(Node.doc_id == doc_id)
            if version is not None:
                node_query = node_query.filter(Node.version == version)
            neighbors = (
                node_query.order_by(Node.node_id.asc())
                .limit(self.config.max_nodes * 4)
                .all()
            )
            neighbors = [
                node
                for node in neighbors
                if node.node_id in neighbor_ids
                and (doc_id is None or node.doc_id == doc_id)
                and (version is None or node.version == version)
            ]
            neighbors = self.acl_enforcer.filter_nodes(
                neighbors, stage=f"evidence_chain_hop_{hop}"
            )
            remaining = self.config.max_nodes - len(nodes_by_id)
            neighbors = neighbors[:remaining]
            frontier = {node.node_id for node in neighbors}
            nodes_by_id.update((node.node_id, node) for node in neighbors)

        authorized_ids = set(nodes_by_id)
        unique_edges: Dict[Tuple[str, str, str], Edge] = {}
        for edge in candidate_edges:
            if edge.from_node_id not in authorized_ids or edge.to_node_id not in authorized_ids:
                continue
            edge_type = self._edge_type_value(edge.edge_type)
            key = (edge.from_node_id, edge.to_node_id, edge_type)
            unique_edges[key] = edge
        return nodes_by_id, [unique_edges[key] for key in sorted(unique_edges)]

    def _propagate(
        self,
        node_ids: Set[str],
        edges: Sequence[Edge],
        restart_scores: Mapping[str, float],
    ) -> Tuple[Dict[str, float], int, bool, Dict[str, Dict[str, float]]]:
        adjacency: Dict[str, Dict[str, float]] = {node_id: {} for node_id in node_ids}
        for edge in edges:
            if edge.from_node_id == edge.to_node_id:
                continue
            base = self._EDGE_TYPE_WEIGHTS.get(edge.edge_type, 0.5)
            confidence = self._clamp_confidence(edge.confidence)
            weight = base * confidence
            if weight <= 0.0:
                continue
            adjacency[edge.from_node_id][edge.to_node_id] = max(
                adjacency[edge.from_node_id].get(edge.to_node_id, 0.0), weight
            )
            adjacency[edge.to_node_id][edge.from_node_id] = max(
                adjacency[edge.to_node_id].get(edge.from_node_id, 0.0), weight
            )

        restart = {node_id: max(0.0, restart_scores.get(node_id, 0.0)) for node_id in node_ids}
        restart_total = sum(restart.values())
        if restart_total <= 0.0:
            uniform = 1.0 / len(node_ids)
            restart = {node_id: uniform for node_id in node_ids}
        else:
            restart = {node_id: value / restart_total for node_id, value in restart.items()}

        current = dict(restart)
        converged = False
        iterations = 0
        restart_probability = self.config.restart_probability
        for iteration in range(1, self.config.propagation_steps + 1):
            next_scores = {
                node_id: restart_probability * restart[node_id] for node_id in node_ids
            }
            for source_id in sorted(node_ids):
                neighbors = adjacency[source_id]
                if not neighbors:
                    next_scores[source_id] += (1.0 - restart_probability) * current[source_id]
                    continue
                degree = sum(neighbors.values())
                if degree <= 0.0:
                    next_scores[source_id] += (1.0 - restart_probability) * current[source_id]
                    continue
                for target_id, weight in neighbors.items():
                    next_scores[target_id] += (
                        (1.0 - restart_probability) * current[source_id] * weight / degree
                    )
            total = sum(next_scores.values())
            if total > 0.0:
                next_scores = {node_id: value / total for node_id, value in next_scores.items()}
            delta = sum(abs(next_scores[node_id] - current[node_id]) for node_id in node_ids)
            current = next_scores
            iterations = iteration
            if delta <= self.config.convergence_tolerance:
                converged = True
                break
        return current, iterations, converged, adjacency

    def _select_with_seed_preservation(
        self,
        scored: Sequence[ChainNodeScore],
        seed_ids: Set[str],
    ) -> List[ChainNodeScore]:
        by_id = {item.node_id: item for item in scored}
        selected_ids = [item.node_id for item in scored[: self.config.max_selected_nodes]]
        for seed_id in sorted(
            seed_ids,
            key=lambda node_id: (-by_id[node_id].final_score, node_id),
        ):
            if seed_id in selected_ids or seed_id not in by_id:
                continue
            if len(selected_ids) >= self.config.max_selected_nodes:
                replace_index = next(
                    (
                        index
                        for index in range(len(selected_ids) - 1, -1, -1)
                        if selected_ids[index] not in seed_ids
                    ),
                    None,
                )
                if replace_index is not None:
                    selected_ids[replace_index] = seed_id
            else:
                selected_ids.append(seed_id)
        selected = [by_id[node_id] for node_id in dict.fromkeys(selected_ids)]
        selected.sort(key=lambda item: (-item.final_score, item.node_id))
        return selected

    def _assemble_paths(
        self,
        selected: Sequence[ChainNodeScore],
        seed_ids: Set[str],
        adjacency: Mapping[str, Mapping[str, float]],
        edges: Sequence[Edge],
    ) -> List[EvidencePath]:
        scores = {item.node_id: item.final_score for item in selected}
        edge_lookup: Dict[frozenset[str], Edge] = {}
        for edge in edges:
            edge_lookup[frozenset((edge.from_node_id, edge.to_node_id))] = edge

        candidate_paths: List[Tuple[float, Tuple[str, ...]]] = []
        for target in selected:
            if target.node_id in seed_ids:
                continue
            node_path = self._shortest_path_to_seed(
                target.node_id,
                seed_ids,
                adjacency,
                scores,
                allowed_node_ids=set(scores),
            )
            if len(node_path) < 2:
                continue
            path_score = sum(scores.get(node_id, 0.0) for node_id in node_path) / len(node_path)
            candidate_paths.append((path_score, tuple(node_path)))

        if not candidate_paths:
            candidate_paths = [
                (scores.get(seed_id, 0.0), (seed_id,))
                for seed_id in sorted(seed_ids)
                if seed_id in scores
            ]
        candidate_paths.sort(key=lambda item: (-item[0], item[1]))

        accepted: List[Tuple[float, Tuple[str, ...]]] = []
        for candidate in candidate_paths:
            candidate_set = set(candidate[1])
            duplicate = False
            for _, existing_nodes in accepted:
                existing_set = set(existing_nodes)
                union = candidate_set | existing_set
                overlap = len(candidate_set & existing_set) / len(union) if union else 1.0
                if overlap >= self.config.path_overlap_threshold:
                    duplicate = True
                    break
            if not duplicate:
                accepted.append(candidate)
            if len(accepted) >= self.config.max_chains:
                break

        paths: List[EvidencePath] = []
        for index, (path_score, node_ids) in enumerate(accepted, start=1):
            path_edges: List[ChainEdge] = []
            for left, right in zip(node_ids, node_ids[1:]):
                edge = edge_lookup.get(frozenset((left, right)))
                if edge is None:
                    continue
                path_edges.append(
                    ChainEdge(
                        from_node_id=left,
                        to_node_id=right,
                        edge_type=self._edge_type_value(edge.edge_type),
                        weight=self._EDGE_TYPE_WEIGHTS.get(edge.edge_type, 0.5)
                        * self._clamp_confidence(edge.confidence),
                    )
                )
            paths.append(
                EvidencePath(
                    path_id=f"P{index}",
                    node_ids=node_ids,
                    edges=tuple(path_edges),
                    relevance_score=path_score,
                )
            )
        return paths

    def _shortest_path_to_seed(
        self,
        start: str,
        seed_ids: Set[str],
        adjacency: Mapping[str, Mapping[str, float]],
        scores: Mapping[str, float],
        allowed_node_ids: Set[str],
    ) -> List[str]:
        queue = deque([(start, [start])])
        visited = {start}
        while queue:
            current, path = queue.popleft()
            if current in seed_ids:
                return list(reversed(path))
            if len(path) - 1 >= self.config.max_hops:
                continue
            neighbors = sorted(
                (
                    node_id
                    for node_id in adjacency.get(current, {})
                    if node_id in allowed_node_ids
                ),
                key=lambda node_id: (-scores.get(node_id, 0.0), node_id),
            )
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
        return []

    @staticmethod
    def _order_nodes(
        paths: Sequence[EvidencePath],
        selected: Sequence[ChainNodeScore],
    ) -> List[str]:
        ordered: List[str] = []
        seen: Set[str] = set()
        for path in paths:
            for node_id in path.node_ids:
                if node_id not in seen:
                    ordered.append(node_id)
                    seen.add(node_id)
        for item in selected:
            if item.node_id not in seen:
                ordered.append(item.node_id)
                seen.add(item.node_id)
        return ordered

    @classmethod
    def _query_relevance(cls, question: str, node: Node) -> float:
        query_terms = cls._terms(question)
        if not query_terms:
            return 0.0
        meta = node.meta or {}
        searchable = " ".join(
            value
            for value in (
                node.text_plain or node.text_md or "",
                node.label or "",
                str(meta.get("section_hint") or ""),
            )
            if value
        )
        node_terms = cls._terms(searchable)
        if not node_terms:
            return 0.0
        return min(1.0, len(query_terms & node_terms) / len(query_terms))

    @classmethod
    def _terms(cls, text: str) -> Set[str]:
        return {
            token.lower()
            for token in cls._TOKEN_RE.findall(text or "")
            if len(token) >= 2 and token.lower() not in cls._STOPWORDS
        }

    @staticmethod
    def _normalize_seed_scores(
        seed_ids: Set[str], seed_scores: Mapping[str, float]
    ) -> Dict[str, float]:
        raw: Dict[str, float] = {}
        for node_id in seed_ids:
            try:
                value = float(seed_scores.get(node_id, 0.0))
            except (TypeError, ValueError):
                value = 0.0
            raw[node_id] = value if math.isfinite(value) else 0.0
        positive = {node_id: max(0.0, value) for node_id, value in raw.items()}
        maximum = max(positive.values())
        if maximum <= 0.0:
            return {node_id: 1.0 for node_id in raw}
        # Every authorized seed retains a bounded entry prior even when its
        # retrieval score is much lower than another seed's score.
        return {
            node_id: max(0.10, value / maximum)
            for node_id, value in positive.items()
        }

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.5
        if not math.isfinite(confidence):
            return 0.5
        return min(1.0, max(0.0, confidence))

    @staticmethod
    def _edge_type_value(edge_type: Any) -> str:
        return edge_type.value if hasattr(edge_type, "value") else str(edge_type)

    @staticmethod
    def _dedupe_nodes(nodes: Iterable[Node]) -> List[Node]:
        deduped: Dict[str, Node] = {}
        for node in nodes:
            deduped.setdefault(node.node_id, node)
        return list(deduped.values())
