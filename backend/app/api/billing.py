from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.billing import (
    AccountingPeriod,
    ArLedgerEntry,
    BillingAccount,
    BillingInvoice,
    BillingInvoiceItem,
    BillingRun,
    FeePolicy,
    FeePolicyVersion,
    OverpaymentCredit,
    Payment,
    PaymentAllocation,
    UnmatchedPayment,
)
from app.schemas.r4 import (
    AccountingPeriodCreate,
    AccountingPeriodListResponse,
    AccountingPeriodTransition,
    AccountingPeriodView,
    BillingAccountListResponse,
    BillingAccountView,
    BillingInvoiceListResponse,
    BillingInvoiceView,
    BillingInvoiceVoid,
    BillingPaymentCreate,
    BillingPaymentListResponse,
    BillingPaymentView,
    BillingRunCreate,
    BillingRunListResponse,
    BillingRunView,
    FeePolicyCreate,
    FeePolicyListResponse,
    FeePolicyVersionCreate,
    FeePolicyVersionView,
    FeePolicyView,
    OverpaymentCreditListResponse,
    OverpaymentCreditView,
    PaymentAllocationResult,
    PaymentAllocationView,
    UnmatchedPaymentListResponse,
    UnmatchedPaymentMatch,
    UnmatchedPaymentView,
)
from app.services.billing import allocate_payment, execute_run, record_payment_received, void_invoice
from app.services.r2 import audit, emit, idempotency_replay, remember_idempotency, require_version


router = APIRouter(tags=["R4 billing foundation"])

BILLING_ROLES = frozenset({"admin", "director", "accountant"})
R4_PUBLIC_PERIOD_TRANSITIONS = {
    "OPEN": frozenset({"CLOSING"}),
    "CLOSING": frozenset({"OPEN", "CLOSED"}),
    # LOCKED/reopen needs maker-checker, approved posting scope, expiry and a
    # delta report. Those capabilities remain SPEC-ONLY, so this R4 command
    # surface must not expose the model's future-only transitions.
    "CLOSED": frozenset(),
    "LOCKED": frozenset(),
}


def _building_visibility_conditions(context: UserContext, model):
    context.assert_role(*BILLING_ROLES)
    grants = tuple(grant for grant in context.role_grants if grant.role in BILLING_ROLES)
    if any(grant.building_id is None for grant in grants):
        return ()
    building_ids = [grant.building_id for grant in grants if grant.building_id is not None]
    if not building_ids:
        raise scope_not_found()
    return (model.building_id.in_(building_ids),)


def _scoped_account(session, context: UserContext, billing_account_id: UUID, *, lock: bool = False) -> BillingAccount:
    statement = select(BillingAccount).where(
        BillingAccount.id == billing_account_id,
        *context.scope_conditions(BillingAccount),
        *_building_visibility_conditions(context, BillingAccount),
    )
    if lock:
        statement = statement.with_for_update()
    account = session.scalar(statement)
    if account is None:
        raise scope_not_found()
    return account


def _payment_view(payment: Payment) -> BillingPaymentView:
    return BillingPaymentView.model_validate(payment)


def _unmatched_payment_view(unmatched: UnmatchedPayment, payment: Payment) -> UnmatchedPaymentView:
    return UnmatchedPaymentView.model_validate({
        "id": unmatched.id,
        "payment_id": unmatched.payment_id,
        "building_id": unmatched.building_id,
        "amount_vnd": unmatched.amount_vnd,
        "reason": unmatched.reason,
        "status": unmatched.status,
        "source_reference": payment.source_reference,
        "receipt_number": payment.receipt_number,
        "received_at": payment.received_at,
        "created_at": unmatched.created_at,
        "version": unmatched.version,
    })


def _allocation_result(session, payment: Payment) -> PaymentAllocationResult:
    allocations = session.scalars(select(PaymentAllocation).join(
        BillingInvoice, BillingInvoice.id == PaymentAllocation.billing_invoice_id,
    ).where(
        PaymentAllocation.payment_id == payment.id,
    ).order_by(
        BillingInvoice.due_on.asc().nulls_last(),
        BillingInvoice.issued_on.asc().nulls_last(),
        BillingInvoice.invoice_number.asc(),
        BillingInvoice.id.asc(),
    )).all()
    credit = session.scalar(select(OverpaymentCredit).where(
        OverpaymentCredit.payment_id == payment.id,
    ))
    return PaymentAllocationResult(
        payment=_payment_view(payment),
        allocations=[PaymentAllocationView.model_validate(item) for item in allocations],
        overpayment_credit=OverpaymentCreditView.model_validate(credit) if credit is not None else None,
    )


def _scoped_record(session, context: UserContext, model, resource_id: UUID, *, lock: bool = False):
    statement = select(model).where(
        model.id == resource_id,
        *context.scope_conditions(model),
        *_building_visibility_conditions(context, model),
    )
    if lock:
        statement = statement.with_for_update()
    record = session.scalar(statement)
    if record is None:
        raise scope_not_found()
    return record


def _policy_view(session, policy: FeePolicy) -> FeePolicyView:
    versions = session.scalars(select(FeePolicyVersion).where(
        FeePolicyVersion.fee_policy_id == policy.id,
    ).order_by(FeePolicyVersion.version_number)).all()
    return FeePolicyView.model_validate({
        "id": policy.id,
        "building_id": policy.building_id,
        "code": policy.code,
        "name": policy.name,
        "is_active": policy.is_active,
        "versions": [FeePolicyVersionView.model_validate(version) for version in versions],
    })


def _invoice_view(session, invoice: BillingInvoice) -> BillingInvoiceView:
    items = session.scalars(select(BillingInvoiceItem).where(
        BillingInvoiceItem.billing_invoice_id == invoice.id,
    ).order_by(BillingInvoiceItem.line_number)).all()
    return BillingInvoiceView.model_validate({
        "id": invoice.id,
        "billing_account_id": invoice.billing_account_id,
        "billing_run_id": invoice.billing_run_id,
        "accounting_period_id": invoice.accounting_period_id,
        "building_id": invoice.building_id,
        "invoice_number": invoice.invoice_number,
        "issued_on": invoice.issued_on,
        "due_on": invoice.due_on,
        "status": invoice.status,
        "total_vnd": invoice.total_vnd,
        "outstanding_vnd": invoice.outstanding_vnd,
        "voided_at": invoice.voided_at,
        "void_reason": invoice.void_reason,
        "version": invoice.version,
        "items": items,
    })


def _assert_publish_does_not_change_closing_period(session, policy: FeePolicy, effective_from) -> None:
    closing = session.scalar(select(AccountingPeriod.id).where(
        AccountingPeriod.building_id == policy.building_id,
        AccountingPeriod.status == "CLOSING",
        AccountingPeriod.period_end >= effective_from,
    ).limit(1))
    if closing is not None:
        raise AppError(
            "ERR-POLICY-EFFECTIVE-NEXT-PERIOD",
            "Kỳ đang CLOSING giữ nguyên snapshot; version mới chỉ được hiệu lực từ kỳ sau.",
            409,
        )


@router.get("/billing/accounts", response_model=BillingAccountListResponse)
def list_billing_accounts(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        accounts = session.scalars(select(BillingAccount).where(
            *current_user.scope_conditions(BillingAccount),
            *_building_visibility_conditions(current_user, BillingAccount),
        ).order_by(BillingAccount.account_number, BillingAccount.id)).all()
        return BillingAccountListResponse(
            items=[BillingAccountView.model_validate(account) for account in accounts],
        )


@router.get("/billing/accounts/{billing_account_id}", response_model=BillingAccountView)
def get_billing_account(
    request: Request,
    billing_account_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        return BillingAccountView.model_validate(_scoped_account(session, current_user, billing_account_id))


@router.post("/billing/payments", response_model=BillingPaymentView, status_code=201)
def receive_payment(
    request: Request,
    body: BillingPaymentCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(
            session,
            current_user,
            operation="billing-payment.receive",
            key=idempotency_key,
            payload=payload,
        )
        if replay is not None:
            payment = session.scalar(select(Payment).where(
                Payment.id == replay.resource_id,
                *current_user.scope_conditions(Payment),
                *_building_visibility_conditions(current_user, Payment),
            ))
            if payment is None:
                raise scope_not_found()
            return _payment_view(payment)

        account = None
        if body.billing_account_id is not None:
            account = _scoped_account(session, current_user, body.billing_account_id, lock=True)
            if account.status != "ACTIVE":
                raise AppError("ERR-BILLING-ACCOUNT-INACTIVE", "Tài khoản thu phí không còn hoạt động.", 409)
            building_id = account.building_id
        else:
            building_id = body.building_id
            current_user.assert_building_role(building_id, *BILLING_ROLES)
        period = session.scalar(select(AccountingPeriod).where(
            AccountingPeriod.id == body.accounting_period_id,
            *current_user.scope_conditions(AccountingPeriod),
            AccountingPeriod.building_id == building_id,
        ).with_for_update())
        if period is None:
            raise scope_not_found()
        if period.status not in {"OPEN", "CLOSING"}:
            raise AppError("ERR-ACCOUNTING-PERIOD-CLOSED", "Kỳ kế toán không nhận giao dịch mới.", 409)

        duplicate = session.scalar(select(Payment.id).where(
            *current_user.scope_conditions(Payment),
            or_(
                and_(Payment.payment_source == body.payment_source,
                     Payment.source_reference == body.source_reference),
                Payment.receipt_number == body.receipt_number,
            ),
        ).limit(1))
        if duplicate is not None:
            raise AppError("ERR-DUPLICATE-PAYMENT", "Nguồn thanh toán hoặc biên lai đã tồn tại.", 409)

        payment = Payment(
            tenant_id=current_user.tenant_id,
            site_id=current_user.assert_active_site(),
            building_id=building_id,
            billing_account_id=account.id if account is not None else None,
            accounting_period_id=period.id,
            payment_source=body.payment_source,
            source_reference=body.source_reference,
            receipt_number=body.receipt_number,
            amount_vnd=body.amount_vnd,
            received_at=body.received_at,
            received_by_id=current_user.account_id,
            status="RECEIVED" if account is not None else "UNMATCHED",
        )
        session.add(payment)
        session.flush()
        if account is not None:
            record_payment_received(session, payment, current_user.account_id)
        else:
            session.add(UnmatchedPayment(
                tenant_id=payment.tenant_id,
                site_id=payment.site_id,
                building_id=payment.building_id,
                payment_id=payment.id,
                amount_vnd=payment.amount_vnd,
                reason="Thiếu mã Billing Account khi nhận thanh toán.",
            ))
        audit(
            session,
            current_user,
            request,
            event_type="PaymentReceived" if account is not None else "PaymentUnmatched",
            action="create",
            resource_type="Payment",
            resource_id=payment.id,
            building_id=payment.building_id,
            after={"amount_vnd": payment.amount_vnd, "receipt_number": payment.receipt_number, "status": payment.status},
        )
        emit(
            session,
            current_user,
            request,
            event_type="PaymentReceived" if account is not None else "PaymentUnmatched",
            resource_type="Payment",
            resource_id=payment.id,
            payload={"billing_account_id": str(payment.billing_account_id) if payment.billing_account_id else None,
                     "amount_vnd": payment.amount_vnd},
        )
        remember_idempotency(
            session,
            current_user,
            operation="billing-payment.receive",
            key=idempotency_key,
            payload=payload,
            resource_type="Payment",
            resource_id=payment.id,
            response_status=201,
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            duplicate = session.scalar(select(Payment.id).where(
                *current_user.scope_conditions(Payment),
                or_(
                    and_(Payment.payment_source == body.payment_source,
                         Payment.source_reference == body.source_reference),
                    Payment.receipt_number == body.receipt_number,
                ),
            ).limit(1))
            if duplicate is not None:
                raise AppError("ERR-DUPLICATE-PAYMENT", "Nguồn thanh toán hoặc biên lai đã tồn tại.", 409) from None
            raise
        return _payment_view(payment)


@router.get("/billing/payments", response_model=BillingPaymentListResponse)
def list_payments(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        payments = session.scalars(select(Payment).where(
            *current_user.scope_conditions(Payment),
            *_building_visibility_conditions(current_user, Payment),
        ).order_by(Payment.received_at.desc(), Payment.id)).all()
        return BillingPaymentListResponse(items=[_payment_view(payment) for payment in payments])


@router.get("/billing/unmatched-payments", response_model=UnmatchedPaymentListResponse)
def list_unmatched_payments(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        rows = session.execute(select(UnmatchedPayment, Payment).join(
            Payment, Payment.id == UnmatchedPayment.payment_id,
        ).where(
            *current_user.scope_conditions(UnmatchedPayment),
            *_building_visibility_conditions(current_user, UnmatchedPayment),
        ).order_by(UnmatchedPayment.created_at.desc(), UnmatchedPayment.id)).all()
        return UnmatchedPaymentListResponse(items=[
            _unmatched_payment_view(unmatched, payment) for unmatched, payment in rows
        ])


@router.post("/billing/unmatched-payments/{unmatched_payment_id}/match", response_model=BillingPaymentView)
def match_unmatched_payment(
    request: Request,
    unmatched_payment_id: UUID,
    body: UnmatchedPaymentMatch,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"unmatched_payment_id": str(unmatched_payment_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="billing-payment.match-unmatched",
                                    key=idempotency_key, payload=payload)
        if replay is not None:
            return _payment_view(_scoped_record(session, current_user, Payment, replay.resource_id))
        unmatched = _scoped_record(session, current_user, UnmatchedPayment, unmatched_payment_id, lock=True)
        if unmatched.status != "OPEN":
            raise AppError("ERR-STATE-TRANSITION", "Payment unmatched này không còn chờ match.", 409)
        payment = _scoped_record(session, current_user, Payment, unmatched.payment_id, lock=True)
        if payment.status != "UNMATCHED" or payment.billing_account_id is not None:
            raise AppError("ERR-PAYMENT-INTEGRITY", "Payment unmatched không nhất quán.", 409)
        account = _scoped_account(session, current_user, body.billing_account_id, lock=True)
        if account.status != "ACTIVE" or account.building_id != payment.building_id:
            raise scope_not_found()
        period = _scoped_record(session, current_user, AccountingPeriod, payment.accounting_period_id, lock=True)
        if period.building_id != payment.building_id:
            raise scope_not_found()
        if period.status not in {"OPEN", "CLOSING"}:
            raise AppError("ERR-ACCOUNTING-PERIOD-CLOSED", "Kỳ kế toán không nhận giao dịch mới.", 409)
        payment.billing_account_id = account.id
        payment.status = "RECEIVED"
        payment.version += 1
        unmatched.status = "RESOLVED"
        unmatched.version += 1
        record_payment_received(session, payment, current_user.account_id)
        audit(session, current_user, request, event_type="PaymentMatched", action="match",
              resource_type="UnmatchedPayment", resource_id=unmatched.id, building_id=payment.building_id,
              before={"status": "OPEN"}, after={"status": "RESOLVED", "billing_account_id": str(account.id)})
        emit(session, current_user, request, event_type="PaymentMatched", resource_type="Payment",
             resource_id=payment.id, payload={"unmatched_payment_id": str(unmatched.id)})
        remember_idempotency(session, current_user, operation="billing-payment.match-unmatched", key=idempotency_key,
                             payload=payload, resource_type="Payment", resource_id=payment.id, response_status=200)
        session.commit()
        return _payment_view(payment)


@router.post("/billing/payments/{payment_id}/allocate", response_model=PaymentAllocationResult)
def allocate_received_payment(
    request: Request,
    payment_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = {"payment_id": str(payment_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="billing-payment.allocate",
                                    key=idempotency_key, payload=payload)
        if replay is not None:
            return _allocation_result(session, _scoped_record(session, current_user, Payment, replay.resource_id))
        payment = _scoped_record(session, current_user, Payment, payment_id, lock=True)
        allocations, credit = allocate_payment(session, payment, current_user.account_id)
        audit(session, current_user, request, event_type="PaymentAllocated", action="allocate",
              resource_type="Payment", resource_id=payment.id, building_id=payment.building_id,
              after={"status": payment.status, "allocated_vnd": sum(item.amount_vnd for item in allocations)})
        emit(session, current_user, request, event_type="PaymentAllocated", resource_type="Payment",
             resource_id=payment.id, payload={"status": payment.status, "allocation_count": len(allocations)})
        if credit is not None:
            audit(session, current_user, request, event_type="OverpaymentCreditIssued", action="create",
                  resource_type="OverpaymentCredit", resource_id=credit.id, building_id=credit.building_id,
                  after={"original_vnd": credit.original_vnd, "payment_id": str(payment.id)})
            emit(session, current_user, request, event_type="OverpaymentCreditIssued", resource_type="OverpaymentCredit",
                 resource_id=credit.id, payload={"original_vnd": credit.original_vnd})
        remember_idempotency(session, current_user, operation="billing-payment.allocate", key=idempotency_key,
                             payload=payload, resource_type="Payment", resource_id=payment.id, response_status=200)
        session.commit()
        return _allocation_result(session, payment)


@router.get("/billing/overpayment-credits", response_model=OverpaymentCreditListResponse)
def list_overpayment_credits(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        credits = session.scalars(select(OverpaymentCredit).where(
            *current_user.scope_conditions(OverpaymentCredit),
            *_building_visibility_conditions(current_user, OverpaymentCredit),
        ).order_by(OverpaymentCredit.created_at.desc(), OverpaymentCredit.id)).all()
        return OverpaymentCreditListResponse(items=[OverpaymentCreditView.model_validate(credit) for credit in credits])


@router.get("/billing/fee-policies", response_model=FeePolicyListResponse)
def list_fee_policies(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        policies = session.scalars(select(FeePolicy).where(
            *current_user.scope_conditions(FeePolicy),
            *_building_visibility_conditions(current_user, FeePolicy),
        ).order_by(FeePolicy.code, FeePolicy.id)).all()
        return FeePolicyListResponse(items=[_policy_view(session, policy) for policy in policies])


@router.post("/billing/fee-policies", response_model=FeePolicyView, status_code=201)
def create_fee_policy(
    request: Request,
    body: FeePolicyCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="billing-fee-policy.create",
                                    key=idempotency_key, payload=payload)
        if replay is not None:
            return _policy_view(session, _scoped_record(session, current_user, FeePolicy, replay.resource_id))
        current_user.assert_building_role(body.building_id, *BILLING_ROLES)
        policy = FeePolicy(
            tenant_id=current_user.tenant_id,
            site_id=current_user.assert_active_site(),
            building_id=body.building_id,
            code=body.code,
            name=body.name,
        )
        _assert_publish_does_not_change_closing_period(session, policy, body.effective_from)
        session.add(policy)
        session.flush()
        version = FeePolicyVersion(
            tenant_id=policy.tenant_id,
            site_id=policy.site_id,
            building_id=policy.building_id,
            fee_policy_id=policy.id,
            version_number=1,
            effective_from=body.effective_from,
            unit_rate_vnd=body.unit_rate_vnd,
            basis="UNIT_AREA_M2",
            rounding_unit_vnd=body.rounding_unit_vnd,
            published_at=datetime.now(UTC),
        )
        session.add(version)
        audit(session, current_user, request, event_type="FeePolicyVersionPublished", action="create",
              resource_type="FeePolicy", resource_id=policy.id, building_id=policy.building_id,
              after={"code": policy.code, "version": 1, "effective_from": str(version.effective_from)})
        emit(session, current_user, request, event_type="FeePolicyVersionPublished",
             resource_type="FeePolicy", resource_id=policy.id, payload={"version": 1})
        remember_idempotency(session, current_user, operation="billing-fee-policy.create", key=idempotency_key,
                             payload=payload, resource_type="FeePolicy", resource_id=policy.id,
                             response_status=201)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise AppError("ERR-DUPLICATE-FEE-POLICY", "Mã chính sách phí đã tồn tại trong tòa nhà.", 409) from None
        return _policy_view(session, policy)


@router.post("/billing/fee-policies/{fee_policy_id}/versions", response_model=FeePolicyVersionView, status_code=201)
def publish_fee_policy_version(
    request: Request,
    fee_policy_id: UUID,
    body: FeePolicyVersionCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json") | {"fee_policy_id": str(fee_policy_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="billing-fee-policy.publish",
                                    key=idempotency_key, payload=payload)
        if replay is not None:
            version = _scoped_record(session, current_user, FeePolicyVersion, replay.resource_id)
            return FeePolicyVersionView.model_validate(version)
        policy = _scoped_record(session, current_user, FeePolicy, fee_policy_id, lock=True)
        _assert_publish_does_not_change_closing_period(session, policy, body.effective_from)
        latest = session.scalar(select(func.max(FeePolicyVersion.version_number)).where(
            FeePolicyVersion.fee_policy_id == policy.id,
        )) or 0
        version = FeePolicyVersion(
            tenant_id=policy.tenant_id,
            site_id=policy.site_id,
            building_id=policy.building_id,
            fee_policy_id=policy.id,
            version_number=latest + 1,
            effective_from=body.effective_from,
            unit_rate_vnd=body.unit_rate_vnd,
            basis="UNIT_AREA_M2",
            rounding_unit_vnd=body.rounding_unit_vnd,
            published_at=datetime.now(UTC),
        )
        session.add(version)
        session.flush()
        audit(session, current_user, request, event_type="FeePolicyVersionPublished", action="publish",
              resource_type="FeePolicyVersion", resource_id=version.id, building_id=policy.building_id,
              after={"version": version.version_number, "effective_from": str(version.effective_from)})
        emit(session, current_user, request, event_type="FeePolicyVersionPublished",
             resource_type="FeePolicyVersion", resource_id=version.id,
             payload={"fee_policy_id": str(policy.id), "version": version.version_number})
        remember_idempotency(session, current_user, operation="billing-fee-policy.publish", key=idempotency_key,
                             payload=payload, resource_type="FeePolicyVersion", resource_id=version.id,
                             response_status=201)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise AppError("ERR-DUPLICATE-FEE-POLICY-VERSION", "Version hoặc ngày hiệu lực đã tồn tại.", 409) from None
        return FeePolicyVersionView.model_validate(version)


@router.get("/billing/periods", response_model=AccountingPeriodListResponse)
def list_accounting_periods(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        periods = session.scalars(select(AccountingPeriod).where(
            *current_user.scope_conditions(AccountingPeriod),
            *_building_visibility_conditions(current_user, AccountingPeriod),
        ).order_by(AccountingPeriod.period_start.desc(), AccountingPeriod.period_key)).all()
        return AccountingPeriodListResponse(items=[AccountingPeriodView.model_validate(period) for period in periods])


@router.post("/billing/periods", response_model=AccountingPeriodView, status_code=201)
def create_accounting_period(
    request: Request,
    body: AccountingPeriodCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    if body.period_end < body.period_start:
        raise AppError("ERR-ACCOUNTING-PERIOD-DATES", "Ngày kết thúc kỳ phải sau hoặc bằng ngày bắt đầu.", 422)
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="accounting-period.create",
                                    key=idempotency_key, payload=payload)
        if replay is not None:
            return AccountingPeriodView.model_validate(
                _scoped_record(session, current_user, AccountingPeriod, replay.resource_id),
            )
        current_user.assert_building_role(body.building_id, *BILLING_ROLES)
        period = AccountingPeriod(
            tenant_id=current_user.tenant_id,
            site_id=current_user.assert_active_site(),
            building_id=body.building_id,
            period_key=body.period_key,
            period_start=body.period_start,
            period_end=body.period_end,
            cutoff_at=body.cutoff_at,
        )
        session.add(period)
        session.flush()
        audit(session, current_user, request, event_type="AccountingPeriodCreated", action="create",
              resource_type="AccountingPeriod", resource_id=period.id, building_id=period.building_id,
              after={"period_key": period.period_key, "cutoff_at": period.cutoff_at.isoformat()})
        remember_idempotency(session, current_user, operation="accounting-period.create", key=idempotency_key,
                             payload=payload, resource_type="AccountingPeriod", resource_id=period.id,
                             response_status=201)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise AppError("ERR-DUPLICATE-ACCOUNTING-PERIOD", "Mã kỳ đã tồn tại trong tòa nhà.", 409) from None
        return AccountingPeriodView.model_validate(period)


@router.post("/billing/periods/{accounting_period_id}/transition", response_model=AccountingPeriodView)
def transition_accounting_period(
    request: Request,
    accounting_period_id: UUID,
    body: AccountingPeriodTransition,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        period = _scoped_record(session, current_user, AccountingPeriod, accounting_period_id, lock=True)
        require_version(period.version, body.expected_version)
        if body.status not in R4_PUBLIC_PERIOD_TRANSITIONS[period.status]:
            raise AppError("ERR-STATE-TRANSITION", "Chuyển trạng thái kỳ không hợp lệ.", 409)
        before = period.status
        period.status = body.status
        period.version += 1
        audit(session, current_user, request, event_type="PeriodStateChanged", action="transition",
              resource_type="AccountingPeriod", resource_id=period.id, building_id=period.building_id,
              before={"status": before}, after={"status": period.status})
        emit(session, current_user, request, event_type="PeriodStateChanged",
             resource_type="AccountingPeriod", resource_id=period.id, payload={"status": period.status})
        session.commit()
        return AccountingPeriodView.model_validate(period)


def _run_context(session, current_user: UserContext, body: BillingRunCreate):
    period = _scoped_record(session, current_user, AccountingPeriod, body.accounting_period_id, lock=True)
    policy_version = _scoped_record(session, current_user, FeePolicyVersion, body.fee_policy_version_id, lock=True)
    if policy_version.building_id != period.building_id:
        raise scope_not_found()
    if period.status not in {"OPEN", "CLOSING"}:
        raise AppError("ERR-ACCOUNTING-PERIOD-CLOSED", "Kỳ kế toán không thể phát hành hóa đơn.", 409)
    if (policy_version.effective_from > period.period_start
            or (policy_version.effective_to is not None and policy_version.effective_to <= period.period_start)):
        raise AppError("ERR-FEE-POLICY-NOT-EFFECTIVE", "Version biểu phí không hiệu lực ở đầu kỳ.", 409)
    return period, policy_version


def _record_run_outcome(session, current_user: UserContext, request: Request, run: BillingRun, *, retry: bool) -> None:
    event_type = "BillingRunCompleted" if run.status == "POSTED" else "BillingRunFailed"
    audit(session, current_user, request, event_type=event_type, action="retry" if retry else "run",
          resource_type="BillingRun", resource_id=run.id, building_id=run.building_id,
          after={"status": run.status, "failure_code": run.failure_code, "retry_count": run.retry_count})
    emit(session, current_user, request, event_type=event_type, resource_type="BillingRun", resource_id=run.id,
         payload={"status": run.status, "failure_code": run.failure_code})


@router.get("/billing/runs", response_model=BillingRunListResponse)
def list_billing_runs(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        runs = session.scalars(select(BillingRun).where(
            *current_user.scope_conditions(BillingRun),
            *_building_visibility_conditions(current_user, BillingRun),
        ).order_by(BillingRun.created_at.desc(), BillingRun.id)).all()
        return BillingRunListResponse(items=[BillingRunView.model_validate(run) for run in runs])


@router.post("/billing/runs", response_model=BillingRunView, status_code=201)
def start_billing_run(
    request: Request,
    body: BillingRunCreate,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = body.model_dump(mode="json")
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="billing-run.start",
                                    key=idempotency_key, payload=payload)
        if replay is not None:
            return BillingRunView.model_validate(_scoped_record(session, current_user, BillingRun, replay.resource_id))
        period, policy_version = _run_context(session, current_user, body)
        existing = session.scalar(select(BillingRun.id).where(
            BillingRun.building_id == period.building_id,
            BillingRun.accounting_period_id == period.id,
            BillingRun.fee_policy_version_id == policy_version.id,
        ).limit(1))
        if existing is not None:
            raise AppError("ERR-RUN-DUPLICATE", "Kỳ và version biểu phí này đã có Billing Run.", 409)
        run = BillingRun(
            tenant_id=current_user.tenant_id,
            site_id=current_user.assert_active_site(),
            building_id=period.building_id,
            accounting_period_id=period.id,
            fee_policy_version_id=policy_version.id,
            run_key=body.run_key,
            cutoff_at=period.cutoff_at,
            initiated_by_id=current_user.account_id,
        )
        session.add(run)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise AppError("ERR-RUN-DUPLICATE", "Một kế toán khác đã tạo Billing Run này.", 409) from None
        audit(session, current_user, request, event_type="BillingRunStarted", action="start",
              resource_type="BillingRun", resource_id=run.id, building_id=run.building_id,
              after={"run_key": run.run_key, "cutoff_at": run.cutoff_at.isoformat()})
        execute_run(session, run, period, policy_version, current_user.account_id)
        _record_run_outcome(session, current_user, request, run, retry=False)
        remember_idempotency(session, current_user, operation="billing-run.start", key=idempotency_key,
                             payload=payload, resource_type="BillingRun", resource_id=run.id,
                             response_status=201)
        session.commit()
        return BillingRunView.model_validate(run)


@router.post("/billing/runs/{billing_run_id}/retry", response_model=BillingRunView)
def retry_billing_run(
    request: Request,
    billing_run_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    payload = {"billing_run_id": str(billing_run_id)}
    with request.app.state.database.get_session() as session:
        replay = idempotency_replay(session, current_user, operation="billing-run.retry",
                                    key=idempotency_key, payload=payload)
        if replay is not None:
            return BillingRunView.model_validate(_scoped_record(session, current_user, BillingRun, replay.resource_id))
        run = _scoped_record(session, current_user, BillingRun, billing_run_id, lock=True)
        if run.status != "FAILED":
            raise AppError("ERR-STATE-TRANSITION", "Chỉ Billing Run FAILED mới được retry.", 409)
        period = _scoped_record(session, current_user, AccountingPeriod, run.accounting_period_id, lock=True)
        policy_version = _scoped_record(session, current_user, FeePolicyVersion, run.fee_policy_version_id, lock=True)
        if period.status not in {"OPEN", "CLOSING"}:
            raise AppError("ERR-ACCOUNTING-PERIOD-CLOSED", "Kỳ kế toán không thể retry Billing Run.", 409)
        run.retry_count += 1
        execute_run(session, run, period, policy_version, current_user.account_id)
        _record_run_outcome(session, current_user, request, run, retry=True)
        remember_idempotency(session, current_user, operation="billing-run.retry", key=idempotency_key,
                             payload=payload, resource_type="BillingRun", resource_id=run.id,
                             response_status=200)
        session.commit()
        return BillingRunView.model_validate(run)


@router.get("/billing/invoices", response_model=BillingInvoiceListResponse)
def list_billing_invoices(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        invoices = session.scalars(select(BillingInvoice).where(
            *current_user.scope_conditions(BillingInvoice),
            *_building_visibility_conditions(current_user, BillingInvoice),
        ).order_by(BillingInvoice.issued_on.desc(), BillingInvoice.invoice_number)).all()
        return BillingInvoiceListResponse(items=[_invoice_view(session, invoice) for invoice in invoices])


@router.get("/billing/invoices/{billing_invoice_id}", response_model=BillingInvoiceView)
def get_billing_invoice(
    request: Request,
    billing_invoice_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        return _invoice_view(session, _scoped_record(session, current_user, BillingInvoice, billing_invoice_id))


@router.post("/billing/invoices/{billing_invoice_id}/void", response_model=BillingInvoiceView)
def void_billing_invoice(
    request: Request,
    billing_invoice_id: UUID,
    body: BillingInvoiceVoid,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        invoice = _scoped_record(session, current_user, BillingInvoice, billing_invoice_id, lock=True)
        require_version(invoice.version, body.expected_version)
        period = _scoped_record(session, current_user, AccountingPeriod, invoice.accounting_period_id, lock=True)
        before = invoice.status
        void_invoice(session, invoice, period, current_user.account_id, body.reason)
        audit(session, current_user, request, event_type="InvoiceVoided", action="void",
              resource_type="BillingInvoice", resource_id=invoice.id, building_id=invoice.building_id,
              before={"status": before}, after={"status": invoice.status}, reason=invoice.void_reason)
        emit(session, current_user, request, event_type="InvoiceVoided",
             resource_type="BillingInvoice", resource_id=invoice.id, payload={"reason": invoice.void_reason})
        session.commit()
        return _invoice_view(session, invoice)
