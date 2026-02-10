"""Add content_registry table and canonical_doc_id column

Revision ID: 005
Revises: 004
Create Date: 2026-01-16

This migration adds:
1. content_registry table - maps content_hash → canonical_doc_id for true content identity
2. canonical_doc_id column on documents_graph - links to the canonical doc for this content
3. embedded_collection_version column on documents_graph - tracks which Milvus collection version was used

Purpose: Prevent logical duplicates when the same content is uploaded from different source_uri paths.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create content_registry table
    op.create_table(
        'content_registry',
        sa.Column('content_hash', sa.String(64), primary_key=True),
        sa.Column('canonical_doc_id', sa.String(64), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('source_uri_first_seen', sa.Text(), nullable=True),
        sa.Column('latest_doc_id', sa.String(64), nullable=True),
        sa.Column('alias_count', sa.Integer(), nullable=False, default=1),
    )
    
    # Index on canonical_doc_id for reverse lookups
    op.create_index('ix_content_registry_canonical_doc_id', 'content_registry', ['canonical_doc_id'])
    
    # 2. Add canonical_doc_id column to documents_graph
    op.add_column('documents_graph', sa.Column('canonical_doc_id', sa.String(64), nullable=True))
    
    # Index for finding all aliases of a canonical doc
    op.create_index('ix_documents_graph_canonical_doc_id', 'documents_graph', ['canonical_doc_id'])
    
    # 3. Add embedded_collection_version to track which Milvus collection was used
    op.add_column('documents_graph', sa.Column('embedded_collection_version', sa.String(16), nullable=True))
    
    # 4. Backfill canonical_doc_id for existing documents
    # Set canonical_doc_id = doc_id for all existing docs (they are their own canonical)
    op.execute("""
        UPDATE documents_graph 
        SET canonical_doc_id = doc_id 
        WHERE canonical_doc_id IS NULL
    """)
    
    # 5. Backfill content_registry from existing documents
    # Insert unique content_hash entries, using doc_id as canonical_doc_id
    op.execute("""
        INSERT INTO content_registry (content_hash, canonical_doc_id, first_seen_at, source_uri_first_seen, latest_doc_id, alias_count)
        SELECT DISTINCT ON (content_hash)
            content_hash,
            doc_id as canonical_doc_id,
            ingested_at as first_seen_at,
            source_uri as source_uri_first_seen,
            doc_id as latest_doc_id,
            1 as alias_count
        FROM documents_graph
        WHERE content_hash IS NOT NULL
        ORDER BY content_hash, ingested_at ASC
        ON CONFLICT (content_hash) DO NOTHING
    """)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_documents_graph_canonical_doc_id', table_name='documents_graph')
    op.drop_index('ix_content_registry_canonical_doc_id', table_name='content_registry')
    
    # Drop columns
    op.drop_column('documents_graph', 'embedded_collection_version')
    op.drop_column('documents_graph', 'canonical_doc_id')
    
    # Drop table
    op.drop_table('content_registry')
