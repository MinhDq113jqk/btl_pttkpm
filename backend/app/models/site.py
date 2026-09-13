from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityTimestampMixin


class Site(IdentityTimestampMixin, Base):
    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_sites_tenant_id_code"),
        UniqueConstraint("id", "tenant_id", name="uq_sites_id_tenant_id"),
        Index("ix_greencity_sites_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)

    tenant = relationship("Tenant", backref="sites")
