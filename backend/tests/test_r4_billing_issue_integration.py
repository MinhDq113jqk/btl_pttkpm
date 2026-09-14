"""R4 Task 2 acceptance tests on the disposable PostgreSQL cluster."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
import os
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.core.database import Database
from app.core.security import create_token
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.billing import (
    AccountingPeriod,
    ArLedgerEntry,
    BillingAccount,
    BillingInvoice,
    BillingInvoiceItem,
    BillingRun,
    FeePolicy,
    FeePolicyVersion,
    Payment,
    PaymentAllocation,
)
from app.models.building import Building
from app.models.service import CostLine, PendingCharge, ServiceRequest, WorkOrder
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit
from test_r2_integration import r2_case, with_key


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R4 tests require its disposable PostgreSQL cluster",
)]


@pytest.fixture(scope="module")
def issue_case(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        account = BillingAccount(
            tenant_id=case["tenant"].id,
            site_id=case["sites"][0].id,
            building_id=case["buildings"][0].id,
            unit_id=case["units"][0].id,
            account_number=f"R4-Issue-{uuid4().hex[:10]}",
            opened_on=datetime(2026, 1, 1, tzinfo=UTC).date(),
        )
        session.add(account)
        session.commit()
    return case | {"billing_account": account}


def _key(case, value: str):
    return with_key(case, "accountant", f"r4-task2-{value}-{uuid4().hex[:10]}")


def _policy(case, *, effective_from: str, rate: int = 12000, rounding_unit: int = 1):
    response = case["client"].post("/api/v1/billing/fee-policies", headers=_key(case, "policy"), json={
        "building_id": str(case["buildings"][0].id),
        "code": f"FEE-{uuid4().hex[:8].upper()}",
        "name": "Phí quản lý R4",
        "effective_from": effective_from,
        "unit_rate_vnd": rate,
        "rounding_unit_vnd": rounding_unit,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _period(case, *, key: str, start: str, end: str, cutoff: str):
    response = case["client"].post("/api/v1/billing/periods", headers=_key(case, "period"), json={
        "building_id": str(case["buildings"][0].id),
        "period_key": key,
        "period_start": start,
        "period_end": end,
        "cutoff_at": cutoff,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _run(case, period_id: str, version_id: str):
    return case["client"].post("/api/v1/billing/runs", headers=_key(case, "run"), json={
        "accounting_period_id": period_id,
        "fee_policy_version_id": version_id,
        "run_key": f"run-{uuid4().hex}",
    })


def test_r4_golden_flow_policy_period_run_issues_immutable_snapshot_and_ledger(issue_case):
    case = issue_case
    with case["database"].get_session() as session:
        unit = session.get(type(case["units"][0]), case["units"][0].id)
        unit.area_m2 = 80.25
        session.commit()
    policy = _policy(case, effective_from="2026-09-01")
    period = _period(case, key="2026-09", start="2026-09-01", end="2026-09-30", cutoff="2026-09-20T00:00:00Z")
    run = _run(case, period["id"], policy["versions"][0]["id"])
    assert run.status_code == 201, run.text
    assert run.json()["status"] == "POSTED"

    invoices = case["client"].get("/api/v1/billing/invoices", headers=case["auth"]["accountant"])
    assert invoices.status_code == 200
    invoice = next(item for item in invoices.json()["items"] if item["accounting_period_id"] == period["id"])
    assert invoice["total_vnd"] == invoice["outstanding_vnd"] == 963000
    assert invoice["items"] == [{
        "id": invoice["items"][0]["id"], "line_number": 1, "description": "UNIT AREA M2",
        "basis": "UNIT_AREA_M2", "basis_quantity": 80.25, "unit_rate_vnd_snapshot": 12000,
        "rounding_unit_vnd_snapshot": 1, "amount_vnd": 963000, "source_pending_charge_id": None,
    }]
    with case["database"].get_session() as session:
        stored = session.scalar(select(BillingInvoice).where(BillingInvoice.id == invoice["id"]))
        ledger = session.scalar(select(ArLedgerEntry).where(
            ArLedgerEntry.source_type == "INVOICE", ArLedgerEntry.source_id == stored.id,
            ArLedgerEntry.entry_type == "INVOICE_ISSUED",
        ))
        assert ledger is not None and ledger.debit_vnd == 963000 and ledger.credit_vnd == 0
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text("UPDATE greencity.billing_invoice_items SET amount_vnd=1 WHERE billing_invoice_id=:id"), {"id": stored.id})


def test_r4_run_failure_is_atomic_and_retry_reuses_the_same_run(issue_case):
    case = issue_case
    with case["database"].get_session() as session:
        unit = session.get(type(case["units"][0]), case["units"][0].id)
        unit.area_m2 = 0
        session.commit()
    policy = _policy(case, effective_from="2026-10-01", rounding_unit=1000)
    period = _period(case, key="2026-10", start="2026-10-01", end="2026-10-31", cutoff="2026-10-20T00:00:00Z")
    failed = _run(case, period["id"], policy["versions"][0]["id"])
    assert failed.status_code == 201, failed.text
    assert failed.json()["status"] == "FAILED"
    assert failed.json()["failure_code"] == "ERR-BILLING-BASIS"
    with case["database"].get_session() as session:
        assert session.scalar(select(BillingInvoice.id).where(BillingInvoice.accounting_period_id == period["id"])) is None
        unit = session.get(type(case["units"][0]), case["units"][0].id)
        unit.area_m2 = 82.58
        session.commit()
    retried = case["client"].post(
        f"/api/v1/billing/runs/{failed.json()['id']}/retry", headers=_key(case, "retry"),
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["id"] == failed.json()["id"]
    assert retried.json()["status"] == "POSTED"
    assert retried.json()["retry_count"] == 1
    with case["database"].get_session() as session:
        invoice = session.scalar(select(BillingInvoice).where(BillingInvoice.accounting_period_id == period["id"]))
        assert invoice.total_vnd == 991000


def test_r4_duplicate_run_is_database_backed_and_does_not_duplicate_invoices(issue_case):
    case = issue_case
    with case["database"].get_session() as session:
        unit = session.get(type(case["units"][0]), case["units"][0].id)
        unit.area_m2 = 50
        session.commit()
    policy = _policy(case, effective_from="2026-11-01")
    period = _period(case, key="2026-11", start="2026-11-01", end="2026-11-30", cutoff="2026-11-15T00:00:00Z")
    first = _run(case, period["id"], policy["versions"][0]["id"])
    second = _run(case, period["id"], policy["versions"][0]["id"])
    assert first.status_code == 201 and first.json()["status"] == "POSTED"
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ERR-RUN-DUPLICATE"
    with case["database"].get_session() as session:
        assert str(session.scalar(select(BillingRun).where(BillingRun.accounting_period_id == period["id"])).id) == first.json()["id"]
        assert len(session.scalars(select(BillingInvoice).where(BillingInvoice.accounting_period_id == period["id"])).all()) == 1


def test_r4_two_concurrent_accountants_have_one_billing_run_winner():
    """AC-12: separate connections race on the same business key."""
    settings = Settings()
    database = Database(settings)
    app = create_app(settings, database)
    try:
        with database.get_session() as session:
            tenant = Tenant(name=f"R4 concurrent {uuid4()}")
            session.add(tenant)
            session.flush()
            site = Site(tenant_id=tenant.id, code=f"R4-CON-{uuid4().hex[:8]}", name="Concurrent site", address="Synthetic")
            session.add(site)
            session.flush()
            building = Building(site_id=site.id, code="B1", name="Concurrent building")
            session.add(building)
            session.flush()
            unit = Unit(building_id=building.id, unit_number="0101", floor=1, area_m2=80.25, status="occupied")
            accountant = Account(
                tenant_id=tenant.id,
                username=f"r4_concurrent_{uuid4().hex}",
                full_name="Concurrent accountant",
                hashed_password="token-only-test-account",
            )
            session.add_all((unit, accountant))
            session.flush()
            session.add(AccountRole(account_id=accountant.id, role="accountant", site_id=site.id, building_id=None))
            billing_account = BillingAccount(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
                account_number=f"R4-CON-{uuid4().hex[:8]}", opened_on=date(2026, 1, 1),
            )
            policy = FeePolicy(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                code=f"CON-{uuid4().hex[:8].upper()}", name="Concurrent policy",
            )
            session.add_all((billing_account, policy))
            session.flush()
            version = FeePolicyVersion(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, fee_policy_id=policy.id,
                version_number=1, effective_from=date(2026, 1, 1), unit_rate_vnd=12000,
                rounding_unit_vnd=1, published_at=datetime.now(UTC),
            )
            period = AccountingPeriod(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                period_key="2026-09", period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                cutoff_at=datetime(2026, 9, 20, tzinfo=UTC),
            )
            session.add_all((version, period))
            session.commit()

        headers = {"Authorization": "Bearer " + create_token({
            "sub": str(accountant.id), "active_site_id": str(site.id), "purpose": "session",
        }, settings.auth_secret())}
        barrier = Barrier(3, timeout=10)

        def start_run(run_key: str):
            with TestClient(app) as client:
                barrier.wait()
                return client.post("/api/v1/billing/runs", headers=headers | {"Idempotency-Key": f"r4-concurrent-{run_key}"}, json={
                    "accounting_period_id": str(period.id), "fee_policy_version_id": str(version.id), "run_key": run_key,
                })

        with ThreadPoolExecutor(max_workers=2) as executor:
            requests = [executor.submit(start_run, f"run-{suffix}-{uuid4().hex}") for suffix in ("a", "b")]
            barrier.wait()
            responses = [request.result(timeout=15) for request in requests]
        assert sorted(response.status_code for response in responses) == [201, 409]
        rejected = next(response for response in responses if response.status_code == 409)
        assert rejected.json()["error"]["code"] == "ERR-RUN-DUPLICATE"
        with database.get_session() as session:
            assert len(session.scalars(select(BillingRun).where(BillingRun.accounting_period_id == period.id)).all()) == 1
            assert len(session.scalars(select(BillingInvoice).where(BillingInvoice.accounting_period_id == period.id)).all()) == 1
    finally:
        database.close()


def test_r4_charge_after_cutoff_moves_to_next_period(issue_case):
    case = issue_case
    policy = _policy(case, effective_from="2026-12-01", rate=1000)
    current_period = _period(case, key="2026-12", start="2026-12-01", end="2026-12-31", cutoff="2026-12-15T00:00:00Z")
    next_period = _period(case, key="2027-01", start="2027-01-01", end="2027-01-31", cutoff="2027-01-20T00:00:00Z")
    with case["database"].get_session() as session:
        request = ServiceRequest(
            tenant_id=case["tenant"].id, site_id=case["sites"][0].id, building_id=case["buildings"][0].id,
            unit_id=case["units"][0].id, category_id=case["categories"][0].id,
            code=f"R4-CHG-{uuid4().hex[:8]}", title="Chi phí phát sinh", description="Kiểm tra", priority="MEDIUM",
            status="IN_PROGRESS", sla_started_at=datetime(2026, 12, 1, tzinfo=UTC), sla_duration_minutes=60,
            owner_account_id=case["accounts"]["cskh"].id, created_by_id=case["accounts"]["cskh"].id,
            updated_by_id=case["accounts"]["cskh"].id,
        )
        session.add(request)
        session.flush()
        work_order = WorkOrder(
            tenant_id=request.tenant_id, site_id=request.site_id, building_id=request.building_id,
            service_request_id=request.id, code=f"R4-WO-{uuid4().hex[:8]}", title="Sửa chữa", description="Kiểm tra",
            status="COMPLETED", created_by_id=case["accounts"]["cskh"].id, updated_by_id=case["accounts"]["cskh"].id,
        )
        session.add(work_order)
        session.flush()
        line = CostLine(work_order_id=work_order.id, description="Thay vật tư", amount_vnd=12345,
                        cost_bearer="RESIDENT", status="SUBMITTED", created_by_id=case["accounts"]["cskh"].id,
                        updated_by_id=case["accounts"]["cskh"].id)
        session.add(line)
        session.flush()
        charge = PendingCharge(cost_line_id=line.id, status="APPROVED", submitted_by_id=case["accounts"]["cskh"].id,
                               reviewed_by_id=case["accounts"]["accountant"].id,
                               reviewed_at=datetime(2026, 12, 16, tzinfo=UTC))
        session.add(charge)
        session.commit()
    assert _run(case, current_period["id"], policy["versions"][0]["id"]).json()["status"] == "POSTED"
    assert _run(case, next_period["id"], policy["versions"][0]["id"]).json()["status"] == "POSTED"
    with case["database"].get_session() as session:
        current_items = session.scalars(select(BillingInvoiceItem).join(BillingInvoice).where(
            BillingInvoice.accounting_period_id == current_period["id"],
        )).all()
        next_items = session.scalars(select(BillingInvoiceItem).join(BillingInvoice).where(
            BillingInvoice.accounting_period_id == next_period["id"],
        )).all()
        assert all(item.source_pending_charge_id is None for item in current_items)
        assert {item.source_pending_charge_id for item in next_items if item.source_pending_charge_id} == {charge.id}


def test_r4_void_requires_open_unallocated_invoice_and_preserves_history(issue_case):
    case = issue_case
    policy = _policy(case, effective_from="2027-02-01")
    period = _period(case, key="2027-02", start="2027-02-01", end="2027-02-28", cutoff="2027-02-15T00:00:00Z")
    run = _run(case, period["id"], policy["versions"][0]["id"])
    assert run.json()["status"] == "POSTED"
    invoice = next(item for item in case["client"].get("/api/v1/billing/invoices", headers=case["auth"]["accountant"]).json()["items"]
                   if item["accounting_period_id"] == period["id"])
    voided = case["client"].post(f"/api/v1/billing/invoices/{invoice['id']}/void", headers=case["auth"]["accountant"], json={
        "expected_version": invoice["version"], "reason": "Lập lại theo yêu cầu kế toán",
    })
    assert voided.status_code == 200, voided.text
    assert voided.json()["status"] == "VOID" and voided.json()["total_vnd"] == invoice["total_vnd"]
    assert voided.json()["outstanding_vnd"] == 0 and len(voided.json()["items"]) == 1
    with case["database"].get_session() as session:
        reversal = session.scalar(select(ArLedgerEntry).where(
            ArLedgerEntry.source_id == invoice["id"], ArLedgerEntry.entry_type == "REVERSAL",
        ))
        assert reversal is not None and reversal.credit_vnd == invoice["total_vnd"]
    repeat = case["client"].post(f"/api/v1/billing/invoices/{invoice['id']}/void", headers=case["auth"]["accountant"], json={
        "expected_version": voided.json()["version"], "reason": "Không hợp lệ",
    })
    assert repeat.status_code == 409


def test_r4_void_rejects_allocated_invoice_and_closed_period(issue_case):
    case = issue_case

    allocated_policy = _policy(case, effective_from="2027-04-01")
    allocated_period = _period(case, key="2027-04", start="2027-04-01", end="2027-04-30", cutoff="2027-04-15T00:00:00Z")
    assert _run(case, allocated_period["id"], allocated_policy["versions"][0]["id"]).json()["status"] == "POSTED"
    allocated_invoice = next(item for item in case["client"].get(
        "/api/v1/billing/invoices", headers=case["auth"]["accountant"],
    ).json()["items"] if item["accounting_period_id"] == allocated_period["id"])

    payment = case["client"].post("/api/v1/billing/payments", headers=_key(case, "allocated-payment"), json={
        "billing_account_id": str(case["billing_account"].id),
        "accounting_period_id": allocated_period["id"],
        "payment_source": "CASH",
        "source_reference": f"void-allocation-{uuid4().hex}",
        "receipt_number": f"void-receipt-{uuid4().hex}",
        "amount_vnd": 1,
        "received_at": "2027-04-10T00:00:00Z",
    })
    assert payment.status_code == 201, payment.text
    with case["database"].get_session() as session:
        received = session.get(Payment, payment.json()["id"])
        session.add(PaymentAllocation(
            tenant_id=received.tenant_id,
            site_id=received.site_id,
            building_id=received.building_id,
            payment_id=received.id,
            billing_invoice_id=allocated_invoice["id"],
            amount_vnd=1,
            allocated_by_id=case["accounts"]["accountant"].id,
        ))
        session.commit()
    allocated_void = case["client"].post(
        f"/api/v1/billing/invoices/{allocated_invoice['id']}/void", headers=case["auth"]["accountant"], json={
            "expected_version": allocated_invoice["version"], "reason": "Không void hóa đơn đã có allocation",
        },
    )
    assert allocated_void.status_code == 409
    assert allocated_void.json()["error"]["code"] == "ERR-INVOICE-VOID-RESTRICTED"

    closed_policy = _policy(case, effective_from="2027-05-01")
    closed_period = _period(case, key="2027-05", start="2027-05-01", end="2027-05-31", cutoff="2027-05-15T00:00:00Z")
    assert _run(case, closed_period["id"], closed_policy["versions"][0]["id"]).json()["status"] == "POSTED"
    closed_invoice = next(item for item in case["client"].get(
        "/api/v1/billing/invoices", headers=case["auth"]["accountant"],
    ).json()["items"] if item["accounting_period_id"] == closed_period["id"])
    closing = case["client"].post(
        f"/api/v1/billing/periods/{closed_period['id']}/transition", headers=case["auth"]["accountant"], json={
            "expected_version": closed_period["version"], "status": "CLOSING",
        },
    )
    assert closing.status_code == 200, closing.text
    closed = case["client"].post(
        f"/api/v1/billing/periods/{closed_period['id']}/transition", headers=case["auth"]["accountant"], json={
            "expected_version": closing.json()["version"], "status": "CLOSED",
        },
    )
    assert closed.status_code == 200, closed.text
    closed_void = case["client"].post(
        f"/api/v1/billing/invoices/{closed_invoice['id']}/void", headers=case["auth"]["accountant"], json={
            "expected_version": closed_invoice["version"], "reason": "Không void hóa đơn kỳ đã đóng",
        },
    )
    assert closed_void.status_code == 409
    assert closed_void.json()["error"]["code"] == "ERR-ACCOUNTING-PERIOD-CLOSED"
    with case["database"].get_session() as session:
        assert session.get(BillingInvoice, allocated_invoice["id"]).status == "ISSUED"
        assert session.get(BillingInvoice, closed_invoice["id"]).status == "ISSUED"


def test_r4_fee_period_endpoints_are_authorized_and_closing_rejects_retroactive_policy(issue_case):
    case = issue_case
    forbidden = case["client"].get("/api/v1/billing/fee-policies", headers=case["auth"]["cskh"])
    assert forbidden.status_code == 403
    period = _period(case, key="2027-03", start="2027-03-01", end="2027-03-31", cutoff="2027-03-15T00:00:00Z")
    closing = case["client"].post(f"/api/v1/billing/periods/{period['id']}/transition", headers=case["auth"]["accountant"], json={
        "expected_version": period["version"], "status": "CLOSING",
    })
    assert closing.status_code == 200
    rejected = case["client"].post("/api/v1/billing/fee-policies", headers=_key(case, "closing-policy"), json={
        "building_id": str(case["buildings"][0].id), "code": f"FEE-{uuid4().hex[:8].upper()}", "name": "Không hồi tố",
        "effective_from": "2027-03-15", "unit_rate_vnd": 1000, "rounding_unit_vnd": 1,
    })
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "ERR-POLICY-EFFECTIVE-NEXT-PERIOD"
