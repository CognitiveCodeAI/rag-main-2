"""Add immutable citation snapshots table

Revision ID: 012
Revises: 011
Create Date: 2026-02-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "citation_snapshots",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("request_id", sa.String(length=256), nullable=False),
        sa.Column("doc_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("selector_bundle", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exact_text", sa.Text(), nullable=True),
        sa.Column("answer_hash", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_citation_snapshots_request_id",
        "citation_snapshots",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        "ix_citation_snapshots_doc_version",
        "citation_snapshots",
        ["doc_id", "version"],
        unique=False,
    )
    op.create_index(
        "ix_citation_snapshots_created_at",
        "citation_snapshots",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_citation_snapshots_created_at", table_name="citation_snapshots")
    op.drop_index("ix_citation_snapshots_doc_version", table_name="citation_snapshots")
    op.drop_index("ix_citation_snapshots_request_id", table_name="citation_snapshots")
    op.drop_table("citation_snapshots")

