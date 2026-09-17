"""Transactional-outbox dispatching for notification and future event channels.

The business transaction only creates DomainEvent and, when relevant, its inbox
projection.  A worker invokes this module later, so a channel outage cannot
roll back an already-committed business change.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.policy import UserContext, scope_not_found
from app.models.account import Account
from app.models.platform import DomainEvent, NotificationReadModel


PENDING_DELIVERY_STATES = frozenset({"PENDING", "RETRY_SCHEDULED"})
MAX_DELIVERY_ATTEMPTS = 3
DELIVERY_LEASE_SECONDS = 30


@dataclass(frozen=True)
class OutboxMessage:
    id: UUID
    tenant_id: UUID
    site_id: UUID
    actor_account_id: UUID | None
    event_type: str
    resource_type: str
    resource_id: UUID
    correlation_id: UUID
    payload: dict


class NotificationChannel(Protocol):
    def deliver(self, message: OutboxMessage, *, idempotency_key: str) -> None: ...


class ChannelDeliveryError(Exception):
    """A safe, stable code returned by an unavailable notification channel."""

    def __init__(self, code: str = "CHANNEL_UNAVAILABLE"):
        self.code = code[:80] or "CHANNEL_UNAVAILABLE"
        super().__init__(self.code)


@dataclass(frozen=True)
class DispatchResult:
    event_id: UUID | None
    status: str | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _correlation_id(request: Request) -> UUID:
    try:
        return UUID(str(getattr(request.state, "correlation_id", None)))
    except (TypeError, ValueError):
        return uuid4()


def enqueue_notification(
    session: Session,
    context: UserContext,
    request: Request,
    *,
    event_type: str,
    resource_type: str,
    resource_id: UUID,
    recipient_account_id: UUID,
    template_code: str,
    template_snapshot: dict,
) -> DomainEvent:
    """Write the event and recipient/template snapshot in the caller's transaction."""
    if not template_code or len(template_code) > 80:
        raise ValueError("template_code must be 1-80 characters")
    if not isinstance(template_snapshot, dict):
        raise ValueError("template_snapshot must be an object")
    site_id = context.assert_active_site()
    recipient = session.scalar(select(Account.id).where(
        Account.id == recipient_account_id,
        Account.tenant_id == context.tenant_id,
        Account.is_active.is_(True),
    ))
    if recipient is None:
        raise scope_not_found()
    payload = {
        "notification": {
            "recipient_account_id": str(recipient_account_id),
            "template_code": template_code,
            "template_snapshot": template_snapshot,
        },
    }
    event = DomainEvent(
        tenant_id=context.tenant_id,
        site_id=site_id,
        actor_account_id=context.account_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=_correlation_id(request),
        payload=payload,
    )
    session.add(event)
    session.flush()
    session.add(NotificationReadModel(
        tenant_id=context.tenant_id,
        site_id=site_id,
        recipient_account_id=recipient_account_id,
        domain_event_id=event.id,
        template_code=template_code,
        template_snapshot=template_snapshot,
    ))
    return event


class OutboxDispatcher:
    """Claims one event at a time with a lease and delivers it outside a DB lock."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        channel: NotificationChannel,
        *,
        max_attempts: int = MAX_DELIVERY_ATTEMPTS,
        lease_seconds: int = DELIVERY_LEASE_SECONDS,
    ):
        if max_attempts < 1 or lease_seconds < 1:
            raise ValueError("max_attempts and lease_seconds must be positive")
        self._session_factory = session_factory
        self._channel = channel
        self._max_attempts = max_attempts
        self._lease_seconds = lease_seconds

    def dispatch_once(self, *, now: datetime | None = None, event_id: UUID | None = None) -> DispatchResult:
        now = now or _utc_now()
        claim = self._claim_due_event(now, event_id=event_id)
        if claim is None:
            return DispatchResult(event_id=None, status=None)
        event_id, lock_id, message = claim
        try:
            self._channel.deliver(message, idempotency_key=str(event_id))
        except ChannelDeliveryError as exc:
            return self._record_failure(event_id, lock_id, now, exc.code)
        except Exception:
            # Channel exception text may carry provider tokens or PII; persist a
            # stable diagnostic code only.
            return self._record_failure(event_id, lock_id, now, "CHANNEL_UNAVAILABLE")
        return self._record_success(event_id, lock_id, now)

    def _claim_due_event(self, now: datetime, *, event_id: UUID | None) -> tuple[UUID, UUID, OutboxMessage] | None:
        session = self._session_factory()
        try:
            conditions = [or_(
                DomainEvent.delivery_status.in_(PENDING_DELIVERY_STATES),
                DomainEvent.delivery_status == "PROCESSING",
            ), or_(
                (DomainEvent.delivery_status.in_(PENDING_DELIVERY_STATES)
                 & (DomainEvent.next_attempt_at <= now)),
                ((DomainEvent.delivery_status == "PROCESSING")
                 & (DomainEvent.locked_until <= now)),
            )]
            if event_id is not None:
                conditions.append(DomainEvent.id == event_id)
            event = session.scalar(select(DomainEvent).where(*conditions).order_by(
                DomainEvent.next_attempt_at, DomainEvent.created_at,
            ).with_for_update(skip_locked=True).limit(1))
            if event is None:
                session.rollback()
                return None
            lock_id = uuid4()
            event.delivery_status = "PROCESSING"
            event.delivery_lock_id = lock_id
            event.locked_until = now + timedelta(seconds=self._lease_seconds)
            event.attempt_count += 1
            session.commit()
            message = OutboxMessage(
                id=event.id,
                tenant_id=event.tenant_id,
                site_id=event.site_id,
                actor_account_id=event.actor_account_id,
                event_type=event.event_type,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                correlation_id=event.correlation_id,
                payload=event.payload,
            )
            return event.id, lock_id, message
        finally:
            session.close()

    def _record_success(self, event_id: UUID, lock_id: UUID, now: datetime) -> DispatchResult:
        session = self._session_factory()
        try:
            event = session.scalar(select(DomainEvent).where(
                DomainEvent.id == event_id,
                DomainEvent.delivery_status == "PROCESSING",
                DomainEvent.delivery_lock_id == lock_id,
            ).with_for_update())
            if event is None:
                session.rollback()
                return DispatchResult(event_id=event_id, status="LEASE_LOST")
            event.delivery_status = "PUBLISHED"
            event.published_at = now
            event.next_attempt_at = now
            event.last_error = None
            event.delivery_lock_id = None
            event.locked_until = None
            notification = session.scalar(select(NotificationReadModel).where(
                NotificationReadModel.domain_event_id == event.id,
            ).with_for_update())
            if notification is not None:
                notification.delivery_status = "PUBLISHED"
                notification.delivered_at = now
                notification.last_error = None
            session.commit()
            return DispatchResult(event_id=event_id, status="PUBLISHED")
        finally:
            session.close()

    def _record_failure(self, event_id: UUID, lock_id: UUID, now: datetime, error_code: str) -> DispatchResult:
        session = self._session_factory()
        try:
            event = session.scalar(select(DomainEvent).where(
                DomainEvent.id == event_id,
                DomainEvent.delivery_status == "PROCESSING",
                DomainEvent.delivery_lock_id == lock_id,
            ).with_for_update())
            if event is None:
                session.rollback()
                return DispatchResult(event_id=event_id, status="LEASE_LOST")
            event.last_error = error_code[:80] or "CHANNEL_UNAVAILABLE"
            event.delivery_lock_id = None
            event.locked_until = None
            if event.attempt_count >= self._max_attempts:
                event.delivery_status = "DEAD_LETTER"
                event.next_attempt_at = now
            else:
                event.delivery_status = "RETRY_SCHEDULED"
                event.next_attempt_at = now + timedelta(seconds=min(300, 2 ** (event.attempt_count - 1)))
            notification = session.scalar(select(NotificationReadModel).where(
                NotificationReadModel.domain_event_id == event.id,
            ).with_for_update())
            if notification is not None:
                notification.delivery_status = event.delivery_status
                notification.last_error = event.last_error
            session.commit()
            return DispatchResult(event_id=event_id, status=event.delivery_status)
        finally:
            session.close()
