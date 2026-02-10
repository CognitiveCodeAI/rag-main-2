"""Graph schema: documents_graph, nodes, edges

Revision ID: 003
Revises: 002
Create Date: 2026-01-14

Tables:
- documents_graph: Document metadata with content_hash and summaries (coexists with original documents table)
- nodes: Unified node table (chunks, figures, tables)
- edges: Relationship table (adjacency, references, explained_by)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums if they don't exist
    conn = op.get_bind()
    
    # Check and create node_type_enum
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_type WHERE typname = 'node_type_enum'"
    )).fetchone()
    if not result:
        op.execute("CREATE TYPE node_type_enum AS ENUM ('chunk', 'figure', 'table', 'page')")
    
    # Check and create edge_type_enum
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_type WHERE typname = 'edge_type_enum'"
    )).fetchone()
    if not result:
        op.execute("CREATE TYPE edge_type_enum AS ENUM ('adjacent_prev', 'adjacent_next', 'references', 'explained_by')")
    
    # 1. documents_graph - new document table with graph support
    op.create_table(
        'documents_graph',
        sa.Column('doc_id', sa.String(64), primary_key=True),
        sa.Column('source_uri', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, default=1),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('meta', postgresql.JSONB(), nullable=True),
        sa.Column('doc_summary_md', sa.Text(), nullable=True),
        sa.Column('doc_summary_text', sa.Text(), nullable=True),
    )
    op.create_index('ix_documents_graph_source_uri', 'documents_graph', ['source_uri'])
    op.create_index('ix_documents_graph_content_hash', 'documents_graph', ['content_hash'])
    op.create_unique_constraint('uq_documents_graph_doc_version', 'documents_graph', ['doc_id', 'version'])
    
    # 2. nodes - unified node table (chunks, figures, tables)
    # Use existing enum types (created above)
    node_type = postgresql.ENUM('chunk', 'figure', 'table', 'page', name='node_type_enum', create_type=False)
    
    op.create_table(
        'nodes',
        sa.Column('node_id', sa.String(64), primary_key=True),
        sa.Column('doc_id', sa.String(64), sa.ForeignKey('documents_graph.doc_id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('node_type', node_type, nullable=False),
        sa.Column('page_no', sa.Integer(), nullable=True),
        sa.Column('chunk_index_in_page', sa.Integer(), nullable=True),
        sa.Column('label', sa.String(128), nullable=True),  # e.g., "Figure 1.5", "Table 2"
        sa.Column('caption_md', sa.Text(), nullable=True),
        sa.Column('text_md', sa.Text(), nullable=True),
        sa.Column('text_plain', sa.Text(), nullable=True),
        sa.Column('bbox', postgresql.JSONB(), nullable=True),  # {x0, y0, x1, y1}
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('meta', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Indexes for nodes
    op.create_index('ix_nodes_doc_version_type_page', 'nodes', ['doc_id', 'version', 'node_type', 'page_no'])
    op.create_index('ix_nodes_doc_version', 'nodes', ['doc_id', 'version'])
    op.create_index('ix_nodes_label', 'nodes', ['label'])
    
    # Constraint: chunk nodes must have page_no
    op.execute("""
        ALTER TABLE nodes ADD CONSTRAINT ck_chunk_has_page 
        CHECK (node_type != 'chunk' OR page_no IS NOT NULL)
    """)
    
    # Unique constraint for chunk ordering within a page (partial unique index)
    op.execute("""
        CREATE UNIQUE INDEX uq_nodes_chunk_order 
        ON nodes (doc_id, version, page_no, chunk_index_in_page)
        WHERE node_type = 'chunk'
    """)
    
    # 3. edges - relationship table
    edge_type = postgresql.ENUM('adjacent_prev', 'adjacent_next', 'references', 'explained_by', name='edge_type_enum', create_type=False)
    
    op.create_table(
        'edges',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('doc_id', sa.String(64), sa.ForeignKey('documents_graph.doc_id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('from_node_id', sa.String(64), sa.ForeignKey('nodes.node_id', ondelete='CASCADE'), nullable=False),
        sa.Column('to_node_id', sa.String(64), sa.ForeignKey('nodes.node_id', ondelete='CASCADE'), nullable=False),
        sa.Column('edge_type', edge_type, nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True, default=1.0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Indexes for edges
    op.create_index('ix_edges_doc_version_from_type', 'edges', ['doc_id', 'version', 'from_node_id', 'edge_type'])
    op.create_index('ix_edges_doc_version_to_type', 'edges', ['doc_id', 'version', 'to_node_id', 'edge_type'])
    op.create_index('ix_edges_from_node', 'edges', ['from_node_id'])
    op.create_index('ix_edges_to_node', 'edges', ['to_node_id'])
    
    # Unique constraint to prevent duplicate edges
    op.create_unique_constraint(
        'uq_edges_unique',
        'edges',
        ['doc_id', 'version', 'from_node_id', 'to_node_id', 'edge_type']
    )


def downgrade() -> None:
    # Drop indexes first
    op.execute('DROP INDEX IF EXISTS uq_nodes_chunk_order')
    
    op.drop_table('edges')
    op.drop_table('nodes')
    op.drop_table('documents_graph')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS edge_type_enum')
    op.execute('DROP TYPE IF EXISTS node_type_enum')
