import secrets
import smtplib
from uuid import UUID
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, or_, and_

from app.core.exceptions import AppError
from app.core.policy import UserContext, context_for_account, get_current_user_context, scope_not_found
from app.core.security import hash_password, verify_password
from app.models.account import Account, AccountRole
from app.models.resident_portal import AccountRecovery
from app.schemas.resident_portal import RecoveryInput, RecoveryVerify, RecoveryComplete
from app.services.r2 import audit, utc_now
from app.services.portal_mail import require_smtp, send_recovery
from app.services.account_control import recovery_authority, token_digest, revoke_sessions, is_tenant_admin
from app.services.login_throttle import (load_active_throttle, lock_login_identity,
    lock_new_identity_admission, login_identity_key, login_throttle_has_capacity,
    prune_expired_login_identities, record_login_failure)

router = APIRouter(tags=["Resident account recovery"])
PUBLIC_RESPONSE = {"message": "Nếu tài khoản hợp lệ, Ban quản lý sẽ tiếp nhận yêu cầu. Hãy liên hệ Ban quản lý để xác minh danh tính.", "mode": "VERIFIED_SUPPORT"}


@router.post("/auth/recovery/request")
def request_recovery(body: RecoveryInput, request: Request):
    settings = request.app.state.settings
    with request.app.state.database.get_session() as session:
        now = session.scalar(select(func.now()))
        identity = login_identity_key("recovery:" + body.username, settings.auth_secret())
        lock_login_identity(session, identity)
        prune_expired_login_identities(session, now, settings)
        state = load_active_throttle(session, identity, now, settings)
        if state is not None and state.locked_until and state.locked_until > now:
            session.commit()
            raise AppError("ERR-RECOVERY-THROTTLED", "Vui lòng đợi trước khi gửi lại yêu cầu.", 429)
        if state is None:
            lock_new_identity_admission(session)
            if not login_throttle_has_capacity(session, settings):
                session.commit()
                raise AppError("ERR-RECOVERY-THROTTLED", "Vui lòng thử lại sau.", 429)
        record_login_failure(session, identity, state, now, settings)
        accounts = session.scalars(select(Account).where(Account.username == body.username,
            Account.is_active.is_(True)).limit(2)).all()
        if len(accounts) == 1:
            account = accounts[0]
            roles = set(session.scalars(select(AccountRole.role).where(AccountRole.account_id == account.id, AccountRole.effective_at())))
            pending = session.scalar(select(AccountRecovery.id).where(AccountRecovery.account_id == account.id,
                or_(AccountRecovery.status == "PENDING", and_(AccountRecovery.status == "VERIFIED", AccountRecovery.expires_at > now)),
                AccountRecovery.created_at > now - timedelta(hours=24)).limit(1))
            if roles and not pending:
                context = context_for_account(session, account)
                session.add(AccountRecovery(tenant_id=account.tenant_id, account_id=account.id,
                                           site_id=context.active_site_id))
        session.commit()
    return PUBLIC_RESPONSE


@router.get("/portal/recovery-requests")
def recovery_requests(request: Request, context: UserContext = Depends(get_current_user_context)):
    context.assert_role("admin", "director")
    with request.app.state.database.get_session() as session:
        rows = session.execute(select(AccountRecovery, Account).join(Account, Account.id == AccountRecovery.account_id)
            .where(AccountRecovery.tenant_id == context.tenant_id,
                   True if is_tenant_admin(session, context) else AccountRecovery.site_id == context.assert_active_site(),
                   AccountRecovery.status.in_(("PENDING", "VERIFIED")))
            .order_by(AccountRecovery.created_at.desc()).limit(100)).all()
        return {"items": [{"id": row.id, "username": target.username, "status": row.status,
                           "created_at": row.created_at, "expires_at": row.expires_at} for row, target in rows
                           if recovery_authority(session, context, target)]}


@router.post("/portal/recovery-requests/{identifier}/verify")
def verify_recovery(identifier: UUID, body: RecoveryVerify, request: Request,
                    context: UserContext = Depends(get_current_user_context)):
    context.assert_role("admin", "director")
    with request.app.state.database.get_session() as session:
        row = session.scalar(select(AccountRecovery).where(AccountRecovery.id == identifier,
            AccountRecovery.tenant_id == context.tenant_id,
            True if is_tenant_admin(session, context) else AccountRecovery.site_id == context.assert_active_site()).with_for_update())
        if row is None:
            raise scope_not_found()
        actor = session.get(Account, context.account_id)
        if not verify_password(body.current_password, actor.hashed_password):
            raise AppError("ERR-REAUTHENTICATE", "Cần xác thực lại tài khoản xử lý.", 403)
        if row.status not in {"PENDING", "VERIFIED"}:
            raise AppError("ERR-STATE-TRANSITION", "Yêu cầu không còn chờ khôi phục.", 409)
        target = session.scalar(select(Account).where(Account.id == row.account_id,
            Account.tenant_id == context.tenant_id).with_for_update())
        if target is None or not recovery_authority(session, context, target):
            raise scope_not_found()
        settings = request.app.state.settings
        if settings.smtp_enabled:
            require_smtp(settings)
            if not body.verified_email:
                raise AppError("ERR-VERIFIED-EMAIL", "Cần nhập địa chỉ email đã xác minh với chủ tài khoản.", 422)
            if target.email and body.verified_email.lower() != target.email.lower():
                raise AppError("ERR-VERIFIED-EMAIL", "Email cần trùng địa chỉ đã xác minh của tài khoản.", 422)
        token = secrets.token_urlsafe(48)
        row.token_hash = token_digest('account-recovery', row.id, token)
        row.issued_session_version = target.session_version
        row.expires_at = utc_now() + timedelta(seconds=request.app.state.settings.recovery_token_ttl_seconds)
        row.status = "VERIFIED"; row.verification_reference = body.reference; row.verified_by_id = context.account_id
        row.delivery_status = "PENDING" if settings.smtp_enabled else "SUPPORT"
        issued_digest, issued_expiry = row.token_hash, row.expires_at
        audit(session, context, request, event_type="ResidentRecoveryVerified", action="verify",
            resource_type="AccountRecovery", resource_id=row.id, building_id=None,
            after={"status": "VERIFIED"}, reason="Đã xác minh danh tính theo hồ sơ hỗ trợ.")
        session.commit()
        if settings.smtp_enabled:
            try:
                send_recovery(settings, body.verified_email, row.id, token, row.expires_at)
            except (smtplib.SMTPException, OSError):
                row = session.scalar(select(AccountRecovery).where(AccountRecovery.id == identifier).with_for_update().execution_options(populate_existing=True))
                if row.token_hash == issued_digest and row.status == 'VERIFIED':
                    row.delivery_status = "FAILED"; row.token_hash = None
                session.commit()
                # Do not expose provider messages, recipient or token in errors.
                raise AppError("ERR-MAIL-DELIVERY", "SMTP chưa xác nhận gửi. BQL có thể xác minh lại để cấp mã mới.", 502) from None
            row = session.scalar(select(AccountRecovery).where(AccountRecovery.id == identifier).with_for_update().execution_options(populate_existing=True))
            if row.token_hash == issued_digest and row.status == 'VERIFIED':
                row.delivery_status = "SENT"
            session.commit()
            return {"request_id": row.id, "expires_at": issued_expiry,
                    "message": "SMTP đã tiếp nhận email chứa mã khôi phục. Việc thư đến hộp thư cần kiểm chứng riêng."}
        # Returned once to the authenticated verifier, never stored in plaintext/logs.
        return {"request_id": row.id, "token": token, "expires_at": row.expires_at}


@router.post("/auth/recovery/complete")
def complete_recovery(body: RecoveryComplete, request: Request):
    with request.app.state.database.get_session() as session:
        row = session.scalar(select(AccountRecovery).where(AccountRecovery.id == body.request_id).with_for_update())
        supplied = token_digest('account-recovery', body.request_id, body.token)
        expected = row.token_hash if row and row.token_hash else "0" * 64
        if (not secrets.compare_digest(supplied, expected) or row is None or row.status != "VERIFIED"
                or row.expires_at is None or row.expires_at <= utc_now()):
            raise AppError("ERR-RECOVERY-TOKEN", "Mã khôi phục không hợp lệ hoặc đã hết hạn.", 400)
        account = session.scalar(select(Account).where(Account.id == row.account_id,
            Account.tenant_id == row.tenant_id, Account.is_active.is_(True)).with_for_update())
        if (account is None or account.session_version != row.issued_session_version
            or not session.scalar(select(AccountRole.id).where(AccountRole.account_id == account.id, AccountRole.effective_at()).limit(1))):
            raise AppError("ERR-RECOVERY-TOKEN", "Mã khôi phục không hợp lệ hoặc đã hết hạn.", 400)
        if verify_password(body.new_password, account.hashed_password):
            raise AppError("ERR-PASSWORD-UNCHANGED", "Mật khẩu mới cần khác mật khẩu đang dùng.", 422)
        account.hashed_password = hash_password(body.new_password)
        account.must_change_password = False
        revoke_sessions(session, account)
        row.status = "USED"; row.token_hash = None
        audit(session, context_for_account(session, account), request, event_type='AccountRecoveryCompleted', action='recover',
            resource_type='Account', resource_id=account.id, building_id=None, after={'sessions_revoked': True})
        session.commit()
    return {"message": "Đã khôi phục tài khoản. Hãy đăng nhập lại bằng mật khẩu mới."}
