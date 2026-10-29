"""Whitelisted self profile, email challenges and evidence-based account review."""
import secrets
import smtplib
from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select, update
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.core.security import verify_password
from app.models.account import Account
from app.models.account_parking import AccountEmailChange, AccessReview
from app.schemas.account_parking import AccountProfileInput, EmailChangeInput, EmailConfirm, AccessReviewInput, ReviewDecision
from app.services.account_control import token_digest, revoke_sessions, is_tenant_admin
from app.services.portal_mail import require_smtp, send_email_verification
from app.services.r2 import audit, utc_now, require_version
from app.services.resident_portal import command, scope_values, view
from app.services.operational_control import event, load
from app.api.account_administration import tenant_admin

router = APIRouter(prefix='/portal', tags=['Account profile and review'])


def own_account(session, context):
    row = session.scalar(select(Account).where(Account.id == context.account_id,
        Account.tenant_id == context.tenant_id, Account.is_active.is_(True)).with_for_update())
    if row is None:
        raise scope_not_found()
    return row


def reauthenticate(account, password):
    if not verify_password(password, account.hashed_password):
        raise AppError('ERR-REAUTHENTICATE', 'Cần xác thực lại bằng mật khẩu hiện tại.', 403)


def profile_view(account):
    return {k: getattr(account, k) for k in ('id', 'username', 'full_name', 'email', 'email_verified_at', 'profile_version')}


@router.get('/account-profile')
def profile(request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        return profile_view(own_account(session, context))


@router.post('/account-profile')
def update_profile(body: AccountProfileInput, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        account = own_account(session, context)
        reauthenticate(account, body.current_password); require_version(account.profile_version, body.expected_version)
        account.full_name = body.full_name.strip()
        if len(account.full_name) < 2:
            raise AppError('ERR-CONTROL-INPUT', 'Họ tên cần ít nhất hai ký tự.', 422)
        account.profile_version += 1
        audit(session, context, request, event_type='AccountProfileChanged', action='update', resource_type='Account',
            resource_id=account.id, building_id=None, after={'profile_version': account.profile_version})
        session.commit(); return profile_view(account)


@router.post('/account-profile/email/request')
def request_email(body: EmailChangeInput, request: Request, context: UserContext = Depends(get_current_user_context)):
    settings = request.app.state.settings; require_smtp(settings)
    token = secrets.token_urlsafe(48)
    with request.app.state.database.get_session() as session:
        account = own_account(session, context)
        reauthenticate(account, body.current_password); require_version(account.profile_version, body.expected_version)
        if account.email == body.email:
            raise AppError('ERR-CONFLICT', 'Địa chỉ email đã được xác minh.', 409)
        recent = session.scalar(select(AccountEmailChange.id).where(AccountEmailChange.account_id == account.id,
            AccountEmailChange.created_at > utc_now() - timedelta(minutes=1)).limit(1))
        if recent:
            raise AppError('ERR-EMAIL-THROTTLED', 'Vui lòng đợi một phút trước khi gửi mã mới.', 429)
        session.execute(update(AccountEmailChange).where(AccountEmailChange.account_id == account.id,
            AccountEmailChange.status == 'PENDING').values(status='SUPERSEDED', token_hash=None))
        row = AccountEmailChange(account_id=account.id, email=body.email, session_version=account.session_version,
            profile_version=account.profile_version, expires_at=utc_now() + timedelta(seconds=settings.recovery_token_ttl_seconds))
        session.add(row); session.flush()
        row.token_hash = token_digest('email-change', row.id, token)
        identifier, expiry = row.id, row.expires_at
        audit(session, context, request, event_type='AccountEmailVerificationRequested', action='request', resource_type='Account',
            resource_id=account.id, building_id=None, after={'verification_pending': True})
        session.commit()
    try:
        send_email_verification(settings, body.email, identifier, token, expiry)
    except (smtplib.SMTPException, OSError):
        with request.app.state.database.get_session() as session:
            session.execute(update(AccountEmailChange).where(AccountEmailChange.id == identifier,
                AccountEmailChange.status == 'PENDING').values(status='FAILED', token_hash=None)); session.commit()
        raise AppError('ERR-MAIL-DELIVERY', 'Chưa gửi được mã xác minh email. Vui lòng thử lại sau.', 502) from None
    return {'request_id': identifier, 'expires_at': expiry, 'message': 'Đã gửi mã xác minh đến email mới.'}


@router.post('/account-profile/email/confirm')
def confirm_email(body: EmailConfirm, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        account = own_account(session, context)
        row = session.scalar(select(AccountEmailChange).where(AccountEmailChange.id == body.request_id,
            AccountEmailChange.account_id == account.id).with_for_update())
        if (row is None or row.status != 'PENDING' or row.expires_at <= utc_now()
            or row.session_version != account.session_version or row.profile_version != account.profile_version
            or not secrets.compare_digest(row.token_hash or '', token_digest('email-change', body.request_id, body.token))):
            raise AppError('ERR-EMAIL-TOKEN', 'Mã xác minh không hợp lệ, thông tin đã thay đổi hoặc mã hết hạn.', 400)
        account.email = row.email; account.email_verified_at = utc_now(); account.profile_version += 1
        row.status = 'USED'; row.token_hash = None
        revoke_sessions(session, account)
        audit(session, context, request, event_type='AccountEmailChanged', action='confirm', resource_type='Account',
            resource_id=account.id, building_id=None, after={'email_verified': True, 'sessions_revoked': True})
        session.commit()
    return {'message': 'Đã xác minh email và thu hồi các phiên. Hãy đăng nhập lại.', 'reauthenticate': True}


@router.get('/control/permission-catalog')
def permission_catalog(request: Request, context: UserContext = Depends(get_current_user_context)):
    from app.models.enums import RoleEnum
    from app.core.policy import UNIT_READ_ROLES, BUILDING_UNIT_ROLES, SITE_WIDE_UNIT_ROLES
    from app.services.operational_control import MANAGEMENT, SECURITY, FINANCIAL, TECHNICAL
    from app.services.resident_portal import PORTAL_STAFF
    with request.app.state.database.get_session() as session:
        can_manage_accounts = is_tenant_admin(session, context)
    return {'can_manage_accounts': can_manage_accounts, 'roles': [{'role': r.value, 'scope': 'OWN_UNITS' if r.value == 'resident' else
        'BUILDING' if r.value in BUILDING_UNIT_ROLES else 'SITE' if r.value in SITE_WIDE_UNIT_ROLES else 'ASSIGNED_WORK'} for r in RoleEnum],
        'current_grants': [{'role': g.role, 'building_id': g.building_id} for g in context.role_grants],
        'actions': [
            {'action': 'ACCOUNT_PROFILE', 'roles': [r.value for r in RoleEnum], 'scope': 'SELF'},
            {'action': 'ACCOUNT_LOCK_ROLE_SESSIONS', 'roles': ['admin'], 'scope': 'TENANT_ADMIN_OTHER_ACCOUNT'},
            {'action': 'ACCOUNT_RECOVERY_VERIFY', 'roles': ['admin', 'director'], 'scope': 'TARGET_AUTHORITY_REAUTHENTICATE'},
            {'action': 'ACCESS_REVIEW_RESOLVE', 'roles': ['admin'], 'scope': 'TENANT_ADMIN_INDEPENDENT'},
            {'action': 'UNIT_READ', 'roles': sorted(UNIT_READ_ROLES), 'scope': 'POLICY_PROJECTION_OR_ASSIGNMENT'},
            {'action': 'PARKING_MANAGE', 'roles': list(MANAGEMENT), 'scope': 'SITE_BUILDING'},
            {'action': 'PARKING_RECONCILIATION_READ', 'roles': [*MANAGEMENT, 'security'], 'scope': 'SITE_BUILDING'},
            {'action': 'SECURITY_OPERATIONS', 'roles': list(SECURITY), 'scope': 'SITE_BUILDING_OR_ASSIGNMENT'},
            {'action': 'FINANCIAL_CONTROL', 'roles': list(FINANCIAL), 'scope': 'SITE_BUILDING_INDEPENDENT_APPROVAL'},
            {'action': 'TECHNICAL_CONTROL', 'roles': list(TECHNICAL), 'scope': 'SITE_BUILDING'},
            {'action': 'PORTAL_STAFF', 'roles': list(PORTAL_STAFF), 'scope': 'SITE_ROLE_BUILDING'},
        ], 'note': 'Danh mục nhóm hành động từ policy hiện hành; API kiểm tra thêm trạng thái, đối tượng, thời hạn và phân công.'}


@router.get('/control/access-reviews')
def access_reviews(request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        tenant_admin(session, context)
        return {'items': [view(r) for r in session.scalars(select(AccessReview).where(*context.scope_conditions(AccessReview)).order_by(AccessReview.created_at.desc()).limit(200))]}


@router.post('/control/access-reviews', status_code=201)
def create_access_review(body: AccessReviewInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        tenant_admin(session, context)
        target = session.scalar(select(Account).where(Account.id == body.target_account_id, Account.tenant_id == context.tenant_id).with_for_update())
        if target is None or target.id == context.account_id:
            raise scope_not_found()
        row = AccessReview(**scope_values(context), **body.model_dump(), target_version=target.session_version)
        session.add(row); event(session, context, row, 'OPEN', body.evidence_reference)
        return row, 'profile'
    return command(request, context, key, 'access-review.create', body.model_dump(mode='json'), execute, roles=('admin',))


@router.post('/control/access-reviews/{identifier}/resolve')
def resolve_access_review(identifier: UUID, body: ReviewDecision, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        tenant_admin(session, context)
        # Same lock order as account commands: target, then review.
        initial = load(session, context, AccessReview, identifier, ('admin',))
        locked_accounts = {a.id: a for a in session.scalars(select(Account).where(
            Account.id.in_((initial.target_account_id, context.account_id)), Account.tenant_id == context.tenant_id)
            .order_by(Account.id).with_for_update())}
        target = locked_accounts[initial.target_account_id]
        row = load(session, context, AccessReview, identifier, ('admin',), lock=True)
        require_version(row.version, body.expected_version)
        if row.account_id == context.account_id or target.id == context.account_id:
            raise AppError('ERR-INDEPENDENT-CHECKER', 'Hồ sơ cần quản trị viên khác xử lý.', 403)
        if row.status != 'OPEN':
            raise AppError('ERR-STATE-TRANSITION', 'Hồ sơ đã được xử lý.', 409)
        reauthenticate(locked_accounts[context.account_id], body.current_password)
        require_version(target.session_version, row.target_version)
        before = {'is_active': target.is_active, 'session_version': target.session_version}
        if body.action == 'LOCK':
            target.is_active = False
        if body.action != 'REVIEW':
            revoke_sessions(session, target)
        row.status = 'RESOLVED'; row.version += 1
        row.decision = {'action': body.action, 'reason': body.reason, 'actor_id': str(context.account_id),
            'at': utc_now().isoformat(), 'before': before, 'after': {'is_active': target.is_active, 'session_version': target.session_version}}
        event(session, context, row, body.action, body.reason)
        audit(session, context, request, event_type='AccountAccessReviewResolved', action=body.action, resource_type='Account',
            resource_id=target.id, building_id=None, after={'is_active': target.is_active, 'session_version': target.session_version})
        session.commit(); return view(row)
