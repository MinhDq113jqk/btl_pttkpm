from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResidentInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    person_id: UUID
    full_name: str
    phone_masked: str
    email_masked: str
    relationship_type: str
    is_active: bool
    ownership_ratio: Decimal | None
    valid_from: date
    valid_to: date | None


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


class UnitImportItem(BaseModel):
    """Raw mapped values are validated per row by the import service.

    Keeping the values as ``Any`` lets a 1,000-row batch report each invalid
    row instead of FastAPI rejecting the entire request before the service can
    identify its line and column.  Extra columns are still rejected at the
    request boundary so callers cannot smuggle scope or identity fields.
    """

    model_config = ConfigDict(extra="forbid")

    unit_number: Any = None
    floor: Any = None
    area_m2: Any = None
    status: Any = None


class UnitImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    building_code: str = Field(min_length=1, max_length=50)
    mode: Literal["partial", "all_or_nothing"]
    items: list[UnitImportItem] = Field(min_length=1, max_length=1000)


class UnitImportItemResult(BaseModel):
    row_number: int
    status: Literal["IMPORTED", "VALIDATED", "SKIPPED", "ERROR"]
    code: str
    column: str | None = None
    message: str | None = None


class UnitImportResponse(BaseModel):
    receipt_id: UUID
    status: Literal["APPLIED", "REJECTED"]
    mode: Literal["partial", "all_or_nothing"]
    total_rows: int
    applied_rows: int
    skipped_rows: int
    warning_rows: int
    error_rows: int
    items: list[UnitImportItemResult]
