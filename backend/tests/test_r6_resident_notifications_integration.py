"""Resident notification inbox acceptance tests for the disposable PostgreSQL cluster."""
from datetime import UTC, date, datetime
from decimal import Decimal
import os
import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Database
from app.core.security import create_token, hash_password
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.person import Person, UnitPersonRelationship
from app.models.platform import AuditEvent, DomainEvent, NotificationReadModel
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; resident notification tests require its disposable PostgreSQL cluster",
)]


def _headers(case, actor: str) -> dict[str, str]:
    return case["auth"][actor].copy()


def _scope_error(response) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"


def _notification(session, *, tenant, site, recipient, label: str, correlation_id, read_at=None):
    event = DomainEvent(
        tenant_id=tenant.id,
        site_id=site.id,
        event_type="ResidentCommunicationRequested",
        resource_type="ResidentCommunication",
        resource_id=uuid4(),
        correlation_id=correlation_id,
        payload={"notification": {"template_code": f"R6_{label}"}},
        delivery_status="PUBLISHED",
        published_at=datetime(2026, 1, 20, tzinfo=UTC),
    )
    session.add(event)
    session.flush()
    notification = NotificationReadModel(
        tenant_id=tenant.id,
        site_id=site.id,
        recipient_account_id=recipient.id,
        domain_event_id=event.id,
        template_code=f"R6_{label}",
        template_snapshot={"title": f"Message {label}", "body": "Synthetic resident notification."},
        delivery_status="PUBLISHED",
        delivered_at=datetime(2026, 1, 20, tzinfo=UTC),
        read_at=read_at,
    )
    session.add(notification)
    session.flush()
    return notification, event


@pytest.fixture(scope="module")
def resident_notification_case():
    settings = Settings()
    assert settings.app_env == "test"
    assert settings.sqlalchemy_url().host == "127.0.0.1"
    database = Database(settings)
    connection = database.engine.connect()
    transaction = connection.begin()
    database.sessions = sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint",
    )
    password = secrets.token_urlsafe(24)
    with database.get_session() as session:
        tenant = Tenant(name=f"R6 resident notifications {uuid4()}")
        foreign_tenant = Tenant(name=f"R6 resident notifications foreign {uuid4()}")
        session.add_all((tenant, foreign_tenant))
        session.flush()
        site = Site(tenant_id=tenant.id, code=f"R6-N-{uuid4().hex[:8]}",
                    name="Notification home", address="Synthetic")
        other_site = Site(tenant_id=tenant.id, code=f"R6-NO-{uuid4().hex[:8]}",
                          name="Notification other", address="Synthetic")
        foreign_site = Site(tenant_id=foreign_tenant.id, code=f"R6-NF-{uuid4().hex[:8]}",
                            name="Notification foreign", address="Synthetic")
        session.add_all((site, other_site, foreign_site))
        session.flush()
        building = Building(site_id=site.id, code="R6-N1", name="Notification home")
        other_site_building = Building(site_id=other_site.id, code="R6-NO1", name="Notification other")
        foreign_building = Building(site_id=foreign_site.id, code="R6-NF1", name="Notification foreign")
        session.add_all((building, other_site_building, foreign_building))
        session.flush()
        unit = Unit(building_id=building.id, unit_number="R6-N-0101", floor=1, area_m2=50, status="occupied")
        other_unit = Unit(building_id=building.id, unit_number="R6-N-0102", floor=1, area_m2=50, status="occupied")
        other_site_unit = Unit(building_id=other_site_building.id, unit_number="R6-NO-0101", floor=1,
                               area_m2=50, status="occupied")
        foreign_unit = Unit(building_id=foreign_building.id, unit_number="R6-NF-0101", floor=1,
                            area_m2=50, status="occupied")
        session.add_all((unit, other_unit, other_site_unit, foreign_unit))
        session.flush()

        residents = {}
        for label, resident_unit in (("resident", unit), ("other_resident", other_unit), ("revoked", unit)):
            person = Person(
                tenant_id=tenant.id, full_name=f"R6 {label}", phone_masked="***",
                email_masked=f"{label}@example.invalid",
            )
            session.add(person)
            session.flush()
            account = Account(
                tenant_id=tenant.id, username=f"r6_notification_{label}_{uuid4().hex}",
                full_name=f"R6 {label}", hashed_password=hash_password(password), person_id=person.id,
            )
            session.add(account)
            session.flush()
            session.add_all((
                AccountRole(account_id=account.id, role="resident", site_id=site.id, building_id=building.id),
                UnitPersonRelationship(
                    tenant_id=tenant.id, site_id=site.id, building_id=resident_unit.building_id,
                    unit_id=resident_unit.id, person_id=person.id,
                    relationship_type="family_member" if label == "revoked" else "owner",
                    ownership_ratio=None if label == "revoked" else Decimal("1.0000"),
                    valid_from=date(2025, 1, 1),
                ),
            ))
            residents[label] = (account, person)

        staff = Account(
            tenant_id=tenant.id, username=f"r6_notification_staff_{uuid4().hex}",
            full_name="R6 notification staff", hashed_password=hash_password(password),
        )
        other_site_account = Account(
            tenant_id=tenant.id, username=f"r6_notification_other_site_{uuid4().hex}",
            full_name="R6 other site", hashed_password=hash_password(password),
        )
        foreign_account = Account(
            tenant_id=foreign_tenant.id, username=f"r6_notification_foreign_{uuid4().hex}",
            full_name="R6 foreign", hashed_password=hash_password(password),
        )
        session.add_all((staff, other_site_account, foreign_account))
        session.flush()
        session.add(AccountRole(account_id=staff.id, role="cskh", site_id=site.id, building_id=building.id))

        correlations = {name: uuid4() for name in ("unread", "read", "other", "other_site", "foreign")}
        notifications = {
            "unread": _notification(
                session, tenant=tenant, site=site, recipient=residents["resident"][0], label="UNREAD",
                correlation_id=correlations["unread"],
            ),
            "read": _notification(
                session, tenant=tenant, site=site, recipient=residents["resident"][0], label="READ",
                correlation_id=correlations["read"], read_at=datetime(2026, 1, 21, tzinfo=UTC),
            ),
            "other": _notification(
                session, tenant=tenant, site=site, recipient=residents["other_resident"][0], label="OTHER",
                correlation_id=correlations["other"],
            ),
            "other_site": _notification(
                session, tenant=tenant, site=other_site, recipient=other_site_account, label="OTHER_SITE",
                correlation_id=correlations["other_site"],
            ),
            "foreign": _notification(
                session, tenant=foreign_tenant, site=foreign_site, recipient=foreign_account, label="FOREIGN",
                correlation_id=correlations["foreign"],
            ),
        }
        session.commit()

    with TestClient(create_app(settings, database)) as client:
        auth = {}
        for label, (account, _) in residents.items():
            response = client.post("/api/v1/auth/login", json={
                "username": account.username, "password": password,
            })
            assert response.status_code == 200, response.text
            auth[label] = {"Authorization": "Bearer " + response.json()["access_token"]}
        response = client.post("/api/v1/auth/login", json={
            "username": staff.username, "password": password,
        })
        assert response.status_code == 200, response.text
        auth["staff"] = {"Authorization": "Bearer " + response.json()["access_token"]}
        yield {
            "client": client, "database": database, "settings": settings, "tenant": tenant,
            "site": site, "other_site": other_site, "unit": unit, "residents": residents,
            "auth": auth, "notifications": notifications, "correlations": correlations,
        }
    transaction.rollback()
    connection.close()
    database.close()


def test_resident_inbox_paginates_unread_and_audits_first_read(resident_notification_case):
    case = resident_notification_case
    unread, unread_event = case["notifications"]["unread"]
    read, _ = case["notifications"]["read"]
    inbox = case["client"].get(
        "/api/v1/resident/notifications", headers=_headers(case, "resident"),
        params={"page": 1, "page_size": 1},
    )
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["page"] == 1 and inbox.json()["page_size"] == 1
    assert inbox.json()["total"] == 1 and inbox.json()["unread_count"] == 1
    assert inbox.json()["items"] == [{
        "id": str(unread.id), "template_code": "R6_UNREAD",
        "template_snapshot": {"title": "Message UNREAD", "body": "Synthetic resident notification."},
        "delivery_status": "PUBLISHED", "delivered_at": "2026-01-20T00:00:00Z",
        "read_at": None, "correlation_id": str(case["correlations"]["unread"]),
        "created_at": inbox.json()["items"][0]["created_at"],
    }]
    assert "recipient_account_id" not in inbox.text and "domain_event_id" not in inbox.text

    all_items = case["client"].get(
        "/api/v1/resident/notifications", headers=_headers(case, "resident"),
        params={"include_read": True},
    )
    assert all_items.status_code == 200
    assert all_items.json()["total"] == 2 and all_items.json()["unread_count"] == 1
    assert {item["id"] for item in all_items.json()["items"]} == {str(unread.id), str(read.id)}

    request_correlation = uuid4()
    marked = case["client"].post(
        f"/api/v1/resident/notifications/{unread.id}/read",
        headers=_headers(case, "resident") | {"X-Correlation-ID": str(request_correlation)},
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["read_at"] is not None
    assert marked.json()["correlation_id"] == str(case["correlations"]["unread"])
    replay = case["client"].post(
        f"/api/v1/resident/notifications/{unread.id}/read",
        headers=_headers(case, "resident") | {"X-Correlation-ID": str(uuid4())},
    )
    assert replay.status_code == 200 and replay.json()["read_at"] == marked.json()["read_at"]
    assert case["client"].get(
        "/api/v1/resident/notifications", headers=_headers(case, "resident"),
    ).json() == {"items": [], "page": 1, "page_size": 20, "total": 0, "unread_count": 0}

    with case["database"].get_session() as session:
        audit_event = session.scalar(select(AuditEvent).where(
            AuditEvent.actor_account_id == case["residents"]["resident"][0].id,
            AuditEvent.event_type == "ResidentNotificationRead",
            AuditEvent.resource_id == unread.id,
            AuditEvent.correlation_id == request_correlation,
        ))
        assert audit_event is not None
        assert audit_event.after_data == {
            "domain_event_id": str(unread_event.id),
            "notification_correlation_id": str(case["correlations"]["unread"]),
        }


def test_resident_notification_scope_is_account_specific_and_server_derived(resident_notification_case):
    case = resident_notification_case
    own_id = str(case["notifications"]["unread"][0].id)
    other_id = str(case["notifications"]["other"][0].id)
    hidden_ids = {str(case["notifications"][name][0].id) for name in ("other_site", "foreign")}
    other = case["client"].get(
        "/api/v1/resident/notifications", headers=_headers(case, "other_resident"),
        params={"include_read": True},
    )
    assert other.status_code == 200
    assert [item["id"] for item in other.json()["items"]] == [other_id]
    assert own_id not in [item["id"] for item in other.json()["items"]]
    assert not hidden_ids.intersection(item["id"] for item in other.json()["items"])
    _scope_error(case["client"].post(
        f"/api/v1/resident/notifications/{own_id}/read", headers=_headers(case, "other_resident"),
    ))
    assert case["client"].get(
        "/api/v1/resident/notifications", headers=_headers(case, "staff"),
    ).status_code == 403

    forged_tenant_and_role = create_token({
        "sub": str(case["residents"]["resident"][0].id), "tenant_id": str(uuid4()),
        "roles": ["admin", "resident"], "active_site_id": str(case["site"].id), "purpose": "session",
    }, case["settings"].auth_secret())
    forged_allowed = case["client"].get(
        "/api/v1/resident/notifications", headers={"Authorization": "Bearer " + forged_tenant_and_role},
        params={"include_read": True},
    )
    assert forged_allowed.status_code == 200
    assert {item["id"] for item in forged_allowed.json()["items"]} == {
        str(case["notifications"]["unread"][0].id), str(case["notifications"]["read"][0].id),
    }

    forged_site = create_token({
        "sub": str(case["residents"]["resident"][0].id), "tenant_id": str(case["tenant"].id),
        "roles": ["resident"], "active_site_id": str(case["other_site"].id), "purpose": "session",
    }, case["settings"].auth_secret())
    _scope_error(case["client"].get(
        "/api/v1/resident/notifications", headers={"Authorization": "Bearer " + forged_site},
    ))

    with case["database"].get_session() as session:
        _, person = case["residents"]["revoked"]
        relationship = session.scalar(select(UnitPersonRelationship).where(
            UnitPersonRelationship.person_id == person.id,
            UnitPersonRelationship.unit_id == case["unit"].id,
        ))
        assert relationship is not None
        session.delete(relationship)
        session.commit()
    _scope_error(case["client"].get(
        "/api/v1/resident/notifications", headers=_headers(case, "revoked"),
    ))
