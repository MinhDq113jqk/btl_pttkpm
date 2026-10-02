"""Controlled loader for the approved GreenCity submission data.

Usage is intentionally explicit:

    python backend/scripts/load_submission_data.py --source <pack> --manifest <manifest> --stage all --dry-run
    python backend/scripts/load_submission_data.py --source <pack> --stage master --apply
    python backend/scripts/load_submission_data.py --source <pack> --stage references --apply
    python backend/scripts/load_submission_data.py --source <pack> --stage replay --apply
    python backend/scripts/load_submission_data.py --source <pack> --stage all --verify

The loader never reads credentials from XLSX.  Apply requires a local ignored
JSON file named by ``GREENCITY_SUBMISSION_CREDENTIALS_FILE`` with a mapping of
username to one-time password.  Passwords are hashed immediately and
``must_change_password`` remains true.

Replay rows ending in ``CLOSED`` also require
``GREENCITY_SUBMISSION_EVIDENCE_DIR``.  The directory is local-only and must
contain ``<work_code>.png``, ``.jpg``, ``.jpeg`` or ``.bin`` files; the replay
validates the image signature before writing it to private storage.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping
from uuid import UUID, uuid4

# Keep the documented ``python backend/scripts/load_submission_data.py`` form
# equivalent to ``python -m scripts.load_submission_data`` from backend/.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.config import Settings
from app.core.database import Database
from app.core.security import hash_password
from app.models.account import Account, AccountRole
from app.models.billing import AccountingPeriod, BillingAccount, FeePolicy, FeePolicyVersion
from app.models.building import Building
from app.models.maintenance import Asset, MaintenancePlan
from app.models.operations import (
    CleaningArea,
    CleaningChecklistResult,
    CleaningRoute,
    CleaningRouteStop,
    CleaningShift,
    CleaningTask,
    PatrolPoint,
    PatrolWindow,
    SecurityIncident,
    SecurityShift,
)
from app.models.parcel import Parcel
from app.models.person import Person, UnitPersonRelationship
from app.models.service import ServiceCategory
from app.models.site import Site
from app.models.submission_import import SubmissionExternalReference, SubmissionImportRun
from app.models.tenant import Tenant
from app.models.unit import Unit
from app.services.submission_data_contract import CONTRACT_VERSION
from app.services.submission_data_import import (
    SubmissionImportError,
    assert_apply_allowed,
    manifest_summary,
    mark_run_status,
    start_import_run,
    upsert_external_reference,
)
from app.services.submission_data_mapping import derive_fee_policy_code, derive_period_key
from app.services.submission_data_replay import replay_service_requests
from app.services.submission_data_operational_replay import (
    replay_billing_run,
    replay_maintenance_cleaning,
    replay_payment_allocations,
    replay_security_parcels,
)
from app.services.submission_data_normalization import (
    normalize_area_m2,
    normalize_date,
    normalize_decimal,
    normalize_enum,
    normalize_money_vnd,
    normalize_temporal,
)
try:
    from scripts.submission_data_preflight import run_preflight
except ModuleNotFoundError:  # direct ``python backend/scripts/...`` execution
    from submission_data_preflight import run_preflight
from app.services.submission_data_reader import SubmissionPack, iter_submission_rows, read_submission_pack
try:
    from scripts.submission_data_reconcile import reconcile_submission_pack
except ModuleNotFoundError:  # direct ``python backend/scripts/...`` execution
    from submission_data_reconcile import reconcile_submission_pack


UNKNOWN_OPENED_ON = date(1970, 1, 1)
LOCAL_ADDRESS_PLACEHOLDER = "Địa chỉ chưa có trong nguồn dữ liệu đã duyệt"
MASTER_FILES = frozenset({"02_danh_sach_nhan_vien.xlsx", "03_toa_nha_can_ho.xlsx", "04_cu_dan.xlsx"})
REFERENCE_FILES = frozenset({
    "01_cong_viec.xlsx", "05_tai_san_bao_tri.xlsx", "06_ve_sinh.xlsx",
    "07_an_ninh_tuan_tra.xlsx", "08_su_co_an_ninh.xlsx", "09_chinh_sach_phi.xlsx",
    "12_buu_pham.xlsx",
})


def _rows(pack: SubmissionPack, file_name: str) -> list[dict[str, object]]:
    return [
        row for workbook, _, row in iter_submission_rows(pack)
        if workbook.file_name == file_name
    ]


def _rows_with_tenant(pack: SubmissionPack, file_name: str) -> list[dict[str, object]]:
    """Derive omitted tenant codes only from an unambiguous source structure."""

    structure: dict[tuple[str, str], str] = {}
    for row in _rows(pack, "03_toa_nha_can_ho.xlsx"):
        key = (_norm(row.get("site_code")), _norm(row.get("building_code")))
        tenant_code = _required(row.get("tenant_code"), "TENANT_CODE_REQUIRED")
        prior = structure.setdefault(key, tenant_code)
        if _norm(prior) != _norm(tenant_code):
            raise SubmissionImportError("STRUCTURE_CONTEXT_AMBIGUOUS")
    enriched = []
    for row in _rows(pack, file_name):
        if _text(row.get("tenant_code")):
            enriched.append(row)
            continue
        key = (_norm(row.get("site_code")), _norm(row.get("building_code")))
        tenant_code = structure.get(key)
        if tenant_code is None:
            raise SubmissionImportError("STRUCTURE_CONTEXT_NOT_FOUND")
        enriched.append({**row, "tenant_code": tenant_code})
    return enriched


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: object) -> str:
    return _text(value).casefold()


def _required(value: object, code: str) -> str:
    result = _text(value)
    if not result:
        raise SubmissionImportError(code)
    return result


def _utc(value: object, *, field: str) -> datetime:
    result = normalize_temporal(value, field=field, as_of_utc=datetime.max.replace(tzinfo=UTC))
    return result.utc


def _credential_map() -> dict[str, str]:
    path_value = os.getenv("GREENCITY_SUBMISSION_CREDENTIALS_FILE", "").strip()
    if not path_value:
        raise SubmissionImportError("SUBMISSION_CREDENTIALS_REQUIRED")
    path = Path(path_value)
    if not path.is_file() or path.name in {".env", ".env.example"}:
        raise SubmissionImportError("SUBMISSION_CREDENTIALS_FILE_INVALID")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SubmissionImportError("SUBMISSION_CREDENTIALS_FILE_INVALID") from exc
    if not isinstance(payload, dict) or not payload:
        raise SubmissionImportError("SUBMISSION_CREDENTIALS_FILE_INVALID")
    result: dict[str, str] = {}
    for username, password in payload.items():
        if not isinstance(username, str) or not isinstance(password, str) or len(password.encode("utf-8")) < 16:
            raise SubmissionImportError("SUBMISSION_CREDENTIALS_INVALID")
        result[username.strip()] = password
    return result


def _tenant(session, code: str) -> Tenant:
    matches = session.scalars(select(Tenant).where(Tenant.code == code).with_for_update()).all()
    if len(matches) > 1:
        raise SubmissionImportError("TENANT_AMBIGUOUS")
    if matches:
        return matches[0]
    tenant = Tenant(code=code, name=code)
    session.add(tenant)
    session.flush()
    return tenant


def _site(session, tenant: Tenant, row: Mapping[str, object]) -> Site:
    code = _required(row.get("site_code"), "SITE_CODE_REQUIRED")
    records = session.scalars(select(Site).where(Site.tenant_id == tenant.id, Site.code == code).with_for_update()).all()
    if len(records) > 1:
        raise SubmissionImportError("SITE_AMBIGUOUS")
    name = _required(row.get("site_name"), "SITE_NAME_REQUIRED")
    if records:
        if records[0].name != name:
            raise SubmissionImportError("SITE_METADATA_CONFLICT")
        return records[0]
    site = Site(tenant_id=tenant.id, code=code, name=name, address=LOCAL_ADDRESS_PLACEHOLDER)
    session.add(site)
    session.flush()
    return site


def _building(session, site: Site, row: Mapping[str, object]) -> Building:
    code = _required(row.get("building_code"), "BUILDING_CODE_REQUIRED")
    records = session.scalars(select(Building).where(Building.site_id == site.id, Building.code == code).with_for_update()).all()
    floors = row.get("floors_count")
    if not isinstance(floors, int) or floors < 1:
        raise SubmissionImportError("BUILDING_FLOORS_INVALID")
    name = _required(row.get("building_name"), "BUILDING_NAME_REQUIRED")
    if records:
        if records[0].name != name or records[0].floors_count != floors:
            raise SubmissionImportError("BUILDING_METADATA_CONFLICT")
        return records[0]
    building = Building(site_id=site.id, code=code, name=name, floors_count=floors)
    session.add(building)
    session.flush()
    return building


def _unit(session, building: Building, row: Mapping[str, object]) -> Unit:
    number = _required(row.get("unit_number"), "UNIT_NUMBER_REQUIRED")
    record = session.scalar(select(Unit).where(Unit.building_id == building.id, Unit.unit_number == number).with_for_update())
    area = float(normalize_area_m2(row.get("area_m2"), field="area_m2"))
    floor = row.get("floor")
    if not isinstance(floor, int) or not 1 <= floor <= building.floors_count:
        raise SubmissionImportError("UNIT_FLOOR_INVALID")
    status = normalize_enum(row.get("unit_status"), ("OCCUPIED", "VACANT", "RESERVED"), field="unit_status", output_case="lower")
    if record:
        if (record.floor, round(record.area_m2, 2), record.status) != (floor, round(area, 2), status):
            raise SubmissionImportError("UNIT_METADATA_CONFLICT")
        return record
    record = Unit(building_id=building.id, unit_number=number, floor=floor, area_m2=area, status=status, version=1)
    session.add(record)
    session.flush()
    return record


def _billing_account(session, tenant: Tenant, site: Site, building: Building, unit: Unit, row: Mapping[str, object]) -> BillingAccount:
    number = _required(row.get("billing_account_number"), "BILLING_ACCOUNT_NUMBER_REQUIRED")
    record = session.scalar(select(BillingAccount).where(BillingAccount.site_id == site.id, BillingAccount.account_number == number).with_for_update())
    status = normalize_enum(row.get("billing_status"), ("ACTIVE", "SUSPENDED", "CLOSED"), field="billing_status", output_case="preserve")
    if record:
        if record.unit_id != unit.id or record.status != status:
            raise SubmissionImportError("BILLING_ACCOUNT_METADATA_CONFLICT")
        return record
    record = BillingAccount(
        tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
        account_number=number, status=status, opened_on=UNKNOWN_OPENED_ON,
    )
    session.add(record)
    session.flush()
    return record


def _account(session, tenant: Tenant, row: Mapping[str, object], credentials: Mapping[str, str]) -> Account:
    username = _required(row.get("username"), "ACCOUNT_USERNAME_REQUIRED")
    record = session.scalar(select(Account).where(Account.tenant_id == tenant.id, Account.username == username).with_for_update())
    role = normalize_enum(row.get("role"), ("ADMIN", "DIRECTOR", "CSKH", "ACCOUNTANT", "TECHNICAL_LEAD", "TECHNICIAN", "CLEANING", "SECURITY", "RESIDENT"), field="role", output_case="lower")
    active = normalize_enum(row.get("status"), ("ACTIVE", "INACTIVE"), field="status", output_case="preserve") == "ACTIVE"
    if record:
        if record.full_name != _required(row.get("full_name"), "ACCOUNT_NAME_REQUIRED") or record.is_active != active:
            raise SubmissionImportError("ACCOUNT_METADATA_CONFLICT")
    else:
        password = credentials.get(username)
        if password is None:
            raise SubmissionImportError("SUBMISSION_CREDENTIAL_MISSING")
        record = Account(
            tenant_id=tenant.id,
            username=username,
            hashed_password=hash_password(password),
            full_name=_required(row.get("full_name"), "ACCOUNT_NAME_REQUIRED"),
            is_active=active,
            must_change_password=True,
            session_version=1,
        )
        session.add(record)
        session.flush()
    site_code = _text(row.get("site_code"))
    building_code = _text(row.get("building_code"))
    site = session.scalar(select(Site).where(Site.tenant_id == tenant.id, Site.code == site_code)) if site_code else None
    building = session.scalar(select(Building).where(Building.site_id == site.id, Building.code == building_code)) if site and building_code else None
    existing_role = session.scalar(select(AccountRole).where(
        AccountRole.account_id == record.id, AccountRole.role == role,
        AccountRole.site_id == (site.id if site else None), AccountRole.building_id == (building.id if building else None),
    ))
    if existing_role is None:
        session.add(AccountRole(account_id=record.id, role=role, site_id=site.id if site else None, building_id=building.id if building else None))
        session.flush()
    return record


def _person(session, tenant: Tenant, site: Site, building: Building, unit: Unit, row: Mapping[str, object], run) -> Person:
    resident_code = _required(row.get("resident_code"), "RESIDENT_CODE_REQUIRED")
    existing_ref = session.scalar(select(SubmissionExternalReference).where(
        SubmissionExternalReference.tenant_id == tenant.id,
        SubmissionExternalReference.source == "resident",
        SubmissionExternalReference.entity_type == "Person",
        SubmissionExternalReference.source_key == resident_code,
    ).with_for_update())
    if existing_ref:
        person = session.get(Person, existing_ref.target_id)
        if person is None:
            raise SubmissionImportError("EXTERNAL_REFERENCE_TARGET_MISSING")
    else:
        person = Person(
            tenant_id=tenant.id,
            full_name=_required(row.get("full_name"), "RESIDENT_NAME_REQUIRED"),
            phone_masked=_required(row.get("phone_masked"), "RESIDENT_PHONE_REQUIRED"),
            email_masked=_required(row.get("email_masked"), "RESIDENT_EMAIL_REQUIRED"),
        )
        session.add(person)
        session.flush()
        upsert_external_reference(
            session, run, tenant_id=tenant.id, source="resident", entity_type="Person",
            source_key=resident_code, target_id=person.id,
            payload={"resident_code": resident_code, "unit_number": unit.unit_number, "relationship_type": _text(row.get("relationship_type"))},
        )
    relationship = normalize_enum(row.get("relationship_type"), ("OWNER", "TENANT", "FAMILY_MEMBER"), field="relationship_type", output_case="lower")
    ratio = normalize_decimal(row.get("ownership_ratio"), field="ownership_ratio", quantum=Decimal("0.0001"))
    if relationship != "owner" and ratio == 0:
        ratio = None
    valid_from = normalize_date(row.get("valid_from"), field="valid_from")
    valid_to = normalize_date(row.get("valid_to"), field="valid_to") if row.get("valid_to") is not None else None
    existing_relationship = session.scalar(select(UnitPersonRelationship).where(
        UnitPersonRelationship.unit_id == unit.id,
        UnitPersonRelationship.person_id == person.id,
        UnitPersonRelationship.relationship_type == relationship,
        UnitPersonRelationship.valid_from == valid_from,
    ).with_for_update())
    if existing_relationship is None:
        session.add(UnitPersonRelationship(
            unit_id=unit.id, person_id=person.id, tenant_id=tenant.id, site_id=site.id,
            building_id=building.id, relationship_type=relationship, ownership_ratio=ratio,
            valid_from=valid_from, valid_to=valid_to,
        ))
        session.flush()
    return person


def load_master(session, pack: SubmissionPack, run, *, credentials: Mapping[str, str]) -> dict[str, int]:
    """Load tenant/site/building/unit/account/person master data idempotently."""

    structure_rows = _rows(pack, "03_toa_nha_can_ho.xlsx")
    contexts: dict[tuple[str, str, str], tuple[Tenant, Site, Building, Unit]] = {}
    for row in structure_rows:
        tenant = _tenant(session, _required(row.get("tenant_code"), "TENANT_CODE_REQUIRED"))
        site = _site(session, tenant, row)
        building = _building(session, site, row)
        unit = _unit(session, building, row)
        _billing_account(session, tenant, site, building, unit, row)
        contexts[(_norm(row.get("tenant_code")), _norm(row.get("site_code")), _norm(row.get("unit_number")))] = (tenant, site, building, unit)
        upsert_external_reference(
            session, run, tenant_id=tenant.id, source="unit", entity_type="Unit",
            source_key=f"{site.code}:{building.code}:{unit.unit_number}", target_id=unit.id,
            payload={"unit_number": unit.unit_number, "building_code": building.code},
        )
    for row in _rows(pack, "02_danh_sach_nhan_vien.xlsx"):
        tenant = _tenant(session, _required(row.get("tenant_code"), "TENANT_CODE_REQUIRED"))
        account = _account(session, tenant, row, credentials)
        upsert_external_reference(
            session, run, tenant_id=tenant.id, source="employee", entity_type="Account",
            source_key=_required(row.get("employee_code"), "EMPLOYEE_CODE_REQUIRED"), target_id=account.id,
            payload={"username": account.username, "role": _text(row.get("role"))},
        )
    for row in _rows(pack, "04_cu_dan.xlsx"):
        key = (_norm(row.get("tenant_code")), _norm(row.get("site_code")), _norm(row.get("unit_number")))
        context = contexts.get(key)
        if context is None:
            raise SubmissionImportError("UNIT_CONTEXT_NOT_FOUND")
        _person(session, *context, row, run)
    return {
        "tenants": session.query(Tenant).count(),
        "sites": session.query(Site).count(),
        "buildings": session.query(Building).count(),
        "units": session.query(Unit).count(),
        "billing_accounts": session.query(BillingAccount).count(),
        "accounts": session.query(Account).count(),
        "persons": session.query(Person).count(),
    }


def _reference_account(session, tenant_id: UUID, username: str) -> Account:
    account = session.scalar(select(Account).where(Account.tenant_id == tenant_id, Account.username == username))
    if account is None:
        raise SubmissionImportError("REFERENCE_ACCOUNT_NOT_FOUND")
    return account


def _reference_account_with_role(
    session,
    tenant_id: UUID,
    username: str,
    *,
    site_id: UUID,
    building_id: UUID,
    roles: tuple[str, ...],
    error_code: str,
) -> Account:
    """Resolve an account by its explicit username and scoped role grant.

    Reference loading must never infer an operator from a display name or use a
    tenant-wide fallback.  The account and the grant are therefore checked
    independently before a row can create an operational reference.
    """

    account = _reference_account(session, tenant_id, username)
    grants = session.scalars(select(AccountRole).where(
        AccountRole.account_id == account.id,
        AccountRole.role.in_(roles),
    )).all()
    if not any(
        grant.site_id == site_id
        and (grant.building_id is None or grant.building_id == building_id)
        for grant in grants
    ):
        raise SubmissionImportError(error_code)
    return account


def _reference_site_building(session, structure: Mapping[tuple[str, str], Mapping[str, object]], row: Mapping[str, object]):
    site_code = _required(row.get("site_code"), "SITE_CODE_REQUIRED")
    building_code = _required(row.get("building_code"), "BUILDING_CODE_REQUIRED")
    source = structure.get((_norm(site_code), _norm(building_code)))
    if source is None:
        raise SubmissionImportError("REFERENCE_STRUCTURE_NOT_FOUND")
    tenant = session.scalar(select(Tenant).where(Tenant.code == _required(source.get("tenant_code"), "TENANT_CODE_REQUIRED")))
    site = session.scalar(select(Site).where(Site.tenant_id == tenant.id, Site.code == site_code)) if tenant else None
    building = session.scalar(select(Building).where(Building.site_id == site.id, Building.code == building_code)) if site else None
    if tenant is None or site is None or building is None:
        raise SubmissionImportError("REFERENCE_SCOPE_NOT_FOUND")
    return tenant, site, building


def _deterministic_pin(parcel_code: str) -> str:
    secret = os.getenv("GREENCITY_SUBMISSION_PIN_SECRET", "").strip()
    if len(secret.encode("utf-8")) < 16:
        raise SubmissionImportError("SUBMISSION_PIN_SECRET_REQUIRED")
    digest = hmac.new(secret.encode("utf-8"), parcel_code.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:12]


def _reference_parcel_actor(session, tenant_id: UUID, site_id: UUID, building_id: UUID) -> Account:
    """Require one explicit site director as the import actor for parcel intake."""

    candidates = session.scalars(select(Account).join(AccountRole).where(
        Account.tenant_id == tenant_id,
        Account.is_active.is_(True),
        AccountRole.site_id == site_id,
        AccountRole.building_id.is_(None),
        AccountRole.role == "director",
    ).order_by(Account.id)).all()
    if len(candidates) != 1:
        raise SubmissionImportError("PARCEL_IMPORT_ACTOR_AMBIGUOUS")
    return candidates[0]


def load_references(session, pack: SubmissionPack, run) -> dict[str, int]:
    """Load idempotent reference rows without applying terminal source states."""

    counts = defaultdict(int)
    structure = {
        (_norm(row.get("site_code")), _norm(row.get("building_code"))): row
        for row in _rows(pack, "03_toa_nha_can_ho.xlsx")
    }

    # Category/SLA is the single reference used by FCS-12 replay.
    for row in _rows(pack, "01_cong_viec.xlsx"):
        tenant, site, building = _reference_site_building(session, structure, row)
        code = _required(row.get("request_type"), "CATEGORY_CODE_REQUIRED")
        created = _utc(row.get("created_at"), field="created_at")
        due = _utc(row.get("sla_due_at"), field="sla_due_at")
        sla = int((due - created).total_seconds() // 60)
        if sla <= 0:
            raise SubmissionImportError("CATEGORY_SLA_INVALID")
        existing = session.scalar(select(ServiceCategory).where(
            ServiceCategory.site_id == site.id, ServiceCategory.code == code,
        ).with_for_update())
        if existing and (existing.sla_minutes != sla or existing.name != code):
            raise SubmissionImportError("CATEGORY_SLA_CONFLICT")
        if existing is None:
            existing = ServiceCategory(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                code=code, name=code, sla_minutes=sla, is_active=True,
            )
            session.add(existing)
            session.flush()
        counts["service_category_rows"] += 1
    counts["service_categories"] = session.query(ServiceCategory).count()

    # Asset and maintenance plan metadata are immutable at the source boundary.
    for row in _rows(pack, "05_tai_san_bao_tri.xlsx"):
        tenant, site, building = _reference_site_building(session, structure, row)
        actor = _reference_account(session, tenant.id, _required(row.get("responsible_username"), "MAINTENANCE_OWNER_REQUIRED"))
        asset_code = _required(row.get("asset_code"), "ASSET_CODE_REQUIRED")
        asset_name = _required(row.get("asset_name"), "ASSET_NAME_REQUIRED")
        asset_status = normalize_enum(row.get("status"), ("ACTIVE", "INACTIVE", "RETIRED"), field="status", output_case="preserve")
        description = f"asset_type={_required(row.get('asset_type'), 'ASSET_TYPE_REQUIRED')}; location={_required(row.get('location'), 'ASSET_LOCATION_REQUIRED')}; source=approved-pack"
        asset = session.scalar(select(Asset).where(
            Asset.site_id == site.id, Asset.code == asset_code,
        ).with_for_update())
        if asset is None:
            asset = Asset(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                code=asset_code, name=asset_name, description=description,
                status=asset_status, created_by_id=actor.id, updated_by_id=actor.id,
            )
            session.add(asset)
            session.flush()
        elif (asset.name, asset.description, asset.status, asset.building_id) != (asset_name, description, asset_status, building.id):
            raise SubmissionImportError("ASSET_METADATA_CONFLICT")
        plan_code = _required(row.get("maintenance_plan_code"), "MAINTENANCE_PLAN_CODE_REQUIRED")
        interval_days = int(row["interval_days"])
        if not 1 <= interval_days <= 3650:
            raise SubmissionImportError("MAINTENANCE_INTERVAL_INVALID")
        next_due = _utc(row.get("next_due_date"), field="next_due_date")
        template = [{"label": "visual_inspection", "required": True}, {"label": "operational_check", "required": True}]
        plan = session.scalar(select(MaintenancePlan).where(
            MaintenancePlan.asset_id == asset.id, MaintenancePlan.code == plan_code,
        ).with_for_update())
        if plan is None:
            plan = MaintenancePlan(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                asset_id=asset.id, code=plan_code, title=plan_code,
                interval_days=interval_days, next_due_at=next_due,
                checklist_template=template, evidence_required=True, is_active=True,
                created_by_id=actor.id, updated_by_id=actor.id,
            )
            session.add(plan)
            session.flush()
        elif (plan.interval_days, plan.next_due_at, plan.checklist_template, plan.evidence_required) != (
            interval_days, next_due, template, True,
        ):
            raise SubmissionImportError("MAINTENANCE_PLAN_METADATA_CONFLICT")
        upsert_external_reference(
            session, run, tenant_id=tenant.id, source="maintenance", entity_type="Asset",
            source_key=asset_code, target_id=asset.id,
            payload={"asset_code": asset_code, "plan_code": plan_code},
        )
        counts["assets"] += 1
        counts["maintenance_plans"] += 1

    # Cleaning references are created in the initial PLANNED state.  Source
    # results/status are replay inputs for FCS-13 and never terminal writes here.
    for row in _rows(pack, "06_ve_sinh.xlsx"):
        tenant, site, building = _reference_site_building(session, structure, row)
        route_code = _required(row.get("route_code"), "CLEANING_ROUTE_REQUIRED")
        area_code = _required(row.get("area_code"), "CLEANING_AREA_REQUIRED")
        cleaner = _reference_account_with_role(
            session, tenant.id, _required(row.get("assignee_username"), "CLEANING_ASSIGNEE_REQUIRED"),
            site_id=site.id, building_id=building.id, roles=("cleaning",),
            error_code="CLEANING_ASSIGNEE_SCOPE_NOT_FOUND",
        )
        route = session.scalar(select(CleaningRoute).where(
            CleaningRoute.site_id == site.id, CleaningRoute.code == route_code,
        ).with_for_update())
        if route is None:
            route = CleaningRoute(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                code=route_code, name=route_code, is_active=True,
            )
            session.add(route)
            session.flush()
        elif route.building_id != building.id:
            raise SubmissionImportError("CLEANING_ROUTE_SCOPE_CONFLICT")
        area = session.scalar(select(CleaningArea).where(
            CleaningArea.site_id == site.id, CleaningArea.code == area_code,
        ).with_for_update())
        if area is None:
            area = CleaningArea(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                code=area_code, name=area_code, is_active=True,
            )
            session.add(area)
            session.flush()
        elif area.building_id != building.id:
            raise SubmissionImportError("CLEANING_AREA_SCOPE_CONFLICT")
        template = [
            {"label": "floor", "source": _required(row.get("checklist_floor"), "CLEANING_CHECKLIST_FLOOR_REQUIRED")},
            {"label": "bins", "source": _required(row.get("checklist_bins"), "CLEANING_CHECKLIST_BINS_REQUIRED")},
        ]
        stop = session.scalar(select(CleaningRouteStop).where(
            CleaningRouteStop.route_id == route.id, CleaningRouteStop.cleaning_area_id == area.id,
        ).with_for_update())
        if stop is None:
            last_position = session.scalar(select(CleaningRouteStop.position).where(
                CleaningRouteStop.route_id == route.id,
            ).order_by(CleaningRouteStop.position.desc()).limit(1)) or 0
            stop = CleaningRouteStop(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                route_id=route.id, cleaning_area_id=area.id,
                position=last_position + 1, checklist_template=template,
            )
            session.add(stop)
            session.flush()
        elif stop.checklist_template != template:
            raise SubmissionImportError("CLEANING_CHECKLIST_TEMPLATE_CONFLICT")
        start = _utc(row.get("scheduled_start"), field="scheduled_start")
        end = _utc(row.get("scheduled_end"), field="scheduled_end")
        if end <= start:
            raise SubmissionImportError("CLEANING_SHIFT_WINDOW_INVALID")
        shift_code = _required(row.get("shift_code"), "CLEANING_SHIFT_REQUIRED")
        existing_ref = session.scalar(select(SubmissionExternalReference).where(
            SubmissionExternalReference.tenant_id == tenant.id,
            SubmissionExternalReference.source == "cleaning",
            SubmissionExternalReference.entity_type == "CleaningShift",
            SubmissionExternalReference.source_key == f"{site.code}:{shift_code}",
        ).with_for_update())
        shift = session.get(CleaningShift, existing_ref.target_id) if existing_ref else session.scalar(select(CleaningShift).where(
            CleaningShift.route_id == route.id, CleaningShift.scheduled_start_at == start,
        ).with_for_update())
        if shift is None:
            shift = CleaningShift(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                route_id=route.id, scheduled_start_at=start, scheduled_end_at=end,
                status="PLANNED", created_by_id=cleaner.id, updated_by_id=cleaner.id,
            )
            session.add(shift)
            session.flush()
        elif (shift.route_id, shift.building_id, shift.scheduled_start_at, shift.scheduled_end_at) != (
            route.id, building.id, start, end,
        ):
            raise SubmissionImportError("CLEANING_SHIFT_METADATA_CONFLICT")
        task = session.scalar(select(CleaningTask).where(
            CleaningTask.shift_id == shift.id, CleaningTask.route_stop_id == stop.id,
        ).with_for_update())
        if task is None:
            task = CleaningTask(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                shift_id=shift.id, route_stop_id=stop.id, assigned_to_id=cleaner.id,
                status="PLANNED", created_by_id=cleaner.id, updated_by_id=cleaner.id,
            )
            session.add(task)
            session.flush()
        elif task.assigned_to_id != cleaner.id:
            raise SubmissionImportError("CLEANING_ASSIGNEE_CONFLICT")
        for position, label in enumerate(("floor", "bins", "quality"), 1):
            checklist = session.scalar(select(CleaningChecklistResult).where(
                CleaningChecklistResult.cleaning_task_id == task.id,
                CleaningChecklistResult.position == position,
            ).with_for_update())
            if checklist is None:
                session.add(CleaningChecklistResult(
                    cleaning_task_id=task.id, position=position, label=label,
                    is_required=True, result="PENDING",
                ))
        session.flush()
        source_status = normalize_enum(row.get("status"), ("PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"), field="cleaning_status", output_case="preserve")
        if not isinstance(row.get("rework_required"), bool):
            raise SubmissionImportError("CLEANING_REWORK_FLAG_INVALID")
        for field in ("checklist_floor", "checklist_bins", "quality_result"):
            normalize_enum(row.get(field), ("PENDING", "PASS", "FAIL", "NOT_APPLICABLE", "REWORK"), field=field, output_case="preserve")
        upsert_external_reference(
            session, run, tenant_id=tenant.id, source="cleaning", entity_type="CleaningShift",
            source_key=f"{site.code}:{shift_code}", target_id=shift.id,
            payload={
                "shift_code": shift_code, "source_status": source_status,
                "rework_required": row.get("rework_required"),
                "checklist": [row.get("checklist_floor"), row.get("checklist_bins"), row.get("quality_result")],
            },
        )
        counts["cleaning_routes"] += 1
        counts["cleaning_areas"] += 1
        counts["cleaning_route_stops"] += 1
        counts["cleaning_shifts"] += 1
        counts["cleaning_tasks"] += 1
        counts["cleaning_checklists"] += 3

    # Incidents are created before patrol rows so incident_code is a strict FK-like reference.
    for row in _rows(pack, "08_su_co_an_ninh.xlsx"):
        tenant, site, building = _reference_site_building(session, structure, row)
        incident_code = _required(row.get("incident_code"), "INCIDENT_CODE_REQUIRED")
        reported_by = _reference_account_with_role(
            session, tenant.id, _required(row.get("reported_by_username"), "INCIDENT_REPORTER_REQUIRED"),
            site_id=site.id, building_id=building.id, roles=("security", "cskh", "director", "admin"),
            error_code="INCIDENT_REPORTER_SCOPE_NOT_FOUND",
        )
        owner_username = _text(row.get("owner_username"))
        if owner_username:
            _reference_account_with_role(
                session, tenant.id, owner_username, site_id=site.id, building_id=building.id,
                roles=("security", "director", "admin"), error_code="INCIDENT_OWNER_SCOPE_NOT_FOUND",
            )
        incident_type = normalize_enum(row.get("incident_type"), ("SECURITY", "FIRE"), field="incident_type", output_case="preserve")
        severity = normalize_enum(row.get("severity"), ("LOW", "MEDIUM", "HIGH", "CRITICAL"), field="severity", output_case="preserve")
        source_status = normalize_enum(row.get("status"), ("NEW", "TRIAGED", "IN_PROGRESS", "RESOLVED", "CLOSED"), field="incident_status", output_case="preserve")
        occurred_at = _utc(row.get("reported_at"), field="reported_at")
        location = _required(row.get("location"), "INCIDENT_LOCATION_REQUIRED")
        title = f"{incident_type} @ {location}"[:200]
        description = _required(row.get("description"), "INCIDENT_DESCRIPTION_REQUIRED")
        incident = session.scalar(select(SecurityIncident).where(
            SecurityIncident.site_id == site.id, SecurityIncident.code == incident_code,
        ).with_for_update())
        if incident is None:
            incident = SecurityIncident(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                code=incident_code, incident_type=incident_type, severity=severity,
                status="NEW", title=title, description=description,
                occurred_at=occurred_at, reported_by_id=reported_by.id,
                created_by_id=reported_by.id, updated_by_id=reported_by.id,
            )
            session.add(incident)
            session.flush()
        elif (incident.building_id, incident.incident_type, incident.severity, incident.title, incident.description, incident.occurred_at, incident.reported_by_id) != (
            building.id, incident_type, severity, title, description, occurred_at, reported_by.id,
        ):
            raise SubmissionImportError("SECURITY_INCIDENT_METADATA_CONFLICT")
        if row.get("resolved_at") is not None:
            _utc(row.get("resolved_at"), field="resolved_at")
        upsert_external_reference(
            session, run, tenant_id=tenant.id, source="security", entity_type="SecurityIncident",
            source_key=f"{site.code}:{incident_code}", target_id=incident.id,
            payload={"incident_code": incident_code, "source_status": source_status, "owner_present": bool(owner_username)},
        )
        counts["security_incidents"] += 1

    # Patrol points/windows are also initial-state references.  Patrol logs and
    # handoffs remain FCS-14 commands because the source does not carry the
    # second handoff identity or an event timestamp.
    for row in _rows(pack, "07_an_ninh_tuan_tra.xlsx"):
        tenant, site, building = _reference_site_building(session, structure, row)
        guard = _reference_account_with_role(
            session, tenant.id, _required(row.get("guard_username"), "SECURITY_GUARD_REQUIRED"),
            site_id=site.id, building_id=building.id, roles=("security",),
            error_code="SECURITY_GUARD_SCOPE_NOT_FOUND",
        )
        start = _utc(row.get("scheduled_start"), field="scheduled_start")
        end = _utc(row.get("scheduled_end"), field="scheduled_end")
        window_start = _utc(row.get("window_start"), field="window_start")
        window_end = _utc(row.get("window_end"), field="window_end")
        if end <= start or window_end <= window_start or window_start < start or window_end > end:
            raise SubmissionImportError("SECURITY_WINDOW_INVALID")
        normalize_enum(row.get("patrol_status"), ("SCHEDULED", "COMPLETED", "MISSED", "CANCELLED"), field="patrol_status", output_case="preserve")
        event_type = _text(row.get("event_type"))
        if event_type:
            normalize_enum(event_type, ("CHECK_IN", "CHECK_OUT", "NOTE"), field="patrol_event_type", output_case="preserve")
        incident_code = _text(row.get("incident_code"))
        if incident_code:
            incident_ref = session.scalar(select(SubmissionExternalReference).where(
                SubmissionExternalReference.tenant_id == tenant.id,
                SubmissionExternalReference.source == "security",
                SubmissionExternalReference.entity_type == "SecurityIncident",
                SubmissionExternalReference.source_key == f"{site.code}:{incident_code}",
            ))
            if incident_ref is None:
                raise SubmissionImportError("SECURITY_INCIDENT_REFERENCE_NOT_FOUND")
        handoff_summary = _text(row.get("handoff_summary"))
        if handoff_summary:
            receivers = session.scalars(select(Account).join(AccountRole).where(
                Account.tenant_id == tenant.id, Account.is_active.is_(True),
                AccountRole.site_id == site.id, AccountRole.building_id == building.id,
                AccountRole.role == "security", Account.id != guard.id,
            ).order_by(Account.id)).all()
            if len(receivers) != 1:
                raise SubmissionImportError("SECURITY_HANDOFF_RECEIVER_AMBIGUOUS")
            counts["security_handoff_candidates"] += 1
        shift_code = _required(row.get("shift_code"), "SECURITY_SHIFT_REQUIRED")
        shift_ref_key = f"{site.code}:{building.code}:{shift_code}"
        shift_ref = session.scalar(select(SubmissionExternalReference).where(
            SubmissionExternalReference.tenant_id == tenant.id,
            SubmissionExternalReference.source == "security",
            SubmissionExternalReference.entity_type == "SecurityShift",
            SubmissionExternalReference.source_key == shift_ref_key,
        ).with_for_update())
        shift = session.get(SecurityShift, shift_ref.target_id) if shift_ref else session.scalar(select(SecurityShift).where(
            SecurityShift.building_id == building.id, SecurityShift.scheduled_start_at == start,
        ).with_for_update())
        if shift is None:
            shift = SecurityShift(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                assigned_to_id=guard.id, scheduled_start_at=start, scheduled_end_at=end,
                status="PLANNED", created_by_id=guard.id, updated_by_id=guard.id,
            )
            session.add(shift)
            session.flush()
        elif (shift.assigned_to_id, shift.scheduled_start_at, shift.scheduled_end_at, shift.building_id) != (
            guard.id, start, end, building.id,
        ):
            raise SubmissionImportError("SECURITY_SHIFT_METADATA_CONFLICT")
        point_code = _required(row.get("patrol_point_code"), "PATROL_POINT_REQUIRED")
        point = session.scalar(select(PatrolPoint).where(
            PatrolPoint.site_id == site.id, PatrolPoint.code == point_code,
        ).with_for_update())
        if point is None:
            point = PatrolPoint(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                code=point_code, name=point_code, is_active=True,
                created_by_id=guard.id, updated_by_id=guard.id,
            )
            session.add(point)
            session.flush()
        # Patrol points are site-scoped by the domain unique key.  The same
        # named lobby point may therefore be reused by windows in different
        # buildings of one site; the window keeps the concrete building scope.
        window = session.scalar(select(PatrolWindow).where(
            PatrolWindow.security_shift_id == shift.id,
            PatrolWindow.patrol_point_id == point.id,
            PatrolWindow.window_start_at == window_start,
        ).with_for_update())
        if window is None:
            window = PatrolWindow(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                security_shift_id=shift.id, patrol_point_id=point.id,
                window_start_at=window_start, window_end_at=window_end,
                status="SCHEDULED", created_by_id=guard.id, updated_by_id=guard.id,
            )
            session.add(window)
            session.flush()
        elif (window.window_end_at, window.building_id) != (window_end, building.id):
            raise SubmissionImportError("PATROL_WINDOW_METADATA_CONFLICT")
        upsert_external_reference(
            session, run, tenant_id=tenant.id, source="security", entity_type="SecurityShift",
            source_key=shift_ref_key, target_id=shift.id,
            payload={"shift_code": shift_code},
        )
        counts["security_shifts"] += 1
        counts["patrol_points"] += 1
        counts["patrol_windows"] += 1

    # Parcel records start at RECEIVED.  Ready/handed-over/exception states are
    # replay inputs and are deliberately not written in this reference stage.
    for row in _rows(pack, "12_buu_pham.xlsx"):
        tenant, site, building = _reference_site_building(session, structure, row)
        unit_number = _required(row.get("unit_number"), "PARCEL_UNIT_REQUIRED")
        unit = session.scalar(select(Unit).where(
            Unit.building_id == building.id, Unit.unit_number == unit_number,
        ))
        if unit is None:
            raise SubmissionImportError("PARCEL_UNIT_NOT_FOUND")
        parcel_code = _required(row.get("parcel_code"), "PARCEL_CODE_REQUIRED")
        source_status = normalize_enum(row.get("status"), ("RECEIVED", "READY_FOR_PICKUP", "HANDED_OVER", "RETURNED", "LOST", "DAMAGED"), field="parcel_status", output_case="preserve")
        if not isinstance(row.get("case_required"), bool):
            raise SubmissionImportError("PARCEL_CASE_FLAG_INVALID")
        pin = _deterministic_pin(parcel_code)
        actor = _reference_parcel_actor(session, tenant.id, site.id, building.id)
        received_at = _utc(row.get("received_at"), field="received_at")
        parcel = session.scalar(select(Parcel).where(
            Parcel.site_id == site.id, Parcel.parcel_code == parcel_code,
        ).with_for_update())
        if parcel is None:
            parcel = Parcel(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                unit_id=unit.id, recipient_person_id=None, parcel_code=parcel_code,
                recipient_name_snapshot=_required(row.get("recipient_name_snapshot"), "PARCEL_RECIPIENT_REQUIRED"),
                recipient_contact_snapshot=_required(row.get("recipient_contact_masked"), "PARCEL_CONTACT_REQUIRED"),
                storage_location=_required(row.get("storage_location"), "PARCEL_STORAGE_REQUIRED"),
                pin_hash=hash_password(pin), status="RECEIVED", received_at=received_at,
                created_by_id=actor.id, updated_by_id=actor.id,
            )
            session.add(parcel)
            session.flush()
        elif (parcel.building_id, parcel.unit_id, parcel.recipient_name_snapshot, parcel.recipient_contact_snapshot, parcel.storage_location, parcel.received_at) != (
            building.id, unit.id, _required(row.get("recipient_name_snapshot"), "PARCEL_RECIPIENT_REQUIRED"),
            _required(row.get("recipient_contact_masked"), "PARCEL_CONTACT_REQUIRED"),
            _required(row.get("storage_location"), "PARCEL_STORAGE_REQUIRED"), received_at,
        ):
            raise SubmissionImportError("PARCEL_METADATA_CONFLICT")
        for field in ("ready_at", "handed_over_at"):
            if row.get(field) is not None:
                _utc(row.get(field), field=field)
        attempts = row.get("pin_attempt_count")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or not 0 <= attempts <= 10:
            raise SubmissionImportError("PARCEL_PIN_ATTEMPT_COUNT_INVALID")
        upsert_external_reference(
            session, run, tenant_id=tenant.id, source="parcel", entity_type="Parcel",
            source_key=f"{site.code}:{parcel_code}", target_id=parcel.id,
            payload={"parcel_code": parcel_code, "source_status": source_status, "case_required": row.get("case_required")},
        )
        counts["parcels"] += 1
        if row.get("case_required"):
            counts["parcel_case_candidates"] += 1

    policy_rows = _rows(pack, "09_chinh_sach_phi.xlsx")
    for row in policy_rows:
        tenant, site, building = _reference_site_building(session, structure, row)
        code = _required(row.get("fee_policy_code"), "FEE_POLICY_CODE_REQUIRED")
        policy_name = _required(row.get("fee_policy_name"), "FEE_POLICY_NAME_REQUIRED")
        active = normalize_enum(row.get("policy_status"), ("ACTIVE", "INACTIVE"), field="policy_status", output_case="preserve") == "ACTIVE"
        policy = session.scalar(select(FeePolicy).where(
            FeePolicy.building_id == building.id, FeePolicy.code == code,
        ).with_for_update())
        if policy is None:
            policy = FeePolicy(tenant_id=tenant.id, site_id=site.id, building_id=building.id, code=code, name=policy_name, is_active=active)
            session.add(policy)
            session.flush()
        elif (policy.name, policy.is_active) != (policy_name, active):
            raise SubmissionImportError("FEE_POLICY_METADATA_CONFLICT")
        try:
            version_number = int(row["version_number"])
        except (TypeError, ValueError) as exc:
            raise SubmissionImportError("FEE_POLICY_VERSION_INVALID") from exc
        if isinstance(row["version_number"], bool) or version_number <= 0:
            raise SubmissionImportError("FEE_POLICY_VERSION_INVALID")
        effective_from = normalize_date(row.get("effective_from"), field="effective_from")
        effective_to = normalize_date(row.get("effective_to"), field="effective_to") if row.get("effective_to") else None
        if effective_to is not None and effective_to < effective_from:
            raise SubmissionImportError("FEE_POLICY_VERSION_DATES_INVALID")
        unit_rate = int(normalize_money_vnd(row.get("unit_rate_vnd"), field="unit_rate_vnd"))
        rounding_unit = int(normalize_money_vnd(row.get("rounding_unit_vnd"), field="rounding_unit_vnd"))
        basis = normalize_enum(row.get("basis"), ("UNIT_AREA_M2",), field="basis", output_case="preserve")
        version = session.scalar(select(FeePolicyVersion).where(
            FeePolicyVersion.fee_policy_id == policy.id, FeePolicyVersion.version_number == version_number,
        ).with_for_update())
        version_values = (effective_from, effective_to, unit_rate, basis, rounding_unit)
        if version is None:
            version = FeePolicyVersion(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                fee_policy_id=policy.id, version_number=version_number,
                effective_from=effective_from, effective_to=effective_to,
                unit_rate_vnd=unit_rate, basis=basis,
                rounding_unit_vnd=rounding_unit, published_at=None,
            )
            session.add(version)
            session.flush()
        elif (version.effective_from, version.effective_to, version.unit_rate_vnd, version.basis, version.rounding_unit_vnd) != version_values:
            raise SubmissionImportError("FEE_POLICY_VERSION_CONFLICT")
        period_key = _required(row.get("period_key"), "PERIOD_KEY_REQUIRED")
        period_start = normalize_date(row.get("period_start"), field="period_start")
        period_end = normalize_date(row.get("period_end"), field="period_end")
        if period_end < period_start:
            raise SubmissionImportError("ACCOUNTING_PERIOD_DATES_INVALID")
        cutoff = _utc(row.get("cutoff_at"), field="cutoff_at")
        period_status = normalize_enum(row.get("period_status"), ("OPEN", "CLOSING", "CLOSED", "LOCKED"), field="period_status", output_case="preserve")
        period = session.scalar(select(AccountingPeriod).where(
            AccountingPeriod.building_id == building.id, AccountingPeriod.period_key == period_key,
        ).with_for_update())
        if period is None:
            period = AccountingPeriod(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                period_key=period_key, period_start=period_start, period_end=period_end,
                cutoff_at=cutoff, status=period_status, version=1,
            )
            session.add(period)
            session.flush()
        elif (period.period_start, period.period_end, period.cutoff_at, period.status) != (period_start, period_end, cutoff, period_status):
            raise SubmissionImportError("ACCOUNTING_PERIOD_CONFLICT")
        counts["fee_policies"] += 1
        counts["fee_policy_versions"] += 1
        counts["accounting_periods"] += 1
    return dict(counts)


def _pack_manifest(pack: SubmissionPack) -> dict[str, object]:
    return {
        "schema_version": CONTRACT_VERSION,
        "workbooks": [
            {"file_name": workbook.file_name, "sha256": workbook.source_sha256, "row_count": workbook.data_row_count}
            for workbook in pack.workbooks
        ],
    }


def _source_manifest_path(source: Path, manifest_path: Path | None) -> Path:
    """Find the approved checksum list, without accepting an arbitrary pack."""

    if manifest_path is not None:
        candidate = Path(manifest_path)
    elif source.name == "synthetic":
        candidate = source.parent / "synthetic_manifest.json"
    elif source.name == "excel-data":
        candidate = source.parent / "DATA_SOURCE_MANIFEST.json"
    else:
        raise SubmissionImportError("SOURCE_MANIFEST_REQUIRED")
    if not candidate.is_file():
        raise SubmissionImportError("SOURCE_MANIFEST_MISSING")
    return candidate


def _assert_pack_matches_source_manifest(pack: SubmissionPack, manifest_path: Path) -> None:
    """Bind the in-memory rows used by apply/verify to the approved checksums.

    Preflight reads the files independently.  Checking its result alone would
    leave a gap if a workbook changed between that read and the loader read.
    """

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest["workbooks"]
        if not isinstance(entries, list) or len(entries) != len(pack.workbooks):
            raise ValueError
        by_name = {entry["file_name"]: entry for entry in entries}
        if len(by_name) != len(entries) or set(by_name) != {item.file_name for item in pack.workbooks}:
            raise ValueError
        for workbook in pack.workbooks:
            entry = by_name[workbook.file_name]
            if not isinstance(entry, dict):
                raise ValueError
            row_count = entry.get("row_count")
            if row_count is None:
                sheets = entry["sheets"]
                data_sheets = [sheet for sheet in sheets if sheet.get("sheet_role") == "data"]
                if len(data_sheets) != 1:
                    raise ValueError
                row_count = data_sheets[0]["data_row_count"]
            if not isinstance(row_count, int) or isinstance(row_count, bool):
                raise ValueError
            digest = entry["sha256"]
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError
            if row_count != workbook.data_row_count or digest.lower() != workbook.source_sha256:
                raise SubmissionImportError("SOURCE_CHECKSUM_MISMATCH")
            if "size_bytes" in entry and entry["size_bytes"] != workbook.source_size_bytes:
                raise SubmissionImportError("SOURCE_CHECKSUM_MISMATCH")
    except (KeyError, TypeError, ValueError, OSError, UnicodeError) as exc:
        raise SubmissionImportError("SOURCE_MANIFEST_INVALID") from exc


def _evidence_provider_from_env():
    """Return an optional local-only evidence reader for the replay stage."""

    value = os.getenv("GREENCITY_SUBMISSION_EVIDENCE_DIR", "").strip()
    if not value:
        return None
    root = Path(value).resolve()

    def provider(work_code: str) -> bytes | None:
        for suffix in (".png", ".jpg", ".jpeg", ".bin"):
            candidate = (root / f"{work_code}{suffix}").resolve()
            if not candidate.is_relative_to(root) or not candidate.is_file():
                continue
            if candidate.stat().st_size > 10 * 1024 * 1024:
                raise SubmissionImportError("REPLAY_EVIDENCE_TOO_LARGE")
            return candidate.read_bytes()
        return None

    return provider


def _preflight_ok_for_stage(source: Path, stage: str, *,
                            manifest_path: Path | None = None) -> tuple[SubmissionPack, Any, dict[str, object]]:
    if stage not in {"master", "references", "replay", "all"}:
        raise SubmissionImportError("IMPORT_STAGE_INVALID")
    source = Path(source)
    approved_manifest = _source_manifest_path(source, manifest_path)
    pack = read_submission_pack(source)
    _assert_pack_matches_source_manifest(pack, approved_manifest)
    as_of = datetime.now(UTC)
    result = run_preflight(source, as_of_utc=as_of, manifest_path=approved_manifest)
    if not result.source_checksum_verified:
        raise SubmissionImportError("SOURCE_CHECKSUM_MISMATCH")
    deferred_terminal = {"FUTURE_TERMINAL_EVENT"} if stage in {"master", "references"} else set()
    blocking = [
        issue for issue in result.issues
        if issue.severity == "ERROR" and issue.code.split(":", 1)[0] not in deferred_terminal
    ]
    if blocking:
        raise SubmissionImportError("PREFLIGHT_BLOCKED")
    summary = manifest_summary(_pack_manifest(pack))
    return pack, summary, {"status": result.status, "rows": result.total_rows, "orphans": result.orphan_count}


def dry_run(source: Path, *, stage: str, manifest_path: Path | None = None) -> dict[str, object]:
    pack, summary, preflight = _preflight_ok_for_stage(source, stage, manifest_path=manifest_path)
    return {
        "status": "PASS",
        "stage": stage,
        "manifest_sha256": summary.manifest_sha256,
        "workbooks": summary.workbook_count,
        "rows": summary.total_rows,
        "preflight": preflight,
        "master_rows": sum(len(_rows(pack, name)) for name in MASTER_FILES),
        "reference_rows": sum(len(_rows(pack, name)) for name in REFERENCE_FILES),
        "database_write": False,
    }


def _replay_operations(session, pack: SubmissionPack, run, *, as_of_utc: datetime,
                       evidence_storage_root: Path, written_evidence_paths: list[Path]) -> dict[str, object]:
    counts: dict[str, object] = dict(replay_service_requests(
        session, _rows(pack, "01_cong_viec.xlsx"), run,
        as_of_utc=as_of_utc,
        evidence_provider=_evidence_provider_from_env(),
        evidence_storage_root=evidence_storage_root,
        written_evidence_paths=written_evidence_paths,
    ))
    counts.update({
        f"fcs13_{key}": value
        for key, value in replay_maintenance_cleaning(
            session, _rows(pack, "05_tai_san_bao_tri.xlsx"),
            _rows_with_tenant(pack, "06_ve_sinh.xlsx"), run, as_of_utc=as_of_utc,
        ).items()
    })
    counts.update({
        f"fcs14_{key}": value
        for key, value in replay_security_parcels(
            session, _rows_with_tenant(pack, "07_an_ninh_tuan_tra.xlsx"),
            _rows(pack, "08_su_co_an_ninh.xlsx"),
            _rows_with_tenant(pack, "12_buu_pham.xlsx"), run, as_of_utc=as_of_utc,
        ).items()
    })
    counts["fcs15_billing"] = replay_billing_run(
        session, _rows(pack, "09_chinh_sach_phi.xlsx"),
        _rows(pack, "10_hoa_don.xlsx"), run, as_of_utc=as_of_utc,
    )
    counts["fcs16_payments"] = replay_payment_allocations(
        session, _rows(pack, "11_thanh_toan.xlsx"),
        _rows(pack, "10_hoa_don.xlsx"),
        _rows(pack, "09_chinh_sach_phi.xlsx"), run, as_of_utc=as_of_utc,
    )
    return counts


def apply(source: Path, *, stage: str, manifest_path: Path | None = None) -> dict[str, object]:
    pack, summary, preflight = _preflight_ok_for_stage(source, stage, manifest_path=manifest_path)
    as_of = datetime.now(UTC)
    credentials = _credential_map() if stage in {"master", "all"} else {}
    settings = Settings()
    database = Database(settings)
    written_evidence_paths: list[Path] = []
    try:
        with database.get_session() as session:
            result = start_import_run(session, summary, stage=stage)
            run = result.run
            if result.replayed and run.status == "APPLIED":
                reconciliation = reconcile_submission_pack(session, pack, stage)
                return {"status": "REPLAY", "stage": stage, "manifest_sha256": summary.manifest_sha256,
                        "workbooks": summary.workbook_count, "rows": summary.total_rows,
                        "reconciliation": reconciliation, "database_write": False}
            assert_apply_allowed(run, manifest_sha256=summary.manifest_sha256)
            mark_run_status(run, "APPLYING")
            if stage == "master":
                counts = load_master(session, pack, run, credentials=credentials)
            elif stage == "references":
                counts = load_references(session, pack, run)
            elif stage == "replay":
                counts = _replay_operations(
                    session, pack, run, as_of_utc=as_of,
                    evidence_storage_root=settings.private_storage_path,
                    written_evidence_paths=written_evidence_paths,
                )
            else:
                counts = {**load_master(session, pack, run, credentials=credentials), **load_references(session, pack, run)}
                counts.update(_replay_operations(
                    session, pack, run, as_of_utc=as_of,
                    evidence_storage_root=settings.private_storage_path,
                    written_evidence_paths=written_evidence_paths,
                ))
            reconciliation = reconcile_submission_pack(session, pack, stage)
            mark_run_status(run, "APPLIED")
            session.commit()
            return {"status": "PASS", "stage": stage, "manifest_sha256": summary.manifest_sha256,
                    "workbooks": summary.workbook_count, "rows": summary.total_rows,
                    "counts": counts, "reconciliation": reconciliation, "preflight": preflight,
                    "database_write": True}
    except Exception as exc:
        # The session context rolls back all stage mutations.  Do not echo the
        # exception because it could contain driver details or source values.
        for target in written_evidence_paths:
            target.unlink(missing_ok=True)
        if isinstance(exc, SubmissionImportError):
            raise
        raise SubmissionImportError("SUBMISSION_IMPORT_FAILED") from exc
    finally:
        database.close()


def verify(source: Path, *, stage: str, manifest_path: Path | None = None) -> dict[str, object]:
    pack, summary, preflight = _preflight_ok_for_stage(source, stage, manifest_path=manifest_path)
    database = Database(Settings())
    try:
        with database.get_session() as session:
            run = session.scalar(select(SubmissionImportRun).where(
                SubmissionImportRun.manifest_sha256 == summary.manifest_sha256,
                SubmissionImportRun.stage == stage,
            ))
            if run is None or run.status != "APPLIED":
                raise SubmissionImportError("SUBMISSION_IMPORT_NOT_APPLIED")
            reconciliation = reconcile_submission_pack(session, pack, stage)
            return {"status": "PASS", "stage": stage, "manifest_sha256": summary.manifest_sha256,
                    "workbooks": summary.workbook_count, "rows": summary.total_rows,
                    "reconciliation": reconciliation, "database_write": False, "preflight": preflight}
    finally:
        database.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="GreenCity approved submission-pack loader")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, help="Approved source checksums (required for nonstandard pack paths)")
    parser.add_argument("--stage", choices=("master", "references", "replay", "all"), required=True)
    parser.add_argument("--report-dir", type=Path, help="Write a metadata-only reconciliation report for --verify")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.report_dir is not None and not args.verify:
        parser.error("--report-dir requires --verify")
    try:
        if args.dry_run:
            result = dry_run(args.source, stage=args.stage, manifest_path=args.manifest)
        elif args.apply:
            result = apply(args.source, stage=args.stage, manifest_path=args.manifest)
        else:
            result = verify(args.source, stage=args.stage, manifest_path=args.manifest)
            if args.report_dir is not None:
                report_dir = args.report_dir.resolve()
                if report_dir.is_relative_to(args.source.resolve()):
                    raise SubmissionImportError("REPORT_DIR_INSIDE_SOURCE")
                report_dir.mkdir(parents=True, exist_ok=True)
                report = {
                    "status": result["status"], "stage": result["stage"],
                    "manifest_sha256": result["manifest_sha256"],
                    "workbooks": result["workbooks"], "rows": result["rows"],
                    "reconciliation": result["reconciliation"],
                    "database_write": False,
                }
                (report_dir / "submission-data-reconciliation.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
    except (SubmissionImportError, OSError, ValueError) as exc:
        print(f"FCS09_LOADER=FAIL code={getattr(exc, 'code', 'LOADER_ERROR')}")
        return 1
    print(
        f"FCS09_LOADER={result['status']} stage={result['stage']} "
        f"workbooks={result.get('workbooks', 12)} rows={result.get('rows', 0)} "
        f"database_write={result.get('database_write', False)}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
