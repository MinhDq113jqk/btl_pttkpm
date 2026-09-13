from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityTimestampMixin


class Person(IdentityTimestampMixin, Base):
    __tablename__ = "persons"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_persons_id_tenant_id"),
        Index("ix_greencity_persons_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_masked: Mapped[str] = mapped_column(String(50), nullable=False)
    email_masked: Mapped[str] = mapped_column(String(100), nullable=False)


class UnitPersonRelationship(IdentityTimestampMixin, Base):
    __tablename__ = "unit_person_relationships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"], ["greencity.tenants.id"], ondelete="CASCADE",
            name="fk_unit_person_relationships_tenant_id_tenants",
        ),
        ForeignKeyConstraint(
            ["person_id", "tenant_id"], ["greencity.persons.id", "greencity.persons.tenant_id"],
            ondelete="CASCADE", name="fk_unit_person_relationships_person_tenant",
        ),
        ForeignKeyConstraint(
            ["unit_id", "building_id"], ["greencity.units.id", "greencity.units.building_id"],
            ondelete="CASCADE", name="fk_unit_person_relationships_unit_building",
        ),
        ForeignKeyConstraint(
            ["building_id", "site_id"], ["greencity.buildings.id", "greencity.buildings.site_id"],
            ondelete="CASCADE", name="fk_unit_person_relationships_building_site",
        ),
        ForeignKeyConstraint(
            ["site_id", "tenant_id"], ["greencity.sites.id", "greencity.sites.tenant_id"],
            ondelete="CASCADE", name="fk_unit_person_relationships_site_tenant",
        ),
        CheckConstraint(
            "relationship_type IN ('owner', 'tenant', 'family_member')",
            name="relationship_type_allowed",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="valid_interval",
        ),
        CheckConstraint(
            "(relationship_type = 'owner' AND ownership_ratio > 0 "
            "AND ownership_ratio <= 1) OR "
            "(relationship_type <> 'owner' AND ownership_ratio IS NULL)",
            name="ownership_ratio_semantics",
        ),
        UniqueConstraint(
            "unit_id", "person_id", "relationship_type", "valid_from",
            name="uq_unit_person_relationships_episode",
        ),
        Index("ix_greencity_unit_person_relationships_unit_id", "unit_id"),
        Index("ix_greencity_unit_person_relationships_person_id", "person_id"),
    )

    unit_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    person_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False, default="owner")
    ownership_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    valid_from: Mapped[date] = mapped_column(
        Date, nullable=False, default=date.today, server_default=func.current_date(),
    )
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    person = relationship("Person", backref="unit_relationships")
