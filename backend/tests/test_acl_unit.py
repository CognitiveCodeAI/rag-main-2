"""Unit tests for ACL models, enforcer, and postgres filter."""

import pytest
from unittest.mock import MagicMock, patch

from app.acl.models import (
    DocumentACL,
    Entitlements,
    NodeACLOverride,
    Visibility,
)


# =============================================================================
# Entitlements
# =============================================================================

class TestEntitlements:
    def test_entitlements_creation(self):
        e = Entitlements(
            tenant_id="t1",
            user_id="u1",
            roles=frozenset(["analyst"]),
            groups=frozenset(["finance"]),
        )
        assert e.tenant_id == "t1"
        assert e.user_id == "u1"
        assert e.is_admin is False

    def test_entitlements_admin(self):
        e = Entitlements(
            tenant_id="t1",
            user_id="admin1",
            roles=frozenset(["admin"]),
            groups=frozenset(),
            is_admin=True,
        )
        assert e.is_admin is True

    def test_entitlements_hash_deterministic(self):
        e1 = Entitlements(
            tenant_id="t1",
            user_id="u1",
            roles=frozenset(["b", "a"]),
            groups=frozenset(["y", "x"]),
        )
        e2 = Entitlements(
            tenant_id="t1",
            user_id="u1",
            roles=frozenset(["a", "b"]),
            groups=frozenset(["x", "y"]),
        )
        assert e1.entitlements_hash() == e2.entitlements_hash()

    def test_entitlements_hash_varies_by_tenant(self):
        e1 = Entitlements(tenant_id="t1", user_id="u1")
        e2 = Entitlements(tenant_id="t2", user_id="u1")
        assert e1.entitlements_hash() != e2.entitlements_hash()


# =============================================================================
# DocumentACL.permits
# =============================================================================

class TestDocumentACLPermits:
    def _make_entitlements(self, tenant="t1", user="u1", roles=None, groups=None, admin=False):
        return Entitlements(
            tenant_id=tenant,
            user_id=user,
            roles=frozenset(roles or []),
            groups=frozenset(groups or []),
            is_admin=admin,
        )

    def test_wrong_tenant_always_denied(self):
        acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.public,
        )
        e = self._make_entitlements(tenant="t2")
        assert acl.permits(e) is False

    def test_admin_bypasses_all(self):
        acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.restricted,
            allowed_users=["other_user"],
        )
        e = self._make_entitlements(tenant="t1", admin=True)
        assert acl.permits(e) is True

    def test_public_any_tenant_user(self):
        acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.public,
        )
        e = self._make_entitlements(tenant="t1")
        assert acl.permits(e) is True

    def test_internal_requires_matching_role(self):
        acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.internal,
            allowed_roles=["analyst", "manager"],
        )
        # Has matching role
        e1 = self._make_entitlements(tenant="t1", roles=["analyst"])
        assert acl.permits(e1) is True

        # No matching role or group
        e2 = self._make_entitlements(tenant="t1", roles=["intern"])
        assert acl.permits(e2) is False

    def test_internal_requires_matching_group(self):
        acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.internal,
            allowed_groups=["finance"],
        )
        e1 = self._make_entitlements(tenant="t1", groups=["finance"])
        assert acl.permits(e1) is True

        e2 = self._make_entitlements(tenant="t1", groups=["hr"])
        assert acl.permits(e2) is False

    def test_internal_empty_lists_allows_all_tenant_users(self):
        acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.internal,
            allowed_roles=[],
            allowed_groups=[],
        )
        e = self._make_entitlements(tenant="t1")
        assert acl.permits(e) is True

    def test_restricted_requires_explicit_user(self):
        acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.restricted,
            allowed_users=["user1", "user2"],
        )
        e1 = self._make_entitlements(tenant="t1", user="user1")
        assert acl.permits(e1) is True

        e2 = self._make_entitlements(tenant="t1", user="user3")
        assert acl.permits(e2) is False

    def test_restricted_empty_users_denies_all(self):
        acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.restricted,
            allowed_users=[],
        )
        e = self._make_entitlements(tenant="t1", user="anyone")
        assert acl.permits(e) is False


# =============================================================================
# NodeACLOverride
# =============================================================================

class TestNodeACLOverride:
    def test_from_meta_none(self):
        assert NodeACLOverride.from_meta(None) is None
        assert NodeACLOverride.from_meta({}) is None
        assert NodeACLOverride.from_meta({"other": "data"}) is None

    def test_from_meta_with_override(self):
        meta = {
            "acl_override": {
                "visibility": "restricted",
                "allowed_users": ["special_user"],
            }
        }
        override = NodeACLOverride.from_meta(meta)
        assert override is not None
        assert override.visibility == "restricted"
        assert override.allowed_users == ["special_user"]

    def test_override_restricts_public_doc(self):
        """Node override can restrict a public doc's node."""
        override = NodeACLOverride(
            visibility="restricted",
            allowed_users=["user1"],
        )
        doc_acl = DocumentACL(
            tenant_id="t1",
            visibility=Visibility.public,
        )
        e_allowed = Entitlements(
            tenant_id="t1",
            user_id="user1",
            roles=frozenset(),
            groups=frozenset(),
        )
        e_denied = Entitlements(
            tenant_id="t1",
            user_id="user2",
            roles=frozenset(),
            groups=frozenset(),
        )
        assert override.permits(e_allowed, doc_acl) is True
        assert override.permits(e_denied, doc_acl) is False


# =============================================================================
# ACLEnforcer
# =============================================================================

class TestACLEnforcer:
    def test_acl_disabled_returns_all(self):
        from app.acl.enforcer import ACLEnforcer

        db = MagicMock()
        enforcer = ACLEnforcer(db, entitlements=None)

        assert enforcer.acl_enabled is False
        assert enforcer.get_accessible_doc_ids() is None

        results = [{"doc_id": "d1", "node_id": "n1"}]
        assert enforcer.filter_search_results(results) == results

    def test_filter_search_results_removes_unauthorized(self):
        from app.acl.enforcer import ACLEnforcer

        db = MagicMock()
        e = Entitlements(tenant_id="t1", user_id="u1")
        enforcer = ACLEnforcer(db, e)

        # Mock accessible doc_ids
        enforcer._accessible_doc_ids = {"doc_a", "doc_b"}

        results = [
            {"doc_id": "doc_a", "node_id": "n1"},
            {"doc_id": "doc_c", "node_id": "n2"},  # Not accessible
            {"doc_id": "doc_b", "node_id": "n3"},
        ]

        filtered = enforcer.filter_search_results(results)
        assert len(filtered) == 2
        assert filtered[0]["doc_id"] == "doc_a"
        assert filtered[1]["doc_id"] == "doc_b"

    def test_filter_citations_removes_unauthorized(self):
        from app.acl.enforcer import ACLEnforcer

        db = MagicMock()
        e = Entitlements(tenant_id="t1", user_id="u1")
        enforcer = ACLEnforcer(db, e)
        enforcer._accessible_doc_ids = {"doc_a"}

        citations = [
            {"doc_id": "doc_a", "page": 1},
            {"doc_id": "doc_x", "page": 2},
        ]
        filtered = enforcer.filter_citations(citations)
        assert len(filtered) == 1
        assert filtered[0]["doc_id"] == "doc_a"

    def test_audit_log_records_denials(self):
        from app.acl.enforcer import ACLEnforcer

        db = MagicMock()
        e = Entitlements(tenant_id="t1", user_id="u1")
        enforcer = ACLEnforcer(db, e)
        enforcer._accessible_doc_ids = {"doc_a"}

        enforcer.filter_search_results(
            [{"doc_id": "doc_a"}, {"doc_id": "doc_b"}],
            stage="test_stage",
        )

        log = enforcer.get_audit_log()
        assert len(log) == 1
        assert log[0]["stage"] == "test_stage"
        assert log[0]["denied"] == 1
        assert log[0]["allowed"] == 1


# =============================================================================
# Visibility enum
# =============================================================================

class TestVisibility:
    def test_values(self):
        assert Visibility.public.value == "public"
        assert Visibility.internal.value == "internal"
        assert Visibility.restricted.value == "restricted"
