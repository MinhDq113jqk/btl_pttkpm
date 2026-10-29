"""Calculate, check, then issue against the same locked source snapshot."""
from datetime import timedelta
import hashlib,json
from uuid import UUID
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from app.core.exceptions import AppError
from app.models.billing import AccountingPeriod,BillingAccount,BillingInvoice,BillingInvoiceItem,BillingRun,FeePolicy,FeePolicyVersion
from app.models.financial_control import BillingReview, FinanceCommand, FinanceEvent, FinancePolicy, ApprovalDelegation, AllocationReversal, CreditUseAllocation
from app.models.person import UnitPersonRelationship
from app.models.property import UnitProfileEpisode
from app.models.resident_portal import LiabilityEpisode,PortalFeeSource
from app.models.service import PendingCharge,CostLine,WorkOrder,ServiceRequest
from app.models.unit import Unit
from app.services.portal_finance import fee_calculation,post_fee_source
from app.services.r2 import utc_now


def digest(value):
    return hashlib.sha256(json.dumps(jsonable_encoder(value),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def responsibility(session,unit_id,start,end):
    episodes=session.scalars(select(LiabilityEpisode).where(LiabilityEpisode.unit_id==unit_id,
        LiabilityEpisode.valid_from<=end,(LiabilityEpisode.valid_to.is_(None)|(LiabilityEpisode.valid_to>start))).order_by(LiabilityEpisode.valid_from)).all()
    if episodes:
        cursor=start;rows=[]
        for e in episodes:
            a=max(start,e.valid_from);b=min(end+timedelta(days=1),e.valid_to or end+timedelta(days=1))
            if a!=cursor or b<=a:raise AppError('ERR-LIABILITY-COVERAGE','Người chịu phí bị thiếu/chồng một phần kỳ; cần xác minh hồ sơ.',409)
            rows.append({'episode_id':str(e.id),'person_id':str(e.person_id),'valid_from':str(a),'valid_to':str(b),'version':e.version})
            cursor=b
        if cursor!=end+timedelta(days=1):raise AppError('ERR-LIABILITY-COVERAGE','Người chịu phí chưa phủ hết kỳ.',409)
        return {'basis':'LIABILITY_EPISODES','episodes':rows}
    owners=session.scalars(select(UnitPersonRelationship).where(UnitPersonRelationship.unit_id==unit_id,
        UnitPersonRelationship.relationship_type=='owner',UnitPersonRelationship.valid_from<=start,
        (UnitPersonRelationship.valid_to.is_(None)|(UnitPersonRelationship.valid_to>end)))).all()
    if len(owners)!=1 or owners[0].ownership_ratio!=1:
        raise AppError('ERR-LIABILITY-MISSING','Chưa xác định được đại diện chịu phí; cần hồ sơ LiabilityEpisode.',409)
    return {'basis':'SOLE_OWNER_DEFAULT','episodes':[{'person_id':str(owners[0].person_id),'relationship_id':str(owners[0].id),
        'valid_from':str(start),'valid_to':str(end+timedelta(days=1))}]}


def run_snapshot(session,run,period,version,actor):
    from app.services.billing import _calculate_run
    session.scalar(select(FeePolicy).where(FeePolicy.id==version.fee_policy_id).with_for_update())
    # Locks must survive the preview savepoint rollback through the final issue.
    account_units=select(BillingAccount.unit_id).where(BillingAccount.building_id==run.building_id)
    session.scalars(select(Unit).where(Unit.id.in_(account_units)).order_by(Unit.id).with_for_update()).all()
    session.scalars(select(BillingAccount).where(BillingAccount.building_id==run.building_id).order_by(BillingAccount.id).with_for_update()).all()
    session.execute(select(PendingCharge,CostLine,WorkOrder,ServiceRequest).join(CostLine,CostLine.id==PendingCharge.cost_line_id)
        .join(WorkOrder,WorkOrder.id==CostLine.work_order_id).join(ServiceRequest,ServiceRequest.id==WorkOrder.service_request_id)
        .where(WorkOrder.building_id==run.building_id,PendingCharge.status=='APPROVED').order_by(PendingCharge.id).with_for_update()).all()
    nested=session.begin_nested()
    try:
        _calculate_run(session,run,period,version,actor)
        session.flush()
        invoices=session.scalars(select(BillingInvoice).where(BillingInvoice.billing_run_id==run.id).order_by(BillingInvoice.billing_account_id)).all()
        rows=[]
        for invoice in invoices:
            account=session.get(BillingAccount,invoice.billing_account_id);unit=session.get(Unit,account.unit_id)
            items=session.scalars(select(BillingInvoiceItem).where(BillingInvoiceItem.billing_invoice_id==invoice.id).order_by(BillingInvoiceItem.line_number)).all()
            rows.append({'billing_account_id':str(account.id),'account_version':account.version,'unit_id':str(unit.id),'unit_version':unit.version,
                'total_vnd':invoice.total_vnd,'responsibility':responsibility(session,unit.id,max(period.period_start,account.opened_on),
                    min(period.period_end,(account.closed_on-timedelta(days=1)) if account.closed_on else period.period_end)),
                'items':[{k:jsonable_encoder(getattr(i,k)) for k in ['fee_policy_version_id','description','basis','basis_quantity',
                    'unit_rate_vnd_snapshot','rounding_unit_vnd_snapshot','amount_vnd','source_pending_charge_id','calculation_snapshot']} for i in items]})
        versions=session.scalars(select(FeePolicyVersion).where(FeePolicyVersion.fee_policy_id==version.fee_policy_id).order_by(FeePolicyVersion.version_number)).all()
        charges=session.execute(select(PendingCharge,CostLine).join(CostLine,CostLine.id==PendingCharge.cost_line_id)
            .where(PendingCharge.id.in_([UUID(i['source_pending_charge_id']) for r in rows for i in r['items'] if i['source_pending_charge_id']]))).all()
        profiles=session.scalars(select(UnitProfileEpisode).where(UnitProfileEpisode.unit_id.in_([UUID(r['unit_id']) for r in rows]),
            UnitProfileEpisode.valid_from<=period.period_end,(UnitProfileEpisode.valid_to.is_(None)|(UnitProfileEpisode.valid_to>period.period_start))).order_by(UnitProfileEpisode.id)).all()
        return {'period_id':str(period.id),'period_version':period.version,'cutoff_at':jsonable_encoder(run.cutoff_at),'invoices':rows,
            'unit_profiles':[jsonable_encoder({k:getattr(p,k) for k in ('id','version','valid_from','valid_to','area_m2','net_area_m2','gross_area_m2','reason')}) for p in profiles],
            'policy_versions':[jsonable_encoder({k:getattr(v,k) for k in ('id','version','basis','area_field','unit_rate_vnd','rounding_unit_vnd','effective_from','effective_to')}) for v in versions],
            'charges':[{'id':str(c.id),'version':c.version-1,'cost_line_id':str(l.id),'cost_line_version':l.version,'amount_vnd':l.amount_vnd} for c,l in sorted(charges,key=lambda pair:str(pair[0].id))]}
    finally:
        nested.rollback()


def source_snapshot(session,source,period):
    calculation=fee_calculation(session,source,period)
    return {'period_id':str(period.id),'period_version':period.version,'source_id':str(source.id),'source_version':source.version,
        'calculation':calculation,'responsibility':responsibility(session,source.unit_id,period.period_start,period.period_end)}


def prepare_run_review(session,run,period,version,actor):
    snapshot=run_snapshot(session,run,period,version,actor)
    row=BillingReview(tenant_id=run.tenant_id,site_id=run.site_id,building_id=run.building_id,unit_id=None,
        account_id=actor,billing_run_id=run.id,period_id=period.id,snapshot=snapshot,calculation_hash=digest(snapshot))
    session.add(row);run.status='REVIEW';return row


def prepare_source_review(session,source,period,actor,expected_hash=None):
    from app.services.portal_finance import calculation_hash
    from app.models.resident_portal import PortalFeePosting
    if not source.recurring and session.scalar(select(PortalFeePosting.id).where(PortalFeePosting.fee_source_id==source.id,PortalFeePosting.period_id!=period.id).limit(1)):
        raise AppError('ERR-FEE-ALREADY-POSTED','Khoản phí một lần đã được phát hành.',409)
    existing=session.scalar(select(BillingReview).where(BillingReview.fee_source_id==source.id,BillingReview.period_id==period.id).with_for_update())
    if existing:return existing
    snapshot=source_snapshot(session,source,period)
    if expected_hash and expected_hash!=calculation_hash(source,period,snapshot['calculation']):
        raise AppError('ERR-FEE-PREVIEW-STALE','Căn cứ tính đã đổi; cần xem trước lại.',409)
    if snapshot['calculation']['amount_vnd']<=0:raise AppError('ERR-FEE-NO-ACCRUAL','Không phát sinh phí phải thu trong kỳ.',409)
    row=BillingReview(tenant_id=source.tenant_id,site_id=source.site_id,building_id=source.building_id,unit_id=source.unit_id,
        account_id=actor,fee_source_id=source.id,period_id=period.id,snapshot=snapshot,calculation_hash=digest(snapshot))
    session.add(row);return row


def recalculate_review(session,row,period,actor):
    if period.status not in {'OPEN','CLOSING'}:raise AppError('ERR-ACCOUNTING-PERIOD-CLOSED','Kỳ không nhận tính/phát hành mới.',409)
    if row.billing_run_id:
        run=session.get(BillingRun,row.billing_run_id)
        version=session.get(FeePolicyVersion,run.fee_policy_version_id)
        return run_snapshot(session,run,period,version,actor)
    initial=session.get(PortalFeeSource,row.fee_source_id)
    session.scalar(select(Unit).where(Unit.id==initial.unit_id).with_for_update())
    source=session.scalar(select(PortalFeeSource).where(PortalFeeSource.id==row.fee_source_id).with_for_update().execution_options(populate_existing=True))
    return source_snapshot(session,source,period)


def issue_review(session,row,period,actor):
    if row.billing_run_id:
        from app.services.billing import execute_run
        run=session.get(BillingRun,row.billing_run_id);version=session.get(FeePolicyVersion,run.fee_policy_version_id)
        snapshots={r['billing_account_id']:r['responsibility'] for r in row.snapshot['invoices']}
        result=execute_run(session,run,period,version,actor,responsibility_resolver=lambda account:snapshots[str(account.id)])
        if result.status!='POSTED':raise AppError(result.failure_code or 'ERR-BILLING-ISSUE',result.failure_detail or 'Không phát hành được.',409)
        invoices=session.scalars(select(BillingInvoice).where(BillingInvoice.billing_run_id==run.id)).all()
    else:
        source=session.get(PortalFeeSource,row.fee_source_id)
        invoice=post_fee_source(session,source,period,actor,responsibility_snapshot=row.snapshot['responsibility'])
        source.version+=1;invoices=[invoice]
    row.issued_invoice_ids=[str(i.id) for i in invoices];row.status='ISSUED'
    return invoices


def event(session,row,actor,action,reason):
    session.add(FinanceEvent(resource_type=row.__class__.__name__,resource_id=row.id,actor_id=actor,
        action=action,reason=reason,snapshot=jsonable_encoder({'status':getattr(row,'status',None),'version':row.version,
            'hash':getattr(row,'calculation_hash',None),'snapshot':getattr(row,'snapshot',{})})))


def check_approver(session,context,row,purpose,amount=0):
    from app.services.resident_portal import FINANCE, staff_conditions
    if row.account_id == context.account_id:
        raise AppError('ERR-MAKER-CHECKER','Người lập không được tự duyệt.',403)
    context.assert_building_role(row.building_id,*FINANCE)
    policy=session.scalar(select(FinancePolicy).where(FinancePolicy.tenant_id==row.tenant_id,
        FinancePolicy.site_id==row.site_id,FinancePolicy.code==purpose,FinancePolicy.status=='ACTIVE').with_for_update())
    if policy is None: return
    data=policy.data
    if amount > data['max_amount_vnd']:
        raise AppError('ERR-APPROVAL-LIMIT','Số tiền vượt hạn mức quy trình đã cấu hình.',409)
    if any(g.role in data['approval_roles'] and g.building_id in (None,row.building_id) for g in context.role_grants):return
    delegate=session.scalar(select(ApprovalDelegation.id).where(ApprovalDelegation.tenant_id==row.tenant_id,
        ApprovalDelegation.site_id==row.site_id,ApprovalDelegation.building_id==row.building_id,
        ApprovalDelegation.delegate_account_id==context.account_id,ApprovalDelegation.purpose==purpose,
        ApprovalDelegation.revoked.is_(False),ApprovalDelegation.valid_from<=utc_now(),ApprovalDelegation.valid_to>utc_now()).limit(1))
    if delegate is None:raise AppError('ERR-APPROVAL-POLICY','Người duyệt không thuộc chính sách/ủy nhiệm có hiệu lực.',403)


def financial_record(session,context,model,identifier,building=None,lock=True):
    from app.services.resident_portal import FINANCE, staff_conditions
    from app.core.policy import scope_not_found
    stmt=select(model).where(model.id==identifier,*context.scope_conditions(model),*staff_conditions(context,model,FINANCE))
    if building:stmt=stmt.where(model.building_id==building)
    if lock:stmt=stmt.with_for_update().execution_options(populate_existing=True)
    row=session.scalar(stmt)
    if row is None:raise scope_not_found()
    return row


def posting_permission(session,row,period):
    if period.status == 'OPEN':return
    grants=session.scalars(select(FinanceCommand).where(FinanceCommand.period_id==period.id,
        FinanceCommand.kind=='PERIOD_REOPEN',FinanceCommand.status=='EXECUTED')).all()
    from datetime import datetime
    for grant in grants:
        if (grant.data['expires_at'] and datetime.fromisoformat(grant.data['expires_at'])>utc_now()
            and row.kind in grant.data['allowed_kinds'] and str(row.target_id) in grant.data['target_ids']):return
    raise AppError('ERR-ACCOUNTING-PERIOD-CLOSED','Kỳ không OPEN hoặc lệnh nằm ngoài phạm vi/thời hạn mở kỳ đã duyệt.',409)


def command_snapshot(session,context,row,period):
    from app.models.billing import Payment, PaymentAllocation, OverpaymentCredit, ArLedgerEntry
    from app.models.resident_portal import PortalDeposit, PortalFinancialAdjustment
    from app.services.resident_portal import FINANCE, scoped, unit_for
    kind=row.kind
    if kind in {'PERIOD_LOCK','PERIOD_REOPEN'}:
        if row.target_id != period.id:raise AppError('ERR-FINANCE-TARGET','Kỳ đích không khớp.',422)
        if kind=='PERIOD_LOCK' and period.status!='CLOSED':raise AppError('ERR-STATE-TRANSITION','Chỉ khóa kỳ CLOSED.',409)
        if kind=='PERIOD_REOPEN':
            from datetime import datetime
            if period.status not in {'CLOSED','LOCKED'} or datetime.fromisoformat(row.data['expires_at'])<=utc_now():
                raise AppError('ERR-REOPEN-SCOPE','Kỳ/thời hạn mở kỳ không hợp lệ.',409)
            if not row.data['allowed_kinds'] or not row.data['target_ids']:
                raise AppError('ERR-REOPEN-SCOPE','Cần phạm vi chứng từ/nghiệp vụ cụ thể.',422)
        return {'period_version':period.version,'status':period.status}
    posting_permission(session,row,period)
    if kind=='ACCOUNT_OPEN':
        unit=unit_for(session,context,row.target_id,'finance',roles=FINANCE)
        if unit.building_id!=period.building_id:raise AppError('ERR-FINANCE-TARGET','Căn và kỳ khác tòa.',404)
        existing=session.scalar(select(BillingAccount.id).where(BillingAccount.unit_id==unit.id))
        if existing:raise AppError('ERR-BILLING-ACCOUNT-EXISTS','Căn đã có tài khoản thu phí; dùng hồ sơ thay đổi.',409)
        from datetime import date
        from app.services.portal_finance import business_date
        if date.fromisoformat(row.data['effective_on'])>business_date():
            raise AppError('ERR-ACCOUNT-DATE','Chưa hỗ trợ mở tài khoản trước ngày hiệu lực.',409)
        return {'unit_id':str(unit.id),'unit_version':unit.version,'period_version':period.version}
    if kind.startswith('ACCOUNT_'):
        account=financial_record(session,context,BillingAccount,row.target_id,period.building_id)
        target={'ACCOUNT_SUSPEND':'ACTIVE','ACCOUNT_RESUME':'SUSPENDED','ACCOUNT_CLOSE':'ACTIVE'}[kind]
        if account.status!=target:raise AppError('ERR-STATE-TRANSITION','Trạng thái tài khoản không hợp lệ.',409)
        from datetime import date
        effective=date.fromisoformat(row.data['effective_on'])
        if effective<account.opened_on or effective>__import__('app.services.portal_finance',fromlist=['business_date']).business_date():
            raise AppError('ERR-ACCOUNT-DATE','Ngày hiệu lực không hợp lệ.',409)
        posted=session.scalar(select(BillingInvoice.id).join(AccountingPeriod,AccountingPeriod.id==BillingInvoice.accounting_period_id)
            .where(BillingInvoice.billing_account_id==account.id,BillingInvoice.status.not_in(('DRAFT','VOID')),AccountingPeriod.period_end>=effective).limit(1))
        if posted:raise AppError('ERR-ACCOUNT-POSTED','Ngày thay đổi ảnh hưởng kỳ đã phát hành; cần xử lý điều chỉnh riêng.',409)
        result={'account_id':str(account.id),'unit_id':str(account.unit_id),'version':account.version,'status':account.status,'period_version':period.version}
        if kind=='ACCOUNT_CLOSE':
            debt=session.scalar(select(func.coalesce(func.sum(BillingInvoice.outstanding_vnd),0)).where(
                BillingInvoice.billing_account_id==account.id,BillingInvoice.status.not_in(('DRAFT','VOID')))) or 0
            balance=session.scalar(select(func.coalesce(func.sum(ArLedgerEntry.debit_vnd-ArLedgerEntry.credit_vnd),0)).where(ArLedgerEntry.billing_account_id==account.id)) or 0
            credits=session.scalar(select(func.coalesce(func.sum(OverpaymentCredit.remaining_vnd),0)).where(OverpaymentCredit.billing_account_id==account.id)) or 0
            if debt or balance or credits:raise AppError('ERR-ACCOUNT-BALANCE','Cần đối chiếu và xử lý nợ/số dư có trước khi đóng tài khoản.',409)
            result.update({'outstanding_vnd':int(debt),'ledger_balance_vnd':int(balance),'overpayment_vnd':int(credits)})
        return result
    if kind.startswith('DEPOSIT_'):
        deposit=scoped(session,context,PortalDeposit,row.target_id,'finance',roles=FINANCE)
        unit_for(session,context,deposit.unit_id,'finance',roles=FINANCE)
        deposit=scoped(session,context,PortalDeposit,row.target_id,'finance',roles=FINANCE,lock=True)
        if deposit.building_id!=period.building_id:raise AppError('ERR-FINANCE-TARGET','Cọc và kỳ khác tòa.',404)
        available=deposit.refundable_vnd if kind=='DEPOSIT_REFUND' else deposit.balance_vnd-deposit.refundable_vnd
        if row.amount_vnd>available:raise AppError('ERR-DEPOSIT-BALANCE','Cọc khả dụng không đủ.',409)
        return {'unit_id':str(deposit.unit_id),'version':deposit.version,'balance_vnd':deposit.balance_vnd,'refundable_vnd':deposit.refundable_vnd,'period_version':period.version}
    model=BillingInvoice if kind in {'CREDIT','WRITE_OFF','INVOICE_VOID'} else OverpaymentCredit if kind=='CREDIT_USE' else Payment
    initial=financial_record(session,context,model,row.target_id,period.building_id,lock=False)
    account=financial_record(session,context,BillingAccount,initial.billing_account_id,period.building_id)
    target=financial_record(session,context,model,row.target_id,period.building_id)
    result={'account_id':str(account.id),'unit_id':str(account.unit_id),'version':target.version,'period_version':period.version}
    if kind=='INVOICE_VOID':
        allocated=session.scalar(select(PaymentAllocation.id).where(PaymentAllocation.billing_invoice_id==target.id).limit(1))
        used=session.scalar(select(CreditUseAllocation.id).where(CreditUseAllocation.invoice_id==target.id).limit(1))
        if target.status!='ISSUED' or target.outstanding_vnd!=target.total_vnd or allocated or used:
            raise AppError('ERR-INVOICE-VOID-RESTRICTED','Chỉ hủy hóa đơn chưa thanh toán/phân bổ hoặc điều chỉnh.',409)
        if target.accounting_period_id!=period.id:raise AppError('ERR-FINANCE-TARGET','Hủy hóa đơn cần kỳ gốc.',409)
        return {**result,'total_vnd':target.total_vnd,'outstanding_vnd':target.outstanding_vnd}
    if kind in {'CREDIT','WRITE_OFF'}:
        credited=(session.scalar(select(func.coalesce(func.sum(FinanceCommand.amount_vnd),0)).where(FinanceCommand.target_id==target.id,
            FinanceCommand.kind.in_(('CREDIT','WRITE_OFF')),FinanceCommand.status=='EXECUTED')) or 0)+(session.scalar(select(func.coalesce(func.sum(PortalFinancialAdjustment.amount_vnd),0)).where(
                PortalFinancialAdjustment.invoice_id==target.id,PortalFinancialAdjustment.kind=='CREDIT',PortalFinancialAdjustment.status=='COMPLETED')) or 0)
        if target.status in {'DRAFT','VOID'} or row.amount_vnd > (target.outstanding_vnd if kind=='WRITE_OFF' else target.total_vnd-credited):
            raise AppError('ERR-ADJUSTMENT-AMOUNT','Điều chỉnh vượt phần hóa đơn có thể điều chỉnh.',409)
        return {**result,'outstanding_vnd':target.outstanding_vnd,'credited_vnd':credited}
    payment=financial_record(session,context,Payment,target.payment_id if kind=='CREDIT_USE' else target.id,period.building_id)
    if payment.status in {'REVERSED','UNMATCHED'}:raise AppError('ERR-PAYMENT-STATE','Thu tiền nguồn không đủ điều kiện.',409)
    guard_payment_decisions(session,payment.id,command_id=row.id,operation=kind)
    allocations=session.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id==payment.id).order_by(PaymentAllocation.billing_invoice_id)).all()
    credit=session.scalar(select(OverpaymentCredit).where(OverpaymentCredit.payment_id==payment.id).with_for_update())
    result.update({'payment_version':payment.version,'payment_amount_vnd':payment.amount_vnd,'allocations':[{'id':str(a.id),'invoice_id':str(a.billing_invoice_id),'amount_vnd':a.amount_vnd} for a in allocations],
        'credit_version':credit.version if credit else None,'credit_remaining_vnd':credit.remaining_vnd if credit else 0})
    if kind in {'ALLOCATE','CREDIT_USE'}:
        total=sum(a['amount_vnd'] for a in row.data['allocations'])
        available=credit.remaining_vnd if kind=='CREDIT_USE' else (0 if credit else payment.amount_vnd-sum(a.amount_vnd for a in allocations))
        if total>available:raise AppError('ERR-ALLOCATION-AMOUNT','Phân bổ vượt số tiền khả dụng; tiền thừa dùng lệnh CREDIT_USE.',409)
        result['invoices']=[]
        for line in sorted(row.data['allocations'],key=lambda item:item['invoice_id']):
            invoice=financial_record(session,context,BillingInvoice,UUID(line['invoice_id']),period.building_id)
            if invoice.billing_account_id!=account.id or invoice.status not in {'ISSUED','PARTIALLY_PAID'} or line['amount_vnd']>invoice.outstanding_vnd:
                raise AppError('ERR-ALLOCATION-AMOUNT','Hóa đơn khác tài khoản hoặc vượt số nợ còn lại.',409)
            if kind=='ALLOCATE' and any(a.billing_invoice_id==invoice.id for a in allocations):raise AppError('ERR-ALLOCATION-EXISTS','Thu tiền đã được phân bổ vào hóa đơn này; dùng hồ sơ số dư có.',409)
            result['invoices'].append({'id':str(invoice.id),'version':invoice.version,'outstanding_vnd':invoice.outstanding_vnd})
    elif kind=='PAYMENT_REFUND':
        if credit is None or credit.status!='OPEN' or row.amount_vnd>credit.remaining_vnd:
            raise AppError('ERR-REFUND-BALANCE','Số dư có nguồn khả dụng không đủ để hoàn.',409)
    elif kind=='PAYMENT_REVERSE':
        if session.scalar(select(FinanceCommand.id).where(FinanceCommand.target_id==payment.id,FinanceCommand.kind=='PAYMENT_REFUND',FinanceCommand.status=='EXECUTED').limit(1)):
            raise AppError('ERR-PAYMENT-REVERSE','Thu tiền đã hoàn một phần; cần chứng từ điều chỉnh riêng.',409)
        for a in allocations:
            invoice=financial_record(session,context,BillingInvoice,a.billing_invoice_id,period.building_id)
            if invoice.status=='VOID' or invoice.outstanding_vnd+a.amount_vnd>invoice.total_vnd:
                raise AppError('ERR-PAYMENT-REVERSE','Phân bổ nguồn không còn phù hợp để đảo.',409)
        result['invoices']=[{'id':str(a.billing_invoice_id),'version':session.get(BillingInvoice,a.billing_invoice_id).version} for a in allocations]
        uses=session.scalars(select(CreditUseAllocation).where(CreditUseAllocation.credit_id==credit.id)).all() if credit else []
        result['credit_uses']=[]
        for use in uses:
            invoice=financial_record(session,context,BillingInvoice,use.invoice_id,period.building_id)
            if invoice.status=='VOID' or invoice.outstanding_vnd+use.amount_vnd>invoice.total_vnd:raise AppError('ERR-PAYMENT-REVERSE','Phân bổ số dư có không còn phù hợp.',409)
            result['credit_uses'].append({'id':str(use.id),'invoice_id':str(invoice.id),'amount_vnd':use.amount_vnd,'version':invoice.version})
    return result


def decision_amount(row):
    if row.kind=='INVOICE_VOID':return row.snapshot['total_vnd']
    if row.kind=='PAYMENT_REVERSE':return row.snapshot['payment_amount_vnd']
    if row.kind in {'ALLOCATE','CREDIT_USE'}:return sum(a['amount_vnd'] for a in row.data['allocations'])
    return row.amount_vnd


def execute_command(session,context,row,period,execution_reference):
    from app.models.billing import Payment, PaymentAllocation, OverpaymentCredit, ArLedgerEntry
    from app.models.resident_portal import PortalDeposit, PortalDepositMovement
    from app.services.resident_portal import deposit_movement
    from datetime import date
    kind=row.kind
    def ledger(account_id,debit=0,credit=0,entry='CREDIT_ISSUED'):
        session.add(ArLedgerEntry(tenant_id=row.tenant_id,site_id=row.site_id,building_id=row.building_id,
            billing_account_id=account_id,accounting_period_id=period.id,entry_type=entry,source_type='FINANCE_COMMAND',
            source_id=row.id,debit_vnd=debit,credit_vnd=credit,effective_at=utc_now(),created_by_id=context.account_id))
    if kind=='PERIOD_LOCK':period.status='LOCKED';period.version+=1
    elif kind=='PERIOD_REOPEN':
        row.data={**row.data,'ledger_ids_before':[str(i) for i in session.scalars(select(ArLedgerEntry.id).where(ArLedgerEntry.accounting_period_id==period.id))]}
    elif kind=='ACCOUNT_OPEN':
        session.add(BillingAccount(tenant_id=row.tenant_id,site_id=row.site_id,building_id=row.building_id,
            unit_id=row.target_id,account_number=row.data['account_number'],opened_on=date.fromisoformat(row.data['effective_on']),status='ACTIVE'))
    elif kind.startswith('ACCOUNT_'):
        account=session.get(BillingAccount,row.target_id)
        account.status={'ACCOUNT_SUSPEND':'SUSPENDED','ACCOUNT_RESUME':'ACTIVE','ACCOUNT_CLOSE':'CLOSED'}[kind]
        if kind=='ACCOUNT_CLOSE':account.closed_on=date.fromisoformat(row.data['effective_on'])
        account.version+=1
    elif kind.startswith('DEPOSIT_'):
        action=kind.removeprefix('DEPOSIT_');deposit=session.get(PortalDeposit,row.target_id)
        deposit_movement(deposit,action,row.amount_vnd)
        session.add(PortalDepositMovement(tenant_id=row.tenant_id,site_id=row.site_id,building_id=row.building_id,
            unit_id=row.unit_id,account_id=row.account_id,deposit_id=deposit.id,kind=action,amount_vnd=row.amount_vnd,
            reference=execution_reference,reason=row.reason,actor_id=context.account_id))
    elif kind in {'CREDIT','WRITE_OFF'}:
        invoice=session.get(BillingInvoice,row.target_id)
        invoice.outstanding_vnd=max(0,invoice.outstanding_vnd-row.amount_vnd)
        invoice.status='PAID' if invoice.outstanding_vnd==0 else 'PARTIALLY_PAID';invoice.version+=1
        ledger(invoice.billing_account_id,credit=row.amount_vnd)
    elif kind=='INVOICE_VOID':
        invoice=session.get(BillingInvoice,row.target_id)
        invoice.status='VOID';invoice.outstanding_vnd=0;invoice.voided_at=utc_now()
        invoice.voided_by_id=context.account_id;invoice.void_reason=row.reason;invoice.version+=1
        ledger(invoice.billing_account_id,credit=invoice.total_vnd,entry='REVERSAL')
    else:
        credit=session.get(OverpaymentCredit,row.target_id) if kind=='CREDIT_USE' else session.scalar(select(OverpaymentCredit).where(OverpaymentCredit.payment_id==row.target_id))
        payment=session.get(Payment,credit.payment_id if kind=='CREDIT_USE' else row.target_id)
        if kind=='PAYMENT_REFUND':
            credit.remaining_vnd-=row.amount_vnd;credit.version+=1
            credit.status='EXHAUSTED' if credit.remaining_vnd==0 else 'OPEN'
            # Overpayment funds left AR when the separate credit was created.
            # Cash execution consumes that payable; it must not debit AR again.
        elif kind=='PAYMENT_REVERSE':
            for a in session.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id==payment.id)):
                invoice=session.get(BillingInvoice,a.billing_invoice_id)
                invoice.outstanding_vnd+=a.amount_vnd
                invoice.status='ISSUED' if invoice.outstanding_vnd==invoice.total_vnd else 'PARTIALLY_PAID';invoice.version+=1
                session.add(AllocationReversal(allocation_id=a.id,command_id=row.id,amount_vnd=a.amount_vnd))
            for use in session.scalars(select(CreditUseAllocation).where(CreditUseAllocation.credit_id==credit.id)) if credit else []:
                invoice=session.get(BillingInvoice,use.invoice_id)
                invoice.outstanding_vnd+=use.amount_vnd;invoice.version+=1
                invoice.status='ISSUED' if invoice.outstanding_vnd==invoice.total_vnd else 'PARTIALLY_PAID'
                session.add(AllocationReversal(credit_allocation_id=use.id,command_id=row.id,amount_vnd=use.amount_vnd))
            reverse_ar=payment.amount_vnd-(credit.remaining_vnd if credit else 0)
            if credit:credit.status='VOID';credit.remaining_vnd=0;credit.version+=1
            payment.status='REVERSED'
            if reverse_ar:ledger(payment.billing_account_id,debit=reverse_ar,entry='REVERSAL')
        else:
            for line in row.data['allocations']:
                invoice=session.get(BillingInvoice,UUID(line['invoice_id']))
                if kind=='CREDIT_USE':
                    session.add(CreditUseAllocation(command_id=row.id,credit_id=credit.id,invoice_id=invoice.id,amount_vnd=line['amount_vnd']))
                else:
                    session.add(PaymentAllocation(tenant_id=row.tenant_id,site_id=row.site_id,building_id=row.building_id,
                        payment_id=payment.id,billing_invoice_id=invoice.id,amount_vnd=line['amount_vnd'],allocated_by_id=context.account_id))
                session.flush()
                invoice.outstanding_vnd-=line['amount_vnd'];invoice.version+=1
                invoice.status='PAID' if invoice.outstanding_vnd==0 else 'PARTIALLY_PAID'
            total=sum(a['amount_vnd'] for a in row.data['allocations'])
            if kind=='CREDIT_USE':
                credit.remaining_vnd-=total;credit.version+=1;credit.status='EXHAUSTED' if credit.remaining_vnd==0 else 'OPEN'
                ledger(payment.billing_account_id,credit=total,entry='CREDIT_APPLIED')
            allocated=session.scalar(select(func.coalesce(func.sum(PaymentAllocation.amount_vnd),0)).where(PaymentAllocation.payment_id==payment.id)) or 0
            if kind=='ALLOCATE' and allocated<payment.amount_vnd:
                remaining=payment.amount_vnd-allocated
                credit=OverpaymentCredit(tenant_id=row.tenant_id,site_id=row.site_id,building_id=row.building_id,
                    billing_account_id=payment.billing_account_id,payment_id=payment.id,original_vnd=remaining,remaining_vnd=remaining,status='OPEN')
                session.add(credit);session.flush()
                ledger(payment.billing_account_id,debit=remaining,entry='CREDIT_ISSUED')
                payment.status='OVERPAID'
            else:payment.status='ALLOCATED' if not credit or credit.remaining_vnd==0 else 'OVERPAID'
        payment.version+=1
    row.data={**row.data,'execution_reference':execution_reference}
    row.status='EXECUTED';row.executed_at=utc_now()


def guard_payment_decisions(session,payment_id,*,command_id=None,provider=False,operation=None):
    """Account lock at callers serializes decisions across manual/provider paths."""
    from app.models.resident_portal import PortalFinancialAdjustment, PortalPaymentIntent
    from app.models.billing import OverpaymentCredit, Payment
    payment=session.get(Payment,payment_id)
    if payment is None or payment.status=='REVERSED':
        raise AppError('ERR-PAYMENT-STATE','Thu tiền nguồn đã đảo/không tồn tại.',409)
    if not provider:
        old=session.scalar(select(PortalFinancialAdjustment.id).join(PortalPaymentIntent,
            PortalPaymentIntent.id==PortalFinancialAdjustment.payment_intent_id).where(
            PortalPaymentIntent.payment_id==payment_id,PortalFinancialAdjustment.kind=='REFUND',
            PortalFinancialAdjustment.status.in_(('APPROVED','SENDING','RECONCILIATION','COMPLETED'))).limit(1))
        if old:raise AppError('ERR-PAYMENT-RESERVED','Nguồn đã được dành cho hoàn VNPay; xử lý/đối soát hồ sơ nguồn trước.',409)
    conditions=[FinanceCommand.kind.in_(('PAYMENT_REFUND','PAYMENT_REVERSE')),
        FinanceCommand.target_id==payment_id,
        FinanceCommand.status.in_(('APPROVED','RECONCILIATION','EXECUTED')
            if provider or operation=='PAYMENT_REVERSE' else ('APPROVED','RECONCILIATION'))]
    if command_id:conditions.append(FinanceCommand.id!=command_id)
    if session.scalar(select(FinanceCommand.id).where(*conditions).limit(1)):
        raise AppError('ERR-PAYMENT-RESERVED','Nguồn đang hoàn/đảo hoặc đã thực hiện; cần xử lý hồ sơ nguồn trước.',409)
    if provider:
        credits=select(OverpaymentCredit.id).where(OverpaymentCredit.payment_id==payment_id)
        if session.scalar(select(FinanceCommand.id).where(FinanceCommand.kind=='CREDIT_USE',
            FinanceCommand.target_id.in_(credits),FinanceCommand.status=='EXECUTED').limit(1)):
            raise AppError('ERR-PAYMENT-RESERVED','Tiền thừa nguồn đã sử dụng; cần đối soát trước khi hoàn qua VNPay.',409)
