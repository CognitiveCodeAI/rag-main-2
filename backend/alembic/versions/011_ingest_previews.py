"""Add ingest preview staging table

Revision ID: 011
Revises: 010
Create Date: 2026-02-13

Adds ingest_previews for two-step upload flow:
1) upload + metadata preview
2) user review/edit
3) process after confirmation
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_previews",
        sa.Column("preview_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("preview_doc_id", sa.String(length=256), nullable=False),
        sa.Column("preview_version_id", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("metadata_extracted", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_confidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'ready'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ingest_previews_status", "ingest_previews", ["status"], unique=False)
    op.create_index("ix_ingest_previews_expires_at", "ingest_previews", ["expires_at"], unique=False)
    op.create_index("ix_ingest_previews_created_at", "ingest_previews", ["created_at"], unique=False)
    op.create_index("ix_ingest_previews_checksum", "ingest_previews", ["checksum"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ingest_previews_checksum", table_name="ingest_previews")
    op.drop_index("ix_ingest_previews_created_at", table_name="ingest_previews")
    op.drop_index("ix_ingest_previews_expires_at", table_name="ingest_previews")
    op.drop_index("ix_ingest_previews_status", table_name="ingest_previews")
    op.drop_table("ingest_previews")
