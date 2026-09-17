from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.billing import ArLedgerEntry, BillingAccount, BillingInvoice, BillingInvoiceItem, Payment
from app.schemas.resident_billing import (
    ResidentArBalanceView,
    ResidentBillingInvoiceItemView,
    ResidentBillingInvoiceListResponse,
    ResidentBillingInvoiceView,
    ResidentBillingSummaryResponse,
    ResidentPaymentListResponse,
    ResidentPaymentView,
)


router = APIRouter(tags=["R6 resident billing"])


def _assert_resident_scope(context: UserContext) -> None:
    context.assert_role("resident")
    context.assert_active_site()
    if context.resident_person_id is None or not context.resident_unit_ids:
        raise scope_not_found()


def _as_of_utc(as_of: datetime) -> datetime:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise AppError("ERR-AS-OF-TIMEZONE", "as_of phải bao gồm múi giờ.", 422)
    return as_of.astimezone(UTC)


def _resident_account_conditions(context: UserContext):
    return (
        *context.scope_conditions(BillingAccount),
        BillingAccount.unit_id.in_(context.resident_unit_ids),
    )


@router.get("/resident/billing/summary", response_model=ResidentBillingSummaryResponse)
def get_resident_billing_summary(
    request: Request,
    as_of: datetime = Query(..., description="RFC3339 timestamp including a timezone."),
    current_user: UserContext = Depends(get_current_user_context),
):
    _assert_resident_scope(current_user)
    cutoff = _as_of_utc(as_of)
    with request.app.state.database.get_session() as session:
        rows = session.execute(select(
            BillingAccount.unit_id,
            func.coalesce(func.sum(ArLedgerEntry.debit_vnd - ArLedgerEntry.credit_vnd), 0).label("balance"),
        ).outerjoin(ArLedgerEntry, and_(
            ArLedgerEntry.billing_account_id == BillingAccount.id,
            *current_user.scope_conditions(ArLedgerEntry),
            ArLedgerEntry.effective_at <= cutoff,
        )).where(
            *_resident_account_conditions(current_user),
        ).group_by(BillingAccount.id, BillingAccount.unit_id).order_by(
            BillingAccount.account_number, BillingAccount.id,
        )).all()
        items = [ResidentArBalanceView(unit_id=row.unit_id, ar_balance_vnd=int(row.balance)) for row in rows]
        return ResidentBillingSummaryResponse(
            as_of=cutoff,
            total_ar_balance_vnd=sum(item.ar_balance_vnd for item in items),
            items=items,
        )


def _resident_invoice_view(
    invoice: BillingInvoice, unit_id, items: list[BillingInvoiceItem],
) -> ResidentBillingInvoiceView:
    # issued_on is non-null because the only query that reaches this view filters it.
    if invoice.issued_on is None:
        raise scope_not_found()
    return ResidentBillingInvoiceView(
        id=invoice.id,
        unit_id=unit_id,
        invoice_number=invoice.invoice_number,
        issued_on=invoice.issued_on,
        due_on=invoice.due_on,
        total_vnd=invoice.total_vnd,
        items=[ResidentBillingInvoiceItemView(
            line_number=item.line_number,
            description=item.description,
            basis=item.basis,
            basis_quantity=float(item.basis_quantity),
            unit_rate_vnd_snapshot=item.unit_rate_vnd_snapshot,
            rounding_unit_vnd_snapshot=item.rounding_unit_vnd_snapshot,
            amount_vnd=item.amount_vnd,
        ) for item in items],
    )


@router.get("/resident/billing/invoices", response_model=ResidentBillingInvoiceListResponse)
def list_resident_billing_invoices(
    request: Request,
    as_of: datetime = Query(..., description="RFC3339 timestamp including a timezone."),
    current_user: UserContext = Depends(get_current_user_context),
):
    _assert_resident_scope(current_user)
    cutoff = _as_of_utc(as_of)
    with request.app.state.database.get_session() as session:
        rows = session.execute(select(BillingInvoice, BillingAccount.unit_id).join(
            BillingAccount, and_(
                BillingAccount.id == BillingInvoice.billing_account_id,
                BillingAccount.building_id == BillingInvoice.building_id,
            ),
        ).where(
            *current_user.scope_conditions(BillingInvoice),
            *_resident_account_conditions(current_user),
            BillingInvoice.issued_on.is_not(None),
            # Invoices retain a date rather than an issuance timestamp.  The cutoff
            # semantics are therefore calendar-day based; AR stays timestamp exact.
            BillingInvoice.issued_on <= cutoff.date(),
        ).order_by(
            BillingInvoice.issued_on.desc(), BillingInvoice.invoice_number.desc(), BillingInvoice.id.desc(),
        )).all()
        invoice_ids = [invoice.id for invoice, _ in rows]
        items_by_invoice: dict = {invoice_id: [] for invoice_id in invoice_ids}
        if invoice_ids:
            items = session.scalars(select(BillingInvoiceItem).where(
                *current_user.scope_conditions(BillingInvoiceItem),
                BillingInvoiceItem.billing_invoice_id.in_(invoice_ids),
            ).order_by(BillingInvoiceItem.billing_invoice_id, BillingInvoiceItem.line_number)).all()
            for item in items:
                items_by_invoice[item.billing_invoice_id].append(item)
        return ResidentBillingInvoiceListResponse(
            as_of=cutoff,
            items=[_resident_invoice_view(invoice, unit_id, items_by_invoice[invoice.id])
                   for invoice, unit_id in rows],
        )


@router.get("/resident/billing/payments", response_model=ResidentPaymentListResponse)
def list_resident_payments(
    request: Request,
    as_of: datetime = Query(..., description="RFC3339 timestamp including a timezone."),
    current_user: UserContext = Depends(get_current_user_context),
):
    _assert_resident_scope(current_user)
    cutoff = _as_of_utc(as_of)
    with request.app.state.database.get_session() as session:
        rows = session.execute(select(Payment, BillingAccount.unit_id).join(
            BillingAccount, and_(
                BillingAccount.id == Payment.billing_account_id,
                BillingAccount.building_id == Payment.building_id,
            ),
        ).where(
            *current_user.scope_conditions(Payment),
            *_resident_account_conditions(current_user),
            Payment.received_at <= cutoff,
        ).order_by(Payment.received_at.desc(), Payment.id.desc())).all()
        return ResidentPaymentListResponse(
            as_of=cutoff,
            items=[ResidentPaymentView(
                id=payment.id,
                unit_id=unit_id,
                payment_source=payment.payment_source,
                receipt_number=payment.receipt_number,
                amount_vnd=payment.amount_vnd,
                received_at=payment.received_at,
            ) for payment, unit_id in rows],
        )
