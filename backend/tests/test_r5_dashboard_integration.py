"""R5 CAP-BI dashboard and audit-explorer acceptance tests on isolated PostgreSQL."""
from datetime import UTC, date, datetime, timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_token
from app.models.account import Account, AccountRole
from app.models.billing import AccountingPeriod, ArLedgerEntry, BillingAccount
from app.models.building import Building
from app.models.maintenance import Asset, MaintenanceOccurrence, MaintenancePlan
from app.models.operations import (
    CleaningArea,
    CleaningRoute,
    CleaningRouteStop,
    CleaningShift,
    CleaningTask,
    SecurityIncident,
)
from app.models.platform import AuditEvent
from app.models.service import ServiceRequest
from app.models.unit import Unit
from test_r2_integration import r2_case


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; R5 dashboard tests require its disposable PostgreSQL cluster",
)]


AS_OF = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)


def _restricted_director_auth(case, building_id):
    with case["database"].get_session() as session:
        account = Account(
            tenant_id=case["tenant"].id,
            username=f"r5_dashboard_director_{uuid4().hex}",
            full_name="R5 building dashboard director",
            hashed_password=case["accounts"]["director"].hashed_password,
        )
        session.add(account)
        session.flush()
        session.add(AccountRole(
            account_id=account.id,
            role="director",
            site_id=case["sites"][0].id,
            building_id=building_id,
        ))
        session.commit()
    token = create_token({
        "sub": str(account.id),
        "active_site_id": str(case["sites"][0].id),
        "purpose": "session",
    }, case["settings"].auth_secret())
    return {"Authorization": f"Bearer {token}"}


def _seed_fixed_oracle(case):
    """Create rows whose current state changes after AS_OF where supported."""
    correlation_id = uuid4()
    with case["database"].get_session() as session:
        tenant = case["tenant"]
        site = case["sites"][0]
        building = case["buildings"][0]
        unit = case["units"][0]
        category = case["categories"][0]
        actor = case["accounts"]["director"]

        overdue = ServiceRequest(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
            category_id=category.id, code=f"R5-SLA-{uuid4().hex[:8]}", title="Overdue at cutoff",
            description="fixed oracle", priority="HIGH", status="RESOLVED",
            sla_started_at=AS_OF - timedelta(hours=5), sla_duration_minutes=60,
            owner_account_id=actor.id, created_by_id=actor.id, updated_by_id=actor.id,
            resolved_at=AS_OF + timedelta(hours=1), created_at=AS_OF - timedelta(hours=5),
        )
        resolved_before = ServiceRequest(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
            category_id=category.id, code=f"R5-SLA-CLOSED-{uuid4().hex[:8]}", title="Resolved before cutoff",
            description="fixed oracle", priority="HIGH", status="RESOLVED",
            sla_started_at=AS_OF - timedelta(hours=5), sla_duration_minutes=60,
            owner_account_id=actor.id, created_by_id=actor.id, updated_by_id=actor.id,
            resolved_at=AS_OF - timedelta(hours=2), created_at=AS_OF - timedelta(hours=5),
        )
        session.add_all((overdue, resolved_before))

        asset = Asset(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=unit.id,
            code=f"R5-ASSET-{uuid4().hex[:8]}", name="Dashboard pump", description="fixed oracle",
            created_by_id=actor.id, updated_by_id=actor.id,
        )
        session.add(asset)
        session.flush()
        plan = MaintenancePlan(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id, asset_id=asset.id,
            code=f"R5-PLAN-{uuid4().hex[:8]}", title="Pump maintenance", interval_days=30,
            next_due_at=AS_OF + timedelta(days=30), checklist_template=[],
            created_by_id=actor.id, updated_by_id=actor.id,
        )
        session.add(plan)
        session.flush()
        due_at_cutoff = MaintenanceOccurrence(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id, plan_id=plan.id,
            due_at=AS_OF - timedelta(days=1), status="COMPLETED",
            completed_at=AS_OF + timedelta(hours=2), created_by_id=actor.id,
            updated_by_id=actor.id, created_at=AS_OF - timedelta(days=2),
        )
        completed_before = MaintenanceOccurrence(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id, plan_id=plan.id,
            due_at=AS_OF - timedelta(days=2), status="COMPLETED",
            completed_at=AS_OF - timedelta(days=1), created_by_id=actor.id,
            updated_by_id=actor.id, created_at=AS_OF - timedelta(days=3),
        )
        session.add_all((due_at_cutoff, completed_before))

        route = CleaningRoute(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            code=f"R5-ROUTE-{uuid4().hex[:8]}", name="Dashboard route",
            created_by_id=actor.id, updated_by_id=actor.id,
        )
        area = CleaningArea(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            code=f"R5-AREA-{uuid4().hex[:8]}", name="Dashboard area",
            created_by_id=actor.id, updated_by_id=actor.id,
        )
        session.add_all((route, area))
        session.flush()
        stop = CleaningRouteStop(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            route_id=route.id, cleaning_area_id=area.id, position=1, checklist_template=[],
        )
        shift = CleaningShift(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id, route_id=route.id,
            scheduled_start_at=AS_OF - timedelta(hours=3), scheduled_end_at=AS_OF - timedelta(hours=1),
            created_by_id=actor.id, updated_by_id=actor.id,
        )
        session.add_all((stop, shift))
        session.flush()
        rework = CleaningTask(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id, shift_id=shift.id,
            route_stop_id=stop.id, status="REWORK_REQUIRED", submitted_at=AS_OF - timedelta(hours=1),
            created_by_id=actor.id, updated_by_id=actor.id, created_at=AS_OF - timedelta(hours=3),
        )
        session.add(rework)

        open_at_cutoff = SecurityIncident(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            code=f"R5-INC-{uuid4().hex[:8]}", incident_type="SECURITY", severity="HIGH",
            status="CLOSED", title="Open at cutoff", description="fixed oracle",
            occurred_at=AS_OF - timedelta(hours=2), reported_by_id=actor.id,
            created_by_id=actor.id, updated_by_id=actor.id, closed_at=AS_OF + timedelta(hours=2),
            created_at=AS_OF - timedelta(hours=2),
        )
        closed_before = SecurityIncident(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            code=f"R5-INC-CLOSED-{uuid4().hex[:8]}", incident_type="FIRE", severity="LOW",
            status="CLOSED", title="Closed before cutoff", description="fixed oracle",
            occurred_at=AS_OF - timedelta(hours=3), reported_by_id=actor.id,
            created_by_id=actor.id, updated_by_id=actor.id, closed_at=AS_OF - timedelta(hours=1),
            created_at=AS_OF - timedelta(hours=3),
        )
        session.add_all((open_at_cutoff, closed_before))

        debt_unit = Unit(
            building_id=building.id, unit_number=f"R5-AR-{uuid4().hex[:8]}", floor=90,
            area_m2=50, status="occupied",
        )
        session.add(debt_unit)
        session.flush()
        billing_account = BillingAccount(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id, unit_id=debt_unit.id,
            account_number=f"R5-AR-{uuid4().hex[:8]}", opened_on=date(2026, 1, 1),
        )
        period = AccountingPeriod(
            tenant_id=tenant.id, site_id=site.id, building_id=building.id,
            period_key=f"R5-2026-05-{uuid4().hex[:6]}", period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31), cutoff_at=AS_OF,
        )
        session.add_all((billing_account, period))
        session.flush()
        entries = [
            ArLedgerEntry(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                billing_account_id=billing_account.id, accounting_period_id=period.id,
                entry_type="INVOICE_ISSUED", source_type="R5_ORACLE", source_id=uuid4(),
                debit_vnd=500_000, credit_vnd=0, effective_at=AS_OF - timedelta(days=1),
                created_by_id=actor.id,
            ),
            ArLedgerEntry(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                billing_account_id=billing_account.id, accounting_period_id=period.id,
                entry_type="PAYMENT_RECEIVED", source_type="R5_ORACLE", source_id=uuid4(),
                debit_vnd=0, credit_vnd=200_000, effective_at=AS_OF - timedelta(hours=1),
                created_by_id=actor.id,
            ),
            ArLedgerEntry(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id,
                billing_account_id=billing_account.id, accounting_period_id=period.id,
                entry_type="INVOICE_ISSUED", source_type="R5_ORACLE", source_id=uuid4(),
                debit_vnd=900_000, credit_vnd=0, effective_at=AS_OF + timedelta(days=1),
                created_by_id=actor.id,
            ),
        ]
        session.add_all(entries)
        session.flush()
        session.add_all((
            AuditEvent(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, actor_account_id=actor.id,
                event_type="R5DashboardOraclePrepared", action="create", resource_type="BillingAccount",
                resource_id=billing_account.id, after_data={"amount_vnd": 300_000},
                correlation_id=correlation_id, created_at=AS_OF - timedelta(minutes=1),
            ),
            AuditEvent(
                tenant_id=tenant.id, site_id=site.id, building_id=building.id, actor_account_id=actor.id,
                event_type="R5DashboardOracleUpdatedAfterCutoff", action="update", resource_type="BillingAccount",
                resource_id=billing_account.id, after_data={"amount_vnd": 1_200_000},
                correlation_id=uuid4(), created_at=AS_OF + timedelta(minutes=1),
            ),
        ))
        session.commit()
        return {
            "correlation_id": correlation_id,
            "building_id": building.id,
            "overdue_id": overdue.id,
            "debt_account_id": billing_account.id,
        }


def _dashboard(case, headers):
    response = case["client"].get("/api/v1/dashboard", params={"as_of": AS_OF.isoformat()}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def dashboard_case(r2_case):
    return r2_case | {"dashboard_seed": _seed_fixed_oracle(r2_case)}


def test_ac25_fixed_oracle_dashboard_and_drill_down_reconcile(dashboard_case):
    case = dashboard_case
    seeded = case["dashboard_seed"]
    dashboard = _dashboard(case, case["auth"]["director"])
    assert datetime.fromisoformat(dashboard.pop("as_of").replace("Z", "+00:00")) == AS_OF
    assert dashboard == {
        "sla_overdue_count": 1,
        "maintenance_due_count": 1,
        "cleaning_rework_count": 1,
        "open_incident_count": 1,
        "ar_debt_vnd": 300_000,
    }

    expected_counts = {
        "sla_overdue": dashboard["sla_overdue_count"],
        "maintenance_due": dashboard["maintenance_due_count"],
        "cleaning_rework": dashboard["cleaning_rework_count"],
        "open_incidents": dashboard["open_incident_count"],
    }
    for metric, count in expected_counts.items():
        response = case["client"].get(
            f"/api/v1/dashboard/drill-down/{metric}",
            params={"as_of": AS_OF.isoformat()}, headers=case["auth"]["director"],
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["metric"] == metric and len(body["items"]) == count
    debt = case["client"].get(
        "/api/v1/dashboard/drill-down/ar_debt",
        params={"as_of": AS_OF.isoformat()}, headers=case["auth"]["director"],
    )
    assert debt.status_code == 200
    assert sum(item["amount_vnd"] for item in debt.json()["items"]) == dashboard["ar_debt_vnd"]
    assert debt.json()["items"][0]["resource_id"] == str(seeded["debt_account_id"])

    audit = case["client"].get(
        "/api/v1/audit-events", params={
            "resource_type": "BillingAccount",
            "resource_id": str(seeded["debt_account_id"]),
            "as_of": AS_OF.isoformat(),
        },
        headers=case["auth"]["director"],
    )
    assert audit.status_code == 200, audit.text
    assert [(item["resource_id"], item["resource_type"], item["event_type"]) for item in audit.json()["items"]] == [
        (str(seeded["debt_account_id"]), "BillingAccount", "R5DashboardOraclePrepared"),
    ]


def test_dashboard_is_server_scoped_and_requires_a_timezone_aware_cutoff(dashboard_case):
    case = dashboard_case
    seeded = case["dashboard_seed"]
    restricted = _restricted_director_auth(case, seeded["building_id"])
    assert _dashboard(case, restricted)["sla_overdue_count"] == 1

    assert case["client"].get(
        "/api/v1/dashboard", params={"as_of": AS_OF.isoformat()}, headers=case["auth"]["cskh"],
    ).status_code == 403
    naive = case["client"].get(
        "/api/v1/dashboard", params={"as_of": "2026-05-15T12:00:00"}, headers=restricted,
    )
    assert naive.status_code == 422 and naive.json()["error"]["code"] == "ERR-VALIDATION"
    missing = case["client"].get("/api/v1/dashboard", headers=restricted)
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "ERR-VALIDATION"

    with case["database"].get_session() as session:
        assert session.scalar(select(ServiceRequest.id).where(ServiceRequest.id == seeded["overdue_id"])) is not None
