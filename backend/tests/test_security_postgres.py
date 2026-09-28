"""Actual PostgreSQL + HTTP/auth; only the disposable cluster runner enables these."""
from datetime import UTC, date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
import secrets
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi import Header, Request
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Database
from app.core.policy import get_current_user_context
from app.core.security import create_token, decode_token, hash_password
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.auth_session import AuthSession
from app.models.login_throttle import LoginThrottle
from app.models.building import Building
from app.models.person import Person, UnitPersonRelationship
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit
from app.services.login_throttle import login_identity_key
from auth_test_support import mint_session_token

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
                    for _ in range(4)]
        session.add_all(accounts)
        session.flush()
        session.add_all([
            AccountRole(account_id=accounts[0].id, role="admin", site_id=None),
            AccountRole(account_id=accounts[1].id, role="cskh", site_id=sites[0].id,
                        building_id=buildings[0].id),
            AccountRole(account_id=accounts[2].id, role="admin", site_id=sites[0].id),
            AccountRole(account_id=accounts[2].id, role="cleaning", site_id=sites[1].id),
            AccountRole(account_id=accounts[3].id, role="resident", site_id=None),
        ])
        people = [Person(tenant_id=t.id, full_name=f"Synthetic tenant {i}",
                         phone_masked="***", email_masked="***@example.invalid")
                  for i, t in enumerate(tenants)]
        session.add_all(people)
        session.flush()
        session.add(UnitPersonRelationship(
            unit_id=units[0].id,
            person_id=people[0].id,
            relationship_type="owner",
            ownership_ratio=Decimal("1.0000"),
            valid_from=date(2025, 1, 1),
        ))
        accounts[3].person_id = people[0].id
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


def test_session_token_is_persisted_and_logout_revokes_only_that_session(case):
    client, database, settings, _, accounts, *_ = case
    first = login(case, 0)
    second = login(case, 0)
    claims = decode_token(first["Authorization"][7:], settings.auth_secret())
    with database.get_session() as session:
        stored = session.get(AuthSession, UUID(claims["sid"]))
        assert stored is not None
        assert stored.account_id == accounts[0].id

    response = client.post("/api/v1/auth/logout", headers=first)
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.get("/api/v1/auth/me", headers=second).status_code == 200


def test_logout_all_invalidates_every_account_session(case):
    client, _, _, _, _, *_ = case
    first = login(case, 0)
    second = login(case, 0)
    response = client.post("/api/v1/auth/logout-all", headers=first)
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.get("/api/v1/auth/me", headers=second).status_code == 401


def test_site_switch_issues_new_scope_without_invalidating_other_tabs(case):
    client, _, _, _, _, sites, *_ = case
    previous = login(case, 0)
    switched = client.post(
        "/api/v1/auth/switch-site", headers=previous,
        json={"site_id": str(sites[1].id)},
    )
    assert switched.status_code == 200
    current = {"Authorization": "Bearer " + switched.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=current).json()["active_site_id"] == str(sites[1].id)
    assert client.get("/api/v1/auth/me", headers=previous).json()["active_site_id"] == str(sites[0].id)


def test_site_switch_cannot_recreate_a_session_revoked_after_dependency_validation(case):
    client, database, _, _, accounts, sites, *_ = case
    previous = login(case, 0)

    def revoke_after_authentication(request: Request, authorization: str | None = Header(None)):
        context = get_current_user_context(request, authorization)
        with database.get_session() as session:
            account = session.scalar(select(Account).where(
                Account.id == context.account_id,
            ).with_for_update())
            account.session_version += 1
            session.execute(update(AuthSession).where(
                AuthSession.account_id == account.id,
                AuthSession.revoked_at.is_(None),
            ).values(revoked_at=datetime.now(UTC)))
            session.commit()
        return context

    client.app.dependency_overrides[get_current_user_context] = revoke_after_authentication
    try:
        response = client.post(
            "/api/v1/auth/switch-site", headers=previous,
            json={"site_id": str(sites[1].id)},
        )
    finally:
        client.app.dependency_overrides.pop(get_current_user_context, None)

    assert response.status_code == 401
    with database.get_session() as session:
        assert session.scalar(select(Account.session_version).where(Account.id == accounts[0].id)) == 2
        assert session.scalar(select(AuthSession).where(
            AuthSession.account_id == accounts[0].id,
            AuthSession.revoked_at.is_(None),
        )) is None


def test_forced_password_change_blocks_business_routes_and_revokes_old_session(case):
    client, database, _, password, accounts, _, units, _ = case
    with database.get_session() as session:
        session.get(Account, accounts[1].id).must_change_password = True
        session.commit()

    initial = client.post("/api/v1/auth/login", json={
        "username": accounts[1].username, "password": password,
    })
    assert initial.status_code == 200
    old_token = {"Authorization": "Bearer " + initial.json()["access_token"]}
    assert initial.json()["user"]["must_change_password"] is True
    assert client.get("/api/v1/auth/me", headers=old_token).status_code == 200
    blocked = client.get(f"/api/v1/units/{units[0].id}/360", headers=old_token)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "ERR-PASSWORD-CHANGE-REQUIRED"

    changed = client.post("/api/v1/auth/change-password", headers=old_token, json={
        "current_password": password,
        "new_password": "distinct-password-for-test-user",
    })
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/me", headers=old_token).status_code == 401
    relogin = client.post("/api/v1/auth/login", json={
        "username": accounts[1].username,
        "password": "distinct-password-for-test-user",
    })
    assert relogin.status_code == 200
    assert relogin.json()["user"]["must_change_password"] is False
    current = {"Authorization": "Bearer " + relogin.json()["access_token"]}
    assert client.get(f"/api/v1/units/{units[0].id}/360", headers=current).status_code == 200


def test_legacy_session_token_without_persisted_session_claims_is_rejected(case):
    client, _, settings, _, accounts, sites, *_ = case
    legacy = create_token({
        "sub": str(accounts[1].id), "active_site_id": str(sites[0].id), "purpose": "session",
    }, settings.auth_secret())
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + legacy})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ERR-UNAUTHORIZED"


def test_login_throttle_persists_cooldown_and_resets_after_success(case):
    client, database, settings, password, accounts, *_ = case
    username = accounts[1].username
    unknown_username = f"unknown_{uuid4().hex}"
    for _ in range(settings.login_throttle_failure_threshold):
        wrong = client.post("/api/v1/auth/login", json={"username": username, "password": "incorrect"})
        assert wrong.status_code == 401
        assert wrong.json()["error"]["code"] == "ERR-UNAUTHORIZED"
        unknown = client.post("/api/v1/auth/login", json={"username": unknown_username, "password": "incorrect"})
        assert unknown.status_code == 401
        assert unknown.json()["error"]["code"] == "ERR-UNAUTHORIZED"
        assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]

    origin = settings.cors_origins[0]
    throttled = client.post("/api/v1/auth/login", headers={"Origin": origin}, json={
        "username": username, "password": password,
    })
    unknown_throttled = client.post("/api/v1/auth/login", json={
        "username": unknown_username, "password": "incorrect",
    })
    assert throttled.status_code == 429
    assert throttled.json()["error"]["code"] == "ERR-LOGIN-THROTTLED"
    assert unknown_throttled.status_code == 429
    assert unknown_throttled.json()["error"]["code"] == throttled.json()["error"]["code"]
    assert unknown_throttled.json()["error"]["message"] == throttled.json()["error"]["message"]
    assert 1 <= int(throttled.headers["retry-after"]) <= settings.login_throttle_base_backoff_seconds
    assert "retry-after" in throttled.headers["access-control-expose-headers"].lower()
    assert throttled.headers["cache-control"] == "private, no-store"
    login_responses = client.get("/openapi.json").json()["paths"]["/api/v1/auth/login"]["post"]["responses"]
    assert "Retry-After" in login_responses["429"]["headers"]
    key = login_identity_key(username, settings.auth_secret())
    with database.get_session() as session:
        state = session.get(LoginThrottle, key)
        assert state is not None
        locked_until = state.locked_until

    repeated = client.post("/api/v1/auth/login", json={"username": username, "password": "incorrect"})
    assert repeated.status_code == 429
    with database.get_session() as session:
        assert session.get(LoginThrottle, key).locked_until == locked_until

    reset_username = accounts[2].username
    failed_before_success = client.post("/api/v1/auth/login", json={
        "username": reset_username, "password": "incorrect",
    })
    assert failed_before_success.status_code == 401
    reset_key = login_identity_key(reset_username, settings.auth_secret())
    with database.get_session() as session:
        assert session.get(LoginThrottle, reset_key).failure_count == 1
    recovered = client.post("/api/v1/auth/login", json={"username": reset_username, "password": password})
    assert recovered.status_code == 200
    with database.get_session() as session:
        assert session.get(LoginThrottle, reset_key) is None


def test_login_throttle_failures_are_atomic_across_workers(case):
    settings = case[2]
    database = Database(settings)
    tenant_id, account_id = uuid4(), uuid4()
    username = f"concurrent_login_{uuid4().hex}"
    with database.get_session() as session:
        session.add(Tenant(id=tenant_id, name=f"Concurrent login {tenant_id}"))
        session.flush()
        session.add(Account(
            id=account_id,
            tenant_id=tenant_id,
            username=username,
            full_name="Concurrent login fixture",
            hashed_password=hash_password(secrets.token_urlsafe(24)),
        ))
        session.commit()

    barrier = Barrier(3, timeout=10)

    def fail_from_worker():
        worker_database = Database(settings)
        try:
            with TestClient(create_app(settings, worker_database)) as client:
                barrier.wait()
                return client.post("/api/v1/auth/login", json={
                    "username": username, "password": "incorrect",
                })
        finally:
            worker_database.close()

    key = login_identity_key(username, settings.auth_secret())
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(fail_from_worker) for _ in range(2)]
            barrier.wait()
            responses = [future.result(timeout=15) for future in futures]
        assert [response.status_code for response in responses] == [401, 401]
        with database.get_session() as session:
            state = session.get(LoginThrottle, key)
            assert state is not None
            assert state.failure_count == 2
    finally:
        with database.get_session() as session:
            session.execute(delete(LoginThrottle).where(LoginThrottle.identity_key == key))
            session.execute(delete(Account).where(Account.id == account_id))
            session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            session.commit()
        database.close()


def test_login_throttle_bounds_unknown_identity_rows(case):
    client, database, settings, password, accounts, *_ = case
    client.app.state.settings.login_throttle_max_identities = 1
    first_unknown = f"unknown_{uuid4().hex}"
    second_unknown = f"unknown_{uuid4().hex}"

    first_failure = client.post("/api/v1/auth/login", json={
        "username": first_unknown, "password": "incorrect",
    })
    assert first_failure.status_code == 401
    overflow = client.post("/api/v1/auth/login", json={
        "username": second_unknown, "password": "incorrect",
    })
    assert overflow.status_code == 429
    assert overflow.headers["retry-after"] == str(settings.login_throttle_base_backoff_seconds)
    with database.get_session() as session:
        assert session.scalar(select(func.count()).select_from(LoginThrottle)) == 1

    valid_existing = client.post("/api/v1/auth/login", json={
        "username": accounts[1].username, "password": password,
    })
    assert valid_existing.status_code == 200


def test_postgres_tls_and_head(case):
    with case[1].engine.connect() as connection:
        assert connection.scalar(text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"))
        assert connection.scalar(text("SELECT version_num FROM greencity.alembic_version")) == "0018"


def test_seed_repeat_keeps_expected_counts(case):
    # Separate connection cannot see this fixture's uncommitted transaction.
    # Other acceptance fixtures are allowed to create their own committed rows,
    # so this verifies only the canonical seed rather than every table globally.
    with case[1].engine.connect() as connection:
        tenant_id = connection.execute(text(
            "SELECT id FROM greencity.tenants WHERE name = 'GreenCity Corporation'"
        )).scalar_one()
        parameters = {"tenant_id": tenant_id}

        def count(sql: str) -> int:
            return connection.scalar(text(sql), parameters)

        assert count("SELECT count(*) FROM greencity.tenants WHERE id = :tenant_id") == 1
        assert count("""
            SELECT count(*) FROM greencity.sites
            WHERE tenant_id = :tenant_id AND code IN ('GC-WEST', 'GC-EAST')
        """) == 2
        assert count("""
            SELECT count(*) FROM greencity.buildings building
            JOIN greencity.sites site ON site.id = building.site_id
            WHERE site.tenant_id = :tenant_id AND (
                (site.code = 'GC-WEST' AND building.code = 'W1') OR
                (site.code = 'GC-EAST' AND building.code = 'E1')
            )
        """) == 2
        assert count("""
            SELECT count(*) FROM greencity.units unit
            JOIN greencity.buildings building ON building.id = unit.building_id
            JOIN greencity.sites site ON site.id = building.site_id
            WHERE site.tenant_id = :tenant_id AND (
                (site.code = 'GC-WEST' AND building.code = 'W1'
                 AND unit.unit_number IN ('W1-0101', 'W1-0102', 'W1-0103')) OR
                (site.code = 'GC-EAST' AND building.code = 'E1'
                 AND unit.unit_number = 'E1-0201')
            )
        """) == 4
        assert count("""
            SELECT count(*) FROM greencity.persons
            WHERE tenant_id = :tenant_id AND phone_masked IN ('090***0001', '090***0002')
        """) == 2
        assert count("""
            SELECT count(*) FROM greencity.unit_person_relationships relationship
            JOIN greencity.units unit ON unit.id = relationship.unit_id
            JOIN greencity.buildings building ON building.id = unit.building_id
            JOIN greencity.sites site ON site.id = building.site_id
            JOIN greencity.persons person ON person.id = relationship.person_id
            WHERE site.tenant_id = :tenant_id AND (
                (site.code = 'GC-WEST' AND building.code = 'W1'
                 AND unit.unit_number IN ('W1-0101', 'W1-0102', 'W1-0103')
                 AND person.phone_masked = '090***0001'
                 AND relationship.relationship_type IN ('owner', 'tenant')) OR
                (site.code = 'GC-EAST' AND building.code = 'E1'
                 AND unit.unit_number = 'E1-0201'
                 AND person.phone_masked = '090***0002'
                 AND relationship.relationship_type = 'owner')
            )
        """) == 4
        assert count("""
            SELECT count(*) FROM greencity.accounts
            WHERE tenant_id = :tenant_id AND username IN (
                'admin_demo', 'director_west', 'cskh_west', 'cskh_east',
                'accountant_west', 'techlead_west', 'technician_west',
                'cleaning_west', 'security_west'
            )
        """) == 9
        assert count("""
            SELECT count(*) FROM greencity.account_roles role
            JOIN greencity.accounts account ON account.id = role.account_id
            WHERE account.tenant_id = :tenant_id AND account.username IN (
                'admin_demo', 'director_west', 'cskh_west', 'cskh_east',
                'accountant_west', 'techlead_west', 'technician_west',
                'cleaning_west', 'security_west'
            )
        """) == 9
        assert count("""
            SELECT count(*) FROM greencity.service_categories category
            JOIN greencity.sites site ON site.id = category.site_id
            WHERE category.tenant_id = :tenant_id
              AND site.code IN ('GC-WEST', 'GC-EAST')
              AND category.code = 'TECHNICAL'
        """) == 2
        assert count("""
            SELECT count(*) FROM greencity.cleaning_routes route
            JOIN greencity.sites site ON site.id = route.site_id
            WHERE route.tenant_id = :tenant_id
              AND site.code IN ('GC-WEST', 'GC-EAST')
              AND route.code = 'CLN-LOBBY'
        """) == 2
        assert count("""
            SELECT count(*) FROM greencity.cleaning_areas area
            JOIN greencity.sites site ON site.id = area.site_id
            WHERE area.tenant_id = :tenant_id
              AND site.code IN ('GC-WEST', 'GC-EAST')
              AND area.code = 'LOBBY'
        """) == 2
        assert count("""
            SELECT count(*) FROM greencity.cleaning_route_stops stop
            JOIN greencity.cleaning_routes route ON route.id = stop.route_id
            JOIN greencity.sites site ON site.id = route.site_id
            WHERE stop.tenant_id = :tenant_id
              AND site.code IN ('GC-WEST', 'GC-EAST')
              AND route.code = 'CLN-LOBBY' AND stop.position = 1
        """) == 2
        assert count("""
            SELECT count(*) FROM greencity.patrol_points point
            JOIN greencity.sites site ON site.id = point.site_id
            WHERE point.tenant_id = :tenant_id
              AND site.code IN ('GC-WEST', 'GC-EAST')
              AND point.code = 'SEC-LOBBY'
        """) == 2


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
              "roles": ["admin"], "active_site_id": str(sites[0].id), "purpose": "session"}
    headers = {"Authorization": "Bearer " + mint_session_token(
        case[1], accounts[1].id, settings.auth_secret(), claims=claims,
    )}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(accounts[1].tenant_id)
    assert response.json()["roles"] == ["cskh"]
    claims["active_site_id"] = str(sites[2].id)
    headers = {"Authorization": "Bearer " + mint_session_token(
        case[1], accounts[1].id, settings.auth_secret(), claims=claims,
    )}
    assert_scoped_404(client.get(f"/api/v1/units/{units[2].id}/360", headers=headers))


def test_resident_identity_and_scope_are_database_derived(case):
    client, _, settings, _, accounts, sites, units, people = case
    headers = login(case, 3)

    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    user = response.json()
    assert user["roles"] == ["resident"]
    assert user["resident_person_id"] == str(people[0].id)
    assert user["resident_unit_ids"] == [str(units[0].id)]
    assert user["active_site_id"] == str(sites[0].id)
    assert [site["id"] for site in user["allowed_sites"]] == [str(sites[0].id)]

    # Resident identity does not turn the existing staff-only reads into a
    # household search oracle.
    assert client.get(f"/api/v1/units/{units[0].id}/360", headers=headers).status_code == 403
    assert client.get(f"/api/v1/persons/{people[0].id}/units", headers=headers).status_code == 403

    # A signed client claim cannot substitute a different Person or role.
    claims = {
        "sub": str(accounts[3].id), "tenant_id": str(uuid4()),
        "person_id": str(people[1].id), "roles": ["admin", "resident"],
        "active_site_id": str(sites[0].id), "purpose": "session",
    }
    forged_headers = {"Authorization": "Bearer " + mint_session_token(
        case[1], accounts[3].id, settings.auth_secret(), claims=claims,
    )}
    forged = client.get("/api/v1/auth/me", headers=forged_headers)
    assert forged.status_code == 200
    assert forged.json()["resident_person_id"] == str(people[0].id)
    assert forged.json()["resident_unit_ids"] == [str(units[0].id)]
    assert forged.json()["roles"] == ["resident"]

    claims["active_site_id"] = str(sites[1].id)
    invalid_site_headers = {"Authorization": "Bearer " + mint_session_token(
        case[1], accounts[3].id, settings.auth_secret(), claims=claims,
    )}
    assert_scoped_404(client.get("/api/v1/auth/me", headers=invalid_site_headers))


def test_resident_mapping_rejects_cross_tenant_and_rechecks_revocation(case):
    client, database, _, _, accounts, _, units, people = case
    with database.get_session() as session:
        account = session.get(Account, accounts[3].id)
        account.person_id = people[1].id
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    headers = login(case, 3)
    with database.get_session() as session:
        relationship = session.scalar(select(UnitPersonRelationship).where(
            UnitPersonRelationship.person_id == people[0].id,
            UnitPersonRelationship.unit_id == units[0].id,
        ))
        session.delete(relationship)
        session.commit()
    assert_scoped_404(client.get("/api/v1/auth/me", headers=headers))


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
        session.add(UnitPersonRelationship(
            unit_id=unit.id,
            person_id=case[7][0].id,
            relationship_type="owner",
            ownership_ratio=Decimal("1.0000"),
            valid_from=date(2025, 1, 1),
        ))
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
              "unit_grants": [{"role": "admin", "building_id": None}], "purpose": "session"}
    headers = {"Authorization": "Bearer " + mint_session_token(
        case[1], case[4][1].id, case[2].auth_secret(), claims=claims,
    ),
               "X-Role": "admin", "X-Building-ID": str(same_site_other_building[0].id)}
    assert_scoped_404(case[0].get(f"/api/v1/units/{same_site_other_building[1].id}/360?role=admin", headers=headers))
