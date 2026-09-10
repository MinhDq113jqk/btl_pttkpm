import logging
import secrets
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.models import Tenant

FAKE_URL = "postgres://test_user:fake-secret@db.invalid:5432/testdb?sslmode=require"


def settings(**kwargs):
    # Unit config tests must not inherit the integration cluster's CA override.
    kwargs.setdefault("database_ssl_root_cert", None)
    return Settings(_env_file=None, database_url=FAKE_URL, secret_key=secrets.token_urlsafe(32), **kwargs)


def test_uri_normalization_keeps_original_secret():
    config = settings()
    assert config.sqlalchemy_url().drivername == "postgresql+psycopg"
    assert config.sqlalchemy_url().query["sslmode"] == "require"
    assert config.database_url.get_secret_value() == FAKE_URL
    assert "fake-secret" not in repr(config)


@pytest.mark.parametrize("mode", ["disable", "prefer", "allow"])
def test_insecure_tls_rejected(mode):
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, database_url=FAKE_URL.replace("require", mode))
    assert "fake-secret" not in str(exc.value)


@pytest.mark.parametrize("uri", ["sqlite://", "not-a-url", "postgresql://"])
def test_invalid_database_url_rejected(uri):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=uri)


def test_production_requires_verified_tls():
    with pytest.raises(ValidationError):
        settings(app_env="production", cors_origins=["https://app.example"])


def test_ca_enables_verify_full():
    config = settings(database_ssl_root_cert="C:/private/ca.pem")
    assert config.sqlalchemy_url().query["sslmode"] == "verify-full"


def test_wildcard_cors_rejected():
    with pytest.raises(ValidationError):
        settings(cors_origins=["*"])


def test_connection_pool_config():
    db = Database(settings())
    try:
        assert db.engine.pool.size() == 5
        assert db.engine.pool._max_overflow == 10
        assert db.engine.pool._pre_ping is True
        assert db.engine.hide_parameters is True
    finally:
        db.close()


@pytest.fixture
def client():
    db = Mock(spec=Database)
    app = create_app(settings(), db)
    with TestClient(app) as instance:
        yield instance, db


def test_health_checks_database(client):
    http, db = client
    response = http.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
    UUID(response.headers["x-correlation-id"])
    db.ping.assert_called_once()


def test_correlation_id_preserved(client):
    http, _ = client
    expected = str(uuid4())
    response = http.get("/health", headers={"X-Correlation-ID": expected})
    assert response.headers["x-correlation-id"] == expected


def test_untrusted_correlation_replaced(client):
    http, _ = client
    response = http.get("/health", headers={"X-Correlation-ID": "fake-secret"})
    UUID(response.headers["x-correlation-id"])


def test_database_failure_is_safe_503_and_recovers(client, caplog):
    http, db = client
    db.ping.side_effect = OperationalError("secret-sql", {}, Exception(FAKE_URL))
    with caplog.at_level(logging.INFO, logger="greencity"):
        response = http.get("/health?password=fake-secret")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ERR-DATABASE-UNAVAILABLE"
    assert response.json()["error"]["correlation_id"] == response.headers["x-correlation-id"]
    assert "fake-secret" not in response.text + caplog.text
    assert "processing_time_ms=" in caplog.text
    db.ping.side_effect = None
    assert http.get("/health").status_code == 200


def test_unexpected_error_is_safe_500(client, caplog):
    http, db = client
    db.ping.side_effect = RuntimeError(FAKE_URL)
    response = http.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "ERR-INTERNAL"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "fake-secret" not in response.text + caplog.text


def test_notfound_uses_envelope_without_path_leak(client, caplog):
    http, _ = client
    with caplog.at_level(logging.INFO, logger="greencity"):
        response = http.get("/fake-secret")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ERR-NOTFOUND"
    assert "fake-secret" not in response.text + caplog.text


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://localhost:3000"])
def test_cors_allowed(client, origin):
    http, _ = client
    response = http.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_denies_unknown_origin(client):
    http, _ = client
    response = http.options("/health", headers={"Origin": "https://untrusted.invalid", "Access-Control-Request-Method": "GET"})
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_documentation(client, path):
    http, _ = client
    assert http.get(path).status_code == 200


def test_validation_does_not_echo_body():
    class Payload(BaseModel):
        count: int
    app = create_app(settings(), Mock(spec=Database))
    @app.post("/test-validation")
    def validate(payload: Payload):
        return payload
    with TestClient(app) as http:
        response = http.post("/test-validation", json={"count": "fake-secret"})
    assert response.status_code == 422
    assert "fake-secret" not in response.text


def test_base_ddl_uses_uuid_and_timestamptz():
    ddl = str(CreateTable(Tenant.__table__).compile(dialect=postgresql.dialect()))
    assert "greencity.tenants" in ddl
    assert "UUID" in ddl
    assert ddl.count("TIMESTAMP WITH TIME ZONE") == 2
    assert "name_not_blank" in ddl
