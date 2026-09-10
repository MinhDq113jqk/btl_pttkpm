from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.policy import UserContext, context_for_account, get_current_user_context, scope_not_found
from app.core.security import create_token, verify_password
from app.models.account import Account
from app.models.site import Site
from app.schemas.auth import LoginRequest, LoginResponse, SiteSummary, SwitchSiteRequest, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


def user_info(session: Session, context: UserContext) -> UserInfo:
    sites = session.scalars(context.sites_query()).all()
    return UserInfo(
        account_id=context.account_id, tenant_id=context.tenant_id,
        username=context.username, full_name=context.full_name, roles=context.roles,
        active_site_id=context.active_site_id,
        allowed_sites=[SiteSummary(id=s.id, code=s.code, name=s.name) for s in sites],
    )


def login_response(request: Request, session: Session, context: UserContext) -> LoginResponse:
    token = create_token({
        "sub": str(context.account_id), "tenant_id": str(context.tenant_id),
        "active_site_id": str(context.active_site_id) if context.active_site_id else None,
    }, request.app.state.settings.auth_secret())
    return LoginResponse(access_token=token, token_type="Bearer", user=user_info(session, context))


@router.post("/login", response_model=LoginResponse)
def login(request: Request, body: LoginRequest):
    with request.app.state.database.get_session() as session:
        # Keep the identity contract; ambiguous usernames fail closed until
        # OD-LOGIN chooses a tenant-aware scheme. Never guess the tenant.
        accounts = session.scalars(select(Account).where(
            Account.username == body.username, Account.is_active.is_(True),
        ).limit(2)).all()
        if len(accounts) != 1 or not verify_password(body.password, accounts[0].hashed_password):
            raise AppError("ERR-UNAUTHORIZED", "Tên đăng nhập hoặc mật khẩu không chính xác", 401)
        return login_response(request, session, context_for_account(session, accounts[0]))


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
        ))
        if account is None:
            raise AppError("ERR-UNAUTHORIZED", "Tài khoản không tồn tại hoặc đã bị khóa", 401)
        # Re-read membership and site-specific roles before signing the new scope.
        context = context_for_account(session, account, body.site_id)
        return login_response(request, session, context)
