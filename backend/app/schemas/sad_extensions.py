"""Typed contracts for the remaining SAD domains."""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.schemas.resident_portal import PortalInput


class Evidence(PortalInput):
    evidence_reference: str = Field(min_length=3, max_length=300)


class Interval(Evidence):
    starts_on: date
    ends_on: date

    @model_validator(mode='after')
    def interval(self):
        if self.ends_on <= self.starts_on: raise ValueError('Ngày kết thúc phải sau ngày bắt đầu.')
        return self


class InsurancePolicy(Interval):
    insurer: str = Field(min_length=3, max_length=200)
    policy_number: str = Field(min_length=3, max_length=100)
    insured_objects: list[str] = Field(min_length=1, max_length=100)
    coverage: str = Field(min_length=3, max_length=4000)
    exclusions: str = Field(min_length=3, max_length=4000)
    limit_vnd: int = Field(gt=0, le=999999999999)
    deductible_vnd: int = Field(ge=0, le=999999999999)
    contact: str = Field(min_length=3, max_length=300)


class InsuranceClaim(Evidence):
    policy_id: UUID
    incident_id: UUID
    occurred_on: date
    loss_vnd: int = Field(gt=0, le=999999999999)
    description: str = Field(min_length=3, max_length=4000)
    evidence_documents: list[UUID] = Field(default_factory=list, max_length=30)
    handler_account_id: UUID


class InsuranceOutcome(Evidence):
    decision: Literal['ACCEPTED', 'REJECTED', 'PAID']
    provider_reference: str = Field(min_length=3, max_length=150)
    amount_vnd: int = Field(ge=0, le=999999999999)
    decided_on: date


class ProjectItem(PortalInput):
    code: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=3, max_length=1000)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    uom: str = Field(min_length=1, max_length=30)
    due_on: date
    asset_id: UUID | None = None
    planned_vnd: int = Field(ge=0, le=999999999999)


class Project(Interval):
    budget_id: UUID
    owner_account_id: UUID
    objectives: str = Field(min_length=3, max_length=4000)
    scope: str = Field(min_length=3, max_length=4000)
    impact: str = Field(min_length=3, max_length=4000)
    planned_vnd: int = Field(gt=0, le=999999999999)
    items: list[ProjectItem] = Field(min_length=1, max_length=100)
    contract_id: UUID | None = None

    @model_validator(mode='after')
    def plan(self):
        if len({i.code for i in self.items}) != len(self.items): raise ValueError('Mã hạng mục không được trùng.')
        if sum(i.planned_vnd for i in self.items) != self.planned_vnd: raise ValueError('Tổng dự toán hạng mục phải bằng dự toán dự án.')
        if any(not self.starts_on <= i.due_on <= self.ends_on for i in self.items): raise ValueError('Mốc nằm ngoài thời gian dự án.')
        return self


class ProjectChange(Project):
    project_id: UUID
    expected_project_version: int = Field(ge=1)
    change_reason: str = Field(min_length=3, max_length=2000)


class ProjectAcceptance(Evidence):
    project_id: UUID
    item_code: str = Field(min_length=2, max_length=80)
    accepted_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    defective_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    defect_resolution: str = Field(default='', max_length=4000)
    actual_vnd: int = Field(ge=0, le=999999999999)
    performed_on: date


class ProjectProgress(Evidence):
    project_id: UUID
    item_code: str = Field(min_length=2, max_length=80)
    performed_on: date
    actual_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    issues: str = Field(min_length=3, max_length=2000)
    operating_impact: str = Field(min_length=3, max_length=2000)
    notification_reference: str = Field(min_length=3, max_length=300)


class ProjectDefectResolution(Evidence):
    project_id: UUID
    acceptance_id: UUID
    addressed_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    resolution: str = Field(min_length=3, max_length=4000)
    responsible_account_id: UUID


class ProjectHandover(Evidence):
    project_id: UUID
    as_built_document_ids: list[UUID] = Field(min_length=1, max_length=30)
    asset_ids: list[UUID] = Field(min_length=1, max_length=100)
    operating_instructions: str = Field(min_length=3, max_length=4000)
    recipient_account_id: UUID
    warranty_until: date
    warranty_contact: str = Field(min_length=3, max_length=300)


class ProjectSettlement(Evidence):
    project_id: UUID
    expense_ids: list[UUID] = Field(default_factory=list, max_length=100)
    actual_vnd: int = Field(ge=0, le=999999999999)
    explanation: str = Field(min_length=3, max_length=4000)


class CommercialSpace(Evidence):
    property_node_id: UUID
    use_purpose: str = Field(min_length=3, max_length=300)
    area_m2: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    asking_rent_vnd: int = Field(ge=0, le=999999999999)
    operating_conditions: str = Field(min_length=3, max_length=4000)


class CommercialProposal(Interval):
    space_id: UUID
    party_kind: Literal['ORGANIZATION','PERSON']
    party_name: str = Field(min_length=3, max_length=200)
    legal_reference: str = Field(min_length=3, max_length=150)
    contact: str = Field(min_length=3, max_length=300)
    purpose: str = Field(min_length=3, max_length=1000)
    operating_plan: str = Field(min_length=3, max_length=4000)
    rent_vnd: int = Field(gt=0, le=999999999999)
    service_vnd: int = Field(ge=0, le=999999999999)
    deposit_vnd: int = Field(ge=0, le=999999999999)


class CommercialLease(Evidence):
    proposal_id: UUID
    contract_number: str = Field(min_length=3, max_length=100)
    terms: str = Field(min_length=3, max_length=4000)
    rent_cycle: Literal['MONTH','QUARTER','YEAR']
    responsible_account_id: UUID
    handover_condition: str = Field(min_length=3, max_length=2000)


class LeaseAmendment(CommercialProposal):
    lease_id: UUID
    expected_lease_version: int = Field(ge=1)
    operation: Literal['AMEND','RENEW','TERMINATE','REPOSSESS']
    obligations_explanation: str = Field(min_length=3, max_length=4000)
    return_condition: str | None = Field(default=None, min_length=3, max_length=2000)


class CommercialCharge(Evidence):
    lease_id: UUID
    starts_on: date
    ends_on: date
    due_on: date

    @model_validator(mode='after')
    def interval(self):
        if self.ends_on <= self.starts_on: raise ValueError('Khoảng tính phí không hợp lệ.')
        return self


class CommercialMovement(Evidence):
    charge_id: UUID
    amount_vnd: int = Field(gt=0, le=999999999999)
    reference: str = Field(min_length=3, max_length=150)
    operation: Literal['RECEIPT','REFUND','DEDUCTION']
    occurred_on: date


class EnergyTarget(Interval):
    area_id: UUID
    commodity: Literal['ELECTRICITY','WATER']
    uom: Literal['kWh','m3']
    meter_ids: list[UUID] = Field(min_length=1, max_length=100)
    target_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    tolerance_percent: Decimal = Field(ge=0, le=1000, max_digits=8, decimal_places=4)
    definition: str = Field(min_length=3, max_length=1000)
    policy_reference: str = Field(min_length=3, max_length=300)

    @model_validator(mode='after')
    def unit(self):
        if {'ELECTRICITY':'kWh','WATER':'m3'}[self.commodity]!=self.uom: raise ValueError('Đơn vị không khớp đại lượng.')
        if len(set(self.meter_ids))!=len(self.meter_ids): raise ValueError('Đồng hồ không được trùng.')
        return self


class EnergyMeasure(Evidence):
    target_id: UUID
    description: str = Field(min_length=3, max_length=4000)
    owner_account_id: UUID
    due_on: date
    expected_saving: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    cost_vnd: int = Field(ge=0, le=999999999999)


class EnergyReport(Interval):
    target_id: UUID
    explanation: str = Field(min_length=3, max_length=4000)
    verified_cause_reference: str | None = Field(default=None, min_length=3, max_length=300)


class EnergyResult(Interval):
    measure_id: UUID
    baseline_report_id: UUID
    result_report_id: UUID
    conclusion: str = Field(min_length=3, max_length=4000)


class AssistantRequest(PortalInput):
    mode: Literal['SEARCH','STATUS','SUMMARY','DRAFT','HANDOFF']
    query: str = Field(min_length=3, max_length=2000)
    unit_id: UUID | None = None
    request_id: UUID | None = None
    record_source: Literal['portal_dossiers','resident_vehicles','resident_bookings','resident_credentials','resident_service_enrollments','billing_invoices','operations_records'] | None = None
    record_id: UUID | None = None
    content_id: UUID | None = None
    category_id: UUID | None = None
    conversation_id: UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def record_reference(self):
        if bool(self.record_source) != bool(self.record_id): raise ValueError('Chọn đủ loại và hồ sơ nguồn.')
        if self.record_id and self.request_id: raise ValueError('Chỉ chọn một hồ sơ hoặc yêu cầu nguồn.')
        if self.record_id and self.mode!='STATUS': raise ValueError('Hồ sơ nguồn được dùng khi tra cứu trạng thái.')
        return self
