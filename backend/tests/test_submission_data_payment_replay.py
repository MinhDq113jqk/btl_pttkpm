"""FCS-16 payment replay and AR reconciliation checks."""

from datetime import UTC, date, datetime
import os
from uuid import uuid4

import pytest
from sqlalchemy import select

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
    OverpaymentCredit,
    UnmatchedPayment,
)
from app.models.submission_import import SubmissionImportRun
from app.models.unit import Unit
from app.services.submission_data_operational_replay import OperationalReplayError, replay_payment_allocations
from test_r2_integration import r2_case


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; FCS-16 requires disposable PostgreSQL",
)]


def test_fcs16_replays_allocated_partial_overpaid_unmatched_and_is_idempotent(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        tenant = session.get(type(case["tenant"]), case["tenant"].id)
        site = session.get(type(case["sites"][0]), case["sites"][0].id)
        building = session.get(type(case["buildings"][0]), case["buildings"][0].id)
        accountant = session.get(type(case["accounts"]["accountant"]), case["accounts"]["accountant"].id)
        extra_units = [
            Unit(building_id=building.id, unit_number=f"FCS16-0{index}", floor=1,
                 area_m2=50, status="occupied")
            for index in (3, 4, 5)
        ]
        session.add_all(extra_units)
        session.flush()
        # r2_case's second fixture unit belongs to the other building; keep all
        # payment accounts inside the single building under test.
        units = [case["units"][0], *extra_units]
        tenant.code = tenant.code or f"FCS16-T-{uuid4().hex[:8]}"
        site.code = site.code or f"FCS16-S-{uuid4().hex[:8]}"
        building.code = building.code or f"FCS16-B-{uuid4().hex[:8]}"
        period = AccountingPeriod(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            period_key="2026-08", period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            cutoff_at=datetime(2026, 8, 20, tzinfo=UTC), status="OPEN",
        )
        policy = FeePolicy(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            code="FCS16-POLICY", name="Synthetic FCS16 policy", is_active=True,
        )
        session.add_all((period, policy))
        session.flush()
        version = FeePolicyVersion(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            fee_policy_id=policy.id, version_number=1, effective_from=date(2026, 8, 1),
            unit_rate_vnd=1, rounding_unit_vnd=1, published_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
        session.add(version)
        session.flush()
        run = BillingRun(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            accounting_period_id=period.id, fee_policy_version_id=version.id,
            run_key="FCS16-BILLING-RUN", cutoff_at=period.cutoff_at, status="POSTED",
        )
        session.add(run)
        session.flush()

        accounts = []
        invoices = []
        oracle = []
        payments = []
        for index, (account_number, unit, total, invoice_number) in enumerate((
            ("FCS16-A", units[0], 100_000, "FCS16-INV-A"),
            ("FCS16-B", units[1], 200_000, "FCS16-INV-B"),
            ("FCS16-C", units[2], 100_000, "FCS16-INV-C"),
            ("FCS16-D", units[3], 75_000, "FCS16-INV-D"),
        ), 1):
            account = BillingAccount(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
                account_number=account_number, status="ACTIVE", opened_on=date(2026, 1, 1),
            )
            session.add(account)
            session.flush()
            invoice = BillingInvoice(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                billing_account_id=account.id, billing_run_id=run.id, accounting_period_id=period.id,
                invoice_number=invoice_number, issued_on=date(2026, 8, 1), due_on=date(2026, 8, 15),
                status="ISSUED", total_vnd=total, outstanding_vnd=total,
            )
            session.add(invoice)
            session.flush()
            session.add(ArLedgerEntry(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                billing_account_id=account.id, accounting_period_id=period.id,
                entry_type="INVOICE_ISSUED", source_type="BILLING_INVOICE", source_id=invoice.id,
                debit_vnd=total, credit_vnd=0, effective_at=datetime(2026, 8, 1, tzinfo=UTC),
            ))
            accounts.append(account)
            invoices.append(invoice)
        session.flush()
        import_run = SubmissionImportRun(
            manifest_sha256=uuid4().hex + uuid4().hex, schema_version="fcs16-test", stage="replay",
            status="APPLYING", correlation_id=uuid4(), workbook_count=12, total_rows=4,
        )
        session.add(import_run)
        session.flush()

        def payment_row(account_number, invoice_number, status, amount, allocated, overpayment, suffix):
            return {
                "source_reference": f"FCS16-SOURCE-{suffix}",
                "receipt_number": f"FCS16-RECEIPT-{suffix}",
                "payment_source": "BANK_TRANSFER",
                "tenant_code": tenant.code,
                "site_code": site.code,
                "building_code": building.code,
                "billing_account_number": account_number,
                "received_at": datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
                "amount_vnd": amount,
                "status": status,
                "matched_invoice_number": invoice_number,
                "allocated_vnd": allocated,
                "unmatched_reason": None,
                "overpayment_vnd": overpayment,
                "received_by_username": accountant.username,
            }

        payments = [
            payment_row("FCS16-A", "FCS16-INV-A", "ALLOCATED", 100_000, 100_000, 0, "A"),
            payment_row("FCS16-B", "FCS16-INV-B", "PARTIALLY_ALLOCATED", 50_000, 50_000, 0, "B"),
            payment_row("FCS16-C", "FCS16-INV-C", "OVERPAID", 150_000, 100_000, 50_000, "C"),
            {
                "source_reference": "FCS16-SOURCE-D",
                "receipt_number": "FCS16-RECEIPT-D",
                "payment_source": "CASH",
                "tenant_code": tenant.code,
                "site_code": site.code,
                "building_code": building.code,
                "billing_account_number": None,
                "received_at": datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
                "amount_vnd": 25_000,
                "status": "UNMATCHED",
                "matched_invoice_number": None,
                "allocated_vnd": 0,
                "unmatched_reason": "No account reference in approved source.",
                "overpayment_vnd": 0,
                "received_by_username": accountant.username,
            },
        ]
        invoice_rows = [
            {"invoice_number": "FCS16-INV-A", "billing_account_number": "FCS16-A", "tenant_code": tenant.code, "site_code": site.code, "building_code": building.code, "unit_number": units[0].unit_number, "period_key": "2026-08", "invoice_status": "PAID", "outstanding_vnd": 0},
            {"invoice_number": "FCS16-INV-B", "billing_account_number": "FCS16-B", "tenant_code": tenant.code, "site_code": site.code, "building_code": building.code, "unit_number": units[1].unit_number, "period_key": "2026-08", "invoice_status": "PARTIALLY_PAID", "outstanding_vnd": 150_000},
            {"invoice_number": "FCS16-INV-C", "billing_account_number": "FCS16-C", "tenant_code": tenant.code, "site_code": site.code, "building_code": building.code, "unit_number": units[2].unit_number, "period_key": "2026-08", "invoice_status": "PAID", "outstanding_vnd": 0},
            {"invoice_number": "FCS16-INV-D", "billing_account_number": "FCS16-D", "tenant_code": tenant.code, "site_code": site.code, "building_code": building.code, "unit_number": units[3].unit_number, "period_key": "2026-08", "invoice_status": "ISSUED", "outstanding_vnd": 75_000},
        ]
        policy_rows = [{
            "fee_policy_code": policy.code, "fee_policy_name": policy.name,
            "tenant_code": tenant.code, "site_code": site.code, "building_code": building.code,
            "version_number": 1, "period_key": "2026-08",
        }]
        first = replay_payment_allocations(
            session, payments, invoice_rows, policy_rows, import_run,
            as_of_utc=datetime(2026, 8, 31, tzinfo=UTC),
        )
        second = replay_payment_allocations(
            session, payments, invoice_rows, policy_rows, import_run,
            as_of_utc=datetime(2026, 8, 31, tzinfo=UTC),
        )
        assert first["payment_rows"] == 4
        assert first["payments_created"] == 4
        assert first["unmatched_count"] == 1
        assert first["overpaid_count"] == 1
        assert first["ar_delta_vnd"] == 0
        assert second["payments_replayed"] == 4
        assert session.scalar(select(Payment).where(
            Payment.tenant_id == tenant.id,
            Payment.source_reference == "FCS16-SOURCE-A",
        )) is not None
        assert len(session.scalars(select(PaymentAllocation).where(
            PaymentAllocation.tenant_id == tenant.id,
        )).all()) == 3
        assert len(session.scalars(select(OverpaymentCredit).where(
            OverpaymentCredit.tenant_id == tenant.id,
        )).all()) == 1
        assert len(session.scalars(select(UnmatchedPayment).where(
            UnmatchedPayment.tenant_id == tenant.id,
        )).all()) == 1
        assert [invoice.status for invoice in invoices] == ["PAID", "PARTIALLY_PAID", "PAID", "ISSUED"]
        with pytest.raises(OperationalReplayError, match="PAYMENT_ORACLE_INVOICE_DUPLICATE"):
            replay_payment_allocations(
                session, payments, [*invoice_rows, invoice_rows[0]], policy_rows,
                import_run, as_of_utc=datetime(2026, 8, 31, tzinfo=UTC),
            )
        altered = [dict(payments[0], received_at=datetime(2026, 8, 21, 10, 0, tzinfo=UTC)), *payments[1:]]
        with pytest.raises(OperationalReplayError, match="PAYMENT_ORACLE_RETRY_CONFLICT"):
            replay_payment_allocations(
                session, altered, invoice_rows, policy_rows,
                import_run, as_of_utc=datetime(2026, 8, 31, tzinfo=UTC),
            )
        session.commit()
