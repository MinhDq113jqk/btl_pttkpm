"""Resident Service Request acceptance tests for the disposable PostgreSQL cluster."""
from datetime import date
from decimal import Decimal
import os
import secrets
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Database
from app.core.security import create_token, hash_password
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.person import Person, UnitPersonRelationship
from app.models.platform import Attachment, AuditEvent, IdempotencyRecord
from app.models.service import ServiceCategory, ServiceRequest
from app.models.tenant import Tenant
from app.models.site import Site
from app.models.building import Building
from app.models.unit import Unit


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; resident requests require its disposable PostgreSQL cluster",
)]

PNG = (b"\x89PNG\r\n\x1a\n" + b"resident-synthetic-evidence"
       + b"\x00\x00\x00\x00IEND\xaeB\x60\x82")


def _headers(case, resident: str, key: str | None = None) -> dict[str, str]:
    headers = case["auth"][resident].copy()
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _scope_error(response) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"


@pytest.fixture(scope="module")
def resident_request_case():
    """Own fixture keeps resident authorization tests independent of staff tests."""
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
        tenant = Tenant(name=f"R6 resident requests {uuid4()}")
        session.add(tenant)
        session.flush()
        site = Site(tenant_id=tenant.id, code=f"R6-W-{uuid4().hex[:8]}",
                    name="Resident West", address="Synthetic")
        other_site = Site(tenant_id=tenant.id, code=f"R6-E-{uuid4().hex[:8]}",
                          name="Resident East", address="Synthetic")
        session.add_all((site, other_site))
        session.flush()
        building = Building(site_id=site.id, code="B1", name="Resident West")
        other_building = Building(site_id=other_site.id, code="E1", name="Resident East")
        session.add_all((building, other_building))
        session.flush()
        unit = Unit(building_id=building.id, unit_number="R6-0101", floor=1,
                    area_m2=50, status="occupied")
        other_unit = Unit(building_id=other_building.id, unit_number="R6-E-0101", floor=1,
                          area_m2=50, status="occupied")
        category = ServiceCategory(tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                                   code="R6-TECH", name="Resident technical", sla_minutes=240)
        other_category = ServiceCategory(
            tenant_id=tenant.id, site_id=other_site.id, building_id=other_building.id,
            code="R6-E-TECH", name="Resident east", sla_minutes=240,
        )
        staff = Account(tenant_id=tenant.id, username=f"r6_cskh_{uuid4().hex}",
                        full_name="R6 CSKH", hashed_password=hash_password(password))
        session.add_all((unit, other_unit, category, other_category, staff))
        session.flush()
        session.add(AccountRole(account_id=staff.id, role="cskh", site_id=site.id,
                                building_id=building.id))
        residents = {}
        for label in ("resident", "housemate", "revoked"):
            person = Person(
                tenant_id=tenant.id,
                full_name=f"R6 {label}", phone_masked="***", email_masked=f"{label}@example.invalid",
            )
            session.add(person)
            session.flush()
            account = Account(
                tenant_id=tenant.id, username=f"r6_{label}_{uuid4().hex}",
                full_name=f"R6 {label}", hashed_password=hash_password(password), person_id=person.id,
            )
            session.add(account)
            session.flush()
            session.add(AccountRole(account_id=account.id, role="resident", site_id=site.id,
                                    building_id=building.id))
            session.add(UnitPersonRelationship(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                unit_id=unit.id, person_id=person.id,
                relationship_type="owner" if label == "resident" else "family_member",
                ownership_ratio=Decimal("1.0000") if label == "resident" else None,
                valid_from=date(2025, 1, 1),
            ))
            residents[label] = (account, person)

        foreign_tenant = Tenant(name=f"R6 foreign {uuid4()}")
        session.add(foreign_tenant)
        session.flush()
        foreign_site = Site(tenant_id=foreign_tenant.id, code=f"R6-{uuid4().hex[:8]}",
                            name="Foreign", address="Synthetic")
        session.add(foreign_site)
        session.flush()
        foreign_building = Building(site_id=foreign_site.id, code="F1", name="Foreign")
        session.add(foreign_building)
        session.flush()
        foreign_unit = Unit(building_id=foreign_building.id, unit_number="F-0101", floor=1,
                            area_m2=50, status="occupied")
        session.add(foreign_unit)
        session.commit()

    with TestClient(create_app(settings, database)) as client:
        auth = {}
        for label, (account, _) in residents.items():
            response = client.post("/api/v1/auth/login", json={
                "username": account.username, "password": password,
            })
            assert response.status_code == 200, response.text
            auth[label] = {"Authorization": "Bearer " + response.json()["access_token"]}
        staff_response = client.post("/api/v1/auth/login", json={
            "username": staff.username, "password": password,
        })
        assert staff_response.status_code == 200, staff_response.text
        auth["cskh"] = {"Authorization": "Bearer " + staff_response.json()["access_token"]}
        yield {
            "client": client, "database": database, "settings": settings,
            "tenant": tenant, "site": site, "other_site": other_site, "building": building,
            "other_building": other_building, "unit": unit, "other_unit": other_unit,
            "category": category, "other_category": other_category, "staff": staff,
            "residents": residents, "foreign_unit": foreign_unit, "auth": auth,
        }
    transaction.rollback()
    connection.close()
    database.close()


def _create(case, *, key="resident-create-0001", **overrides):
    body = {
        "unit_id": str(case["unit"].id),
        "category_id": str(case["category"].id),
        "title": "Rò rỉ nước tại bếp",
        "description": "Nước rò rỉ liên tục dưới chậu rửa.",
        "priority": "HIGH",
    } | overrides
    response = case["client"].post("/api/v1/resident/service-requests",
                                    headers=_headers(case, "resident", key), json=body)
    return response, body


def test_resident_service_request_options_are_limited_to_effective_units(resident_request_case):
    case = resident_request_case
    response = case["client"].get(
        "/api/v1/resident/service-request-options",
        headers=_headers(case, "resident"),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert {item["id"] for item in payload["buildings"]} == {str(case["building"].id)}
    assert {item["id"] for item in payload["units"]} == {str(case["unit"].id)}
    assert {item["id"] for item in payload["categories"]} == {str(case["category"].id)}
    assert "tenant_id" not in response.text
    assert case["client"].get(
        "/api/v1/resident/service-request-options", headers=_headers(case, "cskh"),
    ).status_code == 403
    forged_site = create_token({
        "sub": str(case["residents"]["resident"][0].id),
        "tenant_id": str(case["tenant"].id),
        "roles": ["resident"],
        "active_site_id": str(case["other_site"].id),
        "purpose": "session",
    }, case["settings"].auth_secret())
    assert case["client"].get(
        "/api/v1/resident/service-request-options",
        headers={"Authorization": "Bearer " + forged_site},
    ).status_code == 404


def test_resident_create_replay_and_scope_are_server_derived(resident_request_case):
    case = resident_request_case
    created, body = _create(case)
    assert created.status_code == 201, created.text
    request_view = created.json()
    assert request_view["unit_id"] == str(case["unit"].id)
    assert request_view["status"] == "NEW"
    assert "tenant_id" not in request_view and "owner_account_id" not in request_view

    replay, _ = _create(case)
    assert replay.status_code == 201
    assert replay.json()["id"] == request_view["id"]
    conflict, _ = _create(case, title="Nội dung khác")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ERR-CONFLICT"

    listing = case["client"].get("/api/v1/resident/service-requests", headers=_headers(case, "resident"))
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == request_view["id"]
    _scope_error(case["client"].get(
        f"/api/v1/resident/service-requests/{request_view['id']}", headers=_headers(case, "housemate"),
    ))
    assert case["client"].get("/api/v1/resident/service-requests", headers=_headers(case, "housemate")).json()["total"] == 0

    for unit_id, category_id in ((case["other_unit"].id, case["category"].id),
                                 (case["foreign_unit"].id, case["category"].id),
                                 (case["unit"].id, case["other_category"].id)):
        blocked, _ = _create(case, key=f"resident-scope-{uuid4().hex[:12]}",
                             unit_id=str(unit_id), category_id=str(category_id))
        _scope_error(blocked)
    assert case["client"].post("/api/v1/resident/service-requests", headers=_headers(
        case, "cskh", "staff-cannot-create-resident",
    ), json=body).status_code == 403

    with case["database"].get_session() as session:
        assert session.scalar(select(func.count(ServiceRequest.id)).where(
            ServiceRequest.created_by_id == case["residents"]["resident"][0].id,
        )) == 1
        assert session.scalar(select(func.count(IdempotencyRecord.id)).where(
            IdempotencyRecord.operation == "resident-service-request.create",
            IdempotencyRecord.actor_account_id == case["residents"]["resident"][0].id,
        )) == 1


def test_resident_update_is_versioned_and_keeps_staff_reassignment_visible(resident_request_case):
    case = resident_request_case
    original = case["client"].get("/api/v1/resident/service-requests", headers=_headers(case, "resident")).json()["items"][0]
    update_body = {"expected_version": original["version"], "title": "Rò rỉ nước nghiêm trọng"}
    updated = case["client"].patch(
        f"/api/v1/resident/service-requests/{original['id']}",
        headers=_headers(case, "resident", "resident-update-0001"), json=update_body,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == original["version"] + 1
    assert updated.json()["title"] == update_body["title"]
    replay = case["client"].patch(
        f"/api/v1/resident/service-requests/{original['id']}",
        headers=_headers(case, "resident", "resident-update-0001"), json=update_body,
    )
    assert replay.status_code == 200
    assert replay.json()["version"] == updated.json()["version"]
    stale = case["client"].patch(
        f"/api/v1/resident/service-requests/{original['id']}",
        headers=_headers(case, "resident", "resident-update-0002"), json=update_body,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "ERR-CONFLICT"

    with case["database"].get_session() as session:
        record = session.get(ServiceRequest, original["id"])
        record.owner_account_id = case["staff"].id
        record.status = "TRIAGED"
        record.version += 1
        session.commit()
    # Assignment changes the operational owner but does not turn the resident's
    # own request into an inaccessible record.
    visible = case["client"].get(
        f"/api/v1/resident/service-requests/{original['id']}", headers=_headers(case, "resident"),
    )
    assert visible.status_code == 200
    forbidden_state = case["client"].patch(
        f"/api/v1/resident/service-requests/{original['id']}",
        headers=_headers(case, "resident", "resident-update-0003"),
        json={"expected_version": visible.json()["version"], "priority": "LOW"},
    )
    assert forbidden_state.status_code == 409
    assert forbidden_state.json()["error"]["code"] == "ERR-STATE-TRANSITION"


def test_resident_evidence_timeline_download_and_immutable_audit(resident_request_case):
    case = resident_request_case
    request_id = case["client"].get("/api/v1/resident/service-requests", headers=_headers(case, "resident")).json()["items"][0]["id"]
    with case["database"].get_session() as session:
        record = session.get(ServiceRequest, request_id)
        record.status = "WAITING_INFO"
        record.version += 1
        session.commit()

    headers = _headers(case, "resident", "resident-evidence-0001") | {
        "Content-Type": "image/png", "X-File-Name": "kitchen.png",
    }
    uploaded = case["client"].post(
        f"/api/v1/resident/service-requests/{request_id}/evidence", headers=headers, content=PNG,
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    replay = case["client"].post(
        f"/api/v1/resident/service-requests/{request_id}/evidence", headers=headers, content=PNG,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == attachment["id"]
    evidence = case["client"].get(
        f"/api/v1/resident/service-requests/{request_id}/evidence", headers=_headers(case, "resident"),
    )
    assert evidence.status_code == 200
    assert [item["id"] for item in evidence.json()["items"]] == [attachment["id"]]
    _scope_error(case["client"].get(
        f"/api/v1/resident/service-requests/{request_id}/evidence", headers=_headers(case, "housemate"),
    ))

    signed = case["client"].get(
        f"/api/v1/resident/service-requests/{request_id}/evidence/{attachment['id']}/signed-link",
        headers=_headers(case, "resident"),
    )
    assert signed.status_code == 200, signed.text
    download = case["client"].get(signed.json()["url"], headers=_headers(case, "resident"))
    assert download.status_code == 200
    assert download.content == PNG
    assert download.headers["cache-control"] == "private, no-store"

    rejected_headers = _headers(case, "resident", "resident-evidence-0002") | {
        "Content-Type": "image/png", "X-File-Name": "../../bad.png",
    }
    rejected = case["client"].post(
        f"/api/v1/resident/service-requests/{request_id}/evidence", headers=rejected_headers,
        content=b"not an image",
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "ERR-FILE-QUARANTINED"
    assert case["client"].post(
        f"/api/v1/resident/service-requests/{request_id}/evidence", headers=rejected_headers,
        content=b"not an image",
    ).status_code == 422

    timeline = case["client"].get(
        f"/api/v1/resident/service-requests/{request_id}/timeline", headers=_headers(case, "resident"),
    )
    assert timeline.status_code == 200
    assert {event["event_type"] for event in timeline.json()["items"]} >= {
        "ResidentServiceRequestCreated", "ResidentServiceRequestUpdated",
    }
    assert "actor_account_id" not in timeline.text

    with case["database"].get_session() as session:
        attachment_row = session.get(Attachment, attachment["id"])
        assert attachment_row.service_request_id == UUID(request_id)
        assert attachment_row.work_order_id is None
        audit_event = session.scalar(select(AuditEvent).where(
            AuditEvent.resource_type == "ServiceRequest", AuditEvent.resource_id == request_id,
        ).order_by(AuditEvent.created_at).limit(1))
        assert audit_event is not None
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text("UPDATE greencity.audit_events SET action = 'mutated' WHERE id = :id"),
                                {"id": audit_event.id})


def test_resident_scope_is_rechecked_after_relationship_revocation(resident_request_case):
    case = resident_request_case
    request_id = case["client"].get("/api/v1/resident/service-requests", headers=_headers(case, "resident")).json()["items"][0]["id"]
    with case["database"].get_session() as session:
        account, person = case["residents"]["revoked"]
        relationship = session.scalar(select(UnitPersonRelationship).where(
            UnitPersonRelationship.person_id == person.id,
            UnitPersonRelationship.unit_id == case["unit"].id,
        ))
        assert relationship is not None
        session.delete(relationship)
        session.commit()
    _scope_error(case["client"].get(
        f"/api/v1/resident/service-requests/{request_id}", headers=_headers(case, "revoked"),
    ))

    forged = create_token({
        "sub": str(case["residents"]["resident"][0].id),
        "tenant_id": str(uuid4()),
        "roles": ["admin", "resident"],
        "active_site_id": str(case["other_site"].id),
        "purpose": "session",
    }, case["settings"].auth_secret())
    _scope_error(case["client"].get(
        f"/api/v1/resident/service-requests/{request_id}",
        headers={"Authorization": "Bearer " + forged},
    ))
