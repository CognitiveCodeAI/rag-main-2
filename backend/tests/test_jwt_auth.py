"""JWT/OIDC verification tests (C2/C3 / audit C-2).

Fully offline: an RSA keypair is generated in-process, tokens are signed with
it, and the verifier's JWKS lookup is monkeypatched to return the public key —
so the REAL jwt.decode policy (alg allow-list, aud, iss, exp, signature) is
exercised with no network or IdP. Runs in the default suite.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.config import Settings
from app.auth import jwt_verifier

ISSUER = "https://issuer.example.com"
AUDIENCE = "npr-api"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = _private_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
PUBLIC_PEM = _private_key.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)


def _settings(**overrides):
    base = dict(
        auth_enabled=True,
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_jwks_url=ISSUER + "/jwks",
        jwt_algorithms=["RS256"],
        jwt_tenant_claim="tenant_id",
        jwt_user_claim="sub",
        jwt_roles_claim="roles",
        jwt_groups_claim="groups",
        acl_admin_roles=["admin"],
    )
    base.update(overrides)
    return Settings(**base)


def _claims(**overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "tenant_id": "acme",
        "roles": ["analyst", "admin"],
        "groups": ["legal"],
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return claims


def _sign(claims, key=PRIVATE_PEM, alg="RS256"):
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": "test-key-1"})


class _Req:
    def __init__(self, token=None, raw=None):
        if raw is not None:
            self.headers = {"Authorization": raw}
        elif token is not None:
            self.headers = {"Authorization": f"Bearer {token}"}
        else:
            self.headers = {}


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch):
    # Real signature/claims verification, but no network: return our public key.
    monkeypatch.setattr(jwt_verifier, "_resolve_signing_key", lambda token, settings: PUBLIC_PEM)


def test_valid_token_yields_entitlements():
    ent = jwt_verifier.entitlements_from_token(_Req(_sign(_claims())), _settings())
    assert ent.tenant_id == "acme"
    assert ent.user_id == "user-123"
    assert "analyst" in ent.roles
    assert ent.is_admin is True  # "admin" is in acl_admin_roles


def test_missing_token_rejected():
    with pytest.raises(HTTPException) as e:
        jwt_verifier.verify_bearer_token(_Req(None), _settings())
    assert e.value.status_code == 401


def test_non_bearer_scheme_rejected():
    with pytest.raises(HTTPException) as e:
        jwt_verifier.verify_bearer_token(_Req(raw="Basic abc"), _settings())
    assert e.value.status_code == 401


def test_alg_none_rejected():
    token = jwt.encode(_claims(), None, algorithm="none")
    with pytest.raises(HTTPException) as e:
        jwt_verifier.verify_bearer_token(_Req(token), _settings())
    assert e.value.status_code == 401


def test_hs256_token_rejected_by_allowlist():
    # Any HS256 token must be rejected because the allow-list is RS256 only.
    # (This is the defense against public-key/HMAC confusion attacks.)
    forged = jwt.encode(_claims(), "attacker-chosen-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as e:
        jwt_verifier.verify_bearer_token(_Req(forged), _settings())
    assert e.value.status_code == 401


def test_wrong_issuer_rejected():
    token = _sign(_claims(iss="https://evil.example.com"))
    with pytest.raises(HTTPException) as e:
        jwt_verifier.verify_bearer_token(_Req(token), _settings())
    assert e.value.status_code == 401


def test_wrong_audience_rejected():
    token = _sign(_claims(aud="some-other-api"))
    with pytest.raises(HTTPException) as e:
        jwt_verifier.verify_bearer_token(_Req(token), _settings())
    assert e.value.status_code == 401


def test_expired_token_rejected():
    # Past the default 30s leeway.
    token = _sign(_claims(exp=int(time.time()) - 3600))
    with pytest.raises(HTTPException) as e:
        jwt_verifier.verify_bearer_token(_Req(token), _settings())
    assert e.value.status_code == 401


def test_tampered_signature_rejected():
    token = _sign(_claims())
    tampered = token[:-3] + ("aaa" if token[-3:] != "aaa" else "bbb")
    with pytest.raises(HTTPException) as e:
        jwt_verifier.verify_bearer_token(_Req(tampered), _settings())
    assert e.value.status_code == 401


def test_token_signed_by_other_key_rejected():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    token = _sign(_claims(), key=other_pem)
    with pytest.raises(HTTPException) as e:
        jwt_verifier.verify_bearer_token(_Req(token), _settings())
    assert e.value.status_code == 401


def test_missing_identity_claims_rejected():
    token = _sign(_claims(tenant_id=None))
    with pytest.raises(HTTPException) as e:
        jwt_verifier.entitlements_from_token(_Req(token), _settings())
    assert e.value.status_code == 401


def test_config_rejects_symmetric_algorithms():
    with pytest.raises(Exception):
        Settings(jwt_algorithms=["HS256"])
    with pytest.raises(Exception):
        Settings(jwt_algorithms=["none"])


def test_effective_jwks_url_derivation():
    s = Settings(oidc_issuer="https://iss.example.com", oidc_jwks_url="")
    assert s.effective_jwks_url == "https://iss.example.com/.well-known/jwks.json"


def test_settings_write_requires_admin_when_authenticated():
    # A non-admin authenticated user cannot mutate app settings (403).
    from fastapi.testclient import TestClient
    from main import app
    from app.acl.dependencies import get_entitlements
    from app.acl.models import Entitlements

    nonadmin = Entitlements(
        tenant_id="acme", user_id="u1",
        roles=frozenset({"analyst"}), groups=frozenset(), is_admin=False,
    )
    app.dependency_overrides[get_entitlements] = lambda: nonadmin
    try:
        client = TestClient(app)
        resp = client.put("/v1/settings", json={})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_entitlements, None)


def test_delete_document_requires_admin_when_authenticated():
    from fastapi.testclient import TestClient
    from main import app
    from app.acl.dependencies import get_entitlements
    from app.acl.models import Entitlements

    nonadmin = Entitlements(
        tenant_id="acme", user_id="u1",
        roles=frozenset({"analyst"}), groups=frozenset(), is_admin=False,
    )
    app.dependency_overrides[get_entitlements] = lambda: nonadmin
    try:
        client = TestClient(app)
        resp = client.delete("/v1/documents/some-doc-id")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_entitlements, None)


def test_settings_read_requires_auth_when_enabled(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    monkeypatch.setattr("app.acl.dependencies.get_settings", lambda: _settings())
    client = TestClient(app)
    assert client.get("/v1/settings").status_code == 401


def test_unauthenticated_write_route_rejected_when_auth_enabled(monkeypatch):
    # C2 acceptance: with auth enabled, POST /v1/ingest/document without a
    # bearer token is rejected (no token ever reaches ingestion).
    from fastapi.testclient import TestClient
    from main import app

    monkeypatch.setattr("app.acl.dependencies.get_settings", lambda: _settings())
    client = TestClient(app)
    resp = client.post(
        "/v1/ingest/document",
        files={"file": ("t.pdf", b"%PDF-1.4 test", "application/pdf")},
        data={"tenant_id": "attacker-tenant"},
    )
    assert resp.status_code == 401
