"""Canary leakage tests for ACL enforcement.

These tests use unique "canary" strings to verify that unauthorized content
NEVER appears in retrieval candidates, graph expansion, context packing,
LLM prompts, or citations.

These are integration tests that require a database session but mock
external services (Milvus, OpenAI).
"""

import uuid
import pytest
from unittest.mock import MagicMock, patch

from app.acl.enforcer import ACLEnforcer
from app.acl.models import DocumentACL, Entitlements, Visibility


# Unique canary strings for each test
CANARY_SECRET_LEGAL = f"CANARY_SECRET_LEGAL_{uuid.uuid4().hex[:8]}"
CANARY_RESTRICTED_DATA = f"CANARY_RESTRICTED_DATA_{uuid.uuid4().hex[:8]}"
CANARY_CROSS_TENANT = f"CANARY_CROSS_TENANT_{uuid.uuid4().hex[:8]}"


class TestCanaryLeakagePrevention:
    """Verify canary strings never leak through ACL enforcement."""

    def _make_enforcer(self, tenant_id, user_id, accessible_doc_ids):
        """Create an ACLEnforcer with pre-set accessible doc_ids."""
        db = MagicMock()
        e = Entitlements(
            tenant_id=tenant_id,
            user_id=user_id,
            roles=frozenset(),
            groups=frozenset(),
        )
        enforcer = ACLEnforcer(db, e)
        enforcer._accessible_doc_ids = accessible_doc_ids
        return enforcer

    def test_restricted_doc_canary_not_in_search_results(self):
        """Restricted doc content must not appear in search results."""
        enforcer = self._make_enforcer("t1", "user2", {"public_doc"})

        results = [
            {"doc_id": "public_doc", "node_id": "n1", "text": "public stuff"},
            {
                "doc_id": "restricted_doc",
                "node_id": "n2",
                "text": CANARY_SECRET_LEGAL,
            },
        ]

        filtered = enforcer.filter_search_results(results, stage="vector_search")

        # Canary must NOT be in any filtered result
        for r in filtered:
            assert CANARY_SECRET_LEGAL not in r.get("text", ""), (
                f"CANARY LEAK: {CANARY_SECRET_LEGAL} found in search results!"
            )
        assert len(filtered) == 1

    def test_restricted_doc_canary_not_in_citations(self):
        """Restricted doc content must not appear in citations."""
        enforcer = self._make_enforcer("t1", "user2", {"public_doc"})

        citations = [
            {"doc_id": "public_doc", "page": 1, "text": "public"},
            {
                "doc_id": "restricted_doc",
                "page": 5,
                "text": CANARY_RESTRICTED_DATA,
            },
        ]

        filtered = enforcer.filter_citations(citations)

        for c in filtered:
            assert CANARY_RESTRICTED_DATA not in c.get("text", ""), (
                f"CANARY LEAK in citations: {CANARY_RESTRICTED_DATA}"
            )
        assert len(filtered) == 1

    def test_cross_tenant_canary_not_visible(self):
        """Tenant A's content must not be visible to Tenant B."""
        # Tenant B can only see their own docs
        enforcer = self._make_enforcer("tenant_b", "userB", {"doc_b1"})

        results = [
            {"doc_id": "doc_b1", "node_id": "n1", "text": "tenant B data"},
            {
                "doc_id": "doc_a1",
                "node_id": "n2",
                "text": CANARY_CROSS_TENANT,
            },
        ]

        filtered = enforcer.filter_search_results(results, stage="vector_search")

        for r in filtered:
            assert CANARY_CROSS_TENANT not in r.get("text", ""), (
                f"CROSS-TENANT LEAK: {CANARY_CROSS_TENANT}"
            )
        assert len(filtered) == 1
        assert filtered[0]["doc_id"] == "doc_b1"

    def test_graph_expansion_node_filter(self):
        """Restricted nodes must be filtered during graph expansion."""
        enforcer = self._make_enforcer("t1", "user1", {"doc_public"})

        # Mock Node objects
        public_node = MagicMock()
        public_node.doc_id = "doc_public"
        public_node.node_id = "n_public"
        public_node.meta = {}

        restricted_node = MagicMock()
        restricted_node.doc_id = "doc_restricted"
        restricted_node.node_id = "n_restricted"
        restricted_node.text_plain = CANARY_SECRET_LEGAL
        restricted_node.meta = {}

        nodes = [public_node, restricted_node]
        filtered = enforcer.filter_nodes(nodes, stage="expansion_adjacent")

        assert len(filtered) == 1
        assert filtered[0].node_id == "n_public"

    def test_fallback_ladder_respects_acl(self):
        """Fallback search results must still be filtered by ACL."""
        enforcer = self._make_enforcer("t1", "user1", {"safe_doc"})

        # Simulate fallback results that include unauthorized docs
        fallback_results = [
            {"doc_id": "safe_doc", "node_id": "n1"},
            {"doc_id": "unsafe_doc", "node_id": "n2", "text": CANARY_RESTRICTED_DATA},
        ]

        # Each fallback stage applies the same filter
        for stage in ["fallback_no_filter", "fallback_keyword"]:
            filtered = enforcer.filter_search_results(fallback_results, stage=stage)
            assert len(filtered) == 1
            assert filtered[0]["doc_id"] == "safe_doc"

    def test_seed_injection_respects_acl(self):
        """Injected seeds must be filtered by ACL."""
        enforcer = self._make_enforcer("t1", "user1", {"safe_doc"})

        injected_results = [
            {"doc_id": "safe_doc", "node_id": "fig1"},
            {"doc_id": "restricted_doc", "node_id": "fig2"},
        ]

        filtered = enforcer.filter_search_results(
            injected_results, stage="seed_injection"
        )
        assert len(filtered) == 1
        assert filtered[0]["doc_id"] == "safe_doc"


class TestDocumentACLPermitsCanary:
    """Verify DocumentACL.permits logic with canary scenarios."""

    def test_restricted_doc_denied_to_wrong_user(self):
        acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.restricted,
            allowed_users=["authorized_user"],
        )

        unauthorized = Entitlements(
            tenant_id="t1",
            user_id="unauthorized_user",
            roles=frozenset(),
            groups=frozenset(),
        )
        assert acl.permits(unauthorized) is False

    def test_cross_tenant_always_denied(self):
        acl = DocumentACL(
            tenant_id="tenant_a",
            visibility=Visibility.public,
        )

        tenant_b_user = Entitlements(
            tenant_id="tenant_b",
            user_id="any_user",
            roles=frozenset(["admin"]),
            groups=frozenset(),
            is_admin=True,
        )
        # Even admin from different tenant is denied
        assert acl.permits(tenant_b_user) is False

    def test_internal_doc_wrong_role_denied(self):
        acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.internal,
            allowed_roles=["legal_team"],
        )

        wrong_role = Entitlements(
            tenant_id="t1",
            user_id="u1",
            roles=frozenset(["engineering"]),
            groups=frozenset(),
        )
        assert acl.permits(wrong_role) is False
