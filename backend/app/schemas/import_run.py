"""HTTP contracts for the durable Unit CSV import flow."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UnitCsvMapping(BaseModel):
    """Map fixed server-owned Unit fields to source CSV headers only."""

    model_config = ConfigDict(extra="forbid")

    unit_number: str = Field(min_length=1, max_length=200)
    floor: str = Field(min_length=1, max_length=200)
    area_m2: str = Field(min_length=1, max_length=200)
    status: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def source_headers_are_distinct(self):
        values = [value.strip() for value in self.model_dump().values()]
        if len(set(values)) != len(values):
            raise ValueError("Mỗi cột nguồn chỉ được map vào một trường Unit.")
        return self


class ImportRunPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    mapping: UnitCsvMapping


class ImportRunApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class ImportRowIssue(BaseModel):
    code: str
    column: str | None = None
    message: str


class ImportRunRowView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    status: Literal["VALIDATED", "WARNING", "ERROR", "IMPORTED", "SKIPPED"]
    issues: list[ImportRowIssue]


class ImportRunRowsResponse(BaseModel):
    items: list[ImportRunRowView]
    page: int
    page_size: int
    total: int


class ImportRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mode: Literal["PARTIAL", "ALL_OR_NOTHING"]
    status: Literal["UPLOADED", "VALIDATING", "PREVIEWED", "APPLYING", "APPLIED", "FAILED"]
    source_filename: str
    source_mime_type: str
    source_size_bytes: int
    source_sha256: str
    source_is_quarantined: bool
    total_rows: int
    valid_rows: int
    warning_rows: int
    error_rows: int
    skipped_rows: int
    applied_rows: int
    error_file_available: bool
    failure_code: str | None
    previewed_at: datetime | None
    applied_at: datetime | None
    failed_at: datetime | None
    version: int


class SignedImportErrorLink(BaseModel):
    url: str
    expires_at: datetime
