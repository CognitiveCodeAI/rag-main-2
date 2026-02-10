"""Add ACL columns for document-level permissions

Revision ID: 006
Revises: 005
Create Date: 2026-02-07

This migration adds:
1. ACL columns on documents_graph: tenant_id, visibility, allowed_roles,
   allowed_groups, allowed_users, policy_version, acl_updated_at
2. tenant_id column on content_registry (for tenant-scoped content identity)
3. Composite index on (tenant_id, visibility) for efficient ACL queries
4. Unique index on content_registry(tenant_id, content_hash) for tenant isolation
5. Backfills existing data with default tenant and public visibility
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add ACL columns to documents_graph
    op.add_column('documents_graph', sa.Column('tenant_id', sa.String(64), nullable=True))
    op.add_column('documents_graph', sa.Column('visibility', sa.String(16), nullable=True))
    op.add_column('documents_graph', sa.Column('allowed_roles', JSONB, nullable=True))
    op.add_column('documents_graph', sa.Column('allowed_groups', JSONB, nullable=True))
    op.add_column('documents_graph', sa.Column('allowed_users', JSONB, nullable=True))
    op.add_column('documents_graph', sa.Column('policy_version', sa.Integer, nullable=True))
    op.add_column('documents_graph', sa.Column('acl_updated_at', sa.DateTime(timezone=True), nullable=True))

    # 2. Add tenant_id to content_registry
    op.add_column('content_registry', sa.Column('tenant_id', sa.String(64), nullable=True))

    # 3. Create indexes
    op.create_index('ix_dg_tenant_vis', 'documents_graph', ['tenant_id', 'visibility'])
    op.create_index('ix_documents_graph_tenant_id', 'documents_graph', ['tenant_id'])
    op.create_index(
        'ix_cr_tenant_hash', 'content_registry',
        ['tenant_id', 'content_hash'], unique=True
    )

    # 4. Backfill existing data with defaults
    op.execute("""
        UPDATE documents_graph
        SET tenant_id = 'default',
            visibility = 'public',
            policy_version = 1
        WHERE tenant_id IS NULL
    """)
    op.execute("""
        UPDATE content_registry
        SET tenant_id = 'default'
        WHERE tenant_id IS NULL
    """)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_cr_tenant_hash', table_name='content_registry')
    op.drop_index('ix_documents_graph_tenant_id', table_name='documents_graph')
    op.drop_index('ix_dg_tenant_vis', table_name='documents_graph')

    # Drop content_registry column
    op.drop_column('content_registry', 'tenant_id')

    # Drop documents_graph ACL columns
    op.drop_column('documents_graph', 'acl_updated_at')
    op.drop_column('documents_graph', 'policy_version')
    op.drop_column('documents_graph', 'allowed_users')
    op.drop_column('documents_graph', 'allowed_groups')
    op.drop_column('documents_graph', 'allowed_roles')
    op.drop_column('documents_graph', 'visibility')
    op.drop_column('documents_graph', 'tenant_id')
