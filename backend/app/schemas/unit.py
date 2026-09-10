from uuid import UUID
from pydantic import BaseModel, ConfigDict


class ResidentInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    person_id: UUID
    full_name: str
    phone_masked: str
    email_masked: str
    relationship_type: str
    is_active: bool


class Unit360Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    unit_number: str
    floor: int
    area_m2: float | None
    status: str | None
    version: int
    building_id: UUID
    building_code: str
    building_name: str
    site_id: UUID
    site_code: str
    site_name: str
    residents: list[ResidentInfo]
    residents_visible: bool = True
