from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.r5 import DeliveryStatus


class ResidentNotificationView(BaseModel):
    id: UUID
    template_code: str
    template_snapshot: dict
    delivery_status: DeliveryStatus
    delivered_at: datetime | None
    read_at: datetime | None
    correlation_id: UUID
    created_at: datetime


class ResidentNotificationListResponse(BaseModel):
    items: list[ResidentNotificationView]
    page: int
    page_size: int
    total: int
    unread_count: int
