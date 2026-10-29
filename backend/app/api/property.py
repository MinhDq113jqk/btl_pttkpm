"""Scoped property history, independent identity records and spatial hierarchy."""
from itertools import combinations
import hashlib
import unicodedata
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.building import Building
from app.models.person import Person, UnitPersonRelationship
from app.models.property import LeaseContract, PersonMerge, PropertyNode, UnitProfileEpisode, UnitLocation
from app.models.resident_portal import LiabilityEpisode, PortalDossier, PortalDossierEvent
from app.models.site import Site
from app.models.unit import Unit
from app.schemas.property import NodeInput
from app.schemas.resident_portal import PortalAction, PortalInput
from pydantic import Field
from app.services.r2 import audit, idempotency_replay, remember_idempotency, require_version, validate_idempotency_key
from app.services.resident_portal import FINANCE, MANAGERS, command, scope_values, scoped, unit_for, view, visible_conditions

router = APIRouter(prefix='/portal/property',tags=['Property and leases'])
ROLES = (*MANAGERS,*FINANCE)


class PersonInput(PortalInput):
    full_name: str = Field(min_length=3,max_length=200)
    phone_masked: str = Field(min_length=1,max_length=50)
    email_masked: str = Field(min_length=1,max_length=100)


@router.get('/persons')
def people(request: Request, context: UserContext=Depends(get_current_user_context)):
    context.assert_role(*ROLES)
    with request.app.state.database.get_session() as session:
        allowed = context.units_query().with_only_columns(Unit.id)
        associated = select(UnitPersonRelationship.person_id).where(UnitPersonRelationship.unit_id.in_(allowed))
        query = select(Person).where(Person.tenant_id==context.tenant_id)
        if not set(context.roles)&{'admin','director'}: query = query.where(Person.id.in_(associated))
        return {'items':[view(p) for p in session.scalars(query.order_by(Person.full_name,Person.id).limit(500))]}


@router.post('/persons',status_code=201)
def create_person(body:PersonInput,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    context.assert_role('admin','director')
    payload=body.model_dump(mode='json')
    with request.app.state.database.get_session() as session:
        validate_idempotency_key(key)
        session.execute(select(func.pg_advisory_xact_lock(int.from_bytes(hashlib.sha256(f'{context.tenant_id}:{context.account_id}:person:{key}'.encode()).digest()[:8], 'big', signed=True))))
        replay=idempotency_replay(session,context,operation='property.person.create',key=key,payload=payload)
        if replay:
            person=session.scalar(select(Person).where(Person.id==replay.resource_id,Person.tenant_id==context.tenant_id))
            if person is None: raise scope_not_found()
            return view(person)
        person=Person(tenant_id=context.tenant_id,**payload)
        session.add(person);session.flush()
        audit(session,context,request,event_type='PersonCreated',action='create',resource_type='Person',resource_id=person.id,after={'full_name':person.full_name})
        remember_idempotency(session,context,operation='property.person.create',key=key,payload=payload,
            resource_type='Person',resource_id=person.id,response_status=201)
        session.commit();return view(person)


@router.get('/duplicates')
def duplicates(request:Request,context:UserContext=Depends(get_current_user_context)):
    result=people(request,context)['items']
    normalize=lambda value: ''.join(c for c in unicodedata.normalize('NFKD',value.casefold()) if not unicodedata.combining(c)).strip()
    candidates=[]
    for left,right in combinations(result,2):
        if normalize(left['full_name'])==normalize(right['full_name']):
            candidates.append({'source_person_id':left['id'],'target_person_id':right['id'],
                'name':left['full_name'],'basis':'NAME_MATCH_REQUIRES_EVIDENCE'})
    return {'items':candidates[:200],'automatic_merge':False}


@router.get('/units/{unit_id}/history')
def unit_history(unit_id:UUID,request:Request,context:UserContext=Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        unit=unit_for(session,context,unit_id,roles=ROLES)
        result={'unit':view(unit)}
        for name,model in [('profiles',UnitProfileEpisode),('leases',LeaseContract),('liabilities',LiabilityEpisode),('relationships',UnitPersonRelationship)]:
            result[name]=[view(r) for r in session.scalars(select(model).where(model.unit_id==unit.id,model.tenant_id==context.tenant_id).order_by(model.created_at))]
        dossiers=session.scalars(select(PortalDossier).where(PortalDossier.unit_id==unit.id,
            *visible_conditions(context,PortalDossier,roles=ROLES))).all()
        result['dossiers']=[{'id':r.id,'kind':r.kind,'status':r.status,'title':r.title} for r in dossiers]
        result['events']=[{'id':e.id,'dossier_id':e.dossier_id,'action':e.action,'message':e.message,'created_at':e.created_at}
            for e in session.scalars(select(PortalDossierEvent).where(PortalDossierEvent.dossier_id.in_([r.id for r in dossiers])).order_by(PortalDossierEvent.created_at))]
        return result


@router.get('/leases')
def leases(request:Request,unit_id:UUID|None=None,context:UserContext=Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        conditions=list(visible_conditions(context,LeaseContract,roles=ROLES,own=False))
        if unit_id:
            unit_for(session,context,unit_id,roles=ROLES);conditions.append(LeaseContract.unit_id==unit_id)
        return {'items':[view(r) for r in session.scalars(select(LeaseContract).where(*conditions).order_by(LeaseContract.valid_from.desc()).limit(200))]}


@router.get('/nodes')
def nodes(request:Request,context:UserContext=Depends(get_current_user_context)):
    context.assert_role(*MANAGERS)
    from app.services.resident_portal import staff_conditions
    with request.app.state.database.get_session() as session:
        return {'items':[view(r) for r in session.scalars(select(PropertyNode).where(
            *context.scope_conditions(PropertyNode), or_(PropertyNode.kind == 'ZONE', *staff_conditions(context,PropertyNode,MANAGERS))).order_by(PropertyNode.code))]}


@router.get('/buildings')
def spatial_buildings(request: Request, context: UserContext=Depends(get_current_user_context)):
    context.assert_role(*MANAGERS)
    with request.app.state.database.get_session() as session:
        buildings = session.scalars(select(Building).join(Site).where(Building.site_id == context.assert_active_site(), Site.tenant_id == context.tenant_id).order_by(Building.code)).all()
        buildings = [b for b in buildings if context.matching_grants(frozenset(MANAGERS), b.id)]
        ids = [b.id for b in buildings]
        units = session.scalars(select(Unit).where(Unit.building_id.in_(ids))).all()
        locations = {l.unit_id: l.floor_node_id for l in session.scalars(select(UnitLocation).where(UnitLocation.building_id.in_(ids), *context.scope_conditions(UnitLocation)))}
        return {'items': [view(b) for b in buildings], 'units': [{**view(u), 'floor_node_id': locations.get(u.id)} for u in units]}


@router.post('/nodes',status_code=201)
def create_node(body:NodeInput,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        context.assert_role(*MANAGERS)
        if body.kind == 'ZONE':
            context.assert_role('admin','director')
            if not any(g.role in ('admin', 'director') and g.building_id is None for g in context.role_grants):
                raise scope_not_found()
            if body.building_id or body.parent_id:
                raise AppError('ERR-PROPERTY-PARENT','Phân khu thuộc khu đô thị, không thuộc tòa/tầng.',422)
        session.scalar(select(Site).where(Site.id==context.assert_active_site(),Site.tenant_id==context.tenant_id).with_for_update())
        if body.kind!='ZONE':
            context.assert_building_role(body.building_id,*MANAGERS)
            building=session.scalar(select(Building).where(Building.id==body.building_id,Building.site_id==context.assert_active_site()))
            if building is None:raise scope_not_found()
            if building.status != 'ACTIVE':raise AppError('ERR-PROPERTY-PARENT','Tòa đã ngừng hiệu lực.',409)
        if body.parent_id:
            parent=session.scalar(select(PropertyNode).where(PropertyNode.id == body.parent_id, PropertyNode.site_id == context.assert_active_site(), PropertyNode.tenant_id == context.tenant_id)) if body.kind == 'FLOOR' else scoped(session,context,PropertyNode,body.parent_id,roles=MANAGERS)
            if parent is None: raise scope_not_found()
            required='ZONE' if body.kind=='FLOOR' else 'FLOOR'
            if parent.kind!=required or parent.status!='ACTIVE' or (parent.building_id is not None and parent.building_id!=body.building_id):
                raise AppError('ERR-PROPERTY-PARENT','Không gian cha không đúng loại/phạm vi hoặc đã ngừng hiệu lực.',409)
        if body.kind == 'FLOOR':
            if not building.zone_id or body.parent_id != building.zone_id:
                raise AppError('ERR-BUILDING-ZONE', 'Tòa cần được gán phân khu; tầng phải thuộc phân khu của tòa.', 409)
        elif body.kind not in {'ZONE','FLOOR'} and not body.parent_id:
            raise AppError('ERR-PROPERTY-PARENT','Không gian này cần tầng cha.',422)
        if session.scalar(select(PropertyNode.id).where(PropertyNode.site_id==context.assert_active_site(),PropertyNode.code==body.code)):
            raise AppError('ERR-PROPERTY-CODE','Mã không gian đã tồn tại; không tái sử dụng mã ngừng hiệu lực.',409)
        if body.kind=='FLOOR' and type(body.data.get('floor_number')) is not int:
            raise AppError('ERR-PROPERTY-DATA','Tầng cần số tầng nguyên.',422)
        row=PropertyNode(**scope_values(context,building_id=body.building_id),parent_id=body.parent_id,
            kind=body.kind,code=body.code,name=body.name,data=body.data)
        session.add(row);return row,'profile'
    return command(request,context,key,'property.node.create',body.model_dump(mode='json'),execute)


@router.post('/nodes/{identifier}/actions')
def node_action(identifier:UUID,body:PortalAction,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        row=scoped(session,context,PropertyNode,identifier,lock=True)
        require_version(row.version,body.expected_version)
        if body.action == 'RENAME':
            name = body.data.get('name')
            if not isinstance(name, str) or not 2 <= len(name.strip()) <= 200:
                raise AppError('ERR-PROPERTY-NAME', 'Tên không gian cần 2–200 ký tự.', 422)
            row.name = name.strip(); row.version += 1; return row, 'profile'
        if body.action not in {'ACTIVATE','DEACTIVATE'}:raise AppError('ERR-STATE-TRANSITION','Thao tác không gian không hợp lệ.',409)
        if body.action=='DEACTIVATE' and session.scalar(select(PropertyNode.id).where(PropertyNode.parent_id==row.id,PropertyNode.status=='ACTIVE').limit(1)):
            raise AppError('ERR-PROPERTY-CHILD','Cần xử lý không gian con đang hoạt động trước.',409)
        if body.action == 'DEACTIVATE' and row.kind == 'ZONE' and session.scalar(select(Building.id).where(Building.zone_id == row.id, Building.status == 'ACTIVE').limit(1)):
            raise AppError('ERR-PROPERTY-CHILD', 'Phân khu còn tòa nhà liên kết.', 409)
        if body.action=='DEACTIVATE' and session.scalar(select(Unit.id).join(UnitLocation,UnitLocation.unit_id==Unit.id)
            .where(UnitLocation.floor_node_id==row.id,Unit.status!='INACTIVE').limit(1)):
            raise AppError('ERR-PROPERTY-CHILD','Tầng còn căn đang hoạt động.',409)
        if body.action=='ACTIVATE' and row.parent_id:
            parent = session.scalar(select(PropertyNode).where(PropertyNode.id == row.parent_id, PropertyNode.site_id == row.site_id, PropertyNode.tenant_id == row.tenant_id)) if row.kind == 'FLOOR' else scoped(session,context,PropertyNode,row.parent_id)
            if parent is None: raise scope_not_found()
            if parent.status!='ACTIVE':raise AppError('ERR-PROPERTY-PARENT','Không gian cha chưa hoạt động.',409)
        if body.action == 'ACTIVATE' and row.building_id and session.get(Building, row.building_id).status != 'ACTIVE':
            raise AppError('ERR-PROPERTY-PARENT','Tòa đã ngừng hiệu lực.',409)
        row.status='ACTIVE' if body.action=='ACTIVATE' else 'INACTIVE';row.version+=1
        return row,'profile'
    return command(request,context,key,'property.node.action',{'id':str(identifier),**body.model_dump(mode='json')},execute)


class UnitInput(PortalInput):
    floor_node_id: UUID
    unit_number: str = Field(min_length=1, max_length=50, pattern=r'^[A-Z0-9][A-Z0-9._-]*$')
    area_m2: float = Field(gt=0, le=9999999999, allow_inf_nan=False)


@router.post('/units', status_code=201)
def create_unit(body: UnitInput, request: Request, context: UserContext=Depends(get_current_user_context), key: str=Header(...,alias='Idempotency-Key')):
    payload=body.model_dump(mode='json')
    with request.app.state.database.get_session() as session:
        validate_idempotency_key(key)
        node=scoped(session,context,PropertyNode,body.floor_node_id,lock=True)
        if node.kind != 'FLOOR' or node.status != 'ACTIVE':
            raise AppError('ERR-PROPERTY-PARENT','Cần tầng đang hoạt động trước khi tạo căn.',409)
        if session.get(Building, node.building_id).status != 'ACTIVE':
            raise AppError('ERR-PROPERTY-PARENT','Tòa đã ngừng hiệu lực.',409)
        replay=idempotency_replay(session,context,operation='property.unit.create',key=key,payload=payload)
        if replay: return view(unit_for(session,context,replay.resource_id))
        if session.scalar(select(Unit.id).where(Unit.building_id==node.building_id,Unit.unit_number==body.unit_number)):
            raise AppError('ERR-PROPERTY-CODE','Mã căn đã tồn tại và không được tái sử dụng.',409)
        unit=Unit(building_id=node.building_id,floor=node.data['floor_number'],
            unit_number=body.unit_number,area_m2=body.area_m2,status='vacant')
        session.add(unit);session.flush()
        session.add(UnitLocation(**scope_values(context, unit), floor_node_id=node.id))
        audit(session,context,request,event_type='UnitCreated',action='create',resource_type='Unit',resource_id=unit.id,building_id=unit.building_id,after={'floor_node_id':str(node.id)})
        remember_idempotency(session,context,operation='property.unit.create',key=key,payload=payload,resource_type='Unit',resource_id=unit.id,response_status=201)
        session.commit();return view(unit)
