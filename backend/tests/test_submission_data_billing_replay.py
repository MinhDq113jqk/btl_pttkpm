"""FCS-15 Billing Run generation and oracle reconciliation checks."""

from datetime import UTC, date, datetime, timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.billing import (
    AccountingPeriod,
    BillingAccount,
    BillingInvoice,
    BillingInvoiceItem,
    BillingRun,
    FeePolicy,
    FeePolicyVersion,
)
from app.models.submission_import import SubmissionImportRun
from app.services.submission_data_operational_replay import replay_billing_run
from test_r2_integration import r2_case


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; FCS-15 requires disposable PostgreSQL",
)]


def test_fcs15_billing_run_uses_domain_service_and_is_safe_to_rerun(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        tenant = session.get(type(case["tenant"]), case["tenant"].id)
        tenant.code = tenant.code or f"R2-TENANT-{uuid4().hex[:8]}"
        site = session.get(type(case["sites"][0]), case["sites"][0].id)
        building = session.get(type(case["buildings"][0]), case["buildings"][0].id)
        accountant = session.get(type(case["accounts"]["accountant"]), case["accounts"]["accountant"].id)
        account = BillingAccount(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            unit_id=case["units"][0].id,
            account_number=f"FCS15-BA-{uuid4().hex[:8]}",
            status="ACTIVE",
            opened_on=date(2026, 1, 1),
        )
        policy = FeePolicy(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            code="FEE-R2",
            name="FCS15 synthetic fee",
            is_active=True,
        )
        period = AccountingPeriod(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            period_key="2026-10",
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            cutoff_at=datetime(2026, 10, 1, tzinfo=UTC),
            status="OPEN",
        )
        session.add_all([account, policy, period])
        session.flush()
        version = FeePolicyVersion(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            fee_policy_id=policy.id,
            version_number=1,
            effective_from=date(2026, 10, 1),
            unit_rate_vnd=12000,
            basis="UNIT_AREA_M2",
            rounding_unit_vnd=1000,
            published_at=datetime.now(UTC),
        )
        session.add(version)
        session.flush()
        run = SubmissionImportRun(
            manifest_sha256=uuid4().hex + uuid4().hex,
            schema_version="fcs-test",
            source_kind="synthetic",
            stage="replay",
            status="APPLYING",
            correlation_id=uuid4(),
            workbook_count=12,
            total_rows=1,
        )
        session.add(run)
        session.flush()
        amount = 600000
        invoice_rows = [{
            "invoice_number": "FCS15-INV-0001",
            "billing_account_number": account.account_number,
            "tenant_code": tenant.code,
            "site_code": site.code,
            "building_code": building.code,
            "unit_number": case["units"][0].unit_number,
            "period_key": period.period_key,
            "billing_run_key": "FCS15-RUN-2026-10",
            "policy_version": 1,
            "invoice_status": "ISSUED",
            "issued_on": date(2026, 10, 1),
            "due_on": date(2026, 10, 15),
            "total_vnd": amount,
            "outstanding_vnd": amount,
            "line_code": "FEE",
            "line_description": "FCS15 monthly fee",
            "basis_quantity": 50,
            "unit_rate_vnd_snapshot": 12000,
            "rounding_unit_vnd_snapshot": 1000,
            "amount_vnd": amount,
        }]
        policy_rows = [{
            "fee_policy_code": policy.code,
            "fee_policy_name": policy.name,
            "tenant_code": tenant.code,
            "site_code": site.code,
            "building_code": building.code,
            "version_number": 1,
            "effective_from": datetime(2026, 10, 1, tzinfo=UTC),
            "effective_to": None,
            "unit_rate_vnd": 12000,
            "basis": "UNIT_AREA_M2",
            "rounding_unit_vnd": 1000,
            "period_key": period.period_key,
        }]
        first = replay_billing_run(
            session,
            policy_rows,
            invoice_rows,
            run,
            as_of_utc=datetime(2026, 10, 31, tzinfo=UTC),
        )
        second = replay_billing_run(
            session,
            policy_rows,
            invoice_rows,
            run,
            as_of_utc=datetime(2026, 10, 31, tzinfo=UTC),
        )
        assert first["runs_created"] == 1
        assert first["invoice_count"] == 1
        assert first["invoice_item_count"] == 1
        assert first["status_pending_fcs16"] == 0
        assert second["runs_replayed"] == 1
        assert session.scalar(select(func.count(BillingRun.id)).where(BillingRun.run_key == "FCS15-RUN-2026-10")) == 1
        billing_run_id = session.scalar(select(BillingRun.id).where(BillingRun.run_key == "FCS15-RUN-2026-10"))
        invoice = session.scalar(select(BillingInvoice).where(BillingInvoice.billing_run_id == billing_run_id))
        assert invoice.invoice_number == "FCS15-INV-0001"
        assert invoice.issued_on == date(2026, 10, 1)
        assert invoice.due_on == date(2026, 10, 15)
        items = session.scalars(select(BillingInvoiceItem).where(BillingInvoiceItem.billing_invoice_id == invoice.id)).all()
        assert invoice.total_vnd == sum(item.amount_vnd for item in items) == amount
        assert items[0].fee_policy_version_id == version.id
        assert items[0].rounding_unit_vnd_snapshot == 1000
        assert invoice.status == "ISSUED" and invoice.outstanding_vnd == amount
        session.commit()
