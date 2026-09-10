from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityTimestampMixin


class Account(IdentityTimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_accounts_tenant_id_username"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    roles = relationship("AccountRole", backref="account", cascade="all, delete-orphan")


class AccountRole(IdentityTimestampMixin, Base):
    __tablename__ = "account_roles"
    __table_args__ = (
        CheckConstraint("building_id IS NULL OR site_id IS NOT NULL", name="building_requires_site"),
        ForeignKeyConstraint(["building_id", "site_id"],
                             ["greencity.buildings.id", "greencity.buildings.site_id"],
                             name="fk_account_roles_building_site", ondelete="CASCADE"),
    )

    account_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    site_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.sites.id", ondelete="CASCADE"), nullable=True, index=True)
    building_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)

    site = relationship("Site")
