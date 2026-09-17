"""HTTP DTOs for the V1 parcel intake and handover workflow."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.r2 import ApiModel, InputModel


ParcelStatus = Literal[
    "RECEIVED", "READY_FOR_PICKUP", "HANDED_OVER", "RETURNED", "LOST", "DAMAGED",
]
ParcelExceptionStatus = Literal["RETURNED", "LOST", "DAMAGED"]


class ParcelCreate(InputModel):
    building_id: UUID
    unit_id: UUID
    recipient_person_id: UUID | None = None
    parcel_code: str = Field(min_length=1, max_length=80)
    carrier_reference: str | None = Field(default=None, max_length=120)
    recipient_name_snapshot: str = Field(min_length=1, max_length=200)
    recipient_contact_snapshot: str | None = Field(default=None, max_length=200)
    storage_location: str | None = Field(default=None, max_length=120)
    pin: str = Field(min_length=4, max_length=64)
    received_at: datetime | None = None

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime | None):
        if value is not None and value.tzinfo is None:
            raise ValueError("received_at must include a timezone")
        return value


class ParcelReadyCommand(InputModel):
    expected_version: int = Field(ge=1)


class ParcelHandoverCommand(InputModel):
    expected_version: int = Field(ge=1)
    pin: str = Field(min_length=1, max_length=64)


class ParcelExceptionCommand(InputModel):
    expected_version: int = Field(ge=1)
    status: ParcelExceptionStatus
    reason: str = Field(min_length=3, max_length=500)


class ParcelView(ApiModel):
    id: UUID
    tenant_id: UUID
    site_id: UUID
    building_id: UUID
    unit_id: UUID
    recipient_person_id: UUID | None
    parcel_code: str
    carrier_reference: str | None
    recipient_name_snapshot: str
    recipient_contact_snapshot: str | None
    storage_location: str | None
    pin_attempt_count: int
    pin_locked_until: datetime | None
    status: ParcelStatus
    received_at: datetime
    ready_for_pickup_at: datetime | None
    handed_over_at: datetime | None
    handed_over_by_id: UUID | None
    exception_reason: str | None
    created_by_id: UUID
    updated_by_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class ParcelListResponse(BaseModel):
    items: list[ParcelView]
    page: int
    page_size: int
    total: int


class ParcelCaseCreate(InputModel):
    """Open one shared Case directly from a parcel exception or handover issue."""

    reason: str = Field(min_length=3, max_length=500)


class ParcelCaseView(ApiModel):
    id: UUID
    source_work_order_id: UUID | None
    source_parcel_id: UUID | None
    building_id: UUID
    reason: str
    status: Literal["NEW", "TRIAGED", "IN_PROGRESS", "RESOLVED", "CLOSED"]
    created_by_id: UUID
    updated_by_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class ParcelIncidentLinkCreate(InputModel):
    incident_id: UUID
    reason: str = Field(default="Liên kết incident từ hồ sơ bưu phẩm.", min_length=3, max_length=500)


class ParcelIncidentView(ApiModel):
    id: UUID
    parcel_id: UUID | None
    patrol_window_id: UUID | None
    building_id: UUID
    code: str
    incident_type: Literal["SECURITY", "FIRE"]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    status: Literal["NEW", "TRIAGED", "IN_PROGRESS", "RESOLVED", "CLOSED"]
    title: str
    description: str
    occurred_at: datetime
    reported_by_id: UUID
    version: int


class ParcelAttachmentView(ApiModel):
    id: UUID
    parcel_id: UUID
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ParcelAttachmentListResponse(BaseModel):
    items: list[ParcelAttachmentView]


class ParcelSignedAttachmentLink(BaseModel):
    url: str
    expires_at: datetime


class ParcelTimelineEvent(ApiModel):
    id: UUID
    event_type: str
    action: str
    resource_type: str
    resource_id: UUID
    correlation_id: UUID
    reason: str | None
    before_data: dict | None
    after_data: dict | None
    created_at: datetime


class ParcelTimelineResponse(BaseModel):
    items: list[ParcelTimelineEvent]
