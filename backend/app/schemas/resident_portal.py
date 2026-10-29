from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PortalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DossierCreate(PortalInput):
    unit_id: UUID
    person_id: UUID | None = None
    kind: Literal["PROFILE_CHANGE", "MOVE_IN", "MOVE_OUT", "ABSENCE", "RETURN", "LEASE", "DELEGATION", "TRANSFER", "RENOVATION", "LEASE_RENEW", "LEASE_AMEND", "LEASE_TERMINATE", "LIABILITY_CHANGE", "UNIT_PROFILE", "HANDOVER", "UNIT_STATUS", "PERSON_MERGE"]
    title: str = Field(min_length=3, max_length=200)
    data: dict = Field(default_factory=dict)
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def interval(self):
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("Ngày kết thúc phải sau ngày bắt đầu.")
        return self


class PortalAction(PortalInput):
    action: str = Field(min_length=2, max_length=40)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=4000)
    data: dict = Field(default_factory=dict)


class ResourceInput(PortalInput):
    kind: Literal["PARKING", "FACILITY", "SERVICE"]
    building_id: UUID
    name: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=4000)
    capacity: int = Field(ge=1, le=100000)
    fee_vnd: int = Field(ge=0, le=9999999999)
    deposit_vnd: int = Field(ge=0, le=9999999999)
    policy: dict


class VehicleInput(PortalInput):
    unit_id: UUID
    resource_id: UUID
    plate: str = Field(min_length=3, max_length=30)
    vehicle_type: str = Field(min_length=2, max_length=30)

    @field_validator("plate")
    @classmethod
    def normalize_plate(cls, value):
        return value.upper().replace(" ", "")


class BookingInput(PortalInput):
    unit_id: UUID
    resource_id: UUID
    starts_at: datetime
    ends_at: datetime
    quantity: int = Field(default=1, ge=1, le=100000)

    @model_validator(mode="after")
    def interval(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Thời gian cần có múi giờ.")
        if self.ends_at <= self.starts_at:
            raise ValueError("Thời gian kết thúc phải sau thời gian bắt đầu.")
        return self


class EnrollmentInput(PortalInput):
    unit_id: UUID
    resource_id: UUID


class DepositAction(PortalInput):
    action: Literal["RECEIVE", "DEDUCT", "RELEASE", "REFUND"]
    expected_version: int = Field(ge=1)
    amount_vnd: int = Field(gt=0, le=9999999999)
    reference: str = Field(min_length=3, max_length=150)
    reason: str = Field(min_length=3, max_length=4000)


class FeePostInput(PortalInput):
    period_id: UUID
    expected_version: int = Field(ge=1)
    calculation_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ContentInput(PortalInput):
    building_id: UUID | None = None
    unit_id: UUID | None = None
    kind: Literal["GUIDE", "NOTICE", "OUTAGE", "MAINTENANCE", "EVENT", "SURVEY", "VOTE", "MEETING"]
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=20000)
    publish_at: datetime
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    document_id: UUID | None = None
    policy: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def interval(self):
        if set(self.policy) - {'options', 'capacity', 'confirmed_rule_reference', 'minutes', 'decisions'}:
            raise ValueError('Chính sách cộng đồng có trường không hỗ trợ.')
        if self.kind in {'SURVEY', 'VOTE'}:
            options = self.policy.get('options')
            if not isinstance(options, list) or not 2 <= len(options) <= 20 or any(not isinstance(o, str) or not 1 <= len(o) <= 200 for o in options) or len(set(options)) != len(options):
                raise ValueError('Cần ít nhất hai lựa chọn khác nhau.')
        if 'capacity' in self.policy and (type(self.policy['capacity']) is not int or not 1 <= self.policy['capacity'] <= 100000):
            raise ValueError('Sức chứa sự kiện phải là số nguyên dương.')
        for key in ('confirmed_rule_reference', 'minutes', 'decisions'):
            if key in self.policy and (not isinstance(self.policy[key], str) or not 3 <= len(self.policy[key]) <= 4000):
                raise ValueError('Nội dung chính sách không hợp lệ.')
        for value in (self.publish_at, self.starts_at, self.ends_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("Thời gian cần có múi giờ.")
        if self.ends_at and (not self.starts_at or self.ends_at <= self.starts_at):
            raise ValueError("Khoảng lịch không hợp lệ.")
        return self


class IntentInput(PortalInput):
    unit_id: UUID
    invoice_id: UUID


class FinancialAdjustmentInput(PortalInput):
    unit_id: UUID
    kind: Literal["CREDIT", "REFUND"]
    invoice_id: UUID
    payment_intent_id: UUID | None = None
    amount_vnd: int = Field(gt=0, le=9999999999)
    reason: str = Field(min_length=3, max_length=4000)


class ResourceClosureInput(PortalInput):
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(min_length=3, max_length=4000)
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def interval(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None or self.ends_at <= self.starts_at:
            raise ValueError("Khoảng đóng cần múi giờ và thời gian kết thúc sau bắt đầu.")
        return self


class RecoveryInput(PortalInput):
    username: str = Field(min_length=1, max_length=100)


class RecoveryVerify(PortalInput):
    reference: str = Field(min_length=10, max_length=300)
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    verified_email: str | None = Field(default=None, max_length=254)

    @field_validator("verified_email")
    @classmethod
    def email(cls, value):
        if value is None:
            return value
        import re
        if not re.fullmatch(r"[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+", value):
            raise ValueError("Địa chỉ email không hợp lệ.")
        from email.utils import parseaddr
        if parseaddr(value) != ('', value):
            raise ValueError("Cần một địa chỉ email hợp lệ, không kèm người nhận khác.")
        return value


class RecoveryComplete(PortalInput):
    request_id: UUID
    token: str = Field(min_length=32, max_length=128, repr=False)
    new_password: str = Field(min_length=12, max_length=128, repr=False)
