"""R3 AC-40/AC-41 acceptance tests against the disposable PostgreSQL cluster."""
from datetime import UTC, datetime, timedelta
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.security import create_token
from app.models.account import Account, AccountRole
from app.models.operations import CleaningArea, CleaningRoute, CleaningRouteStop, CleaningShift
from app.models.platform import AuditEvent
from app.models.service import CaseRecord, WorkOrder
from test_r2_integration import r2_case, with_key


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R3 tests require its disposable PostgreSQL cluster",
)]


def _auth(case, account):
    token = create_token({
        "sub": str(account.id),
        "active_site_id": str(case["sites"][0].id),
        "purpose": "session",
    }, case["settings"].auth_secret())
    return {"Authorization": "Bearer " + token}


@pytest.fixture(scope="module")
def cleaning_case(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        cleaners = {}
        for label in ("cleaner_a", "cleaner_b"):
            account = Account(
                tenant_id=case["tenant"].id,
                username=f"r3_{label}_{uuid4().hex}",
                full_name=f"R3 {label}",
                hashed_password=case["accounts"]["cskh"].hashed_password,
            )
            session.add(account)
            session.flush()
            session.add(AccountRole(
                account_id=account.id, role="cleaning", site_id=case["sites"][0].id,
                building_id=case["buildings"][0].id,
            ))
            cleaners[label] = account
        route = CleaningRoute(
            tenant_id=case["tenant"].id, site_id=case["sites"][0].id,
            building_id=case["buildings"][0].id, code=f"R3-CLEAN-{uuid4().hex[:8]}",
            name="R3 cleaning route", created_by_id=case["accounts"]["director"].id,
            updated_by_id=case["accounts"]["director"].id,
        )
        areas = [CleaningArea(
            tenant_id=case["tenant"].id, site_id=case["sites"][0].id,
            building_id=case["buildings"][0].id, code=f"R3-A-{uuid4().hex[:7]}",
            name=f"R3 cleaning area {position}", created_by_id=case["accounts"]["director"].id,
            updated_by_id=case["accounts"]["director"].id,
        ) for position in (1, 2)]
        session.add_all([route, *areas])
        session.flush()
        session.add_all(CleaningRouteStop(
            tenant_id=route.tenant_id, site_id=route.site_id, building_id=route.building_id,
            route_id=route.id, cleaning_area_id=area.id, position=position,
            checklist_template=[
                {"label": f"Điểm kiểm tra {position}.1", "required": True},
                {"label": f"Điểm kiểm tra {position}.2", "required": True},
            ],
        ) for position, area in enumerate(areas, 1))
        foreign_route = CleaningRoute(
            tenant_id=case["tenant"].id, site_id=case["sites"][1].id,
            building_id=case["buildings"][1].id, code=f"R3-F-{uuid4().hex[:8]}",
            name="Foreign route", created_by_id=case["accounts"]["cskh_other"].id,
            updated_by_id=case["accounts"]["cskh_other"].id,
        )
        session.add(foreign_route)
        session.commit()
    case["auth"].update({label: _auth(case, account) for label, account in cleaners.items()})
    return case | {"route": route, "foreign_route": foreign_route, "cleaners": cleaners}


def _shift(case, key, start_at=None):
    start_at = start_at or datetime.now(UTC) + timedelta(hours=1)
    body = {
        "route_id": str(case["route"].id),
        "scheduled_start_at": start_at.isoformat(),
        "scheduled_end_at": (start_at + timedelta(hours=2)).isoformat(),
    }
    response = case["client"].post("/api/v1/cleaning/shifts",
                                   headers=with_key(case, "director", key), json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def _assign(case, task, cleaner):
    response = case["client"].post(f"/api/v1/cleaning/tasks/{task['id']}/assign",
                                   headers=case["auth"]["director"], json={
                                       "assignee_id": str(case["cleaners"][cleaner].id),
                                       "expected_version": task["version"],
                                   })
    assert response.status_code == 200, response.text
    return response.json()


def _start(case, task, cleaner):
    response = case["client"].post(f"/api/v1/cleaning/tasks/{task['id']}/start",
                                   headers=case["auth"][cleaner],
                                   json={"expected_version": task["version"]})
    assert response.status_code == 200, response.text
    return response.json()


def _check(case, task, cleaner, index, result):
    item = task["checklist"][index]
    response = case["client"].patch(
        f"/api/v1/cleaning/tasks/{task['id']}/checklist/{item['id']}",
        headers=case["auth"][cleaner],
        json={"expected_version": item["version"], "result": result, "note": "Synthetic check"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_ac40_cleaning_golden_flow_assigned_only_and_accepted(cleaning_case):
    case = cleaning_case
    shift, body = _shift(case, "cleaning-golden-0001")
    replay = case["client"].post("/api/v1/cleaning/shifts",
                                  headers=with_key(case, "director", "cleaning-golden-0001"), json=body)
    assert replay.status_code == 201 and replay.json()["id"] == shift["id"]
    assert len(shift["tasks"]) == 2
    task_a = _assign(case, shift["tasks"][0], "cleaner_a")
    task_b = _assign(case, shift["tasks"][1], "cleaner_b")
    stale = case["client"].post(f"/api/v1/cleaning/tasks/{task_a['id']}/assign",
                                headers=case["auth"]["director"], json={
                                    "assignee_id": str(case["cleaners"]["cleaner_a"].id),
                                    "expected_version": shift["tasks"][0]["version"],
                                })
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "ERR-CONFLICT"
    listed = case["client"].get("/api/v1/cleaning/tasks", headers=case["auth"]["cleaner_a"])
    assert listed.status_code == 200 and [item["id"] for item in listed.json()["items"]] == [task_a["id"]]
    hidden = case["client"].get(f"/api/v1/cleaning/tasks/{task_b['id']}", headers=case["auth"]["cleaner_a"])
    assert hidden.status_code == 404 and hidden.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    assert case["client"].get("/api/v1/cleaning/tasks", headers=case["auth"]["cskh"]).status_code == 403

    task_a = _start(case, task_a, "cleaner_a")
    assert task_a["started_at"] and task_a["status"] == "IN_PROGRESS"
    task_a = _check(case, task_a, "cleaner_a", 0, "PASS")
    task_a = _check(case, task_a, "cleaner_a", 1, "PASS")
    submit_version = task_a["version"]
    submitted = case["client"].post(f"/api/v1/cleaning/tasks/{task_a['id']}/submit",
                                    headers=with_key(case, "cleaner_a", "cleaning-submit-pass-001"),
                                    json={"expected_version": submit_version})
    assert submitted.status_code == 200, submitted.text
    task_a = submitted.json()
    assert task_a["status"] == "SUBMITTED" and task_a["submitted_at"]
    assert all(item["performed_at"] for item in task_a["checklist"])
    assert {item["performed_by_id"] for item in task_a["checklist"]} == {str(case["cleaners"]["cleaner_a"].id)}
    accepted = case["client"].post(f"/api/v1/cleaning/tasks/{task_a['id']}/accept",
                                   headers=case["auth"]["director"], json={"expected_version": task_a["version"]})
    assert accepted.status_code == 200 and accepted.json()["status"] == "ACCEPTED"
    with case["database"].get_session() as session:
        assert session.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.resource_id == UUID(task_a["id"]))) >= 4


def test_ac41_fail_creates_one_work_order_and_case_without_rewriting_history(cleaning_case):
    case = cleaning_case
    shift, _ = _shift(case, "cleaning-rework-0001")
    task = _start(case, _assign(case, shift["tasks"][0], "cleaner_b"), "cleaner_b")
    task = _check(case, task, "cleaner_b", 0, "FAIL")
    incomplete = case["client"].post(f"/api/v1/cleaning/tasks/{task['id']}/submit",
                                     headers=with_key(case, "cleaner_b", "cleaning-submit-fail-001"),
                                     json={"expected_version": task["version"]})
    assert incomplete.status_code == 422 and incomplete.json()["error"]["code"] == "ERR-CHECKLIST-INCOMPLETE"
    task = _check(case, task, "cleaner_b", 1, "PASS")
    submit_version = task["version"]
    rework = case["client"].post(f"/api/v1/cleaning/tasks/{task['id']}/submit",
                                 headers=with_key(case, "cleaner_b", "cleaning-submit-fail-002"),
                                 json={"expected_version": submit_version})
    assert rework.status_code == 200, rework.text
    task = rework.json()
    assert task["status"] == "REWORK_REQUIRED" and task["checklist"][0]["result"] == "FAIL"
    assert task["rework_work_order_id"] and task["rework_case_id"]
    replay = case["client"].post(f"/api/v1/cleaning/tasks/{task['id']}/submit",
                                  headers=with_key(case, "cleaner_b", "cleaning-submit-fail-002"),
                                  json={"expected_version": submit_version})
    assert replay.status_code == 200 and replay.json()["rework_work_order_id"] == task["rework_work_order_id"]
    with case["database"].get_session() as session:
        work_order = session.get(WorkOrder, UUID(task["rework_work_order_id"]))
        case_record = session.get(CaseRecord, UUID(task["rework_case_id"]))
        assert work_order.cleaning_task_id == UUID(task["id"])
        assert case_record.source_work_order_id == work_order.id
        assert session.scalar(select(func.count(WorkOrder.id)).where(WorkOrder.cleaning_task_id == work_order.cleaning_task_id)) == 1
        assert session.scalar(select(func.count(CaseRecord.id)).where(CaseRecord.source_work_order_id == work_order.id)) == 1


def test_cleaning_cross_site_and_exception_state_branches_are_fail_closed(cleaning_case):
    case = cleaning_case
    start_at = datetime.now(UTC) + timedelta(hours=8)
    cross_site = case["client"].post("/api/v1/cleaning/shifts",
                                     headers=with_key(case, "director", "cleaning-cross-site-001"), json={
                                         "route_id": str(case["foreign_route"].id),
                                         "scheduled_start_at": start_at.isoformat(),
                                         "scheduled_end_at": (start_at + timedelta(hours=2)).isoformat(),
                                     })
    assert cross_site.status_code == 404 and cross_site.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    foreign_roster = case["client"].get("/api/v1/cleaning/assignees",
                                        headers=case["auth"]["director"],
                                        params={"building_id": str(case["buildings"][1].id)})
    assert foreign_roster.status_code == 404 and foreign_roster.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    shift, _ = _shift(case, "cleaning-exceptions-001", start_at + timedelta(hours=3))
    missed = case["client"].post(f"/api/v1/cleaning/tasks/{shift['tasks'][0]['id']}/missed",
                                 headers=case["auth"]["director"], json={
                                     "expected_version": shift["tasks"][0]["version"], "reason": "Không có nhân sự nhận ca",
                                 })
    cancelled = case["client"].post(f"/api/v1/cleaning/tasks/{shift['tasks'][1]['id']}/cancel",
                                    headers=case["auth"]["director"], json={
                                        "expected_version": shift["tasks"][1]["version"], "reason": "Khu vực tạm đóng để thi công",
                                    })
    assert missed.status_code == cancelled.status_code == 200
    assert missed.json()["status"] == "MISSED" and cancelled.json()["status"] == "CANCELLED"
    with case["database"].get_session() as session:
        assert session.get(CleaningShift, UUID(shift["id"])).status == "COMPLETED"
