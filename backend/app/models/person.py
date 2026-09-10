from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityTimestampMixin


class Person(IdentityTimestampMixin, Base):
    __tablename__ = "persons"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_masked: Mapped[str] = mapped_column(String(50), nullable=False)
    email_masked: Mapped[str] = mapped_column(String(100), nullable=False)


class UnitPersonRelationship(IdentityTimestampMixin, Base):
    __tablename__ = "unit_person_relationships"

    unit_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.units.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.persons.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False, default="owner")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    person = relationship("Person", backref="unit_relationships")
