from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PersonUnitRelationshipView(BaseModel):
    unit_id: UUID
    unit_number: str
    building_id: UUID
    building_code: str
    site_id: UUID
    site_code: str
    relationship_type: str
    ownership_ratio: Decimal | None
    valid_from: date
    valid_to: date | None


class PersonUnitsResponse(BaseModel):
    person_id: UUID
    full_name: str
    phone_masked: str
    email_masked: str
    as_of: date
    items: list[PersonUnitRelationshipView]
