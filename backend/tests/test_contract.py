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


PORTAL_METHODS = {
    '/api/v1/portal/operations/commercial-ledgers': {'get'},
    '/api/v1/portal/control/integrations/contract': {'get'},
    '/api/v1/portal/control/integrations/{identifier}/configure': {'post'},
    '/api/v1/portal/control/integrations/{identifier}/sources': {'post'},
    '/api/v1/portal/control/integrations/{identifier}/received': {'get'},
    '/api/v1/portal/control/integrations/{identifier}/readings': {'post'},
    '/api/v1/portal/control/integrations/{identifier}/bank-transactions': {'post'},
    '/api/v1/portal/control/integrations/{identifier}/parking-events': {'post'},
    '/api/v1/portal/control/deliveries/{identifier}/package': {'get'},
    '/api/v1/portal/assistant/options': {'get'},
    '/api/v1/portal/assistant/conversations': {'get'},
    '/api/v1/portal/assistant/support': {'post'},
    '/api/v1/portal/assistant/sources/{source}/{identifier}': {'get'},
    '/api/v1/portal/control/job-runs/{identifier}/actions': {'post'},
    '/api/v1/portal/completion-options': {'get'},
    '/api/v1/portal/content/{identifier}/revision': {'post'},
    '/api/v1/portal/content/{identifier}/chain': {'get'},
    '/api/v1/portal/content/{identifier}/minutes': {'post'},
    '/api/v1/portal/community-tasks': {'get'},
    '/api/v1/portal/community-tasks/{identifier}/actions': {'post'},
    '/api/v1/portal/sla-policies': {'post', 'get'},
    '/api/v1/portal/sla-policies/{identifier}/actions': {'post'},
    '/api/v1/portal/requests/{identifier}/control': {'post', 'get'},
    '/api/v1/portal/service-quality': {'get'},
    '/api/v1/portal/init-datasets': {'post', 'get'},
    '/api/v1/portal/init-datasets/{identifier}': {'get'},
    '/api/v1/portal/init-datasets/{identifier}/actions': {'post'},
    '/api/v1/portal/sources/{source}/{identifier}': {'get'},
    '/api/v1/portal/capabilities': {'get'},
    '/api/v1/portal/control/reports/{identifier}/sources/{source}/{source_id}': {'get'},
    '/api/v1/portal/account-profile': {'get', 'post'},
    '/api/v1/portal/account-profile/email/request': {'post'},
    '/api/v1/portal/account-profile/email/confirm': {'post'},
    '/api/v1/portal/control/permission-catalog': {'get'},
    '/api/v1/portal/control/access-reviews': {'get', 'post'},
    '/api/v1/portal/control/access-reviews/{identifier}/resolve': {'post'},
    '/api/v1/portal/control/parking-usage': {'get', 'post'},
    '/api/v1/portal/control/parking-reconciliations': {'get', 'post'},
    '/api/v1/portal/control/parking-reconciliations/{identifier}': {'get'},
    '/api/v1/portal/control/parking-discrepancies/{identifier}/resolve': {'post'},
    '/api/v1/portal/property/buildings': {'get'},
    '/api/v1/portal/operations/eligible-workers': {'get'},
    '/api/v1/portal/operations/meter-assignments': {'get', 'post'},
    '/api/v1/portal/operations/meter-assignments/{identifier}/actions': {'post'},
    '/api/v1/portal/operations/master-data': {'get'},
    '/api/v1/portal/operations/treasury/{identifier}/comparison': {'get'},
    '/api/v1/portal/operations/my-work': {'get'},
    '/api/v1/portal/operations/my-work/{identifier}/acknowledge': {'post'},
    '/api/v1/portal/operations/records/{identifier}/contract-progress': {'get'},
    '/api/v1/portal/operations/assets/{identifier}/summary': {'get'},
    '/api/v1/portal/control/access-cards': {'get', 'post'},
    '/api/v1/portal/control/access-cards/{identifier}/actions': {'post'},
    '/api/v1/portal/operations/records/{identifier}/progress': {'get'},
    '/api/v1/portal/operations/readings/{identifier}/billing': {'post'},
    '/api/v1/portal/control/accounts': {'get'},
    '/api/v1/portal/control/accounts/{identifier}/actions': {'post'},
    '/api/v1/portal/control/accounts/{identifier}/sessions': {'get'},
    '/api/v1/portal/control/card-blanks': {'get', 'post'},
    '/api/v1/portal/control/card-blanks/{identifier}/actions': {'post'},
    '/api/v1/portal/control/catalog': {'get'},
    '/api/v1/portal/control/content/{identifier}/responses': {'get', 'post'},
    '/api/v1/portal/control/credentials/{identifier}/scope': {'post'},
    '/api/v1/portal/control/deliveries': {'get'},
    '/api/v1/portal/control/deliveries/{identifier}/actions': {'post'},
    '/api/v1/portal/control/documents/bundle': {'post'},
    '/api/v1/portal/control/history/{parent_type}/{identifier}': {'get'},
    '/api/v1/portal/control/integrations': {'get', 'post'},
    '/api/v1/portal/control/integrations/{identifier}/queue': {'post'},
    '/api/v1/portal/control/invitations': {'get', 'post'},
    '/api/v1/portal/control/invitations/{identifier}/send': {'post'},
    '/api/v1/portal/control/job-runs': {'get'},
    '/api/v1/portal/control/jobs': {'get', 'post'},
    '/api/v1/portal/control/jobs/{identifier}/actions': {'post'},
    '/api/v1/portal/control/notification-deliveries': {'get'},
    '/api/v1/portal/control/notification-deliveries/{identifier}/actions': {'post'},
    '/api/v1/portal/control/notification-deliveries/{identifier}/send': {'post'},
    '/api/v1/portal/control/notifications/{identifier}/ack': {'post'},
    '/api/v1/portal/control/parking-slots': {'get', 'post'},
    '/api/v1/portal/control/parking-slots/{identifier}/actions': {'post'},
    '/api/v1/portal/control/preferences': {'get', 'post'},
    '/api/v1/portal/control/reports': {'get', 'post'},
    '/api/v1/portal/control/reports/{identifier}': {'get'},
    '/api/v1/portal/control/reports/{identifier}/download': {'get'},
    '/api/v1/portal/control/templates': {'get', 'post'},
    '/api/v1/portal/control/templates/{identifier}/send': {'post'},
    '/api/v1/portal/control/vehicles/{identifier}/change': {'post'},
    '/api/v1/portal/control/visitor-parking': {'get', 'post'},
    '/api/v1/portal/control/visitor-parking/{identifier}/actions': {'post'},
    '/api/v1/portal/invitations/{identifier}/accept': {'post'},
    '/api/v1/portal/operations/catalog': {'get'},
    '/api/v1/portal/operations/expenses': {'get', 'post'},
    '/api/v1/portal/operations/expenses/{identifier}/actions': {'post'},
    '/api/v1/portal/operations/meters': {'get', 'post'},
    '/api/v1/portal/operations/meters/{identifier}/reconciliation': {'get'},
    '/api/v1/portal/operations/options': {'get'},
    '/api/v1/portal/operations/readings': {'get', 'post'},
    '/api/v1/portal/operations/readings/{identifier}/actions': {'post'},
    '/api/v1/portal/operations/records': {'get', 'post'},
    '/api/v1/portal/operations/records/{identifier}/actions': {'post'},
    '/api/v1/portal/operations/resident-records': {'get'},
    '/api/v1/portal/operations/resident-records/{identifier}/actions': {'post'},
    '/api/v1/portal/operations/stock': {'get', 'post'},
    '/api/v1/portal/operations/stock-movements': {'get', 'post'},
    '/api/v1/portal/operations/stock-movements/{identifier}/actions': {'post'},
    '/api/v1/portal/operations/treasury': {'get', 'post'},
    '/api/v1/portal/operations/treasury-movements': {'get'},
    '/api/v1/portal/operations/treasury/{identifier}/actions': {'post'},
    '/api/v1/portal/operations/treasury/{identifier}/reconciliation': {'get'},
    '/api/v1/portal/property/persons': {'post', 'get'},
    '/api/v1/portal/property/duplicates': {'get'},
    '/api/v1/portal/property/units/{unit_id}/history': {'get'},
    '/api/v1/portal/property/leases': {'get'},
    '/api/v1/portal/property/nodes': {'post', 'get'},
    '/api/v1/portal/property/nodes/{identifier}/actions': {'post'},
    '/api/v1/portal/property/units': {'post'},
    '/api/v1/portal/finance/reviews': {'get'},
    '/api/v1/portal/finance/commands': {'post', 'get'},
    '/api/v1/portal/finance/{resource}/{identifier}/history': {'get'},
    '/api/v1/portal/finance/reviews/{identifier}/actions': {'post'},
    '/api/v1/portal/finance/options': {'get'},
    '/api/v1/portal/finance/commands/preview': {'post'},
    '/api/v1/portal/finance/commands/{identifier}/actions': {'post'},
    '/api/v1/portal/finance/ar': {'post', 'get'},
    '/api/v1/portal/finance/ar/{identifier}/actions': {'post'},
    '/api/v1/portal/finance/policies': {'post', 'get'},
    '/api/v1/portal/finance/policies/{identifier}/actions': {'post'},
    '/api/v1/portal/finance/delegations': {'post', 'get'},
    '/api/v1/portal/finance/delegations/{identifier}/actions': {'post'},
    '/api/v1/portal/finance/periods/{identifier}/delta': {'get'},

    '/api/v1/auth/recovery/request': {'post'},
    '/api/v1/auth/recovery/complete': {'post'},
    '/api/v1/portal/jobs/tick': {'post'},
    '/api/v1/portal/options': {'get'},
    '/api/v1/portal/profile': {'get'},
    '/api/v1/portal/dossiers': {'get', 'post'},
    '/api/v1/portal/dossiers/{identifier}': {'get'},
    '/api/v1/portal/dossiers/{identifier}/actions': {'post'},
    '/api/v1/portal/dossiers/{identifier}/deposit': {'post'},
    '/api/v1/portal/resources': {'get', 'post'},
    '/api/v1/portal/resources/{identifier}/actions': {'post'},
    '/api/v1/portal/resources/{identifier}/availability': {'get'},
    '/api/v1/portal/resources/{identifier}/closures': {'get', 'post'},
    '/api/v1/portal/closures/{identifier}/actions': {'post'},
    '/api/v1/portal/deposits': {'get'},
    '/api/v1/portal/deposits/{identifier}/actions': {'post'},
    '/api/v1/portal/requests/{identifier}/messages': {'get', 'post'},
    '/api/v1/portal/vehicles': {'get', 'post'},
    '/api/v1/portal/vehicles/{identifier}/actions': {'post'},
    '/api/v1/portal/vehicles/{identifier}/credential': {'post'},
    '/api/v1/portal/credentials': {'get'},
    '/api/v1/portal/credentials/{identifier}/actions': {'post'},
    '/api/v1/portal/bookings': {'get', 'post'},
    '/api/v1/portal/bookings/{identifier}/actions': {'post'},
    '/api/v1/portal/enrollments': {'get', 'post'},
    '/api/v1/portal/enrollments/{identifier}/actions': {'post'},
    '/api/v1/portal/fee-sources': {'get'},
    '/api/v1/portal/fee-sources/{identifier}/preview': {'get'},
    '/api/v1/portal/fee-sources/{identifier}/post': {'post'},
    '/api/v1/portal/invoices': {'get'},
    '/api/v1/portal/payment-intents': {'get', 'post'},
    '/api/v1/portal/payment-intents/{identifier}/query': {'post'},
    '/api/v1/portal/payment-intents/{identifier}/reconcile': {'post'},
    '/api/v1/portal/payments/vnpay/ipn': {'get'},
    '/api/v1/portal/payments/vnpay/return': {'get'},
    '/api/v1/portal/adjustments': {'get', 'post'},
    '/api/v1/portal/adjustments/{identifier}/actions': {'post'},
    '/api/v1/portal/adjustments/{identifier}/provider': {'post'},
    '/api/v1/portal/documents': {'get', 'post'},
    '/api/v1/portal/documents/{identifier}/signed-link': {'get'},
    '/api/v1/portal/documents/{identifier}/download': {'get'},
    '/api/v1/portal/documents/{identifier}/actions': {'post'},
    '/api/v1/portal/content': {'get', 'post'},
    '/api/v1/portal/content/{identifier}/actions': {'post'},
    '/api/v1/portal/recovery-requests': {'get'},
    '/api/v1/portal/recovery-requests/{identifier}/verify': {'post'},
}


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
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
        "/api/v1/auth/change-password",
        "/api/v1/assistant/chat",
        "/api/v1/billing/accounts",
        "/api/v1/billing/accounts/{billing_account_id}",
        "/api/v1/billing/fee-policies",
        "/api/v1/billing/fee-policies/{fee_policy_id}/versions",
        "/api/v1/billing/fee-policies/{fee_policy_id}/versions/{version_id}/edit",
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
        "/api/v1/maintenance/assigned-work-orders",
        "/api/v1/maintenance/assets",
        "/api/v1/maintenance/assets/{asset_id}/plans",
        "/api/v1/maintenance/buildings",
        "/api/v1/maintenance/occurrences",
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
        "/api/v1/service-requests/{request_id}/assignees",
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
        "/api/v1/units/export",
        "/api/v1/units/{unit_id}/360",
        "/api/v1/work-orders/{work_order_id}",
        "/api/v1/work-orders/{work_order_id}/accept",
        "/api/v1/work-orders/{work_order_id}/assign",
        "/api/v1/work-orders/{work_order_id}/cancel",
        "/api/v1/work-orders/{work_order_id}/checklist/{item_id}",
        "/api/v1/work-orders/{work_order_id}/close",
        "/api/v1/work-orders/{work_order_id}/cost-lines",
        "/api/v1/work-orders/{work_order_id}/evidence",
        "/api/v1/work-orders/{work_order_id}/assignees",
        "/api/v1/work-orders/{work_order_id}/reopen",
        "/api/v1/work-orders/{work_order_id}/start",
        "/api/v1/work-orders/{work_order_id}/submit",
    }
    paths = app.openapi()["paths"]
    assert set(paths) == expected | set(PORTAL_METHODS)
    for path, methods in PORTAL_METHODS.items():
        assert set(paths[path]) == methods
    assert set(paths['/api/v1/billing/fee-policies/{fee_policy_id}/versions/{version_id}/edit']) == {'post'}


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
    database.current_revision.return_value = "0026"
    response = http.get("/api/v1/readiness")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready", "database": "connected", "schema_revision": "0026",
    }
    database.current_revision.return_value = "0019"
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
