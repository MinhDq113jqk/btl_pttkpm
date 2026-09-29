"""R3 AC-42/AC-43 acceptance tests against the disposable PostgreSQL cluster."""
from datetime import UTC, datetime, timedelta
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.operations import IncidentEscalation, PatrolPoint, SecurityIncident, SecurityShift, SecurityShiftHandoff
from test_r2_integration import r2_case, with_key
from auth_test_support import mint_session_token


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R3 tests require its disposable PostgreSQL cluster",
)]


def _auth(case, account, site_index=0):
    token = mint_session_token(
        case["database"], account.id, case["settings"].auth_secret(),
        claims={"active_site_id": str(case["sites"][site_index].id)},
    )
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


def test_security_dashboard_shows_scoped_standalone_incidents(security_case):
    case = security_case
    now = datetime.now(UTC)
    local_code = f"R3-STANDALONE-{uuid4().hex[:8]}"
    foreign_code = f"R3-FOREIGN-{uuid4().hex[:8]}"
    with case["database"].get_session() as session:
        session.add_all([
            SecurityIncident(
                tenant_id=case["tenant"].id, site_id=case["sites"][0].id,
                building_id=case["buildings"][0].id, code=local_code,
                incident_type="SECURITY", severity="LOW", status="NEW",
                title="Synthetic standalone incident", description="Synthetic incident",
                occurred_at=now, reported_by_id=case["guards"]["guard_a"].id,
            ),
            SecurityIncident(
                tenant_id=case["tenant"].id, site_id=case["sites"][1].id,
                building_id=case["buildings"][1].id, code=foreign_code,
                incident_type="SECURITY", severity="LOW", status="NEW",
                title="Synthetic foreign incident", description="Synthetic incident",
                occurred_at=now, reported_by_id=case["foreign_guard"].id,
            ),
        ])
        session.commit()

    director = case["client"].get("/api/v1/security/dashboard", headers=case["auth"]["director"])
    reporter = case["client"].get("/api/v1/security/dashboard", headers=case["auth"]["guard_a"])
    other_guard = case["client"].get("/api/v1/security/dashboard", headers=case["auth"]["guard_b"])
    assert director.status_code == reporter.status_code == other_guard.status_code == 200
    assert local_code in {item["code"] for item in director.json()["incidents"]}
    assert foreign_code not in {item["code"] for item in director.json()["incidents"]}
    assert local_code in {item["code"] for item in reporter.json()["incidents"]}
    assert local_code not in {item["code"] for item in other_guard.json()["incidents"]}


def test_imported_standalone_incident_lifecycle_and_building_scope(security_case):
    case = security_case
    site = case["sites"][0]
    reporter = case["guards"]["guard_a"]
    with case["database"].get_session() as session:
        other_building = Building(site_id=site.id, code=f"R3-INC-{uuid4().hex[:8]}", name="Synthetic other building")
        session.add(other_building)
        session.flush()
        own = SecurityIncident(
            tenant_id=case["tenant"].id, site_id=site.id, building_id=case["buildings"][0].id,
            patrol_window_id=None, code=f"R3-IMPORTED-{uuid4().hex[:8]}",
            incident_type="SECURITY", severity="HIGH", status="NEW",
            title="Synthetic imported incident", description="Synthetic incident",
            occurred_at=datetime.now(UTC), reported_by_id=reporter.id,
        )
        foreign = SecurityIncident(
            tenant_id=case["tenant"].id, site_id=site.id, building_id=other_building.id,
            patrol_window_id=None, code=f"R3-FOREIGN-{uuid4().hex[:8]}",
            incident_type="SECURITY", severity="HIGH", status="NEW",
            title="Synthetic foreign incident", description="Synthetic incident",
            occurred_at=datetime.now(UTC), reported_by_id=reporter.id,
        )
        session.add_all([own, foreign])
        session.flush()
        for incident in (own, foreign):
            session.add_all(IncidentEscalation(
                security_incident_id=incident.id, target_role=role,
                escalated_by_id=reporter.id, reason="Synthetic imported escalation",
            ) for role in ("security", "director"))
        session.commit()

    reporter_headers = case["auth"]["guard_a"]
    other_guard_headers = case["auth"]["guard_b"]
    own_id = str(own.id)
    foreign_id = str(foreign.id)
    with case["database"].get_session() as session:
        foreign_security_ack_id = session.scalar(select(IncidentEscalation.id).where(
            IncidentEscalation.security_incident_id == foreign.id,
            IncidentEscalation.target_role == "security",
        ))
    dashboard = case["client"].get("/api/v1/security/dashboard", headers=reporter_headers)
    assert dashboard.status_code == 200, dashboard.text
    own_view = next(item for item in dashboard.json()["incidents"] if item["id"] == own_id)
    assert foreign_id not in {item["id"] for item in dashboard.json()["incidents"]}
    security_ack = next(item for item in own_view["escalations"] if item["target_role"] == "security")
    director_ack = next(item for item in own_view["escalations"] if item["target_role"] == "director")

    blocked = [
        case["client"].post(
            f"/api/v1/security/incidents/{own_id}/evidence",
            headers=other_guard_headers | {"Idempotency-Key": f"r3-other-evidence-{uuid4().hex}"},
            json={"evidence_type": "NOTE", "description": "Synthetic note"},
        ),
        case["client"].post(
            f"/api/v1/security/incidents/{own_id}/transition",
            headers=other_guard_headers,
            json={"expected_version": 1, "status": "TRIAGED"},
        ),
        case["client"].post(
            f"/api/v1/security/incidents/{foreign_id}/evidence",
            headers=reporter_headers | {"Idempotency-Key": f"r3-foreign-evidence-{uuid4().hex}"},
            json={"evidence_type": "NOTE", "description": "Synthetic note"},
        ),
        case["client"].post(
            f"/api/v1/security/incidents/{foreign_id}/transition",
            headers=reporter_headers,
            json={"expected_version": 1, "status": "TRIAGED"},
        ),
        case["client"].post(
            f"/api/v1/security/incidents/{foreign_id}/escalations/{foreign_security_ack_id}/acknowledgements",
            headers=reporter_headers | {"Idempotency-Key": f"r3-foreign-ack-{uuid4().hex}"},
            json={"note": "Synthetic acknowledgement"},
        ),
    ]
    for response in blocked:
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"

    denied_role = case["client"].post(
        f"/api/v1/security/incidents/{own_id}/escalations/{director_ack['id']}/acknowledgements",
        headers=reporter_headers | {"Idempotency-Key": f"r3-wrong-role-{uuid4().hex}"},
        json={"note": "Synthetic acknowledgement"},
    )
    assert denied_role.status_code == 403

    evidence_headers = reporter_headers | {"Idempotency-Key": f"r3-imported-evidence-{uuid4().hex}"}
    evidence = case["client"].post(
        f"/api/v1/security/incidents/{own_id}/evidence", headers=evidence_headers,
        json={"evidence_type": "REPORT", "description": "Synthetic imported evidence"},
    )
    assert evidence.status_code == 201, evidence.text
    replay = case["client"].post(
        f"/api/v1/security/incidents/{own_id}/evidence", headers=evidence_headers,
        json={"evidence_type": "REPORT", "description": "Synthetic imported evidence"},
    )
    assert replay.status_code == 201 and len(replay.json()["evidence"]) == 1

    for escalation, headers in ((security_ack, reporter_headers), (director_ack, case["auth"]["director"])):
        ack_headers = headers | {"Idempotency-Key": f"r3-imported-ack-{uuid4().hex}"}
        acknowledged = case["client"].post(
            f"/api/v1/security/incidents/{own_id}/escalations/{escalation['id']}/acknowledgements",
            headers=ack_headers, json={"note": "Synthetic acknowledgement"},
        )
        assert acknowledged.status_code == 201, acknowledged.text
        replay = case["client"].post(
            f"/api/v1/security/incidents/{own_id}/escalations/{escalation['id']}/acknowledgements",
            headers=ack_headers, json={"note": "Synthetic acknowledgement"},
        )
        assert replay.status_code == 201, replay.text

    incident = evidence.json()
    for status in ("TRIAGED", "IN_PROGRESS", "RESOLVED"):
        transitioned = _transition(case, incident, "guard_a", status,
                                   conclusion="Synthetic resolution" if status == "RESOLVED" else None)
        assert transitioned.status_code == 200, transitioned.text
        incident = transitioned.json()
    closed = _transition(case, incident, "director", "CLOSED")
    assert closed.status_code == 200, closed.text
    assert closed.json()["patrol_window_id"] is None
    assert closed.json()["status"] == "CLOSED"


def test_revoked_building_grant_hides_assigned_security_resources(security_case):
    case = security_case
    site = case["sites"][0]
    building_b1 = case["buildings"][0]
    with case["database"].get_session() as session:
        building_b2 = Building(site_id=site.id, code=f"B2-{uuid4().hex[:8]}", name="Synthetic B2")
        guard = Account(
            tenant_id=case["tenant"].id, username=f"r3_multibuilding_{uuid4().hex}",
            full_name="R3 multi-building guard",
            hashed_password=case["accounts"]["cskh"].hashed_password,
        )
        session.add_all([building_b2, guard])
        session.flush()
        grant_b1 = AccountRole(
            account_id=guard.id, role="security", site_id=site.id, building_id=building_b1.id,
        )
        session.add_all([
            grant_b1,
            AccountRole(account_id=guard.id, role="security", site_id=site.id, building_id=building_b2.id),
        ])
        points_b2 = [PatrolPoint(
            tenant_id=case["tenant"].id, site_id=site.id, building_id=building_b2.id,
            code=f"R3-B2-{uuid4().hex[:8]}", name=f"Synthetic B2 point {position}",
            is_active=True,
        ) for position in (1, 2)]
        session.add_all(points_b2)
        session.commit()

    headers = _auth(case, guard)
    start = datetime.now(UTC) + timedelta(days=1)

    def create_shift(building, points):
        body = {
            "building_id": str(building.id), "assignee_id": str(guard.id),
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": (start + timedelta(hours=3)).isoformat(),
            "patrol_windows": [
                {
                    "patrol_point_id": str(point.id),
                    "window_start_at": (start + timedelta(hours=position)).isoformat(),
                    "window_end_at": (start + timedelta(hours=position, minutes=30)).isoformat(),
                }
                for position, point in enumerate(points)
            ],
        }
        response = case["client"].post(
            "/api/v1/security/shifts",
            headers=with_key(case, "director", f"security-revocation-{uuid4().hex}"),
            json=body,
        )
        assert response.status_code == 201, response.text
        return response.json()

    shift_b1 = create_shift(building_b1, case["points"])
    shift_b2 = create_shift(building_b2, points_b2)
    for shift in (shift_b1, shift_b2):
        missed = case["client"].post(
            f"/api/v1/security/patrol-windows/{shift['patrol_windows'][0]['id']}/missed",
            headers=headers,
            json={"expected_version": 1, "reason": "Synthetic missed patrol"},
        )
        assert missed.status_code == 200, missed.text

    incident_codes = {}
    with case["database"].get_session() as session:
        for label, building, shift in (("b1", building_b1, shift_b1), ("b2", building_b2, shift_b2)):
            incident_codes[label] = {}
            for kind, patrol_window_id in (
                ("linked", UUID(shift["patrol_windows"][1]["id"])),
                ("standalone", None),
            ):
                incident = SecurityIncident(
                    tenant_id=case["tenant"].id, site_id=site.id, building_id=building.id,
                    patrol_window_id=patrol_window_id, code=f"R3-REV-{uuid4().hex[:10]}",
                    incident_type="SECURITY", severity="LOW", status="NEW",
                    title=f"Synthetic {label} {kind} incident", description="Synthetic incident",
                    occurred_at=datetime.now(UTC), reported_by_id=guard.id,
                )
                session.add(incident)
                session.flush()
                incident_codes[label][kind] = (incident.code, incident.id)
        session.commit()

    before = case["client"].get("/api/v1/security/dashboard", headers=headers)
    assert before.status_code == 200, before.text
    assert {shift_b1["id"], shift_b2["id"]} <= {item["id"] for item in before.json()["shifts"]}
    with case["database"].get_session() as session:
        session.delete(session.get(AccountRole, grant_b1.id))
        session.commit()

    assert case["client"].get("/api/v1/auth/me", headers=headers).status_code == 200
    listed = case["client"].get("/api/v1/security/shifts", headers=headers)
    dashboard = case["client"].get("/api/v1/security/dashboard", headers=headers)
    assert listed.status_code == dashboard.status_code == 200
    assert shift_b1["id"] not in {item["id"] for item in listed.json()["items"]}
    assert shift_b2["id"] in {item["id"] for item in listed.json()["items"]}
    assert shift_b1["id"] not in {item["id"] for item in dashboard.json()["shifts"]}
    assert shift_b2["id"] in {item["id"] for item in dashboard.json()["shifts"]}
    assert shift_b1["patrol_windows"][0]["id"] not in {item["id"] for item in dashboard.json()["exceptions"]}
    assert shift_b2["patrol_windows"][0]["id"] in {item["id"] for item in dashboard.json()["exceptions"]}
    visible_codes = {item["code"] for item in dashboard.json()["incidents"]}
    assert all(code not in visible_codes for code, _ in incident_codes["b1"].values())
    assert all(code in visible_codes for code, _ in incident_codes["b2"].values())

    blocked_requests = [
        case["client"].get(f"/api/v1/security/shifts/{shift_b1['id']}", headers=headers),
        case["client"].post(
            f"/api/v1/security/shifts/{shift_b1['id']}/start", headers=headers,
            json={"expected_version": shift_b1["version"]},
        ),
        case["client"].post(
            f"/api/v1/security/patrol-windows/{shift_b1['patrol_windows'][1]['id']}/logs",
            headers=headers | {"Idempotency-Key": f"security-revoked-log-{uuid4().hex}"},
            json={"event_type": "NOTE", "note": "Synthetic note", "occurred_at": datetime.now(UTC).isoformat()},
        ),
        case["client"].post(
            f"/api/v1/security/incidents/{incident_codes['b1']['linked'][1]}/evidence",
            headers=headers | {"Idempotency-Key": f"security-revoked-evidence-{uuid4().hex}"},
            json={"evidence_type": "NOTE", "description": "Synthetic evidence"},
        ),
        case["client"].post(
            f"/api/v1/security/incidents/{incident_codes['b1']['linked'][1]}/transition",
            headers=headers, json={"expected_version": 1, "status": "TRIAGED"},
        ),
        case["client"].post(
            f"/api/v1/security/incidents/{incident_codes['b1']['standalone'][1]}/evidence",
            headers=headers | {"Idempotency-Key": f"security-revoked-standalone-{uuid4().hex}"},
            json={"evidence_type": "NOTE", "description": "Synthetic evidence"},
        ),
        case["client"].post(
            f"/api/v1/security/incidents/{incident_codes['b1']['standalone'][1]}/transition",
            headers=headers, json={"expected_version": 1, "status": "TRIAGED"},
        ),
    ]
    for response in blocked_requests:
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"

    assert case["client"].get(f"/api/v1/security/shifts/{shift_b2['id']}", headers=headers).status_code == 200
    allowed = case["client"].post(
        f"/api/v1/security/incidents/{incident_codes['b2']['linked'][1]}/transition",
        headers=headers, json={"expected_version": 1, "status": "TRIAGED"},
    )
    assert allowed.status_code == 200, allowed.text
    allowed_standalone = case["client"].post(
        f"/api/v1/security/incidents/{incident_codes['b2']['standalone'][1]}/transition",
        headers=headers, json={"expected_version": 1, "status": "TRIAGED"},
    )
    assert allowed_standalone.status_code == 200, allowed_standalone.text


def test_mixed_manager_security_grants_and_site_only_security_fail_closed(security_case):
    case = security_case
    site = case["sites"][0]
    building_b1 = case["buildings"][0]
    with case["database"].get_session() as session:
        building_b2 = Building(site_id=site.id, code=f"B2-{uuid4().hex[:8]}", name="Mixed-role B2")
        mixed = Account(
            tenant_id=case["tenant"].id, username=f"r3_mixed_{uuid4().hex}",
            full_name="Mixed manager and guard",
            hashed_password=case["accounts"]["cskh"].hashed_password,
        )
        site_only = Account(
            tenant_id=case["tenant"].id, username=f"r3_site_only_{uuid4().hex}",
            full_name="Site-only guard",
            hashed_password=case["accounts"]["cskh"].hashed_password,
        )
        session.add_all([building_b2, mixed, site_only])
        session.flush()
        session.add_all([
            AccountRole(account_id=mixed.id, role="security", site_id=site.id, building_id=building_b1.id),
            AccountRole(account_id=mixed.id, role="director", site_id=site.id, building_id=building_b2.id),
            AccountRole(account_id=site_only.id, role="security", site_id=site.id, building_id=None),
            AccountRole(account_id=case["guards"]["guard_b"].id, role="security",
                        site_id=site.id, building_id=building_b2.id),
        ])
        point_b2 = PatrolPoint(
            tenant_id=case["tenant"].id, site_id=site.id, building_id=building_b2.id,
            code=f"R3-MIX-{uuid4().hex[:8]}", name="Mixed-role B2 point", is_active=True,
        )
        session.add(point_b2)
        session.commit()

    mixed_headers = _auth(case, mixed)
    site_only_headers = _auth(case, site_only)
    start = datetime.now(UTC) + timedelta(days=2)

    def create_shift(building, assignee, point, day_offset):
        shift_start = start + timedelta(days=day_offset)
        return case["client"].post(
            "/api/v1/security/shifts",
            headers=with_key(case, "director", f"security-mixed-{uuid4().hex}"),
            json={
                "building_id": str(building.id), "assignee_id": str(assignee.id),
                "scheduled_start_at": shift_start.isoformat(),
                "scheduled_end_at": (shift_start + timedelta(hours=2)).isoformat(),
                "patrol_windows": [{
                    "patrol_point_id": str(point.id),
                    "window_start_at": shift_start.isoformat(),
                    "window_end_at": (shift_start + timedelta(minutes=30)).isoformat(),
                }],
            },
        )

    own_b1 = create_shift(building_b1, mixed, case["points"][0], 0)
    other_b1 = create_shift(building_b1, case["guards"]["guard_a"], case["points"][0], 1)
    manager_b2 = create_shift(building_b2, case["guards"]["guard_b"], point_b2, 2)
    for response in (own_b1, other_b1, manager_b2):
        assert response.status_code == 201, response.text
    rejected = create_shift(building_b1, site_only, case["points"][0], 3)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "ERR-INVALID-ASSIGNEE"
    assignees = case["client"].get(
        f"/api/v1/security/assignees?building_id={building_b1.id}",
        headers=case["auth"]["director"],
    )
    assert assignees.status_code == 200
    assert str(site_only.id) not in {item["id"] for item in assignees.json()}

    codes = {}
    with case["database"].get_session() as session:
        invalid_assignment = SecurityShift(
            tenant_id=case["tenant"].id, site_id=site.id, building_id=building_b1.id,
            assigned_to_id=site_only.id,
            scheduled_start_at=start + timedelta(days=4),
            scheduled_end_at=start + timedelta(days=4, hours=2),
            status="PLANNED",
        )
        session.add(invalid_assignment)
        for label, building, reporter, window_id in (
            ("own_b1", building_b1, mixed, UUID(own_b1.json()["patrol_windows"][0]["id"])),
            ("other_b1", building_b1, case["guards"]["guard_a"], None),
            ("manager_b2", building_b2, case["guards"]["guard_b"], None),
            ("site_only", building_b1, site_only, None),
        ):
            code = f"R3-MIX-{uuid4().hex[:10]}"
            session.add(SecurityIncident(
                tenant_id=case["tenant"].id, site_id=site.id, building_id=building.id,
                patrol_window_id=window_id, code=code, incident_type="SECURITY",
                severity="LOW", status="NEW", title=f"Synthetic {label} incident",
                description="Synthetic incident", occurred_at=datetime.now(UTC),
                reported_by_id=reporter.id,
            ))
            codes[label] = code
        session.commit()

    shifts = case["client"].get("/api/v1/security/shifts", headers=mixed_headers)
    dashboard = case["client"].get("/api/v1/security/dashboard", headers=mixed_headers)
    assert shifts.status_code == dashboard.status_code == 200
    visible_shift_ids = {item["id"] for item in shifts.json()["items"]}
    assert {own_b1.json()["id"], manager_b2.json()["id"]} <= visible_shift_ids
    assert other_b1.json()["id"] not in visible_shift_ids
    assert str(invalid_assignment.id) not in visible_shift_ids
    assert visible_shift_ids == {item["id"] for item in dashboard.json()["shifts"]}
    visible_codes = {item["code"] for item in dashboard.json()["incidents"]}
    assert {codes["own_b1"], codes["manager_b2"]} <= visible_codes
    assert codes["other_b1"] not in visible_codes
    assert codes["site_only"] not in visible_codes
    with case["database"].get_session() as session:
        manager_incident_id = session.scalar(select(SecurityIncident.id).where(
            SecurityIncident.code == codes["manager_b2"],
        ))
        other_incident_id = session.scalar(select(SecurityIncident.id).where(
            SecurityIncident.code == codes["other_b1"],
        ))
    manager_transition = case["client"].post(
        f"/api/v1/security/incidents/{manager_incident_id}/transition",
        headers=mixed_headers, json={"expected_version": 1, "status": "TRIAGED"},
    )
    assert manager_transition.status_code == 200, manager_transition.text
    other_transition = case["client"].post(
        f"/api/v1/security/incidents/{other_incident_id}/transition",
        headers=mixed_headers, json={"expected_version": 1, "status": "TRIAGED"},
    )
    assert other_transition.status_code == 404
    assert other_transition.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"

    for route in ("/api/v1/security/shifts", "/api/v1/security/dashboard"):
        response = case["client"].get(route, headers=site_only_headers)
        assert response.status_code == 200, response.text
        assert response.json().get("items", response.json().get("shifts")) == []
        if route.endswith("dashboard"):
            assert response.json()["incidents"] == []
    direct = case["client"].get(
        f"/api/v1/security/shifts/{invalid_assignment.id}", headers=site_only_headers,
    )
    assert direct.status_code == 404
    assert direct.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"

    def high_incident(shift, label):
        created = case["client"].post(
            "/api/v1/security/incidents",
            headers=mixed_headers | {"Idempotency-Key": f"security-mixed-incident-{uuid4().hex}"},
            json={
                "patrol_window_id": shift["patrol_windows"][0]["id"],
                "incident_type": "SECURITY", "severity": "HIGH",
                "title": f"Synthetic {label} escalation", "description": "Synthetic incident",
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )
        assert created.status_code == 201, created.text
        return created.json()

    incident_b1 = high_incident(own_b1.json(), "B1")
    incident_b2 = high_incident(manager_b2.json(), "B2")
    director_b1 = next(item for item in incident_b1["escalations"] if item["target_role"] == "director")
    security_b1 = next(item for item in incident_b1["escalations"] if item["target_role"] == "security")
    director_b2 = next(item for item in incident_b2["escalations"] if item["target_role"] == "director")

    def acknowledge(incident, escalation):
        return case["client"].post(
            f"/api/v1/security/incidents/{incident['id']}/escalations/{escalation['id']}/acknowledgements",
            headers=mixed_headers | {"Idempotency-Key": f"security-mixed-ack-{uuid4().hex}"},
            json={"note": "Synthetic acknowledgement"},
        )

    denied = acknowledge(incident_b1, director_b1)
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    accepted_security = acknowledge(incident_b1, security_b1)
    accepted_director = acknowledge(incident_b2, director_b2)
    assert accepted_security.status_code == accepted_director.status_code == 201
    assert next(item for item in accepted_security.json()["escalations"]
                if item["target_role"] == "director")["acknowledgement"] is None


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
