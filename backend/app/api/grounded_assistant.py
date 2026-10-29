from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.sad_extensions import AssistantConversation
from app.schemas.sad_extensions import AssistantRequest
from app.services.resident_portal import command, scope_values, view
from app.services.r2 import require_version, utc_now
from app.services import grounded_assistant as service

router = APIRouter(prefix='/portal/assistant', tags=['Grounded support'])
ROLES = ('admin', 'director', 'cskh', 'accountant', 'technical_lead', 'technician', 'security', 'cleaning')


def conversation_for(session, context, identifier, lock=False):
    q = select(AssistantConversation).where(AssistantConversation.id == identifier,
        *context.scope_conditions(AssistantConversation), AssistantConversation.account_id == context.account_id)
    row = session.scalar(q.with_for_update() if lock else q)
    if row is None: raise scope_not_found()
    return row


@router.get('/options')
def options(request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    from sqlalchemy import or_
    from app.models.service import ServiceRequest, ServiceCategory
    from app.models.building import Building
    from app.models.site import Site
    from app.models.unit import Unit
    from app.services.resident_portal import resident
    context.assert_role('resident', *ROLES)
    with request.app.state.database.get_session() as session:
        if resident(context):
            visibility = Unit.id.in_(context.resident_units_for('requests'))
        else:
            grants = [g for g in context.role_grants if g.role in ROLES
                and (g.building_id is not None or g.role in {'admin', 'director', 'accountant'})]
            if not grants: raise scope_not_found()
            visibility = or_(*[(Building.id == g.building_id if g.building_id is not None else True) for g in grants])
        units = session.execute(select(Unit, Building).join(Building, Unit.building_id == Building.id)
            .join(Site, Building.site_id == Site.id).where(Building.site_id == context.assert_active_site(),
                Site.tenant_id == context.tenant_id, visibility).order_by(Building.code, Unit.unit_number)).all()
        if unit_id and not any(unit.id == unit_id for unit, _ in units): raise scope_not_found()
        building_ids = [building.id for unit, building in units if not unit_id or unit.id == unit_id]
        rows = session.scalars(service.request_query(context).where(
            *((ServiceRequest.unit_id == unit_id,) if unit_id else ())).order_by(ServiceRequest.created_at.desc()).limit(100))
        categories = session.scalars(select(ServiceCategory).where(*context.scope_conditions(ServiceCategory),
            ServiceCategory.is_active.is_(True), or_(ServiceCategory.building_id.is_(None), ServiceCategory.building_id.in_(building_ids))))
        return {'requests': [{'id':str(r.id), 'label':r.code+' · '+r.title} for r in rows],
                'units': [{'id':str(unit.id), 'unit_number':unit.unit_number, 'building_id':str(building.id), 'building_name':building.name} for unit, building in units],
                'records': service.record_options(session,context,unit_id),
                'categories': [{'id':str(c.id),'label':c.name,'building_id':str(c.building_id) if c.building_id else None} for c in categories]}


@router.get('/conversations')
def conversations(request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        rows = session.scalars(select(AssistantConversation).where(*context.scope_conditions(AssistantConversation),
            AssistantConversation.account_id == context.account_id).order_by(AssistantConversation.updated_at.desc()).limit(100))
        return {'items': [view(r) for r in rows]}


@router.get('/sources/{source}/{identifier}')
def source(source: str, identifier: UUID, request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    source = source.replace('-', '_')
    from app.models.resident_portal import PortalRequestMessage
    with request.app.state.database.get_session() as session:
        if source == 'portal_content':
            rows = service.retrieve(session, context, '', unit_id, identifier)
            if not rows: raise scope_not_found()
            from app.models.resident_portal import PortalContent
            return {**rows[0], 'body':session.get(PortalContent,identifier).body}
        if source == 'service_requests':
            row = service.authorized_request(session, context, identifier)
            return {'title':row.code, 'status':row.status, 'version':row.version, 'description':row.description}
        if source == 'resident_request_messages':
            row = session.scalar(select(PortalRequestMessage).where(PortalRequestMessage.id==identifier, *context.scope_conditions(PortalRequestMessage)))
            if not row: raise scope_not_found()
            service.authorized_request(session, context, row.service_request_id)
            return {'title':row.action, 'message':row.message, 'version':row.version, 'created_at':row.created_at}
        return service.authorized_record(session,context,source,identifier)


@router.post('/support')
def support(body: AssistantRequest, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = conversation_for(session, context, body.conversation_id, lock=True) if body.conversation_id else AssistantConversation(**scope_values(context), title=body.query[:200], messages=[])
        if body.conversation_id:
            if body.expected_version is None: raise AppError('ERR-VERSION-REQUIRED', 'Cần phiên bản cuộc trao đổi hiện tại.', 422)
            require_version(row.version, body.expected_version)
        else: session.add(row); session.flush()
        if len(row.messages) >= 100: raise AppError('ERR-ASSISTANT-LIMIT', 'Cuộc trao đổi đã đủ 100 lượt; mở cuộc mới để tiếp tục.', 409)
        if body.mode == 'HANDOFF':
            target = service.handoff(session, context, body, row)
            result = {'reply': f'Đã chuyển đến CSKH: {target.code}', 'citations': [{'source':'service_requests', 'id':str(target.id), 'title':target.code, 'version':target.version}], 'needs_handoff':False, 'mode':body.mode}
        else: result = service.answer(session, context, body)
        row.messages = [*row.messages, {'query': body.query, 'at': utc_now().isoformat(), **result}]; row.version += 1
        return row, 'profile'
    return command(request, context, key, 'assistant.support', body.model_dump(mode='json'), execute, roles=ROLES)
