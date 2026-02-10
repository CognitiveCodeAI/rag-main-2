"""Core ACL data structures.

Single source of truth for the security model:
- Entitlements: resolved server-side identity + permissions
- Visibility: public / internal / restricted tiers
- DocumentACL: document-level access policy
- NodeACLOverride: node-level restrict-only override
"""

import enum
import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


class Visibility(str, enum.Enum):
    """Document visibility tier."""
    public = "public"          # Any user in the tenant can access
    internal = "internal"      # Users with matching role or group
    restricted = "restricted"  # Explicit user allowlist only


@dataclass(frozen=True)
class Entitlements:
    """Resolved entitlements for the current request.

    Resolved server-side (not from UI trust). Initially from headers,
    swappable to SSO/IdP/OPA without changing retrieval code.
    """
    tenant_id: str
    user_id: str
    roles: frozenset = field(default_factory=frozenset)
    groups: frozenset = field(default_factory=frozenset)
    is_admin: bool = False

    def entitlements_hash(self) -> str:
        """Deterministic hash for cache keying.

        Includes tenant_id, user_id, sorted roles, sorted groups.
        """
        parts = [
            self.tenant_id,
            self.user_id,
            ",".join(sorted(self.roles)),
            ",".join(sorted(self.groups)),
            str(self.is_admin),
        ]
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class DocumentACL:
    """ACL policy for a document."""
    tenant_id: str
    visibility: Visibility
    allowed_roles: List[str] = field(default_factory=list)
    allowed_groups: List[str] = field(default_factory=list)
    allowed_users: List[str] = field(default_factory=list)
    policy_version: int = 1

    @classmethod
    def from_db_row(cls, doc) -> "DocumentACL":
        """Build from a DocumentGraph ORM row."""
        return cls(
            tenant_id=doc.tenant_id or "default",
            visibility=Visibility(doc.visibility or "public"),
            allowed_roles=doc.allowed_roles or [],
            allowed_groups=doc.allowed_groups or [],
            allowed_users=doc.allowed_users or [],
            policy_version=doc.policy_version or 1,
        )

    def permits(self, entitlements: Entitlements) -> bool:
        """Check if entitlements grant access to this document.

        Rules (evaluated in order):
        1. Tenant must match (always)
        2. Admin bypasses visibility checks
        3. Public: any user in tenant
        4. Internal: user has at least one matching role OR group
        5. Restricted: user must be in allowed_users
        """
        # Tenant boundary — non-negotiable
        if entitlements.tenant_id != self.tenant_id:
            return False

        # Admin bypass (audit-logged by caller)
        if entitlements.is_admin:
            return True

        if self.visibility == Visibility.public:
            return True

        if self.visibility == Visibility.internal:
            # User must have at least one matching role or group
            if self.allowed_roles and entitlements.roles & frozenset(self.allowed_roles):
                return True
            if self.allowed_groups and entitlements.groups & frozenset(self.allowed_groups):
                return True
            # If no roles/groups are specified, internal acts like public within tenant
            if not self.allowed_roles and not self.allowed_groups:
                return True
            return False

        if self.visibility == Visibility.restricted:
            return entitlements.user_id in self.allowed_users

        return False


@dataclass
class NodeACLOverride:
    """Optional node-level ACL override stored in nodes.meta["acl_override"].

    RULE: Can only be MORE restrictive than the document policy, never less.
    A node in a public doc can be restricted; a node in a restricted doc
    cannot be made public.
    """
    visibility: Optional[Visibility] = None
    allowed_roles: Optional[List[str]] = None
    allowed_groups: Optional[List[str]] = None
    allowed_users: Optional[List[str]] = None

    @classmethod
    def from_meta(cls, meta: Optional[dict]) -> Optional["NodeACLOverride"]:
        """Parse from node.meta["acl_override"] dict. Returns None if absent."""
        if not meta:
            return None
        override_data = meta.get("acl_override")
        if not override_data:
            return None

        vis = None
        if override_data.get("visibility"):
            try:
                vis = Visibility(override_data["visibility"])
            except ValueError:
                vis = None

        return cls(
            visibility=vis,
            allowed_roles=override_data.get("allowed_roles"),
            allowed_groups=override_data.get("allowed_groups"),
            allowed_users=override_data.get("allowed_users"),
        )

    def permits(self, entitlements: Entitlements, doc_acl: DocumentACL) -> bool:
        """Check if this override permits access.

        Uses override fields where present, falls back to doc_acl otherwise.
        The override can only restrict further, not relax.
        """
        vis = self.visibility or doc_acl.visibility
        roles = self.allowed_roles if self.allowed_roles is not None else doc_acl.allowed_roles
        groups = self.allowed_groups if self.allowed_groups is not None else doc_acl.allowed_groups
        users = self.allowed_users if self.allowed_users is not None else doc_acl.allowed_users

        # Build a synthetic DocumentACL with the override values
        effective = DocumentACL(
            tenant_id=doc_acl.tenant_id,
            visibility=vis,
            allowed_roles=roles,
            allowed_groups=groups,
            allowed_users=users,
            policy_version=doc_acl.policy_version,
        )
        return effective.permits(entitlements)
