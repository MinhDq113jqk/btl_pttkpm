"""R4 Task 3 acceptance tests: receipts, matching, allocation and credit."""
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
    BillingRun,
    FeePolicy,
    FeePolicyVersion,
    OverpaymentCredit,
    Payment,
    PaymentAllocation,
    UnmatchedPayment,
)
from app.models.building import Building
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit
from test_r2_integration import r2_case, with_key


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R4 payment tests require its disposable PostgreSQL cluster",
)]


@pytest.fixture(scope="module")
def payment_case(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        account = BillingAccount(
            tenant_id=case["tenant"].id,
            site_id=case["sites"][0].id,
            building_id=case["buildings"][0].id,
            unit_id=case["units"][0].id,
            account_number=f"R4-PAY-{uuid4().hex[:12]}",
            opened_on=date(2026, 1, 1),
        )
        session.add(account)
        session.commit()
    return case | {"billing_account": account}


def _invoice_set(case, amounts: tuple[int, ...] = (50_000, 50_000)):
    """Create open invoice snapshots with deterministic due-date order."""
    with case["database"].get_session() as session:
        building = case["buildings"][0]
        unit = Unit(
            building_id=building.id, unit_number=f"PAY-{uuid4().hex[:10]}", floor=99,
            area_m2=50, status="occupied",
        )
        session.add(unit)
        session.flush()
        account = BillingAccount(
            tenant_id=case["tenant"].id, site_id=case["sites"][0].id, building_id=building.id,
            unit_id=unit.id, account_number=f"R4-PAY-{uuid4().hex[:12]}", opened_on=date(2026, 1, 1),
        )
        session.add(account)
        session.flush()
        policy = FeePolicy(
            tenant_id=account.tenant_id,
            site_id=account.site_id,
            building_id=account.building_id,
            code=f"PAY-{uuid4().hex[:10].upper()}",
            name="Payment acceptance policy",
        )
        session.add(policy)
        session.flush()
        version = FeePolicyVersion(
            tenant_id=account.tenant_id,
            site_id=account.site_id,
            building_id=account.building_id,
            fee_policy_id=policy.id,
            version_number=1,
            effective_from=date(2026, 1, 1),
            unit_rate_vnd=0,
            rounding_unit_vnd=1,
        )
        session.add(version)
        invoices = []
        periods = []
        for index, amount in enumerate(amounts, 1):
            period = AccountingPeriod(
                tenant_id=account.tenant_id,
                site_id=account.site_id,
                building_id=account.building_id,
                period_key=f"PAY-{uuid4().hex[:12]}",
                period_start=date(2030, index, 1),
                period_end=date(2030, index, 28),
                cutoff_at=datetime(2030, index, 15, tzinfo=UTC),
            )
            session.add(period)
            session.flush()
            run = BillingRun(
                tenant_id=account.tenant_id,
                site_id=account.site_id,
                building_id=account.building_id,
                accounting_period_id=period.id,
                fee_policy_version_id=version.id,
                run_key=f"PAY-RUN-{uuid4().hex}",
                cutoff_at=period.cutoff_at,
                status="POSTED",
            )
            session.add(run)
            session.flush()
            invoice = BillingInvoice(
                tenant_id=account.tenant_id,
                site_id=account.site_id,
                building_id=account.building_id,
                billing_account_id=account.id,
                billing_run_id=run.id,
                accounting_period_id=period.id,
                invoice_number=f"PAY-INV-{index}-{uuid4().hex[:8]}",
                issued_on=period.period_end,
                due_on=period.period_end,
                status="ISSUED",
                total_vnd=amount,
                outstanding_vnd=amount,
            )
            session.add(invoice)
            invoices.append(invoice)
            periods.append(period)
        session.commit()
    return account, periods, invoices


def _receive(case, *, period_id, amount_vnd: int, suffix: str, billing_account_id=None, building_id=None):
    body = {
        "accounting_period_id": str(period_id),
        "payment_source": "BANK_TRANSFER",
        "source_reference": f"source-{suffix}-{uuid4().hex}",
        "receipt_number": f"receipt-{suffix}-{uuid4().hex}",
        "amount_vnd": amount_vnd,
        "received_at": datetime.now(UTC).isoformat(),
    }
    if billing_account_id is not None:
        body["billing_account_id"] = str(billing_account_id)
    else:
        body["building_id"] = str(building_id)
    response = case["client"].post("/api/v1/billing/payments", headers=with_key(
        case, "accountant", f"r4-pay-receive-{suffix}-{uuid4().hex[:8]}"), json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def test_ac17_ac44_auto_allocates_oldest_debt_partial_and_multi_invoice(payment_case):
    case = payment_case
    account, periods, invoices = _invoice_set(case)
    payment, _ = _receive(case, period_id=periods[0].id, amount_vnd=75_000, suffix="allocation",
                          billing_account_id=account.id)
    first = case["client"].post(f"/api/v1/billing/payments/{payment['id']}/allocate", headers=with_key(
        case, "accountant", "r4-pay-allocate-golden-001"))
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["payment"]["status"] == "ALLOCATED"
    assert [(item["billing_invoice_id"], item["amount_vnd"]) for item in result["allocations"]] == [
        (str(invoices[0].id), 50_000), (str(invoices[1].id), 25_000),
    ]
    replay = case["client"].post(f"/api/v1/billing/payments/{payment['id']}/allocate", headers=with_key(
        case, "accountant", "r4-pay-allocate-golden-001"))
    assert replay.status_code == 200 and replay.json() == result
    with case["database"].get_session() as session:
        stored = [session.get(BillingInvoice, invoice.id) for invoice in invoices]
        assert [(item.status, item.outstanding_vnd) for item in stored] == [("PAID", 0), ("PARTIALLY_PAID", 25_000)]
        ledger = session.scalar(select(ArLedgerEntry).where(
            ArLedgerEntry.source_type == "PAYMENT", ArLedgerEntry.source_id == payment["id"],
        ))
        assert ledger is not None and (ledger.debit_vnd, ledger.credit_vnd) == (0, 75_000)
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text("UPDATE greencity.ar_ledger_entries SET credit_vnd=1 WHERE id=:id"), {"id": ledger.id})

        next_payment = Payment(
            tenant_id=stored[1].tenant_id, site_id=stored[1].site_id, building_id=stored[1].building_id,
            billing_account_id=stored[1].billing_account_id, accounting_period_id=stored[1].accounting_period_id,
            payment_source="CASH", source_reference=f"direct-cap-{uuid4().hex}", receipt_number=f"direct-cap-{uuid4().hex}",
            amount_vnd=30_000, received_at=datetime.now(UTC), status="RECEIVED",
        )
        session.add(next_payment)
        session.flush()
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.add(PaymentAllocation(
                    tenant_id=next_payment.tenant_id, site_id=next_payment.site_id, building_id=next_payment.building_id,
                    payment_id=next_payment.id, billing_invoice_id=stored[1].id, amount_vnd=30_000,
                ))
                session.flush()
        session.rollback()


def test_ac18_unmatched_does_not_reduce_debt_until_scoped_match_then_allocation(payment_case):
    case = payment_case
    account, periods, invoices = _invoice_set(case, (50_000,))
    payment, _ = _receive(case, period_id=periods[0].id, amount_vnd=20_000, suffix="unmatched",
                          building_id=account.building_id)
    assert payment["status"] == "UNMATCHED" and payment["billing_account_id"] is None
    with case["database"].get_session() as session:
        unmatched = session.scalar(select(UnmatchedPayment).where(UnmatchedPayment.payment_id == payment["id"]))
        assert unmatched is not None and unmatched.status == "OPEN"
        assert session.scalar(select(ArLedgerEntry.id).where(ArLedgerEntry.source_id == payment["id"])) is None
        assert session.get(BillingInvoice, invoices[0].id).outstanding_vnd == 50_000
    match = case["client"].post(f"/api/v1/billing/unmatched-payments/{unmatched.id}/match", headers=with_key(
        case, "accountant", "r4-pay-match-unmatched-001"), json={"billing_account_id": str(account.id)})
    assert match.status_code == 200, match.text
    assert match.json()["status"] == "RECEIVED"
    allocated = case["client"].post(f"/api/v1/billing/payments/{payment['id']}/allocate", headers=with_key(
        case, "accountant", "r4-pay-allocate-unmatched-001"))
    assert allocated.status_code == 200 and allocated.json()["payment"]["status"] == "ALLOCATED"
    with case["database"].get_session() as session:
        assert session.get(UnmatchedPayment, unmatched.id).status == "RESOLVED"
        assert session.get(BillingInvoice, invoices[0].id).outstanding_vnd == 30_000
        assert session.scalar(select(ArLedgerEntry.id).where(
            ArLedgerEntry.source_type == "PAYMENT", ArLedgerEntry.source_id == payment["id"],
        )) is not None


def test_ac19_excess_is_a_separate_overpayment_credit_not_an_invoice_or_deposit(payment_case):
    case = payment_case
    account, periods, invoices = _invoice_set(case, (50_000,))
    payment, _ = _receive(case, period_id=periods[0].id, amount_vnd=80_000, suffix="credit",
                          billing_account_id=account.id)
    response = case["client"].post(f"/api/v1/billing/payments/{payment['id']}/allocate", headers=with_key(
        case, "accountant", "r4-pay-credit-001"))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["payment"]["status"] == "OVERPAID"
    assert result["overpayment_credit"]["original_vnd"] == result["overpayment_credit"]["remaining_vnd"] == 30_000
    assert len(result["allocations"]) == 1 and result["allocations"][0]["amount_vnd"] == 50_000
    with case["database"].get_session() as session:
        credit = session.scalar(select(OverpaymentCredit).where(OverpaymentCredit.payment_id == payment["id"]))
        assert credit is not None
        ledger = session.scalar(select(ArLedgerEntry).where(
            ArLedgerEntry.source_type == "OVERPAYMENT_CREDIT", ArLedgerEntry.source_id == credit.id,
        ))
        assert (ledger.debit_vnd, ledger.credit_vnd) == (30_000, 0)
        assert session.scalar(text("SELECT to_regclass('greencity.deposits')")) is None
        assert session.scalar(text("SELECT to_regclass('greencity.restricted_funds')")) is None


def test_payment_reconciliation_endpoints_require_accountant_scope(payment_case):
    case = payment_case
    for endpoint in ("/api/v1/billing/payments", "/api/v1/billing/unmatched-payments", "/api/v1/billing/overpayment-credits"):
        response = case["client"].get(endpoint, headers=case["auth"]["cskh"])
        assert response.status_code == 403


def test_ac30_two_accountants_with_different_idempotency_keys_create_one_payment():
    settings = Settings()
    database = Database(settings)
    app = create_app(settings, database)
    try:
        with database.get_session() as session:
            tenant = Tenant(name=f"R4 payment race {uuid4()}")
            session.add(tenant)
            session.flush()
            site = Site(tenant_id=tenant.id, code=f"P-{uuid4().hex[:8]}", name="Payment race", address="Synthetic")
            session.add(site)
            session.flush()
            building = Building(site_id=site.id, code="B1", name="Payment building")
            session.add(building)
            session.flush()
            unit = Unit(building_id=building.id, unit_number="0101", floor=1, area_m2=50, status="occupied")
            accountant = Account(tenant_id=tenant.id, username=f"payment_race_{uuid4().hex}",
                                full_name="Payment accountant", hashed_password="token-only-test-account")
            session.add_all((unit, accountant))
            session.flush()
            session.add(AccountRole(account_id=accountant.id, role="accountant", site_id=site.id, building_id=None))
            billing_account = BillingAccount(tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
                                             account_number=f"P-{uuid4().hex[:8]}", opened_on=date(2026, 1, 1))
            period = AccountingPeriod(tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                                      period_key=f"P-{uuid4().hex[:8]}", period_start=date(2030, 1, 1), period_end=date(2030, 1, 31),
                                      cutoff_at=datetime(2030, 1, 15, tzinfo=UTC))
            session.add_all((billing_account, period))
            session.commit()

        headers = {"Authorization": "Bearer " + create_token({
            "sub": str(accountant.id), "active_site_id": str(site.id), "purpose": "session",
        }, settings.auth_secret())}
        body = {
            "billing_account_id": str(billing_account.id), "accounting_period_id": str(period.id),
            "payment_source": "BANK_TRANSFER", "source_reference": f"race-source-{uuid4().hex}",
            "receipt_number": f"race-receipt-{uuid4().hex}", "amount_vnd": 20_000,
            "received_at": datetime.now(UTC).isoformat(),
        }
        barrier = Barrier(3, timeout=10)

        def receive(key: str):
            with TestClient(app) as client:
                barrier.wait()
                return client.post("/api/v1/billing/payments", headers=headers | {"Idempotency-Key": key}, json=body)

        with ThreadPoolExecutor(max_workers=2) as executor:
            pending = [executor.submit(receive, f"r4-pay-race-{suffix}-{uuid4().hex[:8]}") for suffix in ("a", "b")]
            barrier.wait()
            responses = [item.result(timeout=15) for item in pending]
        assert sorted(response.status_code for response in responses) == [201, 409]
        assert next(response for response in responses if response.status_code == 409).json()["error"]["code"] == "ERR-DUPLICATE-PAYMENT"
        with database.get_session() as session:
            assert len(session.scalars(select(Payment).where(Payment.source_reference == body["source_reference"])).all()) == 1
    finally:
        database.close()
