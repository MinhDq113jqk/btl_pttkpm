"""Exports freeze the same scoped rows used for aggregates and drilldown."""
import hashlib
import io
import json
import zipfile
from datetime import datetime, date
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import select, Date, Numeric, String
from decimal import Decimal
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.operational_control import ReportExport, TreasuryAccount, TreasuryMovement, Expense, StockItem, StockMovement, Meter, MeterReading, OperationsRecord
from app.models.resident_portal import VehicleRegistration, ResidentCredential, FacilityBooking, PortalDeposit
from app.schemas.resident_portal import PortalInput
from pydantic import Field, model_validator
from app.services.operational_control import load, building_scope, MANAGEMENT, FINANCIAL
from app.services.resident_portal import command, scope_values, staff_conditions, view
from app.services.r2 import utc_now
from app.services.private_storage import verified_private_path
from app.api.portal_documents import _document, _document_conditions
from app.models.resident_portal import ResidentDocument

router = APIRouter(prefix='/portal/control', tags=['Operational reports'])


class ExportInput(PortalInput):
    building_id: UUID
    kind: str = Field(min_length=2, max_length=40)
    period_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    statuses: dict[str, list[str]] = Field(default_factory=dict, max_length=20)

    @model_validator(mode='after')
    def interval(self):
        if self.date_from and self.date_to and self.date_from > self.date_to: raise ValueError('Khoảng ngày không hợp lệ.')
        if any(len(v)>30 or any(not 1<=len(s)<=30 for s in v) for v in self.statuses.values()): raise ValueError('Bộ lọc trạng thái không hợp lệ.')
        return self


class BundleInput(PortalInput):
    unit_id: UUID | None = None
    document_ids: list[UUID] = Field(min_length=1, max_length=20)


def report_models(kind):
    from app.models.sad_extensions import CommercialLedger
    from app.models.billing import BillingInvoice, Payment, PaymentAllocation, ArLedgerEntry
    from app.models.financial_control import ArCase, AllocationReversal, FinanceCommand
    from app.models.service import ServiceRequest, WorkOrder
    from app.models.operations import CleaningTask, SecurityIncident, PatrolLog
    from app.models.person import UnitPersonRelationship
    from app.models.unit import Unit
    mapping = {'RESIDENT': (Unit, UnitPersonRelationship, VehicleRegistration, ResidentCredential, FacilityBooking), 'SERVICE': (ServiceRequest, WorkOrder),
        'OPERATIONS': (CleaningTask, SecurityIncident, PatrolLog), 'FINANCIAL': (BillingInvoice, Payment, PaymentAllocation, AllocationReversal, ArLedgerEntry, ArCase, PortalDeposit, TreasuryAccount, TreasuryMovement, Expense, OperationsRecord, FinanceCommand),
        'STOCK': (StockItem, StockMovement), 'METER': (Meter, MeterReading), 'DOSSIERS': (OperationsRecord,)}
    mapping.update({'PROJECT':(OperationsRecord,), 'COMMERCIAL':(CommercialLedger, OperationsRecord), 'ENERGY':(OperationsRecord,), 'INSURANCE':(OperationsRecord,)})
    if kind not in mapping:
        raise AppError('ERR-REPORT-KIND', 'Loại báo cáo không được hỗ trợ.', 422)
    return mapping[kind]


def assert_report_scope(context, row):
    context.assert_building_role(row.building_id, *report_roles(row.kind))
    if row.kind == 'DOSSIERS':
        from app.services.operations_records import definition
        for kind in {r['data']['kind'] for r in row.rows}:
            _, roles = definition(kind); context.assert_building_role(row.building_id, *roles)


REPORT_ROLES = (*MANAGEMENT, 'accountant', 'technical_lead', 'security', 'cleaning')


def report_roles(kind):
    if kind == 'PROJECT':
        from app.services.sad_extensions import ROLES
        return ROLES
    if kind in ('FINANCIAL', 'COMMERCIAL'):
        return FINANCIAL
    if kind in ('STOCK', 'METER', 'ENERGY'):
        return ('admin', 'director', 'technical_lead')
    if kind == 'SERVICE':
        return (*MANAGEMENT, 'technical_lead')
    if kind == 'DOSSIERS':
        return REPORT_ROLES
    return MANAGEMENT


@router.get('/reports')
def reports(request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        rows = session.scalars(select(ReportExport).where(*context.scope_conditions(ReportExport), *staff_conditions(context, ReportExport, REPORT_ROLES)).order_by(ReportExport.created_at.desc()).limit(200)).all()
        items = []
        for row in rows:
            try:
                assert_report_scope(context, row)
            except AppError:
                continue
            items.append({**view(row), 'rows': [], 'row_count': len(row.rows)})
        return {'items': items}


@router.post('/reports', status_code=201)
def export_report(body: ExportInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        roles = report_roles(body.kind)
        building_scope(session, context, body.building_id, roles)
        from sqlalchemy import text
        # Lock a coherent snapshot across all report queries (PostgreSQL repeatable read).
        # command has already acquired an advisory lock, so use one SQL statement below.
        models = report_models(body.kind)
        names={m.__tablename__ for m in models}
        if set(body.statuses)-names: raise AppError('ERR-REPORT-FILTER','Bộ lọc có nguồn không thuộc báo cáo.',422)
        date_from,date_to=body.date_from,body.date_to
        if body.period_id:
            from app.models.billing import AccountingPeriod
            period=load(session,context,AccountingPeriod,body.period_id,roles)
            if period.building_id!=body.building_id: raise scope_not_found()
            date_from=max(date_from,period.period_start) if date_from else period.period_start
            date_to=min(date_to,period.period_end) if date_to else period.period_end
            if date_from>date_to:raise AppError('ERR-REPORT-FILTER','Khoảng ngày nằm ngoài kỳ.',422)
        from sqlalchemy import literal, union_all
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy import cast, func
        extra = []
        if body.kind == 'DOSSIERS':
            from app.services.operations_records import RECORDS
            allowed = []
            for kind, (_, record_roles) in RECORDS.items():
                try:
                    context.assert_building_role(body.building_id, *record_roles); allowed.append(kind)
                except AppError:
                    pass
            extra = [OperationsRecord.kind.in_(allowed)]
        from app.models.unit import Unit
        from app.models.billing import BillingInvoice, Payment, PaymentAllocation
        from app.models.financial_control import AllocationReversal
        def conditions(m):
            if m is AllocationReversal:
                return [m.allocation_id.in_(select(PaymentAllocation.id).where(*conditions(PaymentAllocation)))]
            result=[*(() if m is Unit else context.scope_conditions(m)),m.building_id==body.building_id,*extra]
            if m is OperationsRecord and body.kind=='FINANCIAL':result.append(m.kind=='ADVANCE_SETTLEMENT')
            if m is OperationsRecord and body.kind in ('PROJECT','COMMERCIAL','ENERGY','INSURANCE'):
                from app.services.sad_extensions import RECORDS
                kinds = [k for k in RECORDS if k.startswith({'PROJECT':'PROJECT','COMMERCIAL':'COMMERCIAL','ENERGY':'ENERGY','INSURANCE':'INSURANCE'}[body.kind])]
                if body.kind == 'COMMERCIAL': kinds.append('LEASE_AMENDMENT')
                result.append(m.kind.in_(kinds))
            from app.models.financial_control import FinanceCommand
            if m is FinanceCommand:
                result.append(m.kind.in_(('PAYMENT_REFUND','PAYMENT_REVERSE')))
                result.append(m.target_id.in_(select(Payment.id).where(*conditions(Payment))))
            if body.period_id and hasattr(m,'accounting_period_id'):result.append(m.accounting_period_id==body.period_id)
            if m is PaymentAllocation:
                result.append(m.payment_id.in_(select(Payment.id).where(*conditions(Payment))))
                result.append(m.billing_invoice_id.in_(select(BillingInvoice.id).where(*conditions(BillingInvoice))))
            if hasattr(m,'status') and body.statuses.get(m.__tablename__):result.append(m.status.in_(body.statuses[m.__tablename__]))
            elif body.statuses.get(m.__tablename__):raise AppError('ERR-REPORT-FILTER','Nguồn không có trạng thái để lọc.',422)
            # Stock balances are captured at this moment; flow rows use their business date.
            if m not in (TreasuryAccount,StockItem,Meter,Unit):
                from app.models.billing import ArLedgerEntry
                date_column=cast(m.issued_on if m is BillingInvoice else m.received_at if m is Payment else m.effective_at if m is ArLedgerEntry else m.read_on if hasattr(m,'read_on') else m.created_at, Date)
                if date_from:result.append(date_column>=date_from)
                if date_to:result.append(date_column<=date_to)
            return result
        def snapshot_data(m):
            from sqlalchemy.dialects.postgresql import array
            data=cast(func.row_to_json(m.__table__.table_valued()),JSONB)
            for column in m.__table__.columns:
                if isinstance(column.type,Numeric):data=func.jsonb_set(data,array([column.name]),func.coalesce(func.to_jsonb(cast(column,String)),cast(literal('null'),JSONB)))
            return data
        statements = [select(literal(m.__tablename__).label('source'), snapshot_data(m).label('data')).where(*conditions(m)) for m in models]
        captured_at=utc_now()
        rows = session.execute(union_all(*statements).limit(5001)).all()
        if len(rows) > 5000:
            raise AppError('ERR-REPORT-SIZE', 'Báo cáo vượt 5000 dòng; cần thu hẹp phạm vi.', 422)
        safe = []
        for source, data in rows:
            data = {k: v for k, v in data.items() if k not in ('pin_hash', 'storage_key', 'token_hash', 'verification_reference', 'hashed_password')}
            safe.append({'source': source, 'data': data})
        safe.sort(key=lambda r: (r['source'], r['data']['id']))
        from app.services.report_metrics import metrics, DEFINITION, number_safe_json
        from app.services.sad_completion import fingerprint
        filters=body.model_dump(mode='json',exclude={'building_id','kind'})
        filters.update({'effective_date_from':str(date_from) if date_from else None,'effective_date_to':str(date_to) if date_to else None,'balance_window':'AT_CAPTURE',
            'at_capture_sources':['treasury_accounts','operational_stock_items','operational_meters','units']})
        kpis=metrics(body.kind,safe,as_of=captured_at)
        safe,kpis=number_safe_json(safe),number_safe_json(kpis)
        digest=fingerprint({'rows':safe,'filters':filters,'metrics':kpis,'definition':DEFINITION})
        row = ReportExport(**scope_values(context, building_id=body.building_id), kind=body.kind, as_of=captured_at, rows=safe, digest=digest,filters=filters,metrics=kpis,definition_version=DEFINITION)
        session.add(row); return row, 'profile'
    return command(request, context, key, 'report.export', body.model_dump(mode='json'), execute, roles=REPORT_ROLES)


@router.get('/reports/{identifier}')
def report(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row = load(session, context, ReportExport, identifier, REPORT_ROLES)
        assert_report_scope(context, row)
        counts = {}
        for r in row.rows:
            counts[r['source']] = counts.get(r['source'], 0) + 1
        return {**view(row), 'counts': counts}


@router.get('/reports/{identifier}/download')
def report_download(identifier: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    data = report(identifier, request, context)
    return Response(json.dumps(jsonable_encoder(data), ensure_ascii=False), media_type='application/json', headers={'Content-Disposition': f'attachment; filename="greencity-{identifier}.json"', 'Cache-Control': 'private, no-store'})


@router.get('/reports/{identifier}/sources/{source}/{source_id}')
def report_source(identifier:UUID,source:str,source_id:UUID,request:Request,context:UserContext=Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        report=load(session,context,ReportExport,identifier,REPORT_ROLES);assert_report_scope(context,report)
        captured=next((r['data'] for r in report.rows if r['source']==source and r['data']['id']==str(source_id)),None)
        if captured is None:raise scope_not_found()
        from app.api.sad_completion import source_view
        live=source_view(session,context,source,source_id,expected_building=report.building_id)
        live['current']=jsonable_encoder(live['current'],custom_encoder={Decimal:str})
        from app.services.sad_completion import fingerprint
        return {**live,'snapshot':captured,'snapshot_as_of':report.as_of,'definition_version':report.definition_version,
            'current_differs':fingerprint(captured)!=fingerprint(live['current']),
            'notice':'Hồ sơ hiện tại được đọc tại mốc mới; tổng báo cáo vẫn dùng snapshot đã xuất.'}


@router.post('/documents/bundle')
def document_bundle(body: BundleInput, request: Request, context: UserContext = Depends(get_current_user_context)):
    buffer = io.BytesIO()
    with request.app.state.database.get_session() as session, zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        manifest = []; total = 0
        for identifier in dict.fromkeys(body.document_ids):
            row = _document(session, context, identifier, unit_id=body.unit_id)
            if row.quarantined or row.archived_at:
                raise scope_not_found()
            total += row.size_bytes
            if total > 20 * 1024 * 1024:
                raise AppError('ERR-BUNDLE-SIZE', 'Bộ hồ sơ vượt 20 MB.', 413)
            path = verified_private_path(request.app.state.settings.private_storage_path, row.storage_key, row.sha256, row.size_bytes)
            if path is None:
                raise AppError('ERR-FILE-INTEGRITY', 'Tài liệu không còn khả dụng.', 409)
            name = f'{row.id}-{row.original_name}'
            archive.write(path, name)
            manifest.append({'id': str(row.id), 'title': row.title, 'version': row.content_version, 'sha256': row.sha256, 'filename': name})
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
        from app.services.r2 import audit
        audit(session, context, request, event_type='DocumentBundleExported', action='export', resource_type='ResidentDocument', resource_id=body.document_ids[0], building_id=row.building_id, after={'count': len(manifest)})
        session.commit()
    return Response(buffer.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="greencity-documents.zip"', 'Cache-Control': 'private, no-store'})
