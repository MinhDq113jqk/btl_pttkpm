from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin


def scope_args():
    return (
        ForeignKeyConstraint(["site_id", "tenant_id"], ["greencity.sites.id", "greencity.sites.tenant_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["building_id", "site_id"], ["greencity.buildings.id", "greencity.buildings.site_id"], ondelete="CASCADE"),
    )


class ServiceCategory(IdentityTimestampMixin, Base):
    __tablename__ = "service_categories"
    __table_args__ = scope_args() + (
        UniqueConstraint("site_id", "code", name="uq_service_categories_site_code"),
        CheckConstraint("sla_minutes > 0 AND sla_minutes <= 525600", name="service_categories_sla_range"),
        Index("ix_service_categories_scope", "tenant_id", "site_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sla_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ServiceRequest(IdentityTimestampMixin, Base):
    __tablename__ = "service_requests"
    __table_args__ = scope_args() + (
        ForeignKeyConstraint(["unit_id", "building_id"], ["greencity.units.id", "greencity.units.building_id"], ondelete="RESTRICT"),
        UniqueConstraint("site_id", "code", name="uq_service_requests_site_code"),
        CheckConstraint("status IN ('NEW','TRIAGED','IN_PROGRESS','WAITING_INFO','RESOLVED','CLOSED','CANCELLED')", name="service_requests_status"),
        CheckConstraint("priority IN ('LOW','MEDIUM','HIGH','URGENT')", name="service_requests_priority"),
        CheckConstraint("sla_duration_minutes > 0 AND sla_duration_minutes <= 525600", name="service_requests_sla_range"),
        CheckConstraint(
            "(linked_request_id IS NULL AND link_type IS NULL AND link_reason IS NULL) OR "
            "(linked_request_id IS NOT NULL AND link_type IN ('DUPLICATE','SPLIT','MERGED') "
            "AND length(trim(link_reason)) > 0)",
            name="link_consistency",
        ),
        CheckConstraint("csat_score IS NULL OR csat_score BETWEEN 1 AND 5", name="csat_score"),
        Index("ix_service_requests_scope_status", "tenant_id", "site_id", "status"),
        Index("ix_service_requests_unit_id", "unit_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    unit_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    category_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.service_categories.id", ondelete="RESTRICT"), nullable=False, index=True)
    linked_request_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.service_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    link_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    link_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="NEW")
    sla_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sla_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    sla_breached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_account_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    updated_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    csat_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WorkOrder(IdentityTimestampMixin, Base):
    __tablename__ = "work_orders"
    __table_args__ = scope_args() + (
        UniqueConstraint("site_id", "code", name="uq_work_orders_site_code"),
        UniqueConstraint("maintenance_occurrence_id", name="uq_work_orders_maintenance_occurrence"),
        CheckConstraint("(service_request_id IS NULL) <> (maintenance_occurrence_id IS NULL)", name="work_orders_one_source"),
        CheckConstraint("status IN ('DRAFT','ASSIGNED','IN_PROGRESS','ON_HOLD','WAITING_ACCEPTANCE','COMPLETED','CLOSED','CANCELLED')", name="work_orders_status"),
        Index("ix_work_orders_scope_status", "tenant_id", "site_id", "status"),
        Index("ix_work_orders_assignee_status", "assigned_to_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    service_request_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.service_requests.id", ondelete="RESTRICT"), nullable=True, index=True)
    maintenance_occurrence_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("greencity.maintenance_occurrences.id",
                   name="fk_work_orders_maintenance_occurrence", ondelete="RESTRICT"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    assigned_to_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    updated_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    accepted_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    acceptance_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    acceptance_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    acceptance_evidence_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WorkOrderChecklistItem(IdentityTimestampMixin, Base):
    __tablename__ = "work_order_checklist_items"
    __table_args__ = (
        UniqueConstraint("work_order_id", "position", name="uq_work_order_checklist_position"),
        CheckConstraint("position > 0", name="work_order_checklist_position_positive"),
        Index("ix_work_order_checklist_work_order", "work_order_id"),
        Index("ix_work_order_checklist_items_completed_by_id", "completed_by_id"),
    )

    work_order_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.work_orders.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    is_required: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_completed: Mapped[bool] = mapped_column(nullable=False, default=False)
    result: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completed_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CostLine(IdentityTimestampMixin, Base):
    __tablename__ = "cost_lines"
    __table_args__ = (
        CheckConstraint("amount_vnd > 0", name="cost_lines_amount_positive"),
        CheckConstraint("cost_bearer IN ('RESIDENT','MANAGEMENT')", name="cost_lines_bearer"),
        CheckConstraint("status IN ('DRAFT','SUBMITTED','CANCELLED')", name="cost_lines_status"),
        Index("ix_cost_lines_work_order", "work_order_id"),
        Index("ix_cost_lines_evidence_attachment_id", "evidence_attachment_id"),
    )

    work_order_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.work_orders.id", ondelete="RESTRICT"), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    amount_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_bearer: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SUBMITTED")
    evidence_attachment_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.attachments.id", ondelete="RESTRICT"), nullable=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    updated_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PendingCharge(IdentityTimestampMixin, Base):
    __tablename__ = "pending_charges"
    __table_args__ = (
        UniqueConstraint("cost_line_id", name="uq_pending_charges_cost_line"),
        CheckConstraint("status IN ('SUBMITTED','APPROVED','REJECTED','CANCELLED','POSTED','REVERSED')", name="pending_charges_status"),
        Index("ix_pending_charges_submitted_by_id", "submitted_by_id"),
        Index("ix_pending_charges_reviewed_by_id", "reviewed_by_id"),
    )

    cost_line_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.cost_lines.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SUBMITTED")
    submitted_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    reviewed_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class InvoiceItem(IdentityTimestampMixin, Base):
    """R2 posting anchor; R4 will attach this immutable source to an invoice."""

    __tablename__ = "invoice_items"
    __table_args__ = (
        UniqueConstraint("pending_charge_id", name="uq_invoice_items_pending_charge"),
        UniqueConstraint("site_id", "posting_reference", name="uq_invoice_items_site_reference"),
        CheckConstraint("amount_vnd > 0", name="invoice_items_amount_positive"),
        Index("ix_invoice_items_created_by_id", "created_by_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.sites.id", ondelete="CASCADE"), nullable=False)
    pending_charge_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.pending_charges.id", ondelete="RESTRICT"), nullable=False)
    posting_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    amount_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)


class CaseRecord(IdentityTimestampMixin, Base):
    __tablename__ = "cases"
    __table_args__ = scope_args() + (
        CheckConstraint("status IN ('NEW','TRIAGED','IN_PROGRESS','RESOLVED','CLOSED')", name="cases_status"),
        Index("ix_cases_source_work_order", "source_work_order_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_work_order_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.work_orders.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NEW")
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    updated_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ChargeReversal(Base):
    __tablename__ = "charge_reversals"
    __table_args__ = (
        UniqueConstraint("pending_charge_id", name="uq_charge_reversals_pending_charge"),
        Index("ix_charge_reversals_case_id", "case_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    pending_charge_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.pending_charges.id", ondelete="RESTRICT"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.cases.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
