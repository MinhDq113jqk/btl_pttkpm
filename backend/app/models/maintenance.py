from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin


def scope_args():
    return (
        ForeignKeyConstraint(["site_id", "tenant_id"], ["greencity.sites.id", "greencity.sites.tenant_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["building_id", "site_id"], ["greencity.buildings.id", "greencity.buildings.site_id"], ondelete="CASCADE"),
    )


class Asset(IdentityTimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = scope_args() + (
        ForeignKeyConstraint(["unit_id", "building_id"], ["greencity.units.id", "greencity.units.building_id"], ondelete="RESTRICT"),
        UniqueConstraint("site_id", "code", name="uq_assets_site_code"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE','RETIRED')", name="assets_status"),
        Index("ix_assets_scope_status", "tenant_id", "site_id", "status"),
        Index("ix_assets_unit_id", "unit_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    unit_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    updated_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MaintenancePlan(IdentityTimestampMixin, Base):
    __tablename__ = "maintenance_plans"
    __table_args__ = scope_args() + (
        UniqueConstraint("asset_id", "code", name="uq_maintenance_plans_asset_code"),
        CheckConstraint("interval_days > 0 AND interval_days <= 3650", name="maintenance_plans_interval_range"),
        Index("ix_maintenance_plans_due", "site_id", "is_active", "next_due_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.assets.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checklist_template: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence_required: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    updated_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MaintenanceOccurrence(IdentityTimestampMixin, Base):
    __tablename__ = "maintenance_occurrences"
    __table_args__ = scope_args() + (
        UniqueConstraint("plan_id", "due_at", name="uq_maintenance_occurrences_plan_due"),
        CheckConstraint("status IN ('DUE','WO_CREATED','IN_PROGRESS','COMPLETED','DEFERRED','CANCELLED')", name="maintenance_occurrences_status"),
        Index("ix_maintenance_occurrences_scope_status", "tenant_id", "site_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.maintenance_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DUE")
    defer_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    defer_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    updated_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MaintenanceHistory(Base):
    __tablename__ = "maintenance_history"
    __table_args__ = (
        UniqueConstraint("occurrence_id", name="uq_maintenance_history_occurrence"),
        Index("ix_maintenance_history_asset_completed", "asset_id", "completed_at"),
        Index("ix_maintenance_history_work_order_id", "work_order_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.sites.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.assets.id", ondelete="CASCADE"), nullable=False)
    occurrence_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.maintenance_occurrences.id", ondelete="RESTRICT"), nullable=False)
    work_order_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.work_orders.id", ondelete="RESTRICT"), nullable=False)
    performed_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    accepted_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    result_summary: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
