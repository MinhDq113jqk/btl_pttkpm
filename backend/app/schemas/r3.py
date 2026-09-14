from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InputModel(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def strip_text_inputs(cls, value):
        return value.strip() if isinstance(value, str) else value


class VersionCommand(InputModel):
    expected_version: int = Field(ge=1)


class ReasonCommand(VersionCommand):
    reason: str = Field(min_length=3, max_length=500)


class CleaningShiftCreate(InputModel):
    route_id: UUID
    scheduled_start_at: datetime
    scheduled_end_at: datetime

    @field_validator("scheduled_start_at", "scheduled_end_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value


class CleaningTaskAssign(VersionCommand):
    assignee_id: UUID


class CleaningChecklistUpdate(VersionCommand):
    result: Literal["PASS", "FAIL", "NOT_APPLICABLE"]
    note: str | None = Field(default=None, max_length=500)


class CleaningRouteView(ApiModel):
    id: UUID
    code: str
    name: str
    building_id: UUID


class CleaningAssigneeView(ApiModel):
    id: UUID
    full_name: str


class CleaningChecklistResultView(ApiModel):
    id: UUID
    position: int
    label: str
    is_required: bool
    result: Literal["PENDING", "PASS", "FAIL", "NOT_APPLICABLE"]
    note: str | None
    performed_by_id: UUID | None
    performed_at: datetime | None
    version: int


class CleaningTaskView(ApiModel):
    id: UUID
    shift_id: UUID
    route_id: UUID
    route_code: str
    route_name: str
    area_id: UUID
    area_code: str
    area_name: str
    tenant_id: UUID
    site_id: UUID
    building_id: UUID
    assigned_to_id: UUID | None
    status: Literal[
        "PLANNED", "ASSIGNED", "IN_PROGRESS", "SUBMITTED", "ACCEPTED",
        "MISSED", "REWORK_REQUIRED", "CANCELLED",
    ]
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    started_at: datetime | None
    submitted_at: datetime | None
    accepted_at: datetime | None
    accepted_by_id: UUID | None
    rework_work_order_id: UUID | None
    rework_case_id: UUID | None
    version: int
    checklist: list[CleaningChecklistResultView]


class CleaningTaskListResponse(BaseModel):
    items: list[CleaningTaskView]


class CleaningShiftView(ApiModel):
    id: UUID
    route_id: UUID
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    status: Literal["PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
    version: int
    tasks: list[CleaningTaskView]


class PatrolWindowCreate(InputModel):
    patrol_point_id: UUID
    window_start_at: datetime
    window_end_at: datetime

    @field_validator("window_start_at", "window_end_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value


class SecurityShiftCreate(InputModel):
    building_id: UUID
    assignee_id: UUID
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    patrol_windows: list[PatrolWindowCreate] = Field(min_length=1, max_length=50)

    @field_validator("scheduled_start_at", "scheduled_end_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value


class SecurityShiftHandoffCreate(InputModel):
    received_by_id: UUID
    summary: str = Field(min_length=3, max_length=4000)


class SecurityVisitorCreate(InputModel):
    visitor_name: str = Field(min_length=2, max_length=200)
    visit_purpose: str = Field(min_length=3, max_length=500)
    document_reference: str | None = Field(default=None, max_length=100)
    checked_in_at: datetime

    @field_validator("checked_in_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value


class PatrolLogCreate(InputModel):
    event_type: Literal["CHECK_IN", "NOTE"]
    note: str | None = Field(default=None, max_length=500)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value


class PatrolCompleteCommand(VersionCommand):
    note: str | None = Field(default=None, max_length=500)


class SecurityIncidentCreate(InputModel):
    patrol_window_id: UUID
    incident_type: Literal["SECURITY", "FIRE"]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=10000)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value


class SecurityIncidentEvidenceCreate(InputModel):
    evidence_type: Literal["NOTE", "IMAGE", "REPORT"]
    description: str = Field(min_length=3, max_length=10000)
    storage_reference: str | None = Field(default=None, max_length=255)


class SecurityIncidentTransition(VersionCommand):
    status: Literal["TRIAGED", "IN_PROGRESS", "RESOLVED", "CLOSED"]
    conclusion: str | None = Field(default=None, min_length=3, max_length=10000)


class IncidentEscalationAcknowledgementCreate(InputModel):
    note: str | None = Field(default=None, max_length=500)


class SecurityAssigneeView(ApiModel):
    id: UUID
    full_name: str


class PatrolPointView(ApiModel):
    id: UUID
    code: str
    name: str
    building_id: UUID


class SecurityShiftHandoffView(ApiModel):
    id: UUID
    security_shift_id: UUID
    handed_over_by_id: UUID
    received_by_id: UUID
    summary: str
    created_at: datetime


class SecurityVisitorView(ApiModel):
    id: UUID
    security_shift_id: UUID
    recorded_by_id: UUID
    visitor_name: str
    visit_purpose: str
    document_reference: str | None
    checked_in_at: datetime
    created_at: datetime


class PatrolLogView(ApiModel):
    id: UUID
    patrol_window_id: UUID
    recorded_by_id: UUID
    event_type: Literal["CHECK_IN", "CHECK_OUT", "NOTE"]
    note: str | None
    occurred_at: datetime
    created_at: datetime


class PatrolWindowView(ApiModel):
    id: UUID
    security_shift_id: UUID
    patrol_point_id: UUID
    patrol_point_code: str
    patrol_point_name: str
    building_id: UUID
    window_start_at: datetime
    window_end_at: datetime
    status: Literal["SCHEDULED", "COMPLETED", "MISSED", "CANCELLED"]
    missed_reason: str | None
    completed_at: datetime | None
    version: int
    logs: list[PatrolLogView]


class IncidentEscalationAcknowledgementView(ApiModel):
    id: UUID
    incident_escalation_id: UUID
    acknowledged_by_id: UUID
    note: str | None
    created_at: datetime


class IncidentEscalationView(ApiModel):
    id: UUID
    security_incident_id: UUID
    target_role: Literal["security", "director"]
    escalated_by_id: UUID
    reason: str
    created_at: datetime
    acknowledgement: IncidentEscalationAcknowledgementView | None


class SecurityIncidentEvidenceView(ApiModel):
    id: UUID
    security_incident_id: UUID
    recorded_by_id: UUID
    evidence_type: Literal["NOTE", "IMAGE", "REPORT"]
    description: str
    storage_reference: str | None
    created_at: datetime


class SecurityIncidentView(ApiModel):
    id: UUID
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
    conclusion: str | None
    resolved_at: datetime | None
    closed_at: datetime | None
    version: int
    escalations: list[IncidentEscalationView]
    evidence: list[SecurityIncidentEvidenceView]


class SecurityShiftView(ApiModel):
    id: UUID
    tenant_id: UUID
    site_id: UUID
    building_id: UUID
    assigned_to_id: UUID | None
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    status: Literal["PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
    version: int
    handoffs: list[SecurityShiftHandoffView]
    visitors: list[SecurityVisitorView]
    patrol_windows: list[PatrolWindowView]


class SecurityShiftListResponse(BaseModel):
    items: list[SecurityShiftView]


class SecurityDashboardView(BaseModel):
    shifts: list[SecurityShiftView]
    exceptions: list[PatrolWindowView]
    incidents: list[SecurityIncidentView]
