"""Durable in-app notifications and explicitly verified SMTP delivery."""
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from pydantic import Field
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, context_for_account, scope_not_found
from app.models.account import Account
from app.models.platform import NotificationReadModel
from app.models.resident_portal import AccountRecovery
from app.models.operational_control import AccountInvitation, NotificationTemplate, NotificationDelivery, NotificationPreference
from app.schemas.resident_portal import PortalInput, PortalAction
from app.services.operational_control import load, event, MANAGEMENT
from app.services.resident_portal import command, scope_values, view
from app.services.r2 import utc_now, require_version, audit
from app.api.portal_control import listing

router = APIRouter(prefix='/portal/control', tags=['Notification channels'])


class TemplateSend(PortalInput):
    recipient_account_id: UUID
    variables: dict[str, str] = Field(default_factory=dict)
    category: str = Field(pattern=r'^(COMMUNITY|SERVICE|BILLING|SECURITY)$')


def verified_email(session, recipient_id):
    invitation = session.scalar(select(AccountInvitation).where(AccountInvitation.target_account_id == recipient_id, AccountInvitation.status == 'USED').order_by(AccountInvitation.created_at.desc()).limit(1))
    if invitation:
        return invitation.email
    recovery = session.scalar(select(AccountRecovery).where(AccountRecovery.account_id == recipient_id, AccountRecovery.status == 'USED', AccountRecovery.verified_email.is_not(None)).order_by(AccountRecovery.created_at.desc()).limit(1))
    return recovery.verified_email if recovery else None


@router.post('/templates/{identifier}/send', status_code=201)
def template_send(identifier: UUID, body: TemplateSend, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        template = load(session, context, NotificationTemplate, identifier, MANAGEMENT, lock=True)
        recipient = session.scalar(select(Account).where(Account.id == body.recipient_account_id, Account.tenant_id == context.tenant_id, Account.is_active.is_(True)))
        if recipient is None:
            raise scope_not_found()
        recipient_ctx = context_for_account(session, recipient, template.site_id)
        from app.models.unit import Unit
        unit_ids = session.scalars(select(Unit.id).where(Unit.building_id == template.building_id, Unit.id.in_(recipient_ctx.resident_unit_ids))).all()
        if not unit_ids and not any(g.role != 'resident' and g.building_id in (None, template.building_id) for g in recipient_ctx.role_grants):
            raise scope_not_found()
        if set(body.variables) != set(template.required_fields) or any(len(v) > 2000 for v in body.variables.values()):
            raise AppError('ERR-TEMPLATE-FIELDS', 'Giá trị điền mẫu không khớp các biến đã công bố.', 422)
        try:
            title, rendered = template.title.format(**body.variables), template.body.format(**body.variables)
        except (KeyError, ValueError, IndexError):
            raise AppError('ERR-TEMPLATE-FIELDS', 'Mẫu chưa thể kết xuất.', 422) from None
        if len(title) > 300 or len(rendered) > 20000:
            raise AppError('ERR-TEMPLATE-SIZE', 'Nội dung kết xuất vượt giới hạn.', 422)
        preference = session.scalar(select(NotificationPreference).where(*context.scope_conditions(NotificationPreference), NotificationPreference.account_id == recipient.id, NotificationPreference.category == body.category))
        if preference and not preference.enabled and body.category not in ('BILLING', 'SECURITY') and not template.mandatory:
            raise AppError('ERR-NOTIFICATION-OPT-OUT', 'Người nhận đã tắt nhóm thông báo tùy chọn.', 409)
        from app.services.outbox import enqueue_notification
        source = enqueue_notification(session, context, request, event_type='ConfiguredNotification', resource_type='NotificationTemplate', resource_id=template.id, recipient_account_id=recipient.id, template_code=template.code,
            template_snapshot={'title': title, 'body': rendered, 'category': body.category, 'template_revision': template.revision, 'requires_ack': template.mandatory, 'unit_id': str(unit_ids[0]) if len(unit_ids) == 1 else None})
        session.flush()
        notification = session.scalar(select(NotificationReadModel).where(NotificationReadModel.domain_event_id == source.id))
        delivery = NotificationDelivery(**scope_values(context, building_id=template.building_id), notification_id=notification.id, recipient_id=recipient.id, channel='EMAIL' if preference and preference.channel == 'EMAIL' else 'IN_APP', status='PENDING' if preference and preference.channel == 'EMAIL' else 'QUEUED')
        session.add(delivery); return delivery, 'profile'
    return command(request, context, key, 'notification.template', {'id': str(identifier), **body.model_dump(mode='json')}, execute)


@router.get('/notification-deliveries')
def channel_deliveries(request: Request, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, NotificationDelivery, MANAGEMENT)


@router.post('/notification-deliveries/{identifier}/send')
def send_channel(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context)):
    from app.services.portal_mail import require_smtp, send_message
    require_smtp(request.app.state.settings)
    with request.app.state.database.get_session() as session:
        row = load(session, context, NotificationDelivery, identifier, MANAGEMENT, lock=True)
        require_version(row.version, body.expected_version)
        if row.channel != 'EMAIL' or row.status not in ('PENDING', 'FAILED'):
            raise AppError('ERR-DELIVERY-STATE', 'Chỉ gửi email đang chờ hoặc thất bại được xác nhận.', 409)
        email = verified_email(session, row.recipient_id)
        recipient = session.get(Account, row.recipient_id)
        if not email or not recipient or not recipient.is_active:
            raise AppError('ERR-EMAIL-UNVERIFIED', 'Người nhận chưa có email đã xác minh hoặc tài khoản không hoạt động.', 409)
        notification = session.get(NotificationReadModel, row.notification_id)
        title, rendered = notification.template_snapshot['title'], notification.template_snapshot['body']
        row.status = 'SENDING'; row.attempts += 1; row.version += 1; revision = row.version
        session.commit()
    try:
        send_message(request.app.state.settings, email, title, rendered)
        status = 'SENT'
    except Exception:
        # SMTP timeout may occur after acceptance: do not automatically duplicate delivery.
        status = 'UNKNOWN'
    with request.app.state.database.get_session() as session:
        row = load(session, context, NotificationDelivery, identifier, MANAGEMENT, lock=True)
        if row.version == revision:
            row.status = status; row.sent_at = utc_now() if status == 'SENT' else None; event(session, context, row, 'SEND_EMAIL', body.reason)
        session.flush(); result = view(row); session.commit(); return result


@router.post('/notifications/{identifier}/ack')
def acknowledge(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row = session.scalar(select(NotificationReadModel).where(NotificationReadModel.id == identifier, *context.scope_conditions(NotificationReadModel), NotificationReadModel.recipient_account_id == context.account_id).with_for_update())
        if row is None:
            raise scope_not_found()
        if row.acknowledged_at is None:
            row.acknowledged_at = utc_now(); row.read_at = row.read_at or row.acknowledged_at
            audit(session, context, request, event_type='NotificationAcknowledged', action='ack', resource_type='NotificationReadModel', resource_id=row.id, building_id=None, after={'acknowledged_at': row.acknowledged_at.isoformat()})
        session.commit(); return {'id': row.id, 'acknowledged_at': row.acknowledged_at}


@router.post('/notification-deliveries/{identifier}/actions')
def reconcile_delivery(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = load(session, context, NotificationDelivery, identifier, MANAGEMENT, lock=True)
        require_version(row.version, body.expected_version)
        reference = body.data.get('delivery_evidence_reference')
        if row.status != 'UNKNOWN' or body.action not in ('CONFIRM_SENT', 'CONFIRM_FAILED') or not isinstance(reference, str) or not 3 <= len(reference) <= 300:
            raise AppError('ERR-DELIVERY-RECONCILIATION', 'Cần trạng thái chưa rõ và căn cứ đối chiếu SMTP trước khi gửi lại.', 409)
        row.status = 'SENT' if body.action == 'CONFIRM_SENT' else 'FAILED'; row.sent_at = utc_now() if row.status == 'SENT' else None; row.version += 1
        event(session, context, row, body.action, body.reason + ' / ' + reference)
        return row, 'profile'
    return command(request, context, key, 'notification.reconcile', {'id': str(identifier), **body.model_dump(mode='json')}, execute)
