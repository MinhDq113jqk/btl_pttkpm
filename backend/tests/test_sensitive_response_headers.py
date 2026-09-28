from datetime import UTC, datetime
import secrets
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql://fixture@db.invalid/fixture",
        secret_key=secrets.token_urlsafe(32),
    )


def _assert_private_headers(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_auth_responses_are_private_and_uncacheable_but_health_is_unchanged():
    database = MagicMock(spec=Database)
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    session.scalar.side_effect = [datetime.now(UTC), None, None, 0]
    database.get_session.return_value.__enter__.return_value = session
    app = create_app(_settings(), database)

    with TestClient(app) as client:
        invalid_username = client.post("/api/v1/auth/login", json={"username": "bad\u0000name", "password": "wrong"})
        login = client.post("/api/v1/auth/login", json={"username": "missing", "password": "wrong"})
        me = client.get("/api/v1/auth/me")
        health = client.get("/api/v1/health")

    assert invalid_username.status_code == 422
    assert invalid_username.json()["error"]["code"] == "ERR-VALIDATION"
    assert "bad" not in invalid_username.text
    _assert_private_headers(invalid_username)
    assert login.status_code == 401
    _assert_private_headers(login)
    assert me.status_code == 401
    _assert_private_headers(me)
    assert health.status_code == 200
    assert "cache-control" not in health.headers


def test_unhandled_sensitive_route_error_keeps_private_headers_and_safe_error_contract():
    app = create_app(_settings(), MagicMock(spec=Database))

    def fail_unexpectedly():
        raise RuntimeError("private server detail")

    app.add_api_route("/api/v1/assistant/unhandled-test", fail_unexpectedly, methods=["GET"])
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/assistant/unhandled-test")

    assert response.status_code == 500
    assert "private server detail" not in response.text
    _assert_private_headers(response)
