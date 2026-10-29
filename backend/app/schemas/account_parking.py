from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, field_validator, model_validator
from app.schemas.resident_portal import PortalInput, RecoveryVerify


class AccountProfileInput(PortalInput):
    full_name: str = Field(min_length=2, max_length=200)
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    expected_version: int = Field(ge=1)


class EmailChangeInput(PortalInput):
    email: str = Field(max_length=254)
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    expected_version: int = Field(ge=1)

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        return RecoveryVerify.email(value.strip().lower())


class EmailConfirm(PortalInput):
    request_id: UUID
    token: str = Field(min_length=32, max_length=128, repr=False)


class AccessReviewInput(PortalInput):
    target_account_id: UUID
    evidence_reference: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=10, max_length=2000)


class ReviewDecision(PortalInput):
    expected_version: int = Field(ge=1)
    action: Literal['REVIEW', 'REVOKE_SESSIONS', 'LOCK']
    reason: str = Field(min_length=10, max_length=2000)
    current_password: str = Field(min_length=1, max_length=128, repr=False)


class UsageEntry(PortalInput):
    event_reference: str = Field(min_length=1, max_length=100)
    plate: str = Field(min_length=3, max_length=30)
    occurred_at: datetime
    slot_code: str | None = Field(default=None, max_length=80)
    unit_id: UUID | None = None
    holder_account_id: UUID | None = None

    @field_validator('plate')
    @classmethod
    def normalized(cls, value):
        return value.strip().upper().replace(' ', '')


class UsageBatchInput(PortalInput):
    resource_id: UUID
    source_reference: str = Field(min_length=3, max_length=150)
    starts_at: datetime
    ends_at: datetime
    completeness: Literal['COMPLETE', 'PARTIAL']
    entries: list[UsageEntry] = Field(max_length=500)

    @model_validator(mode='after')
    def period(self):
        if not self.starts_at.tzinfo or not self.ends_at.tzinfo or self.ends_at <= self.starts_at:
            raise ValueError('Khoảng nguồn cần múi giờ và ngày kết thúc sau ngày bắt đầu.')
        if any(not e.occurred_at.tzinfo or not self.starts_at <= e.occurred_at < self.ends_at for e in self.entries):
            raise ValueError('Lượt sử dụng phải nằm trong khoảng nguồn [từ, đến).')
        if len({e.event_reference for e in self.entries}) != len(self.entries):
            raise ValueError('Mã lượt sử dụng bị trùng trong nguồn.')
        return self


class ReconcileInput(PortalInput):
    resource_id: UUID
    starts_at: datetime
    ends_at: datetime
    require_slots: bool
    policy_reference: str = Field(min_length=3, max_length=300)

    @model_validator(mode='after')
    def period(self):
        if not self.starts_at.tzinfo or not self.ends_at.tzinfo or self.ends_at <= self.starts_at:
            raise ValueError('Khoảng đối chiếu cần múi giờ và ngày kết thúc sau ngày bắt đầu.')
        return self


class ParkingDecision(PortalInput):
    expected_version: int = Field(ge=1)
    action: Literal['RECORD_DECISION', 'RELEASE_INVALID_SLOT', 'ASSIGN_MISSING_SLOT']
    reason: str = Field(min_length=10, max_length=2000)
    evidence_reference: str = Field(min_length=3, max_length=300)
    slot_id: UUID | None = None
