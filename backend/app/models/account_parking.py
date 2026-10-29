"""Account verification and immutable source snapshots for parking reconciliation."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, IdentityTimestampMixin
from app.models.resident_portal import PortalScope, portal_scope


class AccountEmailChange(IdentityTimestampMixin, Base):
    __tablename__ = 'account_email_changes'
    account_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.accounts.id'))
    email: Mapped[str] = mapped_column(String(254))
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_version: Mapped[int] = mapped_column(Integer)
    profile_version: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default='PENDING')


class AccessReview(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'account_access_reviews'
    __table_args__ = portal_scope(__tablename__) + (CheckConstraint("status IN ('OPEN','RESOLVED')", name='access_review_status'),)
    target_account_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.accounts.id'))
    evidence_reference: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    target_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ParkingUsageBatch(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'parking_usage_batches'
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint('resource_id', 'source_reference', name='uq_parking_usage_source'),
        CheckConstraint('ends_at > starts_at', name='parking_usage_interval'),)
    resource_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.portal_resources.id'))
    source_reference: Mapped[str] = mapped_column(String(150))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completeness: Mapped[str] = mapped_column(String(20))
    entries: Mapped[list] = mapped_column(JSON)


class ParkingReconciliation(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'parking_reconciliations'
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint('resource_id', 'digest', name='uq_parking_reconciliation_digest'),)
    resource_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.portal_resources.id'))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    policy_reference: Mapped[str] = mapped_column(String(300))
    require_slots: Mapped[bool] = mapped_column(Boolean)
    digest: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)


class ParkingDiscrepancy(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'parking_discrepancies'
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint('resource_id', 'fingerprint', name='uq_parking_discrepancy_source'),
        CheckConstraint("status IN ('OPEN','RESOLVED')", name='parking_discrepancy_status'),)
    resource_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.portal_resources.id'))
    report_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.parking_reconciliations.id'))
    fingerprint: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(40))
    source: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)
