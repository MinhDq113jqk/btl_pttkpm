"""R4 Task 4 fixed-oracle acceptance flow on the isolated PostgreSQL cluster."""
from datetime import date
import os

import pytest
from sqlalchemy import func, select

from app.models.billing import AccountingPeriod, ArLedgerEntry, BillingAccount, BillingInvoice, Payment
from app.models.unit import Unit
from test_r2_integration import r2_case, with_key


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R4 Golden Flow requires its disposable PostgreSQL cluster",
)]


def _headers(case, name: str) -> dict[str, str]:
    return with_key(case, "accountant", f"r4-flow-{name}")


def _create_account(case, account_number: str, area_m2: float) -> BillingAccount:
    with case["database"].get_session() as session:
        unit = Unit(
            building_id=case["buildings"][0].id,
            unit_number=account_number,
            floor=99,
            area_m2=area_m2,
            status="occupied",
        )
        session.add(unit)
        session.flush()
        account = BillingAccount(
            tenant_id=case["tenant"].id,
            site_id=case["sites"][0].id,
            building_id=case["buildings"][0].id,
            unit_id=unit.id,
            account_number=account_number,
            opened_on=date(2026, 1, 1),
        )
        session.add(account)
        session.commit()
        return account


def _policy(case, code: str, effective_from: str, *, rounding_unit_vnd: int = 1) -> dict:
    response = case["client"].post("/api/v1/billing/fee-policies", headers=_headers(case, f"policy-{code}"), json={
        "building_id": str(case["buildings"][0].id),
        "code": code,
        "name": "Fixed oracle management fee",
        "effective_from": effective_from,
        "unit_rate_vnd": 12_000,
        "rounding_unit_vnd": rounding_unit_vnd,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _period(case, period_key: str, start: str, end: str, cutoff: str) -> dict:
    response = case["client"].post("/api/v1/billing/periods", headers=_headers(case, f"period-{period_key}"), json={
        "building_id": str(case["buildings"][0].id),
        "period_key": period_key,
        "period_start": start,
        "period_end": end,
        "cutoff_at": cutoff,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _run(case, period: dict, version_id: str, run_key: str) -> dict:
    response = case["client"].post("/api/v1/billing/runs", headers=_headers(case, f"run-{period['period_key']}"), json={
        "accounting_period_id": period["id"],
        "fee_policy_version_id": version_id,
        "run_key": run_key,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _invoices_by_period(case) -> dict[str, dict]:
    response = case["client"].get("/api/v1/billing/invoices", headers=case["auth"]["accountant"])
    assert response.status_code == 200, response.text
    return {item["accounting_period_id"]: item for item in response.json()["items"]}


def _ar_debt(session, billing_account_id) -> int:
    return session.scalar(select(func.coalesce(func.sum(
        ArLedgerEntry.debit_vnd - ArLedgerEntry.credit_vnd,
    ), 0)).where(ArLedgerEntry.billing_account_id == billing_account_id))


def test_r4_fixed_oracle_financial_golden_flow_with_idempotent_recovery(r2_case):
    """AC-11/17/18/30/36/44: issue, settle, recover a lost response and match."""
    case = r2_case
    account = _create_account(case, "R4-FLOW-ORACLE", 80.25)

    policy = _policy(case, "R4-FLOW", "2026-09-01")
    september = _period(case, "2026-09", "2026-09-01", "2026-09-30", "2026-09-20T00:00:00Z")
    october = _period(case, "2026-10", "2026-10-01", "2026-10-31", "2026-10-20T00:00:00Z")
    version_id = policy["versions"][0]["id"]
    assert _run(case, september, version_id, "r4-flow-september")["status"] == "POSTED"
    assert _run(case, october, version_id, "r4-flow-october")["status"] == "POSTED"

    invoices = _invoices_by_period(case)
    september_invoice = invoices[september["id"]]
    october_invoice = invoices[october["id"]]
    assert [september_invoice["total_vnd"], october_invoice["total_vnd"]] == [963_000, 963_000]
    snapshots = {
        invoice["id"]: {"total_vnd": invoice["total_vnd"], "items": invoice["items"]}
        for invoice in (september_invoice, october_invoice)
    }

    settled_body = {
        "billing_account_id": str(account.id),
        "accounting_period_id": october["id"],
        "payment_source": "BANK_TRANSFER",
        "source_reference": "R4-FLOW-SETTLED-001",
        "receipt_number": "R4-FLOW-RECEIPT-001",
        "amount_vnd": 1_000_000,
        "received_at": "2026-10-25T09:00:00Z",
    }
    settled_headers = _headers(case, "settled-retry")
    settled = case["client"].post("/api/v1/billing/payments", headers=settled_headers, json=settled_body)
    replayed = case["client"].post("/api/v1/billing/payments", headers=settled_headers, json=settled_body)
    assert settled.status_code == replayed.status_code == 201
    assert settled.json() == replayed.json()
    duplicate = case["client"].post("/api/v1/billing/payments", headers=_headers(case, "settled-duplicate"), json={
        **settled_body, "receipt_number": "R4-FLOW-RECEIPT-DIFFERENT",
    })
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "ERR-DUPLICATE-PAYMENT"

    settled_payment = settled.json()
    allocated = case["client"].post(
        f"/api/v1/billing/payments/{settled_payment['id']}/allocate",
        headers=_headers(case, "settled-allocate"),
    )
    assert allocated.status_code == 200, allocated.text
    assert allocated.json()["payment"]["status"] == "ALLOCATED"
    assert [(item["billing_invoice_id"], item["amount_vnd"]) for item in allocated.json()["allocations"]] == [
        (september_invoice["id"], 963_000),
        (october_invoice["id"], 37_000),
    ]

    invoices = _invoices_by_period(case)
    assert invoices[september["id"]]["outstanding_vnd"] == 0
    assert invoices[october["id"]]["outstanding_vnd"] == 926_000
    for invoice in invoices.values():
        assert {"total_vnd": invoice["total_vnd"], "items": invoice["items"]} == snapshots[invoice["id"]]
    with case["database"].get_session() as session:
        assert _ar_debt(session, account.id) == 926_000

    unmatched_body = {
        "building_id": str(case["buildings"][0].id),
        "accounting_period_id": october["id"],
        "payment_source": "BANK_TRANSFER",
        "source_reference": "R4-FLOW-UNMATCHED-001",
        "receipt_number": "R4-FLOW-UNMATCHED-RECEIPT-001",
        "amount_vnd": 100_000,
        "received_at": "2026-10-25T10:00:00Z",
    }
    unmatched = case["client"].post("/api/v1/billing/payments", headers=_headers(case, "unmatched-retry"), json=unmatched_body)
    assert unmatched.status_code == 201, unmatched.text
    assert unmatched.json()["status"] == "UNMATCHED"
    invoices_before_match = _invoices_by_period(case)
    assert invoices_before_match[october["id"]]["outstanding_vnd"] == 926_000
    with case["database"].get_session() as session:
        assert _ar_debt(session, account.id) == 926_000
        assert session.scalar(select(ArLedgerEntry.id).where(
            ArLedgerEntry.source_type == "PAYMENT", ArLedgerEntry.source_id == unmatched.json()["id"],
        )) is None

    queue = case["client"].get("/api/v1/billing/unmatched-payments", headers=case["auth"]["accountant"])
    queue_item = next(item for item in queue.json()["items"] if item["payment_id"] == unmatched.json()["id"])
    matched = case["client"].post(
        f"/api/v1/billing/unmatched-payments/{queue_item['id']}/match",
        headers=_headers(case, "unmatched-match"),
        json={"billing_account_id": str(account.id)},
    )
    assert matched.status_code == 200 and matched.json()["status"] == "RECEIVED"
    matched_allocation = case["client"].post(
        f"/api/v1/billing/payments/{unmatched.json()['id']}/allocate",
        headers=_headers(case, "unmatched-allocate"),
    )
    assert matched_allocation.status_code == 200, matched_allocation.text
    assert matched_allocation.json()["payment"]["status"] == "ALLOCATED"
    assert [(item["billing_invoice_id"], item["amount_vnd"]) for item in matched_allocation.json()["allocations"]] == [
        (october_invoice["id"], 100_000),
    ]

    invoices = _invoices_by_period(case)
    assert invoices[october["id"]]["outstanding_vnd"] == 826_000
    for invoice in invoices.values():
        assert {"total_vnd": invoice["total_vnd"], "items": invoice["items"]} == snapshots[invoice["id"]]
    with case["database"].get_session() as session:
        assert len(session.scalars(select(Payment).where(
            Payment.source_reference == settled_body["source_reference"],
        )).all()) == 1
        assert _ar_debt(session, account.id) == 826_000


def test_r4_failed_run_retry_leaves_no_partial_invoice_then_replays(r2_case):
    """AC-13: a failed calculation rolls back its set, then retries the same run."""
    case = r2_case
    account = _create_account(case, "R4-FLOW-RETRY", 0)

    policy = _policy(case, "R4-RETRY", "2026-11-01", rounding_unit_vnd=1_000)
    period = _period(case, "2026-11", "2026-11-01", "2026-11-30", "2026-11-20T00:00:00Z")
    failed = _run(case, period, policy["versions"][0]["id"], "r4-flow-failure")
    assert failed["status"] == "FAILED"
    assert failed["failure_code"] == "ERR-BILLING-BASIS"
    with case["database"].get_session() as session:
        assert session.scalar(select(BillingInvoice.id).where(
            BillingInvoice.accounting_period_id == period["id"],
        )) is None
        unit = session.get(Unit, account.unit_id)
        unit.area_m2 = 82.58
        session.commit()

    retry_headers = _headers(case, "failed-run-retry")
    retried = case["client"].post(f"/api/v1/billing/runs/{failed['id']}/retry", headers=retry_headers)
    replayed = case["client"].post(f"/api/v1/billing/runs/{failed['id']}/retry", headers=retry_headers)
    assert retried.status_code == replayed.status_code == 200
    assert retried.json() == replayed.json()
    assert retried.json()["id"] == failed["id"]
    assert retried.json()["status"] == "POSTED"
    assert retried.json()["retry_count"] == 1
    with case["database"].get_session() as session:
        invoices = session.scalars(select(BillingInvoice).where(
            BillingInvoice.accounting_period_id == period["id"],
        )).all()
        retried_invoice = next(invoice for invoice in invoices if invoice.billing_account_id == account.id)
        assert retried_invoice.total_vnd == 991_000
        assert len(invoices) == 2


def test_r4_public_period_transition_rejects_future_only_commands(r2_case):
    """AC-15 SPEC-ONLY: public R4 stops at CLOSED; no LOCKED/reopen command."""
    case = r2_case
    period = _period(case, "2026-12", "2026-12-01", "2026-12-31", "2026-12-20T00:00:00Z")
    closing = case["client"].post(
        f"/api/v1/billing/periods/{period['id']}/transition",
        headers=case["auth"]["accountant"],
        json={"expected_version": period["version"], "status": "CLOSING"},
    )
    assert closing.status_code == 200, closing.text
    closed = case["client"].post(
        f"/api/v1/billing/periods/{period['id']}/transition",
        headers=case["auth"]["accountant"],
        json={"expected_version": closing.json()["version"], "status": "CLOSED"},
    )
    assert closed.status_code == 200, closed.text

    for target in ("LOCKED", "CLOSING"):
        rejected = case["client"].post(
            f"/api/v1/billing/periods/{period['id']}/transition",
            headers=case["auth"]["accountant"],
            json={"expected_version": closed.json()["version"], "status": target},
        )
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["error"]["code"] == "ERR-STATE-TRANSITION"

    with case["database"].get_session() as session:
        assert session.get(AccountingPeriod, period["id"]).status == "CLOSED"
