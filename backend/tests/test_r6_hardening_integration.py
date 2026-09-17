"""R6 release-hardening checks against the disposable PostgreSQL cluster."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import os
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.core.config import Settings
from app.core.database import Database
from app.models.platform import DomainEvent
from app.models.site import Site
from app.models.tenant import Tenant
from app.services.outbox import OutboxDispatcher


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R6 hardening requires its disposable PostgreSQL cluster",
)]


class RecordingChannel:
    """Thread-safe test channel; no external provider is contacted."""

    def __init__(self):
        self.calls: list[tuple] = []
        self._lock = Lock()

    def deliver(self, message, *, idempotency_key: str) -> None:
        with self._lock:
            self.calls.append((message.id, idempotency_key, message.correlation_id))


def _database() -> Database:
    settings = Settings()
    assert settings.app_env == "test"
    assert settings.sqlalchemy_url().host == "127.0.0.1"
    return Database(settings)


def test_r6_concurrent_outbox_dispatchers_deliver_one_claimed_event():
    """Two independent workers must not deliver the same due event twice."""
    database = _database()
    try:
        now = datetime.now(UTC)
        correlation_id = uuid4()
        with database.get_session() as session:
            tenant = Tenant(name=f"R6 outbox race {uuid4()}")
            session.add(tenant)
            session.flush()
            site = Site(
                tenant_id=tenant.id,
                code=f"R6-OUTBOX-{uuid4().hex[:8]}",
                name="Outbox race site",
                address="Synthetic",
            )
            session.add(site)
            session.flush()
            event = DomainEvent(
                tenant_id=tenant.id,
                site_id=site.id,
                actor_account_id=None,
                event_type="R6OutboxRace",
                resource_type="ReleaseHardening",
                resource_id=uuid4(),
                correlation_id=correlation_id,
                payload={"kind": "synthetic"},
                next_attempt_at=now,
            )
            session.add(event)
            session.commit()
            event_id = event.id

        channel = RecordingChannel()
        barrier = Barrier(3, timeout=10)

        def dispatch_once():
            dispatcher = OutboxDispatcher(database.get_session, channel)
            barrier.wait()
            return dispatcher.dispatch_once(now=now, event_id=event_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(dispatch_once) for _ in range(2)]
            barrier.wait()
            results = [future.result(timeout=15) for future in futures]

        assert {(result.event_id, result.status) for result in results} == {
            (None, None),
            (event_id, "PUBLISHED"),
        }
        assert channel.calls == [(event_id, str(event_id), correlation_id)]
        with database.get_session() as session:
            persisted = session.scalar(select(DomainEvent).where(DomainEvent.id == event_id))
            assert persisted is not None
            assert persisted.delivery_status == "PUBLISHED"
            assert persisted.attempt_count == 1
            assert persisted.delivery_lock_id is None and persisted.locked_until is None
    finally:
        database.close()


def test_r6_hot_path_indexes_exist_in_postgresql_after_migration():
    """Performance baseline: migrated physical indexes back the resident hot paths."""
    database = _database()
    try:
        index_names = (
            "ix_ar_ledger_entries_account_effective",
            "ix_notification_read_models_recipient",
            "ix_domain_events_dispatch_due",
        )
        with database.get_session() as session:
            for index_name in index_names:
                assert session.scalar(text("SELECT to_regclass(:name)"), {
                    "name": f"greencity.{index_name}",
                }) == f"greencity.{index_name}"
    finally:
        database.close()
