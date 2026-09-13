from datetime import UTC
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.maintenance import Asset, MaintenanceOccurrence, MaintenancePlan
from app.models.service import WorkOrder, WorkOrderChecklistItem
from app.models.unit import Unit
from app.schemas.r2 import (
    AssetCreate,
    AssetView,
    MaintenanceDefer,
    MaintenancePlanCreate,
    MaintenancePlanView,
    SchedulerOccurrenceView,
    SchedulerRun,
    SchedulerRunView,
)
from app.services.r2 import (
    audit,
    emit,
    idempotency_replay,
    remember_idempotency,
    require_version,
    utc_now,
)

router = APIRouter(tags=["R2 maintenance"])


def _scoped_asset(session, context: UserContext, asset_id: UUID, *, lock: bool = False) -> Asset:
    statement = select(Asset).where(Asset.id == asset_id, *context.scope_conditions(Asset))
    if lock:
        statement = statement.with_for_update()
    asset = session.scalar(statement)
    if asset is None:
        raise scope_not_found()
    return asset


def _scoped_plan(session, context: UserContext, plan_id: UUID, *, lock: bool = False) -> MaintenancePlan:
    statement = select(MaintenancePlan).where(
        MaintenancePlan.id == plan_id, *context.scope_conditions(MaintenancePlan),
    )
    if lock:
        statement = statement.with_for_update()
    plan = session.scalar(statement)
    if plan is None:
        raise scope_not_found()
    return plan


@router.post("/assets", response_model=AssetView, status_code=201)
def create_asset(
    request: Request,
    body: AssetCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    current_user.assert_building_role(body.building_id, "technical_lead")
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="asset.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            return AssetView.model_validate(_scoped_asset(session, current_user, replay.resource_id))
        if body.unit_id is not None and session.scalar(select(Unit.id).where(
            Unit.id == body.unit_id, Unit.building_id == body.building_id,
        )) is None:
            raise scope_not_found()
        asset = Asset(
            tenant_id=current_user.tenant_id,
            site_id=current_user.assert_active_site(),
            building_id=body.building_id,
            unit_id=body.unit_id,
            code=body.code,
            name=body.name.strip(),
            description=body.description.strip(),
            status="ACTIVE",
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        )
        session.add(asset)
        session.flush()
        audit(session, current_user, request, event_type="AssetCreated", action="create",
              resource_type="Asset", resource_id=asset.id, building_id=asset.building_id,
              after={"code": asset.code, "status": asset.status})
        remember_idempotency(session, current_user, operation="asset.create",
                             key=idempotency_key, payload=payload,
                             resource_type="Asset", resource_id=asset.id, response_status=201)
        session.commit()
        return AssetView.model_validate(asset)


@router.get("/assets/{asset_id}", response_model=AssetView)
def get_asset(request: Request, asset_id: UUID,
              current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        asset = _scoped_asset(session, current_user, asset_id)
        current_user.assert_building_role(asset.building_id, "admin", "director", "cskh", "technical_lead")
        return AssetView.model_validate(asset)


@router.post("/maintenance-plans", response_model=MaintenancePlanView, status_code=201)
def create_maintenance_plan(
    request: Request,
    body: MaintenancePlanCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    current_user.assert_role("technical_lead")
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="maintenance-plan.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            return MaintenancePlanView.model_validate(_scoped_plan(session, current_user, replay.resource_id))
        asset = _scoped_asset(session, current_user, body.asset_id)
        current_user.assert_building_role(asset.building_id, "technical_lead")
        plan = MaintenancePlan(
            tenant_id=asset.tenant_id,
            site_id=asset.site_id,
            building_id=asset.building_id,
            asset_id=asset.id,
            code=body.code,
            title=body.title.strip(),
            interval_days=body.interval_days,
            next_due_at=body.next_due_at.astimezone(UTC),
            checklist_template=[item.model_dump() for item in body.checklist],
            evidence_required=body.evidence_required,
            is_active=True,
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        )
        session.add(plan)
        session.flush()
        audit(session, current_user, request, event_type="MaintenancePlanCreated", action="create",
              resource_type="MaintenancePlan", resource_id=plan.id, building_id=plan.building_id,
              after={"code": plan.code, "next_due_at": plan.next_due_at.isoformat()})
        remember_idempotency(session, current_user, operation="maintenance-plan.create",
                             key=idempotency_key, payload=payload,
                             resource_type="MaintenancePlan", resource_id=plan.id, response_status=201)
        session.commit()
        return MaintenancePlanView.model_validate(plan)


@router.get("/maintenance-plans/{plan_id}", response_model=MaintenancePlanView)
def get_maintenance_plan(request: Request, plan_id: UUID,
                         current_user: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        plan = _scoped_plan(session, current_user, plan_id)
        current_user.assert_building_role(plan.building_id, "admin", "director", "cskh", "technical_lead")
        return MaintenancePlanView.model_validate(plan)


@router.post("/maintenance/scheduler/run", response_model=SchedulerRunView)
def run_maintenance_scheduler(
    request: Request,
    body: SchedulerRun,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    current_user.assert_role("admin", "technical_lead")
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="maintenance-scheduler.run",
                                    key=idempotency_key, payload=payload)
        if replay and replay.response_body:
            return SchedulerRunView.model_validate(replay.response_body)
        plans = session.scalars(select(MaintenancePlan).where(
            *current_user.scope_conditions(MaintenancePlan),
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.next_due_at <= body.as_of.astimezone(UTC),
        ).order_by(MaintenancePlan.id)).all()
        items = []
        for plan in plans:
            if not current_user.matching_grants(frozenset({"admin", "technical_lead"}), plan.building_id):
                continue
            occurrence_id = uuid4()
            inserted_occurrence_id = session.scalar(pg_insert(MaintenanceOccurrence).values(
                id=occurrence_id,
                tenant_id=plan.tenant_id,
                site_id=plan.site_id,
                building_id=plan.building_id,
                plan_id=plan.id,
                due_at=plan.next_due_at,
                status="DUE",
                created_by_id=current_user.account_id,
                updated_by_id=current_user.account_id,
                version=1,
            ).on_conflict_do_nothing(constraint="uq_maintenance_occurrences_plan_due").returning(
                MaintenanceOccurrence.id,
            ))
            replayed = inserted_occurrence_id is None
            occurrence = session.scalar(select(MaintenanceOccurrence).where(
                MaintenanceOccurrence.plan_id == plan.id,
                MaintenanceOccurrence.due_at == plan.next_due_at,
            ).with_for_update())
            if (occurrence.status == "DEFERRED" and occurrence.defer_until
                    and occurrence.defer_until > body.as_of.astimezone(UTC)):
                existing_work_order_id = session.scalar(select(WorkOrder.id).where(
                    WorkOrder.maintenance_occurrence_id == occurrence.id,
                ))
                items.append(SchedulerOccurrenceView(
                    occurrence_id=occurrence.id,
                    work_order_id=existing_work_order_id,
                    plan_id=plan.id,
                    due_at=occurrence.due_at,
                    replayed=True,
                ))
                continue
            work_order_id = uuid4()
            inserted_work_order_id = session.scalar(pg_insert(WorkOrder).values(
                id=work_order_id,
                tenant_id=plan.tenant_id,
                site_id=plan.site_id,
                building_id=plan.building_id,
                service_request_id=None,
                maintenance_occurrence_id=occurrence.id,
                code=f"MWO-{occurrence.id.hex[:12].upper()}",
                title=plan.title,
                description=f"Bảo trì định kỳ cho kế hoạch {plan.code}",
                status="DRAFT",
                created_by_id=current_user.account_id,
                updated_by_id=current_user.account_id,
                version=1,
            ).on_conflict_do_nothing(constraint="uq_work_orders_maintenance_occurrence").returning(
                WorkOrder.id,
            ))
            if inserted_work_order_id:
                session.add_all(WorkOrderChecklistItem(
                    work_order_id=inserted_work_order_id,
                    position=position,
                    label=item["label"],
                    is_required=item.get("required", True),
                ) for position, item in enumerate(plan.checklist_template, 1))
                audit(session, current_user, request, event_type="MaintenanceOccurrenceDue", action="schedule",
                      resource_type="MaintenanceOccurrence", resource_id=occurrence.id,
                      building_id=plan.building_id,
                      after={"due_at": occurrence.due_at.isoformat(),
                             "work_order_id": str(inserted_work_order_id)})
                emit(session, current_user, request, event_type="MaintenanceOccurrenceDue",
                     resource_type="MaintenanceOccurrence", resource_id=occurrence.id,
                     payload={"work_order_id": str(inserted_work_order_id)})
            else:
                work_order_id = session.scalar(select(WorkOrder.id).where(
                    WorkOrder.maintenance_occurrence_id == occurrence.id,
                ))
            if inserted_work_order_id or occurrence.status in {"DUE", "DEFERRED"}:
                occurrence.status = "WO_CREATED"
                occurrence.defer_until = None
                occurrence.defer_reason = None
                occurrence.updated_by_id = current_user.account_id
                occurrence.version += 1
            items.append(SchedulerOccurrenceView(
                occurrence_id=occurrence.id,
                work_order_id=inserted_work_order_id or work_order_id,
                plan_id=plan.id,
                due_at=occurrence.due_at,
                replayed=replayed,
            ))
        response = SchedulerRunView(items=items)
        anchor = items[0].occurrence_id if items else current_user.assert_active_site()
        remember_idempotency(session, current_user, operation="maintenance-scheduler.run",
                             key=idempotency_key, payload=payload,
                             resource_type="MaintenanceOccurrence" if items else "Site",
                             resource_id=anchor, response_status=200,
                             response_body=response.model_dump(mode="json"))
        session.commit()
        return response


@router.post("/maintenance-occurrences/{occurrence_id}/defer", response_model=SchedulerOccurrenceView)
def defer_maintenance_occurrence(
    request: Request,
    occurrence_id: UUID,
    body: MaintenanceDefer,
    current_user: UserContext = Depends(get_current_user_context),
):
    current_user.assert_role("technical_lead")
    with request.app.state.database.get_session() as session:
        occurrence = session.scalar(select(MaintenanceOccurrence).where(
            MaintenanceOccurrence.id == occurrence_id,
            *current_user.scope_conditions(MaintenanceOccurrence),
        ).with_for_update())
        if occurrence is None:
            raise scope_not_found()
        current_user.assert_building_role(occurrence.building_id, "technical_lead")
        require_version(occurrence.version, body.expected_version)
        if occurrence.status not in {"DUE", "WO_CREATED"} or body.defer_until <= utc_now():
            raise AppError("ERR-MNT-DEFER", "Cần nhập lý do và thời điểm xử lý mới hợp lệ.", 409)
        work_order = session.scalar(select(WorkOrder).where(
            WorkOrder.maintenance_occurrence_id == occurrence.id,
        ))
        if work_order and work_order.status not in {"DRAFT", "CANCELLED"}:
            raise AppError("ERR-MNT-DEFER", "Công việc đã bắt đầu nên không thể hoãn lịch.", 409)
        occurrence.status = "DEFERRED"
        occurrence.defer_until = body.defer_until.astimezone(UTC)
        occurrence.defer_reason = body.reason.strip()
        occurrence.updated_by_id = current_user.account_id
        occurrence.version += 1
        audit(session, current_user, request, event_type="MaintenanceDeferred", action="defer",
              resource_type="MaintenanceOccurrence", resource_id=occurrence.id,
              building_id=occurrence.building_id,
              before={"status": "WO_CREATED" if work_order else "DUE"},
              after={"status": occurrence.status, "defer_until": occurrence.defer_until.isoformat()},
              reason=occurrence.defer_reason)
        session.commit()
        return SchedulerOccurrenceView(
            occurrence_id=occurrence.id,
            work_order_id=work_order.id if work_order else None,
            plan_id=occurrence.plan_id,
            due_at=occurrence.due_at,
            replayed=False,
        )
