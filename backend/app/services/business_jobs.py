"""Frozen run candidates, per-object savepoints and globally deduplicated effects."""
from datetime import datetime, time, UTC, timezone, timedelta
from uuid import UUID
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func
from app.core.exceptions import AppError
from app.models.sad_completion import CommunityTask, JobEffect
from app.models.operational_control import JobRun, OperationsRecord
from app.models.resident_portal import (ResidentDocument,PortalContent,PortalPaymentIntent,ResidentCredential,VehicleRegistration,FacilityBooking,ServiceEnrollment,PortalDossier)
from app.models.property import LeaseContract,UnitProfileEpisode
from app.models.maintenance import Asset, MaintenancePlan
from app.models.service import ServiceRequest
from app.services.resident_portal import scope_values
from app.services.operational_control import event
from app.services.sad_completion import fingerprint
from app.services.r2 import utc_now

KINDS = ('LIFECYCLE','DOCUMENT_EXPIRY','MAINTENANCE','SLA_SCAN','ASSET_DEADLINE','SOP_ACK','COMMUNITY_DECISION','CONTRACT_MILESTONE')
MODELS = {m.__tablename__:m for m in (ResidentDocument,MaintenancePlan,ServiceRequest,Asset,OperationsRecord,CommunityTask,PortalContent,PortalPaymentIntent,ResidentCredential,VehicleRegistration,FacilityBooking,ServiceEnrollment,PortalDossier,LeaseContract,UnitProfileEpisode)}


def candidates(session, context, schedule, cutoff):
    day=cutoff.astimezone(timezone(timedelta(hours=7))).date()
    def rows(model,*conditions):
        return session.scalars(select(model).where(*context.scope_conditions(model),model.building_id==schedule.building_id,*conditions).order_by(model.id)).all()
    out=[]
    def add(row,moment,subtype=''):
        out.append({'source_type':row.__tablename__,'source_id':str(row.id),'version':row.version,
            'moment':str(moment),'subtype':subtype,'effect_key':fingerprint((schedule.kind,str(row.id),str(moment),subtype))})
    if schedule.kind=='LIFECYCLE':
        from sqlalchemy import or_
        from app.models.resident_portal import PortalDossierEvent
        specs=((LeaseContract,(LeaseContract.status=='ACTIVE',LeaseContract.valid_to<=day)),
            (UnitProfileEpisode,(UnitProfileEpisode.valid_from<=day,or_(UnitProfileEpisode.valid_to.is_(None),UnitProfileEpisode.valid_to>day))),
            (PortalDossier,(PortalDossier.kind=='PROFILE_CHANGE',PortalDossier.status.in_(('APPROVED','COMPLETED')),PortalDossier.valid_from<=day,
                ~select(PortalDossierEvent.id).where(PortalDossierEvent.dossier_id==PortalDossier.id,PortalDossierEvent.action=='APPLY').exists())),
            (OperationsRecord,(OperationsRecord.kind=='ASSET_CHANGE',OperationsRecord.status=='COMPLETED')),
            (PortalContent,(PortalContent.status=='PUBLISHED',PortalContent.publish_at<=cutoff,PortalContent.notified_at.is_(None))),
            (PortalPaymentIntent,(PortalPaymentIntent.status=='PENDING',PortalPaymentIntent.expires_at<=cutoff)),
            (VehicleRegistration,(VehicleRegistration.status!='CANCELLED',)),
            (ResidentCredential,(ResidentCredential.status.in_(('ACTIVE','LOCKED','LOST')),)),
            (FacilityBooking,(FacilityBooking.status.in_(('WAITING','AWAITING_DEPOSIT','CONFIRMED')),)),
            (ServiceEnrollment,(ServiceEnrollment.status.in_(('PENDING','ACTIVE','PAUSED')),)))
        for model,conditions in specs:
            for r in rows(model,*conditions):add(r,cutoff)
    elif schedule.kind=='DOCUMENT_EXPIRY':
        for r in rows(ResidentDocument,ResidentDocument.expires_on<=day,ResidentDocument.verification_status!='EXPIRED',ResidentDocument.revoked_at.is_(None)):add(r,r.expires_on)
    elif schedule.kind=='MAINTENANCE':
        for r in rows(MaintenancePlan,MaintenancePlan.is_active.is_(True),MaintenancePlan.next_due_at<=cutoff):add(r,r.next_due_at)
    elif schedule.kind=='SLA_SCAN':
        for r in rows(ServiceRequest,ServiceRequest.status.in_(('NEW','TRIAGED','IN_PROGRESS','WAITING_INFO'))):add(r,cutoff)
    elif schedule.kind=='ASSET_DEADLINE':
        for r in rows(Asset,Asset.status.not_in(('RETIRED','DISPOSED'))):
            for field in ('warranty_until','inspection_due_on'):
                value=getattr(r,field)
                if value and value<=day:add(r,value,field)
    elif schedule.kind=='COMMUNITY_DECISION':
        for r in rows(CommunityTask,CommunityTask.status.in_(('OPEN','IN_PROGRESS')),CommunityTask.due_at<=cutoff):add(r,r.due_at)
    elif schedule.kind in ('SOP_ACK','CONTRACT_MILESTONE'):
        for r in rows(OperationsRecord,OperationsRecord.kind==('TRAINING' if schedule.kind=='SOP_ACK' else 'CONTRACT_MILESTONE'),OperationsRecord.status.in_(('APPROVED','IN_PROGRESS'))):
            value=r.data.get('scheduled_at') if schedule.kind=='SOP_ACK' else r.data.get('due_on')
            if value and (datetime.fromisoformat(value)<=cutoff if schedule.kind=='SOP_ACK' else str(value)<=str(day)):add(r,value)
    if len(out)>5000:raise AppError('ERR-JOB-SIZE','Lượt chạy vượt 5000 đối tượng; cần thu hẹp lịch theo tòa.',422)
    return out


def perform(session,context,request,schedule,run,item):
    model=MODELS[item['source_type']]
    lock=int.from_bytes(bytes.fromhex(item['effect_key'])[:8],'big',signed=True)
    session.execute(select(func.pg_advisory_xact_lock(lock)))
    effect=session.scalar(select(JobEffect).where(JobEffect.site_id==schedule.site_id,JobEffect.effect_key==item['effect_key']))
    if effect:return {**effect.result,'replayed':True}
    if schedule.kind=='LIFECYCLE':
        import hashlib
        key=int.from_bytes(hashlib.sha256(f'portal-jobs:{context.tenant_id}:{context.assert_active_site()}'.encode()).digest()[:8],'big',signed=True)
        session.execute(select(func.pg_advisory_xact_lock(key)))
    row=session.scalar(select(model).where(model.id==UUID(item['source_id']),*context.scope_conditions(model),model.building_id==schedule.building_id).with_for_update().execution_options(populate_existing=True))
    if not row:raise AppError('ERR-JOB-SOURCE','Đối tượng không còn trong phạm vi.',409)
    if row.version!=item['version']:raise AppError('ERR-JOB-SOURCE-STALE','Nguồn thay đổi; cần lập lượt mới sau khi xử lý lượt lỗi.',409)
    result={}
    if schedule.kind=='LIFECYCLE':
        from dataclasses import replace
        from app.core.policy import UnitGrant
        from app.services.portal_jobs import tick
        narrowed=replace(context,role_grants=tuple(UnitGrant(g.role,schedule.building_id) for g in context.role_grants if g.role in ('admin','director')))
        result=tick(session,narrowed,request,cutoff=run.scheduled_at,target=row)
    elif schedule.kind=='MAINTENANCE':
        from app.api.maintenance import dispatch_maintenance_plan
        result=jsonable_encoder(dispatch_maintenance_plan(session,context,request,row,run.scheduled_at))
    elif schedule.kind=='SLA_SCAN':
        from app.services.sad_completion import scan_sla
        result={'breached':[str(i) for i in scan_sla(session,context,request,run.scheduled_at,building_id=schedule.building_id,identifier=row.id)]}
    else:
        from app.services.outbox import enqueue_notification
        recipients=[getattr(row,'owner_id',None) or getattr(row,'account_id',None) or schedule.account_id]
        if schedule.kind=='SOP_ACK':
            from app.services.sad_completion import assert_owner
            from app.models.account import Account
            recipients=[]
            for staff_id in row.data['staff_ids']:
                if staff_id in row.data.get('acknowledgements',{}):continue
                staff=session.get(OperationsRecord,UUID(staff_id))
                if staff and staff.kind=='STAFF':
                    recipient=UUID(staff.data['account_id']);account=session.get(Account,recipient)
                    if account and account.is_active:
                        assert_owner(session,context,recipient,schedule.building_id,('admin','director','cskh','technical_lead','technician','cleaning','security'))
                        recipients.append(recipient)
            result={'pending_acknowledgements':len(recipients),'sop_id':row.data['sop_id']}
        if schedule.kind=='DOCUMENT_EXPIRY':row.verification_status='EXPIRED';row.version+=1
        for recipient in set(recipients):
            enqueue_notification(session,context,request,event_type='BusinessDeadlineDue',resource_type=row.__class__.__name__,resource_id=row.id,
                recipient_account_id=recipient,template_code='PORTAL_UPDATE',template_snapshot={'title':'Nhắc mốc nghiệp vụ: '+schedule.name,
                    'body':f'{getattr(row,"title",getattr(row,"name",schedule.kind))} · {item["moment"]}', 'unit_id':str(getattr(row,'unit_id',None)) if getattr(row,'unit_id',None) else None})
        result={**result,'notifications_queued':len(set(recipients))}
    result=result or {'skipped':True}
    session.add(JobEffect(**scope_values(context,building_id=schedule.building_id),effect_key=item['effect_key'],run_id=run.id,
        source_type=item['source_type'],source_id=row.id,result=result))
    return result


def run_business_schedule(session,context,request,schedule,*,retry=False):
    if schedule.next_run_at>utc_now():raise AppError('ERR-JOB-NOT-DUE','Tác vụ chưa đến hạn.',409)
    run=session.scalar(select(JobRun).where(JobRun.schedule_id==schedule.id,JobRun.scheduled_at==schedule.next_run_at).with_for_update())
    if run and (not retry or run.status not in ('FAILED','PARTIAL')):return run
    if not run:
        run=JobRun(**scope_values(context,building_id=schedule.building_id),schedule_id=schedule.id,scheduled_at=schedule.next_run_at,status='RUNNING',result={})
        session.add(run);session.flush()
        run.result={'run_key':f'{schedule.id}:{run.scheduled_at.isoformat()}', 'cutoff':run.scheduled_at.isoformat(), 'kind':schedule.kind,
            'items':[{**i,'status':'PENDING'} for i in candidates(session,context,schedule,run.scheduled_at)]}
    items=[]
    for item in run.result['items']:
        if item['status']=='SUCCEEDED':items.append(item);continue
        try:
            with session.begin_nested():result=perform(session,context,request,schedule,run,item);session.flush()
            items.append({**item,'status':'SUCCEEDED','result':result,'error_code':None})
        except Exception as exc:
            items.append({**item,'status':'FAILED','error_code':exc.code if isinstance(exc,AppError) else 'ERR-JOB-FAILED'})
    failures=sum(i['status']=='FAILED' for i in items)
    run.result={**run.result,'items':items,'failed':failures,'succeeded':len(items)-failures}
    run.status='PARTIAL' if failures and failures<len(items) else 'FAILED' if failures else 'SUCCEEDED'
    run.version+=1
    if not failures:
        from datetime import timedelta
        schedule.next_run_at=run.scheduled_at+timedelta(minutes=schedule.interval_minutes);schedule.version+=1
    event(session,context,run,run.status,'Lượt chạy giữ kết quả từng đối tượng; retry chỉ phần lỗi.')
    return run
