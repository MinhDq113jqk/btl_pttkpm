"""Invitations have a separate purpose, expiry, verification and one-time use."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import delete, select, update
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.core.security import hash_password
from app.models.account import Account, AccountRole
from app.models.auth_session import AuthSession
from app.models.operational_control import AccountInvitation
from app.schemas.portal_control import InvitationInput, InvitationAccept
from app.schemas.resident_portal import PortalAction
from app.services.operational_control import building_scope, event, load
from app.services.resident_portal import command, scope_values, view
from app.services.r2 import require_version, utc_now, audit

router = APIRouter(prefix='/portal', tags=['Account administration'])


def tenant_admin(session, context):
    context.assert_role('admin')
    if not session.scalar(select(AccountRole.id).where(AccountRole.account_id == context.account_id, AccountRole.role == 'admin', AccountRole.effective_at(), AccountRole.site_id.is_(None), AccountRole.building_id.is_(None))):
        raise AppError('ERR-FORBIDDEN', 'Quản trị tài khoản cần quyền quản trị toàn đơn vị.', 403)


@router.get('/control/accounts')
def accounts(request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        tenant_admin(session, context)
        rows = session.scalars(select(Account).where(Account.tenant_id == context.tenant_id).order_by(Account.username).limit(200)).all()
        return {'items': [{'id': r.id, 'username': r.username, 'full_name': r.full_name, 'is_active': r.is_active, 'session_version': r.session_version, 'person_id': r.person_id,
            'roles': [{'role': x.role, 'site_id': x.site_id, 'building_id': x.building_id, 'valid_from': x.valid_from, 'valid_to': x.valid_to} for x in session.scalars(select(AccountRole).where(AccountRole.account_id == r.id))]} for r in rows]}


@router.get('/control/invitations')
def invitations(request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        tenant_admin(session, context)
        return {'items': [view(r) for r in session.scalars(select(AccountInvitation).where(*context.scope_conditions(AccountInvitation)).order_by(AccountInvitation.created_at.desc()).limit(200))]}


@router.post('/control/invitations', status_code=201)
def invite(body: InvitationInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        tenant_admin(session, context); building_scope(session, context, body.building_id, ('admin',))
        if body.role == 'resident' and body.person_id is None:
            raise AppError('ERR-PERSON-REQUIRED', 'Tài khoản cư dân cần liên kết hồ sơ người.', 422)
        if body.person_id:
            from app.models.person import Person
            if not session.scalar(select(Person.id).where(Person.id == body.person_id, Person.tenant_id == context.tenant_id)):
                raise scope_not_found()
        if session.scalar(select(Account.id).where(Account.tenant_id == context.tenant_id, Account.username == body.username)):
            raise AppError('ERR-CONFLICT', 'Tên đăng nhập đã tồn tại.', 409)
        target = Account(tenant_id=context.tenant_id, username=body.username, full_name=body.full_name, person_id=body.person_id, is_active=False, hashed_password=hash_password(secrets.token_urlsafe(48)))
        session.add(target); session.flush()
        session.add(AccountRole(account_id=target.id, role=body.role, site_id=context.assert_active_site(), building_id=body.building_id if body.role in ('cskh', 'technical_lead', 'technician', 'cleaning', 'security') else None))
        row = AccountInvitation(**scope_values(context, building_id=body.building_id), target_account_id=target.id, email=body.email, verification_reference=body.verification_reference, expires_at=utc_now() + timedelta(hours=24))
        session.add(row); return row, 'profile'
    return command(request, context, key, 'account.invite', body.model_dump(mode='json'), execute, roles=('admin',))


@router.post('/control/invitations/{identifier}/send')
def send_invite(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context)):
    from app.services.portal_mail import require_smtp, send_invitation
    require_smtp(request.app.state.settings)
    token = secrets.token_urlsafe(48)
    with request.app.state.database.get_session() as session:
        tenant_admin(session, context)
        row = load(session, context, AccountInvitation, identifier, ('admin',), lock=True)
        require_version(row.version, body.expected_version)
        if row.status not in ('PENDING', 'SENT'):
            raise AppError('ERR-STATE-TRANSITION', 'Lời mời không còn khả dụng.', 409)
        target = session.get(Account, row.target_account_id)
        if target.is_active:
            raise AppError('ERR-CONFLICT', 'Tài khoản đã được kích hoạt.', 409)
        row.token_hash = hashlib.sha256(('account-invitation:' + token).encode()).hexdigest()
        row.expires_at = utc_now() + timedelta(hours=24); row.delivery_status = 'SENDING'; row.version += 1
        email, expires, revision = row.email, row.expires_at, row.version
        session.commit()
    try:
        send_invitation(request.app.state.settings, email, identifier, token, expires)
        delivery = 'SENT'
    except Exception:
        delivery = 'FAILED'
    with request.app.state.database.get_session() as session:
        row = load(session, context, AccountInvitation, identifier, ('admin',), lock=True)
        if row.version == revision:
            row.delivery_status = delivery
            if delivery == 'SENT':
                row.status = 'SENT'
            event(session, context, row, 'SEND', body.reason)
        session.flush(); result = view(row); session.commit()
    return result


@router.post('/invitations/{identifier}/accept')
def accept_invitation(identifier: UUID, body: InvitationAccept, request: Request):
    with request.app.state.database.get_session() as session:
        row = session.scalar(select(AccountInvitation).where(AccountInvitation.id == identifier).with_for_update())
        supplied = hashlib.sha256(('account-invitation:' + body.token).encode()).hexdigest()
        if not row or row.status not in ('PENDING', 'SENT') or row.expires_at <= utc_now() or not hmac.compare_digest(supplied, row.token_hash or ''):
            raise AppError('ERR-INVITATION-INVALID', 'Lời mời không hợp lệ hoặc đã hết hạn.', 422)
        target = session.scalar(select(Account).where(Account.id == row.target_account_id, Account.tenant_id == row.tenant_id).with_for_update())
        if target is None or target.is_active:
            raise AppError('ERR-INVITATION-INVALID', 'Lời mời không hợp lệ hoặc đã hết hạn.', 422)
        target.hashed_password = hash_password(body.password); target.is_active = True; target.session_version += 1; target.must_change_password = False
        target.email = row.email; target.email_verified_at = utc_now(); target.profile_version += 1
        row.status = 'USED'; row.token_hash = None; row.version += 1
        from app.core.policy import context_for_account
        ctx = context_for_account(session, target, row.site_id)
        audit(session, ctx, request, event_type='AccountActivated', action='activate', resource_type='Account', resource_id=target.id, building_id=row.building_id, after={'is_active': True})
        session.commit(); return {'status': 'ACTIVATED'}


@router.post('/control/accounts/{identifier}/actions')
def account_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    # Return a scoped control record for idempotency, never a password hash/account entity.
    def execute(session):
        tenant_admin(session, context)
        target = session.scalar(select(Account).where(Account.id == identifier, Account.tenant_id == context.tenant_id).with_for_update())
        if target is None:
            raise scope_not_found()
        if target.id == context.account_id:
            raise AppError('ERR-SELF-ADMINISTRATION', 'Không tự thay đổi quyền/trạng thái của mình tại đây.', 403)
        require_version(target.session_version, body.expected_version)
        def role_snapshot():
            return [{'role': r.role, 'site_id': str(r.site_id) if r.site_id else None, 'building_id': str(r.building_id) if r.building_id else None,
                     'valid_from': r.valid_from.isoformat() if r.valid_from else None, 'valid_to': r.valid_to.isoformat() if r.valid_to else None}
                    for r in session.scalars(select(AccountRole).where(AccountRole.account_id == target.id))]
        before = {'is_active': target.is_active, 'roles': role_snapshot()}
        if body.action in ('LOCK', 'END', 'REVOKE_SESSIONS'):
            if body.action != 'REVOKE_SESSIONS':
                target.is_active = False
                for invitation in session.scalars(select(AccountInvitation).where(AccountInvitation.target_account_id == target.id, AccountInvitation.status.in_(('PENDING', 'SENT'))).with_for_update()):
                    invitation.status = 'REVOKED'; invitation.token_hash = None; invitation.version += 1
        elif body.action == 'UNLOCK':
            from app.models.operational_control import OperationsRecord
            ended = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'ACCOUNT_CHANGE', OperationsRecord.related_id == target.id, OperationsRecord.tenant_id == context.tenant_id)).all()
            if any(r.data.get('action') == 'END' for r in ended):
                raise AppError('ERR-ACCOUNT-ENDED', 'Tài khoản đã kết thúc; cần tạo tài khoản mới theo quy trình mời.', 409)
            if session.scalar(select(AccountInvitation.id).where(AccountInvitation.target_account_id == target.id, AccountInvitation.status != 'USED')):
                raise AppError('ERR-ACTIVATION-REQUIRED', 'Tài khoản mời cần tự kích hoạt bằng lời mời.', 409)
            target.is_active = True
        elif body.action == 'SET_ROLE':
            from app.models.enums import RoleEnum
            from app.services.operational_control import as_uuid
            role = body.data.get('role'); building_id = as_uuid(body.data['building_id']) if body.data.get('building_id') else None
            if role not in [r.value for r in RoleEnum] or role == 'resident' and target.person_id is None:
                raise AppError('ERR-ROLE-INVALID', 'Vai trò hoặc liên kết người không phù hợp.', 422)
            if role in ('cskh', 'technical_lead', 'technician', 'cleaning', 'security') and not building_id:
                raise AppError('ERR-ROLE-SCOPE', 'Vai trò vận hành cần phạm vi tòa.', 422)
            if building_id:
                building_scope(session, context, building_id, ('admin',))
            try:
                starts = datetime.fromisoformat(body.data['valid_from'].replace('Z', '+00:00')) if body.data.get('valid_from') else utc_now()
                ends = datetime.fromisoformat(body.data['valid_to'].replace('Z', '+00:00')) if body.data.get('valid_to') else None
                if starts.tzinfo is None or ends and (ends.tzinfo is None or ends <= starts or ends <= utc_now()):
                    raise ValueError()
            except (TypeError, ValueError, AttributeError):
                raise AppError('ERR-ROLE-EFFECTIVITY', 'Hiệu lực quyền cần múi giờ, hạn kết thúc sau bắt đầu và chưa hết hạn.', 422) from None
            session.execute(delete(AccountRole).where(AccountRole.account_id == target.id, AccountRole.site_id == context.assert_active_site()))
            session.add(AccountRole(account_id=target.id, role=role, site_id=context.assert_active_site(), building_id=building_id, valid_from=starts, valid_to=ends))
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Thao tác tài khoản không hợp lệ.', 409)
        target.session_version += 1
        session.execute(update(AuthSession).where(AuthSession.account_id == target.id, AuthSession.revoked_at.is_(None)).values(revoked_at=utc_now()))
        from app.models.operational_control import OperationsRecord
        session.flush()
        row = OperationsRecord(**scope_values(context), kind='ACCOUNT_CHANGE', title=body.reason[:200], related_id=target.id, data={'action': body.action, 'session_version': target.session_version, 'before': before, 'after': {'is_active': target.is_active, 'roles': role_snapshot()}}, status='COMPLETED')
        session.add(row); event(session, context, row, body.action, body.reason); return row, 'profile'
    return command(request, context, key, 'account.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=('admin',))


@router.get('/control/accounts/{identifier}/sessions')
def sessions(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        tenant_admin(session, context)
        if not session.scalar(select(Account.id).where(Account.id == identifier, Account.tenant_id == context.tenant_id)):
            raise scope_not_found()
        from app.models.operational_control import OperationsRecord
        changes = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'ACCOUNT_CHANGE', OperationsRecord.related_id == identifier, OperationsRecord.tenant_id == context.tenant_id).order_by(OperationsRecord.created_at.desc()).limit(200)).all()
        return {'items': [{'id': r.id, 'created_at': r.created_at, 'expires_at': r.expires_at, 'revoked_at': r.revoked_at} for r in session.scalars(select(AuthSession).where(AuthSession.account_id == identifier).limit(200))], 'changes': [view(r) for r in changes]}
