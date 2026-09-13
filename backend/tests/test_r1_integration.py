from datetime import date
from decimal import Decimal
import os
from threading import Event, Thread
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.models.person import Person, UnitPersonRelationship
from app.models.building import Building
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DB_INTEGRATION") != "1",
        reason="Set RUN_DB_INTEGRATION=1 explicitly to run against seeded PostgreSQL",
    ),
]


@pytest.fixture(scope="module")
def app_client():
    settings = Settings()
    db = Database(settings)
    app = create_app(settings, db)
    with TestClient(app) as client:
        yield client, db
    db.close()


def test_login_success(app_client):
    client, _ = app_client
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "cskh_west", "password": "Password@123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert data["user"]["username"] == "cskh_west"
    assert "cskh" in data["user"]["roles"]
    assert data["user"]["active_site_id"] is not None


def test_login_invalid_credentials_returns_401(app_client):
    client, _ = app_client
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "cskh_west", "password": "WrongPassword999"},
    )
    assert response.status_code == 401
    err = response.json()["error"]
    assert err["code"] == "ERR-UNAUTHORIZED"
    assert "chính xác" in err["message"]
    assert "correlation_id" in err


def test_get_me_with_valid_token(app_client):
    client, _ = app_client
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "cskh_west", "password": "Password@123"},
    )
    token = login_resp.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    user = response.json()
    assert user["username"] == "cskh_west"
    assert "cskh" in user["roles"]
    assert len(user["allowed_sites"]) == 1
    assert user["allowed_sites"][0]["code"] == "GC-WEST"


def test_unit_360_same_site_success(app_client):
    client, db = app_client
    # 1. Login as CSKH West
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "cskh_west", "password": "Password@123"},
    )
    token = login_resp.json()["access_token"]

    # 2. Get unit W1-0101 ID from database
    with db.get_session() as session:
        unit = session.execute(
            select(Unit).where(Unit.unit_number == "W1-0101")
        ).scalar_one()
        unit_id = unit.id

    # 3. Request Unit 360
    response = client.get(
        f"/api/v1/units/{unit_id}/360",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["unit_number"] == "W1-0101"
    assert body["building_code"] == "W1"
    assert body["site_code"] == "GC-WEST"
    assert len(body["residents"]) == 1
    assert body["residents"][0]["full_name"] == "Nguyễn Văn An"
    assert body["residents"][0]["phone_masked"] == "090***0001"
    assert body["residents"][0]["relationship_type"] == "owner"
    assert body["residents"][0]["ownership_ratio"] == "1.0000"
    assert body["residents"][0]["valid_from"] == "2025-01-01"
    assert body["residents"][0]["valid_to"] is None


def test_ac03_person_owns_two_units_and_rents_a_third_bidirectionally(app_client):
    client, db = app_client
    token = client.post(
        "/api/v1/auth/login",
        json={"username": "cskh_west", "password": "Password@123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with db.get_session() as session:
        person = session.scalar(select(Person).where(Person.phone_masked == "090***0001"))
        units = {
            unit.unit_number: unit.id
            for unit in session.scalars(select(Unit).where(
                Unit.unit_number.in_(("W1-0101", "W1-0102", "W1-0103"))
            ))
        }

    response = client.get(
        f"/api/v1/persons/{person.id}/units?as_of=2025-06-01",
        headers=headers,
    )
    assert response.status_code == 200
    items = {item["unit_number"]: item for item in response.json()["items"]}
    assert set(items) == {"W1-0101", "W1-0102", "W1-0103"}
    assert items["W1-0101"]["relationship_type"] == "owner"
    assert items["W1-0101"]["ownership_ratio"] == "1.0000"
    assert items["W1-0102"]["relationship_type"] == "owner"
    assert items["W1-0102"]["ownership_ratio"] == "0.5000"
    assert items["W1-0103"]["relationship_type"] == "tenant"
    assert items["W1-0103"]["ownership_ratio"] is None
    assert all(item["valid_from"] == "2025-01-01" for item in items.values())
    assert all(item["valid_to"] is None for item in items.values())

    for unit_number, unit_id in units.items():
        unit_response = client.get(
            f"/api/v1/units/{unit_id}/360?as_of=2025-06-01",
            headers=headers,
        )
        assert unit_response.status_code == 200
        relation = next(
            resident for resident in unit_response.json()["residents"]
            if resident["person_id"] == str(person.id)
        )
        assert relation["relationship_type"] == items[unit_number]["relationship_type"]
        assert relation["ownership_ratio"] == items[unit_number]["ownership_ratio"]

    before_effective = client.get(
        f"/api/v1/units/{units['W1-0101']}/360?as_of=2024-12-31",
        headers=headers,
    )
    assert before_effective.status_code == 200
    assert before_effective.json()["residents"] == []


def test_ac03_person_lookup_enforces_role_and_site_scope(app_client):
    client, db = app_client
    with db.get_session() as session:
        person_id = session.scalar(select(Person.id).where(Person.phone_masked == "090***0001"))

    for username, expected_status, expected_code in (
        ("cskh_east", 404, "ERR-SCOPE-NOTFOUND"),
        ("techlead_west", 403, "ERR-FORBIDDEN"),
    ):
        token = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "Password@123"},
        ).json()["access_token"]
        response = client.get(
            f"/api/v1/persons/{person_id}/units?as_of=2025-06-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == expected_status
        assert response.json()["error"]["code"] == expected_code


def test_ac03_postgres_rejects_ownership_overflow_and_cross_tenant(app_client):
    _, db = app_client
    with db.get_session() as session:
        west_unit = session.scalar(select(Unit).where(Unit.unit_number == "W1-0101"))
        other_person = session.scalar(select(Person).where(Person.phone_masked == "090***0002"))
        session.add(UnitPersonRelationship(
            unit_id=west_unit.id,
            person_id=other_person.id,
            relationship_type="owner",
            ownership_ratio=Decimal("0.0001"),
            valid_from=date(2025, 1, 1),
        ))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    with db.get_session() as session:
        west_unit = session.scalar(select(Unit).where(Unit.unit_number == "W1-0101"))
        foreign_tenant = Tenant(name="AC-03 foreign tenant")
        session.add(foreign_tenant)
        session.flush()
        foreign_person = Person(
            tenant_id=foreign_tenant.id,
            full_name="Scoped fixture",
            phone_masked="000***0000",
            email_masked="scope***@example.invalid",
        )
        session.add(foreign_person)
        session.flush()
        session.add(UnitPersonRelationship(
            unit_id=west_unit.id,
            person_id=foreign_person.id,
            relationship_type="tenant",
            ownership_ratio=None,
            valid_from=date(2025, 1, 1),
        ))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_ac03_postgres_rejects_overlapping_episodes_and_parent_tenant_moves(app_client):
    _, db = app_client
    with db.get_session() as session:
        unit = session.scalar(select(Unit).where(Unit.unit_number == "W1-0101"))
        person = session.scalar(select(Person).where(Person.phone_masked == "090***0002"))
        session.add(UnitPersonRelationship(
            unit_id=unit.id,
            person_id=person.id,
            relationship_type="family_member",
            ownership_ratio=None,
            valid_from=date(2025, 1, 1),
            valid_to=date(2025, 2, 1),
        ))
        session.flush()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(UnitPersonRelationship(
                    unit_id=unit.id,
                    person_id=person.id,
                    relationship_type="family_member",
                    ownership_ratio=None,
                    valid_from=date(2025, 1, 15),
                    valid_to=date(2025, 3, 1),
                ))
                session.flush()
        # The half-open boundary is allowed: [Jan, Feb) followed by [Feb, ...).
        session.add(UnitPersonRelationship(
            unit_id=unit.id,
            person_id=person.id,
            relationship_type="family_member",
            ownership_ratio=None,
            valid_from=date(2025, 2, 1),
        ))
        session.flush()
        session.rollback()

    with db.get_session() as session:
        linked_person = session.scalar(select(Person).where(Person.phone_masked == "090***0001"))
        foreign_tenant = Tenant(name="AC-03 parent-move tenant")
        session.add(foreign_tenant)
        session.flush()
        linked_person.tenant_id = foreign_tenant.id
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    with db.get_session() as session:
        site = session.scalar(select(Site).where(Site.code == "GC-WEST"))
        foreign_tenant = Tenant(name="AC-03 site-move tenant")
        session.add(foreign_tenant)
        session.flush()
        site.tenant_id = foreign_tenant.id
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_ac03_relationship_scope_is_database_derived_and_immutable(app_client):
    _, db = app_client
    relationship_id = None
    foreign_tenant_id = None
    try:
        with db.get_session() as session:
            unit = session.scalar(select(Unit).where(Unit.unit_number == "W1-0101"))
            person = session.scalar(select(Person).where(Person.phone_masked == "090***0002"))
            foreign_tenant = Tenant(name="AC-03 scope-derived tenant")
            session.add(foreign_tenant)
            session.flush()
            relation = UnitPersonRelationship(
                unit_id=unit.id,
                person_id=person.id,
                relationship_type="family_member",
                ownership_ratio=None,
                valid_from=date(2030, 1, 1),
            )
            session.add(relation)
            session.commit()
            session.refresh(relation)
            relationship_id = relation.id
            foreign_tenant_id = foreign_tenant.id
            assert (relation.tenant_id, relation.site_id, relation.building_id) == (
                person.tenant_id,
                unit.building.site_id,
                unit.building_id,
            )

        with db.get_session() as session:
            relation = session.get(UnitPersonRelationship, relationship_id)
            relation.tenant_id = foreign_tenant_id
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()
    finally:
        with db.get_session() as session:
            if relationship_id is not None:
                session.execute(delete(UnitPersonRelationship).where(
                    UnitPersonRelationship.id == relationship_id,
                ))
            if foreign_tenant_id is not None:
                session.execute(delete(Tenant).where(Tenant.id == foreign_tenant_id))
            session.commit()


def test_ac03_concurrent_parent_move_cannot_bypass_relationship_scope(app_client):
    _, db = app_client
    relationship_id = None
    foreign_tenant_id = None
    original_tenant_id = None
    person_id = None
    connection = None
    transaction = None
    relationship_session = None
    try:
        with db.get_session() as session:
            unit = session.scalar(select(Unit).where(Unit.unit_number == "W1-0101"))
            person = session.scalar(select(Person).where(Person.phone_masked == "090***0002"))
            original_tenant_id = person.tenant_id
            foreign_tenant = Tenant(name="AC-03 concurrent-move tenant")
            session.add(foreign_tenant)
            session.commit()
            foreign_tenant_id = foreign_tenant.id
            unit_id = unit.id
            person_id = person.id

        connection = db.engine.connect()
        transaction = connection.begin()
        relationship_session = Session(bind=connection, expire_on_commit=False)
        relation = UnitPersonRelationship(
            unit_id=unit_id,
            person_id=person_id,
            relationship_type="family_member",
            ownership_ratio=None,
            valid_from=date(2031, 1, 1),
        )
        relationship_session.add(relation)
        relationship_session.flush()
        relationship_id = relation.id

        move_started = Event()
        move_finished = Event()
        move_result = {}

        def move_person_to_other_tenant():
            try:
                with db.engine.connect() as concurrent_connection:
                    concurrent_transaction = concurrent_connection.begin()
                    try:
                        concurrent_connection.execute(text("SET LOCAL lock_timeout = '300ms'"))
                        move_started.set()
                        concurrent_connection.execute(text(
                            "UPDATE greencity.persons SET tenant_id = :tenant_id WHERE id = :person_id"
                        ), {"tenant_id": foreign_tenant_id, "person_id": person_id})
                        concurrent_transaction.commit()
                        move_result["committed"] = True
                    except Exception as error:
                        concurrent_transaction.rollback()
                        move_result["error"] = error
            finally:
                move_finished.set()

        mover = Thread(target=move_person_to_other_tenant, daemon=True)
        mover.start()
        assert move_started.wait(timeout=1)
        assert move_finished.wait(timeout=3)
        assert "error" in move_result, "Parent tenant update must wait for the relationship insert."

        transaction.commit()
        transaction = None
        relationship_session.close()
        relationship_session = None

        with db.get_session() as session:
            person = session.get(Person, person_id)
            person.tenant_id = foreign_tenant_id
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()
    finally:
        if relationship_session is not None:
            relationship_session.close()
        if transaction is not None and transaction.is_active:
            transaction.rollback()
        if connection is not None:
            connection.close()
        with db.get_session() as session:
            if relationship_id is not None:
                session.execute(delete(UnitPersonRelationship).where(
                    UnitPersonRelationship.id == relationship_id,
                ))
            if original_tenant_id is not None and person_id is not None:
                session.execute(text(
                    "UPDATE greencity.persons SET tenant_id = :tenant_id WHERE id = :person_id"
                ), {"tenant_id": original_tenant_id, "person_id": person_id})
            if foreign_tenant_id is not None:
                session.execute(delete(Tenant).where(Tenant.id == foreign_tenant_id))
            session.commit()


def test_ac03_temporal_scope_hides_expired_and_other_building_relationships(app_client):
    client, db = app_client
    token = client.post(
        "/api/v1/auth/login",
        json={"username": "cskh_west", "password": "Password@123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    created_relation_ids = []
    hidden_building_id = None
    with db.get_session() as session:
        west_site = session.scalar(select(Site).where(Site.code == "GC-WEST"))
        person = session.scalar(select(Person).where(Person.phone_masked == "090***0002"))
        unit = session.scalar(select(Unit).where(Unit.unit_number == "W1-0101"))
        hidden_building = Building(site_id=west_site.id, code="W2-AC03", name="Hidden AC-03", floors_count=2)
        session.add(hidden_building)
        session.flush()
        hidden_unit = Unit(
            building_id=hidden_building.id,
            unit_number="W2-0101",
            floor=1,
            area_m2=50,
            status="occupied",
        )
        session.add(hidden_unit)
        session.flush()
        expired_relation = UnitPersonRelationship(
            unit_id=unit.id,
            person_id=person.id,
            relationship_type="family_member",
            ownership_ratio=None,
            valid_from=date(2025, 1, 1),
            valid_to=date(2025, 2, 1),
        )
        hidden_relation = UnitPersonRelationship(
            unit_id=hidden_unit.id,
            person_id=person.id,
            relationship_type="tenant",
            ownership_ratio=None,
            valid_from=date(2025, 1, 1),
        )
        session.add_all((expired_relation, hidden_relation))
        session.flush()
        created_relation_ids = [expired_relation.id, hidden_relation.id]
        session.commit()
        person_id = person.id
        unit_id = unit.id
        hidden_building_id = hidden_building.id

    try:
        at_boundary = client.get(
            f"/api/v1/persons/{person_id}/units?as_of=2025-02-01", headers=headers,
        )
        assert at_boundary.status_code == 404
        assert at_boundary.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
        detail = client.get(f"/api/v1/units/{unit_id}/360?as_of=2025-02-01", headers=headers)
        assert detail.status_code == 200
        assert all(resident["person_id"] != str(person_id) for resident in detail.json()["residents"])

        before_boundary = client.get(
            f"/api/v1/persons/{person_id}/units?as_of=2025-01-31", headers=headers,
        )
        assert before_boundary.status_code == 200
        assert [item["unit_number"] for item in before_boundary.json()["items"]] == ["W1-0101"]
    finally:
        with db.get_session() as session:
            session.execute(delete(UnitPersonRelationship).where(
                UnitPersonRelationship.id.in_(created_relation_ids),
            ))
            session.execute(delete(Building).where(Building.id == hidden_building_id))
            session.commit()


def test_unit_360_cross_site_isolation_strictly_returns_404(app_client):
    """
    CRITICAL SECURITY CHECK (Plan 2):
    CSKH East attempts to query unit W1-0101 which belongs to Site West.
    Must return 404 ERR-SCOPE-NOTFOUND (not 200, not 403) to prevent existence leakage.
    """
    client, db = app_client
    # 1. Login as CSKH East (assigned ONLY to Site East)
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "cskh_east", "password": "Password@123"},
    )
    token = login_resp.json()["access_token"]

    # 2. Get unit W1-0101 ID (Site West)
    with db.get_session() as session:
        unit_west = session.execute(
            select(Unit).where(Unit.unit_number == "W1-0101")
        ).scalar_one()
        unit_west_id = unit_west.id

    # 3. Cross-site request
    response = client.get(
        f"/api/v1/units/{unit_west_id}/360",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    err = response.json()["error"]
    assert err["code"] == "ERR-SCOPE-NOTFOUND"


def test_admin_can_access_both_sites(app_client):
    client, db = app_client
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin_demo", "password": "Password@123"},
    )
    token = login_resp.json()["access_token"]

    with db.get_session() as session:
        unit_west = session.execute(select(Unit).where(Unit.unit_number == "W1-0101")).scalar_one()
        unit_east = session.execute(select(Unit).where(Unit.unit_number == "E1-0201")).scalar_one()
        west_site_id = unit_west.building.site_id
        east_site_id = unit_east.building.site_id

    # Active scope is mandatory even for tenant Admin: switch before each read.
    switch = client.post("/api/v1/auth/switch-site",
                         json={"site_id": str(west_site_id)},
                         headers={"Authorization": f"Bearer {token}"})
    assert switch.status_code == 200
    token = switch.json()["access_token"]
    # Query West
    resp_west = client.get(
        f"/api/v1/units/{unit_west.id}/360",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_west.status_code == 200
    assert resp_west.json()["site_code"] == "GC-WEST"

    switch = client.post("/api/v1/auth/switch-site",
                         json={"site_id": str(east_site_id)},
                         headers={"Authorization": f"Bearer {token}"})
    assert switch.status_code == 200
    token = switch.json()["access_token"]
    # Query East
    resp_east = client.get(
        f"/api/v1/units/{unit_east.id}/360",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_east.status_code == 200
    assert resp_east.json()["site_code"] == "GC-EAST"


def test_switch_site_scope_enforcement(app_client):
    client, db = app_client
    with db.get_session() as session:
        site_east = session.execute(select(Site).where(Site.code == "GC-EAST")).scalar_one()

    # 1. Admin can switch to Site East
    admin_login = client.post("/api/v1/auth/login", json={"username": "admin_demo", "password": "Password@123"})
    admin_token = admin_login.json()["access_token"]
    switch_resp = client.post(
        "/api/v1/auth/switch-site",
        json={"site_id": str(site_east.id)},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert switch_resp.status_code == 200
    assert switch_resp.json()["user"]["active_site_id"] == str(site_east.id)

    # 2. CSKH West CANNOT switch to Site East (must return 404 ERR-SCOPE-NOTFOUND)
    cskh_login = client.post("/api/v1/auth/login", json={"username": "cskh_west", "password": "Password@123"})
    cskh_token = cskh_login.json()["access_token"]
    forbidden_switch = client.post(
        "/api/v1/auth/switch-site",
        json={"site_id": str(site_east.id)},
        headers={"Authorization": f"Bearer {cskh_token}"},
    )
    assert forbidden_switch.status_code == 404
    assert forbidden_switch.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
