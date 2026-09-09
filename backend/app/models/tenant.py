from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin


class Tenant(IdentityTimestampMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),)
    name: Mapped[str] = mapped_column(String(200))
