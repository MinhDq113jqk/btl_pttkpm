from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import Field, ValidationError, model_validator
from app.core.exceptions import AppError
from app.schemas.resident_portal import PortalInput


class LeaseData(PortalInput):
    target_person_id: UUID | None = None
    lease_id: UUID | None = None
    contract_reference: str = Field(min_length=3,max_length=150)
    terms: dict = Field(default_factory=dict)


class LeaseEndData(PortalInput):
    lease_id: UUID
    evidence_reference: str = Field(min_length=3,max_length=300)


class LiabilityData(PortalInput):
    liable_person_id: UUID
    evidence_reference: str = Field(min_length=3,max_length=300)


class UnitProfileData(PortalInput):
    area_m2: Decimal | None = Field(default=None,gt=0,le=9999999999,decimal_places=2)
    net_area_m2: Decimal | None = Field(default=None,gt=0,le=9999999999,decimal_places=2)
    gross_area_m2: Decimal | None = Field(default=None,gt=0,le=9999999999,decimal_places=2)
    use_purpose: str | None = Field(default=None,min_length=3,max_length=150)
    operating_status: Literal['ACTIVE','SUSPENDED','INACTIVE','HANDED_OVER','occupied','vacant'] | None = None
    evidence_reference: str = Field(min_length=3,max_length=300)

    @model_validator(mode='after')
    def changed(self):
        if not any(getattr(self,k) is not None for k in ['area_m2','net_area_m2','gross_area_m2','use_purpose','operating_status']):
            raise ValueError('Cần ít nhất một trường thay đổi.')
        return self


class HandoverData(PortalInput):
    reference: str = Field(min_length=3,max_length=150)
    checklist: list[str] = Field(min_length=1,max_length=100)
    accepted_items: list[str] = Field(min_length=1,max_length=100)
    defects: list[str] = Field(default_factory=list,max_length=100)
    evidence_reference: str = Field(min_length=3,max_length=300)

    @model_validator(mode='after')
    def accepted(self):
        if not set(self.checklist) <= set(self.accepted_items):
            raise ValueError('Chưa đủ các điều kiện bàn giao được khai báo.')
        return self


class MergeData(PortalInput):
    source_person_id: UUID
    target_person_id: UUID
    evidence_reference: str = Field(min_length=10,max_length=300)


class NodeInput(PortalInput):
    building_id: UUID | None = None
    parent_id: UUID | None = None
    kind: Literal['ZONE','FLOOR','COMMON_AREA','COMMERCIAL_SPACE']
    code: str = Field(min_length=2,max_length=50,pattern=r'^[A-Z0-9][A-Z0-9._-]*$')
    name: str = Field(min_length=3,max_length=200)
    data: dict = Field(default_factory=dict)


def validate_property_data(kind, data):
    schema = {'LEASE':LeaseData,'LEASE_RENEW':LeaseData,'LEASE_AMEND':LeaseData,'LEASE_TERMINATE':LeaseEndData,
        'LIABILITY_CHANGE':LiabilityData,'UNIT_PROFILE':UnitProfileData,'UNIT_STATUS':UnitProfileData,
        'HANDOVER':HandoverData,'PERSON_MERGE':MergeData}[kind]
    try:
        result = schema.model_validate(data).model_dump(mode='json',exclude_none=True)
    except ValidationError:
        raise AppError('ERR-PROPERTY-DATA','Thông tin hồ sơ bất động sản chưa đúng hoặc thiếu trường bắt buộc.',422) from None
    if kind == 'LEASE' and not result.get('target_person_id'):
        raise AppError('ERR-PROPERTY-DATA','Hợp đồng cần chỉ rõ bên thuê.',422)
    if kind in {'LEASE_RENEW','LEASE_AMEND'} and not result.get('lease_id'):
        raise AppError('ERR-PROPERTY-DATA','Gia hạn/phụ lục cần hợp đồng gốc.',422)
    return result
