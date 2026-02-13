"""SQLAlchemy models for Graph RAG schema (documents_v2, nodes, edges)."""

import enum
from datetime import date, datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .models import Base


class NodeType(enum.Enum):
    """Types of nodes in the document graph."""
    chunk = "chunk"
    figure = "figure"
    table = "table"
    page = "page"


class EdgeType(enum.Enum):
    """Types of edges between nodes."""
    adjacent_prev = "adjacent_prev"
    adjacent_next = "adjacent_next"
    references = "references"
    explained_by = "explained_by"


class ContentRegistry(Base):
    """Content registry for true content identity.

    Maps (tenant_id, content_hash) → canonical_doc_id to prevent logical duplicates
    when the same content is uploaded from different source_uri paths.
    Tenant-scoped to prevent cross-tenant duplicate detection.
    """

    __tablename__ = "content_registry"

    # Composite PK for tenant isolation
    tenant_id = Column(String(64), primary_key=True, nullable=False, default='default')
    content_hash = Column(String(64), primary_key=True, nullable=False)

    canonical_doc_id = Column(String(64), nullable=False, index=True)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    source_uri_first_seen = Column(Text, nullable=True)
    latest_doc_id = Column(String(64), nullable=True)
    alias_count = Column(Integer, nullable=False, default=1)
    
    def __repr__(self) -> str:
        return f"<ContentRegistry(hash={self.content_hash[:16]}..., canonical={self.canonical_doc_id})>"


class DocumentGraph(Base):
    """Documents table for graph RAG - coexists with original documents table."""
    
    __tablename__ = "documents_graph"
    
    doc_id = Column(String(64), primary_key=True)
    source_uri = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    meta = Column(JSONB, nullable=True)
    doc_summary_md = Column(Text, nullable=True)
    doc_summary_text = Column(Text, nullable=True)
    
    # Content identity - links to the canonical doc for this content
    canonical_doc_id = Column(String(64), nullable=True, index=True)
    
    # Embedding tracking - which Milvus collection version was used
    embedded_collection_version = Column(String(16), nullable=True)
    
    # Metadata columns for metadata-aware retrieval
    doc_date = Column(Date, nullable=True)  # Document date
    year = Column(Integer, nullable=True)  # Document year (for filtering)
    source_system = Column(String(64), nullable=True)  # e.g., "upload", "sharepoint", "drive"
    doc_type = Column(String(64), nullable=True)  # e.g., "policy", "memo", "contract", "paper"
    department = Column(String(64), nullable=True)  # e.g., "legal", "marketing", "hr", "engineering"
    authority_tier = Column(SmallInteger, nullable=True)  # 1=highest (policy), 2=procedure, 3=notes
    effective_from = Column(Date, nullable=True)  # Effective start date
    effective_to = Column(Date, nullable=True)  # Effective end date
    supersedes_doc_id = Column(String(64), nullable=True)  # ID of document this supersedes

    # ACL columns
    tenant_id = Column(String(64), nullable=True, index=True)
    visibility = Column(String(16), nullable=True, default="public")  # public | internal | restricted
    allowed_roles = Column(JSONB, nullable=True)    # ["analyst", "legal"]
    allowed_groups = Column(JSONB, nullable=True)   # ["legal-team", "hr-dept"]
    allowed_users = Column(JSONB, nullable=True)    # ["user@example.com"]
    policy_version = Column(Integer, nullable=True, default=1)
    acl_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    nodes = relationship("Node", back_populates="document", cascade="all, delete-orphan")
    edges = relationship("Edge", back_populates="document", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('doc_id', 'version', name='uq_documents_graph_doc_version'),
        Index('ix_dg_tenant_vis', 'tenant_id', 'visibility'),
    )
    
    def __repr__(self) -> str:
        return f"<DocumentGraph(doc_id={self.doc_id}, version={self.version})>"


class Node(Base):
    """Nodes table - unified storage for chunks, figures, tables."""
    
    __tablename__ = "nodes"
    
    node_id = Column(String(64), primary_key=True)
    doc_id = Column(String(64), ForeignKey("documents_graph.doc_id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    node_type = Column(Enum(NodeType, name='node_type_enum', create_type=False), nullable=False)
    page_no = Column(Integer, nullable=True)
    chunk_index_in_page = Column(Integer, nullable=True)
    label = Column(String(128), nullable=True)  # e.g., "Figure 1.5"
    caption_md = Column(Text, nullable=True)
    text_md = Column(Text, nullable=True)
    text_plain = Column(Text, nullable=True)
    bbox = Column(JSONB, nullable=True)  # {x0, y0, x1, y1}
    content_hash = Column(String(64), nullable=True)
    meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("DocumentGraph", back_populates="nodes")
    outgoing_edges = relationship("Edge", foreign_keys="Edge.from_node_id", back_populates="from_node", cascade="all, delete-orphan")
    incoming_edges = relationship("Edge", foreign_keys="Edge.to_node_id", back_populates="to_node", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint(
            "node_type != 'chunk' OR page_no IS NOT NULL",
            name='ck_chunk_has_page'
        ),
        UniqueConstraint(
            'doc_id', 'version', 'page_no', 'chunk_index_in_page',
            name='uq_nodes_chunk_order'
        ),
    )
    
    def __repr__(self) -> str:
        return f"<Node(node_id={self.node_id}, type={self.node_type.value}, page={self.page_no})>"


class Edge(Base):
    """Edges table - relationships between nodes."""
    
    __tablename__ = "edges"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String(64), ForeignKey("documents_graph.doc_id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    from_node_id = Column(String(64), ForeignKey("nodes.node_id", ondelete="CASCADE"), nullable=False)
    to_node_id = Column(String(64), ForeignKey("nodes.node_id", ondelete="CASCADE"), nullable=False)
    edge_type = Column(Enum(EdgeType, name='edge_type_enum', create_type=False), nullable=False)
    confidence = Column(Float, nullable=True, default=1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("DocumentGraph", back_populates="edges")
    from_node = relationship("Node", foreign_keys=[from_node_id], back_populates="outgoing_edges")
    to_node = relationship("Node", foreign_keys=[to_node_id], back_populates="incoming_edges")
    
    __table_args__ = (
        UniqueConstraint(
            'doc_id', 'version', 'from_node_id', 'to_node_id', 'edge_type',
            name='uq_edges_unique'
        ),
    )
    
    def __repr__(self) -> str:
        return f"<Edge({self.from_node_id} --{self.edge_type.value}--> {self.to_node_id})>"
