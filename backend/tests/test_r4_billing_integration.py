"""R4 foundation acceptance tests against the disposable PostgreSQL cluster."""
from datetime import UTC, date, datetime
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.security import create_token
from app.models.account import Account, AccountRole
from app.models.billing import (
    AccountingPeriod,
    ArLedgerEntry,
    BillingAccount,
    BillingInvoice,
    BillingRun,
    FeePolicy,
    FeePolicyVersion,
    Payment,
    PaymentAllocation,
)
from app.models.building import Building
from app.models.platform import AuditEvent, IdempotencyRecord
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit
from test_r2_integration import r2_case, with_key


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R4 tests require its disposable PostgreSQL cluster",
)]


def _auth(case, account, site_id):
    token = create_token({
        "sub": str(account.id),
        "active_site_id": str(site_id),
        "purpose": "session",
    }, case["settings"].auth_secret())
    return {"Authorization": "Bearer " + token}


@pytest.fixture(scope="module")
def billing_case(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        accounts = []
        periods = []
        for index, (site, building, unit) in enumerate(zip(
            case["sites"], case["buildings"], case["units"], strict=True,
        ), 1):
            account = BillingAccount(
                tenant_id=case["tenant"].id,
                site_id=site.id,
                building_id=building.id,
                unit_id=unit.id,
                account_number=f"R4-BA-{index}-{uuid4().hex[:8]}",
                opened_on=date(2026, 1, 1),
            )
            period = AccountingPeriod(
                tenant_id=case["tenant"].id,
                site_id=site.id,
                building_id=building.id,
                period_key=f"R4-2026-09-{uuid4().hex[:8]}",
                period_start=date(2026, 9, 1),
                period_end=date(2026, 9, 30),
            )
            session.add_all((account, period))
            accounts.append(account)
            periods.append(period)
        session.flush()
        east_accountant = Account(
            tenant_id=case["tenant"].id,
            username=f"r4_accountant_east_{uuid4().hex}",
            full_name="R4 accountant east",
            hashed_password=case["accounts"]["accountant"].hashed_password,
        )
        session.add(east_accountant)
        session.flush()
        session.add(AccountRole(
            account_id=east_accountant.id,
            role="accountant",
            site_id=case["sites"][1].id,
            building_id=None,
        ))
        policy = FeePolicy(
            tenant_id=case["tenant"].id,
            site_id=case["sites"][0].id,
            building_id=case["buildings"][0].id,
            code=f"R4-POLICY-{uuid4().hex[:8]}",
            name="R4 policy",
        )
        session.add(policy)
        session.flush()
        policy_version = FeePolicyVersion(
            tenant_id=policy.tenant_id,
            site_id=policy.site_id,
            building_id=policy.building_id,
            fee_policy_id=policy.id,
            version_number=1,
            effective_from=date(2026, 1, 1),
            unit_rate_vnd=0,
        )
        session.add(policy_version)
        session.flush()
        run = BillingRun(
            tenant_id=policy.tenant_id,
            site_id=policy.site_id,
            building_id=policy.building_id,
            accounting_period_id=periods[0].id,
            fee_policy_version_id=policy_version.id,
            run_key=f"R4-RUN-{uuid4().hex}",
        )
        session.add(run)
        session.flush()
        invoice = BillingInvoice(
            tenant_id=policy.tenant_id,
            site_id=policy.site_id,
            building_id=policy.building_id,
            billing_account_id=accounts[0].id,
            billing_run_id=run.id,
            accounting_period_id=periods[0].id,
            invoice_number=f"R4-INV-{uuid4().hex}",
            status="ISSUED",
            total_vnd=150000,
            outstanding_vnd=150000,
        )
        session.add(invoice)
        session.commit()
    case["auth"]["accountant_east"] = _auth(case, east_accountant, case["sites"][1].id)
    return case | {"billing_accounts": accounts, "periods": periods, "invoice": invoice}


def test_r4_billing_account_read_is_server_scoped(billing_case):
    case = billing_case
    west_account = case["billing_accounts"][0]
    listed = case["client"].get("/api/v1/billing/accounts", headers=case["auth"]["accountant"])
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [str(west_account.id)]
    assert case["client"].get("/api/v1/billing/accounts", headers=case["auth"]["cskh"]).status_code == 403
    hidden = case["client"].get(
        f"/api/v1/billing/accounts/{west_account.id}",
        headers=case["auth"]["accountant_east"],
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"


def test_r4_scope_hides_billing_accounts_outside_tenant_site_or_building(billing_case):
    """R4 reads derive all three scope levels from the signed session."""
    case = billing_case
    with case["database"].get_session() as session:
        restricted = Account(
            tenant_id=case["tenant"].id,
            username=f"r4_building_scope_{uuid4().hex}",
            full_name="R4 building scoped accountant",
            hashed_password=case["accounts"]["accountant"].hashed_password,
        )
        other_building = Building(
            site_id=case["sites"][0].id,
            code=f"R4-B-{uuid4().hex[:8]}",
            name="R4 hidden building",
        )
        other_tenant = Tenant(name=f"R4 other tenant {uuid4()}")
        session.add_all((restricted, other_building, other_tenant))
        session.flush()
        session.add(AccountRole(
            account_id=restricted.id,
            role="accountant",
            site_id=case["sites"][0].id,
            building_id=case["buildings"][0].id,
        ))
        other_building_unit = Unit(
            building_id=other_building.id,
            unit_number=f"R4-SCOPE-{uuid4().hex[:8]}",
            floor=99,
            area_m2=50,
            status="occupied",
        )
        other_site = Site(
            tenant_id=other_tenant.id,
            code=f"R4-S-{uuid4().hex[:8]}",
            name="R4 other site",
            address="Synthetic",
        )
        session.add_all((other_building_unit, other_site))
        session.flush()
        other_tenant_building = Building(
            site_id=other_site.id,
            code="R4-B1",
            name="R4 other tenant building",
        )
        session.add(other_tenant_building)
        session.flush()
        other_tenant_unit = Unit(
            building_id=other_tenant_building.id,
            unit_number="0101",
            floor=1,
            area_m2=50,
            status="occupied",
        )
        session.add(other_tenant_unit)
        session.flush()
        building_hidden_account = BillingAccount(
            tenant_id=case["tenant"].id,
            site_id=case["sites"][0].id,
            building_id=other_building.id,
            unit_id=other_building_unit.id,
            account_number=f"R4-BUILDING-{uuid4().hex[:8]}",
            opened_on=date(2026, 1, 1),
        )
        tenant_hidden_account = BillingAccount(
            tenant_id=other_tenant.id,
            site_id=other_site.id,
            building_id=other_tenant_building.id,
            unit_id=other_tenant_unit.id,
            account_number=f"R4-TENANT-{uuid4().hex[:8]}",
            opened_on=date(2026, 1, 1),
        )
        session.add_all((building_hidden_account, tenant_hidden_account))
        session.commit()

    restricted_headers = _auth(case, restricted, case["sites"][0].id)
    visible = case["client"].get(
        f"/api/v1/billing/accounts/{case['billing_accounts'][0].id}",
        headers=restricted_headers,
    )
    assert visible.status_code == 200
    outside_scope = (
        (case["auth"]["accountant_east"], case["billing_accounts"][0].id),
        (restricted_headers, building_hidden_account.id),
        (case["auth"]["accountant"], tenant_hidden_account.id),
    )
    for headers, account_id in outside_scope:
        hidden = case["client"].get(f"/api/v1/billing/accounts/{account_id}", headers=headers)
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"


def test_r4_payment_deduplicates_source_and_receipt_and_writes_immutable_ledger_and_audit(billing_case):
    case = billing_case
    body = {
        "billing_account_id": str(case["billing_accounts"][0].id),
        "accounting_period_id": str(case["periods"][0].id),
        "payment_source": "BANK_TRANSFER",
        "source_reference": f"bank-r4-{uuid4().hex}",
        "receipt_number": f"receipt-r4-{uuid4().hex}",
        "amount_vnd": 120000,
        "received_at": datetime.now(UTC).isoformat(),
    }
    created = case["client"].post(
        "/api/v1/billing/payments",
        headers=with_key(case, "accountant", "r4-payment-receive-001"),
        json=body,
    )
    assert created.status_code == 201, created.text
    replayed = case["client"].post(
        "/api/v1/billing/payments",
        headers=with_key(case, "accountant", "r4-payment-receive-001"),
        json=body,
    )
    assert replayed.status_code == 201
    assert replayed.json() == created.json()

    source_duplicate = case["client"].post(
        "/api/v1/billing/payments",
        headers=with_key(case, "accountant", "r4-payment-receive-002"),
        json=body | {"receipt_number": f"receipt-r4-{uuid4().hex}"},
    )
    assert source_duplicate.status_code == 409
    assert source_duplicate.json()["error"]["code"] == "ERR-DUPLICATE-PAYMENT"
    receipt_duplicate = case["client"].post(
        "/api/v1/billing/payments",
        headers=with_key(case, "accountant", "r4-payment-receive-003"),
        json=body | {"source_reference": f"bank-r4-{uuid4().hex}"},
    )
    assert receipt_duplicate.status_code == 409
    assert receipt_duplicate.json()["error"]["code"] == "ERR-DUPLICATE-PAYMENT"

    payment_id = created.json()["id"]
    with case["database"].get_session() as session:
        payment = session.scalar(select(Payment).where(Payment.id == payment_id))
        ledger = session.scalar(select(ArLedgerEntry).where(
            ArLedgerEntry.source_type == "PAYMENT",
            ArLedgerEntry.source_id == payment.id,
        ))
        audit = session.scalar(select(AuditEvent).where(
            AuditEvent.resource_type == "Payment",
            AuditEvent.resource_id == payment.id,
            AuditEvent.event_type == "PaymentReceived",
        ))
        assert ledger is not None and ledger.debit_vnd == 0 and ledger.credit_vnd == 120000
        assert audit is not None
        assert session.scalar(select(IdempotencyRecord.id).where(
            IdempotencyRecord.resource_id == payment.id,
            IdempotencyRecord.operation == "billing-payment.receive",
        )) is not None
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.add(PaymentAllocation(
                    tenant_id=payment.tenant_id,
                    site_id=payment.site_id,
                    building_id=payment.building_id,
                    payment_id=payment.id,
                    billing_invoice_id=case["invoice"].id,
                    amount_vnd=120001,
                    allocated_by_id=case["accounts"]["accountant"].id,
                ))
                session.flush()
        allocation = PaymentAllocation(
            tenant_id=payment.tenant_id,
            site_id=payment.site_id,
            building_id=payment.building_id,
            payment_id=payment.id,
            billing_invoice_id=case["invoice"].id,
            amount_vnd=120000,
            allocated_by_id=case["accounts"]["accountant"].id,
        )
        session.add(allocation)
        session.commit()
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text("UPDATE greencity.ar_ledger_entries SET credit_vnd=1 WHERE id=:id"), {"id": ledger.id})
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text("DELETE FROM greencity.ar_ledger_entries WHERE id=:id"), {"id": ledger.id})
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text("UPDATE greencity.audit_events SET reason='tampered' WHERE id=:id"), {"id": audit.id})
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text("DELETE FROM greencity.audit_events WHERE id=:id"), {"id": audit.id})
