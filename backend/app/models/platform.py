from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "tenant_id"], ["greencity.sites.id", "greencity.sites.tenant_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["building_id", "site_id"], ["greencity.buildings.id", "greencity.buildings.site_id"], ondelete="CASCADE"),
        Index("ix_audit_events_scope_created", "tenant_id", "site_id", "created_at"),
        Index("ix_audit_events_actor_account_id", "actor_account_id"),
        Index("ix_audit_events_resource", "resource_type", "resource_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    actor_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DomainEvent(Base):
    """Transactional outbox: workers only see rows after the business commit."""

    __tablename__ = "domain_events"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "tenant_id"], ["greencity.sites.id", "greencity.sites.tenant_id"], ondelete="CASCADE"),
        Index("ix_domain_events_unpublished", "published_at", "created_at"),
        Index("ix_domain_events_actor_account_id", "actor_account_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "site_id", "actor_account_id", "operation", "idempotency_key",
                         name="uq_idempotency_scope_operation_key"),
        ForeignKeyConstraint(["site_id", "tenant_id"], ["greencity.sites.id", "greencity.sites.tenant_id"], ondelete="CASCADE"),
        Index("ix_idempotency_resource", "resource_type", "resource_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_account_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="CASCADE"), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Attachment(IdentityTimestampMixin, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "tenant_id"], ["greencity.sites.id", "greencity.sites.tenant_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["building_id", "site_id"], ["greencity.buildings.id", "greencity.buildings.site_id"], ondelete="CASCADE"),
        UniqueConstraint("storage_key", name="uq_attachments_storage_key"),
        Index("ix_attachments_work_order_created", "work_order_id", "created_at"),
        Index("ix_attachments_uploaded_by_id", "uploaded_by_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    work_order_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.work_orders.id", ondelete="CASCADE"), nullable=False)
    uploaded_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_quarantined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
