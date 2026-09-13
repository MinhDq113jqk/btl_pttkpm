from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ServiceRequestStatus = Literal[
    "NEW", "TRIAGED", "IN_PROGRESS", "WAITING_INFO", "RESOLVED", "CLOSED", "CANCELLED",
]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InputModel(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def strip_text_inputs(cls, value):
        return value.strip() if isinstance(value, str) else value


class ServiceRequestCreate(InputModel):
    category_id: UUID
    building_id: UUID
    unit_id: UUID | None = None
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=4000)
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = "MEDIUM"
    linked_request_id: UUID | None = None
    link_type: Literal["DUPLICATE", "SPLIT", "MERGED"] | None = None
    link_reason: str | None = Field(default=None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_link(self):
        supplied = (self.linked_request_id, self.link_type, self.link_reason)
        if any(value is not None for value in supplied) and not all(value is not None for value in supplied):
            raise ValueError("linked_request_id, link_type and link_reason must be supplied together")
        return self


class ServiceRequestView(ApiModel):
    id: UUID
    code: str
    tenant_id: UUID
    site_id: UUID
    building_id: UUID
    unit_id: UUID | None
    category_id: UUID
    linked_request_id: UUID | None
    link_type: str | None
    link_reason: str | None
    title: str
    description: str
    priority: str
    status: str
    sla_started_at: datetime
    sla_duration_minutes: int
    sla_deadline: datetime
    sla_breached_at: datetime | None
    owner_account_id: UUID
    resolved_at: datetime | None
    closed_at: datetime | None
    csat_score: int | None
    version: int


class ServiceRequestListItem(ApiModel):
    id: UUID
    code: str
    title: str
    unit_id: UUID | None
    unit_number: str | None
    building_id: UUID
    building_code: str
    building_name: str
    status: ServiceRequestStatus
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"]
    sla_deadline: datetime
    created_at: datetime


class ServiceRequestListResponse(BaseModel):
    items: list[ServiceRequestListItem]
    page: int
    page_size: int
    total: int


class TriageRequest(InputModel):
    expected_version: int = Field(ge=1)
    owner_account_id: UUID
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"]


class ChecklistTemplateItem(InputModel):
    label: str = Field(min_length=2, max_length=300)
    required: bool = True


class WorkOrderCreate(InputModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=4000)
    checklist: list[ChecklistTemplateItem] = Field(min_length=1, max_length=50)


class WorkOrderAssign(InputModel):
    assignee_id: UUID
    expected_version: int = Field(ge=1)


class VersionCommand(InputModel):
    expected_version: int = Field(ge=1)


class ReasonCommand(VersionCommand):
    reason: str = Field(min_length=3, max_length=500)


class ChecklistUpdate(VersionCommand):
    is_completed: bool
    result: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_result_when_completed(self):
        if self.is_completed and not (self.result or "").strip():
            raise ValueError("A completed checklist item requires a result")
        return self


class WorkOrderSubmit(VersionCommand):
    result_summary: str = Field(min_length=3, max_length=4000)


class WorkOrderAccept(VersionCommand):
    mode: Literal["PROXY", "TECHNICAL"]
    reason: str | None = Field(default=None, max_length=500)
    evidence_id: UUID | None = None

    @model_validator(mode="after")
    def validate_proxy_evidence(self):
        if self.mode == "PROXY" and (not (self.reason or "").strip() or self.evidence_id is None):
            raise ValueError("Proxy acceptance requires reason and evidence_id")
        return self


class WorkOrderClose(VersionCommand):
    csat_score: int | None = Field(default=None, ge=1, le=5)


class ChecklistItemView(ApiModel):
    id: UUID
    position: int
    label: str
    is_required: bool
    is_completed: bool
    result: str | None
    version: int


class WorkOrderView(ApiModel):
    id: UUID
    code: str
    tenant_id: UUID
    site_id: UUID
    building_id: UUID
    service_request_id: UUID | None
    maintenance_occurrence_id: UUID | None
    title: str
    description: str
    status: str
    assigned_to_id: UUID | None
    acceptance_mode: str | None
    acceptance_reason: str | None
    acceptance_evidence_id: UUID | None
    result_summary: str | None
    completed_at: datetime | None
    closed_at: datetime | None
    version: int
    checklist: list[ChecklistItemView]
    evidence_count: int


class CostLineCreate(InputModel):
    description: str = Field(min_length=2, max_length=300)
    amount_vnd: int = Field(gt=0, le=2_000_000_000)
    cost_bearer: Literal["RESIDENT", "MANAGEMENT"]
    evidence_attachment_id: UUID | None = None

    @field_validator("amount_vnd", mode="before")
    @classmethod
    def reject_non_integer_money(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("amount_vnd must be an integer")
        return value


class CostLineView(ApiModel):
    id: UUID
    work_order_id: UUID
    description: str
    amount_vnd: int
    cost_bearer: str
    status: str
    evidence_attachment_id: UUID | None
    version: int
    pending_charge_id: UUID | None = None


class ChargeDecision(VersionCommand):
    decision: Literal["APPROVE", "REJECT"]
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def rejection_requires_reason(self):
        if self.decision == "REJECT" and not (self.reason or "").strip():
            raise ValueError("A rejected charge requires a reason")
        return self


class ChargePost(VersionCommand):
    posting_reference: str = Field(min_length=3, max_length=100)


class PendingChargeView(ApiModel):
    id: UUID
    cost_line_id: UUID
    status: str
    submitted_by_id: UUID
    reviewed_by_id: UUID | None
    reviewed_at: datetime | None
    review_reason: str | None
    posted_at: datetime | None
    version: int


class AttachmentView(ApiModel):
    id: UUID
    work_order_id: UUID
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str


class SignedAttachmentLink(BaseModel):
    url: str
    expires_at: datetime


class AssetCreate(InputModel):
    building_id: UUID
    unit_id: UUID | None = None
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=4000)


class AssetView(ApiModel):
    id: UUID
    tenant_id: UUID
    site_id: UUID
    building_id: UUID
    unit_id: UUID | None
    code: str
    name: str
    description: str
    status: str
    version: int


class MaintenancePlanCreate(InputModel):
    asset_id: UUID
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    title: str = Field(min_length=3, max_length=200)
    interval_days: int = Field(ge=1, le=3650)
    next_due_at: datetime
    checklist: list[ChecklistTemplateItem] = Field(min_length=1, max_length=50)
    evidence_required: bool = True

    @field_validator("next_due_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError("next_due_at must include a timezone")
        return value


class MaintenancePlanView(ApiModel):
    id: UUID
    tenant_id: UUID
    site_id: UUID
    building_id: UUID
    asset_id: UUID
    code: str
    title: str
    interval_days: int
    next_due_at: datetime
    checklist_template: list
    evidence_required: bool
    is_active: bool
    version: int


class MaintenanceDefer(VersionCommand):
    defer_until: datetime
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("defer_until")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError("defer_until must include a timezone")
        return value


class SchedulerRun(InputModel):
    as_of: datetime

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        return value


class SchedulerOccurrenceView(ApiModel):
    occurrence_id: UUID
    work_order_id: UUID | None
    plan_id: UUID
    due_at: datetime
    replayed: bool


class SchedulerRunView(BaseModel):
    items: list[SchedulerOccurrenceView]


class SlaRun(InputModel):
    as_of: datetime

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError("as_of must include a timezone")
        return value


class SlaRunView(BaseModel):
    breached_request_ids: list[UUID]
