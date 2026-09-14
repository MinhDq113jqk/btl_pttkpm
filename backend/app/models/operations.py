from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin


def scope_args():
    return (
        ForeignKeyConstraint(
            ["site_id", "tenant_id"],
            ["greencity.sites.id", "greencity.sites.tenant_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["building_id", "site_id"],
            ["greencity.buildings.id", "greencity.buildings.site_id"],
            ondelete="CASCADE",
        ),
    )


class CleaningRoute(IdentityTimestampMixin, Base):
    __tablename__ = "cleaning_routes"
    __table_args__ = scope_args() + (
        UniqueConstraint("site_id", "code", name="uq_cleaning_routes_site_code"),
        Index("ix_cleaning_routes_scope_active", "tenant_id", "site_id", "is_active"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CleaningArea(IdentityTimestampMixin, Base):
    __tablename__ = "cleaning_areas"
    __table_args__ = scope_args() + (
        UniqueConstraint("site_id", "code", name="uq_cleaning_areas_site_code"),
        Index("ix_cleaning_areas_scope_active", "tenant_id", "site_id", "is_active"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CleaningRouteStop(IdentityTimestampMixin, Base):
    __tablename__ = "cleaning_route_stops"
    __table_args__ = scope_args() + (
        UniqueConstraint("route_id", "cleaning_area_id", name="uq_cleaning_route_stops_route_area"),
        UniqueConstraint("route_id", "position", name="uq_cleaning_route_stops_route_position"),
        CheckConstraint("position > 0", name="cleaning_route_stops_position_positive"),
        Index("ix_cleaning_route_stops_route", "route_id", "position"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    route_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.cleaning_routes.id", ondelete="CASCADE"), nullable=False)
    cleaning_area_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.cleaning_areas.id", ondelete="RESTRICT"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    checklist_template: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CleaningShift(IdentityTimestampMixin, Base):
    __tablename__ = "cleaning_shifts"
    __table_args__ = scope_args() + (
        UniqueConstraint("route_id", "scheduled_start_at", name="uq_cleaning_shifts_route_start"),
        CheckConstraint("scheduled_end_at > scheduled_start_at", name="cleaning_shifts_window_valid"),
        CheckConstraint("status IN ('PLANNED','IN_PROGRESS','COMPLETED','CANCELLED')", name="cleaning_shifts_status"),
        Index("ix_cleaning_shifts_scope_start", "tenant_id", "site_id", "building_id", "scheduled_start_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    route_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.cleaning_routes.id", ondelete="RESTRICT"), nullable=False)
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PLANNED")
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CleaningTask(IdentityTimestampMixin, Base):
    __tablename__ = "cleaning_tasks"
    __table_args__ = scope_args() + (
        UniqueConstraint("shift_id", "route_stop_id", name="uq_cleaning_tasks_shift_stop"),
        UniqueConstraint("rework_of_task_id", name="uq_cleaning_tasks_rework_source"),
        CheckConstraint(
            "status IN ('PLANNED','ASSIGNED','IN_PROGRESS','SUBMITTED','ACCEPTED','MISSED','REWORK_REQUIRED','CANCELLED')",
            name="cleaning_tasks_status",
        ),
        Index("ix_cleaning_tasks_scope_status", "tenant_id", "site_id", "building_id", "status"),
        Index("ix_cleaning_tasks_assignee_status", "assigned_to_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    shift_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.cleaning_shifts.id", ondelete="RESTRICT"), nullable=False)
    route_stop_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.cleaning_route_stops.id", ondelete="RESTRICT"), nullable=False)
    rework_of_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.cleaning_tasks.id", ondelete="RESTRICT"), nullable=True)
    assigned_to_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PLANNED")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CleaningChecklistResult(IdentityTimestampMixin, Base):
    __tablename__ = "cleaning_checklist_results"
    __table_args__ = (
        UniqueConstraint("cleaning_task_id", "position", name="uq_cleaning_checklist_results_task_position"),
        CheckConstraint("position > 0", name="cleaning_checklist_results_position_positive"),
        CheckConstraint("result IN ('PENDING','PASS','FAIL','NOT_APPLICABLE')", name="cleaning_checklist_results_result"),
        Index("ix_cleaning_checklist_results_task", "cleaning_task_id", "position"),
    )

    cleaning_task_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.cleaning_tasks.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    is_required: Mapped[bool] = mapped_column(nullable=False, default=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    performed_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SecurityShift(IdentityTimestampMixin, Base):
    __tablename__ = "security_shifts"
    __table_args__ = scope_args() + (
        UniqueConstraint("building_id", "scheduled_start_at", name="uq_security_shifts_building_start"),
        CheckConstraint("scheduled_end_at > scheduled_start_at", name="security_shifts_window_valid"),
        CheckConstraint("status IN ('PLANNED','IN_PROGRESS','COMPLETED','CANCELLED')", name="security_shifts_status"),
        Index("ix_security_shifts_scope_start", "tenant_id", "site_id", "building_id", "scheduled_start_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    assigned_to_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PLANNED")
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SecurityShiftHandoff(IdentityTimestampMixin, Base):
    __tablename__ = "security_shift_handoffs"
    __table_args__ = scope_args() + (
        Index("ix_security_shift_handoffs_shift", "security_shift_id", "created_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_shift_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.security_shifts.id", ondelete="RESTRICT"), nullable=False)
    handed_over_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    received_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)


class SecurityVisitorLog(IdentityTimestampMixin, Base):
    __tablename__ = "security_visitor_logs"
    __table_args__ = scope_args() + (
        Index("ix_security_visitor_logs_shift_created", "security_shift_id", "created_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_shift_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.security_shifts.id", ondelete="RESTRICT"), nullable=False)
    recorded_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    visitor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    visit_purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    document_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PatrolPoint(IdentityTimestampMixin, Base):
    __tablename__ = "patrol_points"
    __table_args__ = scope_args() + (
        UniqueConstraint("site_id", "code", name="uq_patrol_points_site_code"),
        Index("ix_patrol_points_scope_active", "tenant_id", "site_id", "is_active"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PatrolWindow(IdentityTimestampMixin, Base):
    __tablename__ = "patrol_windows"
    __table_args__ = scope_args() + (
        UniqueConstraint("security_shift_id", "patrol_point_id", "window_start_at", name="uq_patrol_windows_shift_point_start"),
        CheckConstraint("window_end_at > window_start_at", name="patrol_windows_window_valid"),
        CheckConstraint("status IN ('SCHEDULED','COMPLETED','MISSED','CANCELLED')", name="patrol_windows_status"),
        CheckConstraint("status <> 'MISSED' OR length(trim(missed_reason)) > 0", name="patrol_windows_missed_reason"),
        Index("ix_patrol_windows_scope_status", "tenant_id", "site_id", "building_id", "status"),
        Index("ix_patrol_windows_due", "security_shift_id", "window_end_at", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_shift_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.security_shifts.id", ondelete="RESTRICT"), nullable=False)
    patrol_point_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.patrol_points.id", ondelete="RESTRICT"), nullable=False)
    window_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SCHEDULED")
    missed_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PatrolLog(IdentityTimestampMixin, Base):
    __tablename__ = "patrol_logs"
    __table_args__ = (
        CheckConstraint("event_type IN ('CHECK_IN','CHECK_OUT','NOTE')", name="patrol_logs_event_type"),
        Index("ix_patrol_logs_window_created", "patrol_window_id", "created_at"),
    )

    patrol_window_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.patrol_windows.id", ondelete="CASCADE"), nullable=False)
    recorded_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SecurityIncident(IdentityTimestampMixin, Base):
    __tablename__ = "security_incidents"
    __table_args__ = scope_args() + (
        UniqueConstraint("site_id", "code", name="uq_security_incidents_site_code"),
        CheckConstraint("incident_type IN ('SECURITY','FIRE')", name="security_incidents_type"),
        CheckConstraint("severity IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="security_incidents_severity"),
        CheckConstraint("status IN ('NEW','TRIAGED','IN_PROGRESS','RESOLVED','CLOSED')", name="security_incidents_status"),
        Index("ix_security_incidents_scope_status", "tenant_id", "site_id", "building_id", "status"),
        Index("ix_security_incidents_scope_severity", "tenant_id", "site_id", "severity"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patrol_window_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.patrol_windows.id", ondelete="RESTRICT"), nullable=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    incident_type: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NEW")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reported_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    updated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class IncidentEscalation(IdentityTimestampMixin, Base):
    __tablename__ = "incident_escalations"
    __table_args__ = (
        UniqueConstraint("security_incident_id", "target_role", name="uq_incident_escalations_incident_role"),
        CheckConstraint("target_role IN ('security','director')", name="incident_escalations_target_role"),
        Index("ix_incident_escalations_incident", "security_incident_id", "created_at"),
    )

    security_incident_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.security_incidents.id", ondelete="CASCADE"), nullable=False)
    target_role: Mapped[str] = mapped_column(String(20), nullable=False)
    escalated_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class IncidentEscalationAcknowledgement(IdentityTimestampMixin, Base):
    __tablename__ = "incident_escalation_acknowledgements"
    __table_args__ = (
        UniqueConstraint("incident_escalation_id", name="uq_incident_escalation_acknowledgements_escalation"),
        Index("ix_incident_escalation_acknowledgements_escalation", "incident_escalation_id", "created_at"),
    )

    incident_escalation_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.incident_escalations.id", ondelete="CASCADE"), nullable=False)
    acknowledged_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SecurityIncidentEvidence(IdentityTimestampMixin, Base):
    __tablename__ = "security_incident_evidence"
    __table_args__ = (
        CheckConstraint("evidence_type IN ('NOTE','IMAGE','REPORT')", name="security_incident_evidence_type"),
        CheckConstraint("length(trim(description)) > 0", name="security_incident_evidence_description"),
        Index("ix_security_incident_evidence_incident", "security_incident_id", "created_at"),
    )

    security_incident_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.security_incidents.id", ondelete="CASCADE"), nullable=False)
    recorded_by_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    storage_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
