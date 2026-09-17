from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.r2 import InputModel


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ResidentServiceRequestCreate(InputModel):
    unit_id: UUID
    category_id: UUID
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=4000)
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = "MEDIUM"


class ResidentServiceRequestUpdate(InputModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=4000)
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.title is None and self.description is None and self.priority is None:
            raise ValueError("At least one editable field must be supplied")
        return self


class ResidentServiceRequestView(ApiModel):
    id: UUID
    code: str
    unit_id: UUID
    category_id: UUID
    title: str
    description: str
    priority: str
    status: str
    sla_deadline: datetime
    sla_breached_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class ResidentServiceRequestListResponse(BaseModel):
    items: list[ResidentServiceRequestView]
    page: int
    page_size: int
    total: int


class ResidentRequestTimelineEvent(ApiModel):
    id: UUID
    event_type: str
    action: str
    before_status: str | None
    after_status: str | None
    before_priority: str | None
    after_priority: str | None
    created_at: datetime


class ResidentRequestTimelineResponse(BaseModel):
    items: list[ResidentRequestTimelineEvent]


class ResidentAttachmentView(ApiModel):
    id: UUID
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ResidentAttachmentListResponse(BaseModel):
    items: list[ResidentAttachmentView]


class ResidentSignedAttachmentLink(BaseModel):
    url: str
    expires_at: datetime
