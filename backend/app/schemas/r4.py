from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InputModel(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def strip_text_inputs(cls, value):
        return value.strip() if isinstance(value, str) else value


class BillingPaymentCreate(InputModel):
    billing_account_id: UUID | None = None
    building_id: UUID | None = None
    accounting_period_id: UUID
    payment_source: Literal["CASH", "BANK_TRANSFER", "GATEWAY"]
    source_reference: str = Field(min_length=1, max_length=120)
    receipt_number: str = Field(min_length=1, max_length=80)
    amount_vnd: StrictInt = Field(gt=0)
    received_at: datetime

    @model_validator(mode="after")
    def require_known_account_or_scoped_unmatched_building(self):
        if (self.billing_account_id is None) == (self.building_id is None):
            raise ValueError("Provide exactly one of billing_account_id or building_id")
        return self

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value


class BillingAccountView(ApiModel):
    id: UUID
    tenant_id: UUID
    site_id: UUID
    building_id: UUID
    unit_id: UUID
    account_number: str
    status: Literal["ACTIVE", "SUSPENDED", "CLOSED"]
    opened_on: date
    closed_on: date | None
    version: int


class BillingAccountListResponse(BaseModel):
    items: list[BillingAccountView]


class BillingPaymentView(ApiModel):
    id: UUID
    billing_account_id: UUID | None
    accounting_period_id: UUID
    building_id: UUID
    payment_source: Literal["CASH", "BANK_TRANSFER", "GATEWAY"]
    source_reference: str
    receipt_number: str
    amount_vnd: StrictInt
    received_at: datetime
    status: Literal[
        "RECEIVED", "ALLOCATING", "PARTIALLY_ALLOCATED", "ALLOCATED",
        "UNMATCHED", "OVERPAID", "REVERSED",
    ]
    created_at: datetime
    version: int


class BillingPaymentListResponse(BaseModel):
    items: list[BillingPaymentView]


class PaymentAllocationView(ApiModel):
    id: UUID
    payment_id: UUID
    billing_invoice_id: UUID
    amount_vnd: StrictInt
    created_at: datetime


class OverpaymentCreditView(ApiModel):
    id: UUID
    billing_account_id: UUID
    payment_id: UUID
    original_vnd: StrictInt
    remaining_vnd: StrictInt
    status: Literal["OPEN", "EXHAUSTED", "VOID"]
    created_at: datetime
    version: int


class OverpaymentCreditListResponse(BaseModel):
    items: list[OverpaymentCreditView]


class PaymentAllocationResult(BaseModel):
    payment: BillingPaymentView
    allocations: list[PaymentAllocationView]
    overpayment_credit: OverpaymentCreditView | None


class UnmatchedPaymentView(ApiModel):
    id: UUID
    payment_id: UUID
    building_id: UUID
    amount_vnd: StrictInt
    reason: str
    status: Literal["OPEN", "RESOLVED", "REFUNDED"]
    source_reference: str
    receipt_number: str
    received_at: datetime
    created_at: datetime
    version: int


class UnmatchedPaymentListResponse(BaseModel):
    items: list[UnmatchedPaymentView]


class UnmatchedPaymentMatch(InputModel):
    billing_account_id: UUID


class FeePolicyCreate(InputModel):
    building_id: UUID
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    name: str = Field(min_length=2, max_length=200)
    effective_from: date
    unit_rate_vnd: StrictInt = Field(ge=0)
    rounding_unit_vnd: StrictInt = Field(default=1, ge=1)


class FeePolicyVersionCreate(InputModel):
    effective_from: date
    unit_rate_vnd: StrictInt = Field(ge=0)
    rounding_unit_vnd: StrictInt = Field(default=1, ge=1)


class FeePolicyVersionView(ApiModel):
    id: UUID
    fee_policy_id: UUID
    version_number: int
    effective_from: date
    effective_to: date | None
    unit_rate_vnd: StrictInt
    basis: Literal["UNIT_AREA_M2"]
    rounding_unit_vnd: StrictInt
    published_at: datetime | None


class FeePolicyView(ApiModel):
    id: UUID
    building_id: UUID
    code: str
    name: str
    is_active: bool
    versions: list[FeePolicyVersionView]


class FeePolicyListResponse(BaseModel):
    items: list[FeePolicyView]


class AccountingPeriodCreate(InputModel):
    building_id: UUID
    period_key: str = Field(min_length=4, max_length=20, pattern=r"^[0-9]{4}-[0-9]{2}$")
    period_start: date
    period_end: date
    cutoff_at: datetime

    @field_validator("cutoff_at")
    @classmethod
    def require_cutoff_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("cutoff_at must include a timezone")
        return value


class AccountingPeriodTransition(InputModel):
    expected_version: StrictInt = Field(ge=1)
    status: Literal["OPEN", "CLOSING", "CLOSED", "LOCKED"]


class AccountingPeriodView(ApiModel):
    id: UUID
    building_id: UUID
    period_key: str
    period_start: date
    period_end: date
    cutoff_at: datetime
    status: Literal["OPEN", "CLOSING", "CLOSED", "LOCKED"]
    version: int


class AccountingPeriodListResponse(BaseModel):
    items: list[AccountingPeriodView]


class BillingRunCreate(InputModel):
    accounting_period_id: UUID
    fee_policy_version_id: UUID
    run_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class BillingRunView(ApiModel):
    id: UUID
    accounting_period_id: UUID
    fee_policy_version_id: UUID
    building_id: UUID
    run_key: str
    status: Literal["DRAFT", "CALCULATING", "REVIEW", "POSTED", "FAILED", "CANCELLED"]
    cutoff_at: datetime
    retry_count: int
    failure_code: str | None
    failure_detail: str | None
    failed_at: datetime | None
    completed_at: datetime | None
    version: int


class BillingRunListResponse(BaseModel):
    items: list[BillingRunView]


class BillingInvoiceItemView(ApiModel):
    id: UUID
    line_number: int
    description: str
    basis: str
    basis_quantity: float
    unit_rate_vnd_snapshot: StrictInt
    rounding_unit_vnd_snapshot: StrictInt
    amount_vnd: StrictInt
    source_pending_charge_id: UUID | None


class BillingInvoiceView(ApiModel):
    id: UUID
    billing_account_id: UUID
    billing_run_id: UUID
    accounting_period_id: UUID
    building_id: UUID
    invoice_number: str
    issued_on: date | None
    due_on: date | None
    status: Literal["DRAFT", "ISSUED", "PARTIALLY_PAID", "PAID", "VOID"]
    total_vnd: StrictInt
    outstanding_vnd: StrictInt
    voided_at: datetime | None
    void_reason: str | None
    version: int
    items: list[BillingInvoiceItemView] = []


class BillingInvoiceListResponse(BaseModel):
    items: list[BillingInvoiceView]


class BillingInvoiceVoid(InputModel):
    expected_version: StrictInt = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)
