"""Foundation contract tests, not authentication or business-scope acceptance."""
import logging
import secrets
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.database import Database
from app.core.exceptions import AppError
from app.main import create_app
from app.schemas.errors import ErrorEnvelope


class Payload(BaseModel):
    count: int


@pytest.fixture
def contract_client():
    config = Settings(_env_file=None, app_env="test",
                      database_url="postgresql://fixture@db.invalid/fixture", secret_key=secrets.token_urlsafe(32))
    database = Mock(spec=Database)
    app = create_app(config, database)

    # Test-only probes exercise shared handlers; these are NOT production routes.
    @app.post("/api/v1/contract-probe")
    def probe(payload: Payload):
        return payload

    @app.get("/api/v1/error-probe/{status}")
    def error_probe(status: int):
        if status == 404:
            raise AppError("ERR-SCOPE-NOTFOUND", "Không tìm thấy dữ liệu.", 404)
        raise HTTPException(status, detail="private-marker", headers={
            "WWW-Authenticate": "Bearer",
        } if status == 401 else None)

    with TestClient(app) as http:
        yield http, database


def assert_error(response, code):
    body = response.json()
    ErrorEnvelope.model_validate(body)
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "correlation_id"}
    assert body["error"]["code"] == code
    assert body["error"]["correlation_id"] == response.headers["x-correlation-id"]
    UUID(body["error"]["correlation_id"])
    assert "private-marker" not in response.text


def test_versioned_health_and_legacy_alias(contract_client):
    http, database = contract_client
    for path in ("/api/v1/health", "/health"):
        response = http.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "connected"}
        UUID(response.headers["x-correlation-id"])
    assert database.ping.call_count == 2


def test_production_openapi_only_publishes_versioned_health(contract_client):
    http, _ = contract_client
    paths = http.get("/openapi.json").json()["paths"]
    assert "/api/v1/health" in paths
    assert "/health" not in paths


def test_production_app_has_no_test_probes():
    config = Settings(_env_file=None, app_env="test",
                      database_url="postgresql://fixture@db.invalid/fixture", secret_key=secrets.token_urlsafe(32))
    app = create_app(config, Mock(spec=Database))
    expected = {
        "/api/v1/health",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/auth/switch-site",
        "/api/v1/units/{unit_id}/360",
    }
    assert set(app.openapi()["paths"]) == expected


@pytest.mark.parametrize("status", [401, 403, 404, 405, 409, 422, 500, 503])
def test_openapi_errors_use_shared_dto(contract_client, status):
    http, _ = contract_client
    spec = http.get("/openapi.json").json()
    # Includes a DTO route: default FastAPI HTTPValidationError must not reappear.
    for path, method in (("/api/v1/health", "get"), ("/api/v1/contract-probe", "post")):
        response = spec["paths"][path][method]["responses"][str(status)]
        assert response["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorEnvelope",
        }
        assert response["headers"]["X-Correlation-ID"]["schema"]["format"] == "uuid"
    assert "HTTPValidationError" not in spec["components"]["schemas"]


def test_validation_matches_documented_envelope(contract_client):
    http, _ = contract_client
    response = http.post("/api/v1/contract-probe", json={"count": "private-marker"})
    assert response.status_code == 422
    assert_error(response, "ERR-VALIDATION")


def test_malformed_json_uses_validation_envelope(contract_client):
    http, _ = contract_client
    response = http.post("/api/v1/contract-probe", content='{"private-marker":',
                         headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert_error(response, "ERR-VALIDATION")


@pytest.mark.parametrize("status,code", [(401, "ERR-UNAUTHORIZED"),
                                        (403, "ERR-FORBIDDEN"),
                                        (404, "ERR-SCOPE-NOTFOUND")])
def test_error_handlers_preserve_contract_and_auth_challenge(contract_client, status, code):
    http, _ = contract_client
    response = http.get(f"/api/v1/error-probe/{status}")
    assert response.status_code == status
    assert_error(response, code)
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"


def test_unknown_resource_does_not_echo_path_or_query(contract_client, caplog):
    http, _ = contract_client
    with caplog.at_level(logging.INFO, logger="greencity"):
        response = http.get("/api/v1/private-marker?token=private-marker")
    assert response.status_code == 404
    assert_error(response, "ERR-NOTFOUND")
    assert "private-marker" not in caplog.text


def test_method_not_allowed_keeps_allow_header(contract_client):
    http, _ = contract_client
    response = http.post("/api/v1/health")
    assert response.status_code == 405
    assert_error(response, "ERR-HTTP")
    assert "GET" in response.headers["allow"]


@pytest.mark.parametrize("failure,status,code", [
    (OperationalError("private-marker", {}, Exception("private-marker")),
     503, "ERR-DATABASE-UNAVAILABLE"),
    (RuntimeError("private-marker"), 500, "ERR-INTERNAL"),
])
def test_versioned_failures_preserve_correlation_and_redact(contract_client, caplog,
                                                          failure, status, code):
    http, database = contract_client
    database.ping.side_effect = failure
    correlation = str(uuid4())
    response = http.get("/api/v1/health", headers={"X-Correlation-ID": correlation})
    assert response.status_code == status
    assert_error(response, code)
    assert response.headers["x-correlation-id"] == correlation
    assert "private-marker" not in caplog.text
