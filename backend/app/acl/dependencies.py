"""FastAPI dependencies for ACL entitlements injection."""

from typing import Optional

from fastapi import Depends, Request

from app.acl.models import Entitlements
from app.acl.resolver import EntitlementsResolver
from app.config import get_settings


async def get_entitlements(request: Request) -> Optional[Entitlements]:
    """FastAPI dependency: resolve entitlements from request.

    Returns None when ACL is disabled (feature flag off).
    Soft dependency — routes continue to work without ACL headers
    when ACL is disabled.
    """
    settings = get_settings()
    return EntitlementsResolver.from_request(request, settings)


async def require_entitlements(request: Request) -> Entitlements:
    """FastAPI dependency: resolve entitlements, 401 if missing.

    Hard dependency — always returns valid Entitlements.
    When ACL is disabled, returns admin-level defaults.
    """
    settings = get_settings()
    return EntitlementsResolver.require(request, settings)
