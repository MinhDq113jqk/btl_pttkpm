"""Scoped records for community execution, SLA policy and dataset acceptance."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, IdentityTimestampMixin
from app.models.resident_portal import PortalScope, portal_scope


class CommunityTask(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'community_tasks'
    __table_args__ = portal_scope(__tablename__) + (
        UniqueConstraint('content_id', 'decision_key', name='uq_community_decision'),
        CheckConstraint("status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')", name='community_task_status'),)
    content_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.portal_content.id'))
    decision_key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.accounts.id'))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    result: Mapped[str] = mapped_column(Text, default='')
    evidence_reference: Mapped[str] = mapped_column(String(300), default='')


class SlaPolicy(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'sla_policies'
    __table_args__ = portal_scope(__tablename__)
    category_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.service_categories.id'))
    definition: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='DRAFT')
    approved_by_id: Mapped[UUID | None] = mapped_column(ForeignKey('greencity.accounts.id'), nullable=True)


class InitDataset(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'init_datasets'
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint("status IN ('DRAFT','SUBMITTED','CHECKED','ACCEPTED','REJECTED')", name='init_dataset_status'),)
    name: Mapped[str] = mapped_column(String(200))
    manifest: Mapped[dict] = mapped_column(JSON)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    source_digest: Mapped[str] = mapped_column(String(64), default='')
    status: Mapped[str] = mapped_column(String(20), default='DRAFT')
    checker_id: Mapped[UUID | None] = mapped_column(ForeignKey('greencity.accounts.id'), nullable=True)
    confirmer_id: Mapped[UUID | None] = mapped_column(ForeignKey('greencity.accounts.id'), nullable=True)


class JobEffect(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'job_effects'
    __table_args__ = portal_scope(__tablename__) + (
        UniqueConstraint('site_id', 'effect_key', name='uq_job_effect_key'),)
    effect_key: Mapped[str] = mapped_column(String(300))
    run_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.job_runs.id'))
    source_type: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[UUID] = mapped_column()
    result: Mapped[dict] = mapped_column(JSON)
