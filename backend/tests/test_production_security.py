"""Unit tests for the production fail-closed security guard (C1/C5).

These run in the default suite (no external infra), so CI exercises them.
"""

from app.config import Settings


def test_development_is_not_production():
    assert Settings(environment="development").is_production is False
    assert Settings().is_production is False  # default profile


def test_production_profile_detected():
    assert Settings(environment="production").is_production is True
    assert Settings(environment="PROD").is_production is True


def test_production_with_insecure_defaults_reports_all_violations():
    s = Settings(
        environment="production",
        acl_enabled=False,
        db_password="ragpass",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
    )
    problems = s.validate_production_security()
    # ACL disabled + AUTH disabled + 3 weak credentials
    assert len(problems) == 5
    assert any("ACL_ENABLED" in p for p in problems)
    assert any("AUTH_ENABLED" in p for p in problems)
    assert any("DB_PASSWORD" in p for p in problems)


def _secure_auth(**extra):
    """Production config with auth correctly enabled and configured."""
    base = dict(
        environment="production",
        acl_enabled=True,
        auth_enabled=True,
        oidc_issuer="https://idp.example.com",
        oidc_audience="npr-api",
        oidc_jwks_url="https://idp.example.com/jwks",
        db_password="a-real-secret",
        minio_access_key="a-real-key",
        minio_secret_key="a-real-secret",
    )
    base.update(extra)
    return Settings(**base)


def test_production_with_secure_config_is_clean():
    assert _secure_auth().validate_production_security() == []


def test_production_requires_auth_enabled():
    s = _secure_auth(auth_enabled=False)
    problems = s.validate_production_security()
    assert any("AUTH_ENABLED" in p for p in problems)


def test_production_auth_enabled_but_unconfigured_flagged():
    s = _secure_auth(oidc_issuer="", oidc_audience="", oidc_jwks_url="")
    problems = s.validate_production_security()
    assert any("OIDC_ISSUER" in p for p in problems)
    assert any("OIDC_AUDIENCE" in p for p in problems)


def test_empty_credentials_flagged_in_production():
    s = _secure_auth(db_password="", minio_access_key="", minio_secret_key="")
    problems = s.validate_production_security()
    assert len(problems) == 3  # three empty credentials (auth correctly configured)
