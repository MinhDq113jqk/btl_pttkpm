from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, StrictInt, model_validator
from app.schemas.resident_portal import PortalInput

CommandKind = Literal['DEPOSIT_DEDUCT','DEPOSIT_RELEASE','DEPOSIT_REFUND','CREDIT','WRITE_OFF',
    'PAYMENT_REVERSE','PAYMENT_REFUND','ALLOCATE','CREDIT_USE','PERIOD_LOCK','PERIOD_REOPEN',
    'ACCOUNT_OPEN','ACCOUNT_SUSPEND','ACCOUNT_RESUME','ACCOUNT_CLOSE','INVOICE_VOID']


class AllocationLine(PortalInput):
    invoice_id: UUID
    amount_vnd: StrictInt = Field(gt=0, le=9999999999)


class CommandData(PortalInput):
    allocations: list[AllocationLine] = Field(default_factory=list, max_length=100)
    expires_at: datetime | None = None
    allowed_kinds: list[Literal['CREDIT','WRITE_OFF','PAYMENT_REVERSE','PAYMENT_REFUND','INVOICE_VOID']] = Field(default_factory=list)
    target_ids: list[UUID] = Field(default_factory=list, max_length=100)
    effective_on: date | None = None
    account_number: str | None = Field(default=None,min_length=2,max_length=80)
    execution_reference: str | None = Field(default=None,min_length=3,max_length=150)

    @model_validator(mode='after')
    def distinct(self):
        if len({r.invoice_id for r in self.allocations}) != len(self.allocations):
            raise ValueError('Không lặp hóa đơn trong phân bổ.')
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError('Thời hạn cần múi giờ.')
        return self


class CommandInput(PortalInput):
    expected_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    kind: CommandKind
    period_id: UUID
    target_id: UUID
    amount_vnd: StrictInt = Field(default=0,ge=0,le=9999999999)
    reason: str = Field(min_length=3,max_length=4000)
    evidence_reference: str = Field(min_length=3,max_length=300)
    data: CommandData = Field(default_factory=CommandData)

    @model_validator(mode='after')
    def complete(self):
        if self.kind in {'ALLOCATE','CREDIT_USE'} and not self.data.allocations:
            raise ValueError('Cần phân bổ cụ thể.')
        if self.kind == 'PERIOD_REOPEN' and (not self.data.expires_at or not self.data.allowed_kinds or not self.data.target_ids):
            raise ValueError('Mở kỳ cần phạm vi chứng từ, nghiệp vụ và thời hạn.')
        if self.kind.startswith('ACCOUNT_') and not self.data.effective_on:
            raise ValueError('Cần ngày hiệu lực tài khoản.')
        if self.kind == 'ACCOUNT_OPEN' and not self.data.account_number:
            raise ValueError('Cần số tài khoản thu phí.')
        monetary = {'DEPOSIT_DEDUCT','DEPOSIT_RELEASE','DEPOSIT_REFUND','CREDIT','WRITE_OFF','PAYMENT_REFUND'}
        if self.kind in monetary and self.amount_vnd <= 0:
            raise ValueError('Số tiền phải lớn hơn không.')
        return self


class ArInput(PortalInput):
    invoice_id: UUID
    invoice_item_id: UUID | None = None
    kind: Literal['DISPUTE','REMINDER','PROMISE']
    amount_vnd: StrictInt = Field(gt=0,le=9999999999)
    due_on: date | None = None
    reason: str = Field(min_length=3,max_length=4000)
    # An explicit choice is mandatory for reminders affecting disputed debt.
    include_disputed: bool | None = None


class PolicyInput(PortalInput):
    code: CommandKind | Literal['BILLING']
    purpose: str = Field(min_length=3,max_length=300)
    approval_roles: list[Literal['admin','director','accountant']] = Field(min_length=1)
    max_amount_vnd: StrictInt = Field(gt=0,le=999999999999)


class DelegationInput(PortalInput):
    delegate_account_id: UUID
    building_id: UUID
    purpose: CommandKind | Literal['BILLING']
    valid_from: datetime
    valid_to: datetime
    reason: str = Field(min_length=3,max_length=300)

    @model_validator(mode='after')
    def interval(self):
        if self.valid_from.tzinfo is None or self.valid_to.tzinfo is None or self.valid_to <= self.valid_from:
            raise ValueError('Khoảng ủy nhiệm cần múi giờ và ngày kết thúc sau ngày bắt đầu.')
        return self
