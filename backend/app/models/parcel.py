"""Durable parcel record and state contract for the V1 parcel-to-case flow.

Workflow commands, pickup verification, shared Case/Incident links and private
attachments are implemented by the Parcel API while this module remains the
single source of truth for the persisted state machine and database invariants.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin
from app.models.enums import ParcelStatusEnum


PARCEL_STATUS_TRANSITIONS = {
    ParcelStatusEnum.RECEIVED.value: frozenset({
        ParcelStatusEnum.READY_FOR_PICKUP.value,
        ParcelStatusEnum.RETURNED.value,
        ParcelStatusEnum.LOST.value,
        ParcelStatusEnum.DAMAGED.value,
    }),
    ParcelStatusEnum.READY_FOR_PICKUP.value: frozenset({
        ParcelStatusEnum.HANDED_OVER.value,
        ParcelStatusEnum.RETURNED.value,
        ParcelStatusEnum.LOST.value,
        ParcelStatusEnum.DAMAGED.value,
    }),
    ParcelStatusEnum.HANDED_OVER.value: frozenset(),
    ParcelStatusEnum.RETURNED.value: frozenset(),
    ParcelStatusEnum.LOST.value: frozenset(),
    ParcelStatusEnum.DAMAGED.value: frozenset(),
}


class Parcel(IdentityTimestampMixin, Base):
    """A tenant/site/building-scoped received parcel.

    Recipient and actor references use composite tenant foreign keys so a
    caller cannot accidentally attach a parcel to another tenant's identity.
    ``pin_hash`` is deliberately the only PIN representation persisted here;
    plaintext PIN handling stays in the request-only handover workflow.
    """

    __tablename__ = "parcels"
    __table_args__ = (
        ForeignKeyConstraint(
            ["site_id", "tenant_id"],
            ["greencity.sites.id", "greencity.sites.tenant_id"],
            name="fk_parcels_site_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["building_id", "site_id"],
            ["greencity.buildings.id", "greencity.buildings.site_id"],
            name="fk_parcels_building_site",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["unit_id", "building_id"],
            ["greencity.units.id", "greencity.units.building_id"],
            name="fk_parcels_unit_building",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["recipient_person_id", "tenant_id"],
            ["greencity.persons.id", "greencity.persons.tenant_id"],
            name="fk_parcels_recipient_person_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_id", "tenant_id"],
            ["greencity.accounts.id", "greencity.accounts.tenant_id"],
            name="fk_parcels_created_by_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by_id", "tenant_id"],
            ["greencity.accounts.id", "greencity.accounts.tenant_id"],
            name="fk_parcels_updated_by_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["handed_over_by_id", "tenant_id"],
            ["greencity.accounts.id", "greencity.accounts.tenant_id"],
            name="fk_parcels_handed_over_by_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("site_id", "parcel_code", name="uq_parcels_site_code"),
        CheckConstraint(
            "length(trim(parcel_code)) > 0",
            name="parcel_code_not_blank",
        ),
        CheckConstraint(
            "length(trim(recipient_name_snapshot)) > 0",
            name="recipient_name_snapshot_not_blank",
        ),
        CheckConstraint(
            "length(trim(pin_hash)) >= 32",
            name="pin_hash_min_length",
        ),
        CheckConstraint(
            "pin_attempt_count >= 0 AND pin_attempt_count <= 10",
            name="pin_attempts_range",
        ),
        CheckConstraint(
            "version > 0",
            name="version_positive",
        ),
        CheckConstraint(
            "status IN ('RECEIVED','READY_FOR_PICKUP','HANDED_OVER','RETURNED','LOST','DAMAGED')",
            name="status_allowed",
        ),
        CheckConstraint(
            "status NOT IN ('RETURNED','LOST','DAMAGED') OR "
            "(exception_reason IS NOT NULL AND length(trim(exception_reason)) > 0)",
            name="exception_reason_required",
        ),
        CheckConstraint(
            "(status = 'HANDED_OVER' AND handed_over_at IS NOT NULL AND handed_over_by_id IS NOT NULL) OR "
            "(status <> 'HANDED_OVER' AND handed_over_at IS NULL AND handed_over_by_id IS NULL)",
            name="handover_fields_semantics",
        ),
        Index(
            "ix_parcels_scope_status",
            "tenant_id", "site_id", "building_id", "status",
        ),
        Index(
            "ix_parcels_unit_status_received",
            "unit_id", "status", "received_at",
        ),
        Index(
            "ix_parcels_recipient_status",
            "recipient_person_id", "status",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False,
    )
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    unit_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    recipient_person_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    parcel_code: Mapped[str] = mapped_column(String(80), nullable=False)
    carrier_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recipient_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_contact_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    storage_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    pin_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pin_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=ParcelStatusEnum.RECEIVED.value)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ready_for_pickup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handed_over_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handed_over_by_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    exception_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    updated_by_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
