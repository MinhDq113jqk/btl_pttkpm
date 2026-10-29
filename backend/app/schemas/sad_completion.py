from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, field_validator, model_validator
from app.schemas.resident_portal import PortalInput, ContentInput


class ContentRevision(PortalInput):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)
    content: ContentInput


class Decision(PortalInput):
    key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=3, max_length=200)
    owner_id: UUID
    due_at: datetime

    @field_validator('due_at')
    @classmethod
    def timezone(cls, v):
        if v.tzinfo is None: raise ValueError('Thời gian cần múi giờ.')
        return v


class Minutes(PortalInput):
    participants: list[str] = Field(min_length=1, max_length=500)
    result_basis: str = Field(min_length=3, max_length=4000)
    decisions: list[Decision] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique(self):
        if len({d.key for d in self.decisions}) != len(self.decisions): raise ValueError('Mã quyết định trùng.')
        return self


class SlaDefinition(PortalInput):
    minutes: int = Field(ge=1, le=525600)
    weekdays: list[int] = Field(min_length=1, max_length=7)
    opens_minute: int = Field(ge=0, le=1439)
    closes_minute: int = Field(ge=1, le=1440)
    pause_reasons: list[str] = Field(max_length=20)
    confirmed_reference: str = Field(min_length=3, max_length=300)
    handoff_minutes: int = Field(ge=1, le=10080)

    @model_validator(mode='after')
    def interval(self):
        if self.opens_minute >= self.closes_minute or any(v not in range(1,8) for v in self.weekdays) or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError('Ca làm/ngày làm không hợp lệ.')
        if any(not 1<=len(reason)<=80 for reason in self.pause_reasons) or len(set(self.pause_reasons))!=len(self.pause_reasons):
            raise ValueError('Điều kiện dừng cần mã khác nhau, tối đa 80 ký tự.')
        return self


class SlaInput(PortalInput):
    building_id: UUID
    category_id: UUID
    definition: SlaDefinition


class DatasetManifest(PortalInput):
    csv_run_ids: list[UUID] = Field(default_factory=list, max_length=100)
    loader_run_ids: list[UUID] = Field(default_factory=list, max_length=100)
    expected_counts: dict[str, int] = Field(min_length=1, max_length=100)
    expected_values: dict[str, int] = Field(default_factory=dict, max_length=20)

    @model_validator(mode='after')
    def required(self):
        if not self.csv_run_ids and not self.loader_run_ids: raise ValueError('Cần batch nguồn.')
        if any(v < 0 for v in self.expected_counts.values()) or any(v < 0 for v in self.expected_values.values()): raise ValueError('Giá trị đối chiếu không âm.')
        if len(set(self.csv_run_ids)) != len(self.csv_run_ids) or len(set(self.loader_run_ids)) != len(self.loader_run_ids): raise ValueError('Batch trùng.')
        return self


class DatasetInput(PortalInput):
    building_id: UUID
    name: str = Field(min_length=3, max_length=200)
    manifest: DatasetManifest
