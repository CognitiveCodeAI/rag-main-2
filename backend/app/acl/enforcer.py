"""Defense-in-depth ACL enforcement for the QA pipeline.

Applied at EVERY stage:
1. Post vector search
2. Post fallback search
3. Post seed injection
4. Per expansion hop (adjacent, references, explained_by)
5. Context packing
6. Citation hydration

IMPORTANT: If any caching is added to the pipeline in the future,
cache keys MUST include tenant_id + entitlements_hash + policy_version.
Otherwise, cached results can leak across users.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.acl.models import (
    DocumentACL,
    Entitlements,
    NodeACLOverride,
)
from app.acl.postgres_filter import ACLPostgresFilter

logger = logging.getLogger(__name__)


class ACLEnforcer:
    """Central ACL enforcement for the QA pipeline.

    Each filter method returns the filtered subset of results.
    When entitlements is None (ACL disabled), returns results unchanged.
    """

    def __init__(self, db: Session, entitlements: Optional[Entitlements]):
        self.db = db
        self.entitlements = entitlements
        # FRAGILE COUPLING:
        # These caches are request-scoped; reusing enforcers across requests can leak prior-user authorization state.
        self._accessible_doc_ids: Optional[set] = None
        self._doc_acl_cache: Dict[str, DocumentACL] = {}
        self._acl_log: List[Dict[str, Any]] = []

    @property
    def acl_enabled(self) -> bool:
        return self.entitlements is not None

    def get_accessible_doc_ids(self) -> Optional[set]:
        """Lazily compute and cache the set of accessible doc_ids.

        Returns None if ACL disabled (all accessible).
        """
        if not self.acl_enabled:
            return None
        # PERFORMANCE COUPLING:
        # ACL doc-id set is cached for this request to avoid repeated policy SQL scans on each pipeline stage.
        if self._accessible_doc_ids is None:
            self._accessible_doc_ids = ACLPostgresFilter.get_accessible_doc_ids(
                self.db, self.entitlements
            )
            logger.debug(
                f"[ACL] Resolved {len(self._accessible_doc_ids)} accessible doc_ids "
                f"for tenant={self.entitlements.tenant_id}"
            )
        return self._accessible_doc_ids

    def get_milvus_acl_filter(self) -> Optional[str]:
        """Build Milvus boolean expression for pre-filtering (optimization only).

        IMPORTANT: This is NOT the security gate. Postgres is always the final check.
        """
        if not self.acl_enabled:
            return None

        # SECURITY ASSUMPTION:
        # This expression is pre-filter only; all callers must still invoke Postgres/ACLEnforcer stage filters.
        parts = [f'tenant_id == "{self.entitlements.tenant_id}"']
        if not self.entitlements.is_admin:
            parts.append('visibility != "restricted"')

        return " && ".join(parts)

    def filter_search_results(
        self, results: List[Dict[str, Any]], stage: str = "vector_search"
    ) -> List[Dict[str, Any]]:
        """Filter search results by accessible doc_ids.

        Used after: vector search, fallback search, seed injection.
        """
        accessible = self.get_accessible_doc_ids()
        if accessible is None:
            return results

        # DATA INTEGRITY:
        # Search-result records must carry canonical graph doc_id in "doc_id"; mismatched IDs are treated as unauthorized.
        allowed = [r for r in results if r.get("doc_id") in accessible]
        denied = len(results) - len(allowed)
        if denied > 0:
            self._log(stage, len(results), len(allowed), denied)
        return allowed

    def filter_nodes(self, nodes: list, stage: str = "expansion") -> list:
        """Filter Node ORM objects by doc-level + node-level ACL.

        Used after: each expansion hop, context packing.
        """
        accessible = self.get_accessible_doc_ids()
        if accessible is None:
            return nodes

        allowed = []
        denied_count = 0
        for node in nodes:
            # Doc-level check
            if node.doc_id not in accessible:
                denied_count += 1
                continue

            # Node-level ACL override check (restrict-only)
            if self._node_acl_denied(node):
                denied_count += 1
                continue

            allowed.append(node)

        if denied_count > 0:
            self._log(stage, len(nodes), len(allowed), denied_count)
        return allowed

    def filter_citations(
        self, citations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter citations in the final answer.

        Last line of defense: ensures no unauthorized content in response.
        """
        accessible = self.get_accessible_doc_ids()
        if accessible is None:
            return citations

        allowed = [c for c in citations if c.get("doc_id") in accessible]
        denied = len(citations) - len(allowed)
        if denied > 0:
            self._log("citations", len(citations), len(allowed), denied)
        return allowed

    def _node_acl_denied(self, node) -> bool:
        """Check if a node is denied by its node-level ACL override.

        Returns True if the node should be filtered out.
        """
        override = NodeACLOverride.from_meta(node.meta)
        if override is None:
            return False

        # Get or cache the document ACL
        doc_acl = self._get_doc_acl(node.doc_id)
        # WARNING:
        # Missing parent document ACL currently fails open; node/doc referential integrity must be preserved upstream.
        if doc_acl is None:
            return False

        return not override.permits(self.entitlements, doc_acl)

    def _get_doc_acl(self, doc_id: str) -> Optional[DocumentACL]:
        """Get DocumentACL for a doc_id, with caching."""
        # ORDER DEPENDENCY:
        # ACL snapshot is stable per request; policy changes mid-request are not reflected until next enforcer instance.
        if doc_id in self._doc_acl_cache:
            return self._doc_acl_cache[doc_id]

        from app.db.graph_models import DocumentGraph

        doc = (
            self.db.query(DocumentGraph)
            .filter(DocumentGraph.doc_id == doc_id)
            .first()
        )
        if doc is None:
            return None

        acl = DocumentACL.from_db_row(doc)
        self._doc_acl_cache[doc_id] = acl
        return acl

    def _log(self, stage: str, total: int, allowed: int, denied: int):
        """Record an ACL filtering decision for audit."""
        entry = {
            "stage": stage,
            "total": total,
            "allowed": allowed,
            "denied": denied,
        }
        if self.entitlements:
            entry["tenant_id"] = self.entitlements.tenant_id
            entry["user_id"] = self.entitlements.user_id
        self._acl_log.append(entry)
        logger.info(
            f"[ACL] {stage}: {denied}/{total} results filtered "
            f"(tenant={entry.get('tenant_id')})"
        )

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Return all ACL decisions for the request."""
        return self._acl_log
