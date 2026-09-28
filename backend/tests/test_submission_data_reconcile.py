"""Focused, synthetic checks for read-only submission-pack reconciliation."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts import submission_data_reconcile as reconcile


def _scoped_ids():
    tenant = SimpleNamespace(id=uuid4())
    site = SimpleNamespace(id=uuid4(), code="SYN-SITE")
    building = SimpleNamespace(id=uuid4())
    return tenant, site, building


def test_duplicate_invoice_oracle_fails_before_database_lookup():
    row = {"tenant_code": "SYN-TENANT", "site_code": "SYN-SITE", "invoice_number": "SYN-INV"}
    rows = defaultdict(list, {"10_hoa_don.xlsx": [row, dict(row)]})

    with pytest.raises(reconcile.ReconciliationError) as error:
        reconcile._finance(object(), rows, defaultdict(int))

    assert error.value.code == "RECONCILE_INVOICE_ORACLE_DUPLICATE"


def test_tenant_for_source_without_tenant_column_comes_from_structure(monkeypatch):
    tenant, site, building = _scoped_ids()
    site.tenant_id = tenant.id
    building.site_id = site.id
    targets = iter((tenant, site, building))
    monkeypatch.setattr(reconcile, "_one", lambda _session, _query, _code: next(targets))
    source = {"site_code": "SYN-SITE", "building_code": "SYN-BUILDING"}
    structure = [{**source, "tenant_code": "SYN-TENANT"}]

    assert reconcile._scope(object(), source, structure) == (tenant, site, building)
    with pytest.raises(reconcile.ReconciliationError) as error:
        reconcile._scope(object(), source, structure + [{**source, "tenant_code": "OTHER-TENANT"}])
    assert error.value.code == "RECONCILE_TENANT_SCOPE_AMBIGUOUS"


def test_service_replay_checks_each_work_order_identity_and_state(monkeypatch):
    tenant, site, building = _scoped_ids()
    requests = {}
    work_orders = {}
    for suffix in ("1", "2"):
        code = f"SYN-WORK-{suffix}"
        request = SimpleNamespace(
            id=uuid4(), tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            code=code, status="IN_PROGRESS", title="Synthetic work", priority="HIGH",
        )
        requests[f"{site.code}:{code}"] = request
        work_orders[f"{site.code}:{code}"] = SimpleNamespace(
            id=uuid4(), tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            service_request_id=request.id, code=f"WO-{code}", status="IN_PROGRESS",
        )
    rows = defaultdict(list, {"01_cong_viec.xlsx": [
        {"work_code": code, "status": "IN_PROGRESS", "title": "Synthetic work",
         "priority": "HIGH", "cost_vnd": 1000}
        for code in ("SYN-WORK-1", "SYN-WORK-2")
    ]})
    monkeypatch.setattr(reconcile, "_scope", lambda _session, _row: (tenant, site, building))

    def reference(_session, _tenant, _source, entity, key, _model, **_scope):
        target = (requests if entity == "ServiceRequest" else work_orders).get(key)
        if target is None:
            raise reconcile.ReconciliationError("RECONCILE_REFERENCE_MISSING")
        return target

    monkeypatch.setattr(reconcile, "_reference", reference)
    monkeypatch.setattr(reconcile, "_one", lambda _session, _query, _code: SimpleNamespace(
        amount_vnd=1000, cost_bearer="MANAGEMENT",
    ))
    counts = defaultdict(int)
    reconcile._service_replay(object(), rows, counts)
    assert counts["replay_service_requests"] == 2
    assert counts["replay_work_orders"] == 2

    # A missing FCS-12 work order must fail despite an APPLIED import-run row.
    del work_orders["SYN-SITE:SYN-WORK-2"]
    with pytest.raises(reconcile.ReconciliationError) as error:
        reconcile._service_replay(object(), rows, defaultdict(int))
    assert error.value.code == "RECONCILE_REFERENCE_MISSING"


def test_operational_replay_checks_cleaning_terminal_status(monkeypatch):
    tenant, site, building = _scoped_ids()
    shift = SimpleNamespace(
        id=uuid4(), tenant_id=tenant.id, site_id=site.id,
        building_id=building.id, status="COMPLETED",
    )
    task = SimpleNamespace(tenant_id=tenant.id, site_id=site.id, building_id=building.id)
    rows = defaultdict(list, {"06_ve_sinh.xlsx": [
        {"shift_code": "SYN-SHIFT", "status": "COMPLETED"},
    ]})
    monkeypatch.setattr(reconcile, "_scope", lambda _session, _row, _structure=None: (tenant, site, building))
    monkeypatch.setattr(reconcile, "_reference", lambda *_args, **_kwargs: shift)
    monkeypatch.setattr(reconcile, "_one", lambda *_args: task)
    counts = defaultdict(int)
    reconcile._operational_replay(object(), rows, counts)
    assert counts["replay_cleaning_shifts"] == 1

    shift.status = "PLANNED"
    with pytest.raises(reconcile.ReconciliationError) as error:
        reconcile._operational_replay(object(), rows, defaultdict(int))
    assert error.value.code == "RECONCILE_CLEANING_STATUS_MISMATCH"


def test_invoice_item_and_ar_readback_detects_drift(monkeypatch):
    tenant, site, building = _scoped_ids()
    account = SimpleNamespace(id=uuid4())
    billing_run = SimpleNamespace(id=uuid4(), fee_policy_version_id=uuid4(), status="POSTED")
    period = SimpleNamespace(id=uuid4())
    invoice = SimpleNamespace(
        id=uuid4(), tenant_id=tenant.id, site_id=site.id, building_id=building.id,
        billing_account_id=account.id, billing_run_id=billing_run.id,
        accounting_period_id=period.id, status="ISSUED", total_vnd=100000,
        outstanding_vnd=100000, issued_on=date(2026, 7, 1), due_on=date(2026, 7, 15),
    )
    version = SimpleNamespace(id=billing_run.fee_policy_version_id, version_number=1)
    item = SimpleNamespace(
        tenant_id=tenant.id, site_id=site.id, building_id=building.id,
        fee_policy_version_id=version.id, description="UNIT AREA M2",
        basis_quantity=Decimal("10.00"), unit_rate_vnd_snapshot=10000,
        rounding_unit_vnd_snapshot=1000, amount_vnd=100000,
    )
    row = {
        "tenant_code": "SYN-TENANT", "site_code": "SYN-SITE",
        "building_code": "SYN-BUILDING", "invoice_number": "SYN-INV",
        "billing_account_number": "SYN-ACCOUNT", "billing_run_key": "SYN-RUN",
        "period_key": "2026-07", "policy_version": 1,
        "invoice_status": "ISSUED", "total_vnd": 100000,
        "outstanding_vnd": 100000, "issued_on": date(2026, 7, 1),
        "due_on": date(2026, 7, 15), "line_description": "UNIT AREA M2",
        "basis_quantity": Decimal("10.00"), "unit_rate_vnd_snapshot": 10000,
        "rounding_unit_vnd_snapshot": 1000, "amount_vnd": 100000,
    }
    rows = defaultdict(list, {"10_hoa_don.xlsx": [row]})
    monkeypatch.setattr(reconcile, "_scope", lambda _session, _row: (tenant, site, building))
    targets = iter((invoice, account, billing_run, period))
    monkeypatch.setattr(reconcile, "_one", lambda _session, _query, _code: next(targets))

    class Session:
        ar_balance = 100000

        def get(self, _model, _identifier):
            return version

        def scalars(self, _query):
            return SimpleNamespace(all=lambda: [item])

        def scalar(self, _query):
            return self.ar_balance

    session = Session()
    counts = defaultdict(int)
    reconcile._finance(session, rows, counts)
    assert counts["replay_invoices"] == 1
    assert counts["replay_invoice_items"] == 1
    assert counts["replay_ar_accounts"] == 1

    session.ar_balance = 99999
    targets = iter((invoice, account, billing_run, period))
    with pytest.raises(reconcile.ReconciliationError) as error:
        reconcile._finance(session, rows, defaultdict(int))
    assert error.value.code == "RECONCILE_AR_MISMATCH"
