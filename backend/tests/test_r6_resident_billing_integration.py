"""Resident billing read acceptance tests for the disposable PostgreSQL cluster."""
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
import os
import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Database
from app.core.security import create_token, hash_password
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
)
from app.models.building import Building
from app.models.person import Person, UnitPersonRelationship
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; resident billing requires its disposable PostgreSQL cluster",
)]

ISSUED_AT = datetime(2026, 1, 10, 0, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 1, 12, 13, tzinfo=UTC)


def _headers(case, actor: str) -> dict[str, str]:
    return case["auth"][actor].copy()


def _scope_error(response) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"


def _create_billing_records(session, *, tenant, site, building, unit, prefix: str):
    """Create a complete R4 chain so the read API only uses durable sources."""
    account = BillingAccount(
        tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
        account_number=f"{prefix}-BA-{uuid4().hex[:8]}", opened_on=date(2026, 1, 1),
    )
    policy = FeePolicy(
        tenant_id=tenant.id, site_id=site.id, building_id=building.id,
        code=f"{prefix}-{uuid4().hex[:8]}", name=f"{prefix} policy",
    )
    session.add_all((account, policy))
    session.flush()
    version = FeePolicyVersion(
        tenant_id=tenant.id, site_id=site.id, building_id=building.id, fee_policy_id=policy.id,
        version_number=1, effective_from=date(2026, 1, 1), unit_rate_vnd=2500,
        rounding_unit_vnd=1, published_at=ISSUED_AT,
    )
    period = AccountingPeriod(
        tenant_id=tenant.id, site_id=site.id, building_id=building.id,
        period_key=f"2026-01-{uuid4().hex[:8]}", period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31), cutoff_at=ISSUED_AT, status="OPEN",
    )
    session.add_all((version, period))
    session.flush()
    run = BillingRun(
        tenant_id=tenant.id, site_id=site.id, building_id=building.id,
        accounting_period_id=period.id, fee_policy_version_id=version.id,
        run_key=f"{prefix}-RUN-{uuid4().hex}", status="POSTED", cutoff_at=ISSUED_AT,
    )
    session.add(run)
    session.flush()
    invoice = BillingInvoice(
        tenant_id=tenant.id, site_id=site.id, building_id=building.id,
        billing_account_id=account.id, billing_run_id=run.id, accounting_period_id=period.id,
        invoice_number=f"{prefix}-INV-{uuid4().hex[:8]}", issued_on=ISSUED_AT.date(),
        due_on=date(2026, 1, 31), status="ISSUED", total_vnd=125_000,
        # Deliberately unlike either historical ledger balance.  The resident
        # summary must therefore not accidentally use this current snapshot.
        outstanding_vnd=17,
    )
    session.add(invoice)
    session.flush()
    item = BillingInvoiceItem(
        tenant_id=tenant.id, site_id=site.id, building_id=building.id,
        billing_invoice_id=invoice.id, fee_policy_version_id=version.id, line_number=1,
        description="Unit area fee", basis="UNIT_AREA_M2", basis_quantity=Decimal("50.00"),
        unit_rate_vnd_snapshot=2500, rounding_unit_vnd_snapshot=1, amount_vnd=125_000,
    )
    payment = Payment(
        tenant_id=tenant.id, site_id=site.id, building_id=building.id,
        billing_account_id=account.id, accounting_period_id=period.id,
        payment_source="BANK_TRANSFER", source_reference=f"{prefix}-REF-{uuid4().hex[:8]}",
        receipt_number=f"{prefix}-RCPT-{uuid4().hex[:8]}", amount_vnd=25_000,
        received_at=RECEIVED_AT, status="RECEIVED",
    )
    session.add_all((item, payment))
    session.flush()
    session.add_all((
        ArLedgerEntry(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            billing_account_id=account.id, accounting_period_id=period.id,
            entry_type="INVOICE_ISSUED", source_type="INVOICE", source_id=invoice.id,
            debit_vnd=125_000, credit_vnd=0, effective_at=ISSUED_AT,
        ),
        ArLedgerEntry(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            billing_account_id=account.id, accounting_period_id=period.id,
            entry_type="PAYMENT_RECEIVED", source_type="PAYMENT", source_id=payment.id,
            debit_vnd=0, credit_vnd=25_000, effective_at=RECEIVED_AT,
        ),
    ))
    return {"account": account, "period": period, "invoice": invoice, "payment": payment}


@pytest.fixture(scope="module")
def resident_billing_case():
    settings = Settings()
    assert settings.app_env == "test"
    assert settings.sqlalchemy_url().host == "127.0.0.1"
    database = Database(settings)
    connection = database.engine.connect()
    transaction = connection.begin()
    database.sessions = sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint",
    )
    password = secrets.token_urlsafe(24)
    with database.get_session() as session:
        tenant = Tenant(name=f"R6 resident billing {uuid4()}")
        foreign_tenant = Tenant(name=f"R6 resident billing foreign {uuid4()}")
        session.add_all((tenant, foreign_tenant))
        session.flush()
        site = Site(tenant_id=tenant.id, code=f"R6-B-{uuid4().hex[:8]}",
                    name="Billing home", address="Synthetic")
        other_site = Site(tenant_id=tenant.id, code=f"R6-O-{uuid4().hex[:8]}",
                          name="Billing other", address="Synthetic")
        foreign_site = Site(tenant_id=foreign_tenant.id, code=f"R6-F-{uuid4().hex[:8]}",
                            name="Billing foreign", address="Synthetic")
        session.add_all((site, other_site, foreign_site))
        session.flush()
        building = Building(site_id=site.id, code="R6-B1", name="Billing home")
        other_building = Building(site_id=site.id, code="R6-B2", name="Billing nearby")
        other_site_building = Building(site_id=other_site.id, code="R6-O1", name="Billing other site")
        foreign_building = Building(site_id=foreign_site.id, code="R6-F1", name="Billing foreign")
        session.add_all((building, other_building, other_site_building, foreign_building))
        session.flush()
        unit = Unit(building_id=building.id, unit_number="R6-0101", floor=1, area_m2=50, status="occupied")
        other_unit = Unit(building_id=other_building.id, unit_number="R6-0201", floor=2, area_m2=50, status="occupied")
        other_site_unit = Unit(building_id=other_site_building.id, unit_number="R6-O-0101", floor=1,
                               area_m2=50, status="occupied")
        foreign_unit = Unit(building_id=foreign_building.id, unit_number="R6-F-0101", floor=1,
                            area_m2=50, status="occupied")
        session.add_all((unit, other_unit, other_site_unit, foreign_unit))
        session.flush()

        residents = {}
        for label, resident_unit in (("resident", unit), ("other_resident", other_unit), ("revoked", unit)):
            person = Person(
                tenant_id=tenant.id, full_name=f"R6 {label}", phone_masked="***",
                email_masked=f"{label}@example.invalid",
            )
            session.add(person)
            session.flush()
            account = Account(
                tenant_id=tenant.id, username=f"r6_billing_{label}_{uuid4().hex}",
                full_name=f"R6 {label}", hashed_password=hash_password(password), person_id=person.id,
            )
            session.add(account)
            session.flush()
            session.add_all((
                AccountRole(account_id=account.id, role="resident", site_id=site.id, building_id=building.id),
                UnitPersonRelationship(
                    tenant_id=tenant.id, site_id=site.id, building_id=resident_unit.building_id,
                    unit_id=resident_unit.id, person_id=person.id,
                    relationship_type="family_member" if label == "revoked" else "owner",
                    ownership_ratio=None if label == "revoked" else Decimal("1.0000"),
                    valid_from=date(2025, 1, 1),
                ),
            ))
            residents[label] = (account, person)

        staff = Account(
            tenant_id=tenant.id, username=f"r6_billing_staff_{uuid4().hex}", full_name="R6 staff",
            hashed_password=hash_password(password),
        )
        session.add(staff)
        session.flush()
        session.add(AccountRole(account_id=staff.id, role="accountant", site_id=site.id, building_id=building.id))

        records = {
            "resident": _create_billing_records(
                session, tenant=tenant, site=site, building=building, unit=unit, prefix="R6-OWN",
            ),
            "other_building": _create_billing_records(
                session, tenant=tenant, site=site, building=other_building, unit=other_unit, prefix="R6-OTHER-B",
            ),
            "other_site": _create_billing_records(
                session, tenant=tenant, site=other_site, building=other_site_building,
                unit=other_site_unit, prefix="R6-OTHER-S",
            ),
            "foreign": _create_billing_records(
                session, tenant=foreign_tenant, site=foreign_site, building=foreign_building,
                unit=foreign_unit, prefix="R6-FOREIGN",
            ),
        }
        session.commit()

    with TestClient(create_app(settings, database)) as client:
        auth = {}
        for label, (account, _) in residents.items():
            response = client.post("/api/v1/auth/login", json={
                "username": account.username, "password": password,
            })
            assert response.status_code == 200, response.text
            auth[label] = {"Authorization": "Bearer " + response.json()["access_token"]}
        response = client.post("/api/v1/auth/login", json={
            "username": staff.username, "password": password,
        })
        assert response.status_code == 200, response.text
        auth["staff"] = {"Authorization": "Bearer " + response.json()["access_token"]}
        yield {
            "client": client, "database": database, "settings": settings, "tenant": tenant,
            "site": site, "other_site": other_site, "unit": unit, "other_unit": other_unit,
            "residents": residents, "auth": auth, "records": records,
        }
    transaction.rollback()
    connection.close()
    database.close()


def _as_of(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def test_resident_billing_reads_invoice_payment_and_ledger_balance_at_one_cutoff(resident_billing_case):
    case = resident_billing_case
    before_payment = RECEIVED_AT - timedelta(seconds=1)
    after_payment = datetime(2026, 1, 13, 7, tzinfo=timezone(timedelta(hours=7)))
    expected_cutoff = after_payment.astimezone(UTC)

    before_summary = case["client"].get(
        "/api/v1/resident/billing/summary", headers=_headers(case, "resident"),
        params={"as_of": _as_of(before_payment)},
    )
    assert before_summary.status_code == 200, before_summary.text
    assert before_summary.json()["total_ar_balance_vnd"] == 125_000

    invoice_response = case["client"].get(
        "/api/v1/resident/billing/invoices", headers=_headers(case, "resident"),
        params={"as_of": _as_of(expected_cutoff)},
    )
    payment_response = case["client"].get(
        "/api/v1/resident/billing/payments", headers=_headers(case, "resident"),
        params={"as_of": _as_of(expected_cutoff)},
    )
    summary_response = case["client"].get(
        "/api/v1/resident/billing/summary", headers=_headers(case, "resident"),
        params={"as_of": _as_of(after_payment)},
    )
    for response in (invoice_response, payment_response, summary_response):
        assert response.status_code == 200, response.text
        assert datetime.fromisoformat(response.json()["as_of"].replace("Z", "+00:00")) == expected_cutoff

    own = case["records"]["resident"]
    invoices = invoice_response.json()["items"]
    assert invoices == [{
        "id": str(own["invoice"].id), "unit_id": str(case["unit"].id),
        "invoice_number": own["invoice"].invoice_number, "issued_on": "2026-01-10",
        "due_on": "2026-01-31", "total_vnd": 125_000,
        "items": [{
            "line_number": 1, "description": "Unit area fee", "basis": "UNIT_AREA_M2",
            "basis_quantity": 50.0, "unit_rate_vnd_snapshot": 2500,
            "rounding_unit_vnd_snapshot": 1, "amount_vnd": 125_000,
        }],
    }]
    payments = payment_response.json()["items"]
    assert payments == [{
        "id": str(own["payment"].id), "unit_id": str(case["unit"].id),
        "payment_source": "BANK_TRANSFER", "receipt_number": own["payment"].receipt_number,
        "amount_vnd": 25_000, "received_at": _as_of(RECEIVED_AT),
    }]
    assert "billing_account_id" not in invoices[0]
    assert "source_reference" not in payments[0]
    assert summary_response.json() == {
        "as_of": _as_of(expected_cutoff), "total_ar_balance_vnd": 100_000,
        "items": [{"unit_id": str(case["unit"].id), "ar_balance_vnd": 100_000}],
    }

    # The API value is checked against an independent direct-SQL ledger oracle,
    # not BillingInvoice.outstanding_vnd (which is intentionally 17 above).
    with case["database"].get_session() as session:
        oracle = session.scalar(select(func.coalesce(func.sum(
            ArLedgerEntry.debit_vnd - ArLedgerEntry.credit_vnd,
        ), 0)).where(
            ArLedgerEntry.billing_account_id == own["account"].id,
            ArLedgerEntry.effective_at <= expected_cutoff,
        ))
    assert summary_response.json()["total_ar_balance_vnd"] == int(oracle) == 100_000


def test_resident_billing_enforces_server_derived_unit_scope_and_read_only_surface(resident_billing_case):
    case = resident_billing_case
    cutoff = _as_of(datetime(2026, 1, 13, tzinfo=UTC))
    own_invoice_id = str(case["records"]["resident"]["invoice"].id)
    other_invoice_id = str(case["records"]["other_building"]["invoice"].id)
    hidden_invoice_ids = {
        str(case["records"]["other_site"]["invoice"].id),
        str(case["records"]["foreign"]["invoice"].id),
    }

    resident_invoices = case["client"].get(
        "/api/v1/resident/billing/invoices", headers=_headers(case, "resident"), params={"as_of": cutoff},
    )
    assert resident_invoices.status_code == 200
    assert [item["id"] for item in resident_invoices.json()["items"]] == [own_invoice_id]
    assert not hidden_invoice_ids.intersection(item["id"] for item in resident_invoices.json()["items"])

    other_invoices = case["client"].get(
        "/api/v1/resident/billing/invoices", headers=_headers(case, "other_resident"), params={"as_of": cutoff},
    )
    assert other_invoices.status_code == 200
    assert [item["id"] for item in other_invoices.json()["items"]] == [other_invoice_id]
    assert own_invoice_id not in [item["id"] for item in other_invoices.json()["items"]]

    assert case["client"].get(
        "/api/v1/resident/billing/summary", headers=_headers(case, "staff"), params={"as_of": cutoff},
    ).status_code == 403
    write_attempt = case["client"].post(
        "/api/v1/billing/payments", headers=_headers(case, "resident") | {"Idempotency-Key": "resident-no-write"},
        json={
            "billing_account_id": str(case["records"]["resident"]["account"].id),
            "accounting_period_id": str(case["records"]["resident"]["period"].id),
            "payment_source": "CASH", "source_reference": "resident-attempt",
            "receipt_number": "resident-attempt", "amount_vnd": 1,
            "received_at": _as_of(datetime(2026, 1, 13, tzinfo=UTC)),
        },
    )
    assert write_attempt.status_code == 403, write_attempt.text


def test_resident_billing_rejects_invalid_or_revoked_scope(resident_billing_case):
    case = resident_billing_case
    cutoff = _as_of(datetime(2026, 1, 13, tzinfo=UTC))
    missing = case["client"].get("/api/v1/resident/billing/summary", headers=_headers(case, "resident"))
    assert missing.status_code == 422
    naive = case["client"].get(
        "/api/v1/resident/billing/summary", headers=_headers(case, "resident"),
        params={"as_of": "2026-01-13T00:00:00"},
    )
    assert naive.status_code == 422
    assert naive.json()["error"]["code"] == "ERR-AS-OF-TIMEZONE"

    forged_tenant_and_roles = create_token({
        "sub": str(case["residents"]["resident"][0].id), "tenant_id": str(uuid4()),
        "roles": ["admin", "resident"], "active_site_id": str(case["site"].id), "purpose": "session",
    }, case["settings"].auth_secret())
    forged_allowed = case["client"].get(
        "/api/v1/resident/billing/summary", headers={"Authorization": "Bearer " + forged_tenant_and_roles},
        params={"as_of": cutoff},
    )
    assert forged_allowed.status_code == 200
    assert forged_allowed.json()["total_ar_balance_vnd"] == 100_000

    forged_site = create_token({
        "sub": str(case["residents"]["resident"][0].id), "tenant_id": str(case["tenant"].id),
        "roles": ["resident"], "active_site_id": str(case["other_site"].id), "purpose": "session",
    }, case["settings"].auth_secret())
    _scope_error(case["client"].get(
        "/api/v1/resident/billing/summary", headers={"Authorization": "Bearer " + forged_site},
        params={"as_of": cutoff},
    ))

    with case["database"].get_session() as session:
        _, person = case["residents"]["revoked"]
        relationship = session.scalar(select(UnitPersonRelationship).where(
            UnitPersonRelationship.person_id == person.id,
            UnitPersonRelationship.unit_id == case["unit"].id,
        ))
        assert relationship is not None
        session.delete(relationship)
        session.commit()
    _scope_error(case["client"].get(
        "/api/v1/resident/billing/summary", headers=_headers(case, "revoked"), params={"as_of": cutoff},
    ))
