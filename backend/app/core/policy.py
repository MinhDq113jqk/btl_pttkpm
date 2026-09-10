from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, Request
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.security import decode_token
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.enums import RoleEnum
from app.models.site import Site
from app.models.unit import Unit

UNIT_READ_ROLES = frozenset({"admin", "director", "cskh", "accountant",
                             "technical_lead", "technician", "security"})
SITE_WIDE_UNIT_ROLES = frozenset({"admin", "director", "accountant"})
BUILDING_UNIT_ROLES = frozenset({"cskh", "technical_lead", "security"})
RESIDENT_READ_ROLES = frozenset({"admin", "director", "cskh", "accountant"})


@dataclass(frozen=True)
class UnitGrant:
    role: str
    building_id: UUID | None


def scope_not_found() -> AppError:
    return AppError("ERR-SCOPE-NOTFOUND", "Không tìm thấy dữ liệu.", 404)


@dataclass
class UserContext:
    account_id: UUID
    tenant_id: UUID
    username: str
    full_name: str
    roles: list[str]
    active_site_id: UUID | None
    # Concrete tenant-validated IDs. Legacy None fails closed, never a wildcard.
    allowed_site_ids: list[UUID] | None
    unit_grants: tuple[UnitGrant, ...] = ()

    def is_admin(self) -> bool:
        return "admin" in self.roles

    def can_access_site(self, site_id: UUID) -> bool:
        return site_id in (self.allowed_site_ids or [])

    def assert_site_access(self, site_id: UUID) -> None:
        if not self.can_access_site(site_id):
            raise scope_not_found()

    def assert_role(self, *required_roles: str) -> None:
        if not any(role in self.roles for role in required_roles):
            raise AppError("ERR-FORBIDDEN", "Bạn không có quyền thực hiện thao tác này", 403)

    def sites_query(self):
        return select(Site).where(
            Site.tenant_id == self.tenant_id,
            Site.id.in_(self.allowed_site_ids or []),
        ).order_by(Site.code, Site.id)

    def units_query(self):
        self.assert_role(*UNIT_READ_ROLES)
        if not self.unit_grants:
            # Includes technician: no genuine WO assignment exists in R1 yet.
            raise scope_not_found()
        building_scope = or_(*[
            Building.id == grant.building_id if grant.building_id is not None else True
            for grant in self.unit_grants
        ])
        # Filter BEFORE loading Person relationships; an ID is never authorization.
        return select(Unit).join(Building, Unit.building_id == Building.id).join(
            Site, Building.site_id == Site.id,
        ).where(
            Site.tenant_id == self.tenant_id,
            Site.id.in_(self.allowed_site_ids or []),
            Site.id == self.active_site_id,
            building_scope,
        )

    def unit_projection(self, building_id: UUID) -> tuple[bool, bool]:
        """Return (residents visible, full unit details) for this target ONLY."""
        matched = [grant for grant in self.unit_grants
                   if grant.building_id is None or grant.building_id == building_id]
        return (any(grant.role in RESIDENT_READ_ROLES for grant in matched),
                any(grant.role != "security" for grant in matched))


def context_for_account(session: Session, account: Account,
                        active_site_id: UUID | None = None) -> UserContext:
    # Tenant-wide admin is an explicit grant (site_id NULL). Site-specific admin
    # roles must never become tenant-wide or grant roles in another active site.
    valid_building = or_(AccountRole.building_id.is_(None),
                        AccountRole.building_id.in_(select(Building.id).where(
                            Building.site_id == AccountRole.site_id)))
    known_role = AccountRole.role.in_([role.value for role in RoleEnum])
    grant = select(AccountRole.id).where(
        AccountRole.account_id == account.id,
        valid_building,
        known_role,
        or_(AccountRole.site_id == Site.id,
            and_(AccountRole.role == "admin", AccountRole.site_id.is_(None))),
    ).exists()
    sites = session.scalars(select(Site).where(
        Site.tenant_id == account.tenant_id, grant,
    ).order_by(Site.code, Site.id)).all()
    site_ids = [site.id for site in sites]
    if active_site_id is not None and active_site_id not in site_ids:
        raise scope_not_found()
    if active_site_id is None:
        active_site_id = site_ids[0] if site_ids else None
    role_scope = AccountRole.site_id == active_site_id if active_site_id else False
    roles = session.scalars(select(AccountRole).where(
        AccountRole.account_id == account.id,
        valid_building,
        known_role,
        or_(role_scope, and_(AccountRole.role == "admin", AccountRole.site_id.is_(None))),
    )).all()
    unit_grants = tuple(UnitGrant(grant.role, grant.building_id) for grant in roles
                        if grant.role in SITE_WIDE_UNIT_ROLES
                        or (grant.role in BUILDING_UNIT_ROLES and grant.building_id is not None))
    return UserContext(account.id, account.tenant_id, account.username, account.full_name,
                       sorted({grant.role for grant in roles}), active_site_id, site_ids, unit_grants)


def get_current_user_context(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
) -> UserContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("ERR-UNAUTHORIZED", "Yêu cầu đăng nhập để truy cập tài nguyên", 401)
    claims = decode_token(authorization[len("Bearer "):].strip(),
                          request.app.state.settings.auth_secret())
    # decode_token validates claim types; role and tenant claims are never trusted.
    with request.app.state.database.get_session() as session:
        account = session.scalar(select(Account).where(
            Account.id == UUID(claims["sub"]), Account.is_active.is_(True),
        ))
        if account is None:
            raise AppError("ERR-UNAUTHORIZED", "Tài khoản không tồn tại hoặc đã bị khóa", 401)
        active_site_id = UUID(claims["active_site_id"]) if claims.get("active_site_id") else None
        context = context_for_account(session, account, active_site_id)
    request.state.user_id = str(context.account_id)
    return context
