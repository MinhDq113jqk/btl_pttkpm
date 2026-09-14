from datetime import UTC
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import or_, select

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.operations import (
    CleaningArea,
    CleaningChecklistResult,
    CleaningRoute,
    CleaningRouteStop,
    CleaningShift,
    CleaningTask,
)
from app.models.service import CaseRecord, WorkOrder, WorkOrderChecklistItem
from app.schemas.r3 import (
    CleaningAssigneeView,
    CleaningChecklistResultView,
    CleaningChecklistUpdate,
    CleaningRouteView,
    CleaningShiftCreate,
    CleaningShiftView,
    CleaningTaskAssign,
    CleaningTaskListResponse,
    CleaningTaskView,
    ReasonCommand,
    VersionCommand,
)
from app.services.r2 import (
    audit,
    emit,
    idempotency_replay,
    remember_idempotency,
    require_version,
    utc_now,
)


router = APIRouter(tags=["R3 cleaning operations"])

MANAGER_ROLES = frozenset({"admin", "director"})
TERMINAL_TASK_STATES = frozenset({"ACCEPTED", "MISSED", "REWORK_REQUIRED", "CANCELLED"})


def _scoped_route(session, context: UserContext, route_id: UUID) -> CleaningRoute:
    route = session.scalar(select(CleaningRoute).where(
        CleaningRoute.id == route_id,
        *context.scope_conditions(CleaningRoute),
        CleaningRoute.is_active.is_(True),
    ))
    if route is None:
        raise scope_not_found()
    return route


def _scoped_task(session, context: UserContext, task_id: UUID, *, lock: bool = False) -> CleaningTask:
    statement = select(CleaningTask).where(
        CleaningTask.id == task_id,
        *context.scope_conditions(CleaningTask),
    )
    if lock:
        statement = statement.with_for_update()
    task = session.scalar(statement)
    if task is None:
        raise scope_not_found()
    return task


def _is_manager_for(context: UserContext, building_id: UUID) -> bool:
    return bool(context.matching_grants(MANAGER_ROLES, building_id))


def _assert_manager(context: UserContext, building_id: UUID) -> None:
    context.assert_building_role(building_id, *MANAGER_ROLES)


def _assert_task_visible(context: UserContext, task: CleaningTask) -> None:
    if _is_manager_for(context, task.building_id):
        return
    if "cleaning" in context.roles:
        if task.assigned_to_id == context.account_id:
            return
        raise scope_not_found()
    context.assert_role("cleaning", *MANAGER_ROLES)
    raise scope_not_found()


def _assert_assigned_cleaner(context: UserContext, task: CleaningTask) -> None:
    context.assert_role("cleaning")
    if task.assigned_to_id != context.account_id:
        raise scope_not_found()


def _route_stop_snapshot(stop: CleaningRouteStop) -> list[dict]:
    template = stop.checklist_template
    if not isinstance(template, list) or not template:
        raise AppError("ERR-CONFLICT", "Tuyến vệ sinh không có checklist hợp lệ.", 409)
    if len(template) > 50:
        raise AppError("ERR-CONFLICT", "Tuyến vệ sinh có quá nhiều mục checklist.", 409)
    snapshot = []
    for item in template:
        label = item.get("label") if isinstance(item, dict) else None
        if not isinstance(label, str) or not 2 <= len(label.strip()) <= 300:
            raise AppError("ERR-CONFLICT", "Tuyến vệ sinh có checklist không hợp lệ.", 409)
        snapshot.append({"label": label.strip(), "required": bool(item.get("required", True))})
    return snapshot


def _task_view(session, task: CleaningTask) -> CleaningTaskView:
    shift = session.get(CleaningShift, task.shift_id)
    stop = session.get(CleaningRouteStop, task.route_stop_id)
    area = session.get(CleaningArea, stop.cleaning_area_id) if stop else None
    route = session.get(CleaningRoute, shift.route_id) if shift else None
    if shift is None or stop is None or area is None or route is None:
        raise AppError("ERR-CONFLICT", "Liên kết ca vệ sinh không còn toàn vẹn.", 409)
    checklist = session.scalars(select(CleaningChecklistResult).where(
        CleaningChecklistResult.cleaning_task_id == task.id,
    ).order_by(CleaningChecklistResult.position)).all()
    work_order = session.scalar(select(WorkOrder).where(WorkOrder.cleaning_task_id == task.id))
    case_id = None
    if work_order is not None:
        case_id = session.scalar(select(CaseRecord.id).where(
            CaseRecord.source_work_order_id == work_order.id,
        ).order_by(CaseRecord.created_at).limit(1))
    return CleaningTaskView(
        id=task.id,
        shift_id=task.shift_id,
        route_id=route.id,
        route_code=route.code,
        route_name=route.name,
        area_id=area.id,
        area_code=area.code,
        area_name=area.name,
        tenant_id=task.tenant_id,
        site_id=task.site_id,
        building_id=task.building_id,
        assigned_to_id=task.assigned_to_id,
        status=task.status,
        scheduled_start_at=shift.scheduled_start_at,
        scheduled_end_at=shift.scheduled_end_at,
        started_at=task.started_at,
        submitted_at=task.submitted_at,
        accepted_at=task.accepted_at,
        accepted_by_id=task.accepted_by_id,
        rework_work_order_id=work_order.id if work_order else None,
        rework_case_id=case_id,
        version=task.version,
        checklist=[CleaningChecklistResultView.model_validate(item) for item in checklist],
    )


def _shift_view(session, shift: CleaningShift) -> CleaningShiftView:
    tasks = session.scalars(select(CleaningTask).where(
        CleaningTask.shift_id == shift.id,
    ).order_by(CleaningTask.created_at, CleaningTask.id)).all()
    return CleaningShiftView(
        id=shift.id,
        route_id=shift.route_id,
        scheduled_start_at=shift.scheduled_start_at,
        scheduled_end_at=shift.scheduled_end_at,
        status=shift.status,
        version=shift.version,
        tasks=[_task_view(session, task) for task in tasks],
    )


def _complete_shift_if_terminal(session, context: UserContext, request: Request, task: CleaningTask) -> None:
    shift = session.scalar(select(CleaningShift).where(
        CleaningShift.id == task.shift_id,
        *context.scope_conditions(CleaningShift),
    ).with_for_update())
    if shift is None or shift.status in {"COMPLETED", "CANCELLED"}:
        return
    states = session.scalars(select(CleaningTask.status).where(
        CleaningTask.shift_id == shift.id,
    ).with_for_update()).all()
    if states and all(status in TERMINAL_TASK_STATES for status in states):
        previous = shift.status
        shift.status = "COMPLETED"
        shift.updated_by_id = context.account_id
        shift.version += 1
        audit(session, context, request, event_type="CleaningShiftCompleted", action="complete",
              resource_type="CleaningShift", resource_id=shift.id, building_id=shift.building_id,
              before={"status": previous}, after={"status": shift.status})


@router.get("/cleaning/routes", response_model=list[CleaningRouteView])
def list_cleaning_routes(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    current_user.assert_role(*MANAGER_ROLES)
    with request.app.state.database.get_session() as session:
        routes = session.scalars(select(CleaningRoute).where(
            *current_user.scope_conditions(CleaningRoute),
            CleaningRoute.is_active.is_(True),
        ).order_by(CleaningRoute.code, CleaningRoute.id)).all()
        return [CleaningRouteView.model_validate(route) for route in routes
                if _is_manager_for(current_user, route.building_id)]


@router.get("/cleaning/assignees", response_model=list[CleaningAssigneeView])
def list_cleaning_assignees(
    request: Request,
    building_id: UUID = Query(...),
    current_user: UserContext = Depends(get_current_user_context),
):
    current_user.assert_role(*MANAGER_ROLES)
    with request.app.state.database.get_session() as session:
        if session.scalar(select(Building.id).where(
            Building.id == building_id,
            Building.site_id == current_user.assert_active_site(),
        )) is None:
            raise scope_not_found()
        _assert_manager(current_user, building_id)
        accounts = session.scalars(select(Account).join(AccountRole).where(
            Account.tenant_id == current_user.tenant_id,
            Account.is_active.is_(True),
            AccountRole.role == "cleaning",
            AccountRole.site_id == current_user.assert_active_site(),
            or_(AccountRole.building_id.is_(None), AccountRole.building_id == building_id),
        ).distinct().order_by(Account.full_name, Account.id)).all()
        return [CleaningAssigneeView.model_validate(account) for account in accounts]


@router.post("/cleaning/shifts", response_model=CleaningShiftView, status_code=201)
def create_cleaning_shift(
    request: Request,
    body: CleaningShiftCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    current_user.assert_role(*MANAGER_ROLES)
    if body.scheduled_end_at <= body.scheduled_start_at:
        raise AppError("ERR-STATE-TRANSITION", "Thời gian kết thúc ca phải sau thời gian bắt đầu.", 409)
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="cleaning-shift.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            shift = session.scalar(select(CleaningShift).where(
                CleaningShift.id == replay.resource_id,
                *current_user.scope_conditions(CleaningShift),
            ))
            if shift is None:
                raise scope_not_found()
            _assert_manager(current_user, shift.building_id)
            return _shift_view(session, shift)
        route = _scoped_route(session, current_user, body.route_id)
        _assert_manager(current_user, route.building_id)
        stops = session.scalars(select(CleaningRouteStop).where(
            CleaningRouteStop.route_id == route.id,
            *current_user.scope_conditions(CleaningRouteStop),
        ).order_by(CleaningRouteStop.position)).all()
        snapshots = [(stop, _route_stop_snapshot(stop)) for stop in stops]
        if not snapshots:
            raise AppError("ERR-CONFLICT", "Tuyến vệ sinh chưa có khu vực được cấu hình.", 409)
        shift = CleaningShift(
            tenant_id=route.tenant_id,
            site_id=route.site_id,
            building_id=route.building_id,
            route_id=route.id,
            scheduled_start_at=body.scheduled_start_at.astimezone(UTC),
            scheduled_end_at=body.scheduled_end_at.astimezone(UTC),
            status="PLANNED",
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        )
        session.add(shift)
        session.flush()
        for stop, snapshot in snapshots:
            task = CleaningTask(
                tenant_id=shift.tenant_id,
                site_id=shift.site_id,
                building_id=shift.building_id,
                shift_id=shift.id,
                route_stop_id=stop.id,
                status="PLANNED",
                created_by_id=current_user.account_id,
                updated_by_id=current_user.account_id,
            )
            session.add(task)
            session.flush()
            session.add_all(CleaningChecklistResult(
                cleaning_task_id=task.id,
                position=position,
                label=item["label"],
                is_required=item["required"],
            ) for position, item in enumerate(snapshot, 1))
        audit(session, current_user, request, event_type="CleaningShiftCreated", action="create",
              resource_type="CleaningShift", resource_id=shift.id, building_id=shift.building_id,
              after={"route_id": str(route.id), "task_count": len(snapshots)})
        emit(session, current_user, request, event_type="CleaningShiftCreated",
             resource_type="CleaningShift", resource_id=shift.id,
             payload={"route_id": str(route.id), "task_count": len(snapshots)})
        remember_idempotency(session, current_user, operation="cleaning-shift.create",
                             key=idempotency_key, payload=payload,
                             resource_type="CleaningShift", resource_id=shift.id,
                             response_status=201)
        session.commit()
        return _shift_view(session, shift)


@router.get("/cleaning/tasks", response_model=CleaningTaskListResponse)
def list_cleaning_tasks(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    current_user.assert_role("cleaning", *MANAGER_ROLES)
    with request.app.state.database.get_session() as session:
        statement = select(CleaningTask).where(*current_user.scope_conditions(CleaningTask))
        if not any(_is_manager_for(current_user, grant.building_id)
                   for grant in current_user.role_grants):
            statement = statement.where(CleaningTask.assigned_to_id == current_user.account_id)
        tasks = session.scalars(statement.order_by(CleaningTask.created_at.desc(), CleaningTask.id)).all()
        return CleaningTaskListResponse(items=[_task_view(session, task) for task in tasks
                                               if _is_manager_for(current_user, task.building_id)
                                               or task.assigned_to_id == current_user.account_id])


@router.get("/cleaning/tasks/{task_id}", response_model=CleaningTaskView)
def get_cleaning_task(
    request: Request,
    task_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        task = _scoped_task(session, current_user, task_id)
        _assert_task_visible(current_user, task)
        return _task_view(session, task)


@router.post("/cleaning/tasks/{task_id}/assign", response_model=CleaningTaskView)
def assign_cleaning_task(
    request: Request,
    task_id: UUID,
    body: CleaningTaskAssign,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        task = _scoped_task(session, current_user, task_id, lock=True)
        _assert_manager(current_user, task.building_id)
        require_version(task.version, body.expected_version)
        if task.status not in {"PLANNED", "ASSIGNED"}:
            raise AppError("ERR-STATE-TRANSITION", "Chỉ phân công task đang chờ xử lý.", 409)
        assignee = session.scalar(select(Account).join(AccountRole).where(
            Account.id == body.assignee_id,
            Account.tenant_id == current_user.tenant_id,
            Account.is_active.is_(True),
            AccountRole.role == "cleaning",
            AccountRole.site_id == current_user.assert_active_site(),
            or_(AccountRole.building_id.is_(None), AccountRole.building_id == task.building_id),
        ))
        if assignee is None:
            raise scope_not_found()
        before = {"status": task.status, "assigned_to_id": str(task.assigned_to_id) if task.assigned_to_id else None}
        task.status = "ASSIGNED"
        task.assigned_to_id = assignee.id
        task.updated_by_id = current_user.account_id
        task.version += 1
        audit(session, current_user, request, event_type="CleaningTaskAssigned", action="assign",
              resource_type="CleaningTask", resource_id=task.id, building_id=task.building_id,
              before=before, after={"status": task.status, "assigned_to_id": str(assignee.id)})
        emit(session, current_user, request, event_type="CleaningTaskAssigned",
             resource_type="CleaningTask", resource_id=task.id,
             payload={"assigned_to_id": str(assignee.id)})
        session.commit()
        return _task_view(session, task)


@router.post("/cleaning/tasks/{task_id}/start", response_model=CleaningTaskView)
def start_cleaning_task(
    request: Request,
    task_id: UUID,
    body: VersionCommand,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        task = _scoped_task(session, current_user, task_id, lock=True)
        _assert_assigned_cleaner(current_user, task)
        require_version(task.version, body.expected_version)
        if task.status != "ASSIGNED":
            raise AppError("ERR-STATE-TRANSITION", "Task chưa sẵn sàng để bắt đầu.", 409)
        task.status = "IN_PROGRESS"
        task.started_at = utc_now()
        task.updated_by_id = current_user.account_id
        task.version += 1
        shift = session.scalar(select(CleaningShift).where(
            CleaningShift.id == task.shift_id,
            *current_user.scope_conditions(CleaningShift),
        ).with_for_update())
        if shift is None:
            raise scope_not_found()
        if shift.status == "PLANNED":
            shift.status = "IN_PROGRESS"
            shift.updated_by_id = current_user.account_id
            shift.version += 1
            audit(session, current_user, request, event_type="CleaningShiftStarted", action="start",
                  resource_type="CleaningShift", resource_id=shift.id, building_id=shift.building_id,
                  before={"status": "PLANNED"}, after={"status": shift.status})
        audit(session, current_user, request, event_type="CleaningTaskStarted", action="start",
              resource_type="CleaningTask", resource_id=task.id, building_id=task.building_id,
              before={"status": "ASSIGNED"}, after={"status": task.status})
        emit(session, current_user, request, event_type="CleaningTaskStarted",
             resource_type="CleaningTask", resource_id=task.id)
        session.commit()
        return _task_view(session, task)


@router.patch("/cleaning/tasks/{task_id}/checklist/{item_id}", response_model=CleaningTaskView)
def update_cleaning_checklist(
    request: Request,
    task_id: UUID,
    item_id: UUID,
    body: CleaningChecklistUpdate,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        task = _scoped_task(session, current_user, task_id, lock=True)
        _assert_assigned_cleaner(current_user, task)
        if task.status != "IN_PROGRESS":
            raise AppError("ERR-STATE-TRANSITION", "Checklist chỉ cập nhật khi task đang thực hiện.", 409)
        item = session.scalar(select(CleaningChecklistResult).where(
            CleaningChecklistResult.id == item_id,
            CleaningChecklistResult.cleaning_task_id == task.id,
        ).with_for_update())
        if item is None:
            raise scope_not_found()
        require_version(item.version, body.expected_version)
        before = {"result": item.result, "note": item.note}
        item.result = body.result
        item.note = body.note or None
        item.performed_by_id = current_user.account_id
        item.performed_at = utc_now()
        item.version += 1
        task.updated_by_id = current_user.account_id
        task.version += 1
        audit(session, current_user, request, event_type="CleaningChecklistUpdated", action="checklist-update",
              resource_type="CleaningChecklistResult", resource_id=item.id, building_id=task.building_id,
              before=before, after={"result": item.result, "note": item.note})
        session.commit()
        return _task_view(session, task)


def _create_rework_case(session, context: UserContext, request: Request, task: CleaningTask,
                        failed: list[CleaningChecklistResult]) -> tuple[WorkOrder, CaseRecord]:
    existing = session.scalar(select(WorkOrder).where(WorkOrder.cleaning_task_id == task.id))
    if existing is not None:
        case_record = session.scalar(select(CaseRecord).where(
            CaseRecord.source_work_order_id == existing.id,
        ).order_by(CaseRecord.created_at).limit(1))
        if case_record is not None:
            return existing, case_record
        case_record = CaseRecord(
            tenant_id=task.tenant_id,
            site_id=task.site_id,
            building_id=task.building_id,
            source_work_order_id=existing.id,
            reason="Checklist vệ sinh không đạt; Case được khôi phục cho Work Order đã có.",
            status="NEW",
            created_by_id=context.account_id,
            updated_by_id=context.account_id,
        )
        session.add(case_record)
        session.flush()
        return existing, case_record
    area = session.scalar(select(CleaningArea).join(CleaningRouteStop).where(
        CleaningRouteStop.id == task.route_stop_id,
        CleaningArea.id == CleaningRouteStop.cleaning_area_id,
    ))
    area_name = area.name if area else "khu vực vệ sinh"
    labels = ", ".join(item.label for item in failed)
    work_order = WorkOrder(
        tenant_id=task.tenant_id,
        site_id=task.site_id,
        building_id=task.building_id,
        cleaning_task_id=task.id,
        code=f"CWO-{uuid4().hex[:12].upper()}",
        title=f"Làm lại vệ sinh: {area_name}"[:200],
        description=f"Checklist vệ sinh không đạt: {labels}",
        status="DRAFT",
        created_by_id=context.account_id,
        updated_by_id=context.account_id,
    )
    session.add(work_order)
    session.flush()
    session.add_all(WorkOrderChecklistItem(
        work_order_id=work_order.id,
        position=position,
        label=item.label,
        is_required=True,
    ) for position, item in enumerate(failed, 1))
    case_record = CaseRecord(
        tenant_id=task.tenant_id,
        site_id=task.site_id,
        building_id=task.building_id,
        source_work_order_id=work_order.id,
        reason=f"Checklist vệ sinh không đạt: {labels}"[:500],
        status="NEW",
        created_by_id=context.account_id,
        updated_by_id=context.account_id,
    )
    session.add(case_record)
    session.flush()
    audit(session, context, request, event_type="CleaningReworkWorkOrderCreated", action="create",
          resource_type="WorkOrder", resource_id=work_order.id, building_id=task.building_id,
          after={"cleaning_task_id": str(task.id), "failed_count": len(failed)})
    audit(session, context, request, event_type="CleaningReworkCaseOpened", action="create",
          resource_type="Case", resource_id=case_record.id, building_id=task.building_id,
          after={"source_work_order_id": str(work_order.id)})
    emit(session, context, request, event_type="CleaningReworkRequired",
         resource_type="CleaningTask", resource_id=task.id,
         payload={"work_order_id": str(work_order.id), "case_id": str(case_record.id)})
    return work_order, case_record


@router.post("/cleaning/tasks/{task_id}/submit", response_model=CleaningTaskView)
def submit_cleaning_task(
    request: Request,
    task_id: UUID,
    body: VersionCommand,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"task_id": str(task_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="cleaning-task.submit",
                                    key=idempotency_key, payload=payload)
        if replay:
            task = _scoped_task(session, current_user, replay.resource_id)
            _assert_assigned_cleaner(current_user, task)
            return _task_view(session, task)
        task = _scoped_task(session, current_user, task_id, lock=True)
        _assert_assigned_cleaner(current_user, task)
        require_version(task.version, body.expected_version)
        if task.status != "IN_PROGRESS":
            raise AppError("ERR-STATE-TRANSITION", "Task chưa sẵn sàng để nộp kết quả.", 409)
        checklist = session.scalars(select(CleaningChecklistResult).where(
            CleaningChecklistResult.cleaning_task_id == task.id,
        ).order_by(CleaningChecklistResult.position).with_for_update()).all()
        incomplete = [item for item in checklist
                      if item.is_required and item.result not in {"PASS", "FAIL"}]
        if incomplete:
            raise AppError("ERR-CHECKLIST-INCOMPLETE", "Checklist bắt buộc chưa được đánh giá đạt hoặc không đạt.", 422)
        failed = [item for item in checklist if item.result == "FAIL"]
        previous = task.status
        task.status = "REWORK_REQUIRED" if failed else "SUBMITTED"
        task.submitted_at = utc_now()
        task.updated_by_id = current_user.account_id
        task.version += 1
        if failed:
            _create_rework_case(session, current_user, request, task, failed)
        audit(session, current_user, request,
              event_type="CleaningTaskReworkRequired" if failed else "CleaningTaskSubmitted",
              action="submit", resource_type="CleaningTask", resource_id=task.id,
              building_id=task.building_id, before={"status": previous},
              after={"status": task.status, "failed_count": len(failed)})
        if not failed:
            emit(session, current_user, request, event_type="CleaningTaskSubmitted",
                 resource_type="CleaningTask", resource_id=task.id)
        _complete_shift_if_terminal(session, current_user, request, task)
        remember_idempotency(session, current_user, operation="cleaning-task.submit",
                             key=idempotency_key, payload=payload,
                             resource_type="CleaningTask", resource_id=task.id,
                             response_status=200)
        session.commit()
        return _task_view(session, task)


@router.post("/cleaning/tasks/{task_id}/accept", response_model=CleaningTaskView)
def accept_cleaning_task(
    request: Request,
    task_id: UUID,
    body: VersionCommand,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        task = _scoped_task(session, current_user, task_id, lock=True)
        _assert_manager(current_user, task.building_id)
        require_version(task.version, body.expected_version)
        if task.status != "SUBMITTED":
            raise AppError("ERR-STATE-TRANSITION", "Task chưa chờ nghiệm thu.", 409)
        required_not_passed = session.scalar(select(CleaningChecklistResult.id).where(
            CleaningChecklistResult.cleaning_task_id == task.id,
            CleaningChecklistResult.is_required.is_(True),
            CleaningChecklistResult.result != "PASS",
        ).limit(1))
        if required_not_passed is not None:
            raise AppError("ERR-CHECKLIST-INCOMPLETE", "Checklist bắt buộc phải đạt trước khi nghiệm thu.", 422)
        task.status = "ACCEPTED"
        task.accepted_at = utc_now()
        task.accepted_by_id = current_user.account_id
        task.updated_by_id = current_user.account_id
        task.version += 1
        audit(session, current_user, request, event_type="CleaningTaskAccepted", action="accept",
              resource_type="CleaningTask", resource_id=task.id, building_id=task.building_id,
              before={"status": "SUBMITTED"}, after={"status": task.status})
        emit(session, current_user, request, event_type="CleaningTaskAccepted",
             resource_type="CleaningTask", resource_id=task.id)
        _complete_shift_if_terminal(session, current_user, request, task)
        session.commit()
        return _task_view(session, task)


def _close_cleaning_task(
    request: Request,
    task_id: UUID,
    body: ReasonCommand,
    current_user: UserContext,
    *,
    status: str,
    event_type: str,
) -> CleaningTaskView:
    with request.app.state.database.get_session() as session:
        task = _scoped_task(session, current_user, task_id, lock=True)
        _assert_manager(current_user, task.building_id)
        require_version(task.version, body.expected_version)
        allowed = {"PLANNED", "ASSIGNED"} if status == "MISSED" else {"PLANNED", "ASSIGNED", "IN_PROGRESS"}
        if task.status not in allowed:
            raise AppError("ERR-STATE-TRANSITION", "Task không thể chuyển sang trạng thái này.", 409)
        previous = task.status
        task.status = status
        task.updated_by_id = current_user.account_id
        task.version += 1
        audit(session, current_user, request, event_type=event_type, action=status.lower(),
              resource_type="CleaningTask", resource_id=task.id, building_id=task.building_id,
              before={"status": previous}, after={"status": status}, reason=body.reason)
        _complete_shift_if_terminal(session, current_user, request, task)
        session.commit()
        return _task_view(session, task)


@router.post("/cleaning/tasks/{task_id}/missed", response_model=CleaningTaskView)
def miss_cleaning_task(request: Request, task_id: UUID, body: ReasonCommand,
                       current_user: UserContext = Depends(get_current_user_context)):
    return _close_cleaning_task(request, task_id, body, current_user,
                                status="MISSED", event_type="CleaningTaskMissed")


@router.post("/cleaning/tasks/{task_id}/cancel", response_model=CleaningTaskView)
def cancel_cleaning_task(request: Request, task_id: UUID, body: ReasonCommand,
                         current_user: UserContext = Depends(get_current_user_context)):
    return _close_cleaning_task(request, task_id, body, current_user,
                                status="CANCELLED", event_type="CleaningTaskCancelled")
