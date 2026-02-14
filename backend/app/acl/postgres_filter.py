"""Reusable SQLAlchemy filters for ACL enforcement.

Postgres is ALWAYS the final authorization gate.
Milvus filtering is an optimization; these filters are the security boundary.
"""

import logging
from typing import Optional

from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.acl.models import Entitlements
from app.db.graph_models import DocumentGraph

logger = logging.getLogger(__name__)


class ACLPostgresFilter:
    """Build SQLAlchemy filters for ACL enforcement."""

    @staticmethod
    def document_filter(query, entitlements: Optional[Entitlements]):
        """Apply ACL filter to a DocumentGraph query.

        Returns unmodified query if entitlements is None (ACL disabled).
        """
        if entitlements is None:
            return query

        # SECURITY ASSUMPTION:
        # Tenant predicate is mandatory and must remain outside visibility OR branches to prevent cross-tenant widening.
        # Always scope by tenant_id
        query = query.filter(DocumentGraph.tenant_id == entitlements.tenant_id)

        # Admin bypass
        if entitlements.is_admin:
            return query

        # INVARIANT:
        # Non-admin authorization is additive (OR over allowed visibility paths); changing OR/AND structure can silently deny or leak docs.
        # Build visibility-based OR conditions
        visibility_conditions = [
            DocumentGraph.visibility == "public",
        ]

        # Internal: user has matching role or group
        internal_conditions = []
        for role in entitlements.roles:
            internal_conditions.append(
                DocumentGraph.allowed_roles.op("@>")(f'["{role}"]')
            )
        for group in entitlements.groups:
            internal_conditions.append(
                DocumentGraph.allowed_groups.op("@>")(f'["{group}"]')
            )

        if internal_conditions:
            visibility_conditions.append(
                and_(
                    DocumentGraph.visibility == "internal",
                    or_(*internal_conditions),
                )
            )
        else:
            # No roles/groups: internal docs with empty allow-lists are accessible
            visibility_conditions.append(
                and_(
                    DocumentGraph.visibility == "internal",
                    or_(
                        DocumentGraph.allowed_roles.is_(None),
                        DocumentGraph.allowed_roles == "[]",
                    ),
                    or_(
                        DocumentGraph.allowed_groups.is_(None),
                        DocumentGraph.allowed_groups == "[]",
                    ),
                )
            )

        # Restricted: user must be in allowed_users
        # DATA INTEGRITY:
        # Keep restricted membership check explicit; NULL/empty allowed_users must never imply access.
        visibility_conditions.append(
            and_(
                DocumentGraph.visibility == "restricted",
                DocumentGraph.allowed_users.op("@>")(
                    f'["{entitlements.user_id}"]'
                ),
            )
        )

        # Documents with NULL visibility (pre-ACL data) are treated as public
        # FRAGILE COUPLING:
        # This legacy null-visibility compatibility path is relied on by pre-migration records; tightening requires coordinated backfill.
        visibility_conditions.append(DocumentGraph.visibility.is_(None))

        query = query.filter(or_(*visibility_conditions))

        return query

    @staticmethod
    def get_accessible_doc_ids(
        db: Session, entitlements: Optional[Entitlements]
    ) -> Optional[set]:
        """Get the set of doc_ids accessible to the user.

        Returns None if ACL is disabled (meaning all docs accessible).
        """
        if entitlements is None:
            return None

        query = db.query(DocumentGraph.doc_id)
        query = ACLPostgresFilter.document_filter(query, entitlements)
        return {row.doc_id for row in query.all()}
