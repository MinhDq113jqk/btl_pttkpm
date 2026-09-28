from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.api import auth
from app.core.config import Settings
from app.models.login_throttle import LoginThrottle
from app.services.login_throttle import (
    load_active_throttle,
    login_identity_key,
    record_login_failure,
)


def test_login_verifies_exactly_one_matching_account_hash(monkeypatch):
    calls = []
    account = SimpleNamespace(hashed_password="account-hash")
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: calls.append((password, hashed)) or True)

    assert auth._verified_login_account([account], "candidate") is account
    assert calls == [("candidate", "account-hash")]


def test_unknown_or_ambiguous_login_still_runs_one_dummy_password_check(monkeypatch):
    calls = []
    accounts = [SimpleNamespace(hashed_password="first"), SimpleNamespace(hashed_password="second")]
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: calls.append((password, hashed)) or False)

    assert auth._verified_login_account([], "candidate") is None
    assert auth._verified_login_account(accounts, "candidate") is None
    assert len(calls) == 2
    assert all(password == "candidate" for password, _ in calls)
    assert all(hashed == auth._DUMMY_LOGIN_PASSWORD_HASH for _, hashed in calls)
    assert all(hashed not in {"first", "second"} for _, hashed in calls)


def test_login_throttle_key_is_domain_separated_opaque_and_stable():
    key = login_identity_key("unknown.user", "server-secret")

    assert len(key) == 64
    assert key == login_identity_key("unknown.user", "server-secret")
    assert key != login_identity_key("unknown.user", "other-secret")
    assert "unknown.user" not in key


def test_login_failure_backoff_doubles_and_caps_at_configured_maximum():
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql://fixture@db.invalid/fixture",
        secret_key="test-secret-with-more-than-32-bytes-0123456789",
        login_throttle_failure_threshold=2,
        login_throttle_base_backoff_seconds=60,
        login_throttle_max_backoff_seconds=120,
    )
    session = MagicMock()
    now = datetime(2026, 9, 23, tzinfo=UTC)
    state = None
    for attempt in range(1, 6):
        if state is not None:
            state.locked_until = now
        state = record_login_failure(session, "a" * 64, state, now, settings)
        if attempt == 1:
            assert state.locked_until is None
        else:
            assert state.locked_until == now + timedelta(
                seconds=min(60 * 2 ** (attempt - settings.login_throttle_failure_threshold), 120),
            )
    assert state.failure_count == 5


def test_reset_window_cannot_clear_an_unexpired_cooldown():
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql://fixture@db.invalid/fixture",
        secret_key="test-secret-with-more-than-32-bytes-0123456789",
    )
    now = datetime(2026, 9, 23, tzinfo=UTC)
    state = LoginThrottle(
        identity_key="a" * 64,
        failure_count=settings.login_throttle_failure_threshold,
        last_failure_at=now - timedelta(days=2),
        locked_until=now + timedelta(minutes=1),
    )
    session = MagicMock()
    session.scalar.return_value = state

    assert load_active_throttle(session, state.identity_key, now, settings) is state
    session.delete.assert_not_called()


def test_reset_window_must_cover_the_maximum_cooldown():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            database_url="postgresql://fixture@db.invalid/fixture",
            secret_key="test-secret-with-more-than-32-bytes-0123456789",
            login_throttle_reset_seconds=600,
            login_throttle_max_backoff_seconds=1800,
        )
