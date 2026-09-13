"""PostgreSQL acceptance evidence for the bounded R1 Unit import slice."""

from copy import deepcopy
import os
import secrets
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Database
from app.core.security import create_token, hash_password
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.platform import AuditEvent, DomainEvent, IdempotencyRecord
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit
from app.services.unit_import import IMPORT_OPERATION, IMPORT_RESOURCE_TYPE


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
        reason="Run scripts.test_isolated; Unit import tests require disposable PostgreSQL",
    ),
]


@pytest.fixture(scope="module")
def unit_import_case():
    settings = Settings()
    assert settings.app_env == "test"
    assert settings.sqlalchemy_url().host == "127.0.0.1"
    database = Database(settings)
    connection = database.engine.connect()
    transaction = connection.begin()
    database.sessions = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    password = secrets.token_urlsafe(24)
    with database.get_session() as session:
        tenant = Tenant(name=f"Unit import fixture {uuid4()}")
        foreign_tenant = Tenant(name=f"Foreign import fixture {uuid4()}")
        session.add_all((tenant, foreign_tenant))
        session.flush()
        west = Site(
            tenant_id=tenant.id,
            code=f"IMPORT-WEST-{uuid4().hex[:6]}",
            name="Import West",
            address="Synthetic",
        )
        east = Site(
            tenant_id=tenant.id,
            code=f"ZZ-IMPORT-EAST-{uuid4().hex[:6]}",
            name="Import East",
            address="Synthetic",
        )
        foreign_site = Site(
            tenant_id=foreign_tenant.id,
            code=f"IMPORT-FOREIGN-{uuid4().hex[:6]}",
            name="Foreign",
            address="Synthetic",
        )
        session.add_all((west, east, foreign_site))
        session.flush()
        buildings = {
            "B1": Building(site_id=west.id, code="B1", name="Permitted", floors_count=80),
            "B2": Building(site_id=west.id, code="B2", name="Other West", floors_count=80),
            "E1": Building(site_id=east.id, code="E1", name="East", floors_count=80),
            "F1": Building(site_id=foreign_site.id, code="F1", name="Foreign", floors_count=80),
        }
        session.add_all(buildings.values())
        session.flush()
        session.add_all(
            Unit(
                building_id=buildings["B1"].id,
                unit_number=f"EXIST-{number:04d}",
                floor=1,
                area_m2=50,
                status="occupied",
            )
            for number in range(1, 26)
        )
        hashed_password = hash_password(password)
        accounts = {
            "admin": Account(
                tenant_id=tenant.id,
                username=f"unit_import_admin_{uuid4().hex}",
                full_name="Unit import admin",
                hashed_password=hashed_password,
            ),
            "cskh": Account(
                tenant_id=tenant.id,
                username=f"unit_import_cskh_{uuid4().hex}",
                full_name="Unit import CSKH",
                hashed_password=hashed_password,
            ),
            "technician": Account(
                tenant_id=tenant.id,
                username=f"unit_import_tech_{uuid4().hex}",
                full_name="Unit import technician",
                hashed_password=hashed_password,
            ),
        }
        session.add_all(accounts.values())
        session.flush()
        session.add_all((
            AccountRole(account_id=accounts["admin"].id, role="admin", site_id=None),
            AccountRole(
                account_id=accounts["cskh"].id,
                role="cskh",
                site_id=west.id,
                building_id=buildings["B1"].id,
            ),
            AccountRole(
                account_id=accounts["technician"].id,
                role="technician",
                site_id=west.id,
                building_id=None,
            ),
        ))
        session.commit()

    app = create_app(settings, database)
    with TestClient(app) as client:
        auth = {}
        for label, account in accounts.items():
            response = client.post("/api/v1/auth/login", json={
                "username": account.username,
                "password": password,
            })
            assert response.status_code == 200
            auth[label] = {"Authorization": "Bearer " + response.json()["access_token"]}
        yield {
            "client": client,
            "database": database,
            "settings": settings,
            "tenant": tenant,
            "sites": {"west": west, "east": east},
            "buildings": buildings,
            "accounts": accounts,
            "auth": auth,
        }
    transaction.rollback()
    connection.close()
    database.close()


def with_key(case, actor: str, key: str):
    return case["auth"][actor] | {"Idempotency-Key": key}


def count_units(case, building_code: str) -> int:
    with case["database"].get_session() as session:
        return session.scalar(select(func.count(Unit.id)).where(
            Unit.building_id == case["buildings"][building_code].id,
        ))


def item(number: int, *, unit_number: str | None = None, **overrides):
    values = {
        "unit_number": unit_number if unit_number is not None else f"B1-{number:04d}",
        "floor": 1,
        "area_m2": 50.5,
        "status": "occupied",
    }
    values.update(overrides)
    return values


def thousand_row_payload():
    items = [item(number) for number in range(1, 901)]
    items.extend(item(number, unit_number=f" b1-{number:04d} ") for number in range(901, 926))
    items.extend(item(number, unit_number=f"B1-{number:04d}") for number in range(1, 26))
    items.extend(item(number, unit_number=f"EXIST-{number:04d}") for number in range(1, 26))
    items.extend(item(number, unit_number="") for number in range(1, 6))
    items.extend(item(number, floor=0) for number in range(1, 6))
    items.extend(item(number, status="not-a-status") for number in range(1, 6))
    items.extend(item(number, area_m2=-1) for number in range(1, 6))
    items.extend(item(number, floor=81) for number in range(1, 6))
    assert len(items) == 1000
    return {"building_code": "B1", "mode": "partial", "items": items}


def test_bulk_unit_import_has_exact_1000_row_results_and_idempotent_retry(unit_import_case):
    case = unit_import_case
    payload = thousand_row_payload()
    before = count_units(case, "B1")
    response = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "admin", "unit-import-1000-a"),
        json=payload,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "APPLIED"
    assert body["mode"] == "partial"
    assert (body["total_rows"], body["applied_rows"], body["skipped_rows"],
            body["warning_rows"], body["error_rows"]) == (1000, 925, 50, 75, 25)
    assert len(body["items"]) == 1000
    assert [result["row_number"] for result in body["items"]] == list(range(1, 1001))
    assert body["items"][0] == {
        "row_number": 1, "status": "IMPORTED", "code": "OK", "column": None, "message": None,
    }
    assert body["items"][900]["status"] == "IMPORTED"
    assert body["items"][900]["code"] == "WARN-NORMALIZED"
    assert body["items"][925] == {
        "row_number": 926,
        "status": "SKIPPED",
        "code": "WARN-DUPLICATE-IN-BATCH",
        "column": "unit_number",
        "message": "Mã căn trùng trong cùng lô nhập.",
    }
    assert body["items"][950]["status"] == "SKIPPED"
    assert body["items"][950]["code"] == "WARN-ALREADY-EXISTS"
    error_columns = {
        result["column"]
        for result in body["items"]
        if result["status"] == "ERROR"
    }
    assert error_columns == {"unit_number", "floor", "status", "area_m2"}
    for result in body["items"][975:]:
        assert result["status"] == "ERROR"
        assert result["code"] == "ERR-IMPORT-ROW"
        assert result["column"]
        assert result["message"]
    assert count_units(case, "B1") == before + 925

    replay = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "admin", "unit-import-1000-a"),
        json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == body
    assert count_units(case, "B1") == before + 925

    changed = deepcopy(payload)
    changed["items"][0]["floor"] = 2
    conflict = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "admin", "unit-import-1000-a"),
        json=changed,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ERR-CONFLICT"
    assert count_units(case, "B1") == before + 925

    repeat_with_new_key = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "admin", "unit-import-1000-b"),
        json=payload,
    )
    assert repeat_with_new_key.status_code == 200, repeat_with_new_key.text
    assert repeat_with_new_key.json()["applied_rows"] == 0
    assert repeat_with_new_key.json()["error_rows"] == 25
    assert count_units(case, "B1") == before + 925

    receipt_id = UUID(body["receipt_id"])
    with case["database"].get_session() as session:
        assert session.scalar(select(func.count(IdempotencyRecord.id)).where(
            IdempotencyRecord.operation == IMPORT_OPERATION,
            IdempotencyRecord.idempotency_key == "unit-import-1000-a",
        )) == 1
        audit = session.scalar(select(AuditEvent).where(
            AuditEvent.resource_type == IMPORT_RESOURCE_TYPE,
            AuditEvent.resource_id == receipt_id,
        ))
        event = session.scalar(select(DomainEvent).where(
            DomainEvent.resource_type == IMPORT_RESOURCE_TYPE,
            DomainEvent.resource_id == receipt_id,
        ))
        assert audit is not None
        assert audit.tenant_id == case["tenant"].id
        assert audit.site_id == case["sites"]["west"].id
        assert audit.after_data["applied_rows"] == 925
        assert event is not None
        assert event.event_type == "ImportRunCompleted"
        assert event.payload["error_rows"] == 25


def test_all_or_nothing_rejects_without_writes_and_replays_receipt(unit_import_case):
    case = unit_import_case
    before = count_units(case, "B1")
    payload = {
        "building_code": "B1",
        "mode": "all_or_nothing",
        "items": [item(1, unit_number="ATOMIC-0001"), item(2, unit_number="ATOMIC-0002", floor=0),
                  item(3, unit_number="ATOMIC-0003")],
    }
    response = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "admin", "unit-import-atomic-01"),
        json=payload,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "REJECTED"
    assert (body["applied_rows"], body["skipped_rows"], body["error_rows"]) == (0, 0, 1)
    assert [result["status"] for result in body["items"]] == ["VALIDATED", "ERROR", "VALIDATED"]
    assert count_units(case, "B1") == before
    replay = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "admin", "unit-import-atomic-01"),
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json() == body
    assert count_units(case, "B1") == before


def test_import_scope_and_payload_cannot_be_spoofed(unit_import_case):
    case = unit_import_case
    b1_before = count_units(case, "B1")
    b2_before = count_units(case, "B2")
    out_of_scope = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "cskh", "unit-import-cskh-b2"),
        json={"building_code": "B2", "mode": "partial", "items": [item(1)]},
    )
    assert out_of_scope.status_code == 404
    assert out_of_scope.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    assert count_units(case, "B2") == b2_before

    allowed = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "cskh", "unit-import-cskh-b1"),
        json={"building_code": "B1", "mode": "partial", "items": [item(1, unit_number="CSKH-0001")]},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["applied_rows"] == 1
    assert count_units(case, "B1") == b1_before + 1

    payload = {"building_code": "B1", "mode": "partial", "items": [item(1, unit_number="SPOOF-0001")]}
    for key, value in (("tenant_id", str(uuid4())), ("site_id", str(uuid4())),
                       ("building_id", str(uuid4())), ("role", "admin")):
        rejected = case["client"].post(
            "/api/v1/units/import",
            headers=with_key(case, "cskh", f"unit-import-spoof-{key}"),
            json=payload | {key: value},
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "ERR-VALIDATION"
    row_extra = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "cskh", "unit-import-spoof-row"),
        json=payload | {"items": [payload["items"][0] | {"role": "admin"}]},
    )
    assert row_extra.status_code == 422
    assert row_extra.json()["error"]["code"] == "ERR-VALIDATION"
    assert count_units(case, "B1") == b1_before + 1

    forged_headers = {
        "Authorization": "Bearer " + create_token({
            "sub": str(case["accounts"]["cskh"].id),
            "tenant_id": str(uuid4()),
            "roles": ["admin"],
            "active_site_id": str(case["sites"]["west"].id),
            "purpose": "session",
        }, case["settings"].auth_secret()),
        "Idempotency-Key": "unit-import-forged-b2",
    }
    forged = case["client"].post(
        "/api/v1/units/import",
        headers=forged_headers,
        json={"building_code": "B2", "mode": "partial", "items": [item(1)]},
    )
    assert forged.status_code == 404
    assert forged.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    assert count_units(case, "B2") == b2_before

    technician = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "technician", "unit-import-tech-0001"),
        json={"building_code": "B1", "mode": "partial", "items": [item(1)]},
    )
    assert technician.status_code == 403
    assert technician.json()["error"]["code"] == "ERR-FORBIDDEN"


def test_admin_must_switch_active_site_before_importing_another_site(unit_import_case):
    case = unit_import_case
    east_before = count_units(case, "E1")
    denied = case["client"].post(
        "/api/v1/units/import",
        headers=with_key(case, "admin", "unit-import-admin-east-1"),
        json={"building_code": "E1", "mode": "partial", "items": [item(1, unit_number="E1-0001")]},
    )
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    switched = case["client"].post(
        "/api/v1/auth/switch-site",
        headers=case["auth"]["admin"],
        json={"site_id": str(case["sites"]["east"].id)},
    )
    assert switched.status_code == 200
    east_token = {"Authorization": "Bearer " + switched.json()["access_token"],
                  "Idempotency-Key": "unit-import-admin-east-2"}
    allowed = case["client"].post(
        "/api/v1/units/import",
        headers=east_token,
        json={"building_code": "E1", "mode": "partial", "items": [item(1, unit_number="E1-0001")]},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["applied_rows"] == 1
    assert count_units(case, "E1") == east_before + 1
