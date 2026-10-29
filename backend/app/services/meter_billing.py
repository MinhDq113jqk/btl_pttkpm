"""Measured sources use published tariffs and the existing billing review workflow."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid5
from sqlalchemy import select
from app.core.exceptions import AppError
from app.models.billing import FeePolicy, FeePolicyVersion
from app.models.operational_control import MeterReading
from app.models.resident_portal import PortalFeeSource, PortalFeePosting


def effective_reading(session, reading):
    from types import SimpleNamespace
    from app.models.operational_control import OperationsRecord
    corrections = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'METER_CORRECTION',
        OperationsRecord.tenant_id == reading.tenant_id, OperationsRecord.site_id == reading.site_id,
        OperationsRecord.status.in_(('APPROVED', 'COMPLETED'))).order_by(OperationsRecord.created_at.desc())).all()
    correction = next((c for c in corrections if str(reading.id) in c.data.get('effective_readings', {})), None)
    if not correction: return reading
    values = correction.data['effective_readings'][str(reading.id)]
    return SimpleNamespace(**{k: getattr(reading, k) for k in ('id', 'tenant_id', 'site_id', 'building_id', 'unit_id', 'account_id', 'meter_id', 'read_on', 'version')},
        value=Decimal(values['value']), consumption=Decimal(values['consumption']))


def price_snapshot(session, reading, meter, tariff):
    reading = effective_reading(session, reading)
    policy = session.get(FeePolicy, tariff.fee_policy_id)
    previous = session.scalar(select(MeterReading).where(MeterReading.meter_id == meter.id,
        MeterReading.read_on < reading.read_on).order_by(MeterReading.read_on.desc()).limit(1))
    start = previous.read_on if previous else meter.valid_from
    if (not policy or not policy.is_active or tariff.building_id != meter.building_id
            or tariff.basis != 'SERVICE_UNIT' or not tariff.published_at
            or tariff.tariff.get('commodity') not in (None, meter.commodity)
            or tariff.effective_from > start
            or tariff.effective_to and tariff.effective_to < reading.read_on):
        raise AppError('ERR-METER-TARIFF', 'Cần biểu phí theo sản lượng đã công bố phủ cả khoảng đo; khi đổi giá cần chỉ số tại mốc đổi.', 409)
    later = session.scalars(select(FeePolicyVersion).where(FeePolicyVersion.fee_policy_id == tariff.fee_policy_id,
        FeePolicyVersion.published_at.is_not(None), FeePolicyVersion.effective_from > tariff.effective_from,
        FeePolicyVersion.effective_from < reading.read_on)).all()
    if later:
        raise AppError('ERR-METER-TARIFF', 'Khoảng đo đã gặp phiên bản giá mới; cần chia chỉ số tại mốc đổi giá.', 409)
    expected_uom = {'WATER': 'm3', 'ELECTRICITY': 'kWh'}[meter.commodity]
    if tariff.tariff.get('uom') and tariff.tariff['uom'].casefold() != expected_uom.casefold():
        raise AppError('ERR-METER-UOM', 'Đơn vị biểu phí khác đơn vị đo chuẩn; cần quy đổi được xác nhận.', 409)
    from app.services.meter_assignments import assignment_for_interval
    assignment = assignment_for_interval(session, meter, start, reading.read_on)
    if assignment.unit_id != reading.unit_id:
        raise AppError('ERR-METER-ASSIGNMENT', 'Khoảng đo khác căn được gắn đồng hồ.', 409)
    rounding = tariff.rounding_unit_vnd
    from app.models.operational_control import OperationsRecord
    benefits = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'FEE_BENEFIT', OperationsRecord.status == 'APPROVED', OperationsRecord.building_id == meter.building_id)).all()
    benefits = [b for b in benefits if b.data['fee_policy_id'] == str(tariff.fee_policy_id) and str(reading.unit_id) in b.data['unit_ids'] and b.data['valid_from'] < reading.read_on.isoformat() and b.data['valid_to'] > start.isoformat()]
    if len(benefits) > 1 or any(b.data['valid_from'] > start.isoformat() or b.data['valid_to'] < reading.read_on.isoformat() for b in benefits):
        raise AppError('ERR-METER-BENEFIT-BOUNDARY', 'Miễn giảm đổi trong khoảng đo; cần chỉ số tại mốc hiệu lực.', 409)
    factor = (Decimal(100)-Decimal(benefits[0].data['percent']))/100 if benefits else Decimal(1)
    amount = int((reading.consumption * tariff.unit_rate_vnd * factor / rounding).quantize(Decimal(1), rounding=ROUND_HALF_UP)) * rounding
    if amount > 999999999999:
        raise AppError('ERR-METER-RANGE', 'Tiền tiêu thụ vượt giới hạn.', 422)
    return {'method': 'METER', 'meter_id': str(meter.id), 'reading_id': str(reading.id),
        'reading_version': reading.version, 'commodity': meter.commodity,
        'starts_on': start.isoformat(), 'ends_on': reading.read_on.isoformat(),
        'value': str(reading.value), 'consumption': str(reading.consumption),
        'assignment_id': str(assignment.id), 'point': assignment.point, 'uom': tariff.tariff.get('uom'),
        'tariff_version_id': str(tariff.id), 'tariff_revision': tariff.version,
        'unit_rate_vnd': tariff.unit_rate_vnd, 'rounding_unit_vnd': rounding, 'benefit_factor': str(factor),
        'benefits': [{'id': str(b.id), 'version': b.version, 'data': b.data} for b in benefits], 'amount_vnd': amount}


def correction_sources(session, readings):
    sources = session.scalars(select(PortalFeeSource).where(PortalFeeSource.source_kind == 'METER',
        PortalFeeSource.source_id.in_([r.id for r in readings])).with_for_update()).all()
    if sources and session.scalar(select(PortalFeePosting.id).where(PortalFeePosting.fee_source_id.in_([s.id for s in sources])).limit(1)):
        raise AppError('ERR-METER-INVOICED', 'Chỉ số ảnh hưởng hóa đơn đã phát hành; cần hồ sơ điều chỉnh tài chính, không sửa chỉ số nguồn.', 409)
    return sources


def financial_correction(session, context, dossier, meter, reading, after, corrected, base):
    """Preserve issued measurement snapshots; create financial drafts for independent action."""
    from types import SimpleNamespace
    from app.models.operational_control import OperationsRecord
    from app.models.billing import BillingInvoice
    from app.models.resident_portal import PortalFinancialAdjustment
    from app.services.portal_finance import create_fee_source
    from app.services.resident_portal import scope_values
    affected = [reading, *([after] if after else [])]
    sources = session.scalars(select(PortalFeeSource).where(PortalFeeSource.source_kind == 'METER', PortalFeeSource.source_id.in_([r.id for r in affected])).with_for_update()).all()
    postings = session.scalars(select(PortalFeePosting).where(PortalFeePosting.fee_source_id.in_([s.id for s in sources]))).all()
    if not postings: return False
    old = session.scalars(select(OperationsRecord).where(OperationsRecord.kind == 'METER_CORRECTION', OperationsRecord.status.in_(('APPROVED', 'COMPLETED')), OperationsRecord.building_id == dossier.building_id)).all()
    if any(c.data.get('effective_readings') and set(c.data['effective_readings']) & {str(r.id) for r in affected} for c in old):
        raise AppError('ERR-METER-FINANCIAL-CORRECTION', 'Khoảng đo đã có hiệu chỉnh tài chính; cần giải quyết hồ sơ đó trước khi lập điều chỉnh khác.', 409)
    adjusted = {str(reading.id): {'value': str(corrected), 'consumption': str((corrected-base)*meter.multiplier)}}
    if after:
        after_value = effective_reading(session, after).value
        adjusted[str(after.id)] = {'value': str(after_value), 'consumption': str((after_value-corrected)*meter.multiplier)}
    credits, debits = [], []
    for source in sources:
        tariff = session.get(FeePolicyVersion, UUID(source.policy_snapshot['tariff_version_id']))
        quantity = Decimal(adjusted[str(source.source_id)]['consumption'])
        rate = source.policy_snapshot['unit_rate_vnd']; rounding = source.policy_snapshot['rounding_unit_vnd']
        amount = int((quantity*rate*Decimal(source.policy_snapshot.get('benefit_factor', '1'))/rounding).quantize(Decimal(1), rounding=ROUND_HALF_UP))*rounding
        if not 0 <= amount <= 999999999999:
            raise AppError('ERR-METER-RANGE', 'Tiền hiệu chỉnh vượt giới hạn.', 422)
        delta = amount-source.amount_vnd
        posted = [p for p in postings if p.fee_source_id == source.id]
        if not posted:
            source.amount_vnd = amount; source.policy_snapshot = {**source.policy_snapshot, **adjusted[str(source.source_id)], 'correction_record_id': str(dossier.id), 'amount_vnd': amount}; source.version += 1
            continue
        if len(posted) != 1:
            raise AppError('ERR-METER-FINANCIAL-CORRECTION', 'Nguồn đo phải gắn đúng một hóa đơn.', 409)
        invoice = session.scalar(select(BillingInvoice).where(BillingInvoice.id == posted[0].invoice_id).with_for_update())
        if invoice.status == 'VOID':
            raise AppError('ERR-METER-FINANCIAL-CORRECTION', 'Hóa đơn đã hủy; cần xử lý hồ sơ tài chính hiện hành.', 409)
        source_reading = next(r for r in affected if r.id == source.source_id)
        values = scope_values(context, building_id=source_reading.building_id); values['unit_id'] = source_reading.unit_id
        if delta < 0:
            credit = PortalFinancialAdjustment(**values, kind='CREDIT', invoice_id=invoice.id, period_id=invoice.accounting_period_id,
                amount_vnd=-delta, reason='Hiệu chỉnh đồng hồ ' + str(dossier.id), requested_by_id=dossier.account_id)
            session.add(credit); session.flush(); credits.append(str(credit.id))
        elif delta > 0:
            origin = SimpleNamespace(id=uuid5(dossier.id, str(source.id)), **{k: getattr(source_reading, k) for k in ('tenant_id', 'site_id', 'building_id', 'unit_id', 'account_id')})
            fee = create_fee_source(session, origin, 'METER_CORRECTION', delta, 'Chênh lệch chỉ số ' + meter.code,
                {'correction_record_id': str(dossier.id), 'original_invoice_id': str(invoice.id), 'original_fee_source_id': str(source.id), 'delta_vnd': delta, 'effective_reading': adjusted[str(source.source_id)]})
            session.flush(); debits.append(str(fee.id))
    dossier.data = {**dossier.data, 'effective_readings': adjusted, 'credit_adjustment_ids': credits, 'additional_fee_source_ids': debits,
        'financial_status': 'DRAFTS_REQUIRE_FINANCE_APPROVAL', 'preserved_source_reading_ids': [str(r.id) for r in affected]}
    return True


def refresh_sources(session, sources, readings, meter):
    by_id = {r.id: r for r in readings}
    for source in sources:
        tariff = session.get(FeePolicyVersion, UUID(source.policy_snapshot['tariff_version_id']))
        snapshot = price_snapshot(session, by_id[source.source_id], meter, tariff)
        source.amount_vnd = snapshot['amount_vnd']; source.policy_snapshot = snapshot; source.version += 1
