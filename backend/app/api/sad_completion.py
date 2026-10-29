"""Community decisions, SLA ownership, initialization acceptance and source links."""
from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func, or_
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.resident_portal import PortalContent
from app.models.account import Account
from app.models.sad_completion import CommunityTask, SlaPolicy, InitDataset
from app.schemas.resident_portal import PortalAction
from app.schemas.sad_completion import ContentRevision, Minutes, SlaInput, DatasetInput, DatasetManifest
from app.services.resident_portal import command, view, scope_values, staff_conditions, scoped, resident, unit_for
from app.services.operational_control import load, building_scope, independent, state, event, data_model, MANAGEMENT
from app.services.r2 import require_version, utc_now
from app.services.sad_completion import SERVICE_ROLES, assert_owner, dataset_sources, sla_deadline

router = APIRouter(prefix='/portal', tags=['SAD completion workflows'])


@router.get('/completion-options')
def completion_options(request:Request,building_id:UUID | None=None,context:UserContext=Depends(get_current_user_context)):
    from app.models.service import ServiceCategory,ServiceRequest
    from app.models.import_run import ImportRun
    from app.models.submission_import import SubmissionImportRun,SubmissionExternalReference
    with request.app.state.database.get_session() as session:
        if building_id:
            building_scope(session,context,building_id,SERVICE_ROLES)
        else:
            context.assert_building_role(None,'admin','director')
        accounts=[]
        for account in session.scalars(select(Account).where(Account.tenant_id==context.tenant_id,Account.is_active.is_(True)).order_by(Account.id)):
            try:assert_owner(session,context,account.id,building_id)
            except AppError:continue
            accounts.append({'id':str(account.id),'label':account.full_name})
        if building_id is None:
            return {'accounts':accounts,'categories':[],'requests':[],'csv_batches':[],'loader_batches':[],'max_recent_batches':200}
        categories=[{'id':str(r.id),'label':r.name} for r in session.scalars(select(ServiceCategory).where(*context.scope_conditions(ServiceCategory),ServiceCategory.is_active.is_(True),or_(ServiceCategory.building_id.is_(None),ServiceCategory.building_id==building_id)))]
        requests=[{'id':str(r.id),'label':r.code+' · '+r.title} for r in session.scalars(select(ServiceRequest).where(*context.scope_conditions(ServiceRequest),ServiceRequest.building_id==building_id).order_by(ServiceRequest.created_at.desc()).limit(200))]
        csv=[{'id':str(r.id),'label':r.source_filename+' · '+r.status,'status':r.status,'applied_rows':r.applied_rows} for r in session.scalars(select(ImportRun).where(*context.scope_conditions(ImportRun),ImportRun.building_id==building_id).order_by(ImportRun.created_at.desc()).limit(200))]
        loaders=[]
        for run in session.scalars(select(SubmissionImportRun).order_by(SubmissionImportRun.created_at.desc()).limit(200)):
            tenants=set(session.scalars(select(SubmissionExternalReference.tenant_id).where(SubmissionExternalReference.import_run_id==run.id)))
            if tenants=={context.tenant_id}:
                from app.services.sad_completion import loader_references
                refs=session.scalars(select(SubmissionExternalReference).where(SubmissionExternalReference.import_run_id==run.id)).all()
                visible=loader_references(session,context,refs,building_id)
                if visible:loaders.append({'id':str(run.id),'label':run.stage+' · '+run.status,'status':run.status,'total_rows':run.total_rows,'scoped_references':len(visible)})
        return {'accounts':accounts,'categories':categories,'requests':requests,'csv_batches':csv,'loader_batches':loaders,'max_recent_batches':200}


def listing(request, context, model, roles, building_id=None):
    with request.app.state.database.get_session() as session:
        conditions = [*context.scope_conditions(model), *staff_conditions(context, model, roles)]
        if building_id: conditions.append(model.building_id == building_id)
        return {'items':[view(r) for r in session.scalars(select(model).where(*conditions).order_by(model.created_at.desc()).limit(200))]}


@router.post('/content/{identifier}/revision')
def revision(identifier: UUID, body: ContentRevision, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = scoped(session, context, PortalContent, identifier, lock=True)
        context.assert_role(*MANAGEMENT); require_version(row.version, body.expected_version)
        values = body.content.model_dump(exclude={'building_id','unit_id'})
        if body.content.building_id != row.building_id or body.content.unit_id != row.unit_id or body.content.kind != row.kind:
            raise AppError('ERR-CONTENT-SCOPE', 'Bản sửa phải giữ loại và đối tượng công bố.', 422)
        if body.content.document_id:
            from app.api.portal_documents import _document
            doc = _document(session, context, body.content.document_id)
            if not doc.published or doc.revoked_at or doc.quarantined or (doc.building_id and doc.building_id != row.building_id) or (doc.unit_id and doc.unit_id != row.unit_id):
                raise AppError('ERR-DOCUMENT-AUDIENCE', 'Tài liệu không phù hợp đối tượng công bố.', 409)
        if row.status in ('DRAFT','REJECTED'):
            for k,v in values.items(): setattr(row,k,v)
            row.status = 'DRAFT'; row.approved_by_id = None; row.change_reason = body.reason; row.version += 1
        else:
            state(row, ('PUBLISHED','CLOSED'))
            if session.scalar(select(PortalContent.id).where(PortalContent.previous_id == row.id)):
                raise AppError('ERR-CONTENT-SUCCESSOR', 'Đã có bản thay thế; tiếp tục sửa bản đó.', 409)
            row = PortalContent(**{k:getattr(row,k) for k in ('tenant_id','site_id','building_id','unit_id')},
                account_id=context.account_id, previous_id=row.id, change_reason=body.reason, **values)
            session.add(row)
        event(session, context, row, 'REVISION', body.reason)
        return row, 'documents'
    return command(request, context, key, 'content.revision', {'id':str(identifier), **body.model_dump(mode='json')}, execute)


@router.get('/content/{identifier}/chain')
def chain(identifier: UUID, request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        if resident(context):
            unit = unit_for(session, context, unit_id, 'documents')
            row = session.scalar(select(PortalContent).where(PortalContent.id == identifier, *context.scope_conditions(PortalContent)))
            if not row or row.status not in ('PUBLISHED','CLOSED','WITHDRAWN') or row.publish_at > utc_now() or row.building_id not in (None, unit.building_id) or row.unit_id not in (None,unit.id): raise scope_not_found()
        else: row = scoped(session, context, PortalContent, identifier)
        items = []; seen = set()
        while row.previous_id and row.id not in seen:
            seen.add(row.id); row = session.get(PortalContent, row.previous_id)
        while row and row.id not in {r['id'] for r in items}:
            if not resident(context) or row.status in ('PUBLISHED','CLOSED','WITHDRAWN') and row.publish_at <= utc_now(): items.append(view(row))
            row = session.scalar(select(PortalContent).where(PortalContent.previous_id == row.id))
        return {'items':items}


@router.post('/content/{identifier}/minutes')
def minutes(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = scoped(session, context, PortalContent, identifier, lock=True); context.assert_role(*MANAGEMENT)
        require_version(row.version, body.expected_version); state(row, ('PUBLISHED',))
        if body.action != 'RECORD_MINUTES' or row.kind != 'MEETING' or row.minutes:
            raise AppError('ERR-MINUTES-STATE', 'Biên bản chỉ ghi một lần cho cuộc họp đã công bố.', 409)
        checked = data_model(Minutes, body.data)
        for d in checked.decisions:
            assert_owner(session, context, d.owner_id, row.building_id)
            session.add(CommunityTask(**{k:getattr(row,k) for k in ('tenant_id','site_id','building_id','unit_id')}, account_id=context.account_id,
                content_id=row.id, decision_key=d.key, title=d.title, owner_id=d.owner_id, due_at=d.due_at))
        row.minutes = checked.model_dump(mode='json'); row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'documents'
    return command(request, context, key, 'content.minutes', {'id':str(identifier), **body.model_dump(mode='json')}, execute)


@router.get('/community-tasks')
def tasks(request: Request, building_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, CommunityTask, SERVICE_ROLES, building_id)


@router.post('/community-tasks/{identifier}/actions')
def task_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = load(session, context, CommunityTask, identifier, SERVICE_ROLES, lock=True); require_version(row.version, body.expected_version)
        if context.account_id != row.owner_id: context.assert_building_role(row.building_id,'admin','director')
        state(row, ('OPEN','IN_PROGRESS'))
        if body.action == 'START': row.status = 'IN_PROGRESS'
        elif body.action in ('COMPLETE','CANCEL'):
            if body.action == 'CANCEL': context.assert_building_role(row.building_id, 'admin','director')
            evidence = body.data.get('evidence_reference','')
            if not isinstance(evidence,str) or not 3 <= len(evidence) <= 300: raise AppError('ERR-EVIDENCE-REQUIRED','Cần căn cứ kết quả.',422)
            row.status = 'COMPLETED' if body.action == 'COMPLETE' else 'CANCELLED'; row.result = body.reason; row.evidence_reference = evidence
        else: raise AppError('ERR-STATE-TRANSITION','Thao tác nhiệm vụ không hợp lệ.',409)
        row.version += 1; event(session, context, row, body.action, body.reason); return row,'profile'
    return command(request, context, key, 'community-task.'+body.action, {'id':str(identifier), **body.model_dump(mode='json')}, execute, roles=SERVICE_ROLES)


@router.get('/sla-policies')
def policies(request: Request, building_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    return listing(request, context, SlaPolicy, SERVICE_ROLES, building_id)


@router.post('/sla-policies', status_code=201)
def policy_create(body: SlaInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        from app.models.service import ServiceCategory
        building_scope(session, context, body.building_id, MANAGEMENT)
        category = session.get(ServiceCategory, body.category_id)
        if not category or category.tenant_id != context.tenant_id or category.site_id != context.assert_active_site() or category.building_id not in (None, body.building_id) or not category.is_active: raise scope_not_found()
        row = SlaPolicy(**scope_values(context, building_id=body.building_id), category_id=body.category_id, definition=body.definition.model_dump(mode='json')); session.add(row)
        return row,'profile'
    return command(request, context, key, 'sla-policy.create', body.model_dump(mode='json'), execute)


@router.post('/sla-policies/{identifier}/actions')
def policy_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        row = load(session, context, SlaPolicy, identifier, MANAGEMENT, lock=True); require_version(row.version, body.expected_version)
        if body.action != 'PUBLISH': raise AppError('ERR-STATE-TRANSITION','Cần tạo bản chính sách mới để thay đổi.',409)
        state(row, ('DRAFT',)); independent(context,row)
        from app.services.operational_control import financial_lock
        financial_lock(session,context)
        old = session.scalars(select(SlaPolicy).where(SlaPolicy.tenant_id == row.tenant_id, SlaPolicy.site_id == row.site_id,
            SlaPolicy.building_id == row.building_id, SlaPolicy.category_id == row.category_id, SlaPolicy.status == 'ACTIVE').with_for_update()).all()
        for p in old: p.status = 'RETIRED'; p.version += 1
        row.status = 'ACTIVE'; row.approved_by_id = context.account_id; row.version += 1; event(session,context,row,body.action,body.reason)
        return row,'profile'
    return command(request,context,key,'sla-policy.publish',{'id':str(identifier), **body.model_dump(mode='json')},execute)


@router.get('/requests/{identifier}/control')
def request_control(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    from app.models.service import ServiceRequest
    with request.app.state.database.get_session() as session:
        row = load(session,context,ServiceRequest,identifier,SERVICE_ROLES)
        return {**view(row), 'sla_deadline':sla_deadline(row)}


@router.post('/requests/{identifier}/control')
def request_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    from app.models.service import ServiceRequest
    def execute(session):
        row = load(session,context,ServiceRequest,identifier,SERVICE_ROLES,lock=True); require_version(row.version,body.expected_version)
        state(row,('NEW','TRIAGED','IN_PROGRESS','WAITING_INFO','RESOLVED'))
        now = utc_now(); pauses = list(row.sla_pauses or []); handoff = row.handoff or {}
        if body.action == 'PAUSE':
            code = body.data.get('pause_reason')
            if code not in (row.sla_policy_snapshot or {}).get('pause_reasons',[]) or any(not p.get('ended_at') for p in pauses):
                raise AppError('ERR-SLA-PAUSE','Chính sách tại lúc tạo không cho phép dừng vì lý do này.',409)
            if row.sla_breached_at or sla_deadline(row,as_of=now)<=now: raise AppError('ERR-SLA-PAUSE','SLA đã quá hạn; không được dừng để xóa vi phạm.',409)
            pauses.append({'started_at':now.isoformat(),'reason_code':code,'basis':body.reason,'actor_id':str(context.account_id)})
            row.sla_pauses = pauses
        elif body.action == 'RESUME':
            if not pauses or pauses[-1].get('ended_at'): raise AppError('ERR-SLA-PAUSE','SLA chưa dừng.',409)
            pauses[-1] = {**pauses[-1], 'ended_at':now.isoformat(),'resume_basis':body.reason}; row.sla_pauses = pauses
        elif body.action == 'TRANSFER':
            if handoff.get('status') in ('PENDING','ESCALATED'): raise AppError('ERR-HANDOFF-PENDING','Chuyển giao trước chưa được tiếp nhận.',409)
            target = body.data.get('owner_id'); department = body.data.get('department')
            try: target = UUID(target)
            except (ValueError,TypeError): raise AppError('ERR-CONTROL-INPUT','Cần người nhận hợp lệ.',422) from None
            if not isinstance(department,str) or not 3 <= len(department) <= 200: raise AppError('ERR-CONTROL-INPUT','Cần tổ/bộ phận nhận.',422)
            assert_owner(session,context,target,row.building_id)
            if target == row.owner_account_id: raise AppError('ERR-HANDOFF-SAME','Người nhận đã phụ trách.',409)
            row.handoff = {'status':'PENDING','previous':handoff, 'from_id':str(row.owner_account_id),'to_id':str(target),'department':department,
                'requested_by':str(context.account_id),'requested_at':now.isoformat(),'reason':body.reason,
                'due_at':(now+timedelta(minutes=(row.sla_policy_snapshot or {}).get('handoff_minutes',60))).isoformat()}
        elif body.action == 'ACK':
            if handoff.get('status') not in ('PENDING','ESCALATED') or handoff.get('to_id') != str(context.account_id): raise AppError('ERR-HANDOFF-ACK','Chỉ người nhận được tiếp nhận.',403)
            assert_owner(session,context,context.account_id,row.building_id)
            row.owner_account_id = context.account_id; row.handoff = {**handoff,'status':'ACCEPTED','accepted_at':now.isoformat(),'acceptance_basis':body.reason}
        elif body.action == 'REPEAT_CAUSE':
            if len(body.reason)>200: raise AppError('ERR-CONTROL-INPUT','Nguyên nhân tối đa 200 ký tự.',422)
            row.repeat_cause = body.reason
        else: raise AppError('ERR-STATE-TRANSITION','Thao tác điều phối không hợp lệ.',409)
        row.version += 1; row.updated_by_id=context.account_id; event(session,context,row,body.action,body.reason)
        # command requires PortalScope projections; ServiceRequest has owner scope instead.
        row.account_id = row.owner_account_id
        return row,'profile'
    return command(request,context,key,'request.control.'+body.action,{'id':str(identifier), **body.model_dump(mode='json')},execute,roles=SERVICE_ROLES)


@router.get('/service-quality')
def quality(request: Request, building_id: UUID, context: UserContext = Depends(get_current_user_context)):
    from app.models.service import ServiceRequest, CaseRecord
    with request.app.state.database.get_session() as session:
        building_scope(session,context,building_id,SERVICE_ROLES)
        rows = session.scalars(select(ServiceRequest).where(*context.scope_conditions(ServiceRequest),ServiceRequest.building_id==building_id)).all()
        groups = {}
        for row in rows:
            key = row.repeat_cause or 'UNCLASSIFIED'
            group = groups.setdefault(key,{'cause':key,'request_ids':[],'scores':[],'linked':[],'cases':[]})
            group['request_ids'].append(str(row.id))
            if row.csat_score is not None: group['scores'].append(row.csat_score)
            if row.linked_request_id: group['linked'].append({'id':str(row.id),'linked_id':str(row.linked_request_id),'type':row.link_type})
        cases = session.scalars(select(CaseRecord).where(*context.scope_conditions(CaseRecord),CaseRecord.building_id==building_id)).all()
        by_request = {str(r.id):r.repeat_cause or 'UNCLASSIFIED' for r in rows}
        for case in cases:
            if str(case.service_request_id) in by_request: groups[by_request[str(case.service_request_id)]]['cases'].append({'id':str(case.id),'status':case.status})
        for g in groups.values(): g['csat_average']=sum(g['scores'])/len(g['scores']) if g['scores'] else None; g['count']=len(g['request_ids'])
        return {'items':list(groups.values()),'as_of':utc_now()}


@router.get('/init-datasets')
def datasets(request: Request, building_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        rows=session.scalars(select(InitDataset).where(*context.scope_conditions(InitDataset),*staff_conditions(context,InitDataset,MANAGEMENT),
            *([InitDataset.building_id==building_id] if building_id else [])).order_by(InitDataset.created_at.desc()).limit(50)).all()
        items=[]
        for row in rows:
            _,digest=dataset_sources(session,context,row)
            items.append({**view(row),'source_changed':digest!=row.source_digest,'effective_status':'STALE' if digest!=row.source_digest else row.status})
        return {'items':items,'limit':50}


@router.post('/init-datasets',status_code=201)
def dataset_create(body: DatasetInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        building_scope(session,context,body.building_id,MANAGEMENT)
        row=InitDataset(**scope_values(context,building_id=body.building_id),name=body.name,manifest=body.manifest.model_dump(mode='json'))
        row.checks,row.source_digest=dataset_sources(session,context,row); session.add(row); return row,'profile'
    return command(request,context,key,'dataset.create',body.model_dump(mode='json'),execute)


@router.get('/init-datasets/{identifier}')
def dataset_detail(identifier:UUID,request:Request,context:UserContext=Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row=load(session,context,InitDataset,identifier,MANAGEMENT)
        checks,digest=dataset_sources(session,context,row)
        return {**view(row),'current_checks':checks,'source_changed':digest!=row.source_digest,
            'effective_status':'STALE' if digest!=row.source_digest else row.status}


@router.post('/init-datasets/{identifier}/actions')
def dataset_action(identifier:UUID,body:PortalAction,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        row=load(session,context,InitDataset,identifier,MANAGEMENT,lock=True);require_version(row.version,body.expected_version)
        if body.action=='UPDATE':
            state(row,('DRAFT','REJECTED')); row.manifest=data_model(DatasetManifest,body.data).model_dump(mode='json')
            row.checks,row.source_digest=dataset_sources(session,context,row);row.status='DRAFT';row.checker_id=None;row.confirmer_id=None
        elif body.action=='REFRESH':
            row.checks,row.source_digest=dataset_sources(session,context,row);row.status='DRAFT';row.checker_id=None;row.confirmer_id=None
        else:
            checks,digest=dataset_sources(session,context,row)
            if digest!=row.source_digest: raise AppError('ERR-DATASET-STALE','Nguồn thay đổi; cập nhật và xác nhận lại.',409)
            if body.action=='SUBMIT': state(row,('DRAFT','REJECTED'));row.status='SUBMITTED'
            elif body.action=='CHECK':
                state(row,('SUBMITTED',));independent(context,row)
                if not checks['passed']: raise AppError('ERR-DATASET-CHECKS','Còn sai lệch hoặc batch chưa được áp dụng đầy đủ.',409)
                row.checker_id=context.account_id;row.status='CHECKED'
            elif body.action=='CONFIRM':
                state(row,('CHECKED',));independent(context,row)
                if context.account_id==row.checker_id: raise AppError('ERR-INDEPENDENT-CHECKER','Người xác nhận phải khác người kiểm tra.',403)
                assert_owner(session,context,row.checker_id,row.building_id,('admin','director'))
                if not checks['passed']: raise AppError('ERR-DATASET-CHECKS','Kiểm tra bắt buộc chưa đạt.',409)
                row.confirmer_id=context.account_id;row.status='ACCEPTED'
            elif body.action=='REJECT': state(row,('SUBMITTED','CHECKED'));independent(context,row);row.status='REJECTED'
            else: raise AppError('ERR-STATE-TRANSITION','Thao tác bộ dữ liệu không hợp lệ.',409)
            row.checks=checks
        row.version+=1;event(session,context,row,body.action,body.reason);return row,'profile'
    return command(request,context,key,'dataset.'+body.action,{'id':str(identifier),**body.model_dump(mode='json')},execute)


def source_catalog():
    from app.models.sad_extensions import CommercialLedger
    from app.models.service import ServiceRequest,WorkOrder
    from app.models.maintenance import Asset
    from app.models.operational_control import OperationsRecord,StockMovement,StockItem,Expense,Meter,MeterReading,TreasuryMovement,TreasuryAccount
    from app.models.resident_portal import PortalDossier,PortalFeeSource,PortalDeposit,VehicleRegistration,FacilityBooking,ResidentCredential,ServiceEnrollment,PortalFinancialAdjustment
    from app.models.billing import BillingInvoice,BillingInvoiceItem,Payment,PaymentAllocation,ArLedgerEntry
    from app.models.financial_control import ArCase,FinanceCommand
    from app.services.operational_control import TECHNICAL,FINANCIAL,SECURITY
    return {m.__tablename__:(m,roles) for models,roles in (
        ((ServiceRequest,WorkOrder,CommunityTask),SERVICE_ROLES),((Asset,Meter,MeterReading,StockItem,StockMovement),TECHNICAL),
        ((CommercialLedger,Expense,TreasuryMovement,TreasuryAccount,PortalFeeSource,PortalDeposit,PortalFinancialAdjustment,BillingInvoice,BillingInvoiceItem,Payment,PaymentAllocation,ArLedgerEntry,ArCase,FinanceCommand),FINANCIAL),
        ((PortalDossier,VehicleRegistration,FacilityBooking,ServiceEnrollment),MANAGEMENT),((ResidentCredential,),SECURITY),((OperationsRecord,),('admin','director','cskh','accountant','security','technical_lead','cleaning')))
        for m in models}


def source_view(session,context,source,identifier,*,expected_building=None):
    spec=source_catalog().get(source)
    if not spec:raise scope_not_found()
    model,roles=spec;row=load(session,context,model,identifier,roles)
    if expected_building and row.building_id!=expected_building:raise scope_not_found()
    if source=='operations_records':
        from app.services.operations_records import definition
        _,specific=definition(row.kind);context.assert_building_role(row.building_id,*specific)
    links=[]
    fields={'service_request_id':'service_requests','work_order_id':'work_orders','asset_id':'assets','budget_id':'treasury_accounts','fund_id':'treasury_accounts',
        'expense_id':'operational_expenses','procurement_id':'operations_records','meter_id':'operational_meters','payment_id':'payments',
        'billing_invoice_id':'billing_invoices','invoice_id':'billing_invoices','content_id':'portal_content',
        'project_id':'operations_records','lease_id':'operations_records','policy_id':'operations_records','target_id':'operations_records','measure_id':'operations_records','contract_id':'operations_records','source_record_id':'operations_records','proposal_id':'operations_records','space_id':'operations_records'}
    from app.services.report_metrics import number_safe_json
    data=number_safe_json(view(row));nested=data.get('data',{})
    if source in ('portal_fee_sources','portal_deposits'):
        target={'PARKING':'resident_vehicles','BOOKING':'resident_bookings','SERVICE':'resident_service_enrollments','METER':'operational_meter_readings'}.get(data['source_kind'])
        if target:fields['source_id']=target
    if source=='finance_commands':fields['target_id']='payments'
    for field,target in fields.items():
        value=data.get(field) or nested.get(field)
        if value and target in source_catalog():
            try:
                model,roles=source_catalog()[target];related=load(session,context,model,UUID(str(value)),roles)
                if target=='operations_records':
                    from app.services.operations_records import definition
                    _,specific=definition(related.kind);context.assert_building_role(related.building_id,*specific)
            except (AppError,ValueError):continue
            if related.building_id==row.building_id:links.append({'source':target,'id':str(related.id),'label':getattr(related,'code',getattr(related,'title',target))})
    from app.models.operational_control import StockMovement,Expense
    if source=='billing_invoices':
        from app.models.resident_portal import PortalFeePosting,PortalFeeSource
        from app.models.billing import BillingInvoiceItem
        for child in session.scalars(select(BillingInvoiceItem).where(*context.scope_conditions(BillingInvoiceItem),BillingInvoiceItem.building_id==row.building_id,BillingInvoiceItem.billing_invoice_id==row.id)):
            links.append({'source':child.__tablename__,'id':str(child.id),'label':child.description})
        sources=session.scalars(select(PortalFeeSource).join(PortalFeePosting,PortalFeePosting.fee_source_id==PortalFeeSource.id).where(
            *context.scope_conditions(PortalFeeSource),PortalFeeSource.building_id==row.building_id,PortalFeePosting.invoice_id==row.id)).all()
        for fee in sources:links.append({'source':fee.__tablename__,'id':str(fee.id),'label':fee.description})
    if source=='work_orders':
        from app.services.operational_control import TECHNICAL
        try:
            context.assert_building_role(row.building_id,*TECHNICAL)
            for m in session.scalars(select(StockMovement).where(*context.scope_conditions(StockMovement),StockMovement.building_id==row.building_id,StockMovement.work_order_id==row.id)):
                links.append({'source':m.__tablename__,'id':str(m.id),'label':m.reference})
        except AppError:pass
    documents=[]
    document_id=data.get('document_id') or nested.get('document_id')
    if document_id:
        from app.api.portal_documents import _document
        try:
            doc=_document(session,context,UUID(str(document_id)))
            if doc.building_id in (None,row.building_id) and not doc.revoked_at and not doc.quarantined:
                documents.append({'id':str(doc.id),'title':doc.title,'content_version':doc.content_version,'unit_id':str(doc.unit_id) if doc.unit_id else None})
        except (AppError,ValueError):pass
    return {'source':source,'current':data,'links':links,'evidence_documents':documents,'as_of':utc_now(),'evidence_reference':data.get('evidence_reference') or nested.get('evidence_reference'),
        'integration_state':'NOT_CONFIGURED' if source=='resident_credentials' and data.get('sync_status')=='NOT_CONFIGURED' else None}


@router.get('/sources/{source}/{identifier}')
def source_detail(source:str,identifier:UUID,request:Request,context:UserContext=Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:return source_view(session,context,source,identifier)


@router.get('/capabilities')
def capabilities(request:Request,context:UserContext=Depends(get_current_user_context)):
    context.assert_role('admin','director','cskh','accountant','technical_lead','technician','security','cleaning','resident')
    settings=request.app.state.settings
    from app.services.vnpay import require_configuration
    from app.services.portal_mail import require_smtp
    def configured(check):
        try:check()
        except AppError:return 'NOT_CONFIGURED'
        return 'CONFIGURED'
    from app.models.operational_control import IntegrationEndpoint
    from app.models.unit import Unit
    from app.services.resident_portal import resident, staff_conditions
    with request.app.state.database.get_session() as session:
        allowed = [IntegrationEndpoint.building_id.in_(select(Unit.building_id).where(Unit.id.in_(context.resident_unit_ids)))] if resident(context) else list(staff_conditions(context, IntegrationEndpoint, ('admin','director','cskh','accountant','technical_lead','security','cleaning')))
        endpoints = session.scalars(select(IntegrationEndpoint).where(*context.scope_conditions(IntegrationEndpoint), *allowed, IntegrationEndpoint.status == 'ACTIVE')).all()
        def exchange_status(kinds):
            selected = [r for r in endpoints if r.kind in kinds]
            return 'CONFIGURED' if selected else 'NOT_CONFIGURED'
    return {'items':[{'name':'VNPay','status':configured(lambda:require_configuration(settings,context.tenant_id))},
        {'name':'SMTP email','status':configured(lambda:require_smtp(settings))},
        {'name':'Kiểm soát ra vào qua hợp đồng JSON','status':exchange_status(('ACCESS','PARKING'))},
        {'name':'Trao đổi kế toán qua hợp đồng JSON','status':exchange_status(('ACCOUNTING',))},
        {'name':'Trợ lý có nguồn tham chiếu','status':'CONFIGURED'}]}
