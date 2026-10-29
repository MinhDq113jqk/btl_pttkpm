"""Calendar SLA and reproducible initialization evidence. No external I/O."""
import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select
from fastapi.encoders import jsonable_encoder
from app.core.exceptions import AppError
from app.core.policy import context_for_account, scope_not_found
from app.models.account import Account
from app.models.sad_completion import SlaPolicy
from app.services.r2 import utc_now

SERVICE_ROLES = ('admin', 'director', 'cskh', 'technical_lead')


def notify_content_change(session, context, request, row, reason):
    from sqlalchemy import or_
    from app.models.person import UnitPersonRelationship
    from app.services.outbox import enqueue_notification
    conditions = [UnitPersonRelationship.tenant_id == row.tenant_id, UnitPersonRelationship.site_id == row.site_id,
        UnitPersonRelationship.valid_from <= utc_now().date(), or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > utc_now().date())]
    if row.building_id: conditions.append(UnitPersonRelationship.building_id == row.building_id)
    if row.unit_id: conditions.append(UnitPersonRelationship.unit_id == row.unit_id)
    recipients = session.scalars(select(Account.id).join(UnitPersonRelationship, Account.person_id == UnitPersonRelationship.person_id).where(Account.is_active.is_(True),Account.tenant_id == row.tenant_id,*conditions).distinct()).all()
    for recipient in recipients:
        enqueue_notification(session,context,request,event_type='PortalContentChanged',resource_type='PortalContent',resource_id=row.id,
            recipient_account_id=recipient,template_code='PORTAL_CONTENT',template_snapshot={'title':row.title,'body':reason,'unit_id':str(row.unit_id) if row.unit_id else None})


def fingerprint(value):
    return hashlib.sha256(json.dumps(jsonable_encoder(value), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def assert_owner(session, context, identifier, building_id, roles=SERVICE_ROLES):
    account = session.get(Account, identifier)
    if account is None or account.tenant_id != context.tenant_id or not account.is_active: raise scope_not_found()
    owner = context_for_account(session, account, context.assert_active_site())
    owner.assert_building_role(building_id, *(roles if building_id else ('admin','director')))
    return account


def capture_sla(session, record):
    policy = session.scalar(select(SlaPolicy).where(SlaPolicy.tenant_id == record.tenant_id,
        SlaPolicy.site_id == record.site_id, SlaPolicy.building_id == record.building_id,
        SlaPolicy.category_id == record.category_id, SlaPolicy.status == 'ACTIVE').order_by(SlaPolicy.created_at.desc()))
    if policy:
        record.sla_policy_snapshot = {**policy.definition, 'policy_id': str(policy.id), 'version': policy.version}
        record.sla_duration_minutes = policy.definition['minutes']


def sla_deadline(record, *, as_of=None):
    """Consume only published working minutes, excluding authorized pause intervals."""
    now = as_of or utc_now()
    policy = record.sla_policy_snapshot or {}
    pauses = [(datetime.fromisoformat(p['started_at']), datetime.fromisoformat(p['ended_at']) if p.get('ended_at') else now)
              for p in (record.sla_pauses or [])]
    local = timezone(timedelta(hours=7))
    cursor = record.sla_started_at.astimezone(local)
    remaining = record.sla_duration_minutes * 60
    weekdays = policy.get('weekdays', list(range(1, 8)))
    opened, closed = policy.get('opens_minute', 0), policy.get('closes_minute', 1440)
    for _ in range(40000):
        midnight = cursor.replace(hour=0, minute=0, second=0, microsecond=0)
        start = max(cursor, midnight + timedelta(minutes=opened))
        end = midnight + timedelta(minutes=closed)
        intervals = [(start, end)] if cursor.isoweekday() in weekdays and start < end else []
        for pause_start, pause_end in pauses:
            intervals = [(a, min(b, pause_start)) for a, b in intervals if a < min(b, pause_start)] + [
                (max(a, pause_end), b) for a, b in intervals if max(a, pause_end) < b]
        for a, b in sorted(intervals):
            seconds = (b-a).total_seconds()
            if remaining <= seconds: return (a + timedelta(seconds=remaining)).astimezone(UTC)
            remaining -= seconds
        cursor = midnight + timedelta(days=1)
    raise AppError('ERR-SLA-CALENDAR', 'Lịch SLA vượt giới hạn tính toán.', 422)


def scan_sla(session, context, request, cutoff, *, building_id=None, identifier=None):
    from app.models.service import ServiceRequest
    from app.services.r2 import audit, emit
    from app.services.resident_portal import staff_conditions
    rows = session.scalars(select(ServiceRequest).where(*context.scope_conditions(ServiceRequest),
        *staff_conditions(context, ServiceRequest, ('admin', 'director')),
        *([ServiceRequest.building_id == building_id] if building_id else []),
        *([ServiceRequest.id == identifier] if identifier else []),
        ServiceRequest.status.in_(('NEW','TRIAGED','IN_PROGRESS','WAITING_INFO'))).with_for_update()).all()
    breached = []
    for row in rows:
        changed = False
        handoff = row.handoff or {}
        if handoff.get('status') == 'PENDING' and datetime.fromisoformat(handoff['due_at']) <= cutoff:
            row.handoff = {**handoff, 'status': 'ESCALATED', 'escalated_at': cutoff.isoformat()}; changed = True
            audit(session, context, request, event_type='RequestHandoffEscalated', action='escalate',
                resource_type='ServiceRequest', resource_id=row.id, building_id=row.building_id)
            emit(session, context, request, event_type='RequestHandoffEscalated', resource_type='ServiceRequest', resource_id=row.id)
        paused = any(not p.get('ended_at') for p in (row.sla_pauses or []))
        if not paused and not row.sla_breached_at and sla_deadline(row, as_of=cutoff) <= cutoff:
            row.sla_breached_at = cutoff; breached.append(row.id); changed = True
            audit(session, context, request, event_type='SlaBreached', action='escalate', resource_type='ServiceRequest', resource_id=row.id, building_id=row.building_id)
            emit(session, context, request, event_type='SlaBreached', resource_type='ServiceRequest', resource_id=row.id)
        if changed: row.version += 1; row.updated_by_id = context.account_id
    return breached


def dataset_sources(session, context, row):
    from app.models.import_run import ImportRun
    from app.models.submission_import import SubmissionImportRun, SubmissionExternalReference
    from app.models.unit import Unit
    from app.models.billing import BillingAccount, BillingInvoice, Payment
    from app.models.operational_control import Meter, StockItem, Expense, TreasuryMovement
    from app.models.maintenance import Asset
    from app.models.operations import CleaningShift,SecurityIncident,SecurityShift
    from app.models.parcel import Parcel
    models = (Unit, BillingAccount, BillingInvoice, Payment, Meter, StockItem, Expense, TreasuryMovement,Asset,CleaningShift,SecurityIncident,SecurityShift,Parcel)
    # Hold source and domain tables stable until the decision transaction ends.
    # This also prevents accepting a digest computed across different committed states.
    from sqlalchemy import text
    session.execute(text('LOCK TABLE '+', '.join('greencity.'+name for name in sorted(
        {m.__tablename__ for m in models}|{'import_runs','submission_import_runs','submission_external_references','persons','accounts','account_roles','unit_person_relationships'}))+' IN SHARE MODE'))
    sources, errors = [], []
    counts = {'csv_rows': 0, 'loader_rows': 0}
    required_counts={'units'} if row.manifest['csv_run_ids'] else set()
    for identifier in row.manifest['csv_run_ids']:
        batch = session.scalar(select(ImportRun).where(ImportRun.id == UUID(identifier), ImportRun.tenant_id == row.tenant_id,
            ImportRun.site_id == row.site_id, ImportRun.building_id == row.building_id))
        if not batch: raise scope_not_found()
        sources.append({'kind':'CSV', 'id': str(batch.id), 'hash': batch.source_sha256, 'mapping':batch.mapping_hash,
            'version':batch.version, 'status':batch.status, 'rows':batch.total_rows, 'applied':batch.applied_rows, 'errors':batch.error_rows, 'warnings':batch.warning_rows, 'skipped':batch.skipped_rows})
        counts['csv_rows'] += batch.applied_rows
        if batch.status != 'APPLIED' or batch.error_rows or batch.warning_rows or batch.skipped_rows or batch.source_is_quarantined:
            errors.append('CSV:'+str(batch.id))
    for identifier in row.manifest['loader_run_ids']:
        batch = session.get(SubmissionImportRun, UUID(identifier))
        refs = session.scalars(select(SubmissionExternalReference).where(SubmissionExternalReference.import_run_id == UUID(identifier))).all()
        # Loader batches are global: never expose or accept a mixed-tenant batch.
        if not batch or not refs or any(r.tenant_id != context.tenant_id for r in refs): raise scope_not_found()
        scoped_refs=loader_references(session,context,refs,row.building_id)
        if not scoped_refs:raise scope_not_found()
        sources.append({'kind':'LOADER', 'id':str(batch.id), 'hash':batch.manifest_sha256, 'version':batch.version,
            'status':batch.status, 'stage':batch.stage, 'rows':batch.total_rows, 'failure':batch.failure_code,
            'scoped_references':len(scoped_refs),'references':sorted((r.entity_type, str(r.target_id), r.payload_sha256, r.version, loader_target_stamp(session,r)) for r in scoped_refs)})
        counts['loader_rows'] += len(scoped_refs)
        for ref in scoped_refs:
            key='loader:'+ref.entity_type
            counts[key]=counts.get(key,0)+1;required_counts.add(key)
        if batch.status != 'APPLIED' or batch.failure_code: errors.append('LOADER:'+str(batch.id))
    domain = []
    values = {}
    for model in models:
        conditions = [model.building_id == row.building_id]
        if hasattr(model, 'tenant_id'): conditions += list(context.scope_conditions(model))
        records = session.scalars(select(model).where(*conditions).order_by(model.id)).all()
        counts[model.__tablename__] = len(records)
        domain.extend((model.__tablename__, str(r.id), getattr(r, 'version', 1), str(getattr(r, 'updated_at', ''))) for r in records)
        for field in ('total_vnd', 'outstanding_vnd', 'amount_vnd', 'paid_vnd'):
            if hasattr(model, field): values[model.__tablename__+'.'+field] = sum(getattr(r, field) for r in records)
    discrepancies = [{'field':k, 'expected':v, 'actual':counts.get(k), 'type':'COUNT'} for k,v in row.manifest['expected_counts'].items() if counts.get(k) != v]
    discrepancies += [{'field':k, 'expected':v, 'actual':values.get(k), 'type':'VALUE'} for k,v in row.manifest['expected_values'].items() if values.get(k) != v]
    errors.extend('MISSING_REQUIRED_COUNT:'+k for k in sorted(required_counts-set(row.manifest['expected_counts'])))
    checks = {'batches':sources, 'counts':counts, 'values':values, 'errors':errors, 'discrepancies':discrepancies,
        'required_counts':sorted(required_counts),
        'definitions':{'csv_rows':'Số dòng đã áp dụng từ các batch CSV chọn.', 'loader_rows':'Số tham chiếu loader thuộc tòa chọn; rows trong batch là số dòng toàn manifest.'},
        'passed':not errors and not discrepancies}
    return checks, fingerprint({'manifest':row.manifest, 'checks':checks, 'domain':domain})


def loader_references(session,context,refs,building_id):
    from app.models.unit import Unit
    from app.models.maintenance import Asset
    from app.models.operations import CleaningShift,SecurityIncident,SecurityShift
    from app.models.parcel import Parcel
    from app.models.person import UnitPersonRelationship
    catalog={m.__name__:m for m in (Unit,Asset,CleaningShift,SecurityIncident,SecurityShift,Parcel)}
    result=[]
    for ref in refs:
        model=catalog.get(ref.entity_type)
        if model:
            conditions=[model.id==ref.target_id,model.building_id==building_id]
            if hasattr(model,'tenant_id'):conditions+=list(context.scope_conditions(model))
            if session.scalar(select(model.id).where(*conditions)):result.append(ref)
        elif ref.entity_type=='Person':
            if session.scalar(select(UnitPersonRelationship.id).where(*context.scope_conditions(UnitPersonRelationship),UnitPersonRelationship.building_id==building_id,UnitPersonRelationship.person_id==ref.target_id)):result.append(ref)
        elif ref.entity_type=='Account':
            try:assert_owner(session,context,ref.target_id,building_id,('admin','director','cskh','accountant','technical_lead','technician','security','cleaning'))
            except AppError:continue
            result.append(ref)
    return result


def loader_target_stamp(session,ref):
    from app.models.unit import Unit
    from app.models.maintenance import Asset
    from app.models.operations import CleaningShift,SecurityIncident,SecurityShift
    from app.models.parcel import Parcel
    from app.models.person import Person
    model=next((m for m in (Unit,Asset,CleaningShift,SecurityIncident,SecurityShift,Parcel,Person,Account) if m.__name__==ref.entity_type),None)
    row=session.get(model,ref.target_id) if model else None
    return (getattr(row,'version',getattr(row,'session_version',None)),str(getattr(row,'updated_at',None)))
