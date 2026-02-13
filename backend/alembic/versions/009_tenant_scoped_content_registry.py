"""Make content_registry tenant-scoped with composite primary key

Revision ID: 009
Revises: 008
Create Date: 2026-02-12

This migration:
1. Backfills NULL tenant_id to 'default'
2. Makes tenant_id NOT NULL
3. Drops the old primary key (content_hash only)
4. Creates composite primary key (tenant_id, content_hash)
5. Drops redundant unique index ix_cr_tenant_hash (now covered by PK)

Purpose: Prevent cross-tenant duplicate detection by making (tenant_id, content_hash)
the true identity for content registry entries.

WARNING: Downgrade will fail if cross-tenant duplicates exist after upgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Backfill NULL tenant_id to 'default'
    op.execute("UPDATE content_registry SET tenant_id = 'default' WHERE tenant_id IS NULL")

    # 2. Make tenant_id NOT NULL
    op.alter_column('content_registry', 'tenant_id', nullable=False)

    # 3. Drop existing unique index (will be replaced by composite PK)
    op.drop_index('ix_cr_tenant_hash', table_name='content_registry')

    # 4. Drop old primary key (content_hash only)
    op.drop_constraint('content_registry_pkey', 'content_registry', type_='primary')

    # 5. Create composite primary key (tenant_id, content_hash)
    op.create_primary_key('content_registry_pkey', 'content_registry', ['tenant_id', 'content_hash'])


def downgrade() -> None:
    # WARNING: This will fail if cross-tenant duplicates exist
    # (same content_hash in different tenants)

    # 1. Drop composite PK
    op.drop_constraint('content_registry_pkey', 'content_registry', type_='primary')

    # 2. Recreate original single-column PK
    op.create_primary_key('content_registry_pkey', 'content_registry', ['content_hash'])

    # 3. Recreate unique index
    op.create_index('ix_cr_tenant_hash', 'content_registry', ['tenant_id', 'content_hash'], unique=True)

    # 4. Make tenant_id nullable again
    op.alter_column('content_registry', 'tenant_id', nullable=True)
