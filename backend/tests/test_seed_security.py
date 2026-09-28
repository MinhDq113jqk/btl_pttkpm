"""Demo seed credential boundary tests; no database or secret output."""
import json
import secrets

import pytest

from app.core.config import Settings
from scripts.seed import DEMO_ACCOUNT_USERNAMES, load_demo_seed_credentials


def configured_seed_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "app_env": "test",
        "database_url": "postgresql://fixture@db.invalid/fixture?sslmode=require",
        "secret_key": secrets.token_urlsafe(32),
        "demo_seed_enabled": True,
        "demo_seed_credentials_json": json.dumps({
            username: secrets.token_urlsafe(24) for username in DEMO_ACCOUNT_USERNAMES
        }),
    }
    values.update(overrides)
    return Settings(**values)


def test_seed_requires_explicit_enablement():
    with pytest.raises(RuntimeError, match="disabled"):
        load_demo_seed_credentials(configured_seed_settings(demo_seed_enabled=False))


def test_seed_rejects_production():
    with pytest.raises(RuntimeError, match="development or test"):
        load_demo_seed_credentials(configured_seed_settings(
            app_env="production",
            database_url="postgresql://fixture@db.invalid/fixture?sslmode=verify-full",
            cors_origins=["https://app.example.invalid"],
        ))


def test_seed_rejects_missing_or_malformed_credential_map():
    with pytest.raises(RuntimeError, match="required"):
        load_demo_seed_credentials(configured_seed_settings(demo_seed_credentials_json=None))
    with pytest.raises(ValueError, match="valid JSON"):
        load_demo_seed_credentials(configured_seed_settings(demo_seed_credentials_json="not-json"))


def test_seed_requires_exact_unique_credential_map():
    duplicate = {username: "x" * 16 for username in DEMO_ACCOUNT_USERNAMES}
    with pytest.raises(ValueError, match="distinct"):
        load_demo_seed_credentials(configured_seed_settings(
            demo_seed_credentials_json=json.dumps(duplicate),
        ))
    incomplete = dict(list(duplicate.items())[:-1])
    with pytest.raises(ValueError, match="exactly"):
        load_demo_seed_credentials(configured_seed_settings(
            demo_seed_credentials_json=json.dumps(incomplete),
        ))


def test_seed_accepts_one_unique_external_credential_per_account():
    settings = configured_seed_settings()
    assert set(load_demo_seed_credentials(settings)) == set(DEMO_ACCOUNT_USERNAMES)
