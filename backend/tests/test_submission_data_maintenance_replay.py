"""FCS-13 replay checks on the disposable PostgreSQL fixture."""

from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.account import Account, AccountRole
from app.models.maintenance import Asset, MaintenanceOccurrence, MaintenancePlan
from app.models.operations import (
    CleaningArea,
    CleaningChecklistResult,
    CleaningRoute,
    CleaningRouteStop,
    CleaningShift,
    CleaningTask,
)
from app.models.platform import IdempotencyRecord
from app.models.service import CaseRecord, WorkOrder
from app.models.submission_import import SubmissionExternalReference, SubmissionImportRun
from app.services.submission_data_operational_replay import replay_maintenance_cleaning
from app.services.submission_data_import import canonical_payload_sha256
from app.services.submission_data_replay import SubmissionReplayError
from app.services.r2 import utc_now
from test_r2_integration import r2_case


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; FCS-13 requires disposable PostgreSQL",
)]


def _run(case, stage="replay"):
    run = SubmissionImportRun(
        manifest_sha256=uuid4().hex + uuid4().hex,
        schema_version="fcs-test",
        source_kind="synthetic",
        stage=stage,
        status="APPLYING",
        correlation_id=uuid4(),
        workbook_count=12,
        total_rows=2,
    )
    return run


def test_fcs13_scheduler_and_cleaning_replay_are_idempotent_and_keep_rework_history(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        tenant = session.get(type(case["tenant"]), case["tenant"].id)
        tenant.code = tenant.code or f"R2-TENANT-{uuid4().hex[:8]}"
        site = session.get(type(case["sites"][0]), case["sites"][0].id)
        building = session.get(type(case["buildings"][0]), case["buildings"][0].id)
        actor = session.get(type(case["accounts"]["lead"]), case["accounts"]["lead"].id)
        cleaner = Account(
            tenant_id=tenant.id,
            username=f"fcs13_cleaner_{uuid4().hex[:8]}",
            full_name="FCS13 cleaner",
            hashed_password=actor.hashed_password,
        )
        session.add(cleaner)
        session.flush()
        session.add(AccountRole(
            account_id=cleaner.id,
            role="cleaning",
            site_id=site.id,
            building_id=building.id,
        ))
        asset = Asset(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            code=f"FCS13-ASSET-{uuid4().hex[:8]}",
            name="FCS13 pump",
            description="synthetic",
            status="ACTIVE",
            created_by_id=actor.id,
            updated_by_id=actor.id,
        )
        session.add(asset)
        session.flush()
        plan = MaintenancePlan(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            asset_id=asset.id,
            code="FCS13-PLAN",
            title="FCS13 maintenance",
            interval_days=30,
            next_due_at=datetime.now(UTC) - timedelta(days=1),
            checklist_template=[{"label": "inspect", "required": True}],
            evidence_required=True,
            created_by_id=actor.id,
            updated_by_id=actor.id,
        )
        route = CleaningRoute(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            code="FCS13-ROUTE",
            name="FCS13 route",
            created_by_id=actor.id,
            updated_by_id=actor.id,
        )
        area = CleaningArea(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            code="FCS13-AREA",
            name="FCS13 area",
            created_by_id=actor.id,
            updated_by_id=actor.id,
        )
        session.add_all([plan, route, area])
        session.flush()
        stop = CleaningRouteStop(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            route_id=route.id,
            cleaning_area_id=area.id,
            position=1,
            checklist_template=[{"label": "floor", "required": True}, {"label": "bins", "required": True}],
        )
        shift = CleaningShift(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            route_id=route.id,
            scheduled_start_at=datetime.now(UTC) - timedelta(hours=3),
            scheduled_end_at=datetime.now(UTC) - timedelta(hours=1),
            created_by_id=cleaner.id,
            updated_by_id=cleaner.id,
        )
        session.add_all([stop, shift])
        session.flush()
        task = CleaningTask(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            shift_id=shift.id,
            route_stop_id=stop.id,
            assigned_to_id=cleaner.id,
            created_by_id=cleaner.id,
            updated_by_id=cleaner.id,
        )
        session.add(task)
        session.flush()
        session.add_all(CleaningChecklistResult(
            cleaning_task_id=task.id,
            position=position,
            label=label,
            is_required=True,
        ) for position, label in enumerate(("floor", "bins", "quality"), 1))
        run = _run(case)
        session.add(run)
        session.flush()
        session.add_all([
            SubmissionExternalReference(
                import_run_id=run.id,
                tenant_id=tenant.id,
                source="maintenance",
                entity_type="Asset",
                source_key=asset.code,
                target_id=asset.id,
                payload_sha256=canonical_payload_sha256({"asset_code": asset.code}),
            ),
            SubmissionExternalReference(
                import_run_id=run.id,
                tenant_id=tenant.id,
                source="cleaning",
                entity_type="CleaningShift",
                source_key=f"{site.code}:FCS13-SHIFT",
                target_id=shift.id,
                payload_sha256=canonical_payload_sha256({"shift_code": "FCS13-SHIFT"}),
            ),
        ])
        session.flush()
        maintenance_row = {
            "tenant_code": tenant.code,
            "site_code": site.code,
            "building_code": building.code,
            "asset_code": asset.code,
            "maintenance_plan_code": plan.code,
        }
        cleaning_row = {
            "tenant_code": tenant.code,
            "site_code": site.code,
            "building_code": building.code,
            "shift_code": "FCS13-SHIFT",
            "status": "COMPLETED",
            "checklist_floor": "PASS",
            "checklist_bins": "FAIL",
            "quality_result": "REWORK",
            "rework_required": True,
        }
        first = replay_maintenance_cleaning(
            session,
            [maintenance_row],
            [cleaning_row],
            run,
            as_of_utc=datetime.now(UTC),
        )
        second = replay_maintenance_cleaning(
            session,
            [maintenance_row],
            [cleaning_row],
            run,
            as_of_utc=datetime.now(UTC),
        )
        assert first["maintenance_occurrences_created"] == 1
        assert first["maintenance_work_orders_created"] == 1
        assert first["cleaning_rework_cases"] == 1
        assert second["maintenance_rows"] == 1 and second["cleaning_rows"] == 1
        assert session.scalar(select(func.count(MaintenanceOccurrence.id)).where(MaintenanceOccurrence.plan_id == plan.id)) == 1
        occurrence_id = session.scalar(select(MaintenanceOccurrence.id).where(MaintenanceOccurrence.plan_id == plan.id))
        assert session.scalar(select(func.count(WorkOrder.id)).where(WorkOrder.maintenance_occurrence_id == occurrence_id)) == 1
        assert session.scalar(select(func.count(WorkOrder.id)).where(WorkOrder.cleaning_task_id == task.id)) == 1
        assert session.scalar(select(func.count(CaseRecord.id)).where(CaseRecord.source_work_order_id.is_not(None))) >= 1
        stored_task = session.get(CleaningTask, task.id)
        assert stored_task.status == "REWORK_REQUIRED"
        assert session.scalar(select(CleaningChecklistResult.result).where(
            CleaningChecklistResult.cleaning_task_id == task.id,
            CleaningChecklistResult.position == 2,
        )) == "FAIL"
        assert session.scalar(select(func.count(IdempotencyRecord.id)).where(
            IdempotencyRecord.tenant_id == tenant.id,
            IdempotencyRecord.site_id == site.id,
            IdempotencyRecord.operation.in_(("submission.maintenance.replay", "submission.cleaning.replay")),
            IdempotencyRecord.idempotency_key.in_((
                f"maintenance:{asset.code}:{plan.code}:{plan.next_due_at.isoformat()}",
                "cleaning:FCS13-SHIFT",
            )),
        )) == 2
        session.commit()


def test_fcs13_replay_rejects_future_maintenance_schedule(r2_case):
    with pytest.raises(SubmissionReplayError) as error:
        # The validation is intentionally exercised before any DB work.
        from app.services.submission_data_operational_replay import replay_maintenance_cleaning

        replay_maintenance_cleaning([], [], [], object(), as_of_utc=datetime(2026, 9, 27))
    assert error.value.code == "REPLAY_AS_OF_NOT_TIMEZONE_AWARE"
