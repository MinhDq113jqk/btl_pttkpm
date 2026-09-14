"""R3 AC-42/AC-43 acceptance tests against the disposable PostgreSQL cluster."""
from datetime import UTC, datetime, timedelta
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from app.core.security import create_token
from app.models.account import Account, AccountRole
from app.models.operations import PatrolPoint, SecurityShiftHandoff
from test_r2_integration import r2_case, with_key


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R3 tests require its disposable PostgreSQL cluster",
)]


def _auth(case, account, site_index=0):
    token = create_token({
        "sub": str(account.id),
        "active_site_id": str(case["sites"][site_index].id),
        "purpose": "session",
    }, case["settings"].auth_secret())
    return {"Authorization": "Bearer " + token}


@pytest.fixture(scope="module")
def security_case(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        guards = {}
        for label in ("guard_a", "guard_b"):
            account = Account(
                tenant_id=case["tenant"].id,
                username=f"r3_{label}_{uuid4().hex}",
                full_name=f"R3 {label}",
                hashed_password=case["accounts"]["cskh"].hashed_password,
            )
            session.add(account)
            session.flush()
            session.add(AccountRole(
                account_id=account.id, role="security", site_id=case["sites"][0].id,
                building_id=case["buildings"][0].id,
            ))
            guards[label] = account
        foreign_guard = Account(
            tenant_id=case["tenant"].id,
            username=f"r3_guard_foreign_{uuid4().hex}",
            full_name="R3 foreign guard",
            hashed_password=case["accounts"]["cskh"].hashed_password,
        )
        session.add(foreign_guard)
        session.flush()
        session.add(AccountRole(
            account_id=foreign_guard.id, role="security", site_id=case["sites"][1].id,
            building_id=case["buildings"][1].id,
        ))
        points = []
        for position in (1, 2):
            point = PatrolPoint(
                tenant_id=case["tenant"].id, site_id=case["sites"][0].id,
                building_id=case["buildings"][0].id, code=f"R3-SEC-{uuid4().hex[:7]}",
                name=f"R3 điểm tuần tra {position}", is_active=True,
                created_by_id=case["accounts"]["director"].id,
                updated_by_id=case["accounts"]["director"].id,
            )
            session.add(point)
            points.append(point)
        session.commit()
    case["auth"].update({label: _auth(case, account) for label, account in guards.items()})
    case["auth"]["foreign_guard"] = _auth(case, foreign_guard, site_index=1)
    return case | {"guards": guards, "foreign_guard": foreign_guard, "points": points}


def _create_shift(case, key):
    start = datetime.now(UTC) + timedelta(hours=3)
    body = {
        "building_id": str(case["buildings"][0].id),
        "assignee_id": str(case["guards"]["guard_a"].id),
        "scheduled_start_at": start.isoformat(),
        "scheduled_end_at": (start + timedelta(hours=4)).isoformat(),
        "patrol_windows": [
            {"patrol_point_id": str(case["points"][0].id), "window_start_at": start.isoformat(), "window_end_at": (start + timedelta(minutes=40)).isoformat()},
            {"patrol_point_id": str(case["points"][1].id), "window_start_at": (start + timedelta(hours=1)).isoformat(), "window_end_at": (start + timedelta(hours=1, minutes=40)).isoformat()},
        ],
    }
    response = case["client"].post("/api/v1/security/shifts", headers=with_key(case, "director", key), json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def _transition(case, incident, actor, status, conclusion=None):
    payload = {"expected_version": incident["version"], "status": status}
    if conclusion is not None:
        payload["conclusion"] = conclusion
    response = case["client"].post(
        f"/api/v1/security/incidents/{incident['id']}/transition",
        headers=case["auth"][actor], json=payload,
    )
    return response


def test_ac42_security_shift_handoff_patrol_and_missed_exception(security_case):
    case = security_case
    shift, body = _create_shift(case, "security-shift-golden-001")
    replay = case["client"].post("/api/v1/security/shifts", headers=with_key(case, "director", "security-shift-golden-001"), json=body)
    assert replay.status_code == 201 and replay.json()["id"] == shift["id"]
    assert len(shift["patrol_windows"]) == 2

    foreign = case["client"].get(f"/api/v1/security/shifts/{shift['id']}", headers=case["auth"]["foreign_guard"])
    assert foreign.status_code == 404 and foreign.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    forbidden = case["client"].get("/api/v1/security/shifts", headers=case["auth"]["cskh"])
    assert forbidden.status_code == 403

    started = case["client"].post(f"/api/v1/security/shifts/{shift['id']}/start", headers=case["auth"]["guard_a"], json={"expected_version": shift["version"]})
    assert started.status_code == 200, started.text
    shift = started.json()
    handoff = case["client"].post(
        f"/api/v1/security/shifts/{shift['id']}/handoffs",
        headers=with_key(case, "guard_a", "security-handoff-001"),
        json={"received_by_id": str(case["guards"]["guard_b"].id), "summary": "Bàn giao tình trạng cổng chính."},
    )
    assert handoff.status_code == 201, handoff.text
    replay_handoff = case["client"].post(
        f"/api/v1/security/shifts/{shift['id']}/handoffs",
        headers=with_key(case, "guard_a", "security-handoff-001"),
        json={"received_by_id": str(case["guards"]["guard_b"].id), "summary": "Bàn giao tình trạng cổng chính."},
    )
    assert replay_handoff.status_code == 201 and len(replay_handoff.json()["handoffs"]) == 1

    visitor = case["client"].post(
        f"/api/v1/security/shifts/{shift['id']}/visitors",
        headers=with_key(case, "guard_a", "security-visitor-001"),
        json={"visitor_name": "Khách kiểm tra PCCC", "visit_purpose": "Kiểm tra thiết bị định kỳ", "document_reference": "CCCD-MASKED", "checked_in_at": datetime.now(UTC).isoformat()},
    )
    assert visitor.status_code == 201 and len(visitor.json()["visitors"]) == 1

    first, second = visitor.json()["patrol_windows"]
    logged = case["client"].post(
        f"/api/v1/security/patrol-windows/{first['id']}/logs",
        headers=with_key(case, "guard_a", "patrol-checkin-001"),
        json={"event_type": "CHECK_IN", "note": "Đã đến điểm", "occurred_at": datetime.now(UTC).isoformat()},
    )
    assert logged.status_code == 201 and logged.json()["status"] == "SCHEDULED"
    completed = case["client"].post(
        f"/api/v1/security/patrol-windows/{first['id']}/complete",
        headers=case["auth"]["guard_a"], json={"expected_version": logged.json()["version"], "note": "Điểm an toàn"},
    )
    assert completed.status_code == 200 and completed.json()["status"] == "COMPLETED"
    missing_reason = case["client"].post(
        f"/api/v1/security/patrol-windows/{second['id']}/missed",
        headers=case["auth"]["guard_a"], json={"expected_version": second["version"], "reason": "Phong tỏa tạm thời để xử lý sự cố"},
    )
    assert missing_reason.status_code == 200 and missing_reason.json()["status"] == "MISSED"
    assert missing_reason.json()["completed_at"] is None
    dashboard = case["client"].get("/api/v1/security/dashboard", headers=case["auth"]["guard_a"])
    assert dashboard.status_code == 200
    assert [(item["patrol_point_name"], item["missed_reason"]) for item in dashboard.json()["exceptions"]] == [
        (second["patrol_point_name"], "Phong tỏa tạm thời để xử lý sự cố"),
    ]

    with case["database"].get_session() as session:
        handoff_id = UUID(replay_handoff.json()["handoffs"][0]["id"])
        with pytest.raises(DBAPIError):
            session.execute(update(SecurityShiftHandoff).where(SecurityShiftHandoff.id == handoff_id).values(summary="mutated"))
        session.rollback()
        with pytest.raises(DBAPIError):
            session.execute(delete(SecurityShiftHandoff).where(SecurityShiftHandoff.id == handoff_id))
        session.rollback()


def test_ac43_high_incident_escalates_acknowledges_and_requires_evidence_to_close(security_case):
    case = security_case
    shift, _ = _create_shift(case, "security-incident-shift-001")
    shift = case["client"].post(f"/api/v1/security/shifts/{shift['id']}/start", headers=case["auth"]["guard_a"], json={"expected_version": shift["version"]}).json()
    window = shift["patrol_windows"][0]
    created = case["client"].post(
        "/api/v1/security/incidents", headers=with_key(case, "guard_a", "security-incident-high-001"),
        json={"patrol_window_id": window["id"], "incident_type": "FIRE", "severity": "HIGH", "title": "Khói tại phòng kỹ thuật", "description": "Phát hiện khói cần kích hoạt quy trình PCCC.", "occurred_at": datetime.now(UTC).isoformat()},
    )
    assert created.status_code == 201, created.text
    incident = created.json()
    assert {item["target_role"] for item in incident["escalations"]} == {"security", "director"}
    assert all(item["acknowledgement"] is None for item in incident["escalations"])
    triaged = _transition(case, incident, "guard_a", "TRIAGED")
    assert triaged.status_code == 200
    incident = triaged.json()
    progressing = _transition(case, incident, "guard_a", "IN_PROGRESS")
    assert progressing.status_code == 200
    resolved = _transition(case, progressing.json(), "guard_a", "RESOLVED", conclusion="Đã cô lập khu vực và bàn giao PCCC.")
    assert resolved.status_code == 200
    close_without_evidence = _transition(case, resolved.json(), "director", "CLOSED")
    assert close_without_evidence.status_code == 422 and close_without_evidence.json()["error"]["code"] == "ERR-INCIDENT-CLOSE-REQUIREMENTS"

    evidence = case["client"].post(
        f"/api/v1/security/incidents/{incident['id']}/evidence", headers=with_key(case, "guard_a", "security-evidence-001"),
        json={"evidence_type": "REPORT", "description": "Biên bản kiểm tra PCCC đã được ghi nhận.", "storage_reference": "incident-report-ref"},
    )
    assert evidence.status_code == 201
    incident = evidence.json()
    for escalation in incident["escalations"]:
        actor = "guard_a" if escalation["target_role"] == "security" else "director"
        acknowledged = case["client"].post(
            f"/api/v1/security/incidents/{incident['id']}/escalations/{escalation['id']}/acknowledgements",
            headers=with_key(case, actor, f"security-ack-{escalation['target_role']}-001"),
            json={"note": "Đã tiếp nhận escalation."},
        )
        assert acknowledged.status_code == 201, acknowledged.text
        incident = acknowledged.json()
    closed = _transition(case, incident, "director", "CLOSED")
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "CLOSED" and closed.json()["closed_at"]
