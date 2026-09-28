from datetime import UTC, datetime, timedelta
import secrets
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.policy import UserContext, context_for_account, get_current_user_context, scope_not_found
from app.core.security import create_token, hash_password, verify_password
from app.models.account import Account
from app.models.auth_session import AuthSession
from app.models.site import Site
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse, SiteSummary, SwitchSiteRequest, UserInfo
from app.services.login_throttle import (
    load_active_throttle,
    lock_login_identity,
    lock_new_identity_admission,
    login_throttle_has_capacity,
    login_identity_key,
    prune_expired_login_identities,
    record_login_failure,
    retry_after_seconds,
)

router = APIRouter(prefix="/auth", tags=["auth"])
SESSION_TTL_SECONDS = 86400
_DUMMY_LOGIN_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def _verified_login_account(accounts: list[Account], password: str) -> Account | None:
    account = accounts[0] if len(accounts) == 1 else None
    candidate_hash = account.hashed_password if account is not None else _DUMMY_LOGIN_PASSWORD_HASH
    password_matches = verify_password(password, candidate_hash)
    return account if account is not None and password_matches else None


def user_info(session: Session, context: UserContext) -> UserInfo:
    sites = session.scalars(context.sites_query()).all()
    return UserInfo(
        account_id=context.account_id, tenant_id=context.tenant_id,
        username=context.username, full_name=context.full_name, roles=context.roles,
        active_site_id=context.active_site_id,
        allowed_sites=[SiteSummary(id=s.id, code=s.code, name=s.name) for s in sites],
        resident_person_id=context.resident_person_id,
        resident_unit_ids=list(context.resident_unit_ids),
        must_change_password=context.must_change_password,
    )


def login_response(request: Request, session: Session, account: Account, context: UserContext) -> LoginResponse:
    issued_at = int(time.time())
    session_id = uuid4()
    session_row = AuthSession(
        id=session_id,
        account_id=account.id,
        session_version=account.session_version,
        created_at=datetime.fromtimestamp(issued_at, UTC),
        expires_at=datetime.fromtimestamp(issued_at + SESSION_TTL_SECONDS + 1, UTC),
    )
    session.execute(delete(AuthSession).where(
        (AuthSession.expires_at <= datetime.now(UTC)) | AuthSession.revoked_at.is_not(None),
    ))
    session.add(session_row)
    session.flush()
    token = create_token({
        "sub": str(context.account_id), "tenant_id": str(context.tenant_id),
        "active_site_id": str(context.active_site_id) if context.active_site_id else None,
        "purpose": "session", "sid": str(session_id), "sv": account.session_version,
        "iat": issued_at,
    }, request.app.state.settings.auth_secret(), expires_in_seconds=SESSION_TTL_SECONDS)
    session.commit()
    return LoginResponse(access_token=token, token_type="Bearer", user=user_info(session, context))


@router.post("/login", response_model=LoginResponse)
def login(request: Request, body: LoginRequest):
    settings = request.app.state.settings
    with request.app.state.database.get_session() as session:
        now = session.scalar(select(func.now()))
        identity_key = login_identity_key(body.username, settings.auth_secret())
        lock_login_identity(session, identity_key)
        prune_expired_login_identities(session, now, settings)
        throttle_state = load_active_throttle(session, identity_key, now, settings)
        if throttle_state is not None and throttle_state.locked_until is not None and throttle_state.locked_until > now:
            retry_after = retry_after_seconds(throttle_state, now)
            session.commit()
            raise AppError(
                "ERR-LOGIN-THROTTLED",
                "Quá nhiều lần đăng nhập không thành công. Vui lòng thử lại sau.",
                429,
                headers={"Retry-After": str(retry_after)},
            )
        # Keep the identity contract; ambiguous usernames fail closed until
        # OD-LOGIN chooses a tenant-aware scheme. Never guess the tenant.
        accounts = session.scalars(select(Account).where(
            Account.username == body.username, Account.is_active.is_(True),
        ).limit(2).with_for_update()).all()
        account = _verified_login_account(accounts, body.password)
        if account is None:
            if throttle_state is None:
                lock_new_identity_admission(session)
                prune_expired_login_identities(session, now, settings)
                throttle_state = load_active_throttle(session, identity_key, now, settings)
                if throttle_state is None and not login_throttle_has_capacity(session, settings):
                    session.commit()
                    raise AppError(
                        "ERR-LOGIN-THROTTLED",
                        "Quá nhiều lần đăng nhập không thành công. Vui lòng thử lại sau.",
                        429,
                        headers={"Retry-After": str(settings.login_throttle_base_backoff_seconds)},
                    )
            record_login_failure(session, identity_key, throttle_state, now, settings)
            session.commit()
            raise AppError("ERR-UNAUTHORIZED", "Tên đăng nhập hoặc mật khẩu không chính xác", 401)
        if throttle_state is not None:
            session.delete(throttle_state)
        return login_response(request, session, account, context_for_account(session, account))


@router.get("/me", response_model=UserInfo)
def get_me(request: Request, current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        return user_info(session, current_user)


@router.post("/switch-site", response_model=LoginResponse)
def switch_site(request: Request, body: SwitchSiteRequest,
                current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_site_access(body.site_id)
    with request.app.state.database.get_session() as session:
        if session.scalar(current_user.sites_query().where(Site.id == body.site_id)) is None:
            raise scope_not_found()
        account = session.scalar(select(Account).where(
            Account.id == current_user.account_id, Account.tenant_id == current_user.tenant_id,
            Account.is_active.is_(True),
        ).with_for_update())
        if account is None:
            raise AppError("ERR-UNAUTHORIZED", "Tài khoản không tồn tại hoặc đã bị khóa", 401)
        # Re-read membership and site-specific roles before signing the new scope.
        context = context_for_account(session, account, body.site_id)
        current_session = session.scalar(select(AuthSession).where(
            AuthSession.id == request.state.auth_session_id,
            AuthSession.account_id == account.id,
            AuthSession.session_version == account.session_version,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        ).with_for_update())
        if current_session is None:
            raise AppError("ERR-UNAUTHORIZED", "Phiên đăng nhập không còn hợp lệ", 401)
        return login_response(request, session, account, context)


@router.post("/logout", status_code=204)
def logout(request: Request, current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        session_row = session.scalar(select(AuthSession).where(
            AuthSession.id == request.state.auth_session_id,
            AuthSession.account_id == current_user.account_id,
            AuthSession.revoked_at.is_(None),
        ).with_for_update())
        if session_row is not None:
            session_row.revoked_at = datetime.now(UTC)
            session.commit()
    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
def logout_all(request: Request, current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        account = session.scalar(select(Account).where(
            Account.id == current_user.account_id,
            Account.tenant_id == current_user.tenant_id,
            Account.is_active.is_(True),
        ).with_for_update())
        if account is None:
            raise AppError("ERR-UNAUTHORIZED", "Tài khoản không tồn tại hoặc đã bị khóa", 401)
        account.session_version += 1
        session.execute(update(AuthSession).where(
            AuthSession.account_id == account.id,
            AuthSession.revoked_at.is_(None),
        ).values(revoked_at=datetime.now(UTC)))
        session.commit()
    return Response(status_code=204)


@router.post("/change-password", status_code=204)
def change_password(request: Request, body: ChangePasswordRequest,
                    current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        account = session.scalar(select(Account).where(
            Account.id == current_user.account_id,
            Account.tenant_id == current_user.tenant_id,
            Account.is_active.is_(True),
        ).with_for_update())
        if account is None or not verify_password(body.current_password, account.hashed_password):
            raise AppError("ERR-UNAUTHORIZED", "Mật khẩu hiện tại không chính xác", 401)
        if verify_password(body.new_password, account.hashed_password):
            raise AppError("ERR-PASSWORD-UNCHANGED", "Mật khẩu mới phải khác mật khẩu hiện tại.", 400)
        account.hashed_password = hash_password(body.new_password)
        account.must_change_password = False
        account.session_version += 1
        session.execute(update(AuthSession).where(
            AuthSession.account_id == account.id,
            AuthSession.revoked_at.is_(None),
        ).values(revoked_at=datetime.now(UTC)))
        session.commit()
    return Response(status_code=204)
