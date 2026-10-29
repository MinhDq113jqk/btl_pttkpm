"""Effective property records, separate lease agreements and identity mappings."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, JSON, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, IdentityTimestampMixin
from app.models.resident_portal import PortalScope, portal_scope


class LeaseContract(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "lease_contracts"
    __table_args__ = portal_scope(__tablename__) + (
        UniqueConstraint("dossier_id", name="uq_lease_contracts_dossier"),
        CheckConstraint("valid_to > valid_from", name="lease_dates"),
        CheckConstraint("status IN ('ACTIVE','SUPERSEDED','TERMINATED','EXPIRED')", name="lease_status"),
        Index("ix_lease_contracts_unit_dates", "unit_id", "valid_from", "valid_to"),
    )
    dossier_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_dossiers.id"), nullable=False)
    previous_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.lease_contracts.id"), nullable=True)
    lessor_person_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.persons.id"), nullable=False)
    lessee_person_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.persons.id"), nullable=False)
    reference: Mapped[str] = mapped_column(String(150), nullable=False)
    terms: Mapped[dict] = mapped_column(JSON, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    terminated_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")


class UnitProfileEpisode(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "unit_profile_episodes"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="unit_profile_dates"),
        CheckConstraint("area_m2 > 0 AND (net_area_m2 IS NULL OR net_area_m2 > 0) AND (gross_area_m2 IS NULL OR gross_area_m2 > 0)", name="unit_profile_area"),
        UniqueConstraint("unit_id", "valid_from", name="uq_unit_profile_start"),
        Index("ix_unit_profile_dates", "unit_id", "valid_from", "valid_to"),
    )
    dossier_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.portal_dossiers.id"), nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    area_m2: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    net_area_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    gross_area_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    use_purpose: Mapped[str] = mapped_column(String(150), nullable=False)
    operating_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(4000), nullable=False)


class PersonMerge(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "person_merges"
    __table_args__ = portal_scope(__tablename__) + (
        UniqueConstraint("source_person_id", name="uq_person_merge_source"),
        CheckConstraint("source_person_id <> target_person_id", name="person_merge_distinct"),
    )
    dossier_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_dossiers.id"), nullable=False)
    source_person_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.persons.id"), nullable=False)
    target_person_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.persons.id"), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(300), nullable=False)


class PropertyNode(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "property_nodes"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("kind IN ('ZONE','FLOOR','COMMON_AREA','COMMERCIAL_SPACE')", name="property_node_kind"),
        UniqueConstraint("site_id", "code", name="uq_property_node_code"),
    )
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.property_nodes.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class UnitLocation(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'unit_locations'
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint('unit_id', name='uq_unit_location_unit'),)
    floor_node_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.property_nodes.id'), nullable=False)
