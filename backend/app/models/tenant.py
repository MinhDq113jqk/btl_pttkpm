from sqlalchemy import CheckConstraint, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin


class Tenant(IdentityTimestampMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        UniqueConstraint("code", name="uq_tenants_code"),
        Index("ix_tenants_code", "code"),
        {"implicit_returning": False},
    )
    # Source systems identify a tenant by a non-PII code (for example
    # ``GC-CORP``).  Legacy rows may remain NULL until reconciled by the
    # submission loader, so the migration adds this column nullable.
    # ``server_default=NULL`` keeps legacy migration rehearsals compatible:
    # before revision 0018 the physical column does not exist, so an ORM
    # insert that leaves ``code`` unset must omit it from the INSERT list.
    # Revision 0018 creates the nullable column; explicit loader values still
    # travel through the normal INSERT path.
    code: Mapped[str | None] = mapped_column(
        String(50), nullable=True, server_default=text("NULL"), deferred=True,
    )
    name: Mapped[str] = mapped_column(String(200))
