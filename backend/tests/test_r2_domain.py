from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.r2 import CostLineCreate, ServiceRequestCreate, WorkOrderCreate
from app.services.r2 import (
    ImageEvidenceError,
    calculate_sla_deadline,
    next_maintenance_due,
    validate_image_evidence,
)


def test_absolute_sla_deadline_is_recomputed_from_start_and_duration():
    start = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)
    assert calculate_sla_deadline(start, 240) == start + timedelta(hours=4)


@pytest.mark.parametrize("minutes", [0, -1, 525601])
def test_sla_duration_rejects_non_positive_or_unbounded_values(minutes):
    with pytest.raises(ValueError):
        calculate_sla_deadline(datetime.now(UTC), minutes)


def test_next_maintenance_due_advances_from_the_completed_occurrence():
    due = datetime(2026, 9, 11, 2, 30, tzinfo=UTC)
    assert next_maintenance_due(due, 30) == due + timedelta(days=30)


@pytest.mark.parametrize("days", [0, -3, 3661])
def test_maintenance_interval_has_safe_bounds(days):
    with pytest.raises(ValueError):
        next_maintenance_due(datetime.now(UTC), days)


def test_png_and_jpeg_evidence_are_content_validated():
    png = b"\x89PNG\r\n\x1a\n" + b"synthetic" + b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
    jpeg = b"\xff\xd8\xff\xe0" + b"synthetic" + b"\xff\xd9"
    assert validate_image_evidence(png, "image/png") == "image/png"
    assert validate_image_evidence(jpeg, "image/jpeg") == "image/jpeg"


@pytest.mark.parametrize(
    ("content", "claimed"),
    [
        (b"not an image", "image/png"),
        (b"\x89PNG\r\n\x1a\nbody", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\nincomplete", "image/png"),
        (b"\xff\xd8\xff\xe0missing-end", "image/jpeg"),
        (b"", "image/png"),
    ],
)
def test_image_evidence_rejects_spoofed_or_incomplete_content(content, claimed):
    with pytest.raises(ImageEvidenceError):
        validate_image_evidence(content, claimed)


def test_r2_text_inputs_are_trimmed_before_minimum_length_validation():
    with pytest.raises(ValidationError):
        ServiceRequestCreate(
            category_id="00000000-0000-0000-0000-000000000001",
            building_id="00000000-0000-0000-0000-000000000002",
            title="   ",
            description="valid description",
        )
    with pytest.raises(ValidationError):
        WorkOrderCreate(
            title="valid title",
            description="valid description",
            checklist=[{"label": "   ", "required": True}],
        )


@pytest.mark.parametrize("amount", [True, 1.5, "1000"])
def test_vnd_amount_rejects_bool_float_and_numeric_text(amount):
    with pytest.raises(ValidationError):
        CostLineCreate(description="Part", amount_vnd=amount,
                       cost_bearer="MANAGEMENT")
