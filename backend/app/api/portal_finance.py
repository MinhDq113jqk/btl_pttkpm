from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError
from app.core.policy import UserContext, context_for_account, get_current_user_context, scope_not_found
from app.models.account import Account
from app.models.billing import AccountingPeriod, BillingAccount, BillingInvoice, BillingInvoiceItem, Payment
from app.models.resident_portal import PortalFeeSource, PortalFeeInterval, PortalFeePosting, PortalPaymentIntent
from app.schemas.resident_portal import IntentInput, FeePostInput, PortalAction
from app.services.billing import allocate_payment, receive_payment_command
from app.services.portal_finance import post_fee_source, fee_calculation, calculation_hash
from app.services.r2 import audit, require_version, utc_now
from app.services.resident_portal import FINANCE, command, scope_values, scoped, unit_for, view, visible_conditions
from app.services import vnpay

router = APIRouter(prefix="/portal", tags=["Resident portal finance"])


@router.get("/fee-sources")
def fee_sources(request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        conditions = list(visible_conditions(context, PortalFeeSource, "finance", roles=FINANCE))
        if unit_id:
            unit_for(session, context, unit_id, "finance", roles=FINANCE)
            conditions.append(PortalFeeSource.unit_id == unit_id)
        rows = session.scalars(select(PortalFeeSource).where(*conditions).order_by(PortalFeeSource.created_at.desc()).limit(200)).all()
        return {"items": [{**view(row), "intervals": [view(interval) for interval in session.scalars(select(PortalFeeInterval)
            .where(PortalFeeInterval.fee_source_id == row.id).order_by(PortalFeeInterval.starts_on, PortalFeeInterval.created_at, PortalFeeInterval.id))],
            "postings": [view(p) for p in session.scalars(select(PortalFeePosting)
            .where(PortalFeePosting.fee_source_id == row.id))]} for row in rows]}


@router.get("/fee-sources/{identifier}/preview")
def preview_fee(identifier: UUID, period_id: UUID, request: Request, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        initial = scoped(session, context, PortalFeeSource, identifier, "finance", roles=FINANCE)
        period = session.scalar(select(AccountingPeriod).where(AccountingPeriod.id == period_id,
            *context.scope_conditions(AccountingPeriod), AccountingPeriod.building_id == initial.building_id).with_for_update())
        if period is None:
            raise scope_not_found()
        # Match building billing runs: period precedes unit/account locks.
        unit_for(session, context, initial.unit_id, "finance", roles=FINANCE)
        source = scoped(session, context, PortalFeeSource, identifier, "finance", lock=True, roles=FINANCE)
        posting = session.scalar(select(PortalFeePosting).where(PortalFeePosting.fee_source_id == source.id,
            PortalFeePosting.period_id == period.id))
        if posting:
            line = session.scalar(select(BillingInvoiceItem).where(BillingInvoiceItem.billing_invoice_id == posting.invoice_id).limit(1))
            snapshot = line.calculation_snapshot or {"method": "LEGACY", "amount_vnd": line.amount_vnd, "segments": []}
        else:
            snapshot = fee_calculation(session, source, period)
        return {"source_version": source.version, "calculation": snapshot,
            "calculation_hash": calculation_hash(source, period, snapshot),
            "posted_invoice_id": str(posting.invoice_id) if posting else None}


@router.post("/fee-sources/{identifier}/post")
def post_fee(identifier: UUID, body: FeePostInput, request: Request, context: UserContext = Depends(get_current_user_context),
             key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role(*FINANCE)
        initial = scoped(session, context, PortalFeeSource, identifier, "finance", roles=FINANCE)
        period = session.scalar(select(AccountingPeriod).where(AccountingPeriod.id == body.period_id,
            *context.scope_conditions(AccountingPeriod), AccountingPeriod.building_id == initial.building_id).with_for_update())
        if period is None:
            raise scope_not_found()
        unit_for(session, context, initial.unit_id, "finance", roles=FINANCE)
        source = scoped(session, context, PortalFeeSource, identifier, "finance", lock=True, roles=FINANCE)
        require_version(source.version, body.expected_version)
        if period.status not in {'OPEN','CLOSING'}:
            raise AppError('ERR-ACCOUNTING-PERIOD-CLOSED','Kỳ không nhận bản tính mới.',409)
        from app.services.financial_control import prepare_source_review
        review = prepare_source_review(session, source, period, context.account_id, body.calculation_hash)
        return review, "finance"
    return command(request, context, key, "fee-source.post", {"id": str(identifier), **body.model_dump(mode="json")}, execute, roles=FINANCE)


@router.get("/invoices")
def invoices(request: Request, unit_id: UUID, context: UserContext = Depends(get_current_user_context)):
    with request.app.state.database.get_session() as session:
        unit_for(session, context, unit_id, "finance", roles=FINANCE)
        rows = session.scalars(select(BillingInvoice).join(BillingAccount,
            BillingAccount.id == BillingInvoice.billing_account_id).where(
                *context.scope_conditions(BillingInvoice), BillingAccount.unit_id == unit_id,
                BillingInvoice.status != "DRAFT").order_by(BillingInvoice.created_at.desc()).limit(200)).all()
        return {"items": [{**view(row), "items": [view(item) for item in session.scalars(select(BillingInvoiceItem)
            .where(BillingInvoiceItem.billing_invoice_id == row.id).order_by(BillingInvoiceItem.line_number))]} for row in rows]}


@router.get("/payment-intents")
def payment_intents(request: Request, unit_id: UUID | None = None, context: UserContext = Depends(get_current_user_context)):
    configured = True
    try:
        vnpay.require_configuration(request.app.state.settings, context.tenant_id)
    except AppError:
        configured = False
    with request.app.state.database.get_session() as session:
        conditions = list(visible_conditions(context, PortalPaymentIntent, "finance", roles=FINANCE))
        if unit_id:
            unit_for(session, context, unit_id, "finance", roles=FINANCE)
            conditions.append(PortalPaymentIntent.unit_id == unit_id)
        return {"items": [view(row) for row in session.scalars(select(PortalPaymentIntent).where(*conditions)
            .order_by(PortalPaymentIntent.created_at.desc()).limit(200))],
            "provider": "VNPAY", "configured": configured}


@router.post("/payment-intents", status_code=201)
def create_intent(body: IntentInput, request: Request, context: UserContext = Depends(get_current_user_context),
                  key: str = Header(..., alias="Idempotency-Key")):
    settings = request.app.state.settings
    vnpay.require_configuration(settings, context.tenant_id)
    def execute(session):
        context.assert_role("resident")
        unit = unit_for(session, context, body.unit_id, "finance")
        account = session.scalar(select(BillingAccount).where(BillingAccount.unit_id == unit.id,
            *context.scope_conditions(BillingAccount)).with_for_update())
        invoice = session.scalar(select(BillingInvoice).where(BillingInvoice.id == body.invoice_id,
            *context.scope_conditions(BillingInvoice), BillingInvoice.billing_account_id == (account.id if account else None)).with_for_update())
        if invoice is None:
            raise scope_not_found()
        if invoice.status not in {"ISSUED", "PARTIALLY_PAID"} or invoice.outstanding_vnd <= 0:
            raise AppError("ERR-PAYMENT-INVOICE", "Hóa đơn không còn số tiền phải thanh toán.", 409)
        if invoice.outstanding_vnd > 9999999999:
            raise AppError("ERR-PAYMENT-AMOUNT", "Số tiền vượt giới hạn giao thức VNPay.", 422)
        service_account = session.get(Account, settings.vnpay_service_account_id)
        if not service_account or not service_account.is_active or service_account.tenant_id != context.tenant_id:
            raise AppError("ERR-PAYMENT-NOT-CONFIGURED", "Tài khoản dịch vụ VNPay chưa sẵn sàng.", 503)
        context_for_account(session, service_account, context.assert_active_site()).assert_building_role(unit.building_id, *FINANCE)
        pending = session.scalar(select(PortalPaymentIntent).where(PortalPaymentIntent.invoice_id == invoice.id,
            PortalPaymentIntent.account_id == context.account_id, PortalPaymentIntent.status == "PENDING",
            PortalPaymentIntent.expires_at > utc_now(), PortalPaymentIntent.amount_vnd == invoice.outstanding_vnd).limit(1))
        if pending:
            return pending, "finance"
        row = PortalPaymentIntent(**scope_values(context, unit), invoice_id=invoice.id,
            reference=uuid4().hex, amount_vnd=invoice.outstanding_vnd,
            expires_at=utc_now() + timedelta(seconds=settings.vnpay_intent_ttl_seconds))
        session.add(row)
        return row, "finance"
    result = command(request, context, key, "payment-intent.create", body.model_dump(mode="json"), execute, roles=FINANCE)
    with request.app.state.database.get_session() as session:
        row = scoped(session, context, PortalPaymentIntent, UUID(str(result["id"])), "finance", roles=FINANCE)
        return {**result, "payment_url": vnpay.payment_url(row, settings, request.client.host if request.client else "127.0.0.1")}


def _settle(session, intent, settings, *, period_id=None, actor_context=None):
    actor = session.scalar(select(Account).where(Account.id == settings.vnpay_service_account_id,
        Account.tenant_id == intent.tenant_id, Account.is_active.is_(True)))
    if actor is None:
        raise AppError("ERR-PAYMENT-NOT-CONFIGURED", "Thiếu tài khoản dịch vụ VNPay.", 503)
    context = actor_context or context_for_account(session, actor, intent.site_id)
    context.assert_building_role(intent.building_id, *FINANCE)
    account = session.scalar(select(BillingAccount).where(BillingAccount.unit_id == intent.unit_id,
        BillingAccount.tenant_id == intent.tenant_id, BillingAccount.site_id == intent.site_id))
    if account is None:
        raise scope_not_found()
    clauses = [AccountingPeriod.tenant_id == intent.tenant_id, AccountingPeriod.site_id == intent.site_id,
        AccountingPeriod.building_id == intent.building_id, AccountingPeriod.status.in_(("OPEN", "CLOSING"))]
    if period_id:
        clauses.append(AccountingPeriod.id == period_id)
    else:
        clauses.extend((AccountingPeriod.period_start <= intent.provider_received_at.date(),
                        AccountingPeriod.period_end >= intent.provider_received_at.date()))
    periods = session.scalars(select(AccountingPeriod).where(*clauses).with_for_update()).all()
    if len(periods) != 1:
        raise AppError("ERR-PAYMENT-PERIOD", "Cần đối soát kỳ kế toán nhận tiền.", 409)
    session.refresh(account, with_for_update=True)
    payment = receive_payment_command(session, tenant_id=intent.tenant_id, site_id=intent.site_id,
        building_id=intent.building_id, period=periods[0], account=account, payment_source="GATEWAY",
        source_reference="VNPAY:" + intent.provider_transaction, receipt_number="VP-" + intent.provider_transaction,
        amount_vnd=intent.provider_amount_vnd, received_at=intent.provider_received_at, actor_id=context.account_id)
    allocate_payment(session, payment, context.account_id, preferred_invoice_id=intent.invoice_id)
    intent.payment_id = payment.id; intent.status = "PAID"; intent.version += 1
    return context


@router.get("/payments/vnpay/ipn", include_in_schema=True)
def vnpay_ipn(request: Request):
    settings = request.app.state.settings
    pairs = list(request.query_params.multi_items())
    parameters = dict(pairs)
    if (len(parameters) != len(pairs) or not settings.vnpay_enabled or not settings.vnpay_hash_secret
            or parameters.get("vnp_TmnCode") != settings.vnpay_tmn_code
            or not vnpay.verify(parameters, settings.vnpay_hash_secret.get_secret_value())):
        return {"RspCode": "97", "Message": "Invalid signature"}
    try:
        with request.app.state.database.get_session() as session:
            row = session.scalar(select(PortalPaymentIntent).where(
                PortalPaymentIntent.reference == parameters.get("vnp_TxnRef"),
                PortalPaymentIntent.tenant_id == settings.vnpay_tenant_id).with_for_update())
            if row is None:
                return {"RspCode": "01", "Message": "Order not found"}
            amount = parameters.get("vnp_Amount", "")
            if not amount.isdigit() or len(amount) > 12 or not 0 < int(amount) or int(amount) % 100:
                return {"RspCode": "04", "Message": "Invalid amount"}
            if row.status == "PAID":
                return {"RspCode": "02", "Message": "Already confirmed"} if int(amount) == row.amount_vnd * 100 else {"RspCode": "04", "Message": "Invalid amount"}
            success = parameters.get("vnp_ResponseCode") == "00" and parameters.get("vnp_TransactionStatus") == "00"
            row.provider_code = parameters.get("vnp_ResponseCode", "99")[:20]
            if not success:
                if row.status == "PENDING":
                    row.status = "FAILED"; row.version += 1
                session.commit()
                return {"RspCode": "00", "Message": "Confirmed"}
            transaction = parameters.get("vnp_TransactionNo", "")
            if not transaction.isdigit() or len(transaction) > 50:
                return {"RspCode": "99", "Message": "Invalid transaction"}
            received_at = vnpay.payment_time(parameters.get("vnp_PayDate"))
            if received_at > utc_now() + timedelta(minutes=5):
                return {"RspCode": "99", "Message": "Invalid transaction date"}
            if row.provider_transaction and row.provider_transaction != transaction:
                return {"RspCode": "99", "Message": "Transaction conflict"}
            if row.provider_amount_vnd is not None and row.provider_amount_vnd != int(amount) // 100:
                return {"RspCode": "99", "Message": "Transaction conflict"}
            row.provider_transaction = transaction; row.provider_received_at = received_at
            row.provider_amount_vnd = int(amount) // 100
            if row.provider_amount_vnd != row.amount_vnd:
                row.status = "RECONCILIATION"; row.version += 1; session.commit()
                return {"RspCode": "04", "Message": "Invalid amount"}
            try:
                with session.begin_nested():
                    actor = _settle(session, row, settings)
                    audit(session, actor, request, event_type="VnpayPaymentConfirmed", action="confirm",
                        resource_type="PortalPaymentIntent", resource_id=row.id, building_id=row.building_id,
                        after={"payment_id": str(row.payment_id), "amount_vnd": row.amount_vnd})
            except AppError:
                row.status = "RECONCILIATION"; row.version += 1
            session.commit()
            return {"RspCode": "00", "Message": "Confirmed"}
    except (AppError, IntegrityError):
        return {"RspCode": "99", "Message": "Unable to confirm"}


@router.get("/payments/vnpay/return")
def vnpay_return(request: Request):
    # An authenticated portal read determines the balance; Return is informational.
    settings = request.app.state.settings
    pairs = list(request.query_params.multi_items())
    parameters = dict(pairs)
    if (len(parameters) != len(pairs) or not settings.vnpay_enabled
            or parameters.get("vnp_TmnCode") != settings.vnpay_tmn_code
            or not settings.vnpay_hash_secret or not vnpay.verify(parameters, settings.vnpay_hash_secret.get_secret_value())):
        raise AppError("ERR-PAYMENT-SIGNATURE", "Kết quả thanh toán không hợp lệ.", 400)
    return RedirectResponse(settings.portal_public_url.rstrip("/") + "/#/resident-payment", status_code=303)


@router.post("/payment-intents/{identifier}/query")
def query_intent(identifier: UUID, body: PortalAction, request: Request, context: UserContext = Depends(get_current_user_context)):
    settings = request.app.state.settings
    vnpay.require_configuration(settings, context.tenant_id)
    with request.app.state.database.get_session() as session:
        row = scoped(session, context, PortalPaymentIntent, identifier, "finance", lock=True, roles=FINANCE)
        require_version(row.version, body.expected_version)
        if row.status == "PAID":
            return view(row)
        result = vnpay.call_transaction(settings, vnpay.transaction_request(row, settings, uuid4().hex))
        if not vnpay.verify_transaction_response(result, settings, row, "querydr"):
            raise AppError("ERR-PAYMENT-SIGNATURE", "Kết quả truy vấn VNPay không hợp lệ.", 502)
        amount = str(result.get("vnp_Amount", ""))
        if (result.get("vnp_ResponseCode") != "00" or result.get("vnp_TransactionStatus") != "00"
                or result.get("vnp_TransactionType") != "01"):
            return {**view(row), "query_status": "NOT_CONFIRMED"}
        if not amount.isdigit() or len(amount) > 12 or int(amount) <= 0 or int(amount) % 100:
            raise AppError("ERR-PAYMENT-AMOUNT", "Số tiền truy vấn không hợp lệ.", 502)
        transaction = str(result.get("vnp_TransactionNo", ""))
        if not transaction.isdigit() or len(transaction) > 15 or (row.provider_transaction and row.provider_transaction != transaction):
            raise AppError("ERR-PAYMENT-RECONCILIATION", "Giao dịch truy vấn không khớp.", 409)
        row.provider_transaction = transaction; row.provider_amount_vnd = int(amount) // 100
        row.provider_received_at = vnpay.payment_time(result.get("vnp_PayDate"))
        if row.provider_received_at > utc_now() + timedelta(minutes=5):
            raise AppError("ERR-PAYMENT-DATE", "Ngày giao dịch không hợp lệ.", 502)
        row.provider_code = "00"
        if row.provider_amount_vnd != row.amount_vnd:
            row.status = "RECONCILIATION"; row.version += 1
        else:
            try:
                with session.begin_nested():
                    _settle(session, row, settings)
            except AppError:
                row.status = "RECONCILIATION"; row.version += 1
        audit(session, context, request, event_type="VnpayPaymentQueried", action="query", resource_type="PortalPaymentIntent",
            resource_id=row.id, building_id=row.building_id, after={"status": row.status}, reason=body.reason)
        session.commit()
        return view(row)


@router.post("/payment-intents/{identifier}/reconcile")
def reconcile(identifier: UUID, body: PortalAction, request: Request,
              context: UserContext = Depends(get_current_user_context), key: str = Header(..., alias="Idempotency-Key")):
    def execute(session):
        context.assert_role(*FINANCE)
        row = scoped(session, context, PortalPaymentIntent, identifier, "finance", lock=True, roles=FINANCE)
        require_version(row.version, body.expected_version)
        if row.status != "RECONCILIATION" or not row.provider_transaction or not row.provider_received_at or not row.provider_amount_vnd:
            raise AppError("ERR-STATE-TRANSITION", "Không có xác nhận tiền hợp lệ để đối soát.", 409)
        try:
            period = UUID(str(body.data.get("period_id")))
        except ValueError:
            raise AppError("ERR-PAYMENT-PERIOD", "Cần chọn kỳ nhận tiền.", 422) from None
        _settle(session, row, request.app.state.settings, period_id=period, actor_context=context)
        return row, "finance"
    return command(request, context, key, "payment.reconcile", {"id": str(identifier), **body.model_dump(mode="json")}, execute, roles=FINANCE)
