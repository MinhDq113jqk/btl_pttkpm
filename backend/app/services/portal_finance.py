"""Portal fee snapshots and supplemental invoices share the existing AR ledger."""
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select, func

from app.core.exceptions import AppError
from app.models.billing import (AccountingPeriod, ArLedgerEntry, BillingAccount, BillingInvoice,
    BillingInvoiceItem, BillingRun, FeePolicy, FeePolicyVersion)
from app.models.resident_portal import PortalFeePosting, PortalFeeSource, PortalFeeInterval, PortalDeposit, LiabilityEpisode, PortalFinancialAdjustment
from app.services.billing_proration import calculate_proration
from app.services.r2 import utc_now


def business_date():
    return utc_now().astimezone(timezone(timedelta(hours=7))).date()


def fee_effective_date(value=None):
    try:
        result = date.fromisoformat(value) if value is not None else business_date()
    except (TypeError, ValueError):
        raise AppError("ERR-FEE-EFFECTIVE-DATE", "Ngày hiệu lực cần có định dạng YYYY-MM-DD.", 422) from None
    if result > business_date():
        raise AppError("ERR-FEE-EFFECTIVE-DATE", "Chỉ ghi nhận ngày đã có hiệu lực; lịch thay đổi tương lai cần hồ sơ riêng.", 422)
    return result


def create_fee_source(session, row, kind, amount, description, snapshot, *, recurring=False, basis="SERVICE_UNIT", effective_on=None):
    if amount <= 0:
        return None
    source = PortalFeeSource(tenant_id=row.tenant_id, site_id=row.site_id, building_id=row.building_id,
        unit_id=row.unit_id, account_id=row.account_id, source_kind=kind, source_id=row.id,
        description=description, amount_vnd=amount, basis=basis, recurring=recurring,
        valid_from=effective_on or business_date(), policy_snapshot=snapshot)
    session.add(source); session.flush()
    if recurring:
        session.add(PortalFeeInterval(fee_source_id=source.id, starts_on=source.valid_from,
            amount_vnd=amount, rounding_unit_vnd=snapshot.get("rounding_unit_vnd", 1)))
    return source


def create_deposit(session, row, kind, amount):
    if amount <= 0:
        return None
    deposit = PortalDeposit(tenant_id=row.tenant_id, site_id=row.site_id, building_id=row.building_id,
        unit_id=row.unit_id, account_id=row.account_id, source_kind=kind, source_id=row.id, required_vnd=amount)
    session.add(deposit)
    return deposit


def _change_source(session, source, action, effective_on):
    if effective_on < source.valid_from:
        raise AppError("ERR-FEE-EFFECTIVE-DATE", "Ngày thay đổi trước ngày bắt đầu phí.", 409)
    if source.recurring:
        intervals = session.scalars(select(PortalFeeInterval).where(PortalFeeInterval.fee_source_id == source.id)
            .order_by(PortalFeeInterval.starts_on, PortalFeeInterval.id).with_for_update()).all()
        if not intervals:
            raise AppError("ERR-FEE-HISTORY", "Nguồn phí thiếu lịch sử hiệu lực; cần đối chiếu trước.", 409)
        opened = [row for row in intervals if row.ends_on is None]
        if (source.status == "ACTIVE" and len(opened) != 1) or (source.status == "PAUSED" and opened):
            raise AppError("ERR-FEE-HISTORY", "Trạng thái nguồn phí không khớp khoảng hiệu lực.", 409)
        last = opened[0] if opened else max(intervals, key=lambda row: row.ends_on)
        if effective_on < max(row.ends_on or row.starts_on for row in intervals):
            raise AppError("ERR-FEE-EFFECTIVE-DATE", "Ngày thay đổi ghi đè lịch sử đã xác nhận.", 409)
        if action == "RESUME":
            session.add(PortalFeeInterval(fee_source_id=source.id, starts_on=effective_on,
                amount_vnd=source.amount_vnd, rounding_unit_vnd=source.policy_snapshot.get("rounding_unit_vnd", 1)))
        elif last.ends_on is None:
            last.ends_on = effective_on
    source.status = {"PAUSE": "PAUSED", "RESUME": "ACTIVE", "END": "ENDED"}[action]
    if action == "END":
        source.valid_to = effective_on
    source.version += 1


def change_fee_source(session, kind, identifier, action, effective_on):
    source = session.scalar(select(PortalFeeSource).where(PortalFeeSource.source_kind == kind,
        PortalFeeSource.source_id == identifier).with_for_update())
    if source is None:
        return None  # A free service has no monetary source.
    allowed = {"ACTIVE": {"PAUSE", "END"}, "PAUSED": {"RESUME", "END"}, "ENDED": set()}
    if action not in allowed[source.status] or (not source.recurring and action != "END"):
        raise AppError("ERR-FEE-STATE", "Nguồn phí không hỗ trợ thao tác này.", 409)
    if source.recurring and session.scalar(select(PortalFeePosting.id).join(AccountingPeriod,
            AccountingPeriod.id == PortalFeePosting.period_id).where(
                PortalFeePosting.fee_source_id == source.id, AccountingPeriod.period_end >= effective_on).limit(1)):
        raise AppError("ERR-FEE-POSTED-PERIOD", "Ngày thay đổi ảnh hưởng kỳ đã lập hóa đơn; cần lập hồ sơ điều chỉnh, không sửa hóa đơn cũ.", 409)
    _change_source(session, source, action, effective_on)
    return source


def end_fee_source(session, kind, identifier):
    sources = session.scalars(select(PortalFeeSource).where(PortalFeeSource.source_kind == kind,
        PortalFeeSource.source_id == identifier, PortalFeeSource.status != "ENDED").with_for_update()).all()
    for row in sources:
        # Lifecycle cleanup ends future accrual; issued invoice snapshots remain immutable.
        _change_source(session, row, "END", business_date())


def fee_calculation(session, source, period):
    if period.status not in {"OPEN", "CLOSING"}:
        raise AppError("ERR-ACCOUNTING-PERIOD-CLOSED", "Kỳ kế toán không nhận phí mới.", 409)
    if not source.recurring:
        if source.status == "ENDED":
            raise AppError("ERR-FEE-CANCELLED", "Nguồn phí một lần đã kết thúc; cần xử lý điều chỉnh hóa đơn đã lập.", 409)
        if source.valid_from > period.period_end:
            raise AppError("ERR-FEE-PERIOD", "Nguồn phí chưa có hiệu lực trong kỳ.", 409)
        if source.source_kind == 'METER':
            from app.models.operational_control import MeterReading
            reading = session.get(MeterReading, source.source_id)
            if (not reading or reading.status != 'VERIFIED' or reading.version != source.policy_snapshot['reading_version']
                    or not period.period_start <= reading.read_on <= period.period_end):
                raise AppError('ERR-METER-SOURCE-STALE', 'Chỉ số đã đổi hoặc không thuộc kỳ thu phí đã chọn.', 409)
            return {**source.policy_snapshot, 'amount_vnd': source.amount_vnd,
                'period_start': str(period.period_start), 'period_end': str(period.period_end), 'segments': [], 'rounding_groups': []}
        return {"method": "ONE_TIME", "amount_vnd": source.amount_vnd,
            "period_start": str(period.period_start), "period_end": str(period.period_end),
            "segments": [], "rounding_groups": []}
    intervals = session.scalars(select(PortalFeeInterval).where(PortalFeeInterval.fee_source_id == source.id)
        .order_by(PortalFeeInterval.starts_on, PortalFeeInterval.id)).all()
    if not intervals:
        raise AppError("ERR-FEE-HISTORY", "Nguồn phí thiếu lịch sử hiệu lực.", 409)
    try:
        return calculate_proration(period.period_start, period.period_end, [
            {"key": str(row.id), "starts_on": row.starts_on, "ends_on": row.ends_on,
             "amount_vnd": row.amount_vnd, "rounding_unit_vnd": row.rounding_unit_vnd} for row in intervals])
    except ValueError:
        raise AppError("ERR-FEE-HISTORY", "Lịch sử nguồn phí bị chồng hoặc thiếu căn cứ tính.", 409) from None


def calculation_hash(source, period, snapshot):
    material = json.dumps({"source_id": str(source.id), "source_version": source.version,
        "period_id": str(period.id), "period_version": period.version, "calculation": snapshot}, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()


def queue_booking_credit(session, booking, actor_id, reason):
    """Cancellation requests a credit decision; it never deletes an issued invoice."""
    invoices = session.scalars(select(BillingInvoice).join(PortalFeePosting, PortalFeePosting.invoice_id == BillingInvoice.id)
        .join(PortalFeeSource, PortalFeeSource.id == PortalFeePosting.fee_source_id).where(
            PortalFeeSource.source_kind == 'BOOKING', PortalFeeSource.source_id == booking.id,
            BillingInvoice.status.not_in(('DRAFT', 'VOID'))).with_for_update(of=BillingInvoice)).all()
    for invoice in invoices:
        reserved = session.scalar(select(func.coalesce(func.sum(PortalFinancialAdjustment.amount_vnd), 0)).where(
            PortalFinancialAdjustment.invoice_id == invoice.id, PortalFinancialAdjustment.kind == 'CREDIT',
            PortalFinancialAdjustment.status != 'REJECTED')) or 0
        amount = invoice.total_vnd - reserved
        if amount > 0:
            session.add(PortalFinancialAdjustment(tenant_id=booking.tenant_id, site_id=booking.site_id,
                building_id=booking.building_id, unit_id=booking.unit_id, account_id=booking.account_id,
                kind='CREDIT', invoice_id=invoice.id, amount_vnd=amount, reason=reason,
                requested_by_id=actor_id, evidence_reference='BOOKING_CANCEL:' + str(booking.id)))


def post_fee_source(session, source, period, actor, *, expected_calculation_hash=None, responsibility_snapshot=None):
    existing = session.scalar(select(PortalFeePosting).where(PortalFeePosting.fee_source_id == source.id,
                                                           PortalFeePosting.period_id == period.id))
    if existing:
        return session.get(BillingInvoice, existing.invoice_id)
    snapshot = fee_calculation(session, source, period)
    if expected_calculation_hash and expected_calculation_hash != calculation_hash(source, period, snapshot):
        raise AppError("ERR-FEE-PREVIEW-STALE", "Căn cứ tính đã thay đổi; cần xem trước lại.", 409)
    amount = snapshot["amount_vnd"]
    if amount <= 0:
        raise AppError("ERR-FEE-NO-ACCRUAL", "Không có phí phải thu trong kỳ đã chọn.", 409)
    if not source.recurring and session.scalar(select(PortalFeePosting.id).where(
            PortalFeePosting.fee_source_id == source.id).limit(1)):
        raise AppError("ERR-FEE-ALREADY-POSTED", "Phí một lần đã được lập hóa đơn.", 409)
    account = session.scalar(select(BillingAccount).where(BillingAccount.unit_id == source.unit_id,
        BillingAccount.tenant_id == source.tenant_id, BillingAccount.site_id == source.site_id).with_for_update())
    if account is None or account.status != "ACTIVE":
        raise AppError("ERR-BILLING-ACCOUNT-INACTIVE", "Kế toán cần mở tài khoản thu phí cho căn trước.", 409)
    scope = dict(tenant_id=source.tenant_id, site_id=source.site_id, building_id=source.building_id)
    # These policies describe one approved source, not a building-wide recurring run.
    policy = FeePolicy(**scope, code=f"PS-{source.id.hex}-{period.id.hex[:8]}", name=source.description[:200], is_active=False)
    session.add(policy); session.flush()
    version = FeePolicyVersion(**scope, fee_policy_id=policy.id, version_number=1,
        effective_from=period.period_start, effective_to=period.period_end + timedelta(days=1),
        unit_rate_vnd=source.amount_vnd, basis=source.basis,
        rounding_unit_vnd=source.policy_snapshot.get("rounding_unit_vnd", 1), published_at=utc_now())
    session.add(version); session.flush()
    run = BillingRun(**scope, accounting_period_id=period.id, fee_policy_version_id=version.id,
        run_key=f"PORTAL-{source.id.hex}-{period.id.hex}", status="POSTED", initiated_by_id=actor,
        cutoff_at=utc_now(), completed_at=utc_now())
    session.add(run); session.flush()
    invoice = BillingInvoice(**scope, billing_account_id=account.id, billing_run_id=run.id,
        responsibility_snapshot=responsibility_snapshot or {},
        accounting_period_id=period.id, invoice_number=f"PI-{uuid4().hex.upper()}",
        supplemental=True, issued_on=business_date(), due_on=None,
        status="ISSUED", total_vnd=amount, outstanding_vnd=amount)
    session.add(invoice); session.flush()
    session.add(BillingInvoiceItem(**scope, billing_invoice_id=invoice.id, fee_policy_version_id=version.id,
        line_number=1, description=source.description, basis=source.basis, basis_quantity=Decimal(1),
        unit_rate_vnd_snapshot=source.amount_vnd, rounding_unit_vnd_snapshot=source.policy_snapshot.get("rounding_unit_vnd", 1),
        amount_vnd=amount, calculation_snapshot=snapshot))
    session.add(ArLedgerEntry(**scope, billing_account_id=account.id, accounting_period_id=period.id,
        entry_type="INVOICE_ISSUED", source_type="INVOICE", source_id=invoice.id,
        debit_vnd=amount, credit_vnd=0, effective_at=utc_now(), created_by_id=actor))
    liability_date = max(period.period_start, min(business_date(), period.period_end))
    payer = session.scalar(select(LiabilityEpisode.person_id).where(LiabilityEpisode.unit_id == source.unit_id,
        LiabilityEpisode.tenant_id == source.tenant_id, LiabilityEpisode.valid_from <= liability_date,
        (LiabilityEpisode.valid_to.is_(None) | (LiabilityEpisode.valid_to > liability_date)))
        .order_by(LiabilityEpisode.valid_from.desc()).limit(1))
    if payer is None:
        from app.models.account import Account
        payer = session.scalar(select(Account.person_id).where(Account.id == source.account_id, Account.tenant_id == source.tenant_id))
    session.add(PortalFeePosting(fee_source_id=source.id, period_id=period.id, invoice_id=invoice.id, liable_person_id=payer))
    return invoice
