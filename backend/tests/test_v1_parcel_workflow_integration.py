"""Task 2 parcel workflow acceptance tests for the disposable PostgreSQL cluster."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Database
from app.core.security import hash_password
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.operations import PatrolPoint, SecurityIncident
from app.models.parcel import Parcel
from app.models.person import Person
from app.models.platform import Attachment, AuditEvent, DomainEvent, IdempotencyRecord
from app.models.service import CaseRecord
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; parcel workflow requires its disposable PostgreSQL cluster",
)]


def _headers(
    case,
    actor: str,
    key: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, str]:
    headers = case["auth"][actor].copy()
    if key is not None:
        headers["Idempotency-Key"] = key
    if correlation_id is not None:
        headers["X-Correlation-ID"] = correlation_id
    return headers


def _scope_error(response) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"


@pytest.fixture(scope="module")
def parcel_case():
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
        tenant = Tenant(name=f"V1 parcel {uuid4()}")
        foreign_tenant = Tenant(name=f"V1 foreign parcel {uuid4()}")
        session.add_all((tenant, foreign_tenant))
        session.flush()
        site = Site(tenant_id=tenant.id, code=f"P-{uuid4().hex[:8]}",
                    name="Parcel site", address="Synthetic")
        foreign_site = Site(tenant_id=foreign_tenant.id, code=f"FP-{uuid4().hex[:8]}",
                            name="Foreign parcel site", address="Synthetic")
        session.add_all((site, foreign_site))
        session.flush()
        building = Building(site_id=site.id, code="B1", name="Parcel building")
        other_building = Building(site_id=site.id, code="B2", name="Other building")
        foreign_building = Building(site_id=foreign_site.id, code="F1", name="Foreign building")
        session.add_all((building, other_building, foreign_building))
        session.flush()
        unit = Unit(building_id=building.id, unit_number="P-0101", floor=1,
                    area_m2=50, status="occupied")
        other_unit = Unit(building_id=other_building.id, unit_number="P-0201", floor=2,
                          area_m2=50, status="occupied")
        foreign_unit = Unit(building_id=foreign_building.id, unit_number="F-0101", floor=1,
                            area_m2=50, status="occupied")
        person = Person(tenant_id=tenant.id, full_name="Parcel recipient",
                        phone_masked="***", email_masked="recipient@example.invalid")
        foreign_person = Person(tenant_id=foreign_tenant.id, full_name="Foreign recipient",
                                phone_masked="***", email_masked="foreign@example.invalid")
        cskh = Account(tenant_id=tenant.id, username=f"parcel_cskh_{uuid4().hex}",
                       full_name="Parcel CSKH", hashed_password=hash_password(password))
        security = Account(tenant_id=tenant.id, username=f"parcel_security_{uuid4().hex}",
                           full_name="Parcel security", hashed_password=hash_password(password))
        director = Account(tenant_id=tenant.id, username=f"parcel_director_{uuid4().hex}",
                           full_name="Parcel director", hashed_password=hash_password(password))
        accountant = Account(tenant_id=tenant.id, username=f"parcel_accountant_{uuid4().hex}",
                             full_name="Parcel accountant", hashed_password=hash_password(password))
        session.add_all((unit, other_unit, foreign_unit, person, foreign_person,
                         cskh, security, director, accountant))
        session.flush()
        patrol_point = PatrolPoint(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            code=f"P-POINT-{uuid4().hex[:8]}", name="Parcel desk patrol point",
            created_by_id=director.id, updated_by_id=director.id,
        )
        session.add(patrol_point)
        session.flush()
        session.add_all((
            AccountRole(account_id=cskh.id, role="cskh", site_id=site.id, building_id=building.id),
            AccountRole(account_id=security.id, role="security", site_id=site.id, building_id=building.id),
            AccountRole(account_id=director.id, role="director", site_id=site.id, building_id=None),
            AccountRole(account_id=accountant.id, role="accountant", site_id=site.id, building_id=building.id),
        ))
        session.commit()

    with TestClient(create_app(settings, database)) as client:
        auth = {}
        for label, account in (("cskh", cskh), ("security", security),
                               ("director", director), ("accountant", accountant)):
            response = client.post("/api/v1/auth/login", json={
                "username": account.username, "password": password,
            })
            assert response.status_code == 200, response.text
            auth[label] = {"Authorization": "Bearer " + response.json()["access_token"]}
        yield {
            "client": client, "database": database, "settings": settings,
            "tenant": tenant, "foreign_tenant": foreign_tenant,
            "site": site, "foreign_site": foreign_site,
            "building": building, "other_building": other_building,
            "foreign_building": foreign_building,
            "patrol_point": patrol_point,
            "unit": unit, "other_unit": other_unit, "foreign_unit": foreign_unit,
            "person": person, "foreign_person": foreign_person,
            "accounts": {"cskh": cskh, "security": security, "director": director,
                         "accountant": accountant},
            "auth": auth,
        }
    transaction.rollback()
    connection.close()
    database.close()


def _create(case, *, key="parcel-create-001", correlation_id=None, **overrides):
    body = {
        "building_id": str(case["building"].id),
        "unit_id": str(case["unit"].id),
        "recipient_person_id": str(case["person"].id),
        "parcel_code": f"P-{uuid4().hex[:10]}",
        "carrier_reference": "carrier-001",
        "recipient_name_snapshot": "Parcel recipient",
        "recipient_contact_snapshot": "***",
        "storage_location": "Locker A-01",
        "pin": "1234",
    } | overrides
    return case["client"].post(
        "/api/v1/parcels", headers=_headers(case, "cskh", key, correlation_id), json=body,
    ), body


def test_parcel_receive_scope_and_idempotent_replay(parcel_case):
    case = parcel_case
    created, body = _create(case)
    assert created.status_code == 201, created.text
    view = created.json()
    assert view["status"] == "RECEIVED"
    assert view["version"] == 1
    assert view["recipient_name_snapshot"] == body["recipient_name_snapshot"]
    assert '"pin":' not in created.text and "pin_hash" not in created.text

    replay = case["client"].post(
        "/api/v1/parcels", headers=_headers(case, "cskh", "parcel-create-001"), json=body,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == view["id"]
    conflict = case["client"].post(
        "/api/v1/parcels",
        headers=_headers(case, "cskh", "parcel-create-001"),
        json=body | {"parcel_code": "P-DIFFERENT"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ERR-CONFLICT"

    listing = case["client"].get("/api/v1/parcels", headers=_headers(case, "cskh"))
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == view["id"]
    assert case["client"].get(
        f"/api/v1/parcels/{view['id']}", headers=_headers(case, "accountant"),
    ).status_code == 403

    for invalid in (
        {"building_id": str(case["other_building"].id), "unit_id": str(case["other_unit"].id)},
        {"recipient_person_id": str(case["foreign_person"].id)},
    ):
        blocked, _ = _create(case, key=f"parcel-scope-{uuid4().hex[:12]}", **invalid)
        _scope_error(blocked)

    with case["database"].get_session() as session:
        assert session.scalar(select(func.count(Parcel.id)).where(
            Parcel.id == view["id"],
        )) == 1
        assert session.scalar(select(func.count(IdempotencyRecord.id)).where(
            IdempotencyRecord.operation == "parcel.create",
            IdempotencyRecord.resource_id == view["id"],
        )) == 1


def test_parcel_ready_handover_pin_snapshot_audit_and_optimistic_lock(parcel_case):
    case = parcel_case
    created, _ = _create(case, key="parcel-flow-001")
    parcel = created.json()
    ready = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/ready",
        headers=_headers(case, "cskh", "parcel-ready-001"),
        json={"expected_version": parcel["version"]},
    )
    assert ready.status_code == 200, ready.text
    ready_view = ready.json()
    assert ready_view["status"] == "READY_FOR_PICKUP"
    assert ready_view["ready_for_pickup_at"] is not None
    replay = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/ready",
        headers=_headers(case, "cskh", "parcel-ready-001"),
        json={"expected_version": parcel["version"]},
    )
    assert replay.status_code == 200
    assert replay.json()["version"] == ready_view["version"]

    wrong = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/handover",
        headers=_headers(case, "security", "parcel-handover-wrong"),
        json={"expected_version": ready_view["version"], "pin": "9999"},
    )
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "ERR-PIN-INVALID"
    after_wrong = case["client"].get(
        f"/api/v1/parcels/{parcel['id']}", headers=_headers(case, "security"),
    ).json()
    assert after_wrong["pin_attempt_count"] == 1
    assert after_wrong["status"] == "READY_FOR_PICKUP"

    handover = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/handover",
        headers=_headers(case, "security", "parcel-handover-good"),
        json={"expected_version": after_wrong["version"], "pin": "1234"},
    )
    assert handover.status_code == 200, handover.text
    handed = handover.json()
    assert handed["status"] == "HANDED_OVER"
    assert handed["handed_over_by_id"] == str(case["accounts"]["security"].id)
    assert handed["recipient_name_snapshot"] == parcel["recipient_name_snapshot"]
    assert handed["pin_attempt_count"] == 1
    assert "1234" not in handover.text

    replay_handover = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/handover",
        headers=_headers(case, "security", "parcel-handover-good"),
        json={"expected_version": after_wrong["version"], "pin": "1234"},
    )
    assert replay_handover.status_code == 200
    assert replay_handover.json()["id"] == handed["id"]
    stale = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/handover",
        headers=_headers(case, "security", "parcel-handover-stale"),
        json={"expected_version": after_wrong["version"], "pin": "1234"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "ERR-CONFLICT"

    with case["database"].get_session() as session:
        events = session.scalars(select(AuditEvent.event_type).where(
            AuditEvent.resource_type == "Parcel", AuditEvent.resource_id == parcel["id"],
        )).all()
        assert {"ParcelReceived", "ParcelReadyForPickup", "ParcelPinFailed", "ParcelHandedOver"}.issubset(events)
        assert session.scalar(select(func.count(DomainEvent.id)).where(
            DomainEvent.resource_type == "Parcel", DomainEvent.resource_id == parcel["id"],
        )) == 3


def test_parcel_exception_is_reasoned_terminal_and_cannot_reopen(parcel_case):
    case = parcel_case
    created, _ = _create(case, key="parcel-exception-001")
    parcel = created.json()
    lost = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/exception",
        headers=_headers(case, "security", "parcel-exception-command"),
        json={"expected_version": parcel["version"], "status": "LOST", "reason": "Locker audit missing"},
    )
    assert lost.status_code == 200, lost.text
    assert lost.json()["status"] == "LOST"
    assert lost.json()["exception_reason"] == "Locker audit missing"
    replay = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/exception",
        headers=_headers(case, "security", "parcel-exception-command"),
        json={"expected_version": parcel["version"], "status": "LOST", "reason": "Locker audit missing"},
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "LOST"
    reopen = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/ready",
        headers=_headers(case, "cskh", "parcel-exception-reopen"),
        json={"expected_version": lost.json()["version"]},
    )
    assert reopen.status_code == 409
    assert reopen.json()["error"]["code"] == "ERR-STATE-TRANSITION"

    invalid_reason = _create(case, key="parcel-invalid-reason")[0]
    assert invalid_reason.status_code == 201
    invalid = case["client"].post(
        f"/api/v1/parcels/{invalid_reason.json()['id']}/exception",
        headers=_headers(case, "security", "parcel-invalid-exception"),
        json={"expected_version": 1, "status": "DAMAGED", "reason": "x"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "ERR-VALIDATION"


def test_parcel_case_incident_evidence_and_timeline_are_scoped_and_idempotent(parcel_case):
    case = parcel_case
    created, _ = _create(case, key="parcel-case-evidence-001")
    parcel = created.json()

    exception = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/exception",
        headers=_headers(case, "security", "parcel-case-evidence-exception"),
        json={
            "expected_version": parcel["version"],
            "status": "LOST",
            "reason": "Không tìm thấy trong locker.",
        },
    )
    assert exception.status_code == 200, exception.text
    parcel = exception.json()

    opened = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/case",
        headers=_headers(case, "cskh", "parcel-case-open-001"),
        json={"reason": "Kiện thất lạc tại locker."},
    )
    assert opened.status_code == 201, opened.text
    case_view = opened.json()
    assert case_view["source_parcel_id"] == parcel["id"]
    replay = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/case",
        headers=_headers(case, "cskh", "parcel-case-open-001"),
        json={"reason": "Kiện thất lạc tại locker."},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == case_view["id"]
    duplicate = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/case",
        headers=_headers(case, "cskh", "parcel-case-open-002"),
        json={"reason": "Mở thêm lần nữa."},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "ERR-DUPLICATE"

    with case["database"].get_session() as session:
        incident = SecurityIncident(
            tenant_id=case["tenant"].id, site_id=case["site"].id,
            building_id=case["building"].id, code=f"INC-P-{uuid4().hex[:8]}",
            incident_type="SECURITY", severity="LOW", title="Parcel incident",
            description="Parcel linkage fixture", occurred_at=datetime.now(UTC),
            reported_by_id=case["accounts"]["security"].id,
            created_by_id=case["accounts"]["security"].id,
            updated_by_id=case["accounts"]["security"].id,
        )
        session.add(incident)
        session.commit()
        incident_id = incident.id
    linked = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/incident-link",
        headers=_headers(case, "security", "parcel-incident-link-001"),
        json={"incident_id": str(incident_id), "reason": "Đối soát tại chốt an ninh."},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["parcel_id"] == parcel["id"]
    forbidden = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/incident-link",
        headers=_headers(case, "cskh", "parcel-incident-link-cskh"),
        json={"incident_id": str(incident_id)},
    )
    assert forbidden.status_code == 403

    png = b"\x89PNG\r\n\x1a\n" + b"synthetic" + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    upload_headers = _headers(case, "security", "parcel-evidence-001") | {
        "Content-Type": "image/png", "X-File-Name": "locker.png",
    }
    uploaded = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/evidence", headers=upload_headers, content=png,
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    assert attachment["parcel_id"] == parcel["id"]
    assert "storage_key" not in uploaded.text
    replay_upload = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/evidence", headers=upload_headers, content=png,
    )
    assert replay_upload.status_code == 201
    assert replay_upload.json()["id"] == attachment["id"]
    evidence = case["client"].get(
        f"/api/v1/parcels/{parcel['id']}/evidence", headers=_headers(case, "cskh"),
    )
    assert evidence.status_code == 200
    assert [item["id"] for item in evidence.json()["items"]] == [attachment["id"]]
    signed = case["client"].get(
        f"/api/v1/parcels/{parcel['id']}/evidence/{attachment['id']}/signed-link",
        headers=_headers(case, "cskh"),
    )
    assert signed.status_code == 200
    content = case["client"].get(signed.json()["url"], headers=_headers(case, "cskh"))
    assert content.status_code == 200
    assert content.content == png
    bad_token = signed.json()["url"].replace("signed_token=", "signed_token=tampered-")
    assert case["client"].get(bad_token, headers=_headers(case, "cskh")).status_code == 401

    quarantined = case["client"].post(
        f"/api/v1/parcels/{parcel['id']}/evidence",
        headers=_headers(case, "security", "parcel-evidence-bad") | {
            "Content-Type": "image/png", "X-File-Name": "bad.png",
        },
        content=b"not-an-image",
    )
    assert quarantined.status_code == 422
    assert quarantined.json()["error"]["code"] == "ERR-FILE-QUARANTINED"

    timeline = case["client"].get(
        f"/api/v1/parcels/{parcel['id']}/timeline", headers=_headers(case, "cskh"),
    )
    assert timeline.status_code == 200
    event_types = {item["event_type"] for item in timeline.json()["items"]}
    assert {"ParcelReceived", "ParcelCaseOpened", "ParcelIncidentLinked", "ParcelEvidenceAdded"}.issubset(event_types)
    with case["database"].get_session() as session:
        assert session.scalar(select(func.count(CaseRecord.id)).where(CaseRecord.source_parcel_id == parcel["id"])) == 1
        assert session.scalar(select(func.count(SecurityIncident.id)).where(SecurityIncident.parcel_id == parcel["id"])) == 1
        assert session.scalar(select(func.count(Attachment.id)).where(Attachment.parcel_id == parcel["id"])) == 2


def test_parcel_task5_golden_flows_run_through_api_and_preserve_exit_evidence(parcel_case):
    """Task 5 exit proof: one API trace covers both parcel branches end to end.

    The happy branch proves receive -> ready -> handover and immutable snapshots.
    The exception branch proves exception -> Case -> Incident -> private evidence
    -> signed download -> audit timeline. The only SQL below is a read-only oracle;
    all domain mutations, including the prerequisite patrol incident, use HTTP.
    """
    case = parcel_case
    correlation_id = str(uuid4())
    client = case["client"]

    created, _ = _create(
        case, key="parcel-task5-happy-create", correlation_id=correlation_id,
    )
    assert created.status_code == 201, created.text
    happy = created.json()
    snapshot_fields = (
        "tenant_id", "site_id", "building_id", "unit_id", "recipient_person_id",
        "parcel_code", "carrier_reference", "recipient_name_snapshot",
        "recipient_contact_snapshot", "storage_location", "received_at",
    )
    snapshot = {field: happy[field] for field in snapshot_fields}

    ready_headers = _headers(case, "cskh", "parcel-task5-happy-ready", correlation_id)
    ready = client.post(
        f"/api/v1/parcels/{happy['id']}/ready", headers=ready_headers,
        json={"expected_version": happy["version"]},
    )
    assert ready.status_code == 200, ready.text
    ready_view = ready.json()
    ready_replay = client.post(
        f"/api/v1/parcels/{happy['id']}/ready", headers=ready_headers,
        json={"expected_version": happy["version"]},
    )
    assert ready_replay.status_code == 200
    assert ready_replay.json()["id"] == happy["id"]

    handover_headers = _headers(case, "security", "parcel-task5-happy-handover", correlation_id)
    handed = client.post(
        f"/api/v1/parcels/{happy['id']}/handover", headers=handover_headers,
        json={"expected_version": ready_view["version"], "pin": "1234"},
    )
    assert handed.status_code == 200, handed.text
    handed_view = handed.json()
    assert handed_view["status"] == "HANDED_OVER"
    assert handed_view["version"] == ready_view["version"] + 1
    handover_replay = client.post(
        f"/api/v1/parcels/{happy['id']}/handover", headers=handover_headers,
        json={"expected_version": ready_view["version"], "pin": "1234"},
    )
    assert handover_replay.status_code == 200
    assert handover_replay.json()["id"] == happy["id"]
    for field, value in snapshot.items():
        assert handed_view[field] == value, f"snapshot changed for {field}"

    exception_created, _ = _create(
        case, key="parcel-task5-exception-create", correlation_id=correlation_id,
    )
    assert exception_created.status_code == 201, exception_created.text
    exception_parcel = exception_created.json()
    exception = client.post(
        f"/api/v1/parcels/{exception_parcel['id']}/exception",
        headers=_headers(case, "security", "parcel-task5-exception", correlation_id),
        json={
            "expected_version": exception_parcel["version"],
            "status": "LOST",
            "reason": "Không tìm thấy trong locker sau ca trực.",
        },
    )
    assert exception.status_code == 200, exception.text
    exception_view = exception.json()
    assert exception_view["status"] == "LOST"
    exception_replay = client.post(
        f"/api/v1/parcels/{exception_parcel['id']}/exception",
        headers=_headers(case, "security", "parcel-task5-exception", correlation_id),
        json={
            "expected_version": exception_parcel["version"],
            "status": "LOST",
            "reason": "Không tìm thấy trong locker sau ca trực.",
        },
    )
    assert exception_replay.status_code == 200
    assert exception_replay.json()["version"] == exception_view["version"]

    opened = client.post(
        f"/api/v1/parcels/{exception_parcel['id']}/case",
        headers=_headers(case, "cskh", "parcel-task5-case", correlation_id),
        json={"reason": "Mở Case điều tra kiện thất lạc."},
    )
    assert opened.status_code == 201, opened.text
    case_view = opened.json()
    assert case_view["source_parcel_id"] == exception_parcel["id"]
    case_replay = client.post(
        f"/api/v1/parcels/{exception_parcel['id']}/case",
        headers=_headers(case, "cskh", "parcel-task5-case", correlation_id),
        json={"reason": "Mở Case điều tra kiện thất lạc."},
    )
    assert case_replay.status_code == 201
    assert case_replay.json()["id"] == case_view["id"]

    shift_start = datetime.now(UTC).replace(microsecond=0)
    shift = client.post(
        "/api/v1/security/shifts",
        headers=_headers(case, "director", "parcel-task5-shift", correlation_id),
        json={
            "building_id": str(case["building"].id),
            "assignee_id": str(case["accounts"]["security"].id),
            "scheduled_start_at": shift_start.isoformat(),
            "scheduled_end_at": (shift_start.replace(second=0) + timedelta(hours=2)).isoformat(),
            "patrol_windows": [{
                "patrol_point_id": str(case["patrol_point"].id),
                "window_start_at": shift_start.isoformat(),
                "window_end_at": (shift_start.replace(second=0) + timedelta(hours=1)).isoformat(),
            }],
        },
    )
    assert shift.status_code == 201, shift.text
    shift_view = shift.json()
    window_id = shift_view["patrol_windows"][0]["id"]
    incident = client.post(
        "/api/v1/security/incidents",
        headers=_headers(case, "security", "parcel-task5-incident", correlation_id),
        json={
            "patrol_window_id": window_id,
            "incident_type": "SECURITY",
            "severity": "LOW",
            "title": "Kiện thất lạc tại locker",
            "description": "Sự cố được ghi nhận trong ca trực để liên kết hồ sơ.",
            "occurred_at": shift_start.isoformat(),
        },
    )
    assert incident.status_code == 201, incident.text
    incident_id = incident.json()["id"]
    linked_headers = _headers(case, "security", "parcel-task5-incident-link", correlation_id)
    linked = client.post(
        f"/api/v1/parcels/{exception_parcel['id']}/incident-link",
        headers=linked_headers,
        json={"incident_id": incident_id},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["parcel_id"] == exception_parcel["id"]
    assert linked.json()["version"] == incident.json()["version"] + 1
    linked_replay = client.post(
        f"/api/v1/parcels/{exception_parcel['id']}/incident-link",
        headers=linked_headers,
        json={"incident_id": incident_id},
    )
    assert linked_replay.status_code == 200
    assert linked_replay.json()["id"] == incident_id

    png = b"\x89PNG\r\n\x1a\n" + b"task5-evidence" + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    evidence_headers = _headers(case, "security", "parcel-task5-evidence", correlation_id) | {
        "Content-Type": "image/png", "X-File-Name": "task5-locker.png",
    }
    uploaded = client.post(
        f"/api/v1/parcels/{exception_parcel['id']}/evidence",
        headers=evidence_headers, content=png,
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    replay_upload = client.post(
        f"/api/v1/parcels/{exception_parcel['id']}/evidence",
        headers=evidence_headers, content=png,
    )
    assert replay_upload.status_code == 201
    assert replay_upload.json()["id"] == attachment["id"]
    signed = client.get(
        f"/api/v1/parcels/{exception_parcel['id']}/evidence/{attachment['id']}/signed-link",
        headers=_headers(case, "cskh", correlation_id=correlation_id),
    )
    assert signed.status_code == 200, signed.text
    downloaded = client.get(signed.json()["url"], headers=_headers(case, "cskh", correlation_id=correlation_id))
    assert downloaded.status_code == 200
    assert downloaded.content == png
    assert downloaded.headers["cache-control"] == "private, no-store"

    timeline = client.get(
        f"/api/v1/parcels/{exception_parcel['id']}/timeline",
        headers=_headers(case, "cskh", correlation_id=correlation_id),
    )
    assert timeline.status_code == 200, timeline.text
    timeline_events = timeline.json()["items"]
    event_types = {item["event_type"] for item in timeline_events}
    assert {
        "ParcelReceived", "ParcelExceptionRecorded", "ParcelCaseOpened",
        "ParcelIncidentLinked", "ParcelEvidenceAdded",
        "ParcelAttachmentSignedLinkIssued", "ParcelAttachmentDownloaded",
    }.issubset(event_types)
    assert all(item["correlation_id"] == correlation_id for item in timeline_events if item["event_type"] != "ParcelReceived")

    with case["database"].get_session() as session:
        persisted_happy = session.get(Parcel, happy["id"])
        assert persisted_happy is not None
        for field, value in snapshot.items():
            persisted_value = getattr(persisted_happy, field)
            if field == "received_at":
                expected_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
                assert persisted_value.astimezone(UTC) == expected_at, f"SQL snapshot changed for {field}"
            else:
                assert str(persisted_value) == str(value), f"SQL snapshot changed for {field}"
        assert persisted_happy.status == "HANDED_OVER"
        assert session.scalar(select(func.count(Parcel.id)).where(
            Parcel.id.in_([happy["id"], exception_parcel["id"]]),
        )) == 2
        assert session.scalar(select(func.count(CaseRecord.id)).where(
            CaseRecord.source_parcel_id == exception_parcel["id"],
        )) == 1
        assert session.scalar(select(func.count(SecurityIncident.id)).where(
            SecurityIncident.parcel_id == exception_parcel["id"],
        )) == 1
        assert session.scalar(select(func.count(Attachment.id)).where(
            Attachment.parcel_id == exception_parcel["id"],
            Attachment.is_quarantined.is_(False),
        )) == 1
        for operation, key in (
            ("parcel.ready", "parcel-task5-happy-ready"),
            ("parcel.handover", "parcel-task5-happy-handover"),
            ("parcel.exception", "parcel-task5-exception"),
            ("parcel.case.create", "parcel-task5-case"),
            ("parcel.incident.link", "parcel-task5-incident-link"),
            ("parcel.evidence", "parcel-task5-evidence"),
        ):
            assert session.scalar(select(func.count(IdempotencyRecord.id)).where(
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.idempotency_key == key,
            )) == 1
