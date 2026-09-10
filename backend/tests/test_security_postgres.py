"""Actual PostgreSQL + HTTP/auth; only the disposable cluster runner enables these."""
import os
import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Database
from app.core.security import create_token, hash_password
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.person import Person, UnitPersonRelationship
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; never use shared seed data for security fixtures",
)]


@pytest.fixture
def case():
    settings = Settings()
    assert settings.app_env == "test"
    assert settings.sqlalchemy_url().host == "127.0.0.1"
    database = Database(settings)
    connection = database.engine.connect()
    transaction = connection.begin()
    database.sessions = sessionmaker(bind=connection, expire_on_commit=False,
                                     join_transaction_mode="create_savepoint")
    password = secrets.token_urlsafe(24)
    with database.get_session() as session:
        tenants = [Tenant(name=f"Security fixture {uuid4()}") for _ in range(2)]
        session.add_all(tenants)
        session.flush()
        sites = [Site(tenant_id=tenants[0 if i < 2 else 1].id, code=f"S{i}",
                      name="Fixture", address="Synthetic") for i in range(3)]
        session.add_all(sites)
        session.flush()
        buildings = [Building(site_id=site.id, code="B", name="Fixture") for site in sites]
        session.add_all(buildings)
        session.flush()
        units = [Unit(building_id=b.id, unit_number="SAME-CODE", floor=1,
                      area_m2=50, status="occupied") for b in buildings]
        session.add_all(units)
        accounts = [Account(tenant_id=tenants[0].id, username=f"fixture_{uuid4().hex}",
                            full_name="Synthetic", hashed_password=hash_password(password))
                    for _ in range(3)]
        session.add_all(accounts)
        session.flush()
        session.add_all([
            AccountRole(account_id=accounts[0].id, role="admin", site_id=None),
            AccountRole(account_id=accounts[1].id, role="cskh", site_id=sites[0].id,
                        building_id=buildings[0].id),
            AccountRole(account_id=accounts[2].id, role="admin", site_id=sites[0].id),
            AccountRole(account_id=accounts[2].id, role="cleaning", site_id=sites[1].id),
        ])
        people = [Person(tenant_id=t.id, full_name=f"Synthetic tenant {i}",
                         phone_masked="***", email_masked="***@example.invalid")
                  for i, t in enumerate(tenants)]
        session.add_all(people)
        session.flush()
        session.add_all([UnitPersonRelationship(unit_id=units[0].id, person_id=p.id)
                         for p in people])  # Deliberately inconsistent foreign-tenant relation.
        session.commit()
    with TestClient(create_app(settings, database)) as client:
        yield client, database, settings, password, accounts, sites, units, people
    transaction.rollback()
    connection.close()
    database.close()


def login(case, index=0):
    client, _, _, password, accounts, *_ = case
    response = client.post("/api/v1/auth/login", json={
        "username": accounts[index].username, "password": password,
    })
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def assert_scoped_404(response):
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "ERR-SCOPE-NOTFOUND"
    assert error["message"] == "Không tìm thấy dữ liệu."
    assert error["correlation_id"] == response.headers["x-correlation-id"]


def test_postgres_tls_and_head(case):
    with case[1].engine.connect() as connection:
        assert connection.scalar(text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"))
        assert connection.scalar(text("SELECT version_num FROM greencity.alembic_version")) == "0003"


def test_seed_repeat_keeps_expected_counts(case):
    # Separate connection cannot see the fixture's uncommitted transaction.
    expected = {"tenants": 1, "sites": 2, "buildings": 2, "units": 2,
                "persons": 2, "unit_person_relationships": 2, "accounts": 9, "account_roles": 9}
    with case[1].engine.connect() as connection:
        for table, count in expected.items():
            assert connection.scalar(text(f"SELECT count(*) FROM greencity.{table}")) == count


def test_admin_cannot_read_foreign_tenant_or_inactive_site(case):
    client, _, _, _, _, _, units, _ = case
    headers = login(case)
    assert client.get(f"/api/v1/units/{units[0].id}/360", headers=headers).status_code == 200
    for target in (units[1].id, units[2].id, uuid4()):
        assert_scoped_404(client.get(f"/api/v1/units/{target}/360", headers=headers))


def test_switch_requires_real_tenant_membership_and_refreshes_roles(case):
    client, _, _, _, _, sites, units, _ = case
    headers = login(case, 2)
    for target in (sites[2].id, uuid4()):
        assert_scoped_404(client.post("/api/v1/auth/switch-site", json={"site_id": str(target)}, headers=headers))
    response = client.post("/api/v1/auth/switch-site", json={"site_id": str(sites[1].id)}, headers=headers)
    assert response.status_code == 200
    assert response.json()["user"]["roles"] == ["cleaning"]
    # Tenant Admin retains legitimate access after explicitly switching.
    response = client.post("/api/v1/auth/switch-site", json={"site_id": str(sites[1].id)}, headers=login(case))
    assert response.status_code == 200
    fresh = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert client.get(f"/api/v1/units/{units[1].id}/360", headers=fresh).status_code == 200
    assert_scoped_404(client.get(f"/api/v1/units/{units[0].id}/360", headers=fresh))


def test_bad_cross_tenant_grant_never_enters_me_or_login(case):
    client, database, _, _, accounts, sites, _, _ = case
    with database.get_session() as session:
        session.add(AccountRole(account_id=accounts[1].id, role="admin", site_id=sites[2].id))
        session.commit()
    headers = login(case, 1)
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["roles"] == ["cskh"]
    assert [s["id"] for s in response.json()["allowed_sites"]] == [str(sites[0].id)]
    assert_scoped_404(client.post("/api/v1/auth/switch-site", json={"site_id": str(sites[2].id)}, headers=headers))


def test_foreign_tenant_person_never_serialized(case):
    client, _, _, _, _, _, units, people = case
    response = client.get(f"/api/v1/units/{units[0].id}/360", headers=login(case))
    assert response.status_code == 200
    assert [p["person_id"] for p in response.json()["residents"]] == [str(people[0].id)]
    assert str(people[1].id) not in response.text


def test_revoked_membership_and_disabled_account_are_rechecked(case):
    client, database, _, _, accounts, _, units, _ = case
    headers = login(case, 1)
    with database.get_session() as session:
        for grant in session.scalars(select(AccountRole).where(AccountRole.account_id == accounts[1].id)):
            session.delete(grant)
        session.commit()
    assert_scoped_404(client.get(f"/api/v1/units/{units[0].id}/360", headers=headers))
    with database.get_session() as session:
        session.get(Account, accounts[1].id).is_active = False
        session.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_claims_never_override_database_identity_or_scope(case):
    client, _, settings, _, accounts, sites, units, _ = case
    claims = {"sub": str(accounts[1].id), "tenant_id": str(uuid4()),
              "roles": ["admin"], "active_site_id": str(sites[0].id)}
    headers = {"Authorization": "Bearer " + create_token(claims, settings.auth_secret())}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(accounts[1].tenant_id)
    assert response.json()["roles"] == ["cskh"]
    claims["active_site_id"] = str(sites[2].id)
    headers = {"Authorization": "Bearer " + create_token(claims, settings.auth_secret())}
    assert_scoped_404(client.get(f"/api/v1/units/{units[2].id}/360", headers=headers))


def test_unauthenticated_and_invalid_input_use_stable_errors(case):
    client = case[0]
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get(f"/api/v1/units/{uuid4()}/360").status_code == 401
    response = client.get("/api/v1/units/not-a-uuid/360", headers=login(case))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ERR-VALIDATION"


# SEC-02: per-role building scope and target-specific field projection.
def set_grants(case, grants):
    database, account = case[1], case[4][1]
    with database.get_session() as session:
        for old in session.scalars(select(AccountRole).where(AccountRole.account_id == account.id)):
            session.delete(old)
        session.flush()
        session.add_all(AccountRole(account_id=account.id, role=role, site_id=site, building_id=building)
                        for role, site, building in grants)
        session.commit()


@pytest.fixture
def same_site_other_building(case):
    with case[1].get_session() as session:
        building = Building(site_id=case[5][0].id, code="B2", name="Other building same site")
        session.add(building)
        session.flush()
        unit = Unit(building_id=building.id, unit_number="OTHER", floor=2, area_m2=75, status="occupied")
        session.add(unit)
        session.flush()
        session.add(UnitPersonRelationship(unit_id=unit.id, person_id=case[7][0].id))
        session.commit()
        return building, unit


@pytest.mark.parametrize("role,status,residents", [
    ("admin", 200, True), ("director", 200, True), ("cskh", 200, True),
    ("accountant", 200, True), ("technical_lead", 200, False), ("security", 200, False),
    ("technician", 404, None), ("cleaning", 403, None), ("auditor", 403, None),
    ("unknown", 403, None),
])
def test_unit_role_matrix(case, role, status, residents):
    unit = case[6][0]
    set_grants(case, [(role, case[5][0].id, unit.building_id)])
    response = case[0].get(f"/api/v1/units/{unit.id}/360", headers=login(case, 1))
    assert response.status_code == status
    if status == 200:
        data = response.json()
        assert data["residents_visible"] is residents
        if residents:
            assert [p["person_id"] for p in data["residents"]] == [str(case[7][0].id)]
        else:
            assert data["residents"] == []
            assert str(case[7][0].id) not in response.text
        if role == "security":
            assert data["area_m2"] is None
            assert data["status"] is None
        else:
            assert data["area_m2"] == 50


@pytest.mark.parametrize("role", ["admin", "director", "cskh", "accountant", "technical_lead", "security"])
def test_explicit_building_grant_cannot_read_other_building(case, same_site_other_building, role):
    unit = case[6][0]
    set_grants(case, [(role, case[5][0].id, unit.building_id)])
    headers = login(case, 1)
    assert case[0].get(f"/api/v1/units/{unit.id}/360", headers=headers).status_code == 200
    for target in (same_site_other_building[1].id, case[6][2].id, uuid4()):
        assert_scoped_404(case[0].get(f"/api/v1/units/{target}/360", headers=headers))


@pytest.mark.parametrize("role", ["cskh", "technical_lead", "security", "technician"])
def test_site_membership_never_replaces_building_or_assignment(case, role):
    set_grants(case, [(role, case[5][0].id, None)])
    assert_scoped_404(case[0].get(f"/api/v1/units/{case[6][0].id}/360", headers=login(case, 1)))


@pytest.mark.parametrize("role", ["admin", "director", "accountant"])
def test_site_wide_grant_keeps_legitimate_multi_building_access(case, same_site_other_building, role):
    set_grants(case, [(role, case[5][0].id, None)])
    headers = login(case, 1)
    for target in (case[6][0].id, same_site_other_building[1].id):
        response = case[0].get(f"/api/v1/units/{target}/360", headers=headers)
        assert response.status_code == 200
        assert response.json()["residents_visible"] is True


@pytest.mark.parametrize("restricted_role", ["security", "technical_lead", "cleaning"])
def test_mixed_roles_never_transfer_fields_between_buildings(case, same_site_other_building, restricted_role):
    other_building, other_unit = same_site_other_building
    set_grants(case, [("cskh", case[5][0].id, case[6][0].building_id),
                      (restricted_role, case[5][0].id, other_building.id)])
    headers = login(case, 1)
    allowed = case[0].get(f"/api/v1/units/{case[6][0].id}/360", headers=headers)
    assert allowed.json()["residents_visible"] is True
    response = case[0].get(f"/api/v1/units/{other_unit.id}/360", headers=headers)
    if restricted_role == "cleaning":
        assert_scoped_404(response)
    else:
        assert response.status_code == 200
        assert response.json()["residents_visible"] is False
        assert response.json()["residents"] == []
        if restricted_role == "security":
            assert response.json()["area_m2"] is None


def test_admin_building_grant_does_not_expand_through_cleaning_membership(case, same_site_other_building):
    set_grants(case, [("admin", case[5][0].id, case[6][0].building_id),
                      ("cleaning", case[5][0].id, same_site_other_building[0].id)])
    assert_scoped_404(case[0].get(f"/api/v1/units/{same_site_other_building[1].id}/360", headers=login(case, 1)))


@pytest.mark.parametrize("role", ["technical_lead", "security"])
def test_restricted_projection_does_not_query_person_or_relationship(case, role):
    set_grants(case, [(role, case[5][0].id, case[6][0].building_id)])
    statements = []
    def collect(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(case[1].engine, "before_cursor_execute", collect)
    try:
        response = case[0].get(f"/api/v1/units/{case[6][0].id}/360", headers=login(case, 1))
        assert response.status_code == 200
    finally:
        event.remove(case[1].engine, "before_cursor_execute", collect)
    assert not any("greencity.persons" in sql or "greencity.unit_person_relationships" in sql for sql in statements)


def test_revoked_building_grant_takes_effect_with_existing_token(case, same_site_other_building):
    set_grants(case, [("cskh", case[5][0].id, case[6][0].building_id),
                      ("cskh", case[5][0].id, same_site_other_building[0].id)])
    headers = login(case, 1)
    set_grants(case, [("cskh", case[5][0].id, same_site_other_building[0].id)])
    assert_scoped_404(case[0].get(f"/api/v1/units/{case[6][0].id}/360", headers=headers))
    assert case[0].get(f"/api/v1/units/{same_site_other_building[1].id}/360", headers=headers).status_code == 200


@pytest.mark.parametrize("site_index", [1, 2, None])
def test_database_rejects_invalid_building_site_grants(case, site_index):
    with case[1].get_session() as session:
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(AccountRole(account_id=case[4][1].id, role="admin",
                                        site_id=case[5][site_index].id if site_index is not None else None,
                                        building_id=case[6][0].building_id))
                session.flush()


def test_deleting_building_revokes_grant_not_widen_scope(case):
    with case[1].get_session() as session:
        building = Building(site_id=case[5][0].id, code="EMPTY", name="Temporary")
        session.add(building)
        session.flush()
        grant = AccountRole(account_id=case[4][0].id, role="admin", site_id=case[5][0].id,
                            building_id=building.id)
        session.add(grant)
        session.flush()
        grant_id = grant.id
        session.execute(text("DELETE FROM greencity.buildings WHERE id=:id"), {"id": building.id})
        session.flush()
        assert session.scalar(select(AccountRole.id).where(AccountRole.id == grant_id)) is None


@pytest.mark.parametrize("role", ["auditor", "unknown"])
def test_roles_outside_core_roster_do_not_grant_site_metadata(case, role):
    set_grants(case, [(role, case[5][0].id, case[6][0].building_id)])
    response = case[0].get("/api/v1/auth/me", headers=login(case, 1))
    assert response.status_code == 200
    assert response.json()["roles"] == []
    assert response.json()["allowed_sites"] == []
    assert response.json()["active_site_id"] is None


@pytest.mark.parametrize("limited_role", ["security", "technical_lead"])
def test_same_building_grants_combine_but_field_revocation_is_immediate(case, limited_role):
    site, unit = case[5][0], case[6][0]
    set_grants(case, [("cskh", site.id, unit.building_id), (limited_role, site.id, unit.building_id)])
    headers = login(case, 1)
    response = case[0].get(f"/api/v1/units/{unit.id}/360", headers=headers)
    assert response.status_code == 200
    assert response.json()["residents_visible"] is True
    assert response.json()["area_m2"] == 50
    set_grants(case, [(limited_role, site.id, unit.building_id)])
    response = case[0].get(f"/api/v1/units/{unit.id}/360", headers=headers)
    assert response.status_code == 200
    assert response.json()["residents_visible"] is False
    assert response.json()["residents"] == []


@pytest.mark.parametrize("limited_role", ["security", "technical_lead"])
def test_mixed_building_projection_does_not_load_household(case, same_site_other_building, limited_role):
    other_building, other_unit = same_site_other_building
    set_grants(case, [("cskh", case[5][0].id, case[6][0].building_id),
                      (limited_role, case[5][0].id, other_building.id)])
    statements = []
    def collect(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(case[1].engine, "before_cursor_execute", collect)
    try:
        response = case[0].get(f"/api/v1/units/{other_unit.id}/360", headers=login(case, 1))
        assert response.status_code == 200
        assert response.json()["residents_visible"] is False
    finally:
        event.remove(case[1].engine, "before_cursor_execute", collect)
    assert not any("greencity.persons" in sql or "greencity.unit_person_relationships" in sql for sql in statements)


def test_client_building_and_role_claims_cannot_expand_database_grant(case, same_site_other_building):
    site, unit = case[5][0], case[6][0]
    set_grants(case, [("cskh", site.id, unit.building_id)])
    claims = {"sub": str(case[4][1].id), "active_site_id": str(site.id), "roles": ["admin"],
              "building_ids": [str(same_site_other_building[0].id)],
              "unit_grants": [{"role": "admin", "building_id": None}]}
    headers = {"Authorization": "Bearer " + create_token(claims, case[2].auth_secret()),
               "X-Role": "admin", "X-Building-ID": str(same_site_other_building[0].id)}
    assert_scoped_404(case[0].get(f"/api/v1/units/{same_site_other_building[1].id}/360?role=admin", headers=headers))
