"""Add explicit legacy-to-graph identity mapping columns

Revision ID: 010
Revises: 009
Create Date: 2026-02-13

Adds graph_doc_id/graph_version to legacy documents and ingest_jobs so
services can resolve canonical graph identity without source_uri heuristics.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("graph_doc_id", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("graph_version", sa.Integer(), nullable=True))
    op.create_index(
        "ix_documents_graph_doc_version",
        "documents",
        ["graph_doc_id", "graph_version"],
        unique=False,
    )

    op.add_column("ingest_jobs", sa.Column("graph_doc_id", sa.String(length=64), nullable=True))
    op.add_column("ingest_jobs", sa.Column("graph_version", sa.Integer(), nullable=True))
    op.create_index(
        "ix_ingest_jobs_graph_doc_version",
        "ingest_jobs",
        ["graph_doc_id", "graph_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ingest_jobs_graph_doc_version", table_name="ingest_jobs")
    op.drop_column("ingest_jobs", "graph_version")
    op.drop_column("ingest_jobs", "graph_doc_id")

    op.drop_index("ix_documents_graph_doc_version", table_name="documents")
    op.drop_column("documents", "graph_version")
    op.drop_column("documents", "graph_doc_id")
