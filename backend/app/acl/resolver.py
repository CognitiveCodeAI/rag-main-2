"""Entitlements resolver — extracts identity from HTTP requests.

Initial implementation: header-based (reverse proxy pattern).
Production: replace with JWT token validation or OPA integration
without changing any retrieval code.
"""

import logging
from typing import Optional

from fastapi import HTTPException, Request

from app.acl.models import Entitlements

logger = logging.getLogger(__name__)

# Header names
HEADER_TENANT = "X-Tenant-Id"
HEADER_USER = "X-User-Id"
HEADER_ROLES = "X-Roles"    # comma-separated
HEADER_GROUPS = "X-Groups"  # comma-separated


class EntitlementsResolver:
    """Resolve entitlements from an HTTP request."""

    @classmethod
    def from_request(cls, request: Request, settings) -> Optional[Entitlements]:
        """Extract entitlements from request headers.

        Returns None if ACL is disabled (feature flag off).
        Returns None if headers are missing and strict_mode is off.
        Raises 401 if headers are missing and strict_mode is on.
        """
        if not settings.acl_enabled:
            return None

        tenant_id = request.headers.get(HEADER_TENANT)
        user_id = request.headers.get(HEADER_USER)

        # If no identity headers at all, handle based on strict mode
        if not tenant_id and not user_id:
            if settings.acl_strict_mode:
                raise HTTPException(
                    status_code=401,
                    detail="Missing required ACL headers: X-Tenant-Id, X-User-Id",
                )
            return None

        # Require both tenant and user when ACL is active
        if not tenant_id:
            raise HTTPException(
                status_code=401,
                detail="Missing required header: X-Tenant-Id",
            )
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Missing required header: X-User-Id",
            )

        # Parse roles and groups (comma-separated)
        roles_raw = request.headers.get(HEADER_ROLES, "")
        groups_raw = request.headers.get(HEADER_GROUPS, "")

        roles = frozenset(
            r.strip() for r in roles_raw.split(",") if r.strip()
        )
        groups = frozenset(
            g.strip() for g in groups_raw.split(",") if g.strip()
        )

        # Check if user has admin role
        admin_roles = frozenset(settings.acl_admin_roles)
        is_admin = bool(roles & admin_roles)

        entitlements = Entitlements(
            tenant_id=tenant_id,
            user_id=user_id,
            roles=roles,
            groups=groups,
            is_admin=is_admin,
        )

        if is_admin:
            logger.info(
                f"[ACL] Admin access: user={user_id}, tenant={tenant_id}"
            )

        return entitlements

    @classmethod
    def require(cls, request: Request, settings) -> Entitlements:
        """Extract entitlements, raising 401 if missing when ACL is enabled.

        Unlike from_request(), this always raises if ACL is on and headers are missing.
        If ACL is disabled, this dependency is considered unavailable and fails closed.
        """
        if not settings.acl_enabled:
            raise HTTPException(
                status_code=503,
                detail="ACL feature is disabled",
            )

        result = cls.from_request(request, settings)
        if result is None:
            raise HTTPException(
                status_code=401,
                detail="Authentication required: X-Tenant-Id and X-User-Id headers",
            )
        return result
