"""Add app_settings table for runtime configuration

Revision ID: 008
Revises: 007
Create Date: 2026-02-12

Adds an app_settings table with a singleton constraint to store
runtime-configurable settings that can be changed via the UI.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('id', sa.Integer(), primary_key=True, default=1),
        # QA Settings
        sa.Column('enable_llm_query_rewrite', sa.Boolean(), nullable=False, default=False),
        sa.Column('retrieval_top_k', sa.Integer(), nullable=False, default=5),
        sa.Column('enable_reranking', sa.Boolean(), nullable=False, default=True),
        sa.Column('rerank_candidate_max', sa.Integer(), nullable=False, default=15),
        sa.Column('max_context_tokens', sa.Integer(), nullable=False, default=8000),
        # Ingestion Settings
        sa.Column('ocr_quality_threshold', sa.Float(), nullable=False, default=0.3),
        sa.Column('target_chunk_tokens', sa.Integer(), nullable=False, default=500),
        sa.Column('chunk_overlap_tokens', sa.Integer(), nullable=False, default=50),
        # Timestamp
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_app_settings_singleton', 'app_settings', ['id'], unique=True)

    # Insert default singleton row
    op.execute("""
        INSERT INTO app_settings (
            id,
            enable_llm_query_rewrite,
            retrieval_top_k,
            enable_reranking,
            rerank_candidate_max,
            max_context_tokens,
            ocr_quality_threshold,
            target_chunk_tokens,
            chunk_overlap_tokens
        ) VALUES (
            1,
            false,
            5,
            true,
            15,
            8000,
            0.3,
            500,
            50
        ) ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index('ix_app_settings_singleton', table_name='app_settings')
    op.drop_table('app_settings')
