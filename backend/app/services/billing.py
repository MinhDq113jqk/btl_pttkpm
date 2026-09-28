"""Transactional R4 billing calculation; monetary arithmetic lives only here."""
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.policy import UserContext
from app.models.billing import (
    AccountingPeriod,
    ArLedgerEntry,
    BillingAccount,
    BillingInvoice,
    BillingInvoiceItem,
    BillingRun,
    FeePolicyVersion,
    OverpaymentCredit,
    Payment,
    PaymentAllocation,
    UnmatchedPayment,
)
from app.models.service import CostLine, InvoiceItem, PendingCharge, ServiceRequest, WorkOrder
from app.models.unit import Unit
from app.services.r2 import utc_now


def round_half_up_to_unit(value: Decimal, unit_vnd: int) -> int:
    """Round once, deterministically, to a positive integer-VND unit."""
    if unit_vnd < 1:
        raise ValueError("rounding unit must be positive")
    return int((value / Decimal(unit_vnd)).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * unit_vnd)


def split_largest_remainder(total_vnd: int, shares: list[tuple[str, Decimal]]) -> list[int]:
    """ALG-02 helper: floor each share, assign all residual VND deterministically."""
    if total_vnd < 0 or not shares:
        raise ValueError("total and shares must be valid")
    share_total = sum(share for _, share in shares)
    if share_total <= 0 or abs(share_total - Decimal("1")) > Decimal("0.000000000000000001"):
        raise ValueError("shares must total exactly one")
    normalized = [(key, share / share_total) for key, share in shares]
    parts = [int(Decimal(total_vnd) * share) for _, share in normalized]
    residual = total_vnd - sum(parts)
    order = sorted(range(len(normalized)), key=lambda index: (-normalized[index][1], normalized[index][0]))
    for index in order[:residual]:
        parts[index] += 1
    return parts


def _basis_amount(unit: Unit, policy_version: FeePolicyVersion) -> tuple[Decimal, int]:
    if policy_version.basis != "UNIT_AREA_M2":
        raise AppError("ERR-BILLING-BASIS", "Cơ sở tính phí chưa được hỗ trợ.", 409)
    basis = Decimal(str(unit.area_m2))
    if basis <= 0:
        raise AppError("ERR-BILLING-BASIS", "Diện tích căn phải lớn hơn 0 để lập hóa đơn.", 409)
    amount = round_half_up_to_unit(basis * Decimal(policy_version.unit_rate_vnd), policy_version.rounding_unit_vnd)
    return basis, amount


def _approved_charges(session: Session, account: BillingAccount, cutoff_at: datetime):
    return session.execute(
        select(PendingCharge, CostLine).join(
            CostLine, PendingCharge.cost_line_id == CostLine.id,
        ).join(
            WorkOrder, CostLine.work_order_id == WorkOrder.id,
        ).join(
            ServiceRequest, WorkOrder.service_request_id == ServiceRequest.id,
        ).where(
            PendingCharge.status == "APPROVED",
            PendingCharge.reviewed_at.is_not(None),
            PendingCharge.reviewed_at <= cutoff_at,
            WorkOrder.building_id == account.building_id,
            ServiceRequest.unit_id == account.unit_id,
        ).order_by(PendingCharge.reviewed_at, PendingCharge.id).with_for_update()
    ).all()


def _invoice_number(period: AccountingPeriod, account: BillingAccount) -> str:
    return f"INV-{period.period_key}-{account.id.hex[:12].upper()}"


def _calculate_run(
    session: Session,
    run: BillingRun,
    period: AccountingPeriod,
    policy_version: FeePolicyVersion,
    actor_id: UUID,
    *,
    invoice_number_resolver: Callable[[BillingAccount], str] | None = None,
    issued_on_resolver: Callable[[BillingAccount], date | None] | None = None,
    due_on_resolver: Callable[[BillingAccount], date | None] | None = None,
) -> None:
    accounts = session.execute(
        select(BillingAccount, Unit).join(Unit, BillingAccount.unit_id == Unit.id).where(
            BillingAccount.building_id == run.building_id,
            BillingAccount.status == "ACTIVE",
            BillingAccount.opened_on <= period.period_end,
        ).order_by(BillingAccount.account_number, BillingAccount.id).with_for_update()
    ).all()
    for account, unit in accounts:
        basis, fee_amount = _basis_amount(unit, policy_version)
        item_specs = [{
            "description": policy_version.basis.replace("_", " "),
            "basis": policy_version.basis,
            "basis_quantity": basis,
            "unit_rate_vnd_snapshot": policy_version.unit_rate_vnd,
            "rounding_unit_vnd_snapshot": policy_version.rounding_unit_vnd,
            "amount_vnd": fee_amount,
            "source_pending_charge_id": None,
        }]
        approved_charges = _approved_charges(session, account, run.cutoff_at)
        for charge, cost_line in approved_charges:
            item_specs.append({
                "description": cost_line.description,
                "basis": "PENDING_CHARGE",
                "basis_quantity": Decimal("1"),
                "unit_rate_vnd_snapshot": cost_line.amount_vnd,
                "rounding_unit_vnd_snapshot": 1,
                "amount_vnd": cost_line.amount_vnd,
                "source_pending_charge_id": charge.id,
            })
        total_vnd = sum(item["amount_vnd"] for item in item_specs)
        if total_vnd <= 0:
            continue
        invoice = BillingInvoice(
            tenant_id=run.tenant_id,
            site_id=run.site_id,
            building_id=run.building_id,
            billing_account_id=account.id,
            billing_run_id=run.id,
            accounting_period_id=period.id,
            invoice_number=(
                invoice_number_resolver(account)
                if invoice_number_resolver is not None
                else _invoice_number(period, account)
            ),
            issued_on=(
                issued_on_resolver(account)
                if issued_on_resolver is not None
                else period.period_end
            ),
            due_on=(
                due_on_resolver(account)
                if due_on_resolver is not None
                else period.period_end
            ),
            status="ISSUED",
            total_vnd=total_vnd,
            outstanding_vnd=total_vnd,
        )
        session.add(invoice)
        session.flush()
        for line_number, spec in enumerate(item_specs, 1):
            session.add(BillingInvoiceItem(
                tenant_id=run.tenant_id,
                site_id=run.site_id,
                building_id=run.building_id,
                billing_invoice_id=invoice.id,
                fee_policy_version_id=policy_version.id,
                line_number=line_number,
                **spec,
            ))
        session.add(ArLedgerEntry(
            tenant_id=run.tenant_id,
            site_id=run.site_id,
            building_id=run.building_id,
            billing_account_id=account.id,
            accounting_period_id=period.id,
            entry_type="INVOICE_ISSUED",
            source_type="INVOICE",
            source_id=invoice.id,
            debit_vnd=total_vnd,
            credit_vnd=0,
            effective_at=datetime.combine(period.period_end, datetime.min.time(), tzinfo=UTC),
            created_by_id=actor_id,
        ))
        for charge, cost_line in approved_charges:
            # A BillingInvoiceItem is the immutable billing snapshot.  Retain
            # the pre-existing R2 posting anchor as well so every POSTED
            # PendingCharge has exactly one durable source record.
            session.add(InvoiceItem(
                tenant_id=run.tenant_id,
                site_id=run.site_id,
                pending_charge_id=charge.id,
                posting_reference=f"BR-{run.id.hex}-{charge.id.hex}",
                amount_vnd=cost_line.amount_vnd,
                created_by_id=actor_id,
            ))
            charge.status = "POSTED"
            charge.posted_at = utc_now()
            charge.version += 1


def execute_run(
    session: Session,
    run: BillingRun,
    period: AccountingPeriod,
    policy_version: FeePolicyVersion,
    actor_id: UUID,
    *,
    invoice_number_resolver: Callable[[BillingAccount], str] | None = None,
    issued_on_resolver: Callable[[BillingAccount], date | None] | None = None,
    due_on_resolver: Callable[[BillingAccount], date | None] | None = None,
) -> BillingRun:
    """Generate an all-or-nothing invoice set; failures survive for safe retry."""
    run.status = "CALCULATING"
    run.failure_code = None
    run.failure_detail = None
    run.failed_at = None
    try:
        with session.begin_nested():
            _calculate_run(
                session,
                run,
                period,
                policy_version,
                actor_id,
                invoice_number_resolver=invoice_number_resolver,
                issued_on_resolver=issued_on_resolver,
                due_on_resolver=due_on_resolver,
            )
            session.flush()
    except AppError as error:
        run.status = "FAILED"
        run.failure_code = error.code
        run.failure_detail = error.message
        run.failed_at = utc_now()
        run.version += 1
        return run
    except IntegrityError:
        run.status = "FAILED"
        run.failure_code = "ERR-RUN-DUPLICATE"
        run.failure_detail = "Tập hóa đơn trùng hoặc không còn nhất quán; hãy kiểm tra dữ liệu trước khi retry."
        run.failed_at = utc_now()
        run.version += 1
        return run
    run.status = "POSTED"
    run.completed_at = utc_now()
    run.version += 1
    return run


def void_invoice(session: Session, invoice: BillingInvoice, period: AccountingPeriod,
                 actor_id: UUID, reason: str) -> BillingInvoice:
    if period.status != "OPEN":
        raise AppError("ERR-ACCOUNTING-PERIOD-CLOSED", "Chỉ được void hóa đơn trong kỳ OPEN.", 409)
    allocation_exists = session.scalar(select(PaymentAllocation.id).where(
        PaymentAllocation.billing_invoice_id == invoice.id,
    ).limit(1))
    if invoice.status != "ISSUED" or invoice.outstanding_vnd != invoice.total_vnd or allocation_exists is not None:
        raise AppError("ERR-INVOICE-VOID-RESTRICTED", "Chỉ được void hóa đơn chưa có phân bổ thanh toán.", 409)
    invoice.status = "VOID"
    invoice.outstanding_vnd = 0
    invoice.voided_at = utc_now()
    invoice.voided_by_id = actor_id
    invoice.void_reason = reason
    invoice.version += 1
    session.add(ArLedgerEntry(
        tenant_id=invoice.tenant_id,
        site_id=invoice.site_id,
        building_id=invoice.building_id,
        billing_account_id=invoice.billing_account_id,
        accounting_period_id=invoice.accounting_period_id,
        entry_type="REVERSAL",
        source_type="INVOICE",
        source_id=invoice.id,
        debit_vnd=0,
        credit_vnd=invoice.total_vnd,
        effective_at=utc_now(),
        created_by_id=actor_id,
    ))
    return invoice


def record_payment_received(session: Session, payment: Payment, actor_id: UUID) -> ArLedgerEntry:
    """Append the AR credit only after a receipt has a verified Billing Account."""
    if payment.billing_account_id is None:
        raise AppError("ERR-PAYMENT-UNMATCHED", "Payment chưa được match Billing Account.", 409)
    entry = ArLedgerEntry(
        tenant_id=payment.tenant_id,
        site_id=payment.site_id,
        building_id=payment.building_id,
        billing_account_id=payment.billing_account_id,
        accounting_period_id=payment.accounting_period_id,
        entry_type="PAYMENT_RECEIVED",
        source_type="PAYMENT",
        source_id=payment.id,
        debit_vnd=0,
        credit_vnd=payment.amount_vnd,
        effective_at=payment.received_at,
        created_by_id=actor_id,
    )
    session.add(entry)
    return entry


def receive_payment_command(
    session: Session,
    *,
    tenant_id: UUID,
    site_id: UUID,
    building_id: UUID,
    period: AccountingPeriod,
    account: BillingAccount | None,
    payment_source: str,
    source_reference: str,
    receipt_number: str,
    amount_vnd: int,
    received_at: datetime,
    actor_id: UUID | None,
    unmatched_reason: str = "Thiếu mã Billing Account khi nhận thanh toán.",
) -> Payment:
    """Create a receipt through one reusable domain command.

    The HTTP route and the submission-data replay share this mutation boundary;
    callers still own their transaction, audit event and outbox correlation.
    """
    if period.building_id != building_id or period.site_id != site_id or period.tenant_id != tenant_id:
        raise AppError("ERR-SCOPE-NOTFOUND", "Kỳ kế toán không thuộc phạm vi.", 404)
    if period.status not in {"OPEN", "CLOSING"}:
        raise AppError("ERR-ACCOUNTING-PERIOD-CLOSED", "Kỳ kế toán không nhận giao dịch mới.", 409)
    if account is not None:
        if (
            account.tenant_id != tenant_id
            or account.site_id != site_id
            or account.building_id != building_id
            or account.status != "ACTIVE"
        ):
            raise AppError("ERR-BILLING-ACCOUNT-INACTIVE", "Tài khoản thu phí không còn hoạt động.", 409)
    if amount_vnd <= 0:
        raise AppError("ERR-PAYMENT-AMOUNT", "Số tiền thanh toán phải lớn hơn 0.", 422)
    duplicate = session.scalar(select(Payment.id).where(
        Payment.tenant_id == tenant_id,
        Payment.site_id == site_id,
        or_(
            and_(Payment.payment_source == payment_source, Payment.source_reference == source_reference),
            Payment.receipt_number == receipt_number,
        ),
    ).limit(1))
    if duplicate is not None:
        raise AppError("ERR-DUPLICATE-PAYMENT", "Nguồn thanh toán hoặc biên lai đã tồn tại.", 409)

    payment = Payment(
        tenant_id=tenant_id,
        site_id=site_id,
        building_id=building_id,
        billing_account_id=account.id if account is not None else None,
        accounting_period_id=period.id,
        payment_source=payment_source,
        source_reference=source_reference,
        receipt_number=receipt_number,
        amount_vnd=amount_vnd,
        received_at=received_at,
        received_by_id=actor_id,
        status="RECEIVED" if account is not None else "UNMATCHED",
    )
    session.add(payment)
    session.flush()
    if account is not None:
        record_payment_received(session, payment, actor_id) if actor_id is not None else None
    else:
        session.add(UnmatchedPayment(
            tenant_id=tenant_id,
            site_id=site_id,
            building_id=building_id,
            payment_id=payment.id,
            amount_vnd=amount_vnd,
            reason=unmatched_reason,
        ))
    session.flush()
    return payment


def match_unmatched_payment_command(
    session: Session,
    *,
    unmatched: UnmatchedPayment,
    account: BillingAccount,
    actor_id: UUID,
) -> Payment:
    """Resolve an unmatched receipt before it can affect AR or invoices."""
    payment = session.scalar(select(Payment).where(Payment.id == unmatched.payment_id).with_for_update())
    if payment is None:
        raise AppError("ERR-PAYMENT-INTEGRITY", "Payment unmatched không tồn tại.", 409)
    if unmatched.status != "OPEN":
        raise AppError("ERR-STATE-TRANSITION", "Payment unmatched này không còn chờ match.", 409)
    if payment.status != "UNMATCHED" or payment.billing_account_id is not None:
        raise AppError("ERR-PAYMENT-INTEGRITY", "Payment unmatched không nhất quán.", 409)
    if account.status != "ACTIVE" or account.building_id != payment.building_id:
        raise AppError("ERR-SCOPE-NOTFOUND", "Tài khoản thu phí không thuộc phạm vi.", 404)
    period = session.scalar(select(AccountingPeriod).where(
        AccountingPeriod.id == payment.accounting_period_id,
        AccountingPeriod.building_id == payment.building_id,
    ).with_for_update())
    if period is None or period.status not in {"OPEN", "CLOSING"}:
        raise AppError("ERR-ACCOUNTING-PERIOD-CLOSED", "Kỳ kế toán không nhận giao dịch mới.", 409)
    payment.billing_account_id = account.id
    payment.status = "RECEIVED"
    payment.version += 1
    unmatched.status = "RESOLVED"
    unmatched.version += 1
    record_payment_received(session, payment, actor_id)
    session.flush()
    return payment


def allocate_payment(session: Session, payment: Payment, actor_id: UUID) -> tuple[list[PaymentAllocation], OverpaymentCredit | None]:
    """ALG-05: consume the payment against the oldest open debts of one account."""
    if payment.billing_account_id is None or payment.status == "UNMATCHED":
        raise AppError("ERR-PAYMENT-UNMATCHED", "Payment thiếu mã chưa thể phân bổ.", 409)
    if payment.status == "REVERSED":
        raise AppError("ERR-STATE-TRANSITION", "Payment đã reverse không thể phân bổ.", 409)

    existing = session.scalars(select(PaymentAllocation).where(
        PaymentAllocation.payment_id == payment.id,
    ).order_by(PaymentAllocation.created_at, PaymentAllocation.id)).all()
    existing_credit = session.scalar(select(OverpaymentCredit).where(
        OverpaymentCredit.payment_id == payment.id,
    ))
    if payment.status in {"ALLOCATED", "OVERPAID"}:
        return existing, existing_credit

    allocated_vnd = sum(item.amount_vnd for item in existing)
    remaining_vnd = payment.amount_vnd - allocated_vnd
    if remaining_vnd < 0:
        raise AppError("ERR-PAYMENT-INTEGRITY", "Payment có tổng phân bổ vượt số tiền nhận.", 409)
    payment.status = "ALLOCATING"
    invoices = session.scalars(select(BillingInvoice).where(
        BillingInvoice.billing_account_id == payment.billing_account_id,
        BillingInvoice.status.in_(("ISSUED", "PARTIALLY_PAID")),
        BillingInvoice.outstanding_vnd > 0,
    ).order_by(
        BillingInvoice.due_on.asc().nulls_last(),
        BillingInvoice.issued_on.asc().nulls_last(),
        BillingInvoice.invoice_number.asc(),
        BillingInvoice.id.asc(),
    ).with_for_update()).all()

    created: list[PaymentAllocation] = []
    for invoice in invoices:
        if remaining_vnd == 0:
            break
        amount_vnd = min(remaining_vnd, invoice.outstanding_vnd)
        allocation = PaymentAllocation(
            tenant_id=payment.tenant_id,
            site_id=payment.site_id,
            building_id=payment.building_id,
            payment_id=payment.id,
            billing_invoice_id=invoice.id,
            amount_vnd=amount_vnd,
            allocated_by_id=actor_id,
        )
        session.add(allocation)
        # Flush before updating the snapshot balance: the DB trigger sees the
        # same available balance that this command is about to consume.
        session.flush()
        invoice.outstanding_vnd -= amount_vnd
        invoice.status = "PAID" if invoice.outstanding_vnd == 0 else "PARTIALLY_PAID"
        invoice.version += 1
        created.append(allocation)
        remaining_vnd -= amount_vnd

    if remaining_vnd:
        credit = OverpaymentCredit(
            tenant_id=payment.tenant_id,
            site_id=payment.site_id,
            building_id=payment.building_id,
            billing_account_id=payment.billing_account_id,
            payment_id=payment.id,
            original_vnd=remaining_vnd,
            remaining_vnd=remaining_vnd,
            status="OPEN",
        )
        session.add(credit)
        session.flush()
        # The receipt over-credits AR. This debit neutralizes the AR excess
        # while the separate Credit record remains the controlled liability.
        session.add(ArLedgerEntry(
            tenant_id=payment.tenant_id,
            site_id=payment.site_id,
            building_id=payment.building_id,
            billing_account_id=payment.billing_account_id,
            accounting_period_id=payment.accounting_period_id,
            entry_type="CREDIT_ISSUED",
            source_type="OVERPAYMENT_CREDIT",
            source_id=credit.id,
            debit_vnd=remaining_vnd,
            credit_vnd=0,
            effective_at=payment.received_at,
            created_by_id=actor_id,
        ))
        payment.status = "OVERPAID"
        payment.version += 1
        return [*existing, *created], credit

    payment.status = "ALLOCATED"
    payment.version += 1
    return [*existing, *created], None
