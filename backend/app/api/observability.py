from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.platform import AuditEvent, DomainEvent, NotificationReadModel
from app.models.billing import ArLedgerEntry, BillingAccount
from app.models.maintenance import MaintenanceOccurrence, MaintenancePlan
from app.models.operations import CleaningTask, SecurityIncident
from app.models.service import ServiceRequest
from app.schemas.r5 import (
    AuditEventListResponse,
    AuditEventView,
    DashboardDrillDownItem,
    DashboardDrillDownResponse,
    DashboardMetric,
    DashboardView,
    DeliveryStatus,
    NotificationListResponse,
    NotificationView,
    OutboxEventListResponse,
    OutboxEventView,
)
from app.services.r2 import audit, calculate_sla_deadline


router = APIRouter(tags=["R5 control and audit"])

AUDIT_READ_ROLES = frozenset({"admin", "director", "accountant"})
DASHBOARD_READ_ROLES = frozenset({"admin", "director"})
OUTBOX_OPERATOR_ROLES = frozenset({"admin", "director"})
FINANCIAL_AUDIT_RESOURCE_TYPES = frozenset({
    "AccountingPeriod", "BillingAccount", "BillingInvoice", "BillingRun",
    "FeePolicy", "FeePolicyVersion", "OverpaymentCredit", "Payment",
    "PaymentAllocation", "UnmatchedPayment",
})


def _building_visibility_conditions(context: UserContext, model, roles: frozenset[str]):
    context.assert_active_site()
    grants = tuple(grant for grant in context.role_grants if grant.role in roles)
    if any(grant.building_id is None for grant in grants):
        return ()
    building_ids = [grant.building_id for grant in grants if grant.building_id is not None]
    if not building_ids:
        raise scope_not_found()
    return (model.building_id.in_(building_ids),)


def _assert_site_wide_outbox_operator(context: UserContext) -> None:
    context.assert_role(*OUTBOX_OPERATOR_ROLES)
    context.assert_active_site()
    if not any(grant.role in OUTBOX_OPERATOR_ROLES and grant.building_id is None
               for grant in context.role_grants):
        raise scope_not_found()


def _audit_view(event: AuditEvent) -> AuditEventView:
    return AuditEventView.model_validate(event)


def _as_of_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError("ERR-VALIDATION", "as_of phải có timezone.", 422)
    return value.astimezone(UTC)


def _dashboard_requests(session, context: UserContext, as_of: datetime) -> list[ServiceRequest]:
    records = session.scalars(select(ServiceRequest).where(
        *context.scope_conditions(ServiceRequest),
        *_building_visibility_conditions(context, ServiceRequest, DASHBOARD_READ_ROLES),
        ServiceRequest.sla_started_at <= as_of,
    )).all()
    # The lifecycle timestamps, rather than the current status, make a request
    # resolved after the cutoff visible in a historical snapshot.
    return [record for record in records if (
        calculate_sla_deadline(record.sla_started_at, record.sla_duration_minutes) <= as_of
        and (record.resolved_at is None or record.resolved_at > as_of)
        and (record.closed_at is None or record.closed_at > as_of)
    )]


def _dashboard_maintenance(session, context: UserContext, as_of: datetime):
    return session.execute(select(MaintenanceOccurrence, MaintenancePlan).join(
        MaintenancePlan, MaintenancePlan.id == MaintenanceOccurrence.plan_id,
    ).where(
        *context.scope_conditions(MaintenanceOccurrence),
        *_building_visibility_conditions(context, MaintenanceOccurrence, DASHBOARD_READ_ROLES),
        MaintenanceOccurrence.due_at <= as_of,
        or_(MaintenanceOccurrence.completed_at.is_(None), MaintenanceOccurrence.completed_at > as_of),
    ).order_by(MaintenanceOccurrence.due_at, MaintenanceOccurrence.id)).all()


def _dashboard_cleaning(session, context: UserContext, as_of: datetime) -> list[CleaningTask]:
    # REWORK_REQUIRED is terminal. submitted_at is written in the same
    # transition that records the failed checklist, so it is a stable cutoff.
    return session.scalars(select(CleaningTask).where(
        *context.scope_conditions(CleaningTask),
        *_building_visibility_conditions(context, CleaningTask, DASHBOARD_READ_ROLES),
        CleaningTask.status == "REWORK_REQUIRED",
        CleaningTask.submitted_at.is_not(None),
        CleaningTask.submitted_at <= as_of,
    ).order_by(CleaningTask.submitted_at, CleaningTask.id)).all()


def _dashboard_incidents(session, context: UserContext, as_of: datetime) -> list[SecurityIncident]:
    return session.scalars(select(SecurityIncident).where(
        *context.scope_conditions(SecurityIncident),
        *_building_visibility_conditions(context, SecurityIncident, DASHBOARD_READ_ROLES),
        SecurityIncident.created_at <= as_of,
        or_(SecurityIncident.resolved_at.is_(None), SecurityIncident.resolved_at > as_of),
        or_(SecurityIncident.closed_at.is_(None), SecurityIncident.closed_at > as_of),
    ).order_by(SecurityIncident.occurred_at, SecurityIncident.id)).all()


def _dashboard_debt(session, context: UserContext, as_of: datetime):
    balance = func.sum(ArLedgerEntry.debit_vnd - ArLedgerEntry.credit_vnd).label("balance_vnd")
    return session.execute(select(BillingAccount, balance).join(
        ArLedgerEntry, ArLedgerEntry.billing_account_id == BillingAccount.id,
    ).where(
        *context.scope_conditions(ArLedgerEntry),
        *_building_visibility_conditions(context, ArLedgerEntry, DASHBOARD_READ_ROLES),
        ArLedgerEntry.effective_at <= as_of,
    ).group_by(BillingAccount.id).having(balance > 0).order_by(
        BillingAccount.account_number, BillingAccount.id,
    )).all()


@router.get("/dashboard", response_model=DashboardView)
def get_dashboard(
    request: Request,
    as_of: datetime = Query(...),
    current_user: UserContext = Depends(get_current_user_context),
):
    """Read-only R5 CAP-BI summary; all values share the same cutoff."""
    current_user.assert_role(*DASHBOARD_READ_ROLES)
    as_of = _as_of_utc(as_of)
    with request.app.state.database.get_session() as session:
        requests = _dashboard_requests(session, current_user, as_of)
        maintenance = _dashboard_maintenance(session, current_user, as_of)
        cleaning = _dashboard_cleaning(session, current_user, as_of)
        incidents = _dashboard_incidents(session, current_user, as_of)
        debt = _dashboard_debt(session, current_user, as_of)
        return DashboardView(
            as_of=as_of,
            sla_overdue_count=len(requests),
            maintenance_due_count=len(maintenance),
            cleaning_rework_count=len(cleaning),
            open_incident_count=len(incidents),
            ar_debt_vnd=sum(int(row.balance_vnd) for row in debt),
        )


@router.get("/dashboard/drill-down/{metric}", response_model=DashboardDrillDownResponse)
def get_dashboard_drill_down(
    request: Request,
    metric: DashboardMetric,
    as_of: datetime = Query(...),
    current_user: UserContext = Depends(get_current_user_context),
):
    """Return source rows that reconcile exactly to one dashboard KPI."""
    current_user.assert_role(*DASHBOARD_READ_ROLES)
    as_of = _as_of_utc(as_of)
    with request.app.state.database.get_session() as session:
        if metric == "sla_overdue":
            items = [DashboardDrillDownItem(
                metric=metric, resource_type="ServiceRequest", resource_id=record.id,
                building_id=record.building_id, reference=record.code, title=record.title,
                status=record.status,
                occurred_at=calculate_sla_deadline(record.sla_started_at, record.sla_duration_minutes),
            ) for record in _dashboard_requests(session, current_user, as_of)]
        elif metric == "maintenance_due":
            items = [DashboardDrillDownItem(
                metric=metric, resource_type="MaintenanceOccurrence", resource_id=occurrence.id,
                building_id=occurrence.building_id, reference=plan.code, title=plan.title,
                status=occurrence.status, occurred_at=occurrence.due_at,
            ) for occurrence, plan in _dashboard_maintenance(session, current_user, as_of)]
        elif metric == "cleaning_rework":
            items = [DashboardDrillDownItem(
                metric=metric, resource_type="CleaningTask", resource_id=task.id,
                building_id=task.building_id, reference=str(task.id), title="Cleaning rework required",
                status=task.status, occurred_at=task.submitted_at,
            ) for task in _dashboard_cleaning(session, current_user, as_of)]
        elif metric == "open_incidents":
            items = [DashboardDrillDownItem(
                metric=metric, resource_type="SecurityIncident", resource_id=incident.id,
                building_id=incident.building_id, reference=incident.code, title=incident.title,
                status=incident.status, occurred_at=incident.occurred_at,
            ) for incident in _dashboard_incidents(session, current_user, as_of)]
        else:
            items = [DashboardDrillDownItem(
                metric=metric, resource_type="BillingAccount", resource_id=account.id,
                building_id=account.building_id, reference=account.account_number,
                title=f"AR debt {account.account_number}", status=account.status,
                occurred_at=as_of, amount_vnd=int(balance_vnd),
            ) for account, balance_vnd in _dashboard_debt(session, current_user, as_of)]
        return DashboardDrillDownResponse(as_of=as_of, metric=metric, items=items)


@router.get("/audit-events", response_model=AuditEventListResponse)
def list_audit_events(
    request: Request,
    correlation_id: UUID | None = None,
    resource_type: str | None = Query(default=None, min_length=1, max_length=80),
    resource_id: UUID | None = None,
    as_of: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: UserContext = Depends(get_current_user_context),
):
    current_user.assert_role(*AUDIT_READ_ROLES)
    if as_of is not None:
        as_of = _as_of_utc(as_of)
    with request.app.state.database.get_session() as session:
        statement = select(AuditEvent).where(
            *current_user.scope_conditions(AuditEvent),
            *_building_visibility_conditions(current_user, AuditEvent, AUDIT_READ_ROLES),
        )
        # Accountant may inspect the financial trail granted to them, but does
        # not gain a global operational audit feed merely by holding that role.
        if not ({"admin", "director"} & set(current_user.roles)):
            statement = statement.where(AuditEvent.resource_type.in_(FINANCIAL_AUDIT_RESOURCE_TYPES))
        if correlation_id is not None:
            statement = statement.where(AuditEvent.correlation_id == correlation_id)
        if resource_type is not None:
            statement = statement.where(AuditEvent.resource_type == resource_type)
        if resource_id is not None:
            statement = statement.where(AuditEvent.resource_id == resource_id)
        if as_of is not None:
            statement = statement.where(AuditEvent.created_at <= as_of)
        records = session.scalars(statement.order_by(
            AuditEvent.created_at.desc(), AuditEvent.id.desc(),
        ).offset(offset).limit(limit)).all()
        return AuditEventListResponse(items=[_audit_view(record) for record in records])


@router.get("/notifications", response_model=NotificationListResponse)
def list_notifications(
    request: Request,
    include_read: bool = False,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        statement = select(NotificationReadModel).where(
            NotificationReadModel.tenant_id == current_user.tenant_id,
            NotificationReadModel.site_id == current_user.assert_active_site(),
            NotificationReadModel.recipient_account_id == current_user.account_id,
        )
        if not include_read:
            statement = statement.where(NotificationReadModel.read_at.is_(None))
        records = session.scalars(statement.order_by(
            NotificationReadModel.created_at.desc(), NotificationReadModel.id.desc(),
        )).all()
        return NotificationListResponse(items=[NotificationView.model_validate(record) for record in records])


@router.post("/notifications/{notification_id}/read", response_model=NotificationView)
def mark_notification_read(
    request: Request,
    notification_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        record = session.scalar(select(NotificationReadModel).where(
            NotificationReadModel.id == notification_id,
            NotificationReadModel.tenant_id == current_user.tenant_id,
            NotificationReadModel.site_id == current_user.assert_active_site(),
            NotificationReadModel.recipient_account_id == current_user.account_id,
        ).with_for_update())
        if record is None:
            raise scope_not_found()
        if record.read_at is None:
            record.read_at = datetime.now(UTC)
            audit(
                session,
                current_user,
                request,
                event_type="NotificationRead",
                action="read",
                resource_type="Notification",
                resource_id=record.id,
                building_id=None,
                after={"domain_event_id": str(record.domain_event_id)},
            )
            session.commit()
        return NotificationView.model_validate(record)


@router.get("/outbox/events", response_model=OutboxEventListResponse)
def list_outbox_events(
    request: Request,
    delivery_status: DeliveryStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: UserContext = Depends(get_current_user_context),
):
    _assert_site_wide_outbox_operator(current_user)
    with request.app.state.database.get_session() as session:
        statement = select(DomainEvent).where(
            DomainEvent.tenant_id == current_user.tenant_id,
            DomainEvent.site_id == current_user.assert_active_site(),
        )
        if delivery_status is not None:
            statement = statement.where(DomainEvent.delivery_status == delivery_status)
        records = session.scalars(statement.order_by(
            DomainEvent.created_at.desc(), DomainEvent.id.desc(),
        ).offset(offset).limit(limit)).all()
        return OutboxEventListResponse(items=[OutboxEventView.model_validate(record) for record in records])


@router.post("/outbox/events/{event_id}/retry", response_model=OutboxEventView)
def retry_outbox_event(
    request: Request,
    event_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    _assert_site_wide_outbox_operator(current_user)
    with request.app.state.database.get_session() as session:
        event = session.scalar(select(DomainEvent).where(
            DomainEvent.id == event_id,
            DomainEvent.tenant_id == current_user.tenant_id,
            DomainEvent.site_id == current_user.assert_active_site(),
        ).with_for_update())
        if event is None:
            raise scope_not_found()
        if event.delivery_status in {"RETRY_SCHEDULED", "DEAD_LETTER"}:
            before = {"delivery_status": event.delivery_status, "attempt_count": event.attempt_count}
            event.delivery_status = "PENDING"
            event.attempt_count = 0
            event.next_attempt_at = datetime.now(UTC)
            event.last_error = None
            event.delivery_lock_id = None
            event.locked_until = None
            notification = session.scalar(select(NotificationReadModel).where(
                NotificationReadModel.domain_event_id == event.id,
            ).with_for_update())
            if notification is not None:
                notification.delivery_status = "PENDING"
                notification.last_error = None
            audit(
                session,
                current_user,
                request,
                event_type="OutboxDeliveryRetryRequested",
                action="retry",
                resource_type="DomainEvent",
                resource_id=event.id,
                building_id=None,
                before=before,
                after={"delivery_status": event.delivery_status, "attempt_count": event.attempt_count},
            )
            session.commit()
        return OutboxEventView.model_validate(event)
