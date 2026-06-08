"""Fail-closed JWT/OIDC bearer-token verification (C2/C3 — replaces the
trusted-header identity model with cryptographically verified identity).

Security policy (every failure denies — there is no fail-open path):
- Only the configured ASYMMETRIC algorithms are accepted (config validator
  rejects HS*/none, defeating key-confusion and unsigned-token attacks).
- Signature is verified against the issuer's JWKS (fetched + cached by ``kid``
  via PyJWT's ``PyJWKClient``).
- ``aud`` (audience) and ``iss`` (issuer) are required and checked.
- ``exp``/``nbf`` are checked with a small leeway.
- A missing/blank Authorization header, a non-Bearer scheme, a JWKS fetch
  failure, an unknown ``kid``, or any decode error all raise 401.

The signing-key lookup is isolated in ``_resolve_signing_key`` so tests can
inject a key and exercise the real ``jwt.decode`` policy without a network IdP.
"""

import logging
import threading
from typing import Optional

import jwt
from fastapi import HTTPException, Request

from app.acl.models import Entitlements

logger = logging.getLogger(__name__)

# Cache one PyJWKClient per JWKS URL (it maintains its own kid cache).
_jwks_clients: dict = {}
_jwks_lock = threading.Lock()


def _get_jwks_client(jwks_url: str, timeout: float = 5.0) -> "jwt.PyJWKClient":
    with _jwks_lock:
        client = _jwks_clients.get(jwks_url)
        if client is None:
            # Bounded timeout so a slow/unreachable issuer fails closed quickly
            # rather than hanging the request.
            client = jwt.PyJWKClient(jwks_url, cache_keys=True, timeout=timeout)
            _jwks_clients[jwks_url] = client
        return client


def _bearer_token(request: Request) -> str:
    """Extract the Bearer token, or raise 401."""
    header = request.headers.get("Authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization: Bearer token")
    return token.strip()


def _resolve_signing_key(token: str, settings):
    """Resolve the public signing key for a token from the issuer JWKS.

    Isolated for testability — tests monkeypatch this to return a known key.
    Any failure (no JWKS URL, fetch error, unknown kid) raises 401 (fail closed).
    """
    jwks_url = settings.effective_jwks_url
    if not jwks_url:
        raise HTTPException(status_code=401, detail="Authentication is misconfigured (no JWKS)")
    try:
        timeout = float(getattr(settings, "jwt_jwks_timeout_seconds", 5.0))
        return _get_jwks_client(jwks_url, timeout).get_signing_key_from_jwt(token).key
    except HTTPException:
        raise
    except Exception as exc:  # JWKS fetch / unknown kid / malformed token header
        logger.warning("JWKS signing-key resolution failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=401, detail="Token signing key could not be verified")


def verify_bearer_token(request: Request, settings) -> dict:
    """Verify the request's Bearer token and return its validated claims.

    Raises HTTPException(401) on any verification failure.
    """
    if not settings.oidc_audience or not settings.oidc_issuer:
        # Refuse to "verify" without the constraints that make verification meaningful.
        raise HTTPException(status_code=401, detail="Authentication is misconfigured")

    token = _bearer_token(request)

    # Defense-in-depth: reject disallowed/none algorithms and missing kid from
    # the (unverified) header BEFORE doing any key resolution or decode work.
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Malformed token header")
    if header.get("alg") not in set(settings.jwt_algorithms):
        raise HTTPException(status_code=401, detail="Token algorithm not allowed")
    if not header.get("kid"):
        raise HTTPException(status_code=401, detail="Token is missing a key id (kid)")

    signing_key = _resolve_signing_key(token, settings)
    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=list(settings.jwt_algorithms),
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            leeway=settings.jwt_leeway_seconds,
            options={
                "require": ["exp", "iss", "aud"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
    except jwt.PyJWTError as exc:
        logger.warning("JWT verification failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return claims


def _claim_to_frozenset(value) -> frozenset:
    """Normalize a roles/groups claim (list, or comma/space string) to a frozenset."""
    if value is None:
        return frozenset()
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace(",", " ").split()]
        return frozenset(p for p in parts if p)
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(str(v).strip() for v in value if str(v).strip())
    return frozenset()


def claims_to_entitlements(claims: dict, settings) -> Entitlements:
    """Map verified token claims to an Entitlements object. Raises 401 if the
    token lacks the tenant/user identity required to make an authz decision."""
    tenant_id = claims.get(settings.jwt_tenant_claim)
    user_id = claims.get(settings.jwt_user_claim)
    if not tenant_id or not user_id:
        raise HTTPException(
            status_code=401,
            detail="Token is missing required identity claims (tenant / subject)",
        )
    roles = _claim_to_frozenset(claims.get(settings.jwt_roles_claim))
    groups = _claim_to_frozenset(claims.get(settings.jwt_groups_claim))
    is_admin = bool(roles & frozenset(settings.acl_admin_roles))
    return Entitlements(
        tenant_id=str(tenant_id),
        user_id=str(user_id),
        roles=roles,
        groups=groups,
        is_admin=is_admin,
    )


def entitlements_from_token(request: Request, settings) -> Entitlements:
    """Full path: verify the bearer token and resolve Entitlements. Fail-closed."""
    claims = verify_bearer_token(request, settings)
    return claims_to_entitlements(claims, settings)
