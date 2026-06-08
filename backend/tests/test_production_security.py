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
    # ACL disabled + 3 weak credentials
    assert len(problems) == 4
    assert any("ACL_ENABLED" in p for p in problems)
    assert any("DB_PASSWORD" in p for p in problems)


def test_production_with_secure_config_is_clean():
    s = Settings(
        environment="production",
        acl_enabled=True,
        db_password="a-real-secret",
        minio_access_key="a-real-key",
        minio_secret_key="a-real-secret",
    )
    assert s.validate_production_security() == []


def test_empty_credentials_flagged_in_production():
    s = Settings(
        environment="production",
        acl_enabled=True,
        db_password="",
        minio_access_key="",
        minio_secret_key="",
    )
    problems = s.validate_production_security()
    assert len(problems) == 3  # three empty credentials
