"""Canonical contract for the 12 GreenCity submission workbooks.

This module is deliberately independent from SQLAlchemy and from the XLSX
reader.  It is the machine-readable boundary shared by preflight and the
import service.  A field is never silently dropped: it is either
Persist, Derive, Validate, or Ignore-with-reason.

The contract describes the source layout.  It does not perform database writes
or authorize replay while source preflight errors remain.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Literal


Disposition = Literal["Persist", "Derive", "Validate", "Ignore-with-reason"]
DISPOSITIONS = frozenset({"Persist", "Derive", "Validate", "Ignore-with-reason"})
CONTRACT_VERSION = "fcs05-r3"
SOURCE_SHEET = "Dữ liệu"
GUIDE_SHEET = "Hướng dẫn"


@dataclass(frozen=True)
class FieldContract:
    source_name: str
    value_type: str
    required: bool
    disposition: Disposition
    target: str | None
    reference: str | None
    rule: str
    decision_ref: str | None = None
    enum: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkbookContract:
    file_name: str
    schema_version: str
    expected_data_rows: int
    data_sheet: str
    guide_sheet: str
    natural_key: tuple[str, ...]
    target_entities: tuple[str, ...]
    fields: tuple[FieldContract, ...]
    canonical_inputs_missing: tuple[str, ...] = ()
    open_decisions: tuple[str, ...] = ()


def _f(
    source_name: str,
    value_type: str,
    required: bool,
    disposition: Disposition,
    target: str | None,
    reference: str | None,
    rule: str,
    decision_ref: str | None = None,
    enum: tuple[str, ...] = (),
) -> FieldContract:
    return FieldContract(
        source_name=source_name,
        value_type=value_type,
        required=required,
        disposition=disposition,
        target=target,
        reference=reference,
        rule=rule,
        decision_ref=decision_ref,
        enum=enum,
    )


TEXT = "string"
DATE = "date"
DATETIME = "datetime"
INTEGER = "integer"
DECIMAL = "decimal"
BOOLEAN = "boolean"

PRIORITY = ("LOW", "MEDIUM", "HIGH", "URGENT")
SERVICE_STATUS = ("NEW", "TRIAGED", "IN_PROGRESS", "WAITING_INFO", "RESOLVED", "CLOSED", "CANCELLED")
WORK_ORDER_STATUS = ("DRAFT", "ASSIGNED", "IN_PROGRESS", "ON_HOLD", "WAITING_ACCEPTANCE", "COMPLETED", "CLOSED", "CANCELLED")
UNIT_STATUS = ("occupied", "vacant", "reserved")
RELATIONSHIP = ("owner", "tenant", "family_member")
ACCOUNT_ROLE = ("admin", "director", "cskh", "accountant", "technical_lead", "technician", "cleaning", "security", "resident")
BILLING_ACCOUNT_STATUS = ("ACTIVE", "SUSPENDED", "CLOSED")
INVOICE_STATUS = ("DRAFT", "ISSUED", "PARTIALLY_PAID", "PAID", "VOID")
PAYMENT_STATUS = ("RECEIVED", "ALLOCATING", "PARTIALLY_ALLOCATED", "ALLOCATED", "UNMATCHED", "OVERPAID", "REVERSED")
PAYMENT_SOURCE = ("CASH", "BANK_TRANSFER", "GATEWAY")
PARCEL_STATUS = ("RECEIVED", "READY_FOR_PICKUP", "HANDED_OVER", "RETURNED", "LOST", "DAMAGED")
SECURITY_STATUS = ("NEW", "TRIAGED", "IN_PROGRESS", "RESOLVED", "CLOSED")
SECURITY_SEVERITY = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
SECURITY_INCIDENT_TYPE = ("SECURITY", "FIRE")
PATROL_STATUS = ("SCHEDULED", "COMPLETED", "MISSED", "CANCELLED")
CLEANING_STATUS = ("PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED")
CHECKLIST_RESULT = ("PENDING", "PASS", "FAIL", "NOT_APPLICABLE")
PERIOD_STATUS = ("OPEN", "CLOSING", "CLOSED", "LOCKED")


WORKBOOK_CONTRACTS: tuple[WorkbookContract, ...] = (
    WorkbookContract(
        file_name="01_cong_viec.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=9,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("work_code",),
        target_entities=("ServiceRequest", "WorkOrder", "CostLine"),
        fields=(
            _f("work_code", TEXT, True, "Persist", "ServiceRequest.code", "site_code + work_code", "Preserve the source code; reject blank or duplicate code."),
            _f("request_type", TEXT, True, "Validate", "ServiceCategory.code", "site_code + request_type", "Normalize for comparison; resolve category and SLA before apply.", "FCS-05:CATEGORY_SLA"),
            _f("title", TEXT, True, "Persist", "ServiceRequest.title", None, "Trim and enforce the target length."),
            _f("description", TEXT, True, "Persist", "ServiceRequest.description", None, "Trim; retain only in the local approved scope."),
            _f("priority", TEXT, True, "Validate", "ServiceRequest.priority", None, "Normalize to uppercase and validate the service priority enum.", enum=PRIORITY),
            _f("status", TEXT, True, "Validate", "ServiceRequest/WorkOrder.status", None, "Map through state-machine commands; never write a terminal state directly.", enum=SERVICE_STATUS + WORK_ORDER_STATUS),
            _f("tenant_code", TEXT, True, "Derive", "tenant_id", "Tenant.code", "Resolve exactly one tenant; fail on zero or multiple matches."),
            _f("site_code", TEXT, True, "Derive", "site_id", "Site.tenant_id + Site.code", "Resolve within the tenant scope."),
            _f("building_code", TEXT, True, "Derive", "building_id", "Building.site_id + Building.code", "Resolve within the site scope."),
            _f("unit_number", TEXT, False, "Derive", "unit_id", "Unit.building_id + Unit.unit_number", "Blank means a building-scoped request; otherwise resolve one unit."),
            _f("reported_by_username", TEXT, True, "Derive", "created_by_id", "Account.tenant_id + Account.username", "Resolve an existing account; do not join by full name."),
            _f("assignee_username", TEXT, True, "Derive", "owner_account_id/assigned_to_id", "Account.tenant_id + Account.username", "Resolve an existing in-scope account."),
            _f("created_at", DATETIME, True, "Derive", "ServiceRequest.sla_started_at", None, "Interpret in the approved site timezone, convert to UTC, and reject an invalid timestamp.", "FCS-01:TIMEZONE"),
            _f("sla_due_at", DATETIME, True, "Validate", "ServiceRequest SLA oracle", None, "Recompute from category SLA and compare; do not persist as an independent authority.", "FCS-05:CATEGORY_SLA"),
            _f("completed_at", DATETIME, False, "Derive", "WorkOrder.completed_at", None, "Use only through a legal state transition; future timestamps cannot close work."),
            _f("cost_vnd", DECIMAL, True, "Persist", "CostLine.amount_vnd", None, "Parse Decimal, quantize to VND, and require the approved cost bearer before apply.", "FCS-05:COST_BEARER"),
            _f("notes", TEXT, False, "Ignore-with-reason", None, None, "IGNORE: free text is not imported or emitted in evidence; retain only row/error counts."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="02_danh_sach_nhan_vien.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=18,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("employee_code",),
        target_entities=("Account", "AccountRole", "ImportExternalReference"),
        fields=(
            _f("employee_code", TEXT, True, "Persist", "ImportExternalReference.source_key", "source=employee; entity=Account", "Use as the non-PII external key; reject duplicates."),
            _f("full_name", TEXT, True, "Persist", "Account.full_name", None, "Trim and enforce the target length."),
            _f("username", TEXT, True, "Persist", "Account.username", "Account.tenant_id + Account.username", "Use as the account natural lookup; reject duplicate usernames in a tenant."),
            _f("email", TEXT, True, "Ignore-with-reason", None, None, "IGNORE: raw staff contact is not stored by the current account model or emitted in approved evidence."),
            _f("phone", TEXT, True, "Ignore-with-reason", None, None, "IGNORE: raw staff contact is not stored by the current account model or emitted in approved evidence."),
            _f("role", TEXT, True, "Persist", "AccountRole.role", "AccountRole.account_id + scope", "Normalize to lowercase and validate the backend role enum.", enum=ACCOUNT_ROLE),
            _f("department", TEXT, True, "Ignore-with-reason", None, None, "IGNORE: no department field exists in the current account model; preserve as a contract validation field."),
            _f("tenant_code", TEXT, True, "Derive", "tenant_id", "Tenant.code", "Resolve exactly one tenant."),
            _f("site_code", TEXT, False, "Derive", "site_id", "Site.tenant_id + Site.code", "Resolve when supplied; a tenant-level staff row may omit site."),
            _f("building_code", TEXT, False, "Derive", "building_id", "Building.site_id + Building.code", "Resolve when supplied; a site-level staff row may omit building."),
            _f("status", TEXT, True, "Persist", "Account.is_active", None, "Normalize the source status to a boolean active flag; reject unknown values."),
            _f("start_date", DATE, True, "Validate", "Account employment oracle", None, "Validate an ISO date; no employment-date column exists in the current model."),
            _f("notes", TEXT, False, "Ignore-with-reason", None, None, "IGNORE: free text is not imported or emitted in evidence."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="03_toa_nha_can_ho.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=12,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("site_code", "building_code", "unit_number"),
        target_entities=("Tenant", "Site", "Building", "Unit", "BillingAccount"),
        fields=(
            _f("tenant_code", TEXT, True, "Derive", "tenant_id", "Tenant.code", "Resolve exactly one tenant."),
            _f("site_code", TEXT, True, "Persist", "Site.code", "Site.tenant_id + Site.code", "Create or match only the explicitly approved site; reject conflict."),
            _f("site_name", TEXT, True, "Persist", "Site.name", "Site.tenant_id + Site.code", "Use the source name only after site-code identity matches."),
            _f("building_code", TEXT, True, "Persist", "Building.code", "Building.site_id + Building.code", "Create or match within the resolved site."),
            _f("building_name", TEXT, True, "Persist", "Building.name", "Building.site_id + Building.code", "Update only on an explicit conflict policy; otherwise reject mismatch."),
            _f("floors_count", INTEGER, True, "Persist", "Building.floors_count", None, "Require a positive integer."),
            _f("unit_number", TEXT, True, "Persist", "Unit.unit_number", "Unit.building_id + Unit.unit_number", "Preserve as text, including leading zeroes."),
            _f("floor", INTEGER, True, "Persist", "Unit.floor", None, "Require an integer within the building floor range."),
            _f("area_m2", DECIMAL, True, "Persist", "Unit.area_m2", None, "Parse Decimal and apply the approved quantization before the current Float column is written.", "FCS-04:AREA_PRECISION"),
            _f("unit_status", TEXT, True, "Persist", "Unit.status", None, "Normalize to lowercase and validate the unit status enum.", enum=UNIT_STATUS),
            _f("billing_account_number", TEXT, True, "Persist", "BillingAccount.account_number", "BillingAccount.site_id + BillingAccount.account_number", "Read as text to preserve identity and resolve exactly one unit account."),
            _f("billing_status", TEXT, True, "Persist", "BillingAccount.status", None, "Normalize/validate the billing account status enum.", enum=BILLING_ACCOUNT_STATUS),
            _f("resident_code", TEXT, False, "Derive", "UnitPersonRelationship.person_id", "ImportExternalReference.source_key=resident_code", "Resolve the resident mapping only when supplied; do not join by name."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="04_cu_dan.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=11,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("resident_code", "unit_number", "relationship_type"),
        target_entities=("Person", "UnitPersonRelationship", "ImportExternalReference"),
        fields=(
            _f("resident_code", TEXT, True, "Persist", "ImportExternalReference.source_key", "source=resident; entity=Person", "Use as a non-PII external key; reject duplicate source identity."),
            _f("full_name", TEXT, True, "Persist", "Person.full_name", None, "Trim and enforce the target length."),
            _f("phone_masked", TEXT, True, "Persist", "Person.phone_masked", None, "Accept only the masked representation; reject an unmasked pack."),
            _f("email_masked", TEXT, True, "Persist", "Person.email_masked", None, "Accept only the masked representation; reject an unmasked pack."),
            _f("relationship_type", TEXT, True, "Persist", "UnitPersonRelationship.relationship_type", None, "Normalize to lowercase and validate the relationship enum.", enum=RELATIONSHIP),
            _f("ownership_ratio", DECIMAL, True, "Persist", "UnitPersonRelationship.ownership_ratio", None, "Parse Decimal; canonicalize zero for non-owner rows to NULL.", "FCS-04:OWNERSHIP_ZERO"),
            _f("tenant_code", TEXT, True, "Derive", "tenant_id", "Tenant.code", "Resolve exactly one tenant."),
            _f("site_code", TEXT, True, "Derive", "site_id", "Site.tenant_id + Site.code", "Resolve within the tenant."),
            _f("building_code", TEXT, True, "Derive", "building_id", "Building.site_id + Building.code", "Resolve within the site."),
            _f("unit_number", TEXT, True, "Derive", "unit_id", "Unit.building_id + Unit.unit_number", "Resolve exactly one unit."),
            _f("valid_from", DATE, True, "Persist", "UnitPersonRelationship.valid_from", None, "Require an ISO date."),
            _f("valid_to", DATE, False, "Persist", "UnitPersonRelationship.valid_to", None, "Optional ISO date; must not precede valid_from."),
            _f("status", TEXT, True, "Validate", "relationship validity oracle", None, "Validate active/inactive semantics against the valid date range."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="05_tai_san_bao_tri.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=6,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("site_code", "asset_code"),
        target_entities=("Asset", "MaintenancePlan", "ImportExternalReference"),
        fields=(
            _f("asset_code", TEXT, True, "Persist", "Asset.code", "Asset.site_id + Asset.code", "Reject blank or duplicate asset code."),
            _f("asset_name", TEXT, True, "Persist", "Asset.name", None, "Trim and enforce the target length."),
            _f("asset_type", TEXT, True, "Validate", "Asset type metadata", None, "Validate against the approved maintenance category mapping; do not silently drop it.", "FCS-05:MAINTENANCE_CATEGORY"),
            _f("tenant_code", TEXT, True, "Derive", "tenant_id", "Tenant.code", "Resolve exactly one tenant."),
            _f("site_code", TEXT, True, "Derive", "site_id", "Site.tenant_id + Site.code", "Resolve within the tenant."),
            _f("building_code", TEXT, True, "Derive", "building_id", "Building.site_id + Building.code", "Resolve within the site."),
            _f("location", TEXT, True, "Validate", "Asset location metadata", None, "Validate against the approved location mapping; no implicit free-text join.", "FCS-05:MAINTENANCE_LOCATION"),
            _f("status", TEXT, True, "Persist", "Asset.status", None, "Normalize/validate ACTIVE, INACTIVE or RETIRED.", enum=("ACTIVE", "INACTIVE", "RETIRED")),
            _f("installed_on", DATE, True, "Validate", "Asset installation-date oracle", None, "Validate an ISO date; current Asset has no installation-date column."),
            _f("maintenance_plan_code", TEXT, True, "Persist", "MaintenancePlan.code", "MaintenancePlan.asset_id + MaintenancePlan.code", "Resolve repeated codes only after the duplicate-plan decision is recorded.", "FCS-05:MAINTENANCE_PLAN_CODE"),
            _f("interval_days", INTEGER, True, "Persist", "MaintenancePlan.interval_days", None, "Require 1..3650 days."),
            _f("next_due_date", DATE, True, "Derive", "MaintenancePlan.next_due_at", None, "Attach approved site timezone, store UTC, and derive from the plan schedule."),
            _f("vendor_name", TEXT, True, "Validate", "Maintenance vendor metadata", None, "Keep as a validation field until a target representation is approved.", "FCS-05:MAINTENANCE_VENDOR"),
            _f("responsible_username", TEXT, True, "Validate", "Maintenance responsibility metadata", "Account.tenant_id + Account.username", "Resolve the account but do not invent an owner column in MaintenancePlan.", "FCS-05:MAINTENANCE_OWNER"),
            _f("notes", TEXT, False, "Ignore-with-reason", None, None, "IGNORE: free text is not imported or emitted in evidence."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="06_ve_sinh.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=6,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("site_code", "shift_code"),
        target_entities=("CleaningRoute", "CleaningArea", "CleaningShift", "CleaningTask", "CleaningChecklistResult"),
        fields=(
            _f("shift_code", TEXT, True, "Persist", "ImportExternalReference.source_key", "source=cleaning; entity=CleaningShift", "Use as the non-PII shift key; reject duplicate shift identity."),
            _f("route_code", TEXT, True, "Persist", "CleaningRoute.code", "CleaningRoute.site_id + CleaningRoute.code", "Resolve exactly one route."),
            _f("area_code", TEXT, True, "Persist", "CleaningArea.code", "CleaningArea.site_id + CleaningArea.code", "Resolve exactly one area."),
            _f("site_code", TEXT, True, "Derive", "site_id", "Site.code", "Resolve within the tenant."),
            _f("building_code", TEXT, True, "Derive", "building_id", "Building.site_id + Building.code", "Resolve within the site."),
            _f("scheduled_start", DATETIME, True, "Persist", "CleaningShift.scheduled_start_at", None, "Attach the approved site timezone and store UTC.", "FCS-01:TIMEZONE"),
            _f("scheduled_end", DATETIME, True, "Persist", "CleaningShift.scheduled_end_at", None, "Require end after start; attach site timezone and store UTC.", "FCS-01:TIMEZONE"),
            _f("assignee_username", TEXT, True, "Derive", "CleaningTask.assigned_to_id", "Account.tenant_id + Account.username", "Resolve an in-scope cleaning account."),
            _f("status", TEXT, True, "Persist", "CleaningShift.status", None, "Normalize/validate the cleaning state machine.", enum=CLEANING_STATUS),
            _f("checklist_floor", TEXT, True, "Derive", "CleaningChecklistResult.result", None, "Normalize the floor checklist result.", "FCS-05:CLEANING_MASTER", CHECKLIST_RESULT + ("REWORK",)),
            _f("checklist_bins", TEXT, True, "Derive", "CleaningChecklistResult.result", None, "Normalize the bin checklist result.", "FCS-05:CLEANING_MASTER", CHECKLIST_RESULT + ("REWORK",)),
            _f("quality_result", TEXT, True, "Derive", "CleaningChecklistResult.result", None, "Normalize and apply PASS/FAIL/rework state transitions.", "FCS-05:CLEANING_MASTER", CHECKLIST_RESULT + ("REWORK",)),
            _f("rework_required", BOOLEAN, True, "Derive", "CleaningTask.status", None, "Translate true to FAIL -> REWORK_REQUIRED while retaining prior history."),
            _f("notes", TEXT, False, "Ignore-with-reason", None, None, "IGNORE: free text is not imported or emitted in evidence."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="07_an_ninh_tuan_tra.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=6,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("building_code", "shift_code", "patrol_point_code", "window_start"),
        target_entities=("SecurityShift", "PatrolPoint", "PatrolWindow", "PatrolLog", "SecurityShiftHandoff"),
        fields=(
            _f("shift_code", TEXT, True, "Persist", "ImportExternalReference.source_key", "source=security; entity=SecurityShift", "Use as the non-PII shift key."),
            _f("site_code", TEXT, True, "Derive", "site_id", "Site.code", "Resolve within the tenant."),
            _f("building_code", TEXT, True, "Derive", "building_id", "Building.site_id + Building.code", "Resolve within the site."),
            _f("guard_username", TEXT, True, "Derive", "SecurityShift.assigned_to_id", "Account.tenant_id + Account.username", "Resolve an in-scope security account."),
            _f("scheduled_start", DATETIME, True, "Persist", "SecurityShift.scheduled_start_at", None, "Attach the approved site timezone and store UTC.", "FCS-01:TIMEZONE"),
            _f("scheduled_end", DATETIME, True, "Persist", "SecurityShift.scheduled_end_at", None, "Require end after start; attach site timezone and store UTC.", "FCS-01:TIMEZONE"),
            _f("patrol_point_code", TEXT, True, "Persist", "PatrolPoint.code", "PatrolPoint.building_id + PatrolPoint.code", "Resolve exactly one patrol point."),
            _f("window_start", DATETIME, True, "Persist", "PatrolWindow.window_start_at", None, "Attach site timezone and store UTC.", "FCS-01:TIMEZONE"),
            _f("window_end", DATETIME, True, "Persist", "PatrolWindow.window_end_at", None, "Require end after start; attach site timezone and store UTC.", "FCS-01:TIMEZONE"),
            _f("patrol_status", TEXT, True, "Persist", "PatrolWindow.status", None, "Normalize/validate scheduled, completed, missed or cancelled.", enum=PATROL_STATUS),
            _f("event_type", TEXT, False, "Persist", "PatrolLog.event_type", None, "Validate against the approved patrol event mapping when a patrol event exists."),
            _f("incident_code", TEXT, False, "Derive", "SecurityIncident.code", "site_code + incident_code", "Resolve only when supplied; never create an incident from a blank code."),
            _f("handoff_summary", TEXT, False, "Persist", "SecurityShiftHandoff.summary", None, "Persist through a handoff command only when the source contains a handoff summary.", "FCS-05:PATROL_HANDOFF"),
            _f("notes", TEXT, False, "Ignore-with-reason", None, None, "IGNORE: free text is not imported or emitted in evidence."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="08_su_co_an_ninh.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=6,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("site_code", "incident_code"),
        target_entities=("SecurityIncident", "IncidentEscalation", "SecurityIncidentEvidence"),
        fields=(
            _f("incident_code", TEXT, True, "Persist", "SecurityIncident.code", "SecurityIncident.site_id + SecurityIncident.code", "Reject blank or duplicate incident code."),
            _f("incident_type", TEXT, True, "Persist", "SecurityIncident.incident_type", None, "Require the domain incident type enum before apply.", "FCS-05:INCIDENT_TYPE", enum=SECURITY_INCIDENT_TYPE),
            _f("severity", TEXT, True, "Persist", "SecurityIncident.severity", None, "Normalize/validate the severity enum.", enum=SECURITY_SEVERITY),
            _f("status", TEXT, True, "Persist", "SecurityIncident.status", None, "Apply only legal incident transitions; high severity requires closure checks.", enum=SECURITY_STATUS),
            _f("tenant_code", TEXT, True, "Derive", "tenant_id", "Tenant.code", "Resolve exactly one tenant."),
            _f("site_code", TEXT, True, "Derive", "site_id", "Site.tenant_id + Site.code", "Resolve within the tenant."),
            _f("building_code", TEXT, True, "Derive", "building_id", "Building.site_id + Building.code", "Resolve within the site."),
            _f("location", TEXT, True, "Persist", "SecurityIncident.title/location metadata", None, "Keep a structured location only after the incident mapping decision.", "FCS-05:INCIDENT_LOCATION"),
            _f("reported_at", DATETIME, True, "Persist", "SecurityIncident.occurred_at", None, "Attach approved site timezone and store UTC.", "FCS-01:TIMEZONE"),
            _f("reported_by_username", TEXT, True, "Derive", "SecurityIncident.reported_by_id", "Account.tenant_id + Account.username", "Resolve an in-scope account."),
            _f("owner_username", TEXT, False, "Derive", "Incident owner/assignee", "Account.tenant_id + Account.username", "Resolve when supplied; a NEW incident may have no owner yet.", "FCS-05:INCIDENT_OWNER"),
            _f("resolved_at", DATETIME, False, "Derive", "SecurityIncident.resolved_at", None, "Use only through a legal transition; future timestamps cannot resolve an incident.", "FCS-04:FUTURE_TIME"),
            _f("description", TEXT, True, "Persist", "SecurityIncident.description", None, "Trim and enforce the target length."),
            _f("notes", TEXT, False, "Ignore-with-reason", None, None, "IGNORE: free text is not imported or emitted in evidence."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="09_chinh_sach_phi.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=5,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("building_code", "fee_policy_code", "version_number"),
        target_entities=("FeePolicy", "FeePolicyVersion", "AccountingPeriod"),
        fields=(
            _f("fee_policy_code", TEXT, True, "Persist", "FeePolicy.code", "FeePolicy.building_id + FeePolicy.code", "Reject blank or duplicate policy code."),
            _f("fee_policy_name", TEXT, True, "Persist", "FeePolicy.name", None, "Trim and enforce the target length."),
            _f("tenant_code", TEXT, True, "Derive", "tenant_id", "Tenant.code", "Resolve exactly one tenant."),
            _f("site_code", TEXT, True, "Derive", "site_id", "Site.tenant_id + Site.code", "Resolve within the tenant."),
            _f("building_code", TEXT, True, "Derive", "building_id", "Building.site_id + Building.code", "Resolve within the site."),
            _f("version_number", INTEGER, True, "Persist", "FeePolicyVersion.version_number", "fee_policy_id + version_number", "Require a positive integer and one version per policy."),
            _f("effective_from", DATE, True, "Persist", "FeePolicyVersion.effective_from", None, "Require a valid date."),
            _f("effective_to", DATE, False, "Persist", "FeePolicyVersion.effective_to", None, "Optional date; must not precede effective_from."),
            _f("unit_rate_vnd", DECIMAL, True, "Persist", "FeePolicyVersion.unit_rate_vnd", None, "Parse Decimal, require non-negative VND, and quantize at the service boundary."),
            _f("basis", TEXT, True, "Persist", "FeePolicyVersion.basis", None, "Normalize/validate the billing basis.", enum=("UNIT_AREA_M2",)),
            _f("rounding_unit_vnd", DECIMAL, True, "Persist", "FeePolicyVersion.rounding_unit_vnd", None, "Parse Decimal and require a positive rounding unit."),
            _f("period_key", TEXT, True, "Persist", "AccountingPeriod.period_key", "Building.accounting_periods.period_key", "Validate YYYY-MM and de-duplicate within a building."),
            _f("period_start", DATE, True, "Persist", "AccountingPeriod.period_start", None, "Require period_end >= period_start."),
            _f("period_end", DATE, True, "Persist", "AccountingPeriod.period_end", None, "Require period_end >= period_start."),
            _f("cutoff_at", DATETIME, True, "Persist", "AccountingPeriod.cutoff_at", None, "Attach approved site timezone and store UTC.", "FCS-01:TIMEZONE"),
            _f("period_status", TEXT, True, "Persist", "AccountingPeriod.status", None, "Normalize/validate the accounting-period state.", enum=PERIOD_STATUS),
            _f("policy_status", TEXT, True, "Persist", "FeePolicy.is_active", None, "Normalize the policy active flag and reject unknown values."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="10_hoa_don.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=8,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("site_code", "invoice_number", "line_code"),
        target_entities=("BillingRun", "BillingInvoice", "BillingInvoiceItem"),
        canonical_inputs_missing=("fee_policy_code",),
        fields=(
            _f("invoice_number", TEXT, True, "Validate", "BillingInvoice.invoice_number", "site_code + invoice_number", "Use the file as an oracle; invoices are generated by Billing Run, never inserted from this file."),
            _f("billing_account_number", TEXT, True, "Derive", "BillingInvoice.billing_account_id", "BillingAccount.site_id + BillingAccount.account_number", "Resolve exactly one billing account."),
            _f("tenant_code", TEXT, True, "Derive", "tenant_id", "Tenant.code", "Resolve exactly one tenant."),
            _f("site_code", TEXT, True, "Derive", "site_id", "Site.tenant_id + Site.code", "Resolve within the tenant."),
            _f("building_code", TEXT, True, "Derive", "building_id", "Building.site_id + Building.code", "Resolve within the site."),
            _f("unit_number", TEXT, True, "Derive", "unit_id", "Unit.building_id + Unit.unit_number", "Resolve exactly one unit."),
            _f("period_key", TEXT, True, "Derive", "AccountingPeriod.id", "Building.accounting_periods.period_key", "Resolve one accounting period."),
            _f("billing_run_key", TEXT, True, "Derive", "BillingRun.run_key", "BillingRun.site_id + BillingRun.run_key", "Resolve the generated Billing Run; never create a duplicate run from the oracle."),
            _f("policy_version", INTEGER, True, "Derive", "FeePolicyVersion.id", "fee_policy + version_number", "Resolve the version used by Billing Run."),
            _f("invoice_status", TEXT, True, "Validate", "BillingInvoice.status", None, "Compare generated state; do not write status directly.", enum=INVOICE_STATUS),
            _f("issued_on", DATE, True, "Validate", "BillingInvoice.issued_on", None, "Compare generated invoice date."),
            _f("due_on", DATE, True, "Validate", "BillingInvoice.due_on", None, "Compare generated due date."),
            _f("total_vnd", DECIMAL, True, "Validate", "BillingInvoice.total_vnd", None, "Compare generated total; require sum(items) == total."),
            _f("outstanding_vnd", DECIMAL, True, "Validate", "BillingInvoice.outstanding_vnd", None, "Compare generated outstanding balance."),
            _f("line_code", TEXT, True, "Validate", "BillingInvoiceItem.line_number/source reference", None, "Compare generated line identity; no direct item insert."),
            _f("line_description", TEXT, True, "Validate", "BillingInvoiceItem.description", None, "Compare generated description."),
            _f("basis_quantity", DECIMAL, True, "Validate", "BillingInvoiceItem.basis_quantity", None, "Compare generated Decimal quantity."),
            _f("unit_rate_vnd_snapshot", DECIMAL, True, "Validate", "BillingInvoiceItem.unit_rate_vnd_snapshot", None, "Compare generated VND snapshot."),
            _f("rounding_unit_vnd_snapshot", DECIMAL, True, "Validate", "BillingInvoiceItem.rounding_unit_vnd_snapshot", None, "Compare generated rounding unit."),
            _f("amount_vnd", DECIMAL, True, "Validate", "BillingInvoiceItem.amount_vnd", None, "Compare generated amount and sum reconciliation."),
            _f("notes", TEXT, False, "Ignore-with-reason", None, None, "IGNORE: free text is not imported or emitted in evidence."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="11_thanh_toan.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=8,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("site_code", "source_reference", "receipt_number"),
        target_entities=("Payment", "PaymentAllocation", "UnmatchedPayment", "OverpaymentCredit"),
        canonical_inputs_missing=("period_key",),
        fields=(
            _f("source_reference", TEXT, True, "Persist", "Payment.source_reference", "tenant/site/payment_source/source_reference", "Use as a non-PII idempotency key; reject conflict."),
            _f("receipt_number", TEXT, True, "Persist", "Payment.receipt_number", "tenant/site/receipt_number", "Reject duplicate receipt number."),
            _f("payment_source", TEXT, True, "Persist", "Payment.payment_source", None, "Normalize/validate the payment source enum.", enum=PAYMENT_SOURCE),
            _f("tenant_code", TEXT, True, "Derive", "tenant_id", "Tenant.code", "Resolve exactly one tenant."),
            _f("site_code", TEXT, True, "Derive", "site_id", "Site.tenant_id + Site.code", "Resolve within the tenant."),
            _f("building_code", TEXT, True, "Derive", "building_id", "Building.site_id + Building.code", "Resolve within the site."),
            _f("billing_account_number", TEXT, False, "Derive", "Payment.billing_account_id", "BillingAccount.site_id + BillingAccount.account_number", "Resolve when supplied; unmatched payments remain explicit."),
            _f("received_at", DATETIME, True, "Persist", "Payment.received_at", None, "Attach approved site timezone and store UTC.", "FCS-01:TIMEZONE"),
            _f("amount_vnd", DECIMAL, True, "Persist", "Payment.amount_vnd", None, "Parse Decimal and require a positive VND amount."),
            _f("status", TEXT, True, "Validate", "Payment.status", None, "Replay through payment transitions and compare final status.", enum=PAYMENT_STATUS),
            _f("matched_invoice_number", TEXT, False, "Derive", "PaymentAllocation.billing_invoice_id", "BillingInvoice.site_id + BillingInvoice.invoice_number", "Resolve exactly one invoice when supplied; never match by amount alone."),
            _f("allocated_vnd", DECIMAL, False, "Validate", "PaymentAllocation.amount_vnd", None, "Compare allocation produced by the command service."),
            _f("unmatched_reason", TEXT, False, "Derive", "UnmatchedPayment.reason", None, "Create only through the unmatched-payment state path."),
            _f("overpayment_vnd", DECIMAL, False, "Derive", "OverpaymentCredit.remaining_vnd", None, "Create only through the overpayment-credit state path."),
            _f("received_by_username", TEXT, True, "Derive", "Payment.received_by_id", "Account.tenant_id + Account.username", "Resolve an in-scope account."),
            _f("notes", TEXT, False, "Ignore-with-reason", None, None, "IGNORE: free text is not imported or emitted in evidence."),
        ),
        open_decisions=(),
    ),
    WorkbookContract(
        file_name="12_buu_pham.xlsx",
        schema_version=CONTRACT_VERSION,
        expected_data_rows=6,
        data_sheet=SOURCE_SHEET,
        guide_sheet=GUIDE_SHEET,
        natural_key=("site_code", "parcel_code"),
        target_entities=("Parcel", "CaseRecord", "ImportExternalReference"),
        fields=(
            _f("parcel_code", TEXT, True, "Persist", "Parcel.parcel_code", "Parcel.site_id + Parcel.parcel_code", "Reject blank or duplicate parcel code."),
            _f("site_code", TEXT, True, "Derive", "site_id", "Site.code", "Resolve within the tenant."),
            _f("building_code", TEXT, True, "Derive", "building_id", "Building.site_id + Building.code", "Resolve within the site."),
            _f("unit_number", TEXT, True, "Derive", "unit_id", "Unit.building_id + Unit.unit_number", "Resolve exactly one unit."),
            _f("recipient_name_snapshot", TEXT, True, "Persist", "Parcel.recipient_name_snapshot", None, "Persist only within the approved local scope; do not use as a join key."),
            _f("recipient_contact_masked", TEXT, True, "Persist", "Parcel.recipient_contact_snapshot", None, "Accept only the masked representation."),
            _f("received_at", DATETIME, True, "Persist", "Parcel.received_at", None, "Attach approved site timezone and store UTC.", "FCS-01:TIMEZONE"),
            _f("status", TEXT, True, "Validate", "Parcel.status", None, "Replay legal parcel transitions; never write a terminal status directly.", enum=PARCEL_STATUS),
            _f("storage_location", TEXT, True, "Persist", "Parcel.storage_location", None, "Trim and enforce the target length."),
            _f("ready_at", DATETIME, False, "Derive", "Parcel.ready_for_pickup_at", None, "Use only when the state machine allows READY_FOR_PICKUP.", "FCS-04:FUTURE_TIME"),
            _f("handed_over_at", DATETIME, False, "Derive", "Parcel.handed_over_at", None, "Use only through handover command and never without PIN verification.", "FCS-05:PARCEL_PIN"),
            _f("pin_attempt_count", INTEGER, True, "Validate", "Parcel.pin_attempt_count", None, "Validate state metadata; never import or emit a plaintext PIN."),
            _f("case_required", BOOLEAN, True, "Derive", "CaseRecord", None, "Create a case only through the parcel exception/case command.", "FCS-05:PARCEL_EXCEPTION"),
            _f("notes", TEXT, False, "Ignore-with-reason", None, None, "IGNORE: free text is not imported or emitted in evidence."),
        ),
        open_decisions=(),
    ),
)


def contract_as_dict() -> dict[str, object]:
    """Return a JSON-safe representation used by preflight and consistency checks."""

    return {
        "contract_version": CONTRACT_VERSION,
        "status": "OWNER_APPROVED_SOURCE_CORRECTION_PENDING",
        "source_sheet": SOURCE_SHEET,
        "guide_sheet": GUIDE_SHEET,
        "timezone": "Asia/Ho_Chi_Minh",
        "timezone_status": "OWNER_APPROVED_2026-09-27",
        "dispositions": sorted(DISPOSITIONS),
        "workbooks": [asdict(workbook) for workbook in WORKBOOK_CONTRACTS],
    }


def contract_fingerprint() -> str:
    """Return a stable fingerprint for the machine-readable contract."""

    payload = json.dumps(contract_as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def validate_contract() -> tuple[str, ...]:
    """Validate completeness without opening the database or raw cell values."""

    errors: list[str] = []
    if len(WORKBOOK_CONTRACTS) != 12:
        errors.append("expected exactly 12 workbook contracts")
    file_names = [workbook.file_name for workbook in WORKBOOK_CONTRACTS]
    if len(file_names) != len(set(file_names)):
        errors.append("workbook file names must be unique")

    for workbook in WORKBOOK_CONTRACTS:
        names = [field.source_name for field in workbook.fields]
        if len(names) != len(set(names)):
            errors.append(f"{workbook.file_name}: duplicate source field")
        missing_keys = set(workbook.natural_key) - set(names)
        if missing_keys:
            errors.append(f"{workbook.file_name}: natural key not present: {sorted(missing_keys)}")
        for field in workbook.fields:
            if field.disposition not in DISPOSITIONS:
                errors.append(f"{workbook.file_name}.{field.source_name}: invalid disposition")
            if not field.rule.strip():
                errors.append(f"{workbook.file_name}.{field.source_name}: missing rule")
            if field.disposition == "Ignore-with-reason" and not field.rule.startswith("IGNORE:"):
                errors.append(f"{workbook.file_name}.{field.source_name}: ignore reason is not explicit")
            if field.disposition != "Ignore-with-reason" and not field.target:
                errors.append(f"{workbook.file_name}.{field.source_name}: missing target")
            if field.enum and field.value_type != TEXT:
                errors.append(f"{workbook.file_name}.{field.source_name}: enum must be text")
        if workbook.expected_data_rows <= 0:
            errors.append(f"{workbook.file_name}: expected row count must be positive")
    return tuple(errors)


if __name__ == "__main__":
    problems = validate_contract()
    if problems:
        for problem in problems:
            print(problem)
        raise SystemExit(1)
    print(f"FCS03_CONTRACT=PASS workbooks={len(WORKBOOK_CONTRACTS)} fingerprint={contract_fingerprint()}")
