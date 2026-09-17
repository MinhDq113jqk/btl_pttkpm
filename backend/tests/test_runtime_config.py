"""Pilot runtime configuration checks; no network or database writes."""

import secrets

import pytest

from app.core.config import Settings
from scripts.runtime_check import EXPECTED_SCHEMA_REVISION, validate_runtime


def make_settings(**overrides):
    values = {
        "_env_file": None,
        "app_env": "development",
        "database_url": "postgresql://fixture@db.invalid/fixture?sslmode=require",
        "database_ssl_root_cert": None,
        "secret_key": secrets.token_urlsafe(32),
        "cors_origins": ["http://127.0.0.1:3000"],
    }
    values.update(overrides)
    return Settings(**values)


def test_runtime_summary_is_redacted_and_targets_current_schema():
    summary = validate_runtime(make_settings())
    assert summary == {
        "status": "valid",
        "app_env": "development",
        "database": "configured",
        "database_sslmode": "require",
        "cors_origins_count": 1,
        "schema_revision_required": EXPECTED_SCHEMA_REVISION,
    }
    assert "secret_key" not in summary


@pytest.mark.parametrize("secret", [None, "", "short", "CHANGE_ME_generate_a_random_key_with_at_least_32_bytes"])
def test_runtime_rejects_missing_or_placeholder_secret(secret):
    settings = make_settings(secret_key=secret)
    with pytest.raises(ValueError, match="SECRET_KEY"):
        validate_runtime(settings)


def test_runtime_rejects_non_postgres_database():
    with pytest.raises(ValueError, match="PostgreSQL"):
        make_settings(database_url="sqlite:///pilot.db")


def test_runtime_rejects_database_url_placeholder():
    settings = make_settings(
        database_url="postgresql://pilot_user:CHANGE_ME@db.invalid/greencity?sslmode=require"
    )
    with pytest.raises(ValueError, match="placeholder"):
        validate_runtime(settings)
