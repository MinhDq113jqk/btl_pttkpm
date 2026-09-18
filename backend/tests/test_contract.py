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
        "/api/v1/assets",
        "/api/v1/assets/{asset_id}",
        "/api/v1/assets/{asset_id}/maintenance-history",
        "/api/v1/attachments/{attachment_id}/content",
        "/api/v1/attachments/{attachment_id}/signed-link",
        "/api/v1/health",
        "/api/v1/readiness",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/auth/switch-site",
        "/api/v1/assistant/chat",
        "/api/v1/billing/accounts",
        "/api/v1/billing/accounts/{billing_account_id}",
        "/api/v1/billing/fee-policies",
        "/api/v1/billing/fee-policies/{fee_policy_id}/versions",
        "/api/v1/billing/invoices",
        "/api/v1/billing/invoices/{billing_invoice_id}",
        "/api/v1/billing/invoices/{billing_invoice_id}/void",
        "/api/v1/billing/payments",
        "/api/v1/billing/payments/{payment_id}/allocate",
        "/api/v1/billing/periods",
        "/api/v1/billing/periods/{accounting_period_id}/transition",
        "/api/v1/billing/runs",
        "/api/v1/billing/runs/{billing_run_id}/retry",
        "/api/v1/billing/unmatched-payments",
        "/api/v1/billing/unmatched-payments/{unmatched_payment_id}/match",
        "/api/v1/billing/overpayment-credits",
        "/api/v1/cleaning/assignees",
        "/api/v1/cleaning/routes",
        "/api/v1/cleaning/shifts",
        "/api/v1/cleaning/tasks",
        "/api/v1/cleaning/tasks/{task_id}",
        "/api/v1/cleaning/tasks/{task_id}/accept",
        "/api/v1/cleaning/tasks/{task_id}/assign",
        "/api/v1/cleaning/tasks/{task_id}/cancel",
        "/api/v1/cleaning/tasks/{task_id}/checklist/{item_id}",
        "/api/v1/cleaning/tasks/{task_id}/missed",
        "/api/v1/cleaning/tasks/{task_id}/start",
        "/api/v1/cleaning/tasks/{task_id}/submit",
        "/api/v1/import-runs",
        "/api/v1/import-runs/template",
        "/api/v1/import-runs/{run_id}",
        "/api/v1/import-runs/{run_id}/apply",
        "/api/v1/import-runs/{run_id}/error-file",
        "/api/v1/import-runs/{run_id}/error-file/signed-link",
        "/api/v1/import-runs/{run_id}/preview",
        "/api/v1/import-runs/{run_id}/rows",
        "/api/v1/maintenance-occurrences/{occurrence_id}/defer",
        "/api/v1/maintenance-plans",
        "/api/v1/maintenance-plans/{plan_id}",
        "/api/v1/maintenance/scheduler/run",
        "/api/v1/audit-events",
        "/api/v1/dashboard",
        "/api/v1/dashboard/drill-down/{metric}",
        "/api/v1/notifications",
        "/api/v1/notifications/{notification_id}/read",
        "/api/v1/outbox/events",
        "/api/v1/outbox/events/{event_id}/retry",
        "/api/v1/parcels",
        "/api/v1/parcels/{parcel_id}",
        "/api/v1/parcels/{parcel_id}/case",
        "/api/v1/parcels/{parcel_id}/incident",
        "/api/v1/parcels/{parcel_id}/incident-link",
        "/api/v1/parcels/{parcel_id}/timeline",
        "/api/v1/parcels/{parcel_id}/evidence",
        "/api/v1/parcels/{parcel_id}/evidence/{attachment_id}/signed-link",
        "/api/v1/parcels/{parcel_id}/evidence/{attachment_id}/content",
        "/api/v1/parcels/{parcel_id}/ready",
        "/api/v1/parcels/{parcel_id}/handover",
        "/api/v1/parcels/{parcel_id}/exception",
        "/api/v1/pending-charges/{charge_id}/decision",
        "/api/v1/pending-charges/{charge_id}/post",
         "/api/v1/persons/{person_id}/units",
         "/api/v1/resident/service-requests",
         "/api/v1/resident/service-request-options",
         "/api/v1/resident/service-requests/{request_id}",
         "/api/v1/resident/service-requests/{request_id}/evidence",
         "/api/v1/resident/service-requests/{request_id}/evidence/{attachment_id}/content",
         "/api/v1/resident/service-requests/{request_id}/evidence/{attachment_id}/signed-link",
         "/api/v1/resident/service-requests/{request_id}/timeline",
         "/api/v1/resident/billing/summary",
         "/api/v1/resident/billing/invoices",
         "/api/v1/resident/billing/payments",
         "/api/v1/resident/notifications",
         "/api/v1/resident/notifications/{notification_id}/read",
         "/api/v1/service-request-form-options",
        "/api/v1/service-requests",
        "/api/v1/service-requests/sla/run",
        "/api/v1/service-requests/{request_id}",
        "/api/v1/service-requests/{request_id}/close",
        "/api/v1/service-requests/{request_id}/triage",
        "/api/v1/service-requests/{request_id}/work-orders",
        "/api/v1/security/assignees",
        "/api/v1/security/dashboard",
        "/api/v1/security/incidents",
        "/api/v1/security/incidents/{incident_id}/escalations/{escalation_id}/acknowledgements",
        "/api/v1/security/incidents/{incident_id}/evidence",
        "/api/v1/security/incidents/{incident_id}/transition",
        "/api/v1/security/patrol-points",
        "/api/v1/security/patrol-windows/{window_id}/complete",
        "/api/v1/security/patrol-windows/{window_id}/logs",
        "/api/v1/security/patrol-windows/{window_id}/missed",
        "/api/v1/security/shifts",
        "/api/v1/security/shifts/{shift_id}",
        "/api/v1/security/shifts/{shift_id}/handoffs",
        "/api/v1/security/shifts/{shift_id}/start",
        "/api/v1/security/shifts/{shift_id}/visitors",
        "/api/v1/units/import",
        "/api/v1/units/{unit_id}/360",
        "/api/v1/work-orders/{work_order_id}",
        "/api/v1/work-orders/{work_order_id}/accept",
        "/api/v1/work-orders/{work_order_id}/assign",
        "/api/v1/work-orders/{work_order_id}/cancel",
        "/api/v1/work-orders/{work_order_id}/checklist/{item_id}",
        "/api/v1/work-orders/{work_order_id}/close",
        "/api/v1/work-orders/{work_order_id}/cost-lines",
        "/api/v1/work-orders/{work_order_id}/evidence",
        "/api/v1/work-orders/{work_order_id}/reopen",
        "/api/v1/work-orders/{work_order_id}/start",
        "/api/v1/work-orders/{work_order_id}/submit",
    }
    assert set(app.openapi()["paths"]) == expected


def test_r6_resident_openapi_surface_has_only_intended_methods(contract_client):
    """Release contract: resident endpoints do not grow unreviewed write methods."""
    http, _ = contract_client
    paths = http.get("/openapi.json").json()["paths"]
    expected_methods = {
        "/api/v1/resident/service-requests": {"get", "post"},
        "/api/v1/resident/service-request-options": {"get"},
        "/api/v1/resident/service-requests/{request_id}": {"get", "patch"},
        "/api/v1/resident/service-requests/{request_id}/timeline": {"get"},
        "/api/v1/resident/service-requests/{request_id}/evidence": {"get", "post"},
        "/api/v1/resident/service-requests/{request_id}/evidence/{attachment_id}/content": {"get"},
        "/api/v1/resident/service-requests/{request_id}/evidence/{attachment_id}/signed-link": {"get"},
        "/api/v1/resident/billing/summary": {"get"},
        "/api/v1/resident/billing/invoices": {"get"},
        "/api/v1/resident/billing/payments": {"get"},
        "/api/v1/resident/notifications": {"get"},
        "/api/v1/resident/notifications/{notification_id}/read": {"post"},
    }
    for path, methods in expected_methods.items():
        assert set(paths[path]) == methods


def test_readiness_requires_exact_schema_head(contract_client):
    http, database = contract_client
    database.current_revision.return_value = "0015"
    response = http.get("/api/v1/readiness")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready", "database": "connected", "schema_revision": "0015",
    }
    database.current_revision.return_value = "0005"
    response = http.get("/api/v1/readiness")
    assert response.status_code == 503
    assert_error(response, "ERR-DATABASE-NOT-READY")


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 409, 422, 500, 503])
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
