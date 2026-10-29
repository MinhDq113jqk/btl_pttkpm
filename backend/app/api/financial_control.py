"""Controlled financial proposals, draft billing and receivable follow-up."""
from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, select
from pydantic import ValidationError
from app.core.exceptions import AppError
from app.core.policy import UserContext, context_for_account, get_current_user_context, scope_not_found
from app.models.account import Account
from app.models.billing import AccountingPeriod, ArLedgerEntry, BillingAccount, BillingInvoice, BillingInvoiceItem
from app.models.financial_control import BillingReview, FinanceCommand, ArCase, FinanceEvent, FinancePolicy, ApprovalDelegation
from app.schemas.financial_control import CommandInput, ArInput, PolicyInput, DelegationInput
from app.schemas.resident_portal import PortalAction
from app.services.r2 import require_version, utc_now
from app.services.resident_portal import FINANCE, command, resident, scope_values, scoped, unit_for, view, visible_conditions
from app.services.financial_control import (check_approver, command_snapshot, digest, event, execute_command,
    financial_record, issue_review, recalculate_review, decision_amount)

router=APIRouter(prefix='/portal/finance',tags=['Financial decisions'])


def approved_actor(session,row):
    account=session.get(Account,row.approved_by_id)
    if account is None or not account.is_active:raise AppError('ERR-APPROVER-INACTIVE','Người duyệt không còn hiệu lực; cần duyệt lại.',409)
    return context_for_account(session,account,row.site_id)


def records(request,context,model):
    context.assert_role(*FINANCE)
    with request.app.state.database.get_session() as session:
        return {'items':[view(r) for r in session.scalars(select(model).where(*visible_conditions(context,model,'finance',roles=FINANCE,own=False)).order_by(model.created_at.desc()).limit(300))]}


@router.get('/reviews')
def reviews(request:Request,context:UserContext=Depends(get_current_user_context)):
    return records(request,context,BillingReview)


@router.get('/commands')
def commands(request:Request,context:UserContext=Depends(get_current_user_context)):
    return records(request,context,FinanceCommand)


@router.get('/{resource}/{identifier}/history')
def history(resource:str,identifier:UUID,request:Request,context:UserContext=Depends(get_current_user_context)):
    model={'reviews':BillingReview,'commands':FinanceCommand,'ar':ArCase}.get(resource)
    if model is None:raise scope_not_found()
    with request.app.state.database.get_session() as session:
        row=scoped(session,context,model,identifier,'finance',roles=FINANCE,own=False)
        return {'items':[view(e) for e in session.scalars(select(FinanceEvent).where(FinanceEvent.resource_type==model.__name__,FinanceEvent.resource_id==row.id).order_by(FinanceEvent.created_at,FinanceEvent.id))]}


@router.post('/reviews/{identifier}/actions')
def review_action(identifier:UUID,body:PortalAction,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        context.assert_role(*FINANCE)
        initial=scoped(session,context,BillingReview,identifier,'finance',roles=FINANCE,own=False)
        period=financial_record(session,context,AccountingPeriod,initial.period_id,initial.building_id)
        row=scoped(session,context,BillingReview,identifier,'finance',roles=FINANCE,own=False,lock=True)
        require_version(row.version,body.expected_version)
        if not body.reason.strip():raise AppError('ERR-DECISION-REASON','Cần lý do thao tác.',422)
        if body.action in {'REFRESH','SUBMIT','SUPPLEMENT','CANCEL'} and row.account_id!=context.account_id:
            raise AppError('ERR-FORBIDDEN','Thao tác thuộc người lập bản nháp.',403)
        if body.action in {'REFRESH','SUPPLEMENT'} and row.status in {'DRAFT','WAITING_INFO','REJECTED','APPROVED','SUBMITTED','CANCELLED'}:
            row.snapshot=recalculate_review(session,row,period,context.account_id)
            row.calculation_hash=digest(row.snapshot);row.status='DRAFT';row.approved_by_id=None
        elif body.action=='CANCEL' and row.status in {'DRAFT','WAITING_INFO','REJECTED','SUBMITTED'}:row.status='CANCELLED'
        elif body.action in {'SUBMIT','APPROVE','ISSUE'}:
            expected={'SUBMIT':'DRAFT','APPROVE':'SUBMITTED','ISSUE':'APPROVED'}[body.action]
            if row.status!=expected:raise AppError('ERR-STATE-TRANSITION','Bản tính chưa ở trạng thái phù hợp.',409)
            snapshot=recalculate_review(session,row,period,context.account_id)
            if digest(snapshot)!=row.calculation_hash:raise AppError('ERR-BILLING-SOURCE-STALE','Nguồn tính đã đổi; tính lại và trình duyệt lại.',409)
            amount=sum(r['total_vnd'] for r in row.snapshot.get('invoices',[])) if row.billing_run_id else row.snapshot['calculation']['amount_vnd']
            if body.action=='SUBMIT':row.status='SUBMITTED'
            elif body.action=='APPROVE':
                check_approver(session,context,row,'BILLING',amount);row.approved_by_id=context.account_id;row.status='APPROVED'
            else:
                check_approver(session,approved_actor(session,row),row,'BILLING',amount)
                issue_review(session,row,period,context.account_id)
        elif body.action in {'REQUEST_INFO','REJECT'} and row.status=='SUBMITTED':
            check_approver(session,context,row,'BILLING')
            row.status='WAITING_INFO' if body.action=='REQUEST_INFO' else 'REJECTED'
        else:raise AppError('ERR-STATE-TRANSITION','Thao tác bản tính không phù hợp trạng thái.',409)
        row.version+=1;event(session,row,context.account_id,body.action,body.reason)
        return row,'finance'
    return command(request,context,key,'billing-review.action',{'id':str(identifier),**body.model_dump(mode='json')},execute,roles=FINANCE)


def proposal(session,context,body):
    context.assert_role(*FINANCE)
    period=financial_record(session,context,AccountingPeriod,body.period_id)
    row=FinanceCommand(**scope_values(context,building_id=period.building_id),kind=body.kind,period_id=period.id,
        target_id=body.target_id,amount_vnd=body.amount_vnd,reason=body.reason,evidence_reference=body.evidence_reference,
        data=body.data.model_dump(mode='json',exclude_none=True))
    row.snapshot=command_snapshot(session,context,row,period)
    row.amount_vnd=decision_amount(row)
    if body.expected_hash and digest(row.snapshot)!=body.expected_hash:
        raise AppError('ERR-FINANCE-SOURCE-STALE','Nguồn đã đổi từ bản xem trước; xem lại trước khi xác nhận.',409)
    if row.snapshot.get('unit_id'):row.unit_id=UUID(row.snapshot['unit_id'])
    return row


@router.get('/options')
def finance_options(request:Request,context:UserContext=Depends(get_current_user_context)):
    context.assert_role(*FINANCE)
    from app.models.billing import Payment, OverpaymentCredit
    from app.models.resident_portal import PortalDeposit
    from app.services.resident_portal import staff_conditions
    with request.app.state.database.get_session() as session:
        result={}
        for name,model in [('accounts',BillingAccount),('periods',AccountingPeriod),('invoices',BillingInvoice),('payments',Payment),('credits',OverpaymentCredit),('deposits',PortalDeposit)]:
            result[name]=[view(r) for r in session.scalars(select(model).where(*context.scope_conditions(model),*staff_conditions(context,model,FINANCE)).order_by(model.id).limit(500))]
        result['staff_accounts']=[]
        for account in session.scalars(select(Account).where(Account.tenant_id==context.tenant_id,Account.is_active.is_(True))):
            try:context_for_account(session,account,context.assert_active_site()).assert_role(*FINANCE)
            except AppError:continue
            result['staff_accounts'].append({'id':account.id,'name':account.full_name})
        return result


@router.post('/commands/preview')
def preview_command(body:CommandInput,request:Request,context:UserContext=Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        row=proposal(session,context,body)
        return {'snapshot':row.snapshot,'calculation_hash':digest(row.snapshot),'amount_vnd':row.amount_vnd,
            'allocations':row.data.get('allocations',[]),'requires_independent_approval':True}


@router.post('/commands',status_code=201)
def create_command(body:CommandInput,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        row=proposal(session,context,body);session.add(row);session.flush()
        event(session,row,context.account_id,'CREATE',body.reason)
        return row,'finance'
    return command(request,context,key,'finance-command.create',body.model_dump(mode='json'),execute,roles=FINANCE)


@router.post('/commands/{identifier}/actions')
def finance_action(identifier:UUID,body:PortalAction,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        context.assert_role(*FINANCE)
        initial=scoped(session,context,FinanceCommand,identifier,'finance',roles=FINANCE,own=False)
        period=financial_record(session,context,AccountingPeriod,initial.period_id,initial.building_id)
        row=scoped(session,context,FinanceCommand,identifier,'finance',roles=FINANCE,own=False,lock=True)
        require_version(row.version,body.expected_version)
        if not body.reason.strip():raise AppError('ERR-DECISION-REASON','Cần lý do quyết định.',422)
        if body.action in {'SUBMIT','REFRESH','SUPPLEMENT','CANCEL'} and row.account_id!=context.account_id:
            raise AppError('ERR-FORBIDDEN','Thao tác thuộc người lập hồ sơ.',403)
        if body.action in {'REFRESH','SUPPLEMENT'} and row.status in {'DRAFT','WAITING_INFO','REJECTED','APPROVED','SUBMITTED'}:
            if body.data:
                from app.schemas.financial_control import CommandData
                try:row.data=CommandData.model_validate({**row.data,**body.data}).model_dump(mode='json',exclude_none=True)
                except ValidationError:raise AppError('ERR-FINANCE-DATA','Dữ liệu bổ sung không hợp lệ.',422) from None
            row.snapshot=command_snapshot(session,context,row,period);row.status='DRAFT';row.approved_by_id=None
            row.amount_vnd=decision_amount(row)
        elif body.action=='CANCEL' and row.status in {'DRAFT','WAITING_INFO','SUBMITTED','REJECTED'}:row.status='CANCELLED'
        elif body.action in {'REQUEST_INFO','REJECT'} and row.status=='SUBMITTED':
            check_approver(session,context,row,row.kind,row.amount_vnd)
            row.status='WAITING_INFO' if body.action=='REQUEST_INFO' else 'REJECTED'
        elif body.action=='MARK_UNCERTAIN' and row.status=='APPROVED' and row.kind in {'PAYMENT_REFUND','DEPOSIT_REFUND'}:
            row.status='RECONCILIATION'
        elif body.action in {'SUBMIT','APPROVE','EXECUTE','CONFIRM_EXECUTION'}:
            expected={'SUBMIT':'DRAFT','APPROVE':'SUBMITTED','EXECUTE':'APPROVED','CONFIRM_EXECUTION':'RECONCILIATION'}[body.action]
            if row.status!=expected:raise AppError('ERR-STATE-TRANSITION','Hồ sơ chưa ở trạng thái phù hợp.',409)
            fresh=command_snapshot(session,context,row,period)
            if digest(fresh)!=digest(row.snapshot):raise AppError('ERR-FINANCE-SOURCE-STALE','Nguồn đã đổi; kiểm tra và trình duyệt lại.',409)
            if body.action=='SUBMIT':row.status='SUBMITTED'
            elif body.action=='APPROVE':
                check_approver(session,context,row,row.kind,row.amount_vnd);row.status='APPROVED';row.approved_by_id=context.account_id
            else:
                check_approver(session,approved_actor(session,row),row,row.kind,row.amount_vnd)
                reference=body.data.get('execution_reference')
                if not isinstance(reference,str) or not 3<=len(reference.strip())<=150:
                    raise AppError('ERR-EXECUTION-EVIDENCE','Cần mã chứng từ thực hiện/thực chi.',422)
                import hashlib
                material=f'execution:{row.site_id}:{row.kind}:{reference.strip()}'
                session.execute(select(func.pg_advisory_xact_lock(int.from_bytes(hashlib.sha256(material.encode()).digest()[:8],'big',signed=True))))
                duplicate=session.scalar(select(FinanceCommand.id).where(FinanceCommand.site_id==row.site_id,FinanceCommand.kind==row.kind,
                    FinanceCommand.status=='EXECUTED',FinanceCommand.data['execution_reference'].as_string()==reference.strip()).limit(1))
                if duplicate:raise AppError('ERR-EXECUTION-DUPLICATE','Mã chứng từ thực hiện đã được sử dụng.',409)
                if row.kind.startswith('DEPOSIT_'):
                    from app.models.resident_portal import PortalDepositMovement
                    if session.scalar(select(PortalDepositMovement.id).where(PortalDepositMovement.site_id==row.site_id,
                        PortalDepositMovement.kind==row.kind.removeprefix('DEPOSIT_'),PortalDepositMovement.reference==reference.strip()).limit(1)):
                        raise AppError('ERR-EXECUTION-DUPLICATE','Mã chứng từ cọc đã được sử dụng.',409)
                execute_command(session,context,row,period,reference.strip())
        else:raise AppError('ERR-STATE-TRANSITION','Thao tác hồ sơ tài chính không phù hợp.',409)
        row.version+=1;event(session,row,context.account_id,body.action,body.reason)
        return row,'finance'
    return command(request,context,key,'finance-command.action',{'id':str(identifier),**body.model_dump(mode='json')},execute,roles=FINANCE)


@router.get('/ar')
def ar(request:Request,unit_id:UUID|None=None,as_of:date|None=None,context:UserContext=Depends(get_current_user_context)):
    from app.services.portal_finance import business_date
    cutoff=as_of or business_date()
    with request.app.state.database.get_session() as session:
        if resident(context) and unit_id is None:raise AppError('ERR-UNIT-REQUIRED','Cần chọn căn.',422)
        if unit_id:unit_for(session,context,unit_id,'finance',roles=FINANCE)
        accounts=select(BillingAccount.id).where(*context.scope_conditions(BillingAccount))
        if unit_id:accounts=accounts.where(BillingAccount.unit_id==unit_id)
        else:
            from app.services.resident_portal import staff_conditions
            accounts=accounts.where(*staff_conditions(context,BillingAccount,FINANCE))
        invoices=session.scalars(select(BillingInvoice).where(BillingInvoice.billing_account_id.in_(accounts),BillingInvoice.status.not_in(('DRAFT','VOID'))).order_by(BillingInvoice.due_on,BillingInvoice.id)).all()
        cases=session.scalars(select(ArCase).where(ArCase.invoice_id.in_([i.id for i in invoices]))).all()
        aging={'CURRENT':0,'1_30':0,'31_60':0,'61_90':0,'OVER_90':0,'NO_DUE_DATE':0};rows=[]
        for i in invoices:
            days=max(0,(cutoff-(i.due_on or cutoff)).days)
            bucket='CURRENT' if days==0 else '1_30' if days<=30 else '31_60' if days<=60 else '61_90' if days<=90 else 'OVER_90'
            if i.due_on is None:bucket='NO_DUE_DATE'
            aging[bucket]+=i.outstanding_vnd
            disputed=sum(c.amount_vnd for c in cases if c.invoice_id==i.id and c.kind=='DISPUTE' and c.status=='OPEN')
            rows.append({**view(i),'days_overdue':days,'bucket':bucket,'disputed_vnd':disputed})
        ledger=session.scalars(select(ArLedgerEntry).where(ArLedgerEntry.billing_account_id.in_(accounts)).order_by(ArLedgerEntry.effective_at,ArLedgerEntry.id)).all()
        return {'as_of':cutoff,'balance_basis':'CURRENT_BALANCE_AGED_AT_DATE','aging':aging,'items':rows,'cases':[view(c) for c in cases],
            'ledger':[view(e) for e in ledger],'ledger_balance_vnd':sum(e.debit_vnd-e.credit_vnd for e in ledger)}


@router.post('/ar',status_code=201)
def create_ar(body:ArInput,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        from app.services.portal_finance import business_date
        if resident(context):
            if body.kind=='REMINDER':raise AppError('ERR-FORBIDDEN','Nhắc nợ do kế toán lập.',403)
            initial=session.scalar(select(BillingInvoice).where(BillingInvoice.id==body.invoice_id,*context.scope_conditions(BillingInvoice)))
            if initial is None:raise scope_not_found()
            account=session.get(BillingAccount,initial.billing_account_id)
            unit=unit_for(session,context,account.unit_id,'finance')
            invoice=session.scalar(select(BillingInvoice).where(BillingInvoice.id==initial.id).with_for_update())
        else:
            initial=financial_record(session,context,BillingInvoice,body.invoice_id,lock=False)
            account=financial_record(session,context,BillingAccount,initial.billing_account_id)
            invoice=financial_record(session,context,BillingInvoice,initial.id)
            unit=unit_for(session,context,account.unit_id,'finance',roles=FINANCE)
        if invoice.status not in {'ISSUED','PARTIALLY_PAID'} or body.amount_vnd>invoice.outstanding_vnd:
            raise AppError('ERR-AR-AMOUNT','Hồ sơ vượt số nợ còn lại.',409)
        if body.invoice_item_id:
            item=session.scalar(select(BillingInvoiceItem).where(BillingInvoiceItem.id==body.invoice_item_id,BillingInvoiceItem.billing_invoice_id==invoice.id))
            if item is None:raise scope_not_found()
            if body.amount_vnd>item.amount_vnd:raise AppError('ERR-AR-AMOUNT','Tranh chấp vượt giá trị dòng.',409)
        disputed=session.scalar(select(func.coalesce(func.sum(ArCase.amount_vnd),0)).where(ArCase.invoice_id==invoice.id,ArCase.kind=='DISPUTE',ArCase.status=='OPEN')) or 0
        if body.kind=='DISPUTE' and disputed+body.amount_vnd>invoice.outstanding_vnd:raise AppError('ERR-AR-AMOUNT','Tranh chấp đang mở vượt số nợ.',409)
        if body.kind=='REMINDER':
            if body.include_disputed is None:raise AppError('ERR-AR-POLICY','Cần chọn có nhắc phần tranh chấp hay không.',422)
            if not body.include_disputed and body.amount_vnd>max(0,invoice.outstanding_vnd-disputed):raise AppError('ERR-AR-POLICY','Số nhắc gồm phần tranh chấp đã chọn loại trừ.',409)
        if body.kind=='PROMISE' and (body.due_on is None or body.due_on<business_date()):raise AppError('ERR-AR-DATE','Cam kết cần ngày trả hợp lệ.',422)
        row=ArCase(**scope_values(context,unit),invoice_id=invoice.id,invoice_item_id=body.invoice_item_id,
            kind=body.kind,amount_vnd=body.amount_vnd,due_on=body.due_on,reason=body.reason,data={'include_disputed':body.include_disputed})
        session.add(row);session.flush();event(session,row,context.account_id,'CREATE',body.reason)
        if body.kind=='REMINDER':
            from app.services.outbox import enqueue_notification
            from app.services.property import person_family
            people=set()
            for episode in invoice.responsibility_snapshot.get('episodes',[]):
                people.update(person_family(session,context.tenant_id,UUID(episode['person_id'])))
            if not people:raise AppError('ERR-LIABILITY-MISSING','Hóa đơn cũ chưa có căn cứ người chịu phí; xác minh trước khi gửi nhắc nợ.',409)
            for account_id in session.scalars(select(Account.id).where(Account.person_id.in_(people),Account.is_active.is_(True),Account.tenant_id==context.tenant_id)):
                enqueue_notification(session,context,request,event_type='DebtReminder',resource_type='ArCase',resource_id=row.id,
                    recipient_account_id=account_id,template_code='PORTAL_UPDATE',template_snapshot={'title':'Nhắc thanh toán','body':f'Hóa đơn {invoice.invoice_number}: {body.amount_vnd:,} VND. {body.reason}','unit_id':str(unit.id)})
        return row,'finance'
    return command(request,context,key,'ar-case.create',body.model_dump(mode='json'),execute,roles=FINANCE)


@router.post('/ar/{identifier}/actions')
def ar_action(identifier:UUID,body:PortalAction,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        context.assert_role(*FINANCE)
        row=scoped(session,context,ArCase,identifier,'finance',roles=FINANCE,own=False,lock=True)
        require_version(row.version,body.expected_version)
        if row.status!='OPEN' or body.action not in {'RESOLVE','REJECT','FULFILLED','BROKEN'} or not body.reason.strip():
            raise AppError('ERR-STATE-TRANSITION','Cần hồ sơ mở và lý do xử lý.',409)
        if body.action in {'FULFILLED','BROKEN'} and row.kind!='PROMISE':raise AppError('ERR-STATE-TRANSITION','Thao tác chỉ dành cam kết thanh toán.',409)
        row.status=body.action;row.version+=1;event(session,row,context.account_id,body.action,body.reason)
        return row,'finance'
    return command(request,context,key,'ar-case.action',{'id':str(identifier),**body.model_dump(mode='json')},execute,roles=FINANCE)


@router.get('/policies')
def policies(request:Request,context:UserContext=Depends(get_current_user_context)):return records(request,context,FinancePolicy)


@router.post('/policies',status_code=201)
def create_policy(body:PolicyInput,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        context.assert_role('admin','director')
        from app.models.site import Site
        session.scalar(select(Site).where(Site.id==context.assert_active_site()).with_for_update())
        if session.scalar(select(FinancePolicy.id).where(FinancePolicy.site_id==context.assert_active_site(),FinancePolicy.code==body.code)):
            raise AppError('ERR-POLICY-EXISTS','Chính sách đã tồn tại; cập nhật bằng phiên bản hiện tại.',409)
        row=FinancePolicy(**scope_values(context),code=body.code,purpose=body.purpose,
            data={'approval_roles':body.approval_roles,'max_amount_vnd':body.max_amount_vnd})
        session.add(row);return row,'finance'
    return command(request,context,key,'finance-policy.create',body.model_dump(mode='json'),execute,roles=FINANCE)


@router.post('/policies/{identifier}/actions')
def policy_action(identifier:UUID,body:PortalAction,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        context.assert_role('admin','director')
        row=scoped(session,context,FinancePolicy,identifier,'finance',roles=FINANCE,lock=True)
        require_version(row.version,body.expected_version)
        if body.action!='UPDATE' or not body.reason.strip():raise AppError('ERR-STATE-TRANSITION','Cần lý do cập nhật chính sách.',422)
        try:parsed=PolicyInput.model_validate({'code':row.code,'purpose':row.purpose,**body.data})
        except ValidationError:raise AppError('ERR-FINANCE-POLICY','Dữ liệu chính sách không hợp lệ.',422) from None
        row.purpose=parsed.purpose;row.data={'approval_roles':parsed.approval_roles,'max_amount_vnd':parsed.max_amount_vnd};row.version+=1
        event(session,row,context.account_id,'UPDATE',body.reason)
        return row,'finance'
    return command(request,context,key,'finance-policy.action',{'id':str(identifier),**body.model_dump(mode='json')},execute,roles=FINANCE)


@router.get('/delegations')
def delegations(request:Request,context:UserContext=Depends(get_current_user_context)):return records(request,context,ApprovalDelegation)


@router.post('/delegations',status_code=201)
def create_delegation(body:DelegationInput,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        context.assert_building_role(body.building_id,'admin','director')
        account=session.scalar(select(Account).where(Account.id==body.delegate_account_id,Account.tenant_id==context.tenant_id,Account.is_active.is_(True)))
        if account is None:raise scope_not_found()
        context_for_account(session,account,context.assert_active_site()).assert_building_role(body.building_id,*FINANCE)
        if body.delegate_account_id==context.account_id:raise AppError('ERR-DELEGATION','Không tự ủy nhiệm.',422)
        row=ApprovalDelegation(**scope_values(context,building_id=body.building_id),delegate_account_id=account.id,purpose=body.purpose,
            valid_from=body.valid_from,valid_to=body.valid_to)
        session.add(row);session.flush();event(session,row,context.account_id,'CREATE',body.reason)
        return row,'finance'
    return command(request,context,key,'approval-delegation.create',body.model_dump(mode='json'),execute,roles=FINANCE)


@router.post('/delegations/{identifier}/actions')
def delegation_action(identifier:UUID,body:PortalAction,request:Request,context:UserContext=Depends(get_current_user_context),key:str=Header(...,alias='Idempotency-Key')):
    def execute(session):
        row=scoped(session,context,ApprovalDelegation,identifier,'finance',roles=FINANCE,lock=True)
        context.assert_building_role(row.building_id,'admin','director');require_version(row.version,body.expected_version)
        if body.action!='REVOKE' or not body.reason.strip():raise AppError('ERR-STATE-TRANSITION','Cần lý do thu hồi ủy nhiệm.',422)
        row.revoked=True;row.version+=1;event(session,row,context.account_id,'REVOKE',body.reason)
        return row,'finance'
    return command(request,context,key,'approval-delegation.action',{'id':str(identifier),**body.model_dump(mode='json')},execute,roles=FINANCE)


@router.get('/periods/{identifier}/delta')
def period_delta(identifier:UUID,request:Request,context:UserContext=Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        period=financial_record(session,context,AccountingPeriod,identifier,lock=False)
        grants=session.scalars(select(FinanceCommand).where(FinanceCommand.period_id==period.id,FinanceCommand.kind=='PERIOD_REOPEN',FinanceCommand.status=='EXECUTED')).all()
        ledger=session.scalars(select(ArLedgerEntry).where(ArLedgerEntry.accounting_period_id==period.id)).all()
        return {'items':[{'command_id':g.id,'expires_at':g.data['expires_at'],'allowed_kinds':g.data['allowed_kinds'],
            'delta_entries':[view(e) for e in ledger if str(e.id) not in g.data.get('ledger_ids_before',[])],
            'delta_balance_vnd':sum(e.debit_vnd-e.credit_vnd for e in ledger if str(e.id) not in g.data.get('ledger_ids_before',[]))} for g in grants]}
