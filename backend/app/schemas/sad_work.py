"""Typed inputs for SAD T01–T08; policy values always come from approved records."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.schemas.resident_portal import PortalInput
from app.schemas.operational_control import RuleData, SafetyData, CustodyData


class CatalogEntry(PortalInput):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=200)
    active: bool = True


class CatalogData(RuleData):
    catalog: Literal['TEAM', 'POSITION', 'TERRITORY', 'SKILL', 'UOM', 'ASSET_CATEGORY', 'WASTE_TYPE']
    entries: list[CatalogEntry] = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def unique_codes(self):
        if len({e.code for e in self.entries}) != len(self.entries):
            raise ValueError('Mã danh mục bị trùng.')
        return self


class OrganizationData(RuleData):
    legal_name: str = Field(min_length=3, max_length=200)
    address: str = Field(min_length=3, max_length=300)
    representative_account_id: UUID
    contact: str = Field(min_length=3, max_length=300)


class BuildingZoneData(PortalInput):
    zone_id: UUID
    evidence_reference: str = Field(min_length=3, max_length=300)


class BuildingProfileData(PortalInput):
    operation: Literal['CREATE', 'UPDATE', 'ACTIVATE', 'DEACTIVATE']
    code: str = Field(min_length=2, max_length=50, pattern=r'^[A-Z0-9][A-Z0-9_-]*$')
    name: str = Field(min_length=2, max_length=200)
    floors_count: int = Field(ge=1, le=300)
    zone_id: UUID
    evidence_reference: str = Field(min_length=3, max_length=300)


class SiteProfileData(PortalInput):
    name: str = Field(min_length=3, max_length=200)
    address: str = Field(min_length=3, max_length=500)
    evidence_reference: str = Field(min_length=3, max_length=300)


class ToolCustodyData(CustodyData):
    source_movement_id: UUID


class BenefitData(PortalInput):
    fee_policy_id: UUID
    unit_ids: list[UUID] = Field(min_length=1, max_length=500)
    valid_from: date
    valid_to: date
    percent: Decimal = Field(gt=0, le=100, max_digits=7, decimal_places=4)
    evidence_reference: str = Field(min_length=3, max_length=300)

    @model_validator(mode='after')
    def interval(self):
        if self.valid_to <= self.valid_from or len(set(self.unit_ids)) != len(self.unit_ids):
            raise ValueError('Hiệu lực/danh sách căn không hợp lệ.')
        return self


class FeePublicationData(PortalInput):
    fee_version_id: UUID
    evidence_reference: str = Field(min_length=3, max_length=300)


class MeterAssignmentInput(PortalInput):
    meter_id: UUID
    unit_id: UUID | None = None
    point: str = Field(min_length=2, max_length=200)
    valid_from: date
    evidence_reference: str = Field(min_length=3, max_length=300)

class MeterDiscrepancyData(PortalInput):
    meter_id: UUID
    starts_on: date
    ends_on: date
    explanation: str = Field(min_length=3, max_length=4000)
    resolution: Literal['READ_AGAIN', 'CORRECTION', 'ACCEPT_EXPLAINED']
    correction_record_id: UUID | None = None
    evidence_reference: str = Field(min_length=3, max_length=300)


class Milestone(PortalInput):
    code: str = Field(min_length=2, max_length=80)
    due_on: date
    obligation: str = Field(min_length=3, max_length=1000)
    amount_vnd: int = Field(ge=0, le=999999999999)


class ContractMilestoneData(PortalInput):
    contract_id: UUID
    milestone_code: str = Field(min_length=2, max_length=80)
    result: str = Field(min_length=3, max_length=2000)
    evidence_reference: str = Field(min_length=3, max_length=300)


class EvaluationCriterion(PortalInput):
    name: str = Field(min_length=2, max_length=100)
    result: str = Field(min_length=2, max_length=1000)
    evidence_reference: str = Field(min_length=3, max_length=300)


class VendorEvaluationData(PortalInput):
    vendor_id: UUID
    contract_id: UUID
    delivery_ids: list[UUID] = Field(min_length=1, max_length=100)
    criteria: list[EvaluationCriterion] = Field(min_length=1, max_length=30)
    conclusion: str = Field(min_length=3, max_length=2000)


class UomConversionData(PortalInput):
    item_id: UUID
    from_uom: str = Field(min_length=1, max_length=30)
    factor: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    valid_from: date
    valid_to: date | None = None
    evidence_reference: str = Field(min_length=3, max_length=300)


class WasteData(SafetyData):
    waste_type: str = Field(min_length=2, max_length=80)
    quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    uom: str | None = Field(default=None, min_length=1, max_length=30)
    collection_point: str = Field(min_length=2, max_length=200)
    receiving_party: str = Field(min_length=3, max_length=200)
    handover_reference: str = Field(min_length=3, max_length=300)

    @model_validator(mode='after')
    def measured(self):
        if (self.quantity is None) != (self.uom is None):
            raise ValueError('Lượng đo cần đơn vị; chưa đo giữ trống cả hai.')
        return self


class EnvironmentWorkData(SafetyData):
    areas: list[str] = Field(min_length=1, max_length=50)
    starts_at: datetime
    ends_at: datetime
    access_conditions: str = Field(min_length=3, max_length=1000)
    owner_account_id: UUID
    notification_reference: str = Field(min_length=3, max_length=300)

    @model_validator(mode='after')
    def interval(self):
        if not self.starts_at.tzinfo or not self.ends_at.tzinfo or self.ends_at <= self.starts_at:
            raise ValueError('Khoảng thực hiện cần múi giờ hợp lệ.')
        return self


class EnvironmentIncidentData(SafetyData):
    areas: list[str] = Field(min_length=1, max_length=50)
    hazardous: bool
    security_incident_id: UUID | None = None
    owner_account_id: UUID
    notification_reference: str = Field(min_length=3, max_length=300)


class RiskData(SafetyData):
    severity: str = Field(min_length=2, max_length=80)
    likelihood: str = Field(min_length=2, max_length=80)
    policy_reference: str = Field(min_length=3, max_length=300)
    owner_account_id: UUID
    remediation_plan: str = Field(min_length=3, max_length=4000)


class Finding(PortalInput):
    description: str = Field(min_length=3, max_length=2000)
    owner_account_id: UUID
    due_on: date


class InspectionData(SafetyData):
    plan_id: UUID | None = None
    findings: list[Finding] = Field(default_factory=list, max_length=50)
    performed_at: datetime


class EmergencyContact(PortalInput):
    name: str = Field(min_length=2, max_length=200)
    responsibility: str = Field(min_length=3, max_length=300)
    contact: str = Field(min_length=3, max_length=200)


class EmergencyPlanData(RuleData):
    contacts: list[EmergencyContact] = Field(min_length=1, max_length=30)
    evacuation_routes: list[str] = Field(min_length=1, max_length=50)
    assembly_point: str = Field(min_length=2, max_length=200)


class TrainingData(PortalInput):
    sop_id: UUID
    staff_ids: list[UUID] = Field(min_length=1, max_length=200)
    scheduled_at: datetime
    evidence_reference: str = Field(min_length=3, max_length=300)


class AssignmentData(PortalInput):
    target_type: Literal['WORK_ORDER', 'CLEANING', 'SECURITY']
    target_id: UUID
    roster_id: UUID
    required_skill: str = Field(min_length=1, max_length=80)
    sop_id: UUID | None = None
    evidence_reference: str = Field(min_length=3, max_length=300)


class BudgetVarianceData(PortalInput):
    budget_id: UUID
    explanation: str = Field(min_length=3, max_length=4000)
    evidence_reference: str = Field(min_length=3, max_length=300)


class AssetWorkLinkData(PortalInput):
    asset_id: UUID
    work_order_id: UUID
    warranty_decision: Literal['PROVIDER', 'MANAGEMENT', 'NOT_APPLICABLE']
    inspection_reference: str = Field(min_length=3, max_length=300)
    evidence_reference: str = Field(min_length=3, max_length=300)
