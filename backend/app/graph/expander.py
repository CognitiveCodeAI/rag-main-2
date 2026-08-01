"""Graph expansion for retrieval-time context enrichment.

Given seed chunks from vector search, expands context to include:
1. Adjacent chunks (prev + next)
2. Referenced figures/tables (via reference edges)
3. Chunks that explain those figures/tables (via explained_by edges)

This is the "always-on" expansion that happens at retrieval time.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Set, Dict, Optional

from sqlalchemy.orm import Session

from app.db.graph_models import Node, Edge, EdgeType, NodeType

logger = logging.getLogger(__name__)


@dataclass
class ExpandedContext:
    """Result of graph expansion."""
    seed_nodes: List[Node]
    adjacent_nodes: List[Node]
    referenced_nodes: List[Node]  # Figures/tables
    explained_by_nodes: List[Node]  # Chunks explaining figures
    
    # For citation tracking
    node_sources: Dict[str, str] = field(default_factory=dict)  # node_id -> source type
    # Additional authorized nodes selected by query-aware evidence chaining.
    # Empty for the baseline path, preserving existing behavior.
    chain_nodes: List[Node] = field(default_factory=list)
    
    @property
    def all_nodes(self) -> List[Node]:
        """All unique nodes in expansion order."""
        seen = set()
        result = []
        
        for node in self.seed_nodes:
            if node.node_id not in seen:
                seen.add(node.node_id)
                result.append(node)
        
        for node in self.adjacent_nodes:
            if node.node_id not in seen:
                seen.add(node.node_id)
                result.append(node)
        
        for node in self.referenced_nodes:
            if node.node_id not in seen:
                seen.add(node.node_id)
                result.append(node)
        
        for node in self.explained_by_nodes:
            if node.node_id not in seen:
                seen.add(node.node_id)
                result.append(node)

        for node in self.chain_nodes:
            if node.node_id not in seen:
                seen.add(node.node_id)
                result.append(node)
        
        return result
    
    @property
    def total_nodes(self) -> int:
        return len(self.all_nodes)


class GraphExpander:
    """Expands seed chunks via graph traversal."""
    
    # Hard caps to prevent context explosion
    MAX_ADJACENT_PER_SEED = 2  # prev + next
    MAX_REFS_TOTAL = 2  # Total referenced figures/tables
    MAX_EXPLAINED_BY_PER_REF = 2  # Chunks per figure
    MAX_TOTAL_EXPANSION = 10  # Hard cap on total additional nodes
    
    def __init__(self, db: Session, acl_enforcer=None):
        """Initialize expander.

        Args:
            db: Database session
            acl_enforcer: Optional ACLEnforcer for filtering nodes at each hop
        """
        self.db = db
        self.acl_enforcer = acl_enforcer
    
    def expand(
        self,
        seed_chunk_ids: List[str],
        doc_id: Optional[str] = None,
        version: Optional[int] = None
    ) -> ExpandedContext:
        """Expand seed chunks to include related context.
        
        Algorithm:
        1. Load seed nodes
        2. For each seed, follow adjacent_prev and adjacent_next edges
        3. From (seed + adjacent), follow references edges to figures/tables (max 2 total)
        4. For each referenced figure, follow explained_by edge (max 2 per figure)
        
        Args:
            seed_chunk_ids: IDs of seed chunks from vector search
            doc_id: Optional document filter
            version: Optional version filter
            
        Returns:
            ExpandedContext with all nodes
        """
        # Track sources for citations
        node_sources: Dict[str, str] = {}
        
        # 1. Load seed nodes
        seed_nodes = self._load_nodes(seed_chunk_ids)
        if self.acl_enforcer:
            seed_nodes = self.acl_enforcer.filter_nodes(seed_nodes, stage="expansion_seed")
        for node in seed_nodes:
            node_sources[node.node_id] = 'seed'

        if not seed_nodes:
            return ExpandedContext(
                seed_nodes=[],
                adjacent_nodes=[],
                referenced_nodes=[],
                explained_by_nodes=[],
                node_sources={}
            )
        
        logger.debug(f"Expanding {len(seed_nodes)} seed nodes")
        
        # 2. Get adjacent nodes
        adjacent_nodes: List[Node] = []
        seen_ids: Set[str] = {n.node_id for n in seed_nodes}
        
        for seed in seed_nodes:
            adj = self._get_adjacent(seed, seen_ids)
            if self.acl_enforcer:
                adj = self.acl_enforcer.filter_nodes(adj, stage="expansion_adjacent")
            for node in adj:
                if node.node_id not in seen_ids:
                    adjacent_nodes.append(node)
                    seen_ids.add(node.node_id)
                    node_sources[node.node_id] = 'adjacent'
        
        # 3. Get referenced figures/tables from seed + adjacent
        source_nodes = seed_nodes + adjacent_nodes
        referenced_nodes = self._get_references(
            source_nodes,
            seen_ids,
            max_refs=self.MAX_REFS_TOTAL
        )
        if self.acl_enforcer:
            referenced_nodes = self.acl_enforcer.filter_nodes(
                referenced_nodes, stage="expansion_references"
            )

        for node in referenced_nodes:
            if node.node_id not in seen_ids:
                seen_ids.add(node.node_id)
                node_sources[node.node_id] = 'referenced'
        
        # 4. Get explained_by chunks for each referenced figure/table
        explained_by_nodes: List[Node] = []
        
        for ref_node in referenced_nodes:
            explaining = self._get_explained_by(
                ref_node,
                seen_ids,
                max_chunks=self.MAX_EXPLAINED_BY_PER_REF
            )
            if self.acl_enforcer:
                explaining = self.acl_enforcer.filter_nodes(
                    explaining, stage="expansion_explained_by"
                )

            for node in explaining:
                if node.node_id not in seen_ids:
                    explained_by_nodes.append(node)
                    seen_ids.add(node.node_id)
                    node_sources[node.node_id] = 'explained_by'
            
            # Check total expansion cap
            total_expansion = len(adjacent_nodes) + len(referenced_nodes) + len(explained_by_nodes)
            if total_expansion >= self.MAX_TOTAL_EXPANSION:
                logger.debug(f"Hit expansion cap at {total_expansion} nodes")
                break
        
        result = ExpandedContext(
            seed_nodes=seed_nodes,
            adjacent_nodes=adjacent_nodes,
            referenced_nodes=referenced_nodes,
            explained_by_nodes=explained_by_nodes,
            node_sources=node_sources
        )
        
        logger.info(
            f"Expanded {len(seed_nodes)} seeds to {result.total_nodes} total nodes "
            f"(adj={len(adjacent_nodes)}, ref={len(referenced_nodes)}, expl={len(explained_by_nodes)})"
        )
        
        return result
    
    def _load_nodes(self, node_ids: List[str]) -> List[Node]:
        """Load nodes by ID.
        
        Args:
            node_ids: List of node IDs
            
        Returns:
            List of Node objects
        """
        if not node_ids:
            return []
        
        return self.db.query(Node).filter(Node.node_id.in_(node_ids)).all()
    
    def _get_adjacent(
        self,
        node: Node,
        exclude_ids: Set[str]
    ) -> List[Node]:
        """Get adjacent nodes (prev + next).
        
        Args:
            node: Source node
            exclude_ids: Node IDs to exclude
            
        Returns:
            List of adjacent nodes (max 2)
        """
        # Query edges
        edges = self.db.query(Edge).filter(
            Edge.from_node_id == node.node_id,
            Edge.edge_type.in_([EdgeType.adjacent_prev, EdgeType.adjacent_next])
        ).all()
        
        adjacent_ids = [e.to_node_id for e in edges if e.to_node_id not in exclude_ids]
        
        if not adjacent_ids:
            return []
        
        return self.db.query(Node).filter(Node.node_id.in_(adjacent_ids)).all()
    
    def _get_references(
        self,
        source_nodes: List[Node],
        exclude_ids: Set[str],
        max_refs: int
    ) -> List[Node]:
        """Get referenced figures/tables.
        
        Args:
            source_nodes: Nodes to search for references
            exclude_ids: Node IDs to exclude
            max_refs: Maximum number of references to return
            
        Returns:
            List of referenced figure/table nodes
        """
        source_ids = [n.node_id for n in source_nodes]
        
        # Query reference edges
        edges = self.db.query(Edge).filter(
            Edge.from_node_id.in_(source_ids),
            Edge.edge_type == EdgeType.references
        ).order_by(Edge.confidence.desc()).limit(max_refs * 2).all()
        
        ref_ids = [e.to_node_id for e in edges if e.to_node_id not in exclude_ids][:max_refs]
        
        if not ref_ids:
            return []
        
        return self.db.query(Node).filter(Node.node_id.in_(ref_ids)).all()
    
    def _get_explained_by(
        self,
        figure_node: Node,
        exclude_ids: Set[str],
        max_chunks: int
    ) -> List[Node]:
        """Get chunks that explain a figure/table.
        
        Args:
            figure_node: Figure or table node
            exclude_ids: Node IDs to exclude
            max_chunks: Maximum chunks per figure
            
        Returns:
            List of explaining chunk nodes
        """
        # Query explained_by edges (figure -> chunk)
        edges = self.db.query(Edge).filter(
            Edge.from_node_id == figure_node.node_id,
            Edge.edge_type == EdgeType.explained_by
        ).order_by(Edge.confidence.desc()).limit(max_chunks * 2).all()
        
        chunk_ids = [e.to_node_id for e in edges if e.to_node_id not in exclude_ids][:max_chunks]
        
        if not chunk_ids:
            return []
        
        return self.db.query(Node).filter(Node.node_id.in_(chunk_ids)).all()
