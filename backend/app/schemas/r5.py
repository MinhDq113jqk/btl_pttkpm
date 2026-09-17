from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


DeliveryStatus = Literal["PENDING", "PROCESSING", "RETRY_SCHEDULED", "PUBLISHED", "DEAD_LETTER"]


class NotificationView(ApiModel):
    id: UUID
    domain_event_id: UUID
    template_code: str
    template_snapshot: dict
    delivery_status: DeliveryStatus
    delivered_at: datetime | None
    read_at: datetime | None
    last_error: str | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationView]


class OutboxEventView(ApiModel):
    id: UUID
    event_type: str
    resource_type: str
    resource_id: UUID
    correlation_id: UUID
    delivery_status: DeliveryStatus
    attempt_count: int
    next_attempt_at: datetime
    last_error: str | None
    created_at: datetime
    published_at: datetime | None


class OutboxEventListResponse(BaseModel):
    items: list[OutboxEventView]


class AuditEventView(ApiModel):
    id: UUID
    actor_account_id: UUID | None
    event_type: str
    action: str
    resource_type: str
    resource_id: UUID
    building_id: UUID | None
    before_data: dict | None
    after_data: dict | None
    reason: str | None
    correlation_id: UUID
    created_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventView]


DashboardMetric = Literal[
    "sla_overdue",
    "maintenance_due",
    "cleaning_rework",
    "open_incidents",
    "ar_debt",
]


class DashboardView(BaseModel):
    """A read-only, server-scoped operational snapshot at one UTC cutoff."""

    as_of: datetime
    sla_overdue_count: int
    maintenance_due_count: int
    cleaning_rework_count: int
    open_incident_count: int
    ar_debt_vnd: int


class DashboardDrillDownItem(BaseModel):
    metric: DashboardMetric
    resource_type: str
    resource_id: UUID
    building_id: UUID
    reference: str
    title: str
    status: str | None
    occurred_at: datetime
    amount_vnd: int | None = None


class DashboardDrillDownResponse(BaseModel):
    as_of: datetime
    metric: DashboardMetric
    items: list[DashboardDrillDownItem]
