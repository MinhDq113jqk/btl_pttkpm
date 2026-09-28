"""Read-only, metadata-only reconciliation of a loaded submission pack.

The pack stays in memory.  On failure callers receive a stable code, never a
source key, person, amount, or raw cell value.  This module issues SELECTs
only and does not mutate ORM objects or commit a transaction.  The caller may
invoke it inside an apply transaction, where SQLAlchemy can autoflush earlier
loader changes before a SELECT.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping

from sqlalchemy import func, select

from app.models.account import Account, AccountRole
from app.models.billing import (
    AccountingPeriod, ArLedgerEntry, BillingAccount, BillingInvoice,
    BillingInvoiceItem, BillingRun, FeePolicy, FeePolicyVersion, OverpaymentCredit,
    Payment, PaymentAllocation, UnmatchedPayment,
)
from app.models.building import Building
from app.models.maintenance import Asset, MaintenanceOccurrence, MaintenancePlan
from app.models.operations import (
    CleaningShift, CleaningTask, PatrolPoint, PatrolWindow,
    SecurityIncident, SecurityShift,
)
from app.models.parcel import Parcel
from app.models.person import Person, UnitPersonRelationship
from app.models.service import CostLine, ServiceCategory, ServiceRequest, WorkOrder
from app.models.site import Site
from app.models.submission_import import SubmissionExternalReference
from app.models.tenant import Tenant
from app.models.unit import Unit
from app.services.submission_data_import import SubmissionImportError
from app.services.submission_data_mapping import derive_period_key
from app.services.submission_data_normalization import normalize_date, normalize_temporal
from app.services.submission_data_reader import SubmissionPack, iter_submission_rows


class ReconciliationError(SubmissionImportError):
    """The database no longer matches a normalized pack fact."""


def _check(condition: bool, code: str) -> None:
    if not condition:
        raise ReconciliationError(code)


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _required(value: object, code: str) -> str:
    result = _text(value)
    _check(bool(result), code)
    return result


def _vnd(value: object) -> int:
    try:
        _check(value is not None and not isinstance(value, bool), "RECONCILE_AMOUNT_INVALID")
        parsed = Decimal(str(value))
        _check(parsed.is_finite() and parsed == parsed.to_integral_value(), "RECONCILE_AMOUNT_INVALID")
        return int(parsed)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ReconciliationError("RECONCILE_AMOUNT_INVALID") from exc


def _utc(value: object, field: str) -> datetime:
    return normalize_temporal(value, field=field, as_of_utc=datetime.max.replace(tzinfo=UTC)).utc


def _one(session, statement, code: str):
    matches = session.scalars(statement).all()
    _check(len(matches) == 1, code)
    return matches[0]


def _rows(pack: SubmissionPack) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = defaultdict(list)
    for workbook, _, row in iter_submission_rows(pack):
        result[workbook.file_name].append(row)
    return result


def _scope(session, row: Mapping[str, object], structure_rows: list[dict[str, object]] | None = None):
    tenant_code = _text(row.get("tenant_code"))
    if not tenant_code and structure_rows is not None:
        # Files 06, 07 and 12 omit tenant_code.  Resolve it through the same
        # approved structure workbook used by the loader, never by a name.
        matches = {
            _text(structure.get("tenant_code"))
            for structure in structure_rows
            if _text(structure.get("site_code")).casefold() == _text(row.get("site_code")).casefold()
            and _text(structure.get("building_code")).casefold() == _text(row.get("building_code")).casefold()
        }
        _check(len(matches) == 1, "RECONCILE_TENANT_SCOPE_AMBIGUOUS")
        tenant_code = next(iter(matches))
    tenant = _one(session, select(Tenant).where(
        Tenant.code == _required(tenant_code, "RECONCILE_TENANT_CODE_INVALID"),
    ), "RECONCILE_TENANT_MISSING")
    site = _one(session, select(Site).where(
        Site.tenant_id == tenant.id,
        Site.code == _required(row.get("site_code"), "RECONCILE_SITE_CODE_INVALID"),
    ), "RECONCILE_SITE_MISSING")
    building = _one(session, select(Building).where(
        Building.site_id == site.id,
        Building.code == _required(row.get("building_code"), "RECONCILE_BUILDING_CODE_INVALID"),
    ), "RECONCILE_BUILDING_MISSING")
    _check(building.site_id == site.id and site.tenant_id == tenant.id, "RECONCILE_SCOPE_MISMATCH")
    return tenant, site, building


def _reference(session, tenant, source: str, entity_type: str, key: str, model,
               *, site=None, building=None):
    ref = _one(session, select(SubmissionExternalReference).where(
        SubmissionExternalReference.tenant_id == tenant.id,
        SubmissionExternalReference.source == source,
        SubmissionExternalReference.entity_type == entity_type,
        SubmissionExternalReference.source_key == key,
    ), "RECONCILE_REFERENCE_MISSING")
    target = session.get(model, ref.target_id)
    _check(target is not None, "RECONCILE_REFERENCE_TARGET_MISSING")
    _check(getattr(target, "tenant_id", tenant.id) == tenant.id, "RECONCILE_SCOPE_MISMATCH")
    if site is not None:
        _check(getattr(target, "site_id", None) == site.id, "RECONCILE_SCOPE_MISMATCH")
    if building is not None:
        _check(getattr(target, "building_id", None) == building.id, "RECONCILE_SCOPE_MISMATCH")
    return target


def _master(session, rows: dict[str, list[dict[str, object]]], counts: dict[str, int]) -> None:
    for row in rows["03_toa_nha_can_ho.xlsx"]:
        tenant, site, building = _scope(session, row)
        unit = _one(session, select(Unit).where(
            Unit.building_id == building.id, Unit.unit_number == _text(row.get("unit_number")),
        ), "RECONCILE_UNIT_MISSING")
        account = _one(session, select(BillingAccount).where(
            BillingAccount.site_id == site.id,
            BillingAccount.account_number == _text(row.get("billing_account_number")),
        ), "RECONCILE_BILLING_ACCOUNT_MISSING")
        _check(
            site.name == _text(row.get("site_name"))
            and building.name == _text(row.get("building_name"))
            and building.floors_count == row.get("floors_count")
            and unit.floor == row.get("floor")
            and round(unit.area_m2, 2) == round(float(row.get("area_m2")), 2)
            and unit.status == _text(row.get("unit_status")).lower()
            and (account.tenant_id, account.site_id, account.building_id, account.unit_id)
            == (tenant.id, site.id, building.id, unit.id)
            and account.status == _text(row.get("billing_status")).upper(),
            "RECONCILE_MASTER_METADATA_MISMATCH",
        )
        linked = _reference(
            session, tenant, "unit", "Unit",
            f"{site.code}:{building.code}:{unit.unit_number}", Unit,
        )
        _check(linked.id == unit.id, "RECONCILE_REFERENCE_ID_MISMATCH")
        counts["master_units"] += 1

    for row in rows["02_danh_sach_nhan_vien.xlsx"]:
        tenant = _one(session, select(Tenant).where(
            Tenant.code == _text(row.get("tenant_code")),
        ), "RECONCILE_TENANT_MISSING")
        account = _reference(session, tenant, "employee", "Account",
                             _text(row.get("employee_code")), Account)
        _check(
            account.username == _text(row.get("username"))
            and account.full_name == _text(row.get("full_name"))
            and account.is_active == (_text(row.get("status")).upper() == "ACTIVE"),
            "RECONCILE_ACCOUNT_MISMATCH",
        )
        site_code = _text(row.get("site_code"))
        building_code = _text(row.get("building_code"))
        site = _one(session, select(Site).where(
            Site.tenant_id == tenant.id, Site.code == site_code,
        ), "RECONCILE_ACCOUNT_SCOPE_MISSING") if site_code else None
        building = _one(session, select(Building).where(
            Building.site_id == site.id, Building.code == building_code,
        ), "RECONCILE_ACCOUNT_SCOPE_MISSING") if building_code and site else None
        _check(not building_code or building is not None, "RECONCILE_ACCOUNT_SCOPE_MISSING")
        _one(session, select(AccountRole).where(
            AccountRole.account_id == account.id,
            AccountRole.role == _text(row.get("role")).lower(),
            AccountRole.site_id == (site.id if site else None),
            AccountRole.building_id == (building.id if building else None),
        ), "RECONCILE_ACCOUNT_ROLE_MISSING")
        counts["master_accounts"] += 1

    for row in rows["04_cu_dan.xlsx"]:
        tenant, site, building = _scope(session, row)
        unit = _one(session, select(Unit).where(
            Unit.building_id == building.id, Unit.unit_number == _text(row.get("unit_number")),
        ), "RECONCILE_UNIT_MISSING")
        person = _reference(session, tenant, "resident", "Person",
                            _text(row.get("resident_code")), Person)
        _check(
            (person.full_name, person.phone_masked, person.email_masked)
            == (_text(row.get("full_name")), _text(row.get("phone_masked")), _text(row.get("email_masked"))),
            "RECONCILE_PERSON_MISMATCH",
        )
        relationship = _one(session, select(UnitPersonRelationship).where(
            UnitPersonRelationship.unit_id == unit.id,
            UnitPersonRelationship.person_id == person.id,
            UnitPersonRelationship.relationship_type == _text(row.get("relationship_type")).lower(),
            UnitPersonRelationship.valid_from == normalize_date(row.get("valid_from"), field="valid_from"),
        ), "RECONCILE_RELATIONSHIP_MISSING")
        _check(
            (relationship.tenant_id, relationship.site_id, relationship.building_id)
            == (tenant.id, site.id, building.id),
            "RECONCILE_SCOPE_MISMATCH",
        )
        counts["master_relationships"] += 1


def _references(session, rows: dict[str, list[dict[str, object]]], counts: dict[str, int]) -> None:
    specifications = (
        ("05_tai_san_bao_tri.xlsx", "maintenance", "Asset", "asset_code", Asset, False),
        ("06_ve_sinh.xlsx", "cleaning", "CleaningShift", "shift_code", CleaningShift, True),
        ("07_an_ninh_tuan_tra.xlsx", "security", "SecurityShift", "shift_code", SecurityShift, True),
        ("08_su_co_an_ninh.xlsx", "security", "SecurityIncident", "incident_code", SecurityIncident, True),
        ("12_buu_pham.xlsx", "parcel", "Parcel", "parcel_code", Parcel, True),
    )
    for workbook, source, entity, field, model, scoped_key in specifications:
        for row in rows[workbook]:
            tenant, site, building = _scope(session, row, rows["03_toa_nha_can_ho.xlsx"])
            key = _required(row.get(field), "RECONCILE_REFERENCE_KEY_INVALID")
            if scoped_key:
                key = f"{site.code}:{building.code}:{key}" if entity == "SecurityShift" else f"{site.code}:{key}"
            target = _reference(session, tenant, source, entity, key, model, site=site,
                                building=building if entity != "SecurityShift" else None)
            if entity == "SecurityShift":
                _check(target.building_id == building.id, "RECONCILE_SCOPE_MISMATCH")
            if entity == "Asset":
                _check(
                    target.name == _text(row.get("asset_name"))
                    and target.status == _text(row.get("status")).upper(),
                    "RECONCILE_ASSET_MISMATCH",
                )
                plan = _one(session, select(MaintenancePlan).where(
                    MaintenancePlan.asset_id == target.id,
                    MaintenancePlan.code == _text(row.get("maintenance_plan_code")),
                ), "RECONCILE_MAINTENANCE_PLAN_MISSING")
                _check(
                    (plan.tenant_id, plan.site_id, plan.building_id)
                    == (tenant.id, site.id, building.id)
                    and plan.interval_days == row.get("interval_days")
                    and plan.next_due_at == _utc(row.get("next_due_date"), "next_due_date"),
                    "RECONCILE_MAINTENANCE_PLAN_MISMATCH",
                )
                counts["reference_maintenance_plans"] += 1
            counts["reference_rows"] += 1
    for row in rows["01_cong_viec.xlsx"]:
        tenant, site, building = _scope(session, row)
        category = _one(session, select(ServiceCategory).where(
            ServiceCategory.site_id == site.id,
            ServiceCategory.code == _text(row.get("request_type")),
        ), "RECONCILE_CATEGORY_MISSING")
        _check(category.tenant_id == tenant.id and category.site_id == site.id,
               "RECONCILE_SCOPE_MISMATCH")
        sla = int((_utc(row.get("sla_due_at"), "sla_due_at")
                   - _utc(row.get("created_at"), "created_at")).total_seconds() // 60)
        _check(category.sla_minutes == sla, "RECONCILE_CATEGORY_SLA_MISMATCH")
        counts["reference_categories"] += 1

    for row in rows["09_chinh_sach_phi.xlsx"]:
        tenant, site, building = _scope(session, row)
        policy = _one(session, select(FeePolicy).where(
            FeePolicy.building_id == building.id,
            FeePolicy.code == _text(row.get("fee_policy_code")),
        ), "RECONCILE_FEE_POLICY_MISSING")
        _check(
            (policy.tenant_id, policy.site_id, policy.building_id)
            == (tenant.id, site.id, building.id)
            and policy.name == _text(row.get("fee_policy_name"))
            and policy.is_active == (_text(row.get("policy_status")).upper() == "ACTIVE"),
            "RECONCILE_FEE_POLICY_MISMATCH",
        )
        version = _one(session, select(FeePolicyVersion).where(
            FeePolicyVersion.fee_policy_id == policy.id,
            FeePolicyVersion.version_number == row.get("version_number"),
        ), "RECONCILE_FEE_POLICY_VERSION_MISSING")
        _check(
            (version.tenant_id, version.site_id, version.building_id)
            == (tenant.id, site.id, building.id)
            and version.effective_from == normalize_date(row.get("effective_from"), field="effective_from")
            and version.effective_to == (
                normalize_date(row.get("effective_to"), field="effective_to")
                if row.get("effective_to") else None
            )
            and version.unit_rate_vnd == _vnd(row.get("unit_rate_vnd"))
            and version.basis == _text(row.get("basis")).upper()
            and version.rounding_unit_vnd == _vnd(row.get("rounding_unit_vnd")),
            "RECONCILE_FEE_POLICY_VERSION_MISMATCH",
        )
        period = _one(session, select(AccountingPeriod).where(
            AccountingPeriod.building_id == building.id,
            AccountingPeriod.period_key == _text(row.get("period_key")),
        ), "RECONCILE_ACCOUNTING_PERIOD_MISSING")
        _check(
            (period.tenant_id, period.site_id, period.building_id)
            == (tenant.id, site.id, building.id)
            and period.period_start == normalize_date(row.get("period_start"), field="period_start")
            and period.period_end == normalize_date(row.get("period_end"), field="period_end")
            and period.cutoff_at == _utc(row.get("cutoff_at"), "cutoff_at")
            and period.status == _text(row.get("period_status")).upper(),
            "RECONCILE_ACCOUNTING_PERIOD_MISMATCH",
        )
        counts["reference_fee_policy_versions"] += 1
        counts["reference_accounting_periods"] += 1


def _service_replay(session, rows: dict[str, list[dict[str, object]]], counts: dict[str, int]) -> None:
    seen: set[tuple[object, str]] = set()
    for row in rows["01_cong_viec.xlsx"]:
        tenant, site, building = _scope(session, row)
        work_code = _required(row.get("work_code"), "RECONCILE_WORK_CODE_INVALID")
        key = (site.id, work_code)
        _check(key not in seen, "RECONCILE_WORK_ORACLE_DUPLICATE")
        seen.add(key)
        request = _reference(session, tenant, "service-request", "ServiceRequest",
                             f"{site.code}:{work_code}", ServiceRequest,
                             site=site, building=building)
        source_status = _text(row.get("status")).upper()
        _check(source_status in {"NEW", "IN_PROGRESS", "CLOSED"}, "RECONCILE_WORK_STATUS_INVALID")
        _check(
            request.code == work_code and request.status == source_status
            and request.title == _text(row.get("title"))
            and request.priority == _text(row.get("priority")).upper(),
            "RECONCILE_SERVICE_REQUEST_MISMATCH",
        )
        if source_status == "NEW":
            counts["replay_service_requests"] += 1
            continue
        work_order = _reference(session, tenant, "service-request", "WorkOrder",
                                f"{site.code}:{work_code}", WorkOrder,
                                site=site, building=building)
        _check(
            work_order.service_request_id == request.id
            and work_order.code == f"WO-{work_code}"
            and work_order.status == source_status,
            "RECONCILE_WORK_ORDER_MISMATCH",
        )
        cost = _one(session, select(CostLine).where(
            CostLine.work_order_id == work_order.id,
        ), "RECONCILE_COST_LINE_MISSING")
        _check(
            cost.amount_vnd == _vnd(row.get("cost_vnd"))
            and cost.cost_bearer == "MANAGEMENT",
            "RECONCILE_COST_LINE_MISMATCH",
        )
        if source_status == "CLOSED":
            completed = _utc(row.get("completed_at"), "completed_at")
            _check(
                work_order.completed_at == completed
                and request.closed_at == completed
                and work_order.acceptance_evidence_id is not None,
                "RECONCILE_WORK_CLOSURE_MISMATCH",
            )
        counts["replay_service_requests"] += 1
        counts["replay_work_orders"] += 1


def _operational_replay(session, rows: dict[str, list[dict[str, object]]], counts: dict[str, int]) -> None:
    structure = rows["03_toa_nha_can_ho.xlsx"]
    for row in rows["05_tai_san_bao_tri.xlsx"]:
        tenant, site, building = _scope(session, row)
        asset = _reference(session, tenant, "maintenance", "Asset",
                           _text(row.get("asset_code")), Asset, site=site, building=building)
        plan = _one(session, select(MaintenancePlan).where(
            MaintenancePlan.asset_id == asset.id,
            MaintenancePlan.code == _text(row.get("maintenance_plan_code")),
        ), "RECONCILE_MAINTENANCE_PLAN_MISSING")
        occurrence = _reference(
            session, tenant, "maintenance", "MaintenanceOccurrence",
            f"{asset.code}:{plan.code}:{plan.next_due_at.isoformat()}",
            MaintenanceOccurrence, site=site, building=building,
        )
        _check(occurrence.plan_id == plan.id and occurrence.status == "WO_CREATED",
               "RECONCILE_MAINTENANCE_OCCURRENCE_MISMATCH")
        work_order = _one(session, select(WorkOrder).where(
            WorkOrder.maintenance_occurrence_id == occurrence.id,
        ), "RECONCILE_MAINTENANCE_WORK_ORDER_MISSING")
        _check((work_order.tenant_id, work_order.site_id, work_order.building_id)
               == (tenant.id, site.id, building.id), "RECONCILE_SCOPE_MISMATCH")
        counts["replay_maintenance_occurrences"] += 1

    for row in rows["06_ve_sinh.xlsx"]:
        tenant, site, building = _scope(session, row, structure)
        shift = _reference(session, tenant, "cleaning", "CleaningShift",
                           f"{site.code}:{_text(row.get('shift_code'))}",
                           CleaningShift, site=site, building=building)
        _check(shift.status == _text(row.get("status")).upper(), "RECONCILE_CLEANING_STATUS_MISMATCH")
        task = _one(session, select(CleaningTask).where(
            CleaningTask.shift_id == shift.id,
        ), "RECONCILE_CLEANING_TASK_MISSING")
        _check((task.tenant_id, task.site_id, task.building_id)
               == (tenant.id, site.id, building.id), "RECONCILE_SCOPE_MISMATCH")
        counts["replay_cleaning_shifts"] += 1

    for row in rows["07_an_ninh_tuan_tra.xlsx"]:
        tenant, site, building = _scope(session, row, structure)
        shift = _reference(session, tenant, "security", "SecurityShift",
                           f"{site.code}:{building.code}:{_text(row.get('shift_code'))}",
                           SecurityShift, site=site, building=building)
        point = _one(session, select(PatrolPoint).where(
            PatrolPoint.site_id == site.id,
            PatrolPoint.code == _text(row.get("patrol_point_code")),
        ), "RECONCILE_PATROL_POINT_MISSING")
        window = _one(session, select(PatrolWindow).where(
            PatrolWindow.security_shift_id == shift.id,
            PatrolWindow.patrol_point_id == point.id,
            PatrolWindow.window_start_at == _utc(row.get("window_start"), "window_start"),
        ), "RECONCILE_PATROL_WINDOW_MISSING")
        _check((window.tenant_id, window.site_id, window.building_id)
               == (tenant.id, site.id, building.id)
               and window.status == _text(row.get("patrol_status")).upper(),
               "RECONCILE_PATROL_WINDOW_MISMATCH")
        counts["replay_patrol_windows"] += 1

    for row in rows["08_su_co_an_ninh.xlsx"]:
        tenant, site, building = _scope(session, row)
        incident = _reference(session, tenant, "security", "SecurityIncident",
                              f"{site.code}:{_text(row.get('incident_code'))}",
                              SecurityIncident, site=site, building=building)
        _check(incident.status == _text(row.get("status")).upper(),
               "RECONCILE_INCIDENT_STATUS_MISMATCH")
        if row.get("resolved_at") is not None:
            _check(incident.resolved_at == _utc(row.get("resolved_at"), "resolved_at"),
                   "RECONCILE_INCIDENT_RESOLUTION_MISMATCH")
        counts["replay_incidents"] += 1

    for row in rows["12_buu_pham.xlsx"]:
        tenant, site, building = _scope(session, row, structure)
        parcel = _reference(session, tenant, "parcel", "Parcel",
                            f"{site.code}:{_text(row.get('parcel_code'))}",
                            Parcel, site=site, building=building)
        _check(parcel.status == _text(row.get("status")).upper(),
               "RECONCILE_PARCEL_STATUS_MISMATCH")
        counts["replay_parcels"] += 1


def _finance(session, rows: dict[str, list[dict[str, object]]], counts: dict[str, int]) -> None:
    invoice_rows = rows["10_hoa_don.xlsx"]
    policy_rows = rows["09_chinh_sach_phi.xlsx"]
    # Reject a duplicated oracle identity before comparing any database row.
    source_invoice_keys = [
        (_text(row.get("tenant_code")), _text(row.get("site_code")), _text(row.get("invoice_number")))
        for row in invoice_rows
    ]
    _check(all(all(key) for key in source_invoice_keys), "RECONCILE_INVOICE_NUMBER_INVALID")
    _check(len(source_invoice_keys) == len(set(source_invoice_keys)),
           "RECONCILE_INVOICE_ORACLE_DUPLICATE")
    seen_invoices: set[tuple[object, str]] = set()
    expected_ar: dict[object, int] = defaultdict(int)
    for row in invoice_rows:
        tenant, site, building = _scope(session, row)
        number = _required(row.get("invoice_number"), "RECONCILE_INVOICE_NUMBER_INVALID")
        key = (site.id, number)
        _check(key not in seen_invoices, "RECONCILE_INVOICE_ORACLE_DUPLICATE")
        seen_invoices.add(key)
        invoice = _one(session, select(BillingInvoice).where(
            BillingInvoice.site_id == site.id, BillingInvoice.invoice_number == number,
        ), "RECONCILE_INVOICE_MISSING")
        account = _one(session, select(BillingAccount).where(
            BillingAccount.site_id == site.id,
            BillingAccount.account_number == _text(row.get("billing_account_number")),
        ), "RECONCILE_BILLING_ACCOUNT_MISSING")
        billing_run = _one(session, select(BillingRun).where(
            BillingRun.site_id == site.id,
            BillingRun.run_key == _text(row.get("billing_run_key")),
        ), "RECONCILE_BILLING_RUN_MISSING")
        period = _one(session, select(AccountingPeriod).where(
            AccountingPeriod.building_id == building.id,
            AccountingPeriod.period_key == _text(row.get("period_key")),
        ), "RECONCILE_ACCOUNTING_PERIOD_MISSING")
        version = session.get(FeePolicyVersion, billing_run.fee_policy_version_id)
        _check(version is not None and version.version_number == row.get("policy_version"),
               "RECONCILE_POLICY_VERSION_MISMATCH")
        expected_total = _vnd(row.get("total_vnd"))
        expected_outstanding = _vnd(row.get("outstanding_vnd"))
        _check(
            (invoice.tenant_id, invoice.site_id, invoice.building_id,
             invoice.billing_account_id, invoice.billing_run_id, invoice.accounting_period_id)
            == (tenant.id, site.id, building.id, account.id, billing_run.id, period.id)
            and billing_run.status == "POSTED"
            and invoice.status == _text(row.get("invoice_status")).upper()
            and invoice.total_vnd == expected_total
            and invoice.outstanding_vnd == expected_outstanding
            and invoice.issued_on == normalize_date(row.get("issued_on"), field="issued_on")
            and invoice.due_on == normalize_date(row.get("due_on"), field="due_on"),
            "RECONCILE_INVOICE_MISMATCH",
        )
        items = session.scalars(select(BillingInvoiceItem).where(
            BillingInvoiceItem.billing_invoice_id == invoice.id,
        )).all()
        _check(len(items) == 1, "RECONCILE_INVOICE_ITEM_COUNT")
        item = items[0]
        _check(
            (item.tenant_id, item.site_id, item.building_id) == (tenant.id, site.id, building.id)
            and item.fee_policy_version_id == version.id
            and item.description == _text(row.get("line_description"))
            and Decimal(item.basis_quantity) == Decimal(str(row.get("basis_quantity")))
            and item.unit_rate_vnd_snapshot == _vnd(row.get("unit_rate_vnd_snapshot"))
            and item.rounding_unit_vnd_snapshot == _vnd(row.get("rounding_unit_vnd_snapshot"))
            and item.amount_vnd == _vnd(row.get("amount_vnd"))
            and item.amount_vnd == invoice.total_vnd,
            "RECONCILE_INVOICE_ITEM_MISMATCH",
        )
        expected_ar[account.id] += expected_outstanding
        counts["replay_invoices"] += 1
        counts["replay_invoice_items"] += 1

    seen_payments: set[tuple[object, str, str]] = set()
    seen_receipts: set[tuple[object, str]] = set()
    for row in rows["11_thanh_toan.xlsx"]:
        tenant, site, building = _scope(session, row)
        payment_source = _required(row.get("payment_source"), "RECONCILE_PAYMENT_SOURCE_INVALID").upper()
        source_ref = _required(row.get("source_reference"), "RECONCILE_PAYMENT_REF_INVALID")
        receipt = _required(row.get("receipt_number"), "RECONCILE_PAYMENT_RECEIPT_INVALID")
        identity = (site.id, payment_source, source_ref)
        receipt_identity = (site.id, receipt)
        _check(identity not in seen_payments and receipt_identity not in seen_receipts,
               "RECONCILE_PAYMENT_ORACLE_DUPLICATE")
        seen_payments.add(identity)
        seen_receipts.add(receipt_identity)
        payment = _one(session, select(Payment).where(
            Payment.tenant_id == tenant.id, Payment.site_id == site.id,
            Payment.payment_source == payment_source,
            Payment.source_reference == source_ref,
        ), "RECONCILE_PAYMENT_MISSING")
        period_key = derive_period_key(row, invoice_rows, policy_rows)
        period = _one(session, select(AccountingPeriod).where(
            AccountingPeriod.building_id == building.id,
            AccountingPeriod.period_key == period_key,
        ), "RECONCILE_ACCOUNTING_PERIOD_MISSING")
        account_number = _text(row.get("billing_account_number"))
        account = _one(session, select(BillingAccount).where(
            BillingAccount.site_id == site.id,
            BillingAccount.account_number == account_number,
        ), "RECONCILE_BILLING_ACCOUNT_MISSING") if account_number else None
        actor = _one(session, select(Account).where(
            Account.tenant_id == tenant.id,
            Account.username == _text(row.get("received_by_username")),
        ), "RECONCILE_PAYMENT_ACTOR_MISSING")
        source_status = _text(row.get("status")).upper()
        _check(source_status in {"ALLOCATED", "PARTIALLY_ALLOCATED", "OVERPAID", "UNMATCHED"},
               "RECONCILE_PAYMENT_STATUS_INVALID")
        target_status = "ALLOCATED" if source_status == "PARTIALLY_ALLOCATED" else source_status
        _check(
            (payment.tenant_id, payment.site_id, payment.building_id,
             payment.billing_account_id, payment.accounting_period_id)
            == (tenant.id, site.id, building.id, account.id if account else None, period.id)
            and payment.receipt_number == receipt
            and payment.amount_vnd == _vnd(row.get("amount_vnd"))
            and payment.received_at == _utc(row.get("received_at"), "received_at")
            and payment.received_by_id == actor.id
            and payment.status == target_status,
            "RECONCILE_PAYMENT_MISMATCH",
        )
        allocations = session.scalars(select(PaymentAllocation).where(
            PaymentAllocation.payment_id == payment.id,
        )).all()
        _check(all(
            (allocation.tenant_id, allocation.site_id, allocation.building_id)
            == (tenant.id, site.id, building.id)
            for allocation in allocations
        ), "RECONCILE_SCOPE_MISMATCH")
        for allocation in allocations:
            target_invoice = session.get(BillingInvoice, allocation.billing_invoice_id)
            _check(
                target_invoice is not None and account is not None
                and (target_invoice.tenant_id, target_invoice.site_id,
                     target_invoice.building_id, target_invoice.billing_account_id)
                == (tenant.id, site.id, building.id, account.id),
                "RECONCILE_ALLOCATION_SCOPE_MISMATCH",
            )
        _check(sum(item.amount_vnd for item in allocations) == _vnd(row.get("allocated_vnd") or 0),
               "RECONCILE_ALLOCATION_MISMATCH")
        matched_number = _text(row.get("matched_invoice_number"))
        if matched_number:
            invoice = _one(session, select(BillingInvoice).where(
                BillingInvoice.site_id == site.id,
                BillingInvoice.invoice_number == matched_number,
            ), "RECONCILE_MATCHED_INVOICE_MISSING")
            _check(any(item.billing_invoice_id == invoice.id for item in allocations),
                   "RECONCILE_MATCHED_INVOICE_MISMATCH")
        credit_rows = session.scalars(select(OverpaymentCredit).where(
            OverpaymentCredit.payment_id == payment.id,
        )).all()
        _check(len(credit_rows) <= 1, "RECONCILE_CREDIT_DUPLICATE")
        credit = credit_rows[0] if credit_rows else None
        _check((credit.remaining_vnd if credit else 0) == _vnd(row.get("overpayment_vnd") or 0),
               "RECONCILE_CREDIT_MISMATCH")
        if credit is not None:
            _check(
                account is not None
                and (credit.tenant_id, credit.site_id, credit.building_id, credit.billing_account_id)
                == (tenant.id, site.id, building.id, account.id),
                "RECONCILE_SCOPE_MISMATCH",
            )
        unmatched_rows = session.scalars(select(UnmatchedPayment).where(
            UnmatchedPayment.payment_id == payment.id,
        )).all()
        if source_status == "UNMATCHED":
            _check(account is None and not allocations and not credit_rows
                   and len(unmatched_rows) == 1 and unmatched_rows[0].status == "OPEN"
                   and unmatched_rows[0].amount_vnd == payment.amount_vnd,
                   "RECONCILE_UNMATCHED_MISMATCH")
            counts["replay_unmatched"] += 1
        else:
            _check(account is not None and not unmatched_rows, "RECONCILE_PAYMENT_MATCH_MISMATCH")
        counts["replay_payments"] += 1
        counts["replay_allocations"] += len(allocations)
        counts["replay_credits"] += len(credit_rows)

    for account_id, expected_balance in expected_ar.items():
        actual_balance = session.scalar(select(func.coalesce(
            func.sum(ArLedgerEntry.debit_vnd - ArLedgerEntry.credit_vnd), 0,
        )).where(ArLedgerEntry.billing_account_id == account_id))
        _check(int(actual_balance or 0) == expected_balance, "RECONCILE_AR_MISMATCH")
        counts["replay_ar_accounts"] += 1
    # Zero deltas are safe metadata after all source-to-database checks pass.
    counts["invoice_delta_vnd"] = 0
    counts["ar_delta_vnd"] = 0


def reconcile_submission_pack(session, pack: SubmissionPack, stage: str) -> dict[str, int]:
    """Compare source identities and final states with persisted domain rows.

    ``stage`` may be master, references, replay, or all.  Counts identify the
    checks performed; they do not contain source keys, amounts, or personal data.
    A mismatch raises ``ReconciliationError`` with a stable redacted code.
    """

    _check(stage in {"master", "references", "replay", "all"}, "RECONCILE_STAGE_INVALID")
    rows = _rows(pack)
    counts: dict[str, int] = defaultdict(int)
    if stage in {"master", "all"}:
        _master(session, rows, counts)
    if stage in {"references", "all"}:
        _references(session, rows, counts)
    if stage in {"replay", "all"}:
        _service_replay(session, rows, counts)
        _operational_replay(session, rows, counts)
        _finance(session, rows, counts)
    return dict(counts)


__all__ = ["ReconciliationError", "reconcile_submission_pack"]
