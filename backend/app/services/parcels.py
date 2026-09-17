"""Domain helpers for the V1 parcel intake and handover workflow."""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import false, or_, select, true
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.policy import UserContext, scope_not_found
from app.models.building import Building
from app.models.enums import ParcelStatusEnum
from app.models.parcel import PARCEL_STATUS_TRANSITIONS, Parcel
from app.models.platform import Attachment
from app.models.person import Person
from app.models.service import CaseRecord
from app.models.operations import SecurityIncident
from app.models.site import Site
from app.models.unit import Unit
from app.schemas.parcel import ParcelView


PARCEL_OPERATOR_ROLES = frozenset({"admin", "director", "cskh", "security"})
PARCEL_CASE_SOURCE_STATUSES = frozenset({
    ParcelStatusEnum.HANDED_OVER.value,
    ParcelStatusEnum.RETURNED.value,
    ParcelStatusEnum.LOST.value,
    ParcelStatusEnum.DAMAGED.value,
})
PIN_MAX_ATTEMPTS = 5
PIN_ATTEMPT_COUNTER_MAX = 10
PIN_LOCK_DURATION = timedelta(minutes=15)


def utc_now() -> datetime:
    return datetime.now(UTC)


def parcel_view(record: Parcel) -> ParcelView:
    return ParcelView.model_validate(record)


def assert_parcel_operator(context: UserContext, building_id: UUID) -> None:
    context.assert_building_role(building_id, *PARCEL_OPERATOR_ROLES)


def assert_parcel_incident_operator(context: UserContext, building_id: UUID) -> None:
    """Only security managers may connect a parcel to an incident."""
    context.assert_building_role(building_id, "admin", "director", "security")


def parcel_visibility(context: UserContext):
    """Return the server-derived building predicate for parcel list queries."""
    context.assert_active_site()
    context.assert_role(*PARCEL_OPERATOR_ROLES)
    conditions = []
    for grant in context.role_grants:
        if grant.role not in PARCEL_OPERATOR_ROLES:
            continue
        if grant.building_id is None:
            # Only site-wide roles can have a NULL building grant.  Security
            # and CSKH remain building-scoped by policy.
            if grant.role in {"admin", "director"}:
                conditions.append(true())
        else:
            conditions.append(Parcel.building_id == grant.building_id)
    return or_(*conditions) if conditions else false()


def scoped_parcel(
    session: Session,
    context: UserContext,
    parcel_id: UUID,
    *,
    lock: bool = False,
) -> Parcel:
    statement = select(Parcel).where(
        Parcel.id == parcel_id,
        *context.scope_conditions(Parcel),
    )
    if lock:
        statement = statement.with_for_update()
    record = session.scalar(statement)
    if record is None:
        raise scope_not_found()
    assert_parcel_operator(context, record.building_id)
    return record


def scoped_parcel_case(
    session: Session,
    context: UserContext,
    parcel_id: UUID,
    case_id: UUID | None = None,
) -> CaseRecord | None:
    statement = select(CaseRecord).where(
        *context.scope_conditions(CaseRecord),
        CaseRecord.source_parcel_id == parcel_id,
    )
    if case_id is not None:
        statement = statement.where(CaseRecord.id == case_id)
    return session.scalar(statement.order_by(CaseRecord.created_at.asc(), CaseRecord.id.asc()))


def scoped_parcel_incident(
    session: Session,
    context: UserContext,
    parcel_id: UUID,
    incident_id: UUID | None = None,
) -> SecurityIncident | None:
    statement = select(SecurityIncident).where(
        *context.scope_conditions(SecurityIncident),
        SecurityIncident.parcel_id == parcel_id,
    )
    if incident_id is not None:
        statement = statement.where(SecurityIncident.id == incident_id)
    return session.scalar(statement.order_by(SecurityIncident.created_at.asc(), SecurityIncident.id.asc()))


def scoped_parcel_attachment(
    session: Session,
    context: UserContext,
    parcel_id: UUID,
    attachment_id: UUID | None = None,
    *,
    include_quarantined: bool = False,
) -> Attachment | None:
    statement = select(Attachment).where(
        *context.scope_conditions(Attachment),
        Attachment.parcel_id == parcel_id,
    )
    if attachment_id is not None:
        statement = statement.where(Attachment.id == attachment_id)
    if not include_quarantined:
        statement = statement.where(Attachment.is_quarantined.is_(False))
    return session.scalar(statement)


def ensure_unit_in_scope(
    session: Session,
    context: UserContext,
    *,
    building_id: UUID,
    unit_id: UUID,
) -> Unit:
    site_id = context.assert_active_site()
    unit = session.scalar(select(Unit).join(
        Building, (Building.id == Unit.building_id) & (Building.site_id == site_id),
    ).join(
        Site, Site.id == Building.site_id,
    ).where(
        Unit.id == unit_id,
        Unit.building_id == building_id,
        Site.id == site_id,
        Site.tenant_id == context.tenant_id,
    ))
    if unit is None:
        raise scope_not_found()
    return unit


def ensure_recipient_in_tenant(
    session: Session,
    context: UserContext,
    recipient_person_id: UUID | None,
) -> Person | None:
    if recipient_person_id is None:
        return None
    person = session.scalar(select(Person).where(
        Person.id == recipient_person_id,
        Person.tenant_id == context.tenant_id,
    ))
    if person is None:
        raise scope_not_found()
    return person


def assert_transition(record: Parcel, target: str) -> None:
    if target not in PARCEL_STATUS_TRANSITIONS.get(record.status, frozenset()):
        raise AppError("ERR-STATE-TRANSITION", "Parcel không thể chuyển sang trạng thái này.", 409)


def assert_case_source(record: Parcel) -> None:
    """A shared Case must explain a terminal parcel or a handover issue."""
    if record.status not in PARCEL_CASE_SOURCE_STATUSES:
        raise AppError(
            "ERR-STATE-TRANSITION",
            "Chỉ có thể mở Case cho bưu phẩm đã bàn giao hoặc có ngoại lệ.",
            409,
        )


def verify_handover_pin(record: Parcel, supplied_pin: str, now: datetime) -> None:
    if record.pin_locked_until is not None and record.pin_locked_until > now:
        raise AppError("ERR-PIN-LOCKED", "PIN tạm thời bị khóa. Hãy thử lại sau.", 423)
