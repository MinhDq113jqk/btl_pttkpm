from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictInt


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ResidentArBalanceView(ApiModel):
    unit_id: UUID
    ar_balance_vnd: StrictInt


class ResidentBillingSummaryResponse(BaseModel):
    as_of: datetime
    total_ar_balance_vnd: StrictInt
    items: list[ResidentArBalanceView]


class ResidentBillingInvoiceItemView(ApiModel):
    line_number: int
    description: str
    basis: str
    basis_quantity: float
    unit_rate_vnd_snapshot: StrictInt
    rounding_unit_vnd_snapshot: StrictInt
    amount_vnd: StrictInt


class ResidentBillingInvoiceView(ApiModel):
    id: UUID
    unit_id: UUID
    invoice_number: str
    issued_on: date
    due_on: date | None
    total_vnd: StrictInt
    items: list[ResidentBillingInvoiceItemView]


class ResidentBillingInvoiceListResponse(BaseModel):
    as_of: datetime
    items: list[ResidentBillingInvoiceView]


class ResidentPaymentView(ApiModel):
    id: UUID
    unit_id: UUID
    payment_source: str
    receipt_number: str
    amount_vnd: StrictInt
    received_at: datetime


class ResidentPaymentListResponse(BaseModel):
    as_of: datetime
    items: list[ResidentPaymentView]
