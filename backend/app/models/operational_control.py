"""Scoped operational records; quantities and money use dedicated ledgers."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin
from app.models.resident_portal import PortalScope, portal_scope


class ControlEvent(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "operational_control_events"
    __table_args__ = portal_scope(__tablename__) + (Index("ix_control_event_parent", "parent_type", "parent_id", "created_at"),)
    parent_type: Mapped[str] = mapped_column(String(60))
    parent_id: Mapped[UUID] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON)


class ParkingSlot(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "parking_slots"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("resource_id", "code", name="uq_parking_slot_code"), UniqueConstraint("vehicle_id", name="uq_parking_slot_vehicle"), CheckConstraint("status IN ('OPEN','CLOSED')", name="parking_slot_status"),)
    resource_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_resources.id"))
    code: Mapped[str] = mapped_column(String(80))
    vehicle_types: Mapped[list] = mapped_column(JSON)
    vehicle_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.resident_vehicles.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")


class VisitorParking(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "visitor_parking"
    __table_args__ = portal_scope(__tablename__) + (CheckConstraint("rate_vnd >= 0 AND fee_vnd >= 0 AND paid_vnd >= 0 AND paid_vnd <= fee_vnd", name="visitor_parking_amount"),)
    resource_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_resources.id"))
    plate: Mapped[str] = mapped_column(String(30))
    vehicle_type: Mapped[str] = mapped_column(String(30))
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rate_vnd: Mapped[int] = mapped_column(BigInteger)
    fee_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    paid_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    receipt_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="ENTERED")


class CardBlank(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "card_blanks"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("site_id", "code", name="uq_card_blank_code"), UniqueConstraint("credential_id", name="uq_card_blank_credential"),)
    code: Mapped[str] = mapped_column(String(80))
    credential_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.resident_credentials.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")


class IntegrationEndpoint(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "integration_endpoints"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("site_id", "code", name="uq_integration_endpoint_code"),)
    code: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(24))
    adapter: Mapped[str] = mapped_column(String(40), default="NOT_CONFIGURED")
    status: Mapped[str] = mapped_column(String(24), default="DISABLED")


class IntegrationDelivery(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "integration_deliveries"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("endpoint_id", "source_type", "source_id", "source_version", name="uq_integration_delivery_source"),)
    endpoint_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.integration_endpoints.id"))
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[UUID] = mapped_column(Uuid)
    source_version: Mapped[int] = mapped_column(Integer)
    desired_state: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="NOT_CONFIGURED")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    external_reference: Mapped[str | None] = mapped_column(String(150), nullable=True)


class CommunityResponse(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "community_responses"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("content_id", "unit_id", name="uq_community_response_unit"),)
    content_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.portal_content.id"))
    answer: Mapped[str] = mapped_column(String(2000))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="CONFIRMED")


class NotificationPreference(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("site_id", "account_id", "category", name="uq_notification_preference"),)
    category: Mapped[str] = mapped_column(String(80))
    channel: Mapped[str] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean)


class NotificationTemplate(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "notification_templates"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("site_id", "code", "revision", name="uq_notification_template_revision"),)
    code: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    required_fields: Mapped[list] = mapped_column(JSON)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class NotificationDelivery(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'notification_channel_deliveries'
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint('notification_id', 'channel', name='uq_notification_channel'),)
    notification_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.notification_read_models.id'))
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.accounts.id'))
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24), default='PENDING')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobSchedule(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "job_schedules"
    __table_args__ = portal_scope(__tablename__) + (CheckConstraint("interval_minutes >= 5", name="job_schedule_interval"),)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))
    interval_minutes: Mapped[int] = mapped_column(Integer)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class JobRun(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "job_runs"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("schedule_id", "scheduled_at", name="uq_job_run_due"),)
    schedule_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.job_schedules.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict] = mapped_column(JSON)


class ReportExport(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "report_exports"
    __table_args__ = portal_scope(__tablename__)
    kind: Mapped[str] = mapped_column(String(40))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rows: Mapped[list] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    filters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default='{}')
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default='{}')
    definition_version: Mapped[str] = mapped_column(String(40), nullable=False, default='SAD-1', server_default='LEGACY-COUNTS')


class AccountInvitation(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "account_invitations"
    __table_args__ = portal_scope(__tablename__)
    target_account_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.accounts.id"))
    email: Mapped[str] = mapped_column(String(254))
    verification_reference: Mapped[str] = mapped_column(String(300))
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    delivery_status: Mapped[str] = mapped_column(String(24), default="NOT_CONFIGURED")


class OperationsRecord(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "operations_records"
    __table_args__ = portal_scope(__tablename__) + (Index("ix_operations_record_queue", "tenant_id", "site_id", "building_id", "kind", "status"),)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    approved_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=True)
    related_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class Meter(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "operational_meters"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("site_id", "code", name="uq_operational_meter_code"), CheckConstraint("multiplier > 0 AND baseline >= 0", name="meter_values"), Index('uq_meter_live_serial', 'site_id', 'commodity', 'serial', unique=True, postgresql_where=text("status = 'ACTIVE'")),)
    code: Mapped[str] = mapped_column(String(80))
    commodity: Mapped[str] = mapped_column(String(20))
    serial: Mapped[str] = mapped_column(String(100))
    multiplier: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=1)
    baseline: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    upstream_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.operational_meters.id"), nullable=True)
    replaces_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.operational_meters.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class MeterReading(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "operational_meter_readings"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("meter_id", "read_on", name="uq_meter_read_on"), CheckConstraint("value >= 0 AND consumption >= 0", name="meter_reading_values"),)
    meter_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.operational_meters.id"))
    read_on: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    consumption: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    evidence_reference: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(24), default="SUBMITTED")
    anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=True)


class MeterAssignment(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'meter_assignments'
    __table_args__ = portal_scope(__tablename__) + (
        CheckConstraint('valid_to IS NULL OR valid_to > valid_from', name='meter_assignment_interval'),
        Index('ix_meter_assignment_interval', 'meter_id', 'valid_from', 'valid_to'),
    )
    meter_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.operational_meters.id'))
    point: Mapped[str] = mapped_column(String(200))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_reference: Mapped[str] = mapped_column(String(300))


class TreasuryAccount(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "treasury_accounts"
    __table_args__ = portal_scope(__tablename__) + (CheckConstraint("balance_vnd >= 0 AND reserved_vnd >= 0 AND limit_vnd >= 0 AND spent_vnd >= 0", name="treasury_nonnegative"), UniqueConstraint("site_id", "code", name="uq_treasury_code"),)
    kind: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[str] = mapped_column(String(200))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    limit_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    balance_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    spent_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    approved_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=True)


class Expense(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "operational_expenses"
    __table_args__ = portal_scope(__tablename__) + (CheckConstraint("amount_vnd > 0 AND paid_vnd >= 0 AND paid_vnd <= amount_vnd", name="expense_amount"), UniqueConstraint("site_id", "reference", name="uq_expense_reference"),)
    budget_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.treasury_accounts.id"))
    fund_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.treasury_accounts.id"), nullable=True)
    procurement_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.operations_records.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    amount_vnd: Mapped[int] = mapped_column(BigInteger)
    paid_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    reference: Mapped[str] = mapped_column(String(150))
    evidence_reference: Mapped[str] = mapped_column(String(300))
    allocation: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    approved_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=True)


class TreasuryMovement(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "treasury_movements"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("site_id", "reference", name="uq_treasury_movement_reference"), CheckConstraint("amount_vnd <> 0", name="treasury_movement_nonzero"),)
    treasury_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.treasury_accounts.id"))
    expense_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.operational_expenses.id"), nullable=True)
    amount_vnd: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(24))
    reference: Mapped[str] = mapped_column(String(150))
    evidence_reference: Mapped[str] = mapped_column(String(300))


class StockItem(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "operational_stock_items"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("site_id", "code", "warehouse", "location", "lot", name="uq_stock_item_location"), CheckConstraint("quantity >= 0 AND reserved >= 0 AND reserved <= quantity AND minimum >= 0 AND unit_cost_vnd >= 0", name="stock_item_quantities"), CheckConstraint('damaged_quantity >= 0', name='stock_damaged_nonnegative'))
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    uom: Mapped[str] = mapped_column(String(30))
    warehouse: Mapped[str] = mapped_column(String(80))
    location: Mapped[str] = mapped_column(String(80))
    lot: Mapped[str] = mapped_column(String(80))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    minimum: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    unit_cost_vnd: Mapped[int] = mapped_column(BigInteger)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    damaged_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0, server_default='0')


class StockMovement(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = "operational_stock_movements"
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint("site_id", "reference", "kind", name="uq_stock_movement_reference"),)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.operational_stock_items.id"))
    work_order_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.work_orders.id"), nullable=True)
    related_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.operational_stock_movements.id"), nullable=True)
    destination_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.operational_stock_items.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    reference: Mapped[str] = mapped_column(String(150))
    evidence_reference: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(24), default="POSTED")
    approved_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id"), nullable=True)
    custody: Mapped[dict] = mapped_column(JSON, default=dict, server_default='{}')
