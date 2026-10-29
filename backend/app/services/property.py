"""Apply checked property dossiers without rewriting issued financial records."""
from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import func, or_, select, update
from app.core.exceptions import AppError
from app.core.policy import scope_not_found
from app.models.account import Account
from app.models.billing import AccountingPeriod, BillingAccount, BillingInvoice
from app.models.person import Person, UnitPersonRelationship
from app.models.property import LeaseContract, PersonMerge, UnitProfileEpisode
from app.models.resident_portal import LiabilityEpisode
from app.models.unit import Unit
from app.services.portal_finance import business_date
from app.services.resident_portal import scope_values

PROPERTY_KINDS = {'LEASE', 'LEASE_RENEW', 'LEASE_AMEND', 'LEASE_TERMINATE', 'LIABILITY_CHANGE',
    'UNIT_PROFILE', 'HANDOVER', 'UNIT_STATUS', 'PERSON_MERGE'}


def renovation_permission(session,unit,operation):
    if unit.status!='UNDER_RENOVATION':return
    from app.models.resident_portal import PortalDossier
    active=session.scalar(select(PortalDossier).where(PortalDossier.unit_id==unit.id,
        PortalDossier.kind=='RENOVATION',PortalDossier.status=='IN_PROGRESS'))
    if active is None or operation not in active.data.get('allowed_operations',[]):
        raise AppError('ERR-RENOVATION-RESTRICTED','Căn đang thi công; nghiệp vụ chưa được BQL cho phép trong hồ sơ cải tạo.',409)


def person_family(session, tenant_id, person_id):
    edges = session.execute(select(PersonMerge.source_person_id, PersonMerge.target_person_id)
        .where(PersonMerge.tenant_id == tenant_id)).all()
    family = {person_id}
    changed = True
    while changed:
        changed = False
        for source, target in edges:
            if source in family or target in family:
                if not {source, target} <= family:
                    family.update((source, target)); changed = True
    return family


def resolve_person(session, tenant_id, value):
    try:
        identifier = UUID(str(value))
    except (TypeError, ValueError):
        raise AppError('ERR-PROPERTY-DATA', 'Cần mã hồ sơ người hợp lệ.', 422) from None
    person = session.scalar(select(Person).where(Person.id == identifier, Person.tenant_id == tenant_id))
    if person is None:
        raise scope_not_found()
    return person


def _assert_financial_date(session, row):
    posted = session.scalar(select(BillingInvoice.id).join(AccountingPeriod, AccountingPeriod.id == BillingInvoice.accounting_period_id)
        .join(BillingAccount, BillingAccount.id == BillingInvoice.billing_account_id).where(
            BillingAccount.unit_id == row.unit_id, BillingInvoice.status.not_in(('DRAFT', 'VOID')),
            AccountingPeriod.period_end >= row.valid_from).limit(1))
    if posted:
        raise AppError('ERR-PROPERTY-POSTED-PERIOD', 'Ngày thay đổi ảnh hưởng hóa đơn đã phát hành; cần hồ sơ điều chỉnh tài chính riêng.', 409)


def set_profile(session, row, unit, data):
    if unit.status == 'UNDER_RENOVATION':
        raise AppError('ERR-RENOVATION-STATE', 'Cần nghiệm thu đợt cải tạo trước khi thay đổi hồ sơ căn.', 409)
    if set(data) & {'area_m2','net_area_m2','gross_area_m2'}:
        _assert_financial_date(session, row)
    episodes = session.scalars(select(UnitProfileEpisode).where(UnitProfileEpisode.unit_id == unit.id)
        .order_by(UnitProfileEpisode.valid_from).with_for_update()).all()
    if episodes and (episodes[-1].valid_from >= row.valid_from or episodes[-1].valid_to is not None):
        raise AppError('ERR-PROPERTY-HISTORY', 'Ngày thay đổi xung đột lịch sử căn đã xác nhận.', 409)
    prior = episodes[-1] if episodes else None
    if prior is None and row.valid_from > date.min and unit.area_m2 > 0:
        session.add(UnitProfileEpisode(**scope_values_from_row(row), valid_from=date.min, valid_to=row.valid_from,
            area_m2=Decimal(str(unit.area_m2)), use_purpose='Chưa xác minh', operating_status=unit.status,
            reason='LEGACY_BASELINE: giá trị được lưu trước điều chỉnh; chưa có lịch cũ.'))
    if prior:
        prior.valid_to = row.valid_from
        prior.version += 1
    values = dict(area_m2=Decimal(str(prior.area_m2 if prior else unit.area_m2)),
        net_area_m2=prior.net_area_m2 if prior else None, gross_area_m2=prior.gross_area_m2 if prior else None,
        use_purpose=prior.use_purpose if prior else 'Chưa xác minh', operating_status=prior.operating_status if prior else unit.status)
    values.update({k: v for k, v in data.items() if k in values})
    session.add(UnitProfileEpisode(**scope_values_from_row(row), dossier_id=row.id,
        valid_from=row.valid_from, valid_to=row.valid_to, reason=row.decision_reason or row.title, **values))
    if row.valid_to:
        restored = dict(area_m2=prior.area_m2 if prior else Decimal(str(unit.area_m2)),
            net_area_m2=prior.net_area_m2 if prior else None, gross_area_m2=prior.gross_area_m2 if prior else None,
            use_purpose=prior.use_purpose if prior else 'Chưa xác minh', operating_status=prior.operating_status if prior else unit.status)
        session.add(UnitProfileEpisode(**scope_values_from_row(row), dossier_id=row.id,
            valid_from=row.valid_to, valid_to=None, reason='Kết thúc thay đổi có thời hạn: ' + row.title, **restored))
    if row.valid_from <= business_date():
        unit.area_m2 = float(values['area_m2']); unit.status = values['operating_status']; unit.version += 1


def scope_values_from_row(row):
    return {k: getattr(row, k) for k in ('tenant_id','site_id','building_id','unit_id','account_id')}


def apply_property(session, context, row, unit):
    data = row.data
    if row.kind in {'LEASE','LEASE_RENEW','LEASE_AMEND','LEASE_TERMINATE'}:
        previous = None
        if row.kind != 'LEASE':
            previous = session.scalar(select(LeaseContract).where(LeaseContract.id == UUID(data['lease_id']),
                LeaseContract.unit_id == unit.id, LeaseContract.tenant_id == row.tenant_id).with_for_update())
            if previous is None:
                raise scope_not_found()
            if previous.status != 'ACTIVE' and not (row.kind == 'LEASE_RENEW' and previous.status == 'EXPIRED'):
                raise AppError('ERR-LEASE-STATE', 'Hợp đồng không còn hiệu lực để thay đổi.', 409)
        if row.kind == 'LEASE_TERMINATE':
            if not previous.valid_from < row.valid_from <= previous.valid_to:
                raise AppError('ERR-LEASE-DATE', 'Ngày thanh lý nằm ngoài hợp đồng.', 409)
            previous.status = 'TERMINATED'; previous.terminated_on = row.valid_from; previous.version += 1
            return
        if row.valid_to is None:
            raise AppError('ERR-LEASE-DATE', 'Hợp đồng cần ngày kết thúc.', 422)
        if previous:
            if row.kind == 'LEASE_RENEW' and row.valid_from != previous.valid_to:
                raise AppError('ERR-LEASE-DATE', 'Gia hạn bắt đầu tại ngày hợp đồng trước kết thúc.', 409)
            if row.kind == 'LEASE_AMEND' and not previous.valid_from < row.valid_from < previous.valid_to:
                raise AppError('ERR-LEASE-DATE', 'Phụ lục cần mốc mới trong khoảng hợp đồng.', 409)
            previous.status = 'SUPERSEDED'; previous.terminated_on = row.valid_from; previous.version += 1
            lessee = resolve_person(session, row.tenant_id, data.get('target_person_id', previous.lessee_person_id))
            lessor = previous.lessor_person_id
        else:
            lessee = resolve_person(session, row.tenant_id, data['target_person_id']); lessor = row.person_id
        if lessee.id == lessor:
            raise AppError('ERR-LEASE-PARTIES', 'Bên thuê cần khác bên cho thuê.', 422)
        overlap = session.scalar(select(LeaseContract.id).where(LeaseContract.unit_id == unit.id,
            LeaseContract.status == 'ACTIVE', LeaseContract.valid_from < row.valid_to,
            LeaseContract.valid_to > row.valid_from).limit(1))
        if overlap:
            raise AppError('ERR-LEASE-OVERLAP', 'Khoảng thuê chồng hợp đồng đang hiệu lực; cần giải quyết hồ sơ trước.', 409)
        session.add(LeaseContract(**scope_values_from_row(row), dossier_id=row.id,
            previous_id=previous.id if previous else None, lessor_person_id=lessor, lessee_person_id=lessee.id,
            reference=data['contract_reference'], terms=data.get('terms', {}), valid_from=row.valid_from, valid_to=row.valid_to))
    elif row.kind == 'LIABILITY_CHANGE':
        _assert_financial_date(session, row)
        payer = resolve_person(session, row.tenant_id, data['liable_person_id'])
        old = session.scalars(select(LiabilityEpisode).where(LiabilityEpisode.unit_id == unit.id,
            or_(LiabilityEpisode.valid_to.is_(None), LiabilityEpisode.valid_to > row.valid_from)).with_for_update()).all()
        if any(r.valid_from >= row.valid_from or r.valid_to is not None for r in old):
            raise AppError('ERR-LIABILITY-OVERLAP', 'Ngày thay người chịu phí chồng lịch đã xác nhận.', 409)
        for episode in old:
            episode.valid_to = row.valid_from
            episode.version += 1
        session.add(LiabilityEpisode(**scope_values_from_row(row), dossier_id=row.id, person_id=payer.id,
            valid_from=row.valid_from, valid_to=row.valid_to))
    elif row.kind in {'UNIT_PROFILE','HANDOVER','UNIT_STATUS'}:
        if row.kind == 'HANDOVER':
            data = {'operating_status': 'HANDED_OVER'}
        set_profile(session, row, unit, data)
    elif row.kind == 'PERSON_MERGE':
        context.assert_role('admin','director')
        session.execute(select(func.pg_advisory_xact_lock(int.from_bytes(str(row.tenant_id).encode()[:8], 'big', signed=True))))
        source = resolve_person(session, row.tenant_id, data['source_person_id'])
        target = resolve_person(session, row.tenant_id, data['target_person_id'])
        family = person_family(session, row.tenant_id, source.id) | person_family(session, row.tenant_id, target.id)
        if source.id in person_family(session, row.tenant_id, target.id) or session.scalar(select(PersonMerge.id).where(PersonMerge.source_person_id == source.id)):
            raise AppError('ERR-PERSON-MERGE', 'Hai hồ sơ đã cùng một danh tính hợp nhất.', 409)
        # All relationships of both identities must be inside the approver's scope.
        unit_ids = set(session.scalars(select(UnitPersonRelationship.unit_id).where(
            UnitPersonRelationship.person_id.in_(family))))
        allowed = set(session.scalars(context.units_query().with_only_columns(Unit.id)))
        if not unit_ids or not unit_ids <= allowed:
            raise scope_not_found()
        session.add(PersonMerge(**scope_values_from_row(row), dossier_id=row.id, source_person_id=source.id,
            target_person_id=target.id, evidence_reference=data['evidence_reference']))
        # Current login identity changes; historical relationships and invoice snapshots stay linked to their original IDs.
        session.execute(update(Account).where(Account.tenant_id == row.tenant_id, Account.person_id == source.id).values(person_id=target.id))
