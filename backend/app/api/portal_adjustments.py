"""Financial corrections keep original invoices/receipts and separate maker/checker."""
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, select
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.billing import AccountingPeriod, ArLedgerEntry, BillingAccount, BillingInvoice
from app.models.resident_portal import PortalFinancialAdjustment, PortalPaymentIntent
from app.schemas.resident_portal import FinancialAdjustmentInput, PortalAction
from app.services import vnpay
from app.services.r2 import audit, require_version, utc_now
from app.services.resident_portal import FINANCE, command, scope_values, scoped, unit_for, view, visible_conditions

router = APIRouter(prefix='/portal', tags=['Portal financial adjustments'])


def _balance(session, account):
    return int(session.scalar(select(func.coalesce(func.sum(ArLedgerEntry.debit_vnd - ArLedgerEntry.credit_vnd), 0))
        .where(ArLedgerEntry.billing_account_id == account.id)) or 0)


@router.get('/adjustments')
def adjustments(request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        conditions = list(visible_conditions(context, PortalFinancialAdjustment, 'finance', own=False, roles=FINANCE))
        if unit_id:
            unit_for(session, context, unit_id, 'finance', roles=FINANCE)
            conditions.append(PortalFinancialAdjustment.unit_id == unit_id)
        return {'items': [view(r) for r in session.scalars(select(PortalFinancialAdjustment).where(*conditions).order_by(PortalFinancialAdjustment.created_at.desc()).limit(200))]}


@router.post('/adjustments', status_code=201)
def create_adjustment(body: FinancialAdjustmentInput, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        context.assert_role(*FINANCE)
        unit = unit_for(session, context, body.unit_id, 'finance', roles=FINANCE)
        intent = scoped(session, context, PortalPaymentIntent, body.payment_intent_id, 'finance', lock=True, roles=FINANCE) if body.kind == 'REFUND' else None
        account = session.scalar(select(BillingAccount).where(BillingAccount.unit_id == unit.id, *context.scope_conditions(BillingAccount)).with_for_update())
        invoice = session.scalar(select(BillingInvoice).where(BillingInvoice.id == body.invoice_id,
            BillingInvoice.billing_account_id == (account.id if account else None), *context.scope_conditions(BillingInvoice)).with_for_update())
        if invoice is None or invoice.status in {'DRAFT', 'VOID'}:
            raise scope_not_found()
        if body.kind == 'CREDIT' and body.amount_vnd > invoice.total_vnd:
            raise AppError('ERR-ADJUSTMENT-AMOUNT', 'Điều chỉnh vượt giá trị hóa đơn.', 422)
        if body.kind == 'REFUND':
            if intent.status != 'PAID' or intent.unit_id != unit.id or intent.invoice_id != invoice.id:
                raise AppError('ERR-REFUND-SOURCE', 'Cần giao dịch VNPay đã xác nhận của hóa đơn này.', 409)
            from app.services.financial_control import guard_payment_decisions
            guard_payment_decisions(session,intent.payment_id,provider=True)
            if body.amount_vnd > max(0, -_balance(session, account)):
                raise AppError('ERR-REFUND-BALANCE', 'Chưa có số dư có sau điều chỉnh/tiền thừa để hoàn.', 409)
        row = PortalFinancialAdjustment(**scope_values(context, unit), **body.model_dump(exclude={'unit_id'}), requested_by_id=context.account_id)
        session.add(row)
        return row, 'finance'
    return command(request, context, key, 'adjustment.create', body.model_dump(mode='json'), execute, roles=FINANCE)


@router.post('/adjustments/{identifier}/actions')
def adjustment_action(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias='Idempotency-Key')):
    def execute(session):
        context.assert_role(*FINANCE)
        row = scoped(session, context, PortalFinancialAdjustment, identifier, 'finance', lock=True, roles=FINANCE)
        require_version(row.version, body.expected_version)
        if body.action == 'REJECT' and row.status == 'REQUESTED':
            row.status = 'REJECTED'; row.version += 1
            return row, 'finance'
        releasing = body.action == 'RELEASE_REFUND' and row.kind == 'REFUND' and row.status == 'RECONCILIATION' and row.provider_status == '09'
        if body.action == 'RELEASE_REFUND' and not releasing:
            raise AppError('ERR-REFUND-UNCERTAIN', 'Chỉ giải tỏa khi kết quả ký của VNPay xác nhận hoàn tiền bị từ chối (09).', 409)
        if not releasing and (body.action != 'APPROVE' or row.status != 'REQUESTED'):
            raise AppError('ERR-STATE-TRANSITION', 'Chứng từ không ở trạng thái chờ duyệt.', 409)
        if row.requested_by_id == context.account_id:
            raise AppError('ERR-MAKER-CHECKER', 'Người lập không tự duyệt chứng từ.', 403)
        from types import SimpleNamespace
        from app.services.financial_control import check_approver
        check_approver(session,context,SimpleNamespace(account_id=row.requested_by_id,tenant_id=row.tenant_id,
            site_id=row.site_id,building_id=row.building_id), 'CREDIT' if row.kind=='CREDIT' else 'PAYMENT_REFUND',row.amount_vnd)
        intent = scoped(session, context, PortalPaymentIntent, row.payment_intent_id, 'finance', lock=True, roles=FINANCE) if row.kind == 'REFUND' else None
        try:
            period_id = UUID(str(body.data.get('period_id')))
        except ValueError:
            raise AppError('ERR-ACCOUNTING-PERIOD', 'Cần chọn kỳ kế toán.', 422) from None
        period = session.scalar(select(AccountingPeriod).where(AccountingPeriod.id == period_id,
            *context.scope_conditions(AccountingPeriod), AccountingPeriod.building_id == row.building_id).with_for_update())
        if period is None or period.status != 'OPEN':
            raise AppError('ERR-ACCOUNTING-PERIOD-CLOSED', 'Điều chỉnh cần kỳ OPEN cùng tòa.', 409)
        account = session.scalar(select(BillingAccount).where(BillingAccount.unit_id == row.unit_id, *context.scope_conditions(BillingAccount)).with_for_update())
        invoice = session.scalar(select(BillingInvoice).where(BillingInvoice.id == row.invoice_id).with_for_update())
        if invoice is None or account is None:
            raise scope_not_found()
        if releasing:
            debit, credit, entry = 0, row.amount_vnd, 'CREDIT_ISSUED'
            row.status = 'REJECTED'
        elif row.kind == 'CREDIT':
            credited = session.scalar(select(func.coalesce(func.sum(PortalFinancialAdjustment.amount_vnd), 0)).where(
                PortalFinancialAdjustment.invoice_id == invoice.id, PortalFinancialAdjustment.kind == 'CREDIT', PortalFinancialAdjustment.status == 'COMPLETED')) or 0
            from app.models.financial_control import FinanceCommand
            credited += session.scalar(select(func.coalesce(func.sum(FinanceCommand.amount_vnd),0)).where(
                FinanceCommand.target_id==invoice.id,FinanceCommand.kind.in_(('CREDIT','WRITE_OFF')),FinanceCommand.status=='EXECUTED')) or 0
            if invoice.status == 'VOID' or credited + row.amount_vnd > invoice.total_vnd:
                raise AppError('ERR-ADJUSTMENT-AMOUNT', 'Tổng điều chỉnh vượt giá trị hóa đơn.', 409)
            invoice.outstanding_vnd = max(0, invoice.outstanding_vnd - row.amount_vnd)
            invoice.status = 'PAID' if invoice.outstanding_vnd == 0 else 'PARTIALLY_PAID'; invoice.version += 1
            debit, credit, entry = 0, row.amount_vnd, 'CREDIT_ISSUED'
            row.status = 'COMPLETED'; row.completed_at = utc_now()
        else:
            if intent.status != 'PAID' or intent.invoice_id != row.invoice_id or intent.unit_id != row.unit_id:
                raise AppError('ERR-REFUND-SOURCE', 'Giao dịch nguồn không còn hợp lệ.', 409)
            from app.services.financial_control import guard_payment_decisions
            guard_payment_decisions(session,intent.payment_id,provider=True)
            if session.scalar(select(PortalFinancialAdjustment.id).where(
                    PortalFinancialAdjustment.payment_intent_id == intent.id, PortalFinancialAdjustment.id != row.id,
                    PortalFinancialAdjustment.kind == 'REFUND', PortalFinancialAdjustment.provider_request_id.is_not(None)).limit(1)):
                raise AppError('ERR-REFUND-EXISTING', 'Giao dịch này đã gửi một yêu cầu hoàn. Cần đối soát với VNPay trước khi lập lần tiếp theo.', 409)
            reserved = session.scalar(select(func.coalesce(func.sum(PortalFinancialAdjustment.amount_vnd), 0)).where(
                PortalFinancialAdjustment.payment_intent_id == intent.id, PortalFinancialAdjustment.kind == 'REFUND',
                PortalFinancialAdjustment.status.in_(('APPROVED', 'SENDING', 'RECONCILIATION', 'COMPLETED')))) or 0
            if row.amount_vnd > max(0, -_balance(session, account)) or reserved + row.amount_vnd > (intent.provider_amount_vnd or 0):
                raise AppError('ERR-REFUND-BALANCE', 'Số dư có/giao dịch nguồn không đủ để hoàn.', 409)
            # Convert AR credit into the tracked refund payable, before any provider call.
            debit, credit, entry = row.amount_vnd, 0, 'CREDIT_APPLIED'; row.status = 'APPROVED'
        session.add(ArLedgerEntry(tenant_id=row.tenant_id, site_id=row.site_id, building_id=row.building_id,
            billing_account_id=account.id, accounting_period_id=period.id, entry_type=entry,
            source_type='PORTAL_ADJUSTMENT', source_id=row.id, debit_vnd=debit, credit_vnd=credit,
            effective_at=utc_now(), created_by_id=context.account_id))
        if not releasing:
            row.approved_by_id = context.account_id; row.period_id = period.id
        row.version += 1
        return row, 'finance'
    return command(request, context, key, f'adjustment.{body.action.lower()}', {'id': str(identifier), **body.model_dump(mode='json')}, execute, roles=FINANCE)


@router.post('/adjustments/{identifier}/provider')
def refund_provider(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context)):
    settings = request.app.state.settings
    vnpay.require_configuration(settings, context.tenant_id)
    with request.app.state.database.get_session() as session:
        context.assert_role(*FINANCE)
        row = scoped(session, context, PortalFinancialAdjustment, identifier, 'finance', lock=True, roles=FINANCE)
        if row.kind != 'REFUND':
            raise AppError('ERR-STATE-TRANSITION', 'Chỉ gửi chứng từ hoàn tiền.', 409)
        if body.action == 'SEND' and row.status != 'APPROVED':
            return view(row)  # Never repeat an irreversible call after lost response.
        require_version(row.version, body.expected_version)
        if body.action not in {'SEND', 'CHECK'} or (body.action == 'CHECK' and row.status not in {'SENDING', 'RECONCILIATION'}):
            raise AppError('ERR-STATE-TRANSITION', 'Không có chứng từ cần gửi/đối soát.', 409)
        intent = scoped(session, context, PortalPaymentIntent, row.payment_intent_id, 'finance', roles=FINANCE)
        if body.action == 'SEND':
            row.status = 'SENDING'; row.provider_request_id = uuid4().hex; row.provider_requested_at = utc_now(); row.version += 1
            session.commit()
        payload = vnpay.transaction_request(intent, settings, row.provider_request_id if body.action == 'SEND' else uuid4().hex,
            refund=row.amount_vnd if body.action == 'SEND' else None, created_by=context.username,
            created_at=row.provider_requested_at if body.action == 'SEND' else None)
        try:
            result = vnpay.call_transaction(settings, payload)
            session.refresh(row, with_for_update=True)
            if row.status in {'COMPLETED', 'REJECTED'}:
                return view(row)
            expected_command = 'refund' if body.action == 'SEND' else 'querydr'
            if (not vnpay.verify_transaction_response(result, settings, intent, expected_command)
                    or result.get('vnp_Amount') != str(row.amount_vnd * 100)
                    or result.get('vnp_TransactionType') not in {'02', '03'}):
                raise AppError('ERR-PAYMENT-SIGNATURE', 'Kết quả hoàn tiền không khớp.', 502)
            row.provider_status = str(result.get('vnp_TransactionStatus', '99'))[:20]
            row.provider_transaction = str(result.get('vnp_TransactionNo', ''))[:100]
            if result.get('vnp_ResponseCode') == '00' and row.provider_status == '00' and row.provider_transaction:
                row.status = 'COMPLETED'; row.completed_at = utc_now()
            else:
                row.status = 'RECONCILIATION'
        except AppError:
            session.refresh(row, with_for_update=True)
            if row.status in {'COMPLETED', 'REJECTED'}:
                return view(row)
            row.status = 'RECONCILIATION'
        row.version += 1
        audit(session, context, request, event_type='VnpayRefundUpdated', action=body.action.lower(), resource_type='PortalFinancialAdjustment',
            resource_id=row.id, building_id=row.building_id, after={'status': row.status, 'version': row.version}, reason=body.reason)
        session.commit()
        return view(row)
