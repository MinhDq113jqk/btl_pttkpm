from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, field_validator
from app.schemas.resident_portal import PortalInput


class AccessCardInput(PortalInput):
    building_id: UUID
    unit_id: UUID
    holder_account_id: UUID
    valid_to: date
    areas: list[str] = Field(min_length=1, max_length=20)
    authorization_record_id: UUID | None = None


class SlotInput(PortalInput):
    resource_id: UUID
    code: str = Field(min_length=1, max_length=80)
    vehicle_types: list[str] = Field(min_length=1, max_length=10)


class VisitorParkingInput(PortalInput):
    resource_id: UUID
    plate: str = Field(min_length=3, max_length=30)
    vehicle_type: str = Field(min_length=2, max_length=30)
    rate_vnd: int = Field(ge=0, le=9999999999)
    entered_at: datetime

    @field_validator('entered_at')
    @classmethod
    def timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError('Thời gian cần múi giờ.')
        return value


class BlankInput(PortalInput):
    building_id: UUID
    code: str = Field(min_length=3, max_length=80)


class EndpointInput(PortalInput):
    building_id: UUID
    code: str = Field(min_length=3, max_length=80)
    kind: Literal['ACCESS', 'PARKING', 'METER', 'ACCOUNTING', 'BANK']


class CommunityAnswer(PortalInput):
    unit_id: UUID
    answer: str = Field(min_length=1, max_length=2000)
    quantity: int = Field(default=1, ge=1, le=1000)


class TemplateInput(PortalInput):
    building_id: UUID
    code: str = Field(pattern=r'^[A-Z][A-Z0-9_]{2,79}$')
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=3, max_length=4000)
    required_fields: list[str] = Field(default_factory=list, max_length=20)
    mandatory: bool = False


class PreferenceInput(PortalInput):
    category: Literal['COMMUNITY', 'SERVICE', 'BILLING', 'SECURITY']
    channel: Literal['IN_APP', 'EMAIL']
    enabled: bool


class JobInput(PortalInput):
    building_id: UUID
    name: str = Field(min_length=3, max_length=200)
    kind: Literal['LIFECYCLE', 'DOCUMENT_EXPIRY', 'MAINTENANCE', 'SLA_SCAN', 'ASSET_DEADLINE', 'SOP_ACK', 'COMMUNITY_DECISION', 'CONTRACT_MILESTONE']
    interval_minutes: int = Field(ge=5, le=525600)
    next_run_at: datetime

    @field_validator('next_run_at')
    @classmethod
    def timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError('Thời gian cần múi giờ.')
        return value


class InvitationInput(PortalInput):
    building_id: UUID
    username: str = Field(pattern=r'^[a-zA-Z0-9_.-]{3,100}$')
    full_name: str = Field(min_length=3, max_length=200)
    person_id: UUID | None = None
    role: Literal['admin', 'director', 'cskh', 'accountant', 'technical_lead', 'technician', 'cleaning', 'security', 'resident']
    email: str = Field(pattern=r'^[^\s@\r\n]+@[^\s@\r\n]+\.[^\s@\r\n]+$', max_length=254)
    verification_reference: str = Field(min_length=3, max_length=300)


class InvitationAccept(PortalInput):
    token: str = Field(min_length=32, max_length=200)
    password: str = Field(min_length=12, max_length=200)
