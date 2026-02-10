"""Add pipeline_stage column to ingest_jobs and embedding_jobs

Revision ID: 007
Revises: 006
Create Date: 2026-02-09

Adds a pipeline_stage column to both job tables so the backend can report
granular progress (e.g. 'extracting_content', 'generating_embeddings')
instead of just pending/processing/completed/failed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ingest_jobs', sa.Column('pipeline_stage', sa.String(32), nullable=True))
    op.add_column('embedding_jobs', sa.Column('pipeline_stage', sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column('embedding_jobs', 'pipeline_stage')
    op.drop_column('ingest_jobs', 'pipeline_stage')
