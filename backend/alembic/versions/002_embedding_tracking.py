"""Add vector_index_versions table for embedding tracking

Revision ID: 002
Revises: 001
Create Date: 2026-01-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # vector_index_versions - tracks which vectors are indexed in Milvus
    op.create_table(
        'vector_index_versions',
        sa.Column('doc_id', sa.String(256), nullable=False),
        sa.Column('version_id', sa.String(256), nullable=False),
        sa.Column('collection_name', sa.String(128), nullable=False),
        sa.Column('bundle_version', sa.String(32), nullable=False),
        sa.Column('vector_count', sa.Integer(), nullable=False),
        sa.Column('indexed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('doc_id', 'version_id', 'collection_name'),
    )
    op.create_index('ix_vector_index_doc', 'vector_index_versions', ['doc_id'])
    op.create_index('ix_vector_index_collection', 'vector_index_versions', ['collection_name'])
    
    # embedding_jobs - tracks embedding job status
    op.create_table(
        'embedding_jobs',
        sa.Column('job_id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('doc_id', sa.String(256), nullable=False),
        sa.Column('version_id', sa.String(256), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=True),
        sa.Column('record_count', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('bundle_uri', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_embedding_jobs_status', 'embedding_jobs', ['status'])
    op.create_index('ix_embedding_jobs_doc', 'embedding_jobs', ['doc_id', 'version_id'])


def downgrade() -> None:
    op.drop_table('embedding_jobs')
    op.drop_table('vector_index_versions')
