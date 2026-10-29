"""Recovery never changes role grants; privileged targets need tenant administration."""
import hashlib
from sqlalchemy import select, update
from app.models.account import AccountRole
from app.models.auth_session import AuthSession
from app.core.policy import context_for_account
from app.services.r2 import utc_now


def token_digest(purpose, identifier, token):
    return hashlib.sha256(f'{purpose}:{identifier}:{token}'.encode()).hexdigest()


def is_tenant_admin(session, context):
    return session.scalar(select(AccountRole.id).where(AccountRole.account_id == context.account_id,
        AccountRole.role == 'admin', AccountRole.effective_at(), AccountRole.site_id.is_(None),
        AccountRole.building_id.is_(None))) is not None


def recovery_authority(session, context, target):
    if target.tenant_id != context.tenant_id or target.id == context.account_id or not target.is_active:
        return False
    grants = session.scalars(select(AccountRole).where(AccountRole.account_id == target.id, AccountRole.effective_at())).all()
    if not grants:
        return False
    if is_tenant_admin(session, context):
        return True
    if not any(g.role in ('admin', 'director') and g.building_id is None for g in context.role_grants):
        return False
    if any(g.role in ('admin', 'director', 'accountant') or g.site_id != context.active_site_id for g in grants):
        return False
    target_context = context_for_account(session, target)
    return target_context.active_site_id == context.active_site_id and bool(target_context.roles)


def revoke_sessions(session, account):
    account.session_version += 1
    session.execute(update(AuthSession).where(AuthSession.account_id == account.id,
        AuthSession.revoked_at.is_(None)).values(revoked_at=utc_now()))
