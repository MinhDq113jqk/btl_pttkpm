"""Offline response contracts consumed by the FE-21..FE-30 review."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.r5 import NotificationView


def test_notification_response_preserves_acknowledgement_separately_from_read():
    when = datetime(2026, 10, 11, tzinfo=timezone.utc)
    row = SimpleNamespace(id=uuid4(), domain_event_id=uuid4(), template_code="MANDATORY",
                          template_snapshot={"requires_ack": True}, delivery_status="PUBLISHED",
                          delivered_at=when, read_at=when, last_error=None, created_at=when,
                          acknowledged_at=None)
    assert NotificationView.model_validate(row).acknowledged_at is None
    row.acknowledged_at = when
    payload = NotificationView.model_validate(row).model_dump(mode="json")
    assert payload["acknowledged_at"] == payload["read_at"]


def test_old_notification_payload_defaults_to_unacknowledged():
    when = datetime(2026, 10, 11, tzinfo=timezone.utc)
    payload = dict(id=uuid4(), domain_event_id=uuid4(), template_code="UPDATE",
                   template_snapshot={}, delivery_status="PENDING", delivered_at=None,
                   read_at=None, last_error=None, created_at=when)
    assert NotificationView.model_validate(payload).acknowledged_at is None
