import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.models.site import Site
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
