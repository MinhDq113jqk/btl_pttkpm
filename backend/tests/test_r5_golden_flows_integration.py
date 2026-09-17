"""R5 AC-45 five Golden Flows through the public HTTP API only.

The disposable runner owns migration and idempotent seed.  This test never
inserts, updates, or deletes domain data directly: API calls are the only
business mutations.  The small SQL checks at the end are read-only oracles for
the financial invariants that have no public write path.
"""
from datetime import UTC, datetime, timedelta
import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, or_, select

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.models.billing import ArLedgerEntry
from app.models.service import InvoiceItem, PendingCharge


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R5 Golden Flows require its disposable PostgreSQL cluster",
)]

DEMO_PASSWORD = "Password@123"
PNG = b"\x89PNG\r\n\x1a\nR5 evidence\x00\x00\x00\x00IEND\xaeB\x60\x82"


@pytest.fixture(scope="module")
def seeded_api_case():
    """Use only the runner's migrated, repeatable demo seed as prerequisite."""
    settings = Settings()
    assert settings.app_env == "test"
    assert settings.sqlalchemy_url().host == "127.0.0.1"
    database = Database(settings)
    app = create_app(settings, database)
    usernames = {
        "cskh": "cskh_west",
        "cskh_east": "cskh_east",
        "lead": "techlead_west",
        "tech": "technician_west",
        "cleaner": "cleaning_west",
        "security": "security_west",
        "accountant": "accountant_west",
        "director": "director_west",
    }
    with TestClient(app) as client:
        auth, identities = {}, {}
        for actor, username in usernames.items():
            response = client.post("/api/v1/auth/login", json={
                "username": username, "password": DEMO_PASSWORD,
            })
            assert response.status_code == 200, response.text
            payload = response.json()
            auth[actor] = {"Authorization": f"Bearer {payload['access_token']}"}
            identities[actor] = payload["user"]["account_id"]
        yield {"client": client, "database": database, "auth": auth, "identities": identities}
    database.close()


def _headers(case, actor, *, key=None, correlation=None, extra=None):
    headers = dict(case["auth"][actor])
    if key:
        headers["Idempotency-Key"] = key
    if correlation:
        headers["X-Correlation-ID"] = str(correlation)
    if extra:
        headers.update(extra)
    return headers


def _call(case, method, path, actor, *, status=200, body=None, key=None, correlation=None, extra=None, content=None):
    response = case["client"].request(
        method,
        path,
        headers=_headers(case, actor, key=key, correlation=correlation, extra=extra),
        json=body,
        content=content,
    )
    assert response.status_code == status, response.text
    return response.json()


def _work_order(case, work_order_id, actor="lead"):
    return _call(case, "GET", f"/api/v1/work-orders/{work_order_id}", actor)


def _audit_types(case, correlation):
    payload = _call(case, "GET", f"/api/v1/audit-events?correlation_id={correlation}", "director")
    return {item["event_type"] for item in payload["items"]}


def _form_options(case):
    initial = _call(case, "GET", "/api/v1/service-request-form-options", "cskh")
    building_id = initial["buildings"][0]["id"]
    return _call(case, "GET", f"/api/v1/service-request-form-options?building_id={building_id}", "cskh")


def _flow_customer_to_cash(case, token):
    options = _form_options(case)
    building = options["buildings"][0]
    category = next(item for item in options["categories"] if item["building_id"] in {None, building["id"]})
    unit = next(item for item in options["units"] if item["building_id"] == building["id"])
    request_body = {
        "category_id": category["id"], "building_id": building["id"], "unit_id": unit["id"],
        "title": "R5 mất điện hành lang", "description": "Đèn hành lang cần kỹ thuật xử lý.",
        "priority": "HIGH",
    }
    created = _call(case, "POST", "/api/v1/service-requests", "cskh", status=201,
                    body=request_body, key="r5-flow-sr-create", correlation=token)
    replayed = _call(case, "POST", "/api/v1/service-requests", "cskh", status=201,
                     body=request_body, key="r5-flow-sr-create", correlation=token)
    assert replayed == created

    triaged = _call(case, "POST", f"/api/v1/service-requests/{created['id']}/triage", "cskh",
                    body={"expected_version": created["version"], "owner_account_id": case["identities"]["lead"], "priority": "HIGH"},
                    correlation=token)
    work_order = _call(case, "POST", f"/api/v1/service-requests/{triaged['id']}/work-orders", "lead", status=201,
                       body={"title": "Sửa đèn hành lang", "description": "Kiểm tra và thay đèn.",
                             "checklist": [{"label": "Đèn đã hoạt động", "required": True}]},
                       key="r5-flow-sr-work-order", correlation=token)
    work_order = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/assign", "lead",
                       body={"assignee_id": case["identities"]["tech"], "expected_version": work_order["version"]},
                       correlation=token)
    work_order = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/start", "tech",
                       body={"expected_version": work_order["version"]}, correlation=token)
    evidence = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/evidence", "tech", status=201,
                     key="r5-flow-sr-evidence", correlation=token,
                     extra={"Content-Type": "image/png", "X-File-Name": "r5-evidence.png"}, content=PNG)
    checklist = work_order["checklist"][0]
    _call(case, "PATCH", f"/api/v1/work-orders/{work_order['id']}/checklist/{checklist['id']}", "tech",
          body={"expected_version": checklist["version"], "is_completed": True, "result": "Đèn sáng ổn định"},
          correlation=token)
    work_order = _work_order(case, work_order["id"], "tech")
    charge = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/cost-lines", "tech", status=201,
                   body={"description": "Vật tư thay đèn", "amount_vnd": 45_000, "cost_bearer": "RESIDENT",
                         "evidence_attachment_id": evidence["id"]},
                   key="r5-flow-sr-charge", correlation=token)
    decided = _call(case, "POST", f"/api/v1/pending-charges/{charge['pending_charge_id']}/decision", "accountant",
                    body={"expected_version": 1, "decision": "APPROVE"}, correlation=token)
    assert decided["status"] == "APPROVED"

    work_order = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/submit", "tech",
                       body={"expected_version": work_order["version"], "result_summary": "Đèn đã thay và kiểm tra."},
                       correlation=token)
    work_order = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/accept", "lead",
                       body={"expected_version": work_order["version"], "mode": "TECHNICAL"}, correlation=token)
    work_order = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/close", "lead",
                       body={"expected_version": work_order["version"], "csat_score": 5}, correlation=token)
    request_view = _call(case, "GET", f"/api/v1/service-requests/{created['id']}", "cskh")
    closed_request = _call(case, "POST", f"/api/v1/service-requests/{created['id']}/close", "cskh",
                           body={"expected_version": request_view["version"], "csat_score": 5}, correlation=token)
    assert work_order["status"] == "CLOSED"
    assert closed_request["status"] == "CLOSED"

    account = next(item for item in _call(case, "GET", "/api/v1/billing/accounts", "accountant")["items"]
                   if item["building_id"] == building["id"] and item["unit_id"] == unit["id"])
    unique = uuid4().hex[:8].upper()
    policy = _call(case, "POST", "/api/v1/billing/fee-policies", "accountant", status=201,
                   body={"building_id": account["building_id"], "code": f"R5-FEE-{unique}", "name": "Phí R5 oracle",
                         "effective_from": "2099-03-01", "unit_rate_vnd": 10_000, "rounding_unit_vnd": 1},
                   key="r5-flow-billing-policy", correlation=token)
    period = _call(case, "POST", "/api/v1/billing/periods", "accountant", status=201,
                   body={"building_id": account["building_id"], "period_key": "2099-03", "period_start": "2099-03-01",
                         "period_end": "2099-03-31", "cutoff_at": "2099-03-31T23:59:00Z"},
                   key="r5-flow-billing-period", correlation=token)
    run_body = {"accounting_period_id": period["id"], "fee_policy_version_id": policy["versions"][0]["id"],
                "run_key": f"r5-flow-billing-{unique}"}
    run = _call(case, "POST", "/api/v1/billing/runs", "accountant", status=201, body=run_body,
                key="r5-flow-billing-run", correlation=token)
    assert _call(case, "POST", "/api/v1/billing/runs", "accountant", status=201, body=run_body,
                 key="r5-flow-billing-run", correlation=token) == run
    assert run["status"] == "POSTED"
    invoices = _call(case, "GET", "/api/v1/billing/invoices", "accountant")["items"]
    invoice = next(item for item in invoices if item["accounting_period_id"] == period["id"] and item["billing_account_id"] == account["id"])
    assert {item["source_pending_charge_id"] for item in invoice["items"] if item["source_pending_charge_id"]} == {decided["id"]}
    snapshot = {"total_vnd": invoice["total_vnd"], "items": invoice["items"]}
    with case["database"].get_session() as session:
        ledger_before_payment = session.execute(select(
            ArLedgerEntry.id, ArLedgerEntry.debit_vnd, ArLedgerEntry.credit_vnd, ArLedgerEntry.entry_type,
        ).where(ArLedgerEntry.source_id == UUID(invoice["id"]))).all()
    assert ledger_before_payment == [(ledger_before_payment[0][0], snapshot["total_vnd"], 0, "INVOICE_ISSUED")]
    payment_body = {"billing_account_id": account["id"], "accounting_period_id": period["id"], "payment_source": "CASH",
                    "source_reference": f"R5-CASH-{unique}", "receipt_number": f"R5-RCPT-{unique}",
                    "amount_vnd": snapshot["total_vnd"], "received_at": "2099-03-31T12:00:00Z"}
    payment = _call(case, "POST", "/api/v1/billing/payments", "accountant", status=201, body=payment_body,
                    key="r5-flow-billing-payment", correlation=token)
    assert _call(case, "POST", "/api/v1/billing/payments", "accountant", status=201, body=payment_body,
                 key="r5-flow-billing-payment", correlation=token) == payment
    allocated = _call(case, "POST", f"/api/v1/billing/payments/{payment['id']}/allocate", "accountant",
                      key="r5-flow-billing-allocation", correlation=token)
    assert allocated["payment"]["status"] == "ALLOCATED"
    invoice_after = _call(case, "GET", f"/api/v1/billing/invoices/{invoice['id']}", "accountant")
    assert invoice_after["status"] == "PAID" and invoice_after["outstanding_vnd"] == 0
    assert {"total_vnd": invoice_after["total_vnd"], "items": invoice_after["items"]} == snapshot
    with case["database"].get_session() as session:
        assert session.execute(select(
            ArLedgerEntry.id, ArLedgerEntry.debit_vnd, ArLedgerEntry.credit_vnd, ArLedgerEntry.entry_type,
        ).where(ArLedgerEntry.source_id == UUID(invoice["id"]))).all() == ledger_before_payment
    as_of = "2099-04-01T00:00:00Z"
    drill_down = _call(case, "GET", f"/api/v1/dashboard/drill-down/ar_debt?as_of={as_of}", "director")
    assert all(item["resource_id"] != account["id"] for item in drill_down["items"])
    return building, unit


def _flow_maintenance_to_history(case, building_id, unit_id, token):
    unique = uuid4().hex[:10].upper()
    due_at = datetime(2099, 1, 15, 9, tzinfo=UTC)
    asset_body = {"building_id": building_id, "unit_id": unit_id, "code": f"R5-GEN-{unique}",
                  "name": "Máy phát R5", "description": "Tài sản kiểm chứng Golden Flow."}
    asset = _call(case, "POST", "/api/v1/assets", "lead", status=201, body=asset_body,
                  key="r5-flow-asset-create", correlation=token)
    assert _call(case, "POST", "/api/v1/assets", "lead", status=201, body=asset_body,
                 key="r5-flow-asset-create", correlation=token) == asset
    plan = _call(case, "POST", "/api/v1/maintenance-plans", "lead", status=201,
                 body={"asset_id": asset["id"], "code": f"R5-MNT-{unique}", "title": "Bảo trì máy phát R5",
                       "interval_days": 30, "next_due_at": due_at.isoformat(),
                       "checklist": [{"label": "Máy phát chạy thử đạt", "required": True}], "evidence_required": False},
                 key="r5-flow-maintenance-plan", correlation=token)
    run_body = {"as_of": (due_at + timedelta(days=1)).isoformat()}
    scheduled = _call(case, "POST", "/api/v1/maintenance/scheduler/run", "lead", body=run_body,
                      key="r5-flow-maintenance-run", correlation=token)
    replayed = _call(case, "POST", "/api/v1/maintenance/scheduler/run", "lead", body=run_body,
                     key="r5-flow-maintenance-run", correlation=token)
    assert replayed == scheduled
    occurrence = next(item for item in scheduled["items"] if item["plan_id"] == plan["id"])
    work_order = _work_order(case, occurrence["work_order_id"])
    work_order = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/assign", "lead",
                       body={"assignee_id": case["identities"]["tech"], "expected_version": work_order["version"]},
                       correlation=token)
    work_order = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/start", "tech",
                       body={"expected_version": work_order["version"]}, correlation=token)
    checklist = work_order["checklist"][0]
    _call(case, "PATCH", f"/api/v1/work-orders/{work_order['id']}/checklist/{checklist['id']}", "tech",
          body={"expected_version": checklist["version"], "is_completed": True, "result": "Khởi động thử đạt"},
          correlation=token)
    work_order = _work_order(case, work_order["id"], "tech")
    work_order = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/submit", "tech",
                       body={"expected_version": work_order["version"], "result_summary": "Máy phát hoạt động bình thường."},
                       correlation=token)
    accepted = _call(case, "POST", f"/api/v1/work-orders/{work_order['id']}/accept", "lead",
                     body={"expected_version": work_order["version"], "mode": "TECHNICAL"}, correlation=token)
    assert accepted["status"] == "COMPLETED"
    history = _call(case, "GET", f"/api/v1/assets/{asset['id']}/maintenance-history", "lead")
    item = next(entry for entry in history["items"] if entry["occurrence_id"] == occurrence["occurrence_id"])
    assert item["asset_id"] == asset["id"] and item["work_order_id"] == accepted["id"]
    plan_after = _call(case, "GET", f"/api/v1/maintenance-plans/{plan['id']}", "lead")
    assert datetime.fromisoformat(plan_after["next_due_at"].replace("Z", "+00:00")) == due_at + timedelta(days=30)
    rejected = case["client"].get(f"/api/v1/assets/{asset['id']}/maintenance-history", headers=case["auth"]["cskh_east"])
    assert rejected.status_code == 404 and rejected.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"


def _flow_cleaning_to_case(case, token):
    route = _call(case, "GET", "/api/v1/cleaning/routes", "director")[0]
    shift = _call(case, "POST", "/api/v1/cleaning/shifts", "director", status=201,
                  body={"route_id": route["id"], "scheduled_start_at": "2099-02-01T08:00:00Z", "scheduled_end_at": "2099-02-01T12:00:00Z"},
                  key="r5-flow-cleaning-shift", correlation=token)
    task = shift["tasks"][0]
    task = _call(case, "POST", f"/api/v1/cleaning/tasks/{task['id']}/assign", "director",
                 body={"assignee_id": case["identities"]["cleaner"], "expected_version": task["version"]}, correlation=token)
    task = _call(case, "POST", f"/api/v1/cleaning/tasks/{task['id']}/start", "cleaner",
                 body={"expected_version": task["version"]}, correlation=token)
    for index in range(len(task["checklist"])):
        checklist = task["checklist"][index]
        task = _call(case, "PATCH", f"/api/v1/cleaning/tasks/{task['id']}/checklist/{checklist['id']}", "cleaner",
                     body={"expected_version": checklist["version"], "result": "FAIL" if index == 0 else "PASS",
                           "note": "R5 oracle"}, correlation=token)
    submitted = _call(case, "POST", f"/api/v1/cleaning/tasks/{task['id']}/submit", "cleaner",
                      body={"expected_version": task["version"]}, key="r5-flow-cleaning-submit", correlation=token)
    replayed = _call(case, "POST", f"/api/v1/cleaning/tasks/{task['id']}/submit", "cleaner",
                     body={"expected_version": task["version"]}, key="r5-flow-cleaning-submit", correlation=token)
    assert submitted == replayed and submitted["status"] == "REWORK_REQUIRED"
    assert submitted["rework_case_id"] and submitted["rework_work_order_id"]


def _flow_patrol_to_incident(case, token):
    point = _call(case, "GET", "/api/v1/security/patrol-points", "director")[0]
    security_shift = _call(case, "POST", "/api/v1/security/shifts", "director", status=201,
                           body={"building_id": point["building_id"], "assignee_id": case["identities"]["security"],
                                 "scheduled_start_at": "2099-02-02T08:00:00Z", "scheduled_end_at": "2099-02-02T12:00:00Z",
                                 "patrol_windows": [{"patrol_point_id": point["id"], "window_start_at": "2099-02-02T09:00:00Z", "window_end_at": "2099-02-02T10:00:00Z"}]},
                           key="r5-flow-security-shift", correlation=token)
    security_shift = _call(case, "POST", f"/api/v1/security/shifts/{security_shift['id']}/start", "security",
                           body={"expected_version": security_shift["version"]}, correlation=token)
    window = security_shift["patrol_windows"][0]
    incident = _call(case, "POST", "/api/v1/security/incidents", "security", status=201,
                     body={"patrol_window_id": window["id"], "incident_type": "FIRE", "severity": "HIGH",
                           "title": "Khói tại sảnh", "description": "Phát hiện khói khi tuần tra.", "occurred_at": "2099-02-02T09:15:00Z"},
                     key="r5-flow-security-incident", correlation=token)
    incident = _call(case, "POST", f"/api/v1/security/incidents/{incident['id']}/evidence", "security", status=201,
                     body={"evidence_type": "NOTE", "description": "Đã cô lập khu vực và ghi nhận hiện trường."},
                     key="r5-flow-security-evidence", correlation=token)
    security_escalation = next(item for item in incident["escalations"] if item["target_role"] == "security")
    director_escalation = next(item for item in incident["escalations"] if item["target_role"] == "director")
    incident = _call(case, "POST", f"/api/v1/security/incidents/{incident['id']}/escalations/{security_escalation['id']}/acknowledgements", "security", status=201,
                     body={"note": "An ninh đã tiếp nhận."}, key="r5-flow-security-ack-security", correlation=token)
    incident = _call(case, "POST", f"/api/v1/security/incidents/{incident['id']}/escalations/{director_escalation['id']}/acknowledgements", "director", status=201,
                     body={"note": "Giám đốc đã tiếp nhận."}, key="r5-flow-security-ack-director", correlation=token)
    for status in ("TRIAGED", "IN_PROGRESS", "RESOLVED"):
        incident = _call(case, "POST", f"/api/v1/security/incidents/{incident['id']}/transition", "security",
                         body={"expected_version": incident["version"], "status": status}, correlation=token)
    closed = _call(case, "POST", f"/api/v1/security/incidents/{incident['id']}/transition", "director",
                   body={"expected_version": incident["version"], "status": "CLOSED", "conclusion": "Đã xử lý và an toàn."},
                   correlation=token)
    assert closed["status"] == "CLOSED"

def _assert_financial_invariants(case):
    with case["database"].get_session() as session:
        orphan_items = session.scalar(select(func.count(InvoiceItem.id)).outerjoin(
            PendingCharge, PendingCharge.id == InvoiceItem.pending_charge_id,
        ).where(or_(PendingCharge.id.is_(None), PendingCharge.status != "POSTED")))
        unanchored_postings = session.scalar(select(func.count(PendingCharge.id)).outerjoin(
            InvoiceItem, InvoiceItem.pending_charge_id == PendingCharge.id,
        ).where(PendingCharge.status == "POSTED", InvoiceItem.id.is_(None)))
    assert orphan_items == 0 and unanchored_postings == 0


def _flow_control_and_audit(case, correlations):
    """Gate-C fifth flow: reconcile all KPI drill-downs and audit trails."""
    as_of = "2100-01-01T00:00:00Z"
    dashboard = _call(case, "GET", f"/api/v1/dashboard?as_of={as_of}", "director")
    expected_counts = {
        "sla_overdue": dashboard["sla_overdue_count"],
        "maintenance_due": dashboard["maintenance_due_count"],
        "cleaning_rework": dashboard["cleaning_rework_count"],
        "open_incidents": dashboard["open_incident_count"],
    }
    for metric, count in expected_counts.items():
        drill_down = _call(case, "GET", f"/api/v1/dashboard/drill-down/{metric}?as_of={as_of}", "director")
        assert drill_down["as_of"].startswith("2100-01-01")
        assert drill_down["metric"] == metric and len(drill_down["items"]) == count
    debt = _call(case, "GET", f"/api/v1/dashboard/drill-down/ar_debt?as_of={as_of}", "director")
    assert sum(item.get("amount_vnd", 0) for item in debt["items"]) == dashboard["ar_debt_vnd"]
    for correlation in correlations:
        audit = _call(case, "GET", f"/api/v1/audit-events?correlation_id={correlation}", "director")
        assert audit["items"]
        assert all(item["correlation_id"] == str(correlation) for item in audit["items"])
        assert all(item["actor_account_id"] is not None for item in audit["items"])


def test_ac45_five_golden_flows_api_only_with_scope_audit_retry_and_invariants(seeded_api_case):
    """AC-45, AC-22/25/36 regression, INV-01/02 and server-derived scope."""
    case = seeded_api_case
    flow1, flow2, flow3, flow4 = uuid4(), uuid4(), uuid4(), uuid4()
    building, unit = _flow_customer_to_cash(case, flow1)
    _flow_maintenance_to_history(case, building["id"], unit["id"], flow2)
    _flow_cleaning_to_case(case, flow3)
    _flow_patrol_to_incident(case, flow4)
    _assert_financial_invariants(case)
    _flow_control_and_audit(case, (flow1, flow2, flow3, flow4))
    assert {"ServiceRequestCreated", "WorkOrderClosed", "PendingChargeApproved", "BillingRunCompleted", "PaymentReceived", "PaymentAllocated", "ServiceRequestClosed"} <= _audit_types(case, flow1)
    assert {"AssetCreated", "MaintenancePlanCreated", "WorkOrderCompleted"} <= _audit_types(case, flow2)
    assert {"CleaningReworkCaseOpened"} <= _audit_types(case, flow3)
    assert {"SecurityIncidentCreated", "SecurityIncidentTransitioned"} <= _audit_types(case, flow4)
