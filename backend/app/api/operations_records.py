from datetime import date, datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.operational_control import OperationsRecord
from app.schemas.operational_control import RecordInput
from app.schemas.resident_portal import PortalAction
from app.services.resident_portal import command, scope_values, unit_for, staff_conditions, view
from app.services.operational_control import building_scope, load, event, state, independent, data_model, as_uuid, financial_lock
from app.services.operations_records import definition, RECORDS, validate_links, approval_effect, completion_effect
from app.services.r2 import require_version, utc_now

router = APIRouter(prefix='/portal/operations', tags=['Operational dossiers'])
ALL_ROLES = ('admin', 'director', 'cskh', 'accountant', 'technical_lead', 'security', 'cleaning')


@router.get('/commercial-ledgers')
def commercial_ledgers(request: Request, context: UserContext = Depends(get_current_user_context)):
    from app.models.sad_extensions import CommercialLedger
    from app.services.operational_control import FINANCIAL
    context.assert_role(*FINANCIAL)
    with request.app.state.database.get_session() as session:
        return {'items': [view(r) for r in session.scalars(select(CommercialLedger).where(*context.scope_conditions(CommercialLedger), *staff_conditions(context, CommercialLedger, FINANCIAL)).order_by(CommercialLedger.created_at.desc()).limit(500))]}


@router.get('/resident-records')
def resident_records(request: Request, unit_id: UUID, context: UserContext = Depends(get_current_user_context)):
    context.assert_role('resident')
    if unit_id not in context.resident_unit_ids:
        raise scope_not_found()
    with request.app.state.database.get_session() as session:
        rows = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), OperationsRecord.unit_id == unit_id, OperationsRecord.kind.in_(('VISITOR', 'CONTRACTOR', 'VIOLATION')), OperationsRecord.status.not_in(('DRAFT', 'SUBMITTED', 'REJECTED', 'CANCELLED'))).order_by(OperationsRecord.created_at.desc()).limit(200)).all()
        return {'items': [view(row) for row in rows if row.data.get('host_account_id' if row.kind in ('VISITOR', 'CONTRACTOR') else 'subject_account_id') == str(context.account_id)]}


@router.post('/resident-records/{identifier}/actions')
def resident_record_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        context.assert_role('resident')
        row = session.scalar(select(OperationsRecord).where(OperationsRecord.id == identifier, *context.scope_conditions(OperationsRecord), OperationsRecord.unit_id.in_(context.resident_unit_ids)).with_for_update())
        if row is None:
            raise scope_not_found()
        person_key = 'host_account_id' if row.kind in ('VISITOR', 'CONTRACTOR') else 'subject_account_id'
        if row.kind not in ('VISITOR', 'CONTRACTOR', 'VIOLATION') or row.data.get(person_key) != str(context.account_id):
            raise scope_not_found()
        require_version(row.version, body.expected_version)
        if row.kind in ('VISITOR', 'CONTRACTOR') and body.action == 'HOST_CONFIRM':
            state(row, ('APPROVED',)); row.status = 'HOST_CONFIRMED'
        elif row.kind == 'VIOLATION' and body.action in ('EXPLAIN', 'APPEAL'):
            state(row, ('APPROVED', 'EXPLAINED', 'APPEALED', 'DECIDED')); row.status = 'EXPLAINED' if body.action == 'EXPLAIN' else 'APPEALED'
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Chỉ xác nhận khách, giải trình hoặc đề nghị xem xét lại hồ sơ của mình.', 409)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'profile'
    return command(request, context, key, 'resident.operations.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=ALL_ROLES)


@router.get('/options')
def options(request: Request, context: UserContext = Depends(get_current_user_context)):
    context.assert_role(*ALL_ROLES)
    from app.models.operational_control import Meter, MeterReading, TreasuryAccount, Expense, StockItem, StockMovement
    from app.models.resident_portal import PortalResource, VehicleRegistration, ResidentCredential, PortalDossier
    from app.models.maintenance import Asset
    from app.models.service import WorkOrder
    from app.models.parcel import Parcel
    from app.models.property import LeaseContract
    from app.models.account import Account
    from app.services.operational_control import TECHNICAL, FINANCIAL, MANAGEMENT, SECURITY
    from app.models.billing import FeePolicyVersion
    from app.models.billing import FeePolicy
    from app.models.property import PropertyNode
    from app.models.operations import SecurityIncident, CleaningTask, SecurityShift
    sources = [(PropertyNode, ALL_ROLES), (FeePolicy, FINANCIAL), (SecurityIncident, (*MANAGEMENT, 'security', 'cleaning')), (CleaningTask, (*MANAGEMENT, 'technical_lead')), (SecurityShift, (*MANAGEMENT, 'technical_lead')), (Meter, (*TECHNICAL, 'accountant')), (MeterReading, (*TECHNICAL, 'accountant')), (FeePolicyVersion, FINANCIAL), (TreasuryAccount, FINANCIAL), (Expense, FINANCIAL), (StockItem, (*TECHNICAL, 'accountant')), (StockMovement, TECHNICAL),
        (PortalResource, (*MANAGEMENT, 'security')), (VehicleRegistration, (*MANAGEMENT, 'security')), (ResidentCredential, SECURITY), (PortalDossier, (*MANAGEMENT, 'security')),
        (Asset, TECHNICAL), (WorkOrder, TECHNICAL), (Parcel, MANAGEMENT), (LeaseContract, FINANCIAL)]
    result = {}
    with request.app.state.database.get_session() as session:
        for model, roles in sources:
            if not any(r in context.roles for r in roles):
                continue
            rows = session.scalars(select(model).where(*context.scope_conditions(model), *staff_conditions(context, model, roles)).order_by(model.created_at.desc()).limit(500)).all()
            result[model.__tablename__] = [{'id': r.id, 'label': getattr(r, 'name', None) or getattr(r, 'title', None) or getattr(r, 'code', None) or getattr(r, 'plate', None) or getattr(r, 'reference', None) or str(r.id), 'kind': getattr(r, 'kind', None), 'version': getattr(r, 'version', None), 'building_id': r.building_id} for r in rows]
            if model is FeePolicyVersion:
                result['all_fee_versions'] = [{'id': r.id, 'label': f'{session.get(FeePolicy, r.fee_policy_id).name} · v{r.version_number} · {r.basis}', 'building_id': r.building_id} for r in rows if not r.published_at]
                from app.models.billing import FeePolicy
                result[model.__tablename__] = [{'id': r.id, 'label': f'{session.get(FeePolicy, r.fee_policy_id).name} · v{r.version_number} · {r.unit_rate_vnd} VND', 'building_id': r.building_id}
                    for r in rows if r.published_at and r.basis == 'SERVICE_UNIT']
        result['fee_policies'] = result.get('billing_fee_policies', [])
        from app.models.unit import Unit
        from app.models.building import Building
        from app.models.site import Site
        visible_units = select(Unit).join(Building).join(Site).where(Site.tenant_id == context.tenant_id, Site.id == context.assert_active_site(), *staff_conditions(context, Unit, ALL_ROLES))
        result['units'] = [{'id': u.id, 'label': u.unit_number, 'building_id': u.building_id} for u in session.scalars(visible_units)]
        allowed = [kind for kind, (_, roles) in RECORDS.items() if any(r in context.roles for r in roles)]
        if 'MASTER_DATA' not in allowed: allowed.append('MASTER_DATA')
        records = session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), *staff_conditions(context, OperationsRecord, ALL_ROLES), OperationsRecord.kind.in_(allowed)).order_by(OperationsRecord.created_at.desc()).limit(500)).all()
        result['operations_records'] = [{'id': r.id, 'label': r.title, 'kind': r.kind, 'version': r.version, 'building_id': r.building_id, 'status': r.status, 'related_id': r.related_id, 'catalog': r.data.get('catalog'), 'skills': r.data.get('skills'), 'required_skill': r.data.get('required_skill')} for r in records if r.kind != 'MASTER_DATA' or r.status == 'APPROVED']
        from app.models.sad_extensions import CommercialLedger
        from app.models.resident_portal import ResidentDocument
        if any(r in context.roles for r in FINANCIAL):
            result[CommercialLedger.__tablename__] = [{'id':r.id, 'label':f'{r.kind} · {r.amount_vnd} VND', 'building_id':r.building_id, 'version':r.version}
                for r in session.scalars(select(CommercialLedger).where(*context.scope_conditions(CommercialLedger), *staff_conditions(context, CommercialLedger, FINANCIAL)).limit(500))]
        if any(r in context.roles for r in (*MANAGEMENT,'technical_lead')):
            doc_conditions = [] if any(r in context.roles for r in MANAGEMENT) else [ResidentDocument.unit_id.is_(None), ResidentDocument.dossier_id.is_(None)]
            result[ResidentDocument.__tablename__] = [{'id':r.id, 'label':r.title, 'building_id':r.building_id, 'version':r.version}
                for r in session.scalars(select(ResidentDocument).where(*context.scope_conditions(ResidentDocument), *staff_conditions(context, ResidentDocument, (*MANAGEMENT,'technical_lead')),
                    *doc_conditions, ResidentDocument.verification_status=='VERIFIED', ResidentDocument.quarantined.is_(False), ResidentDocument.revoked_at.is_(None), ResidentDocument.archived_at.is_(None)).limit(500))]
        from app.services.sad_work import active_on
        result['catalog_entries'] = [{'id': r.id, 'building_id': r.building_id, 'catalog': r.data['catalog'], 'entries': r.data['entries']} for r in records if r.kind == 'MASTER_DATA' and active_on(r, utc_now().date())]
        # Account selection is limited to accounts currently entitled in the selected site.
        from app.models.account import AccountRole
        from app.core.policy import context_for_account
        from app.models.person import UnitPersonRelationship
        from sqlalchemy import or_
        from app.services.portal_finance import business_date
        buildings = [g.building_id for g in context.role_grants if g.role in ALL_ROLES and g.building_id]
        broad = any(g.role in ('admin', 'director', 'accountant') and g.building_id is None for g in context.role_grants)
        ids = select(AccountRole.account_id).where(AccountRole.effective_at(), AccountRole.site_id == context.assert_active_site(), *(() if broad else (AccountRole.building_id.in_(buildings),)))
        residents = select(UnitPersonRelationship.person_id).where(UnitPersonRelationship.tenant_id == context.tenant_id,
            UnitPersonRelationship.site_id == context.assert_active_site(), UnitPersonRelationship.valid_from <= business_date(),
            or_(UnitPersonRelationship.valid_to.is_(None), UnitPersonRelationship.valid_to > business_date()),
            *(() if broad else (UnitPersonRelationship.building_id.in_(buildings),)))
        accounts = session.scalars(select(Account).where(Account.tenant_id == context.tenant_id, or_(Account.id.in_(ids), Account.person_id.in_(residents)), Account.is_active.is_(True)).limit(500)).all()
        result['accounts'] = [{'id': a.id, 'label': a.full_name} for a in accounts]
        from app.models.person import Person
        if 'admin' in context.roles:
            result['persons'] = [{'id': p.id, 'label': p.full_name} for p in session.scalars(select(Person).where(Person.tenant_id == context.tenant_id).limit(500))]
    return result


@router.get('/catalog')
def catalog(context: UserContext = Depends(get_current_user_context)):
    return {'items': [{'kind': kind, 'schema': model.model_json_schema()} for kind, (model, roles) in RECORDS.items() if kind != 'INSURANCE' and any(r in context.roles for r in roles)]}


@router.get('/records/{identifier}/progress')
def record_progress(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    from app.models.operational_control import Meter, MeterReading
    from app.services.operational_control import TECHNICAL
    with request.app.state.database.get_session() as session:
        row = load(session, context, OperationsRecord, identifier, ALL_ROLES)
        _, roles = definition(row.kind)
        context.assert_building_role(row.building_id, *roles)
        from app.services import sad_extensions
        if row.kind in sad_extensions.RECORDS:
            return sad_extensions.progress(session, context, row)
        if row.kind != 'METER_CYCLE':
            raise scope_not_found()
        result = []
        for identifier in row.data['meter_ids']:
            meter = load(session, context, Meter, as_uuid(identifier), TECHNICAL)
            readings = session.scalars(select(MeterReading).where(MeterReading.meter_id == meter.id,
                MeterReading.read_on >= date.fromisoformat(row.data['starts_on']), MeterReading.read_on <= date.fromisoformat(row.data['ends_on']))).all()
            result.append({'id': meter.id, 'code': meter.code, 'readings': [view(r) for r in readings],
                'status': 'VERIFIED' if any(r.status == 'VERIFIED' for r in readings) else 'UNREADABLE' if str(meter.id) in row.data.get('unreadable', {}) else 'MISSING',
                'reason': row.data.get('unreadable', {}).get(str(meter.id))})
        return {'items': result, 'missing': sum(r['status'] == 'MISSING' for r in result)}


@router.get('/records')
def records(request: Request, kind: str, context: UserContext = Depends(get_current_user_context)):
    _, roles = definition(kind)
    with request.app.state.database.get_session() as session:
        return {'items': [view(r) for r in session.scalars(select(OperationsRecord).where(*context.scope_conditions(OperationsRecord), *staff_conditions(context, OperationsRecord, roles), OperationsRecord.kind == kind).order_by(OperationsRecord.created_at.desc()).limit(200))]}


@router.post('/records', status_code=201)
def create_record(body: RecordInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        financial_lock(session, context)
        model, roles = definition(body.kind); building_scope(session, context, body.building_id, roles)
        unit = unit_for(session, context, body.unit_id, roles=roles) if body.unit_id else None
        if unit and unit.building_id != body.building_id:
            raise scope_not_found()
        data = data_model(model, body.data).model_dump(mode='json')
        row = OperationsRecord(**scope_values(context, unit, building_id=body.building_id), kind=body.kind, title=body.title, related_id=body.related_id, data=data)
        validate_links(session, context, row); session.add(row); event(session, context, row, 'CREATE', body.title)
        return row, 'profile'
    return command(request, context, key, 'operations.create', body.model_dump(mode='json'), execute, roles=ALL_ROLES)


@router.post('/records/{identifier}/actions')
def record_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        financial_lock(session, context)
        row = load(session, context, OperationsRecord, identifier, ALL_ROLES, lock=True)
        model, roles = definition(row.kind); context.assert_building_role(row.building_id, *roles)
        require_version(row.version, body.expected_version)
        if body.action == 'EDIT':
            state(row, ('DRAFT', 'REJECTED')); row.data = data_model(model, body.data).model_dump(mode='json'); row.status = 'DRAFT'; validate_links(session, context, row)
        elif body.action == 'SELECT_QUOTE':
            state(row, ('DRAFT', 'SUBMITTED'))
            if row.kind != 'PURCHASE':
                raise AppError('ERR-RECORD-KIND', 'Chỉ đề nghị mua được chọn báo giá.', 422)
            quote = load(session, context, OperationsRecord, as_uuid(body.data.get('quotation_id')), roles)
            if quote.kind != 'QUOTATION' or quote.related_id != row.id or quote.status != 'APPROVED':
                raise AppError('ERR-QUOTE-SELECTION', 'Báo giá cần được duyệt và thuộc đề nghị này.', 409)
            row.data = {**row.data, 'selected_quote_id': str(quote.id), 'selection_reason': body.reason}
        elif body.action == 'SUBMIT':
            state(row, ('DRAFT', 'REJECTED')); validate_links(session, context, row); row.status = 'SUBMITTED'
        elif body.action == 'PREVIEW':
            state(row, ('DRAFT', 'REJECTED'))
            if row.kind != 'FEE_PUBLICATION':
                raise AppError('ERR-RECORD-KIND', 'Cần hồ sơ công bố biểu phí.', 422)
            from app.services.sad_work import preview_fee
            row.data = {**row.data, 'preview': preview_fee(session, context, row)}
        elif body.action in ('APPROVE', 'REJECT'):
            state(row, ('SUBMITTED',)); independent(context, row)
            if body.action == 'APPROVE':
                validate_links(session, context, row); approval_effect(session, context, row)
                row.status = 'APPROVED'; row.approved_by_id = context.account_id
            else:
                row.status = 'REJECTED'
        elif body.action == 'COMPLETE':
            state(row, ('APPROVED', 'IN_PROGRESS'))
            from app.models.account import Account
            from app.core.policy import context_for_account
            checker = session.get(Account, row.approved_by_id)
            if not checker or not checker.is_active:
                raise AppError('ERR-APPROVAL-STALE', 'Người duyệt không còn hoạt động.', 409)
            independent(context_for_account(session, checker, row.site_id), row)
            if row.kind in ('VISITOR', 'CONTRACTOR', 'VIOLATION', 'KEY_CUSTODY', 'PARCEL_CUSTODY', 'LOST_FOUND', 'TOOL_CUSTODY', 'RULE', 'SOP', 'MASTER_DATA', 'EMERGENCY_PLAN', 'STAFF', 'CONTRACT', 'DEPOSIT_POLICY', 'FEE_PUBLICATION', 'FEE_BENEFIT', 'BUILDING_ZONE', 'BUILDING_PROFILE', 'SITE_PROFILE', 'ORGANIZATION', 'UOM_CONVERSION', 'ASSET_WORK_LINK', 'ROSTER'):
                raise AppError('ERR-DOMAIN-WORKFLOW', 'Hồ sơ cần hoàn thành theo luồng nghiệp vụ riêng.', 409)
            from app.services.sad_work import complete
            complete(session, context, row, body.data)
            from app.services.sad_extensions import complete as extension_complete
            extension_complete(session, context, row)
            if row.kind == 'DELIVERY':
                independent(context, row)
                if body.data.get('defect_resolution'):
                    row.data = {**row.data, 'defect_resolution': str(body.data['defect_resolution'])[:2000]}
            if row.kind == 'METER_CYCLE':
                independent(context, row)
                from app.models.operational_control import MeterReading
                for meter_id in row.data['meter_ids']:
                    verified = session.scalar(select(MeterReading.id).where(MeterReading.meter_id == as_uuid(meter_id),
                        MeterReading.read_on >= date.fromisoformat(row.data['starts_on']), MeterReading.read_on <= date.fromisoformat(row.data['ends_on']), MeterReading.status == 'VERIFIED').limit(1))
                    if not verified and meter_id not in row.data.get('unreadable', {}):
                        raise AppError('ERR-METER-CYCLE-INCOMPLETE', 'Kỳ ghi còn đồng hồ thiếu chỉ số hoặc chưa có căn cứ không ghi được.', 409)
            completion_effect(session, context, row); row.status = 'COMPLETED'
        elif body.action in ('CLAIM_SUBMIT', 'CLAIM_OUTCOME'):
            from app.services.sad_extensions import action as extension_action
            extension_action(session, context, row, body)
        elif body.action == 'UNREADABLE':
            state(row, ('APPROVED', 'IN_PROGRESS'))
            if row.kind != 'METER_CYCLE' or str(body.data.get('meter_id')) not in row.data['meter_ids']:
                raise AppError('ERR-METER-CYCLE', 'Cần đồng hồ thuộc kỳ ghi này.', 422)
            row.data = {**row.data, 'unreadable': {**row.data.get('unreadable', {}), str(body.data['meter_id']): body.reason}}
        elif body.action in ('EXPLAIN', 'APPEAL', 'DECIDE', 'CORRECTIVE_COMPLETE'):
            if row.kind != 'VIOLATION':
                raise AppError('ERR-RECORD-KIND', 'Cần hồ sơ vi phạm.', 422)
            if body.action == 'DECIDE':
                state(row, ('APPROVED', 'EXPLAINED', 'APPEALED')); independent(context, row)
                if not body.data.get('confirmed_process_reference'):
                    raise AppError('ERR-POLICY-INCOMPLETE', 'Quyết định cần quy trình đã được xác nhận.', 422)
                row.status = 'DECIDED'
            elif body.action == 'CORRECTIVE_COMPLETE':
                state(row, ('DECIDED',)); row.status = 'COMPLETED'
            else:
                state(row, ('APPROVED', 'DECIDED', 'EXPLAINED', 'APPEALED')); row.status = 'EXPLAINED' if body.action == 'EXPLAIN' else 'APPEALED'
        elif body.action in ('HOST_CONFIRM', 'ENTER', 'EXIT'):
            if row.kind not in ('VISITOR', 'CONTRACTOR'):
                raise AppError('ERR-RECORD-KIND', 'Cần hồ sơ khách/nhà thầu.', 422)
            if body.action == 'HOST_CONFIRM':
                state(row, ('APPROVED',)); row.status = 'HOST_CONFIRMED'
                if not body.data.get('host_confirmation_reference'):
                    raise AppError('ERR-VISITOR-HOST', 'Cần căn cứ người tiếp đón xác nhận.', 422)
            elif body.action == 'ENTER':
                state(row, ('HOST_CONFIRMED',)); validate_links(session, context, row)
                if not datetime.fromisoformat(row.data['starts_at']) <= utc_now() < datetime.fromisoformat(row.data['ends_at']):
                    raise AppError('ERR-VISITOR-TIME', 'Ngoài thời hạn được phép vào.', 409)
                row.status = 'IN_PROGRESS'
            else:
                state(row, ('IN_PROGRESS',)); row.status = 'COMPLETED'
        elif body.action in ('ABSENCE', 'REPLACE_STAFF', 'HANDOVER'):
            if row.kind != 'ROSTER':
                raise AppError('ERR-RECORD-KIND', 'Cần lịch nhân sự.', 422)
            if body.action == 'ABSENCE':
                state(row, ('APPROVED',)); row.status = 'ABSENT'
            elif body.action == 'REPLACE_STAFF':
                state(row, ('APPROVED', 'ABSENT')); row.data = {**row.data, 'staff_id': str(as_uuid(body.data.get('staff_id')))}; validate_links(session, context, row); row.status = 'APPROVED'
            else:
                state(row, ('APPROVED', 'IN_PROGRESS'))
                from app.services.sad_work import record_ref
                receiver = record_ref(session, context, row, body.data.get('handover_to_roster_id'), 'ROSTER', ('APPROVED', 'IN_PROGRESS'))
                if receiver.id == row.id:
                    raise AppError('ERR-HANDOVER-RECEIVER', 'Cần ca tiếp nhận khác ca nguồn.', 422)
                row.data = {**row.data, 'handover_to_roster_id': str(receiver.id), 'handover_notes': body.reason, 'handover_requested_at': utc_now().isoformat()}
        elif body.action in ('MOVE_CUSTODY', 'RETURN', 'CLAIM'):
            if row.kind not in ('KEY_CUSTODY', 'PARCEL_CUSTODY', 'LOST_FOUND', 'TOOL_CUSTODY'):
                raise AppError('ERR-RECORD-KIND', 'Cần hồ sơ lưu giữ/bàn giao.', 422)
            state(row, ('APPROVED', 'IN_PROGRESS'))
            if any(not isinstance(body.data.get(k), str) or not 3 <= len(body.data[k].strip()) <= 1000 for k in ('recipient_verification_reference', 'condition')):
                raise AppError('ERR-CUSTODY-EVIDENCE', 'Cần xác minh người nhận và tình trạng giao nhận rõ ràng.', 422)
            if body.data['condition'] != row.data['condition'] and not all(isinstance(body.data.get(k), str) and 3 <= len(body.data[k].strip()) <= 1000 for k in ('discrepancy_reference', 'resolution_reference')):
                raise AppError('ERR-CUSTODY-DISCREPANCY', 'Tình trạng khác lúc nhận cần hồ sơ sai lệch và kết luận xử lý.', 422)
            if body.data.get('recipient_account_id'):
                from app.services.sad_work import account_in_building
                account_in_building(session, context, row, body.data['recipient_account_id'])
            if row.kind == 'PARCEL_CUSTODY':
                from app.models.parcel import Parcel
                parcel = load(session, context, Parcel, as_uuid(row.data['reference']), roles, lock=True)
                if body.action == 'MOVE_CUSTODY':
                    if parcel.status not in ('RECEIVED', 'READY_FOR_PICKUP'):
                        raise AppError('ERR-PARCEL-STATE', 'Bưu phẩm không còn được lưu giữ.', 409)
                    if not isinstance(body.data.get('location'), str) or not 2 <= len(body.data['location']) <= 120:
                        raise AppError('ERR-PARCEL-LOCATION', 'Vị trí lưu giữ cần 2–120 ký tự.', 422)
                    parcel.storage_location = body.data['location']; parcel.updated_by_id = context.account_id; parcel.version += 1
                elif body.action == 'RETURN':
                    if parcel.status not in ('RECEIVED', 'READY_FOR_PICKUP'):
                        raise AppError('ERR-PARCEL-STATE', 'Bưu phẩm không còn có thể trả lại.', 409)
                    parcel.status = 'RETURNED'; parcel.exception_reason = body.reason[:500]; parcel.updated_by_id = context.account_id; parcel.version += 1
                elif parcel.status != 'HANDED_OVER':
                    raise AppError('ERR-PARCEL-HANDOVER', 'Cần hoàn tất xác minh/PIN và bàn giao tại phân hệ Bưu phẩm trước.', 409)
            if body.action == 'MOVE_CUSTODY':
                allowed = {k: v for k, v in body.data.items() if k in model.model_fields}
                merged = {k: v for k, v in row.data.items() if k in model.model_fields}
                before = {k: row.data[k] for k in ('custodian_account_id', 'location', 'condition')}
                row.data = {**data_model(model, {**merged, **allowed}).model_dump(mode='json'), 'chain': row.data.get('chain', [])}
                validate_links(session, context, row); row.status = 'IN_PROGRESS'
                if not body.data.get('recipient_verification_reference'):
                    raise AppError('ERR-CUSTODY-EVIDENCE', 'Bàn giao cần xác minh người nhận.', 422)
                row.data = {**row.data, 'chain': [*row.data['chain'], {'from': before, 'to': {k: row.data[k] for k in before}, 'at': utc_now().isoformat(), 'actor_id': str(context.account_id), 'verification': body.data['recipient_verification_reference'], 'evidence_reference': row.data['evidence_reference']}]}
            else:
                if not body.data.get('recipient_verification_reference') or not body.data.get('recipient_name') or not body.data.get('condition'):
                    raise AppError('ERR-CUSTODY-EVIDENCE', 'Cần căn cứ xác minh người nhận hoặc chứng từ trả lại.', 422)
                row.data = {**row.data, 'handover': {**body.data, 'actor_id': str(context.account_id), 'at': utc_now().isoformat()}}
                row.status = 'COMPLETED'
        elif body.action == 'END_EFFECTIVITY':
            state(row, ('APPROVED',)); independent(context, row)
            if row.kind not in ('RULE', 'SOP', 'MASTER_DATA', 'ORGANIZATION', 'EMERGENCY_PLAN'):
                raise AppError('ERR-RECORD-KIND', 'Cần phiên bản cấu hình có hiệu lực.', 422)
            try: end = date.fromisoformat(body.data.get('valid_to', ''))
            except (ValueError, TypeError): raise AppError('ERR-RULE-EFFECTIVITY', 'Cần ngày kết thúc hợp lệ.', 422) from None
            if end <= date.fromisoformat(row.data['valid_from']) or end < utc_now().date() or row.data.get('valid_to'):
                raise AppError('ERR-RULE-EFFECTIVITY', 'Chỉ đóng hiệu lực đang mở từ hiện tại trở đi.', 409)
            row.data = {**row.data, 'valid_to': end.isoformat()}
        elif body.action == 'START':
            if row.kind in ('VISITOR', 'CONTRACTOR', 'VIOLATION', 'KEY_CUSTODY', 'PARCEL_CUSTODY', 'LOST_FOUND', 'TOOL_CUSTODY', 'RULE', 'SOP', 'MASTER_DATA', 'EMERGENCY_PLAN', 'STAFF', 'CONTRACT', 'DEPOSIT_POLICY', 'BUILDING_ZONE', 'BUILDING_PROFILE', 'SITE_PROFILE', 'ORGANIZATION', 'FEE_PUBLICATION', 'FEE_BENEFIT', 'UOM_CONVERSION', 'ASSET_WORK_LINK', 'WORK_ASSIGNMENT'):
                raise AppError('ERR-DOMAIN-WORKFLOW', 'Hồ sơ cần xử lý theo luồng nghiệp vụ riêng.', 409)
            state(row, ('APPROVED',)); row.status = 'IN_PROGRESS'
        elif body.action == 'CANCEL':
            state(row, ('DRAFT', 'SUBMITTED', 'REJECTED')); row.status = 'CANCELLED'
        else:
            raise AppError('ERR-STATE-TRANSITION', 'Thao tác hồ sơ không hợp lệ.', 409)
        row.version += 1; event(session, context, row, body.action, body.reason)
        return row, 'profile'
    return command(request, context, key, 'operations.' + body.action, {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=ALL_ROLES)
