from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, func, select

from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.platform import DomainEvent, NotificationReadModel
from app.schemas.resident_notifications import (
    ResidentNotificationListResponse,
    ResidentNotificationView,
)
from app.services.r2 import audit


router = APIRouter(tags=["R6 resident notifications"])


def _assert_resident_scope(context: UserContext) -> None:
    context.assert_role("resident")
    context.assert_active_site()
    if context.resident_person_id is None or not context.resident_unit_ids:
        raise scope_not_found()


def _notification_conditions(context: UserContext):
    return (
        NotificationReadModel.tenant_id == context.tenant_id,
        NotificationReadModel.site_id == context.assert_active_site(),
        NotificationReadModel.recipient_account_id == context.account_id,
        # A notification projection may never escape its source event's scope.
        DomainEvent.tenant_id == context.tenant_id,
        DomainEvent.site_id == context.assert_active_site(),
    )


def _notification_statement(context: UserContext):
    return select(NotificationReadModel, DomainEvent.correlation_id).join(
        DomainEvent,
        and_(
            DomainEvent.id == NotificationReadModel.domain_event_id,
            DomainEvent.tenant_id == NotificationReadModel.tenant_id,
            DomainEvent.site_id == NotificationReadModel.site_id,
        ),
    ).where(*_notification_conditions(context))


def _view(notification: NotificationReadModel, correlation_id: UUID) -> ResidentNotificationView:
    return ResidentNotificationView(
        id=notification.id,
        template_code=notification.template_code,
        template_snapshot=notification.template_snapshot,
        delivery_status=notification.delivery_status,
        delivered_at=notification.delivered_at,
        read_at=notification.read_at,
        correlation_id=correlation_id,
        created_at=notification.created_at,
    )


@router.get("/resident/notifications", response_model=ResidentNotificationListResponse)
def list_resident_notifications(
    request: Request,
    include_read: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserContext = Depends(get_current_user_context),
):
    _assert_resident_scope(current_user)
    with request.app.state.database.get_session() as session:
        statement = _notification_statement(current_user)
        unread_condition = NotificationReadModel.read_at.is_(None)
        unread_count = session.scalar(select(func.count(NotificationReadModel.id)).select_from(
            NotificationReadModel,
        ).join(DomainEvent, and_(
            DomainEvent.id == NotificationReadModel.domain_event_id,
            DomainEvent.tenant_id == NotificationReadModel.tenant_id,
            DomainEvent.site_id == NotificationReadModel.site_id,
        )).where(*_notification_conditions(current_user), unread_condition)) or 0
        if not include_read:
            statement = statement.where(unread_condition)
        total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = session.execute(statement.order_by(
            NotificationReadModel.created_at.desc(), NotificationReadModel.id.desc(),
        ).offset((page - 1) * page_size).limit(page_size)).all()
        return ResidentNotificationListResponse(
            items=[_view(notification, correlation_id) for notification, correlation_id in rows],
            page=page,
            page_size=page_size,
            total=total,
            unread_count=unread_count,
        )


@router.post("/resident/notifications/{notification_id}/read", response_model=ResidentNotificationView)
def mark_resident_notification_read(
    request: Request,
    notification_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    _assert_resident_scope(current_user)
    with request.app.state.database.get_session() as session:
        row = session.execute(_notification_statement(current_user).where(
            NotificationReadModel.id == notification_id,
        ).with_for_update(of=NotificationReadModel)).one_or_none()
        if row is None:
            raise scope_not_found()
        notification, correlation_id = row
        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)
            audit(
                session,
                current_user,
                request,
                event_type="ResidentNotificationRead",
                action="read",
                resource_type="Notification",
                resource_id=notification.id,
                building_id=None,
                after={
                    "domain_event_id": str(notification.domain_event_id),
                    "notification_correlation_id": str(correlation_id),
                },
            )
            session.commit()
        return _view(notification, correlation_id)
