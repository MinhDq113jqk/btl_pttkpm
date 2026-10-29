"""Resident portal records. Monetary history and approvals are append-only."""
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, DateTime,
                        ForeignKey, ForeignKeyConstraint, Index, Integer, JSON,
                        String, Text, UniqueConstraint, Uuid, text)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin


class PortalScope:
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    unit_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


def portal_scope(name):
    return (
        ForeignKeyConstraint(["site_id", "tenant_id"], ["greencity.sites.id", "greencity.sites.tenant_id"], name=f"fk_{name}_site", ondelete="RESTRICT"),
        ForeignKeyConstraint(["building_id", "site_id"], ["greencity.buildings.id", "greencity.buildings.site_id"], name=f"fk_{name}_building", ondelete="RESTRICT"),
        ForeignKeyConstraint(["unit_id", "building_id"], ["greencity.units.id", "greencity.units.building_id"], name=f"fk_{name}_unit", ondelete="RESTRICT"),
        ForeignKeyConstraint(["account_id", "tenant_id"], ["greencity.accounts.id", "greencity.accounts.tenant_id"], name=f"fk_{name}_account", ondelete="RESTRICT"),
        UniqueConstraint("id", "tenant_id", "site_id", name=f"uq_{name}_scope"),
        CheckConstraint("version > 0", name=f"{name}_version"),
        CheckConstraint("unit_id IS NULL OR building_id IS NOT NULL", name=f"{name}_unit_scope"),
        Index(f"ix_{name}_scope", "tenant_id", "site_id", "building_id", "unit_id"),
    )


class PortalDossier(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "portal_dossiers"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("kind IN ('PROFILE_CHANGE','MOVE_IN','MOVE_OUT','ABSENCE','RETURN','LEASE','DELEGATION','TRANSFER','RENOVATION','LEASE_RENEW','LEASE_AMEND','LEASE_TERMINATE','LIABILITY_CHANGE','UNIT_PROFILE','HANDOVER','UNIT_STATUS','PERSON_MERGE')", name="portal_dossiers_kind"),
        CheckConstraint("status IN ('SUBMITTED','WAITING_INFO','APPROVED','REJECTED','CANCELLED','COMPLETED','REVOKED','IN_PROGRESS')", name="portal_dossiers_status"),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="portal_dossiers_interval"),
        Index("ix_portal_dossiers_queue", "tenant_id", "site_id", "status", "created_at"),
    )
    person_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.persons.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="SUBMITTED")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PortalDossierEvent(IdentityTimestampMixin, Base):
    __tablename__ = "portal_dossier_events"
    dossier_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_dossiers.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class ResidentDelegation(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "resident_delegations"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("valid_to > valid_from", name="resident_delegations_interval"),
        UniqueConstraint("dossier_id", name="uq_resident_delegations_dossier"),
        Index("ix_resident_delegations_person", "delegate_person_id", "valid_from", "valid_to"),
    )
    dossier_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_dossiers.id"), nullable=False)
    delegate_person_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.persons.id"), nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LiabilityEpisode(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "resident_liability_episodes"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="resident_liability_interval"),
        Index("ix_resident_liability_effective", "unit_id", "valid_from", "valid_to"),
    )
    person_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.persons.id"), nullable=False)
    dossier_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_dossiers.id"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class PortalResource(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "portal_resources"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("kind IN ('PARKING','FACILITY','SERVICE')", name="portal_resources_kind"),
        CheckConstraint("capacity > 0 AND fee_vnd >= 0 AND deposit_vnd >= 0", name="portal_resources_amounts"),
        CheckConstraint("status IN ('OPEN','CLOSED')", name="portal_resources_status"),
        Index("ix_portal_resources_kind", "tenant_id", "site_id", "kind", "status"),
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deposit_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    policy: Mapped[dict] = mapped_column(JSON, nullable=False)


class PortalFeeSource(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "portal_fee_sources"
    __table_args__ = portal_scope(__tablename__) + (
        UniqueConstraint("source_kind", "source_id", name="uq_portal_fee_sources_origin"),
        CheckConstraint("amount_vnd >= 0", name="portal_fee_sources_amount"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="portal_fee_sources_interval"),
        CheckConstraint("status IN ('ACTIVE','PAUSED','ENDED')", name="portal_fee_sources_status"),
    )
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    basis: Mapped[str] = mapped_column(String(30), nullable=False)
    recurring: Mapped[bool] = mapped_column(Boolean, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE")


class PortalFeeInterval(IdentityTimestampMixin, Base):
    __tablename__ = "portal_fee_intervals"
    __table_args__ = (
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="portal_fee_intervals_dates"),
        CheckConstraint("amount_vnd >= 0 AND rounding_unit_vnd > 0", name="portal_fee_intervals_amounts"),
        Index("ix_portal_fee_intervals_source_dates", "fee_source_id", "starts_on"),
        Index("uq_portal_fee_intervals_open", "fee_source_id", unique=True, postgresql_where=text("ends_on IS NULL")),
    )
    fee_source_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_fee_sources.id", ondelete="RESTRICT"), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rounding_unit_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1, server_default="1")


class PortalFeePosting(IdentityTimestampMixin, Base):
    __tablename__ = "portal_fee_postings"
    __table_args__ = (UniqueConstraint("fee_source_id", "period_id", name="uq_portal_fee_postings_period"),)
    fee_source_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_fee_sources.id"), nullable=False)
    period_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounting_periods.id"), nullable=False)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.billing_invoices.id"), nullable=False)
    liable_person_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.persons.id"), nullable=True)


class PortalDeposit(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "portal_deposits"
    __table_args__ = portal_scope(__tablename__) + (
        UniqueConstraint("source_kind", "source_id", name="uq_portal_deposits_origin"),
        CheckConstraint("required_vnd >= 0 AND balance_vnd >= 0 AND refundable_vnd >= 0 AND refundable_vnd <= balance_vnd", name="portal_deposits_balance"),
        CheckConstraint("status IN ('AWAITING_FUNDS','HELD','RELEASED','CLOSED')", name="portal_deposits_status"),
    )
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    required_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    refundable_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="AWAITING_FUNDS")


class PortalDepositMovement(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "portal_deposit_movements"
    __table_args__ = portal_scope(__tablename__) + (
        UniqueConstraint("tenant_id", "site_id", "kind", "reference", name="uq_portal_deposit_movements_reference"),
        CheckConstraint("kind IN ('RECEIVE','DEDUCT','RELEASE','REFUND') AND amount_vnd > 0", name="portal_deposit_movements_amount"),
    )
    deposit_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_deposits.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference: Mapped[str] = mapped_column(String(150), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=False)


class VehicleRegistration(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "resident_vehicles"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("status IN ('PENDING','WAITING','OFFERED','ACTIVE','PAUSED','CANCELLED')", name="resident_vehicles_status"),
        Index("ix_resident_vehicles_capacity", "resource_id", "status", "created_at"),
        Index("uq_resident_vehicles_live_plate", "tenant_id", "site_id", "plate", unique=True, postgresql_where=text("status <> 'CANCELLED'")),
    )
    resource_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_resources.id"), nullable=False)
    plate: Mapped[str] = mapped_column(String(30), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class ResidentCredential(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "resident_credentials"
    __table_args__ = portal_scope(__tablename__) + (
        UniqueConstraint("site_id", "code", name="uq_resident_credentials_code"),
        CheckConstraint("status IN ('ACTIVE','LOST','LOCKED','REVOKED','EXPIRED')", name="resident_credentials_status"),
        Index("uq_resident_credentials_live_vehicle", "vehicle_id", unique=True, postgresql_where=text("status = 'ACTIVE'")),
    )
    vehicle_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.resident_vehicles.id"), nullable=True, index=True)
    authorization_record_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    replaces_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.resident_credentials.id"), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(30), nullable=False, default="NOT_CONFIGURED")
    applied_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    access_scope: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")


class FacilityBooking(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "resident_bookings"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("ends_at > starts_at AND quantity > 0", name="resident_bookings_interval"),
        CheckConstraint("status IN ('WAITING','AWAITING_DEPOSIT','CONFIRMED','CHECKED_IN','COMPLETED','CANCELLED','NO_SHOW')", name="resident_bookings_status"),
        Index("ix_resident_bookings_capacity", "resource_id", "starts_at", "ends_at", "status"),
    )
    resource_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_resources.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class ServiceEnrollment(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "resident_service_enrollments"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("status IN ('PENDING','ACTIVE','PAUSED','ENDED','REJECTED')", name="resident_service_enrollments_status"),
        Index("ix_resident_service_enrollments_resource", "resource_id", "status"),
        Index("uq_resident_service_enrollments_live", "unit_id", "resource_id", unique=True, postgresql_where=text("status IN ('PENDING','ACTIVE','PAUSED')")),
    )
    resource_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_resources.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class PortalRequestMessage(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "resident_request_messages"
    __table_args__ = portal_scope(__tablename__) + (
        Index("ix_resident_request_messages_request", "service_request_id", "created_at"),
    )
    service_request_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.service_requests.id"), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)


class ResidentDocument(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "resident_documents"
    __table_args__ = portal_scope(__tablename__) + (
        UniqueConstraint("storage_key", name="uq_resident_documents_storage"),
        UniqueConstraint("replaces_id", name="uq_resident_documents_replaces"),
        CheckConstraint("size_bytes > 0", name="resident_documents_size"),
        Index("ix_resident_documents_dossier", "dossier_id", "created_at"),
    )
    dossier_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.portal_dossiers.id"), nullable=True)
    replaces_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.resident_documents.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quarantined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    verification_status: Mapped[str] = mapped_column(String(24), nullable=False, default="UNVERIFIED", server_default="UNVERIFIED")
    verified_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    retain_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PortalContent(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "portal_content"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("kind IN ('GUIDE','NOTICE','OUTAGE','MAINTENANCE','EVENT','SURVEY','VOTE','MEETING')", name="portal_content_kind"),
        CheckConstraint("status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','PUBLISHED','WITHDRAWN','CLOSED')", name="portal_content_status"),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="portal_content_interval"),
        Index("ix_portal_content_publish", "tenant_id", "site_id", "status", "publish_at"),
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    publish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.resident_documents.id"), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=True)
    policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    previous_id: Mapped[UUID | None] = mapped_column(ForeignKey('greencity.portal_content.id'), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    minutes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default='{}')


class PortalPaymentIntent(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "portal_payment_intents"
    __table_args__ = portal_scope(__tablename__) + (
        UniqueConstraint("reference", name="uq_portal_payment_intents_reference"),
        UniqueConstraint("provider_transaction", name="uq_portal_payment_intents_provider"),
        CheckConstraint("amount_vnd > 0", name="portal_payment_intents_amount"),
        CheckConstraint("status IN ('PENDING','PAID','FAILED','EXPIRED','RECONCILIATION')", name="portal_payment_intents_status"),
    )
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.billing_invoices.id"), nullable=False)
    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_transaction: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider_amount_vnd: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.payments.id"), nullable=True)


class AccountRecovery(IdentityTimestampMixin, Base):
    __tablename__ = "account_recovery_requests"
    __table_args__ = (
        Index("ix_account_recovery_queue", "tenant_id", "status", "created_at"),
        CheckConstraint("status IN ('PENDING','VERIFIED','USED','REJECTED')", name="account_recovery_status"),
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id"), nullable=False)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=False)
    site_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.sites.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    verified_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    issued_session_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PortalFinancialAdjustment(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "portal_financial_adjustments"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("kind IN ('CREDIT','REFUND') AND amount_vnd > 0", name="portal_financial_adjustments_amount"),
        CheckConstraint("status IN ('REQUESTED','APPROVED','SENDING','COMPLETED','RECONCILIATION','REJECTED')", name="portal_financial_adjustments_status"),
        UniqueConstraint("provider_request_id", name="uq_portal_financial_adjustments_provider_request"),
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.billing_invoices.id"), nullable=False)
    payment_intent_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.portal_payment_intents.id"), nullable=True)
    period_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounting_periods.id"), nullable=True)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="REQUESTED")
    requested_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=False)
    approved_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_transaction: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)


class PortalResourceClosure(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "portal_resource_closures"
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("ends_at > starts_at", name="portal_resource_closures_interval"),
        CheckConstraint("status IN ('SCHEDULED','CANCELLED')", name="portal_resource_closures_status"),
        Index("ix_portal_resource_closures_interval", "resource_id", "starts_at", "ends_at"),
    )
    resource_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_resources.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SCHEDULED")
