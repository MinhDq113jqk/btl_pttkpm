from datetime import UTC
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import or_, select

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.operations import (
    IncidentEscalation,
    IncidentEscalationAcknowledgement,
    PatrolLog,
    PatrolPoint,
    PatrolWindow,
    SecurityIncident,
    SecurityIncidentEvidence,
    SecurityShift,
    SecurityShiftHandoff,
    SecurityVisitorLog,
)
from app.schemas.r3 import (
    IncidentEscalationAcknowledgementCreate,
    IncidentEscalationAcknowledgementView,
    IncidentEscalationView,
    PatrolCompleteCommand,
    PatrolLogCreate,
    PatrolLogView,
    PatrolPointView,
    PatrolWindowView,
    ReasonCommand,
    SecurityAssigneeView,
    SecurityDashboardView,
    SecurityIncidentCreate,
    SecurityIncidentEvidenceCreate,
    SecurityIncidentEvidenceView,
    SecurityIncidentTransition,
    SecurityIncidentView,
    SecurityShiftCreate,
    SecurityShiftHandoffCreate,
    SecurityShiftHandoffView,
    SecurityShiftListResponse,
    SecurityShiftView,
    SecurityVisitorCreate,
    SecurityVisitorView,
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


router = APIRouter(tags=["R3 security operations"])

MANAGER_ROLES = frozenset({"admin", "director"})
HIGH_SEVERITIES = frozenset({"HIGH", "CRITICAL"})
INCIDENT_TRANSITIONS = {
    "NEW": {"TRIAGED"},
    "TRIAGED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"RESOLVED"},
    "RESOLVED": {"CLOSED"},
    "CLOSED": set(),
}


def _is_manager_for(context: UserContext, building_id: UUID) -> bool:
    return bool(context.matching_grants(MANAGER_ROLES, building_id))


def _assert_manager(context: UserContext, building_id: UUID) -> None:
    context.assert_building_role(building_id, *MANAGER_ROLES)


def _manager_filters(context: UserContext, model) -> tuple:
    grants = [grant for grant in context.role_grants if grant.role in MANAGER_ROLES]
    if not grants:
        return ()
    if any(grant.building_id is None for grant in grants):
        return ()
    return (model.building_id.in_([grant.building_id for grant in grants]),)


def _scoped_shift(session, context: UserContext, shift_id: UUID, *, lock: bool = False) -> SecurityShift:
    statement = select(SecurityShift).where(
        SecurityShift.id == shift_id,
        *context.scope_conditions(SecurityShift),
    )
    if lock:
        statement = statement.with_for_update()
    shift = session.scalar(statement)
    if shift is None:
        raise scope_not_found()
    return shift


def _assert_shift_visible(context: UserContext, shift: SecurityShift) -> None:
    if _is_manager_for(context, shift.building_id):
        return
    context.assert_role("security")
    if shift.assigned_to_id != context.account_id:
        raise scope_not_found()


def _assert_shift_operator(context: UserContext, shift: SecurityShift) -> None:
    _assert_shift_visible(context, shift)
    if not _is_manager_for(context, shift.building_id) and shift.assigned_to_id != context.account_id:
        raise scope_not_found()


def _scoped_window(session, context: UserContext, window_id: UUID, *, lock: bool = False) -> tuple[PatrolWindow, SecurityShift]:
    statement = select(PatrolWindow).where(
        PatrolWindow.id == window_id,
        *context.scope_conditions(PatrolWindow),
    )
    if lock:
        statement = statement.with_for_update()
    window = session.scalar(statement)
    if window is None:
        raise scope_not_found()
    shift = _scoped_shift(session, context, window.security_shift_id, lock=lock)
    _assert_shift_visible(context, shift)
    return window, shift


def _account_has_security_grant(session, context: UserContext, account_id: UUID, building_id: UUID) -> bool:
    return session.scalar(select(Account.id).join(AccountRole).where(
        Account.id == account_id,
        Account.tenant_id == context.tenant_id,
        Account.is_active.is_(True),
        AccountRole.role == "security",
        AccountRole.site_id == context.assert_active_site(),
        or_(AccountRole.building_id.is_(None), AccountRole.building_id == building_id),
    ).limit(1)) is not None


def _handoff_view(handoff: SecurityShiftHandoff) -> SecurityShiftHandoffView:
    return SecurityShiftHandoffView(
        id=handoff.id,
        security_shift_id=handoff.security_shift_id,
        handed_over_by_id=handoff.handed_over_by_id,
        received_by_id=handoff.received_by_id,
        summary=handoff.summary,
        created_at=handoff.created_at,
    )


def _visitor_view(visitor: SecurityVisitorLog) -> SecurityVisitorView:
    return SecurityVisitorView(
        id=visitor.id,
        security_shift_id=visitor.security_shift_id,
        recorded_by_id=visitor.recorded_by_id,
        visitor_name=visitor.visitor_name,
        visit_purpose=visitor.visit_purpose,
        document_reference=visitor.document_reference,
        checked_in_at=visitor.checked_in_at,
        created_at=visitor.created_at,
    )


def _log_view(log: PatrolLog) -> PatrolLogView:
    return PatrolLogView(
        id=log.id,
        patrol_window_id=log.patrol_window_id,
        recorded_by_id=log.recorded_by_id,
        event_type=log.event_type,
        note=log.note,
        occurred_at=log.occurred_at,
        created_at=log.created_at,
    )


def _window_view(session, window: PatrolWindow) -> PatrolWindowView:
    point = session.scalar(select(PatrolPoint).where(PatrolPoint.id == window.patrol_point_id))
    if point is None:
        raise scope_not_found()
    logs = session.scalars(select(PatrolLog).where(
        PatrolLog.patrol_window_id == window.id,
    ).order_by(PatrolLog.created_at, PatrolLog.id)).all()
    return PatrolWindowView(
        id=window.id,
        security_shift_id=window.security_shift_id,
        patrol_point_id=point.id,
        patrol_point_code=point.code,
        patrol_point_name=point.name,
        building_id=window.building_id,
        window_start_at=window.window_start_at,
        window_end_at=window.window_end_at,
        status=window.status,
        missed_reason=window.missed_reason,
        completed_at=window.completed_at,
        version=window.version,
        logs=[_log_view(log) for log in logs],
    )


def _incident_view(session, incident: SecurityIncident) -> SecurityIncidentView:
    escalations = session.scalars(select(IncidentEscalation).where(
        IncidentEscalation.security_incident_id == incident.id,
    ).order_by(IncidentEscalation.created_at, IncidentEscalation.id)).all()
    escalation_views = []
    for escalation in escalations:
        acknowledgement = session.scalar(select(IncidentEscalationAcknowledgement).where(
            IncidentEscalationAcknowledgement.incident_escalation_id == escalation.id,
        ))
        acknowledgement_view = None if acknowledgement is None else IncidentEscalationAcknowledgementView(
            id=acknowledgement.id,
            incident_escalation_id=acknowledgement.incident_escalation_id,
            acknowledged_by_id=acknowledgement.acknowledged_by_id,
            note=acknowledgement.note,
            created_at=acknowledgement.created_at,
        )
        escalation_views.append(IncidentEscalationView(
            id=escalation.id,
            security_incident_id=escalation.security_incident_id,
            target_role=escalation.target_role,
            escalated_by_id=escalation.escalated_by_id,
            reason=escalation.reason,
            created_at=escalation.created_at,
            acknowledgement=acknowledgement_view,
        ))
    evidence = session.scalars(select(SecurityIncidentEvidence).where(
        SecurityIncidentEvidence.security_incident_id == incident.id,
    ).order_by(SecurityIncidentEvidence.created_at, SecurityIncidentEvidence.id)).all()
    return SecurityIncidentView(
        id=incident.id,
        patrol_window_id=incident.patrol_window_id,
        building_id=incident.building_id,
        code=incident.code,
        incident_type=incident.incident_type,
        severity=incident.severity,
        status=incident.status,
        title=incident.title,
        description=incident.description,
        occurred_at=incident.occurred_at,
        reported_by_id=incident.reported_by_id,
        conclusion=incident.conclusion,
        resolved_at=incident.resolved_at,
        closed_at=incident.closed_at,
        version=incident.version,
        escalations=escalation_views,
        evidence=[SecurityIncidentEvidenceView(
            id=item.id,
            security_incident_id=item.security_incident_id,
            recorded_by_id=item.recorded_by_id,
            evidence_type=item.evidence_type,
            description=item.description,
            storage_reference=item.storage_reference,
            created_at=item.created_at,
        ) for item in evidence],
    )


def _shift_view(session, shift: SecurityShift) -> SecurityShiftView:
    handoffs = session.scalars(select(SecurityShiftHandoff).where(
        SecurityShiftHandoff.security_shift_id == shift.id,
    ).order_by(SecurityShiftHandoff.created_at, SecurityShiftHandoff.id)).all()
    visitors = session.scalars(select(SecurityVisitorLog).where(
        SecurityVisitorLog.security_shift_id == shift.id,
    ).order_by(SecurityVisitorLog.created_at, SecurityVisitorLog.id)).all()
    windows = session.scalars(select(PatrolWindow).where(
        PatrolWindow.security_shift_id == shift.id,
    ).order_by(PatrolWindow.window_start_at, PatrolWindow.id)).all()
    return SecurityShiftView(
        id=shift.id,
        tenant_id=shift.tenant_id,
        site_id=shift.site_id,
        building_id=shift.building_id,
        assigned_to_id=shift.assigned_to_id,
        scheduled_start_at=shift.scheduled_start_at,
        scheduled_end_at=shift.scheduled_end_at,
        status=shift.status,
        version=shift.version,
        handoffs=[_handoff_view(item) for item in handoffs],
        visitors=[_visitor_view(item) for item in visitors],
        patrol_windows=[_window_view(session, item) for item in windows],
    )


def _visible_shifts(session, context: UserContext) -> list[SecurityShift]:
    manager_grants = [grant for grant in context.role_grants if grant.role in MANAGER_ROLES]
    if manager_grants:
        statement = select(SecurityShift).where(
            *context.scope_conditions(SecurityShift),
            *_manager_filters(context, SecurityShift),
        )
    else:
        context.assert_role("security")
        statement = select(SecurityShift).where(
            *context.scope_conditions(SecurityShift),
            SecurityShift.assigned_to_id == context.account_id,
        )
    return session.scalars(statement.order_by(
        SecurityShift.scheduled_start_at.desc(), SecurityShift.id,
    )).all()


def _incident_for_window(session, context: UserContext, window_id: UUID, *, lock: bool = False) -> SecurityIncident:
    statement = select(SecurityIncident).where(
        SecurityIncident.id == window_id,
        *context.scope_conditions(SecurityIncident),
    )
    if lock:
        statement = statement.with_for_update()
    incident = session.scalar(statement)
    if incident is None:
        raise scope_not_found()
    if incident.patrol_window_id is None:
        raise scope_not_found()
    _, shift = _scoped_window(session, context, incident.patrol_window_id, lock=lock)
    _assert_shift_visible(context, shift)
    return incident


@router.get("/security/patrol-points", response_model=list[PatrolPointView])
def list_patrol_points(request: Request, current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role(*MANAGER_ROLES)
    with request.app.state.database.get_session() as session:
        points = session.scalars(select(PatrolPoint).where(
            *current_user.scope_conditions(PatrolPoint),
            PatrolPoint.is_active.is_(True),
            *_manager_filters(current_user, PatrolPoint),
        ).order_by(PatrolPoint.code, PatrolPoint.id)).all()
        return [PatrolPointView.model_validate(point) for point in points]


@router.get("/security/assignees", response_model=list[SecurityAssigneeView])
def list_security_assignees(
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
            AccountRole.role == "security",
            AccountRole.site_id == current_user.assert_active_site(),
            or_(AccountRole.building_id.is_(None), AccountRole.building_id == building_id),
        ).distinct().order_by(Account.full_name, Account.id)).all()
        return [SecurityAssigneeView.model_validate(account) for account in accounts]


@router.post("/security/shifts", response_model=SecurityShiftView, status_code=201)
def create_security_shift(
    request: Request,
    body: SecurityShiftCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    current_user.assert_role(*MANAGER_ROLES)
    if body.scheduled_end_at <= body.scheduled_start_at:
        raise AppError("ERR-STATE-TRANSITION", "Thời gian kết thúc ca phải sau thời gian bắt đầu.", 409)
    if len({item.patrol_point_id for item in body.patrol_windows}) != len(body.patrol_windows):
        raise AppError("ERR-CONFLICT", "Mỗi điểm tuần tra chỉ có một cửa sổ trong ca này.", 409)
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="security-shift.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            shift = _scoped_shift(session, current_user, replay.resource_id)
            _assert_manager(current_user, shift.building_id)
            return _shift_view(session, shift)
        if session.scalar(select(Building.id).where(
            Building.id == body.building_id,
            Building.site_id == current_user.assert_active_site(),
        )) is None:
            raise scope_not_found()
        _assert_manager(current_user, body.building_id)
        if not _account_has_security_grant(session, current_user, body.assignee_id, body.building_id):
            raise AppError("ERR-INVALID-ASSIGNEE", "Nhân viên an ninh không thuộc phạm vi tòa nhà.", 422)
        point_ids = [item.patrol_point_id for item in body.patrol_windows]
        points = session.scalars(select(PatrolPoint).where(
            PatrolPoint.id.in_(point_ids),
            *current_user.scope_conditions(PatrolPoint),
            PatrolPoint.building_id == body.building_id,
            PatrolPoint.is_active.is_(True),
        )).all()
        if {point.id for point in points} != set(point_ids):
            raise scope_not_found()
        for window in body.patrol_windows:
            if (window.window_end_at <= window.window_start_at
                    or window.window_start_at < body.scheduled_start_at
                    or window.window_end_at > body.scheduled_end_at):
                raise AppError("ERR-STATE-TRANSITION", "Cửa sổ tuần tra phải nằm trong thời gian ca.", 409)
        shift = SecurityShift(
            tenant_id=current_user.tenant_id,
            site_id=current_user.assert_active_site(),
            building_id=body.building_id,
            assigned_to_id=body.assignee_id,
            scheduled_start_at=body.scheduled_start_at.astimezone(UTC),
            scheduled_end_at=body.scheduled_end_at.astimezone(UTC),
            status="PLANNED",
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        )
        session.add(shift)
        session.flush()
        session.add_all(PatrolWindow(
            tenant_id=shift.tenant_id,
            site_id=shift.site_id,
            building_id=shift.building_id,
            security_shift_id=shift.id,
            patrol_point_id=item.patrol_point_id,
            window_start_at=item.window_start_at.astimezone(UTC),
            window_end_at=item.window_end_at.astimezone(UTC),
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        ) for item in body.patrol_windows)
        audit(session, current_user, request, event_type="SecurityShiftCreated", action="create",
              resource_type="SecurityShift", resource_id=shift.id, building_id=shift.building_id,
              after={"assignee_id": str(shift.assigned_to_id), "patrol_window_count": len(point_ids)})
        emit(session, current_user, request, event_type="SecurityShiftCreated",
             resource_type="SecurityShift", resource_id=shift.id,
             payload={"patrol_window_count": len(point_ids)})
        remember_idempotency(session, current_user, operation="security-shift.create",
                             key=idempotency_key, payload=payload,
                             resource_type="SecurityShift", resource_id=shift.id,
                             response_status=201)
        session.commit()
        return _shift_view(session, shift)


@router.get("/security/shifts", response_model=SecurityShiftListResponse)
def list_security_shifts(request: Request, current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role("security", *MANAGER_ROLES)
    with request.app.state.database.get_session() as session:
        return SecurityShiftListResponse(items=[_shift_view(session, shift) for shift in _visible_shifts(session, current_user)])


@router.get("/security/shifts/{shift_id}", response_model=SecurityShiftView)
def get_security_shift(request: Request, shift_id: UUID, current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role("security", *MANAGER_ROLES)
    with request.app.state.database.get_session() as session:
        shift = _scoped_shift(session, current_user, shift_id)
        _assert_shift_visible(current_user, shift)
        return _shift_view(session, shift)


@router.post("/security/shifts/{shift_id}/start", response_model=SecurityShiftView)
def start_security_shift(
    request: Request,
    shift_id: UUID,
    body: VersionCommand,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        shift = _scoped_shift(session, current_user, shift_id, lock=True)
        _assert_shift_operator(current_user, shift)
        require_version(shift.version, body.expected_version)
        if shift.status != "PLANNED":
            raise AppError("ERR-STATE-TRANSITION", "Ca trực chưa sẵn sàng để bắt đầu.", 409)
        shift.status = "IN_PROGRESS"
        shift.updated_by_id = current_user.account_id
        shift.version += 1
        audit(session, current_user, request, event_type="SecurityShiftStarted", action="start",
              resource_type="SecurityShift", resource_id=shift.id, building_id=shift.building_id,
              before={"status": "PLANNED"}, after={"status": shift.status})
        session.commit()
        return _shift_view(session, shift)


@router.post("/security/shifts/{shift_id}/handoffs", response_model=SecurityShiftView, status_code=201)
def create_security_handoff(
    request: Request,
    shift_id: UUID,
    body: SecurityShiftHandoffCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"shift_id": str(shift_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="security-handoff.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            handoff = session.get(SecurityShiftHandoff, replay.resource_id)
            if handoff is None:
                raise scope_not_found()
            shift = _scoped_shift(session, current_user, handoff.security_shift_id)
            _assert_shift_visible(current_user, shift)
            return _shift_view(session, shift)
        shift = _scoped_shift(session, current_user, shift_id)
        _assert_shift_operator(current_user, shift)
        if not _account_has_security_grant(session, current_user, body.received_by_id, shift.building_id):
            raise AppError("ERR-INVALID-ASSIGNEE", "Người nhận bàn giao không thuộc phạm vi tòa nhà.", 422)
        handoff = SecurityShiftHandoff(
            tenant_id=shift.tenant_id,
            site_id=shift.site_id,
            building_id=shift.building_id,
            security_shift_id=shift.id,
            handed_over_by_id=current_user.account_id,
            received_by_id=body.received_by_id,
            summary=body.summary,
        )
        session.add(handoff)
        session.flush()
        audit(session, current_user, request, event_type="SecurityShiftHandoffRecorded", action="append",
              resource_type="SecurityShiftHandoff", resource_id=handoff.id, building_id=shift.building_id,
              after={"security_shift_id": str(shift.id), "received_by_id": str(body.received_by_id)})
        remember_idempotency(session, current_user, operation="security-handoff.create",
                             key=idempotency_key, payload=payload,
                             resource_type="SecurityShiftHandoff", resource_id=handoff.id,
                             response_status=201)
        session.commit()
        return _shift_view(session, shift)


@router.post("/security/shifts/{shift_id}/visitors", response_model=SecurityShiftView, status_code=201)
def create_security_visitor(
    request: Request,
    shift_id: UUID,
    body: SecurityVisitorCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"shift_id": str(shift_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="security-visitor.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            visitor = session.get(SecurityVisitorLog, replay.resource_id)
            if visitor is None:
                raise scope_not_found()
            shift = _scoped_shift(session, current_user, visitor.security_shift_id)
            _assert_shift_visible(current_user, shift)
            return _shift_view(session, shift)
        shift = _scoped_shift(session, current_user, shift_id)
        _assert_shift_operator(current_user, shift)
        visitor = SecurityVisitorLog(
            tenant_id=shift.tenant_id,
            site_id=shift.site_id,
            building_id=shift.building_id,
            security_shift_id=shift.id,
            recorded_by_id=current_user.account_id,
            visitor_name=body.visitor_name,
            visit_purpose=body.visit_purpose,
            document_reference=body.document_reference or None,
            checked_in_at=body.checked_in_at.astimezone(UTC),
        )
        session.add(visitor)
        session.flush()
        audit(session, current_user, request, event_type="SecurityVisitorRecorded", action="append",
              resource_type="SecurityVisitorLog", resource_id=visitor.id, building_id=shift.building_id,
              after={"security_shift_id": str(shift.id)})
        remember_idempotency(session, current_user, operation="security-visitor.create",
                             key=idempotency_key, payload=payload,
                             resource_type="SecurityVisitorLog", resource_id=visitor.id,
                             response_status=201)
        session.commit()
        return _shift_view(session, shift)


@router.post("/security/patrol-windows/{window_id}/logs", response_model=PatrolWindowView, status_code=201)
def create_patrol_log(
    request: Request,
    window_id: UUID,
    body: PatrolLogCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"window_id": str(window_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="patrol-log.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            log = session.get(PatrolLog, replay.resource_id)
            if log is None:
                raise scope_not_found()
            window, _ = _scoped_window(session, current_user, log.patrol_window_id)
            return _window_view(session, window)
        window, shift = _scoped_window(session, current_user, window_id)
        _assert_shift_operator(current_user, shift)
        if window.status != "SCHEDULED":
            raise AppError("ERR-STATE-TRANSITION", "Cửa sổ tuần tra không còn ở trạng thái chờ.", 409)
        log = PatrolLog(
            patrol_window_id=window.id,
            recorded_by_id=current_user.account_id,
            event_type=body.event_type,
            note=body.note or None,
            occurred_at=body.occurred_at.astimezone(UTC),
        )
        session.add(log)
        session.flush()
        audit(session, current_user, request, event_type="PatrolLogRecorded", action="append",
              resource_type="PatrolLog", resource_id=log.id, building_id=window.building_id,
              after={"patrol_window_id": str(window.id), "event_type": log.event_type})
        remember_idempotency(session, current_user, operation="patrol-log.create",
                             key=idempotency_key, payload=payload,
                             resource_type="PatrolLog", resource_id=log.id,
                             response_status=201)
        session.commit()
        return _window_view(session, window)


@router.post("/security/patrol-windows/{window_id}/complete", response_model=PatrolWindowView)
def complete_patrol_window(
    request: Request,
    window_id: UUID,
    body: PatrolCompleteCommand,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        window, shift = _scoped_window(session, current_user, window_id, lock=True)
        _assert_shift_operator(current_user, shift)
        require_version(window.version, body.expected_version)
        if window.status != "SCHEDULED":
            raise AppError("ERR-STATE-TRANSITION", "Cửa sổ tuần tra không còn ở trạng thái chờ.", 409)
        log = PatrolLog(
            patrol_window_id=window.id,
            recorded_by_id=current_user.account_id,
            event_type="CHECK_OUT",
            note=body.note or None,
            occurred_at=utc_now(),
        )
        session.add(log)
        window.status = "COMPLETED"
        window.completed_at = utc_now()
        window.updated_by_id = current_user.account_id
        window.version += 1
        audit(session, current_user, request, event_type="PatrolWindowCompleted", action="complete",
              resource_type="PatrolWindow", resource_id=window.id, building_id=window.building_id,
              before={"status": "SCHEDULED"}, after={"status": "COMPLETED"})
        session.commit()
        return _window_view(session, window)


@router.post("/security/patrol-windows/{window_id}/missed", response_model=PatrolWindowView)
def miss_patrol_window(
    request: Request,
    window_id: UUID,
    body: ReasonCommand,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        window, shift = _scoped_window(session, current_user, window_id, lock=True)
        _assert_shift_operator(current_user, shift)
        require_version(window.version, body.expected_version)
        if window.status != "SCHEDULED":
            raise AppError("ERR-STATE-TRANSITION", "Cửa sổ tuần tra không còn ở trạng thái chờ.", 409)
        window.status = "MISSED"
        window.missed_reason = body.reason
        window.updated_by_id = current_user.account_id
        window.version += 1
        audit(session, current_user, request, event_type="PatrolWindowMissed", action="missed",
              resource_type="PatrolWindow", resource_id=window.id, building_id=window.building_id,
              before={"status": "SCHEDULED"}, after={"status": "MISSED"}, reason=body.reason)
        session.commit()
        return _window_view(session, window)


@router.post("/security/incidents", response_model=SecurityIncidentView, status_code=201)
def create_security_incident(
    request: Request,
    body: SecurityIncidentCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="security-incident.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            incident = _incident_for_window(session, current_user, replay.resource_id)
            return _incident_view(session, incident)
        window, shift = _scoped_window(session, current_user, body.patrol_window_id)
        _assert_shift_operator(current_user, shift)
        incident = SecurityIncident(
            tenant_id=window.tenant_id,
            site_id=window.site_id,
            building_id=window.building_id,
            patrol_window_id=window.id,
            code=f"INC-{uuid4().hex[:10].upper()}",
            incident_type=body.incident_type,
            severity=body.severity,
            status="NEW",
            title=body.title,
            description=body.description,
            occurred_at=body.occurred_at.astimezone(UTC),
            reported_by_id=current_user.account_id,
            created_by_id=current_user.account_id,
            updated_by_id=current_user.account_id,
        )
        session.add(incident)
        session.flush()
        if incident.severity in HIGH_SEVERITIES:
            session.add_all(IncidentEscalation(
                security_incident_id=incident.id,
                target_role=role,
                escalated_by_id=current_user.account_id,
                reason=f"Escalation tự động cho sự cố {incident.severity}.",
            ) for role in ("security", "director"))
        audit(session, current_user, request, event_type="SecurityIncidentCreated", action="create",
              resource_type="SecurityIncident", resource_id=incident.id, building_id=incident.building_id,
              after={"severity": incident.severity, "incident_type": incident.incident_type})
        emit(session, current_user, request, event_type="SecurityIncidentEscalated" if incident.severity in HIGH_SEVERITIES else "SecurityIncidentCreated",
             resource_type="SecurityIncident", resource_id=incident.id,
             payload={"severity": incident.severity})
        remember_idempotency(session, current_user, operation="security-incident.create",
                             key=idempotency_key, payload=payload,
                             resource_type="SecurityIncident", resource_id=incident.id,
                             response_status=201)
        session.commit()
        return _incident_view(session, incident)


@router.post("/security/incidents/{incident_id}/evidence", response_model=SecurityIncidentView, status_code=201)
def create_security_incident_evidence(
    request: Request,
    incident_id: UUID,
    body: SecurityIncidentEvidenceCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"incident_id": str(incident_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="security-incident-evidence.create",
                                    key=idempotency_key, payload=payload)
        if replay:
            evidence = session.get(SecurityIncidentEvidence, replay.resource_id)
            if evidence is None:
                raise scope_not_found()
            return _incident_view(session, _incident_for_window(session, current_user, evidence.security_incident_id))
        incident = _incident_for_window(session, current_user, incident_id)
        evidence = SecurityIncidentEvidence(
            security_incident_id=incident.id,
            recorded_by_id=current_user.account_id,
            evidence_type=body.evidence_type,
            description=body.description,
            storage_reference=body.storage_reference or None,
        )
        session.add(evidence)
        session.flush()
        audit(session, current_user, request, event_type="SecurityIncidentEvidenceRecorded", action="append",
              resource_type="SecurityIncidentEvidence", resource_id=evidence.id, building_id=incident.building_id,
              after={"security_incident_id": str(incident.id), "evidence_type": evidence.evidence_type})
        remember_idempotency(session, current_user, operation="security-incident-evidence.create",
                             key=idempotency_key, payload=payload,
                             resource_type="SecurityIncidentEvidence", resource_id=evidence.id,
                             response_status=201)
        session.commit()
        return _incident_view(session, incident)


@router.post("/security/incidents/{incident_id}/escalations/{escalation_id}/acknowledgements", response_model=SecurityIncidentView, status_code=201)
def acknowledge_incident_escalation(
    request: Request,
    incident_id: UUID,
    escalation_id: UUID,
    body: IncidentEscalationAcknowledgementCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"incident_id": str(incident_id), "escalation_id": str(escalation_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="security-escalation.acknowledge",
                                    key=idempotency_key, payload=payload)
        if replay:
            acknowledgement = session.get(IncidentEscalationAcknowledgement, replay.resource_id)
            if acknowledgement is None:
                raise scope_not_found()
            escalation = session.get(IncidentEscalation, acknowledgement.incident_escalation_id)
            if escalation is None:
                raise scope_not_found()
            return _incident_view(session, _incident_for_window(session, current_user, escalation.security_incident_id))
        incident = _incident_for_window(session, current_user, incident_id)
        escalation = session.scalar(select(IncidentEscalation).where(
            IncidentEscalation.id == escalation_id,
            IncidentEscalation.security_incident_id == incident.id,
        ))
        if escalation is None:
            raise scope_not_found()
        if escalation.target_role not in current_user.roles:
            raise AppError("ERR-FORBIDDEN", "Chỉ đúng vai trò nhận escalation mới được acknowledgement.", 403)
        if session.scalar(select(IncidentEscalationAcknowledgement.id).where(
            IncidentEscalationAcknowledgement.incident_escalation_id == escalation.id,
        )) is not None:
            raise AppError("ERR-CONFLICT", "Escalation đã được acknowledgement.", 409)
        acknowledgement = IncidentEscalationAcknowledgement(
            incident_escalation_id=escalation.id,
            acknowledged_by_id=current_user.account_id,
            note=body.note or None,
        )
        session.add(acknowledgement)
        session.flush()
        audit(session, current_user, request, event_type="SecurityEscalationAcknowledged", action="append",
              resource_type="IncidentEscalationAcknowledgement", resource_id=acknowledgement.id,
              building_id=incident.building_id, after={"escalation_id": str(escalation.id)})
        remember_idempotency(session, current_user, operation="security-escalation.acknowledge",
                             key=idempotency_key, payload=payload,
                             resource_type="IncidentEscalationAcknowledgement", resource_id=acknowledgement.id,
                             response_status=201)
        session.commit()
        return _incident_view(session, incident)


@router.post("/security/incidents/{incident_id}/transition", response_model=SecurityIncidentView)
def transition_security_incident(
    request: Request,
    incident_id: UUID,
    body: SecurityIncidentTransition,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        incident = _incident_for_window(session, current_user, incident_id, lock=True)
        require_version(incident.version, body.expected_version)
        if body.status not in INCIDENT_TRANSITIONS[incident.status]:
            raise AppError("ERR-STATE-TRANSITION", "Chuyển trạng thái sự cố không hợp lệ.", 409)
        if body.status == "CLOSED":
            _assert_manager(current_user, incident.building_id)
            conclusion = body.conclusion or incident.conclusion
            has_evidence = session.scalar(select(SecurityIncidentEvidence.id).where(
                SecurityIncidentEvidence.security_incident_id == incident.id,
            ).limit(1)) is not None
            if not conclusion or not has_evidence:
                raise AppError("ERR-INCIDENT-CLOSE-REQUIREMENTS", "Chỉ được đóng sự cố khi có kết luận và bằng chứng.", 422)
            if incident.severity in HIGH_SEVERITIES:
                missing_ack = session.scalar(select(IncidentEscalation.id).where(
                    IncidentEscalation.security_incident_id == incident.id,
                    ~IncidentEscalation.id.in_(select(IncidentEscalationAcknowledgement.incident_escalation_id)),
                ).limit(1))
                if missing_ack is not None:
                    raise AppError("ERR-ESCALATION-UNACKNOWLEDGED", "Sự cố mức cao chưa được acknowledgement đầy đủ.", 422)
            incident.conclusion = conclusion
            incident.closed_at = utc_now()
        elif body.conclusion:
            incident.conclusion = body.conclusion
        if body.status == "RESOLVED":
            incident.resolved_at = utc_now()
        before = incident.status
        incident.status = body.status
        incident.updated_by_id = current_user.account_id
        incident.version += 1
        audit(session, current_user, request, event_type="SecurityIncidentTransitioned", action="transition",
              resource_type="SecurityIncident", resource_id=incident.id, building_id=incident.building_id,
              before={"status": before}, after={"status": incident.status})
        session.commit()
        return _incident_view(session, incident)


@router.get("/security/dashboard", response_model=SecurityDashboardView)
def get_security_dashboard(request: Request, current_user: UserContext = Depends(get_current_user_context)):
    current_user.assert_role("security", *MANAGER_ROLES)
    with request.app.state.database.get_session() as session:
        shifts = _visible_shifts(session, current_user)
        shift_ids = [shift.id for shift in shifts]
        if not shift_ids:
            return SecurityDashboardView(shifts=[], exceptions=[], incidents=[])
        windows = session.scalars(select(PatrolWindow).where(
            PatrolWindow.security_shift_id.in_(shift_ids),
            PatrolWindow.status == "MISSED",
        ).order_by(PatrolWindow.window_end_at, PatrolWindow.id)).all()
        incidents = session.scalars(select(SecurityIncident).where(
            SecurityIncident.patrol_window_id.in_(select(PatrolWindow.id).where(PatrolWindow.security_shift_id.in_(shift_ids))),
        ).order_by(SecurityIncident.occurred_at.desc(), SecurityIncident.id)).all()
        return SecurityDashboardView(
            shifts=[_shift_view(session, shift) for shift in shifts],
            exceptions=[_window_view(session, window) for window in windows],
            incidents=[_incident_view(session, incident) for incident in incidents],
        )
