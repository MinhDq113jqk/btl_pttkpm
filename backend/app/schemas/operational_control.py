from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.schemas.resident_portal import PortalInput


class MeterInput(PortalInput):
    building_id: UUID
    unit_id: UUID | None = None
    code: str = Field(min_length=2, max_length=80)
    serial: str = Field(min_length=2, max_length=100)
    commodity: Literal['WATER', 'ELECTRICITY']
    multiplier: Decimal = Field(default=Decimal('1'), gt=0, le=100000, max_digits=16, decimal_places=4)
    baseline: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    valid_from: date
    upstream_id: UUID | None = None


class ReadingInput(PortalInput):
    meter_id: UUID
    read_on: date
    value: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    evidence_reference: str = Field(min_length=3, max_length=300)
    anomaly_threshold: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)


class MeterBillingInput(PortalInput):
    expected_version: int = Field(ge=1)
    tariff_version_id: UUID


class StockInput(PortalInput):
    building_id: UUID
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=3, max_length=200)
    uom: str = Field(min_length=1, max_length=30)
    warehouse: str = Field(min_length=1, max_length=80)
    location: str = Field(min_length=1, max_length=80)
    lot: str = Field(min_length=1, max_length=80)
    minimum: Decimal = Field(default=Decimal('0'), ge=0, max_digits=18, decimal_places=4)
    unit_cost_vnd: int = Field(ge=0, le=9999999999)
    expires_on: date | None = None


class StockCommand(PortalInput):
    item_id: UUID
    kind: Literal['RECEIVE', 'RESERVE', 'RELEASE', 'ISSUE', 'RETURN', 'TRANSFER', 'COUNT', 'DAMAGE']
    quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    work_order_id: UUID | None = None
    related_id: UUID | None = None
    destination_id: UUID | None = None
    expected_version: int = Field(ge=1)
    reference: str = Field(min_length=3, max_length=150)
    evidence_reference: str = Field(min_length=3, max_length=300)
    sender_account_id: UUID | None = None
    recipient_account_id: UUID | None = None
    condition: Literal['GOOD', 'DAMAGED'] = 'GOOD'
    input_uom: str | None = Field(default=None, min_length=1, max_length=30)
    conversion_id: UUID | None = None
    delivery_id: UUID | None = None

    @model_validator(mode='after')
    def quantity_for_kind(self):
        if self.kind != 'COUNT' and self.quantity <= 0:
            raise ValueError('Số lượng phải dương; kiểm kê cho phép tồn bằng 0.')
        return self


class TreasuryInput(PortalInput):
    building_id: UUID
    kind: Literal['BUDGET', 'FUND']
    code: str = Field(min_length=3, max_length=80)
    purpose: str = Field(min_length=3, max_length=200)
    starts_on: date
    ends_on: date
    limit_vnd: int = Field(default=0, ge=0, le=999999999999)

    @model_validator(mode='after')
    def interval(self):
        if self.ends_on < self.starts_on:
            raise ValueError('Ngày kết thúc phải từ ngày bắt đầu.')
        return self


class ExpenseInput(PortalInput):
    budget_id: UUID
    fund_id: UUID | None = None
    procurement_id: UUID | None = None
    kind: Literal['EXPENSE', 'ADVANCE', 'AP']
    amount_vnd: int = Field(gt=0, le=999999999999)
    reference: str = Field(min_length=3, max_length=150)
    evidence_reference: str = Field(min_length=3, max_length=300)
    allocation: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode='after')
    def allocated(self):
        if self.allocation and (len(self.allocation) > 50 or any(v <= 0 for v in self.allocation.values()) or sum(self.allocation.values()) != self.amount_vnd):
            raise ValueError('Phân bổ phải bằng tổng đề nghị chi.')
        return self


class RecordInput(PortalInput):
    building_id: UUID
    unit_id: UUID | None = None
    kind: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=3, max_length=200)
    data: dict
    related_id: UUID | None = None


class VendorData(PortalInput):
    code: str = Field(min_length=3, max_length=80)
    tax_code: str = Field(min_length=3, max_length=40)
    capabilities: str = Field(min_length=3, max_length=2000)
    contact: str = Field(min_length=3, max_length=300)


class PurchaseData(PortalInput):
    budget_id: UUID
    specification: str = Field(min_length=3, max_length=4000)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    uom: str = Field(min_length=1, max_length=30)
    estimated_vnd: int = Field(gt=0, le=999999999999)
    item_id: UUID | None = None


class QuotationData(PortalInput):
    vendor_id: UUID
    amount_vnd: int = Field(gt=0, le=999999999999)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    specification: str = Field(min_length=3, max_length=4000)
    evidence_reference: str = Field(min_length=3, max_length=300)


class ContractMilestone(PortalInput):
    code: str = Field(min_length=2, max_length=80)
    due_on: date
    obligation: str = Field(min_length=3, max_length=1000)
    amount_vnd: int = Field(ge=0, le=999999999999)


class ContractData(PortalInput):
    vendor_id: UUID
    reference: str = Field(min_length=3, max_length=150)
    starts_on: date
    ends_on: date
    amount_vnd: int = Field(gt=0, le=999999999999)
    milestones: str = Field(min_length=3, max_length=4000)
    purchase_id: UUID | None = None
    milestone_items: list[ContractMilestone] = Field(min_length=1, max_length=50)
    allows_partial_payment: bool = False
    partial_payment_reference: str | None = Field(default=None, min_length=3, max_length=300)
    @model_validator(mode='after')
    def interval(self):
        if self.ends_on <= self.starts_on:
            raise ValueError('Thời gian hợp đồng không hợp lệ.')
        return self


class DeliveryData(PortalInput):
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    reference: str = Field(min_length=3, max_length=150)
    evidence_reference: str = Field(min_length=3, max_length=300)
    defects: str = Field(default='', max_length=2000)
    accepted_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    rejected_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    missing_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    responsible_account_id: UUID | None = None
    rectifies_delivery_id: UUID | None = None

    @model_validator(mode='after')
    def acceptance(self):
        if self.accepted_quantity is not None and self.accepted_quantity + self.rejected_quantity != self.quantity:
            raise ValueError('Phần đạt và lỗi phải bằng lượng thực giao.')
        return self


class SafetyData(PortalInput):
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=3, max_length=4000)
    evidence_reference: str = Field(min_length=3, max_length=300)
    due_on: date
    corrective_action: str = Field(min_length=3, max_length=4000)


class RuleData(PortalInput):
    code: str = Field(min_length=3, max_length=80)
    revision: int = Field(ge=1)
    valid_from: date
    valid_to: date | None = None
    body: str = Field(min_length=3, max_length=4000)
    confirmed_rule_reference: str = Field(min_length=3, max_length=300)
    @model_validator(mode='after')
    def interval(self):
        if self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError('Khoảng hiệu lực không hợp lệ.')
        return self


class ViolationData(PortalInput):
    rule_id: UUID
    occurred_on: date
    evidence_reference: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=3, max_length=4000)
    subject_account_id: UUID


class VisitorData(PortalInput):
    host_account_id: UUID
    name: str = Field(min_length=3, max_length=200)
    starts_at: datetime
    ends_at: datetime
    purpose: str = Field(min_length=3, max_length=2000)
    authorization_dossier_id: UUID | None = None
    areas: list[str] = Field(min_length=1, max_length=20)
    @model_validator(mode='after')
    def interval(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None or self.ends_at <= self.starts_at:
            raise ValueError('Thời gian khách cần múi giờ và khoảng hợp lệ.')
        return self


class CustodyData(PortalInput):
    reference: str = Field(min_length=3, max_length=150)
    location: str = Field(min_length=2, max_length=200)
    custodian_account_id: UUID
    due_on: date
    condition: str = Field(min_length=3, max_length=2000)
    evidence_reference: str = Field(min_length=3, max_length=300)


class StaffData(PortalInput):
    account_id: UUID
    team: str = Field(min_length=3, max_length=80)
    position: str = Field(min_length=3, max_length=80)
    skills: list[str] = Field(min_length=1, max_length=30)
    certificates: str = Field(default='', max_length=2000)
    certificate_expires_on: date | None = None
    territory: str = Field(min_length=2, max_length=80)
    catalog_ids: list[UUID] = Field(min_length=1, max_length=10)


class RosterData(PortalInput):
    staff_id: UUID
    starts_at: datetime
    ends_at: datetime
    required_skill: str = Field(min_length=1, max_length=80)
    task: str = Field(min_length=3, max_length=2000)
    @model_validator(mode='after')
    def interval(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None or self.ends_at <= self.starts_at:
            raise ValueError('Khoảng ca không hợp lệ.')
        return self


class MeterCycleData(PortalInput):
    starts_on: date
    ends_on: date
    meter_ids: list[UUID] = Field(min_length=1, max_length=500)
    route: str = Field(min_length=3, max_length=4000)
    @model_validator(mode='after')
    def interval(self):
        if self.ends_on < self.starts_on or len(set(self.meter_ids)) != len(self.meter_ids):
            raise ValueError('Kỳ ghi hoặc danh sách đồng hồ không hợp lệ.')
        return self


class AssetData(PortalInput):
    asset_id: UUID
    operation: Literal['PROFILE', 'MOVE', 'RETIRE', 'REPLACE', 'DISPOSE', 'WARRANTY', 'INSPECTION', 'OUTAGE', 'RESTORE', 'LABOR']
    serial: str | None = Field(default=None, min_length=2, max_length=100)
    warranty_until: date | None = None
    inspection_due_on: date | None = None
    location: str = Field(min_length=2, max_length=200)
    target_building_id: UUID | None = None
    replacement_asset_id: UUID | None = None
    due_on: date
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    work_order_id: UUID | None = None
    hours: Decimal = Field(default=Decimal('0'), ge=0, max_digits=12, decimal_places=4)
    cost_vnd: int = Field(default=0, ge=0, le=999999999999)
    evidence_reference: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=3, max_length=4000)


class MeterReplacementData(PortalInput):
    meter_id: UUID
    changed_on: date
    final_value: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    new_code: str = Field(min_length=2, max_length=80)
    new_serial: str = Field(min_length=2, max_length=100)
    new_baseline: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    evidence_reference: str = Field(min_length=3, max_length=300)


class MeterCorrectionData(PortalInput):
    reading_id: UUID
    corrected_value: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    evidence_reference: str = Field(min_length=3, max_length=300)


class BudgetRevisionData(PortalInput):
    budget_id: UUID
    new_limit_vnd: int = Field(gt=0, le=999999999999)
    evidence_reference: str = Field(min_length=3, max_length=300)


class AdvanceSettlementData(PortalInput):
    expense_id: UUID
    actual_vnd: int = Field(ge=0, le=999999999999)
    returned_vnd: int = Field(ge=0, le=999999999999)
    reference: str = Field(min_length=3, max_length=150)
    evidence_reference: str = Field(min_length=3, max_length=300)


class ContractRevisionData(PortalInput):
    contract_id: UUID
    operation: Literal['RENEW', 'AMEND', 'TERMINATE', 'LIQUIDATE']
    reference: str = Field(min_length=3, max_length=150)
    starts_on: date
    ends_on: date
    amount_vnd: int = Field(gt=0, le=999999999999)
    milestones: str = Field(min_length=3, max_length=4000)
    milestone_items: list[ContractMilestone] | None = Field(default=None, min_length=1, max_length=50)
    evidence_reference: str = Field(min_length=3, max_length=300)


class DepositPolicyData(PortalInput):
    code: str = Field(min_length=3, max_length=80)
    purpose: str = Field(min_length=3, max_length=200)
    source_kind: Literal['LEASE', 'RENOVATION', 'BOOKING', 'SERVICE']
    amount_vnd: int = Field(ge=0, le=999999999999)
    conditions: str = Field(min_length=3, max_length=4000)
    valid_from: date
    valid_to: date | None = None


class LeaseDepositData(PortalInput):
    lease_id: UUID
    policy_id: UUID
    evidence_reference: str = Field(min_length=3, max_length=300)


class DataQualityData(SafetyData):
    correction_dossier_id: UUID
