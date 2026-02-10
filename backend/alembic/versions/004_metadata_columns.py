"""Add metadata columns to documents_graph for metadata-aware retrieval

Revision ID: 004
Revises: 003
Create Date: 2026-01-16

Columns added to documents_graph:
- doc_date (DATE, nullable) - Document date
- year (INTEGER, nullable) - Document year
- source_system (VARCHAR(64), nullable) - e.g., "upload", "sharepoint"
- doc_type (VARCHAR(64), nullable) - e.g., "policy", "memo", "contract"
- department (VARCHAR(64), nullable) - e.g., "legal", "marketing", "hr"
- authority_tier (SMALLINT, nullable) - 1=highest (policy), 2=procedure, 3=notes
- effective_from (DATE, nullable) - Effective start date
- effective_to (DATE, nullable) - Effective end date
- supersedes_doc_id (VARCHAR(64), nullable) - ID of document this supersedes
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add metadata columns to documents_graph
    op.add_column('documents_graph', sa.Column('doc_date', sa.Date(), nullable=True))
    op.add_column('documents_graph', sa.Column('year', sa.Integer(), nullable=True))
    op.add_column('documents_graph', sa.Column('source_system', sa.String(64), nullable=True))
    op.add_column('documents_graph', sa.Column('doc_type', sa.String(64), nullable=True))
    op.add_column('documents_graph', sa.Column('department', sa.String(64), nullable=True))
    op.add_column('documents_graph', sa.Column('authority_tier', sa.SmallInteger(), nullable=True))
    op.add_column('documents_graph', sa.Column('effective_from', sa.Date(), nullable=True))
    op.add_column('documents_graph', sa.Column('effective_to', sa.Date(), nullable=True))
    op.add_column('documents_graph', sa.Column('supersedes_doc_id', sa.String(64), nullable=True))
    
    # Create indexes for common filter patterns
    op.create_index('ix_documents_graph_year', 'documents_graph', ['year'])
    op.create_index('ix_documents_graph_doc_type', 'documents_graph', ['doc_type'])
    op.create_index('ix_documents_graph_department', 'documents_graph', ['department'])
    op.create_index('ix_documents_graph_authority_tier', 'documents_graph', ['authority_tier'])
    
    # Create composite index for common combined filters
    op.create_index('ix_documents_graph_year_type_dept', 'documents_graph', ['year', 'doc_type', 'department'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_documents_graph_year_type_dept', table_name='documents_graph')
    op.drop_index('ix_documents_graph_authority_tier', table_name='documents_graph')
    op.drop_index('ix_documents_graph_department', table_name='documents_graph')
    op.drop_index('ix_documents_graph_doc_type', table_name='documents_graph')
    op.drop_index('ix_documents_graph_year', table_name='documents_graph')
    
    # Drop columns
    op.drop_column('documents_graph', 'supersedes_doc_id')
    op.drop_column('documents_graph', 'effective_to')
    op.drop_column('documents_graph', 'effective_from')
    op.drop_column('documents_graph', 'authority_tier')
    op.drop_column('documents_graph', 'department')
    op.drop_column('documents_graph', 'doc_type')
    op.drop_column('documents_graph', 'source_system')
    op.drop_column('documents_graph', 'year')
    op.drop_column('documents_graph', 'doc_date')
