from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityTimestampMixin


class Person(IdentityTimestampMixin, Base):
    __tablename__ = "persons"
    __table_args__ = (Index("ix_greencity_persons_tenant_id", "tenant_id"),)

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_masked: Mapped[str] = mapped_column(String(50), nullable=False)
    email_masked: Mapped[str] = mapped_column(String(100), nullable=False)


class UnitPersonRelationship(IdentityTimestampMixin, Base):
    __tablename__ = "unit_person_relationships"
    __table_args__ = (
        Index("ix_greencity_unit_person_relationships_unit_id", "unit_id"),
        Index("ix_greencity_unit_person_relationships_person_id", "person_id"),
    )

    unit_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.units.id", ondelete="CASCADE"), nullable=False)
    person_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.persons.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False, default="owner")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    person = relationship("Person", backref="unit_relationships")
