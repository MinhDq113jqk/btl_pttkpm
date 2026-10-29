"""Extractive assistant: published sources and authorized requests only."""
import re
import unicodedata
from sqlalchemy import and_, select, or_
from app.core.exceptions import AppError
from app.core.policy import scope_not_found
from app.models.resident_portal import PortalContent, PortalRequestMessage
from app.models.service import ServiceRequest, ServiceCategory
from app.services.operational_control import MANAGEMENT
from app.services.resident_portal import unit_for, resident, staff_conditions, visible_conditions
from app.services.r2 import utc_now


def words(text):
    normalized = ''.join(c for c in unicodedata.normalize('NFD', text.lower().replace('đ', 'd')) if unicodedata.category(c) != 'Mn')
    return set(re.findall(r'[a-z0-9]{2,}', normalized))


def retrieve(session, context, query, unit_id=None, content_id=None):
    unit = unit_for(session, context, unit_id, 'documents', roles=(*MANAGEMENT, 'technical_lead', 'accountant', 'security', 'cleaning', 'technician')) if unit_id else None
    if resident(context) and unit is None:
        # Building-level publications only within the resident's current relationships.
        from app.models.unit import Unit
        building_ids = session.scalars(select(Unit.building_id).where(Unit.id.in_(context.resident_units_for('documents')))).all()
        scope = (or_(PortalContent.building_id.is_(None), PortalContent.building_id.in_(building_ids)), PortalContent.unit_id.is_(None))
    elif unit:
        scope = (or_(PortalContent.building_id.is_(None), PortalContent.building_id == unit.building_id), or_(PortalContent.unit_id.is_(None), PortalContent.unit_id == unit.id))
    else:
        scope = staff_conditions(context, PortalContent, (*MANAGEMENT, 'technical_lead', 'accountant', 'security', 'cleaning', 'technician'))
        if not any(r in context.roles for r in MANAGEMENT):
            scope = (*scope, PortalContent.unit_id.is_(None))
    now = utc_now()
    rows = session.scalars(select(PortalContent).where(*context.scope_conditions(PortalContent), *scope,
        PortalContent.status == 'PUBLISHED', PortalContent.publish_at <= now,
        or_(PortalContent.starts_at.is_(None), PortalContent.starts_at <= now),
        or_(PortalContent.ends_at.is_(None), PortalContent.ends_at > now),
        *((PortalContent.id == content_id,) if content_id else ()))).all()
    terms = words(query)
    ranked = sorted(((len(terms & words(r.title + ' ' + r.body)), r) for r in rows), key=lambda x: (-x[0], str(x[1].id)))
    return [{'source': 'portal_content', 'id': str(r.id), 'title': r.title, 'version': r.version,
             'excerpt': r.body[:1500], 'document_id': str(r.document_id) if r.document_id else None}
            for score, r in ranked if score or content_id][:5]


def request_query(context):
    if resident(context):
        from app.api.resident_service_requests import _assert_resident_scope, _resident_request_ownership
        _assert_resident_scope(context)
        visibility = and_(ServiceRequest.unit_id.in_(context.resident_units_for('requests')), _resident_request_ownership(context))
    else:
        from app.api.service_requests import _request_list_visibility, REQUEST_LIST_ROLES
        own = and_(ServiceRequest.created_by_id == context.account_id,
            *staff_conditions(context, ServiceRequest, (*MANAGEMENT, 'technical_lead', 'accountant', 'technician', 'cleaning', 'security')))
        visibility = or_(own, _request_list_visibility(context)) if set(context.roles).intersection(REQUEST_LIST_ROLES) else own
    return select(ServiceRequest).where(*context.scope_conditions(ServiceRequest), visibility)


def authorized_request(session, context, identifier):
    row = session.scalar(request_query(context).where(ServiceRequest.id == identifier))
    if row is None: raise scope_not_found()
    return row


def record_query(context, source):
    from app.api.sad_completion import source_catalog
    from app.models.billing import BillingInvoice, BillingAccount
    permissions={'portal_dossiers':'profile','resident_vehicles':'parking','resident_bookings':'booking',
        'resident_credentials':'parking','resident_service_enrollments':'finance','billing_invoices':'finance','operations_records':'profile'}
    if source not in permissions: raise scope_not_found()
    model, roles=source_catalog()[source]
    if not resident(context): return select(model).where(*context.scope_conditions(model),*staff_conditions(context,model,roles))
    if source=='billing_invoices':
        return select(BillingInvoice).join(BillingAccount,BillingInvoice.billing_account_id==BillingAccount.id).where(
            *context.scope_conditions(BillingInvoice),BillingAccount.unit_id.in_(context.resident_units_for('finance')),BillingInvoice.status!='DRAFT')
    if source=='operations_records':
        return select(model).where(*context.scope_conditions(model),model.unit_id.in_(context.resident_units_for('profile')),
            model.kind.in_(('VISITOR','CONTRACTOR','VIOLATION')),model.status.not_in(('DRAFT','SUBMITTED','REJECTED','CANCELLED')))
    return select(model).where(*visible_conditions(context,model,permissions[source]))


def check_record(context, source, row):
    if source=='operations_records':
        if resident(context):
            key='subject_account_id' if row.kind=='VIOLATION' else 'host_account_id'
            if row.data.get(key)!=str(context.account_id): raise scope_not_found()
        else:
            from app.services.operations_records import definition
            _,roles=definition(row.kind);context.assert_building_role(row.building_id,*roles)
    return row


def record_options(session, context, unit_id=None):
    sources={'portal_dossiers':'Hồ sơ','resident_vehicles':'Xe','resident_bookings':'Đặt tiện ích','resident_credentials':'Thẻ',
        'resident_service_enrollments':'Dịch vụ','billing_invoices':'Hóa đơn','operations_records':'Hồ sơ vận hành'}
    result=[]
    for source,label in sources.items():
        try: query=record_query(context,source)
        except AppError: continue
        from app.api.sad_completion import source_catalog
        model,_=source_catalog()[source]
        if unit_id:
            if hasattr(model,'unit_id'): query=query.where(model.unit_id==unit_id)
            elif source=='billing_invoices':
                from app.models.billing import BillingAccount
                query=query.where(BillingAccount.unit_id==unit_id)
        for row in session.scalars(query.order_by(model.created_at.desc()).limit(35)):
            try: check_record(context,source,row)
            except AppError: continue
            title=getattr(row,'title',None) or getattr(row,'plate',None) or getattr(row,'invoice_number',None) or getattr(row,'code',None) or str(row.id)
            result.append({'source':source,'id':str(row.id),'label':label+' · '+title})
    return result


def authorized_record(session, context, source, identifier):
    from app.api.sad_completion import source_catalog
    spec=source_catalog().get(source)
    if spec is None: raise scope_not_found()
    row=session.scalar(record_query(context,source).where(spec[0].id==identifier))
    if row is None: raise scope_not_found()
    check_record(context,source,row)
    return {'source':source,'id':str(row.id),'title':getattr(row,'title',None) or getattr(row,'plate',None) or getattr(row,'invoice_number',None) or getattr(row,'code',None) or str(row.id),
        'status':row.status,'version':row.version}


def answer(session, context, body):
    citations = []
    if body.mode=='STATUS' and body.record_id:
        record=authorized_record(session,context,body.record_source,body.record_id)
        return {'reply':record['title']+'\nTrạng thái: '+record['status'], 'citations':[record], 'needs_handoff':False,'mode':body.mode}
    if body.mode in ('STATUS', 'SUMMARY') or body.mode == 'DRAFT' and body.request_id:
        if not body.request_id:
            raise AppError('ERR-ASSISTANT-REFERENCE', 'Cần chọn yêu cầu để tra cứu hoặc tóm tắt.', 422)
        req = authorized_request(session, context, body.request_id)
        citations = [{'source': 'service_requests', 'id': str(req.id), 'title': req.code, 'version': req.version}]
        result = f'{req.code} · {req.title}\nTrạng thái: {req.status}\nMô tả: {req.description[:1500]}'
        if body.mode != 'STATUS':
            messages = session.scalars(select(PortalRequestMessage).where(PortalRequestMessage.service_request_id == req.id).order_by(PortalRequestMessage.created_at).limit(50)).all()
            result += '\nDiễn biến:\n' + '\n'.join(f'{m.created_at.isoformat()} · {m.message[:300]}' for m in messages)
            citations += [{'source': 'resident_request_messages', 'id': str(m.id), 'title': m.action, 'version': m.version} for m in messages]
    else:
        citations = retrieve(session, context, body.query, body.unit_id, body.content_id)
        result = '\n\n'.join(f'[{i+1}] {r["title"]} (phiên bản {r["version"]})\n{r["excerpt"]}' for i, r in enumerate(citations))
    if body.mode == 'DRAFT':
        context.assert_role(*MANAGEMENT)
        result = 'Bản nháp để người phụ trách xem xét:\nKính gửi anh/chị,\nBan quản lý xin phản hồi nội dung: ' + body.query + '\nThông tin đã đối chiếu theo hồ sơ hiện tại:\n' + (result or 'Chưa có đủ tài liệu làm căn cứ; CSKH cần xác minh và bổ sung trước khi phản hồi.') + '\nAnh/chị có thể bổ sung thông tin trong yêu cầu hoặc liên hệ CSKH để được hỗ trợ.\nTrân trọng, Ban quản lý GreenCity.'
    elif not result:
        result = 'Chưa tìm được tài liệu đã công bố phù hợp trong phạm vi của bạn. Bạn có thể chuyển nội dung này đến CSKH.'
    return {'reply': result, 'citations': citations, 'needs_handoff': not bool(citations), 'mode': body.mode}


def handoff(session, context, body, conversation):
    if conversation.request_id:
        return authorized_request(session, context, conversation.request_id)
    if not body.unit_id or not body.category_id:
        raise AppError('ERR-ASSISTANT-HANDOFF', 'Chọn căn và danh mục để chuyển đến CSKH.', 422)
    unit = unit_for(session, context, body.unit_id, 'requests', roles=(*MANAGEMENT,'technical_lead','accountant','technician','cleaning','security'))
    category = session.scalar(select(ServiceCategory).where(ServiceCategory.id == body.category_id,
        *context.scope_conditions(ServiceCategory), ServiceCategory.is_active.is_(True),
        or_(ServiceCategory.building_id.is_(None), ServiceCategory.building_id == unit.building_id)))
    if not category: raise scope_not_found()
    from app.services.sad_work import next_code
    from app.services.sad_completion import capture_sla
    summary = '\n'.join(f'{m["mode"]}: {m["query"]}\n{m["reply"][:800]}' for m in conversation.messages[-10:])
    row = ServiceRequest(tenant_id=context.tenant_id, site_id=context.assert_active_site(), building_id=unit.building_id,
        unit_id=unit.id, category_id=category.id, code=next_code(session, context.assert_active_site(), 'SR'),
        title=('Hỗ trợ: ' + body.query)[:200], description=(summary + '\nNội dung chuyển: ' + body.query)[:16000],
        owner_account_id=context.account_id, created_by_id=context.account_id, updated_by_id=context.account_id,
        status='NEW', priority='MEDIUM', sla_started_at=utc_now(), sla_duration_minutes=category.sla_minutes)
    session.add(row); session.flush(); capture_sla(session, row)
    conversation.request_id = row.id; conversation.unit_id = unit.id; conversation.building_id = unit.building_id
    conversation.status = 'HANDED_OFF'
    return row
