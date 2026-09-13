"""R2 acceptance tests against the disposable PostgreSQL cluster only."""
from datetime import UTC, datetime, timedelta
import hashlib
import os
import secrets
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Database
from app.core.security import hash_password
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.maintenance import (
    Asset,
    MaintenanceHistory,
    MaintenanceOccurrence,
    MaintenancePlan,
)
from app.models.platform import Attachment, AuditEvent, DomainEvent, IdempotencyRecord
from app.models.service import (
    CaseRecord,
    ChargeReversal,
    CostLine,
    InvoiceItem,
    PendingCharge,
    ServiceCategory,
    ServiceRequest,
    WorkOrder,
)
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R2 tests require its disposable PostgreSQL cluster",
)]

PNG = (b"\x89PNG\r\n\x1a\n" + b"r2-synthetic-evidence"
       + b"\x00\x00\x00\x00IEND\xaeB\x60\x82")


@pytest.fixture(scope="module")
def r2_case():
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
        tenant = Tenant(name=f"R2 fixture {uuid4()}")
        session.add(tenant)
        session.flush()
        sites = [
            Site(tenant_id=tenant.id, code=f"R2-{suffix}-{uuid4().hex[:6]}",
                 name=f"R2 {suffix}", address="Synthetic")
            for suffix in ("WEST", "EAST")
        ]
        session.add_all(sites)
        session.flush()
        buildings = [
            Building(site_id=site.id, code="B1", name=f"Building {index}")
            for index, site in enumerate(sites)
        ]
        session.add_all(buildings)
        session.flush()
        units = [
            Unit(building_id=building.id, unit_number="R2-0101", floor=1,
                 area_m2=50, status="occupied")
            for building in buildings
        ]
        session.add_all(units)
        session.flush()

        hashed = hash_password(password)
        accounts = {}
        grants = {
            "cskh": [("cskh", sites[0].id, buildings[0].id)],
            "cskh_no_building": [("cskh", sites[0].id, None)],
            "lead": [("technical_lead", sites[0].id, buildings[0].id)],
            "tech": [("technician", sites[0].id, None)],
            "tech_other": [("technician", sites[0].id, None)],
            "accountant": [("accountant", sites[0].id, None)],
            "maker": [("technician", sites[0].id, None),
                      ("accountant", sites[0].id, None)],
            "director": [("director", sites[0].id, None)],
            "cskh_other": [("cskh", sites[1].id, buildings[1].id)],
        }
        for label, role_grants in grants.items():
            account = Account(
                tenant_id=tenant.id,
                username=f"r2_{label}_{uuid4().hex}",
                full_name=f"R2 {label}",
                hashed_password=hashed,
            )
            session.add(account)
            session.flush()
            accounts[label] = account
            session.add_all(AccountRole(
                account_id=account.id,
                role=role,
                site_id=site_id,
                building_id=building_id,
            ) for role, site_id, building_id in role_grants)

        categories = [
            ServiceCategory(
                tenant_id=tenant.id,
                site_id=site.id,
                building_id=building.id,
                code="TECHNICAL",
                name="Technical request",
                sla_minutes=240,
            )
            for site, building in zip(sites, buildings, strict=True)
        ]
        session.add_all(categories)
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
            "sites": sites,
            "buildings": buildings,
            "units": units,
            "accounts": accounts,
            "categories": categories,
            "auth": auth,
        }
    transaction.rollback()
    connection.close()
    database.close()


def with_key(case, actor: str, key: str) -> dict[str, str]:
    return case["auth"][actor] | {"Idempotency-Key": key}


def create_request(case, suffix: str, *, actor="cskh"):
    response = case["client"].post(
        "/api/v1/service-requests",
        headers=with_key(case, actor, f"request-{suffix}-001"),
        json={
            "category_id": str(case["categories"][0].id),
            "building_id": str(case["buildings"][0].id),
            "unit_id": str(case["units"][0].id),
            "title": f"Request {suffix}",
            "description": "Synthetic R2 acceptance request",
            "priority": "HIGH",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def insert_request(session, *, tenant, site, building, unit, category, actor,
                   suffix: str, status="NEW", created_at=None):
    started_at = created_at or datetime.now(UTC)
    record = ServiceRequest(
        tenant_id=tenant.id,
        site_id=site.id,
        building_id=building.id,
        unit_id=unit.id if unit is not None else None,
        category_id=category.id,
        code=f"SR-LIST-{suffix}-{uuid4().hex[:8].upper()}",
        title=f"List request {suffix}",
        description="Synthetic list-scope request",
        priority="HIGH",
        status=status,
        sla_started_at=started_at,
        sla_duration_minutes=category.sla_minutes,
        owner_account_id=actor.id,
        created_by_id=actor.id,
        updated_by_id=actor.id,
        created_at=started_at,
    )
    session.add(record)
    session.flush()
    return record


@pytest.fixture(scope="module")
def service_request_list_data(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        same_site_building = Building(
            site_id=case["sites"][0].id,
            code=f"LIST-B2-{uuid4().hex[:6]}",
            name="List hidden building",
        )
        foreign_tenant = Tenant(name=f"List foreign tenant {uuid4()}")
        session.add_all([same_site_building, foreign_tenant])
        session.flush()
        foreign_site = Site(
            tenant_id=foreign_tenant.id,
            code=f"LIST-FOREIGN-{uuid4().hex[:6]}",
            name="List foreign site",
            address="Synthetic",
        )
        session.add(foreign_site)
        session.flush()
        foreign_building = Building(
            site_id=foreign_site.id,
            code="B1",
            name="List foreign building",
        )
        session.add(foreign_building)
        session.flush()
        same_site_unit = Unit(
            building_id=same_site_building.id,
            unit_number="LIST-HIDDEN",
            floor=2,
            area_m2=55,
            status="occupied",
        )
        foreign_unit = Unit(
            building_id=foreign_building.id,
            unit_number="LIST-FOREIGN",
            floor=3,
            area_m2=60,
            status="occupied",
        )
        foreign_account = Account(
            tenant_id=foreign_tenant.id,
            username=f"list_foreign_{uuid4().hex}",
            full_name="List foreign actor",
            hashed_password=case["accounts"]["cskh"].hashed_password,
        )
        session.add_all([same_site_unit, foreign_unit, foreign_account])
        session.flush()
        same_site_category = ServiceCategory(
            tenant_id=case["tenant"].id,
            site_id=case["sites"][0].id,
            building_id=same_site_building.id,
            code=f"LIST-HIDDEN-{uuid4().hex[:6]}",
            name="List hidden category",
            sla_minutes=180,
        )
        foreign_category = ServiceCategory(
            tenant_id=foreign_tenant.id,
            site_id=foreign_site.id,
            building_id=foreign_building.id,
            code="LIST-FOREIGN",
            name="List foreign category",
            sla_minutes=180,
        )
        session.add_all([same_site_category, foreign_category])
        session.flush()

        base_time = datetime(2026, 1, 1, tzinfo=UTC)
        visible = [
            insert_request(
                session,
                tenant=case["tenant"],
                site=case["sites"][0],
                building=case["buildings"][0],
                unit=case["units"][0],
                category=case["categories"][0],
                actor=case["accounts"]["cskh"],
                suffix=f"VISIBLE-{index}",
                status="WAITING_INFO",
                created_at=base_time + timedelta(minutes=index),
            )
            for index in range(3)
        ]
        hidden_building = insert_request(
            session,
            tenant=case["tenant"],
            site=case["sites"][0],
            building=same_site_building,
            unit=same_site_unit,
            category=same_site_category,
            actor=case["accounts"]["cskh"],
            suffix="HIDDEN-BUILDING",
            status="WAITING_INFO",
        )
        hidden_site = insert_request(
            session,
            tenant=case["tenant"],
            site=case["sites"][1],
            building=case["buildings"][1],
            unit=case["units"][1],
            category=case["categories"][1],
            actor=case["accounts"]["cskh_other"],
            suffix="HIDDEN-SITE",
            status="WAITING_INFO",
        )
        hidden_tenant = insert_request(
            session,
            tenant=foreign_tenant,
            site=foreign_site,
            building=foreign_building,
            unit=foreign_unit,
            category=foreign_category,
            actor=foreign_account,
            suffix="HIDDEN-TENANT",
            status="WAITING_INFO",
        )
        assigned_to_tech = insert_request(
            session,
            tenant=case["tenant"],
            site=case["sites"][0],
            building=case["buildings"][0],
            unit=case["units"][0],
            category=case["categories"][0],
            actor=case["accounts"]["cskh"],
            suffix="ASSIGNED-TECH",
        )
        assigned_to_other = insert_request(
            session,
            tenant=case["tenant"],
            site=case["sites"][0],
            building=case["buildings"][0],
            unit=case["units"][0],
            category=case["categories"][0],
            actor=case["accounts"]["cskh"],
            suffix="ASSIGNED-OTHER",
        )
        session.add_all([
            WorkOrder(
                tenant_id=request_record.tenant_id,
                site_id=request_record.site_id,
                building_id=request_record.building_id,
                service_request_id=request_record.id,
                code=f"WO-LIST-{uuid4().hex[:12].upper()}",
                title="List assigned work order",
                description="Synthetic list assignment",
                status="ASSIGNED",
                assigned_to_id=assignee.id,
                created_by_id=case["accounts"]["lead"].id,
                updated_by_id=case["accounts"]["lead"].id,
            )
            for request_record, assignee in (
                (assigned_to_tech, case["accounts"]["tech"]),
                (assigned_to_other, case["accounts"]["tech_other"]),
            )
        ])
        session.commit()
        return {
            "visible": visible,
            "hidden_building": hidden_building,
            "hidden_site": hidden_site,
            "hidden_tenant": hidden_tenant,
            "assigned_to_tech": assigned_to_tech,
            "assigned_to_other": assigned_to_other,
        }


def create_work_order(case, request_id: str, suffix: str):
    response = case["client"].post(
        f"/api/v1/service-requests/{request_id}/work-orders",
        headers=with_key(case, "cskh", f"work-order-{suffix}-001"),
        json={
            "title": f"Work order {suffix}",
            "description": "Synthetic R2 work order",
            "checklist": [{"label": "Verify result", "required": True}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def assign_and_start(case, work_order: dict, *, technician="tech"):
    response = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/assign",
        headers=case["auth"]["lead"],
        json={
            "assignee_id": str(case["accounts"][technician].id),
            "expected_version": work_order["version"],
        },
    )
    assert response.status_code == 200, response.text
    response = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/start",
        headers=case["auth"][technician],
        json={"expected_version": response.json()["version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def complete_checklist(case, work_order: dict, *, technician="tech"):
    for item in work_order["checklist"]:
        response = case["client"].patch(
            f"/api/v1/work-orders/{work_order['id']}/checklist/{item['id']}",
            headers=case["auth"][technician],
            json={
                "expected_version": item["version"],
                "is_completed": True,
                "result": "Verified",
            },
        )
        assert response.status_code == 200, response.text
    response = case["client"].get(
        f"/api/v1/work-orders/{work_order['id']}",
        headers=case["auth"][technician],
    )
    assert response.status_code == 200, response.text
    return response.json()


def upload_evidence(case, work_order_id: str, suffix: str, *, technician="tech"):
    headers = with_key(case, technician, f"evidence-{suffix}-001") | {
        "Content-Type": "image/png",
        "X-File-Name": f"{suffix}.png",
    }
    response = case["client"].post(
        f"/api/v1/work-orders/{work_order_id}/evidence",
        headers=headers,
        content=PNG,
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit_work_order(case, work_order: dict, *, technician="tech"):
    response = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/submit",
        headers=case["auth"][technician],
        json={"expected_version": work_order["version"], "result_summary": "Completed correctly"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_r2_readiness_reports_migrated_head(r2_case):
    response = r2_case["client"].get("/api/v1/readiness")
    assert response.status_code == 200
    assert response.json()["schema_revision"] == "0006"


def test_r2_request_idempotency_and_scope_are_enforced(r2_case):
    case = r2_case
    original = create_request(case, "idempotent")
    body = {
        "category_id": str(case["categories"][0].id),
        "building_id": str(case["buildings"][0].id),
        "unit_id": str(case["units"][0].id),
        "title": "Request idempotent",
        "description": "Synthetic R2 acceptance request",
        "priority": "HIGH",
    }
    repeated = case["client"].post(
        "/api/v1/service-requests",
        headers=with_key(case, "cskh", "request-idempotent-001"),
        json=body,
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == original["id"]
    body["title"] = "Changed payload"
    conflict = case["client"].post(
        "/api/v1/service-requests",
        headers=with_key(case, "cskh", "request-idempotent-001"),
        json=body,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ERR-CONFLICT"
    hidden = case["client"].get(
        f"/api/v1/service-requests/{original['id']}",
        headers=case["auth"]["cskh_other"],
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    with case["database"].get_session() as session:
        assert session.scalar(select(func.count(ServiceRequest.id)).where(
            ServiceRequest.id == original["id"],
        )) == 1
        assert session.scalar(select(func.count(IdempotencyRecord.id)).where(
            IdempotencyRecord.operation == "service-request.create",
            IdempotencyRecord.idempotency_key == "request-idempotent-001",
        )) == 1


def test_service_request_list_contract_scope_filter_and_pagination(
    r2_case, service_request_list_data,
):
    case = r2_case
    data = service_request_list_data
    query = {"status": "WAITING_INFO", "page": 1, "page_size": 2}
    first = case["client"].get(
        "/api/v1/service-requests", headers=case["auth"]["cskh"], params=query,
    )
    second = case["client"].get(
        "/api/v1/service-requests",
        headers=case["auth"]["cskh"],
        params=query | {"page": 2},
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["total"] == second.json()["total"] == 3
    assert first.json()["page"] == 1
    assert first.json()["page_size"] == 2

    expected_ids = [str(record.id) for record in reversed(data["visible"])]
    returned_ids = [item["id"] for item in first.json()["items"] + second.json()["items"]]
    assert returned_ids == expected_ids
    assert set(first.json()["items"][0]) == {
        "id", "code", "title", "unit_id", "unit_number", "building_id",
        "building_code", "building_name", "status", "priority", "sla_deadline",
        "created_at",
    }
    assert first.json()["items"][0]["unit_number"] == case["units"][0].unit_number
    assert first.json()["items"][0]["building_name"] == case["buildings"][0].name

    hidden_ids = {
        str(data["hidden_building"].id),
        str(data["hidden_site"].id),
        str(data["hidden_tenant"].id),
    }
    assert hidden_ids.isdisjoint(returned_ids)

    for actor in ("lead", "cskh"):
        response = case["client"].get(
            "/api/v1/service-requests",
            headers=case["auth"][actor],
            params={"status": "WAITING_INFO", "page_size": 100},
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 3
        assert {item["id"] for item in response.json()["items"]} == set(expected_ids)

    other_site = case["client"].get(
        "/api/v1/service-requests",
        headers=case["auth"]["cskh_other"],
        params={"status": "WAITING_INFO", "page_size": 100},
    )
    assert other_site.status_code == 200, other_site.text
    assert [item["id"] for item in other_site.json()["items"]] == [str(data["hidden_site"].id)]

    missing_building_grant = case["client"].get(
        "/api/v1/service-requests",
        headers=case["auth"]["cskh_no_building"],
        params={"status": "WAITING_INFO", "page_size": 100},
    )
    assert missing_building_grant.status_code == 200
    assert missing_building_grant.json()["items"] == []
    assert missing_building_grant.json()["total"] == 0
    hidden_detail = case["client"].get(
        f"/api/v1/service-requests/{data['hidden_building'].id}",
        headers=case["auth"]["cskh_no_building"],
    )
    assert hidden_detail.status_code == 404
    assert hidden_detail.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"

    spoofed_scope = case["client"].get(
        "/api/v1/service-requests",
        headers=case["auth"]["cskh"],
        params={
            "status": "WAITING_INFO",
            "page_size": 100,
            "tenant_id": str(data["hidden_tenant"].tenant_id),
            "building_id": str(data["hidden_building"].building_id),
        },
    )
    assert spoofed_scope.status_code == 200
    assert {item["id"] for item in spoofed_scope.json()["items"]} == set(expected_ids)

    assert case["client"].get("/api/v1/service-requests").status_code == 401
    for params in ({"status": "INVALID"}, {"page": 0}, {"page_size": 101}):
        response = case["client"].get(
            "/api/v1/service-requests", headers=case["auth"]["cskh"], params=params,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "ERR-VALIDATION"


def test_service_request_list_technician_is_assigned_only(
    r2_case, service_request_list_data,
):
    case = r2_case
    data = service_request_list_data
    for actor, visible, hidden in (
        ("tech", data["assigned_to_tech"], data["assigned_to_other"]),
        ("tech_other", data["assigned_to_other"], data["assigned_to_tech"]),
    ):
        response = case["client"].get(
            "/api/v1/service-requests",
            headers=case["auth"][actor],
            params={"status": "NEW", "page_size": 100},
        )
        assert response.status_code == 200, response.text
        returned_ids = {item["id"] for item in response.json()["items"]}
        assert str(visible.id) in returned_ids
        assert str(hidden.id) not in returned_ids
        assert str(data["hidden_building"].id) not in returned_ids
        assert str(data["hidden_site"].id) not in returned_ids
        assert str(data["hidden_tenant"].id) not in returned_ids


def test_r2_request_link_and_triage_contract(r2_case):
    case = r2_case
    original = create_request(case, "link-source")
    linked = case["client"].post(
        "/api/v1/service-requests",
        headers=with_key(case, "cskh", "request-linked-0001"),
        json={
            "category_id": str(case["categories"][0].id),
            "building_id": str(case["buildings"][0].id),
            "title": "Linked duplicate request",
            "description": "Synthetic duplicate",
            "priority": "LOW",
            "linked_request_id": original["id"],
            "link_type": "DUPLICATE",
            "link_reason": "Same resident incident",
        },
    )
    assert linked.status_code == 201, linked.text
    assert linked.json()["linked_request_id"] == original["id"]
    assert linked.json()["link_type"] == "DUPLICATE"
    triaged = case["client"].post(
        f"/api/v1/service-requests/{linked.json()['id']}/triage",
        headers=case["auth"]["cskh"],
        json={
            "expected_version": linked.json()["version"],
            "owner_account_id": str(case["accounts"]["lead"].id),
            "priority": "URGENT",
        },
    )
    assert triaged.status_code == 200, triaged.text
    assert triaged.json()["status"] == "TRIAGED"
    assert triaged.json()["priority"] == "URGENT"
    assert triaged.json()["owner_account_id"] == str(case["accounts"]["lead"].id)
    stale = case["client"].post(
        f"/api/v1/service-requests/{linked.json()['id']}/triage",
        headers=case["auth"]["cskh"],
        json={
            "expected_version": linked.json()["version"],
            "owner_account_id": str(case["accounts"]["lead"].id),
            "priority": "HIGH",
        },
    )
    assert stale.status_code == 409


def test_ac06_two_work_orders_resolve_only_after_both_terminal(r2_case):
    case = r2_case
    service_request = create_request(case, "ac06")
    first = create_work_order(case, service_request["id"], "ac06-a")
    second = create_work_order(case, service_request["id"], "ac06-b")
    first = assign_and_start(case, first)
    second = assign_and_start(case, second)
    unassigned = case["client"].get(
        f"/api/v1/work-orders/{first['id']}",
        headers=case["auth"]["tech_other"],
    )
    assert unassigned.status_code == 404

    first = complete_checklist(case, first)
    first_evidence = upload_evidence(case, first["id"], "ac06-a")
    first = submit_work_order(case, first)
    missing_proxy_fields = case["client"].post(
        f"/api/v1/work-orders/{first['id']}/accept",
        headers=case["auth"]["cskh"],
        json={"expected_version": first["version"], "mode": "PROXY"},
    )
    assert missing_proxy_fields.status_code == 422
    wrong_proxy_role = case["client"].post(
        f"/api/v1/work-orders/{first['id']}/accept",
        headers=case["auth"]["lead"],
        json={
            "expected_version": first["version"],
            "mode": "PROXY",
            "reason": "Wrong actor must not proxy accept",
            "evidence_id": first_evidence["id"],
        },
    )
    assert wrong_proxy_role.status_code == 403
    accepted = case["client"].post(
        f"/api/v1/work-orders/{first['id']}/accept",
        headers=case["auth"]["cskh"],
        json={
            "expected_version": first["version"],
            "mode": "PROXY",
            "reason": "Resident authorized proxy acceptance",
            "evidence_id": first_evidence["id"],
        },
    )
    assert accepted.status_code == 200, accepted.text
    request_after_first = case["client"].get(
        f"/api/v1/service-requests/{service_request['id']}",
        headers=case["auth"]["cskh"],
    ).json()
    assert request_after_first["status"] == "IN_PROGRESS"

    second = complete_checklist(case, second)
    upload_evidence(case, second["id"], "ac06-b")
    second = submit_work_order(case, second)
    accepted = case["client"].post(
        f"/api/v1/work-orders/{second['id']}/accept",
        headers=case["auth"]["lead"],
        json={"expected_version": second["version"], "mode": "TECHNICAL"},
    )
    assert accepted.status_code == 200, accepted.text
    resolved = case["client"].get(
        f"/api/v1/service-requests/{service_request['id']}",
        headers=case["auth"]["cskh"],
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolved_at"] is not None

    signed = case["client"].get(
        f"/api/v1/attachments/{first_evidence['id']}/signed-link",
        headers=case["auth"]["cskh"],
    )
    assert signed.status_code == 200
    download = case["client"].get(signed.json()["url"], headers=case["auth"]["cskh"])
    assert download.status_code == 200
    assert download.content == PNG
    assert download.headers["cache-control"] == "private, no-store"
    hidden = case["client"].get(
        signed.json()["url"],
        headers=case["auth"]["cskh_other"],
    )
    assert hidden.status_code == 404


def test_ac24_quarantine_allowlist_and_expiring_actor_scoped_link(r2_case, monkeypatch):
    case = r2_case
    service_request = create_request(case, "ac24")
    work_order = create_work_order(case, service_request["id"], "ac24")
    work_order = assign_and_start(case, work_order)

    rejected_content = b"MZ-not-an-image"
    rejected_digest = hashlib.sha256(rejected_content).hexdigest()
    rejected = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/evidence",
        headers=with_key(case, "tech", "evidence-ac24-rejected") | {
            "Content-Type": "image/png",
            "X-File-Name": "disguised.png",
        },
        content=rejected_content,
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "ERR-FILE-QUARANTINED"

    with case["database"].get_session() as session:
        quarantined = session.scalar(select(Attachment).where(Attachment.sha256 == rejected_digest))
        assert quarantined is not None
        assert quarantined.is_quarantined is True
        assert quarantined.storage_key.startswith(
            f"quarantine/{case['tenant'].id}/{case['sites'][0].id}/"
        )
        assert session.scalar(select(AuditEvent.id).where(
            AuditEvent.event_type == "AttachmentQuarantined",
            AuditEvent.resource_id == quarantined.id,
        )) is not None
        assert session.scalar(select(DomainEvent.id).where(
            DomainEvent.event_type == "AttachmentQuarantined",
            DomainEvent.resource_id == quarantined.id,
        )) is not None
        quarantined_id = quarantined.id
        quarantine_target = case["settings"].private_storage_path / quarantined.storage_key
    assert quarantine_target.is_file()
    assert quarantine_target.read_bytes() == rejected_content

    for suffix in ("content?signed_token=invalid", "signed-link"):
        blocked = case["client"].get(
            f"/api/v1/attachments/{quarantined_id}/{suffix}",
            headers=case["auth"]["tech"],
        )
        assert blocked.status_code == 423
        assert blocked.json()["error"]["code"] == "ERR-FILE-QUARANTINED"

    replay = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/evidence",
        headers=with_key(case, "tech", "evidence-ac24-rejected") | {
            "Content-Type": "image/png",
            "X-File-Name": "disguised.png",
        },
        content=rejected_content,
    )
    assert replay.status_code == 422
    with case["database"].get_session() as session:
        assert session.scalar(select(func.count(Attachment.id)).where(
            Attachment.sha256 == rejected_digest,
        )) == 1

    accepted = upload_evidence(case, work_order["id"], "ac24-valid")
    signed = case["client"].get(
        f"/api/v1/attachments/{accepted['id']}/signed-link",
        headers=case["auth"]["tech"],
    )
    assert signed.status_code == 200
    signed_url = signed.json()["url"]
    assert signed_url.startswith(f"/api/v1/attachments/{accepted['id']}/content?signed_token=")

    download = case["client"].get(signed_url, headers=case["auth"]["tech"])
    assert download.status_code == 200
    assert download.content == PNG
    assert download.headers["cache-control"] == "private, no-store"
    assert case["client"].get(signed_url, headers=case["auth"]["tech_other"]).status_code == 404

    original_time = time.time
    monkeypatch.setattr(
        "app.core.security.time.time",
        lambda: original_time() + case["settings"].attachment_link_ttl_seconds + 1,
    )
    expired = case["client"].get(signed_url, headers=case["auth"]["tech"])
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "ERR-LINK-EXPIRED"


def test_ac08_ac09_ac10_charge_sod_audit_and_reversal(r2_case):
    case = r2_case
    service_request = create_request(case, "charges")
    work_order = create_work_order(case, service_request["id"], "charges")
    work_order = assign_and_start(case, work_order, technician="maker")
    evidence = upload_evidence(case, work_order["id"], "charges", technician="maker")

    resident = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/cost-lines",
        headers=with_key(case, "maker", "cost-resident-001"),
        json={
            "description": "Replacement part",
            "amount_vnd": 125000,
            "cost_bearer": "RESIDENT",
            "evidence_attachment_id": evidence["id"],
        },
    )
    assert resident.status_code == 201, resident.text
    charge_id = resident.json()["pending_charge_id"]
    assert charge_id is not None
    management = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/cost-lines",
        headers=with_key(case, "maker", "cost-management-001"),
        json={
            "description": "Management labor",
            "amount_vnd": 50000,
            "cost_bearer": "MANAGEMENT",
        },
    )
    assert management.status_code == 201, management.text
    assert management.json()["pending_charge_id"] is None

    self_approval = case["client"].post(
        f"/api/v1/pending-charges/{charge_id}/decision",
        headers=case["auth"]["maker"],
        json={"expected_version": 1, "decision": "APPROVE"},
    )
    assert self_approval.status_code == 403
    assert self_approval.json()["error"]["code"] == "ERR-SOD-SELF-APPROVE"
    with case["database"].get_session() as session:
        denied = session.scalar(select(AuditEvent).where(
            AuditEvent.event_type == "PermissionDenied",
            AuditEvent.resource_id == charge_id,
        ))
        assert denied is not None
        assert denied.actor_account_id == case["accounts"]["maker"].id
        assert str(denied.correlation_id) == self_approval.headers["x-correlation-id"]
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(text(
                    "UPDATE greencity.audit_events SET reason='tampered' WHERE id=:id"
                ), {"id": denied.id})

    stale = case["client"].post(
        f"/api/v1/pending-charges/{charge_id}/decision",
        headers=case["auth"]["accountant"],
        json={"expected_version": 99, "decision": "APPROVE"},
    )
    assert stale.status_code == 409
    approved = case["client"].post(
        f"/api/v1/pending-charges/{charge_id}/decision",
        headers=case["auth"]["accountant"],
        json={"expected_version": 1, "decision": "APPROVE"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    posted = case["client"].post(
        f"/api/v1/pending-charges/{charge_id}/post",
        headers=with_key(case, "accountant", "charge-posting-001"),
        json={"expected_version": approved.json()["version"], "posting_reference": "R2-POST-001"},
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "POSTED"
    replay = case["client"].post(
        f"/api/v1/pending-charges/{charge_id}/post",
        headers=with_key(case, "accountant", "charge-posting-001"),
        json={"expected_version": approved.json()["version"], "posting_reference": "R2-POST-001"},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == charge_id

    cancelled = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/cancel",
        headers=case["auth"]["lead"],
        json={"expected_version": work_order["version"], "reason": "Resident cancelled after posting"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
    reopened = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/reopen",
        headers=case["auth"]["lead"],
        json={"expected_version": cancelled.json()["version"], "reason": "Correction work required"},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "IN_PROGRESS"

    with case["database"].get_session() as session:
        assert session.scalar(select(func.count(CostLine.id)).where(
            CostLine.work_order_id == work_order["id"],
        )) == 2
        charge = session.get(PendingCharge, charge_id)
        assert charge.status == "REVERSED"
        assert session.scalar(select(func.count(InvoiceItem.id)).where(
            InvoiceItem.pending_charge_id == charge.id,
        )) == 1
        assert session.scalar(select(func.count(ChargeReversal.id)).where(
            ChargeReversal.pending_charge_id == charge.id,
        )) == 1
        assert session.scalar(select(func.count(CaseRecord.id)).where(
            CaseRecord.source_work_order_id == work_order["id"],
        )) == 1


def test_ac38_ac39_scheduler_and_maintenance_completion(r2_case):
    case = r2_case
    due_at = datetime.now(UTC) - timedelta(days=1)
    asset_response = case["client"].post(
        "/api/v1/assets",
        headers=with_key(case, "lead", "asset-ac38-0001"),
        json={
            "building_id": str(case["buildings"][0].id),
            "unit_id": str(case["units"][0].id),
            "code": "PUMP_AC38",
            "name": "Water pump",
            "description": "Synthetic maintenance asset",
        },
    )
    assert asset_response.status_code == 201, asset_response.text
    asset = asset_response.json()
    plan_response = case["client"].post(
        "/api/v1/maintenance-plans",
        headers=with_key(case, "lead", "plan-ac38-00001"),
        json={
            "asset_id": asset["id"],
            "code": "MONTHLY",
            "title": "Monthly pump inspection",
            "interval_days": 30,
            "next_due_at": due_at.isoformat(),
            "checklist": [{"label": "Inspect pressure", "required": True}],
            "evidence_required": True,
        },
    )
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()
    as_of = datetime.now(UTC)
    first = case["client"].post(
        "/api/v1/maintenance/scheduler/run",
        headers=with_key(case, "lead", "scheduler-ac38-01"),
        json={"as_of": as_of.isoformat()},
    )
    assert first.status_code == 200, first.text
    assert len(first.json()["items"]) == 1
    created = first.json()["items"][0]
    assert created["replayed"] is False
    same_key = case["client"].post(
        "/api/v1/maintenance/scheduler/run",
        headers=with_key(case, "lead", "scheduler-ac38-01"),
        json={"as_of": as_of.isoformat()},
    )
    assert same_key.status_code == 200
    assert same_key.json() == first.json()
    existing = case["client"].post(
        "/api/v1/maintenance/scheduler/run",
        headers=with_key(case, "lead", "scheduler-ac38-02"),
        json={"as_of": as_of.isoformat()},
    )
    assert existing.status_code == 200, existing.text
    assert existing.json()["items"][0]["occurrence_id"] == created["occurrence_id"]
    assert existing.json()["items"][0]["work_order_id"] == created["work_order_id"]
    assert existing.json()["items"][0]["replayed"] is True
    with case["database"].get_session() as session:
        assert session.scalar(select(func.count(MaintenanceOccurrence.id)).where(
            MaintenanceOccurrence.plan_id == plan["id"],
        )) == 1
        assert session.scalar(select(func.count(WorkOrder.id)).where(
            WorkOrder.maintenance_occurrence_id == created["occurrence_id"],
        )) == 1

    work_order = case["client"].get(
        f"/api/v1/work-orders/{created['work_order_id']}",
        headers=case["auth"]["lead"],
    ).json()
    work_order = assign_and_start(case, work_order)
    while_in_progress = case["client"].post(
        "/api/v1/maintenance/scheduler/run",
        headers=with_key(case, "lead", "scheduler-ac38-03"),
        json={"as_of": as_of.isoformat()},
    )
    assert while_in_progress.status_code == 200, while_in_progress.text
    with case["database"].get_session() as session:
        assert session.get(MaintenanceOccurrence, created["occurrence_id"]).status == "IN_PROGRESS"
    missing_all = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/submit",
        headers=case["auth"]["tech"],
        json={"expected_version": work_order["version"], "result_summary": "Not complete"},
    )
    assert missing_all.status_code == 422
    assert missing_all.json()["error"]["code"] == "ERR-CHECKLIST-INCOMPLETE"
    work_order = complete_checklist(case, work_order)
    missing_image = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/submit",
        headers=case["auth"]["tech"],
        json={"expected_version": work_order["version"], "result_summary": "No image yet"},
    )
    assert missing_image.status_code == 422
    upload_evidence(case, work_order["id"], "ac39")
    work_order = submit_work_order(case, work_order)
    completed = case["client"].post(
        f"/api/v1/work-orders/{work_order['id']}/accept",
        headers=case["auth"]["lead"],
        json={"expected_version": work_order["version"], "mode": "TECHNICAL"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"
    with case["database"].get_session() as session:
        occurrence = session.get(MaintenanceOccurrence, created["occurrence_id"])
        updated_plan = session.get(MaintenancePlan, plan["id"])
        assert occurrence.status == "COMPLETED"
        assert occurrence.completed_at is not None
        assert updated_plan.next_due_at == due_at + timedelta(days=30)
        assert session.scalar(select(func.count(MaintenanceHistory.id)).where(
            MaintenanceHistory.occurrence_id == occurrence.id,
            MaintenanceHistory.asset_id == asset["id"],
            MaintenanceHistory.work_order_id == work_order["id"],
        )) == 1


def test_maintenance_defer_is_not_undone_by_early_scheduler_retry(r2_case):
    case = r2_case
    due_at = datetime.now(UTC) - timedelta(hours=1)
    asset = case["client"].post(
        "/api/v1/assets",
        headers=with_key(case, "lead", "asset-defer-0001"),
        json={
            "building_id": str(case["buildings"][0].id),
            "code": "PUMP_DEFER",
            "name": "Deferred pump",
            "description": "Synthetic",
        },
    ).json()
    plan = case["client"].post(
        "/api/v1/maintenance-plans",
        headers=with_key(case, "lead", "plan-defer-00001"),
        json={
            "asset_id": asset["id"],
            "code": "WEEKLY",
            "title": "Deferred inspection",
            "interval_days": 7,
            "next_due_at": due_at.isoformat(),
            "checklist": [{"label": "Inspect", "required": True}],
            "evidence_required": True,
        },
    ).json()
    as_of = datetime.now(UTC)
    scheduled = case["client"].post(
        "/api/v1/maintenance/scheduler/run",
        headers=with_key(case, "lead", "scheduler-defer-01"),
        json={"as_of": as_of.isoformat()},
    ).json()["items"]
    item = next(entry for entry in scheduled if entry["plan_id"] == plan["id"])
    with case["database"].get_session() as session:
        occurrence = session.get(MaintenanceOccurrence, item["occurrence_id"])
        expected_version = occurrence.version
    deferred_until = as_of + timedelta(days=2)
    deferred = case["client"].post(
        f"/api/v1/maintenance-occurrences/{item['occurrence_id']}/defer",
        headers=case["auth"]["lead"],
        json={
            "expected_version": expected_version,
            "defer_until": deferred_until.isoformat(),
            "reason": "Awaiting approved shutdown window",
        },
    )
    assert deferred.status_code == 200, deferred.text
    retried = case["client"].post(
        "/api/v1/maintenance/scheduler/run",
        headers=with_key(case, "lead", "scheduler-defer-02"),
        json={"as_of": (as_of + timedelta(hours=1)).isoformat()},
    )
    assert retried.status_code == 200, retried.text
    with case["database"].get_session() as session:
        occurrence = session.get(MaintenanceOccurrence, item["occurrence_id"])
        assert occurrence.status == "DEFERRED"
        assert occurrence.defer_until == deferred_until


def test_database_scope_constraint_rejects_cross_site_asset(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        invalid = Asset(
            tenant_id=case["tenant"].id,
            site_id=case["sites"][1].id,
            building_id=case["buildings"][0].id,
            code="INVALID_SCOPE",
            name="Must fail",
            description="Synthetic",
            created_by_id=case["accounts"]["lead"].id,
            updated_by_id=case["accounts"]["lead"].id,
        )
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.add(invalid)
                session.flush()
