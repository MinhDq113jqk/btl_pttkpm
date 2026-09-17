"""R5 AC-22/NFR-05 tests against the disposable PostgreSQL cluster."""
from datetime import UTC, datetime
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.policy import context_for_account
from app.models.enums import RoleEnum
from app.models.platform import AuditEvent, DomainEvent, NotificationReadModel
from app.models.service import ServiceRequest
from app.services.outbox import ChannelDeliveryError, OutboxDispatcher, enqueue_notification
from app.services.r2 import audit
from test_r2_integration import insert_request, r2_case


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R5 outbox tests require its disposable PostgreSQL cluster",
)]


class ScriptedChannel:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def deliver(self, message, *, idempotency_key: str) -> None:
        self.calls.append((message.id, idempotency_key, message.correlation_id))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome


def _request(correlation_id: UUID):
    return SimpleNamespace(state=SimpleNamespace(correlation_id=str(correlation_id)))


def _enqueue_source_notification(case, suffix: str):
    correlation_id = uuid4()
    with case["database"].get_session() as session:
        context = context_for_account(session, case["accounts"]["cskh"], case["sites"][0].id)
        source = insert_request(
            session,
            tenant=case["tenant"],
            site=case["sites"][0],
            building=case["buildings"][0],
            unit=case["units"][0],
            category=case["categories"][0],
            actor=case["accounts"]["cskh"],
            suffix=f"R5-{suffix}",
        )
        request = _request(correlation_id)
        audit(
            session,
            context,
            request,
            event_type="ServiceRequestCreated",
            action="create",
            resource_type="ServiceRequest",
            resource_id=source.id,
            building_id=source.building_id,
            after={"status": source.status},
        )
        event = enqueue_notification(
            session,
            context,
            request,
            event_type="NotificationRequested",
            resource_type="ServiceRequest",
            resource_id=source.id,
            recipient_account_id=case["accounts"]["director"].id,
            template_code="SERVICE_REQUEST_CREATED",
            template_snapshot={"title": "New service request", "source_code": source.code},
        )
        session.commit()
        return source.id, event.id, correlation_id


def _event(session, event_id):
    return session.scalar(select(DomainEvent).where(DomainEvent.id == event_id))


def test_ac22_channel_failure_keeps_source_and_retries_idempotently(r2_case):
    source_id, event_id, correlation_id = _enqueue_source_notification(r2_case, "retry")
    channel = ScriptedChannel([ChannelDeliveryError("CHANNEL_TIMEOUT"), None])
    dispatcher = OutboxDispatcher(r2_case["database"].get_session, channel, max_attempts=2)
    first = dispatcher.dispatch_once(now=datetime.now(UTC), event_id=event_id)
    assert first.event_id == event_id and first.status == "RETRY_SCHEDULED"

    with r2_case["database"].get_session() as session:
        source = session.get(ServiceRequest, source_id)
        event = _event(session, event_id)
        source_audit = session.scalar(select(AuditEvent).where(
            AuditEvent.resource_id == source_id,
            AuditEvent.correlation_id == correlation_id,
        ))
        notification = session.scalar(select(NotificationReadModel).where(
            NotificationReadModel.domain_event_id == event_id,
        ))
        assert source is not None  # Channel failure did not roll back its source transaction.
        assert event.correlation_id == correlation_id and source_audit is not None
        assert event.attempt_count == 1 and event.last_error == "CHANNEL_TIMEOUT"
        assert notification.delivery_status == "RETRY_SCHEDULED"
        retry_at = event.next_attempt_at

    second = dispatcher.dispatch_once(now=retry_at, event_id=event_id)
    assert second.event_id == event_id and second.status == "PUBLISHED"
    assert dispatcher.dispatch_once(now=retry_at, event_id=event_id).event_id is None
    assert channel.calls == [(event_id, str(event_id), correlation_id), (event_id, str(event_id), correlation_id)]

    audit_response = r2_case["client"].get(
        "/api/v1/audit-events",
        params={"correlation_id": str(correlation_id)},
        headers=r2_case["auth"]["director"],
    )
    assert audit_response.status_code == 200, audit_response.text
    assert any(item["resource_id"] == str(source_id) for item in audit_response.json()["items"])
    assert r2_case["client"].get(
        "/api/v1/audit-events",
        headers=r2_case["auth"]["cskh"],
    ).status_code == 403

    inbox = r2_case["client"].get("/api/v1/notifications", headers=r2_case["auth"]["director"])
    assert inbox.status_code == 200, inbox.text
    item = next(item for item in inbox.json()["items"] if item["domain_event_id"] == str(event_id))
    assert item["delivery_status"] == "PUBLISHED" and item["last_error"] is None
    read = r2_case["client"].post(
        f"/api/v1/notifications/{item['id']}/read",
        headers=r2_case["auth"]["director"],
    )
    assert read.status_code == 200 and read.json()["read_at"] is not None
    assert r2_case["client"].get(
        "/api/v1/notifications", headers=r2_case["auth"]["director"],
    ).json()["items"] == []


def test_dead_letter_manual_retry_and_backend_audit_roster(r2_case):
    _, event_id, correlation_id = _enqueue_source_notification(r2_case, "dead-letter")
    dispatcher = OutboxDispatcher(
        r2_case["database"].get_session,
        ScriptedChannel([ChannelDeliveryError(), ChannelDeliveryError(), None]),
        max_attempts=2,
    )
    assert dispatcher.dispatch_once(now=datetime.now(UTC), event_id=event_id).status == "RETRY_SCHEDULED"
    with r2_case["database"].get_session() as session:
        retry_at = _event(session, event_id).next_attempt_at
    assert dispatcher.dispatch_once(now=retry_at, event_id=event_id).status == "DEAD_LETTER"

    outbox = r2_case["client"].get(
        "/api/v1/outbox/events",
        params={"delivery_status": "DEAD_LETTER"},
        headers=r2_case["auth"]["director"],
    )
    assert outbox.status_code == 200
    assert any(item["id"] == str(event_id) for item in outbox.json()["items"])
    assert r2_case["client"].get(
        "/api/v1/outbox/events", headers=r2_case["auth"]["cskh"],
    ).status_code == 403

    retry_path = f"/api/v1/outbox/events/{event_id}/retry"
    reset = r2_case["client"].post(retry_path, headers=r2_case["auth"]["director"])
    assert reset.status_code == 200 and reset.json()["delivery_status"] == "PENDING"
    replay = r2_case["client"].post(retry_path, headers=r2_case["auth"]["director"])
    assert replay.status_code == 200 and replay.json()["attempt_count"] == 0
    with r2_case["database"].get_session() as session:
        reset_at = _event(session, event_id).next_attempt_at
    assert dispatcher.dispatch_once(now=reset_at, event_id=event_id).status == "PUBLISHED"

    # The current eight-role backend roster intentionally has no real auditor.
    assert "auditor" not in {role.value for role in RoleEnum}
    accountant_audit = r2_case["client"].get(
        "/api/v1/audit-events",
        params={"correlation_id": str(correlation_id)},
        headers=r2_case["auth"]["accountant"],
    )
    assert accountant_audit.status_code == 200
    assert accountant_audit.json()["items"] == []
