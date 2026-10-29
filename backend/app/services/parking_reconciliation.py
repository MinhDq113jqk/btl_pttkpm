"""Compare a current registration snapshot with declared usage observations."""
import hashlib
import json
from collections import Counter, defaultdict
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.core.exceptions import AppError
from app.core.policy import context_for_account
from app.models.account import Account
from app.models.account_parking import ParkingUsageBatch
from app.models.operational_control import ParkingSlot, VisitorParking
from app.models.resident_portal import VehicleRegistration
from app.services.resident_portal import view


def digest(value):
    return hashlib.sha256(json.dumps(jsonable_encoder(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def collect(session, resource, starts_at, ends_at, as_of, require_slots, policy_reference):
    def resource_scope(model):
        return (model.resource_id == resource.id, model.tenant_id == resource.tenant_id,
            model.site_id == resource.site_id, model.building_id == resource.building_id)
    vehicles = session.scalars(select(VehicleRegistration).where(*resource_scope(VehicleRegistration)).order_by(VehicleRegistration.id)).all()
    slots = session.scalars(select(ParkingSlot).where(*resource_scope(ParkingSlot)).order_by(ParkingSlot.id)).all()
    batches = session.scalars(select(ParkingUsageBatch).where(*resource_scope(ParkingUsageBatch),
        ParkingUsageBatch.starts_at < ends_at, ParkingUsageBatch.ends_at > starts_at).order_by(ParkingUsageBatch.id)).all()
    visitors = session.scalars(select(VisitorParking).where(*resource_scope(VisitorParking),
        VisitorParking.status == 'ENTERED').order_by(VisitorParking.id)).all()
    owner_validity = {}
    for vehicle in vehicles:
        owner = session.get(Account, vehicle.account_id)
        try:
            ctx = context_for_account(session, owner, vehicle.site_id) if owner and owner.is_active else None
            valid = ctx is not None and vehicle.unit_id in ctx.resident_units_for('parking')
        except AppError:
            valid = False
        owner_validity[str(vehicle.id)] = valid
    # Snapshot contains no password, session token or unscoped person details.
    snapshot = jsonable_encoder({'resource': view(resource), 'vehicles': [view(v) for v in vehicles],
        'slots': [view(s) for s in slots], 'usage_batches': [view(b) for b in batches], 'visitors_occupying': [view(v) for v in visitors],
        'owner_validity': owner_validity, 'starts_at': starts_at, 'ends_at': ends_at,
        'require_slots': require_slots, 'policy_reference': policy_reference,
        'comparison': 'CURRENT_REGISTRATIONS_TO_OBSERVATIONS'})
    findings = []
    def add(code, source):
        source = {'resource': {'id': str(resource.id), 'version': resource.version, 'status': resource.status,
            'capacity': resource.capacity, 'policy': resource.policy}, **source}
        source = jsonable_encoder(source)
        findings.append({'code': code, 'source': source, 'fingerprint': digest({'code': code, 'source': source})})
    by_id = {v.id: v for v in vehicles}
    by_plate = defaultdict(list)
    assigned = defaultdict(list)
    held = [v for v in vehicles if v.status in ('ACTIVE', 'PAUSED') or
        v.status == 'OFFERED' and v.offer_expires_at and v.offer_expires_at > as_of]
    for v in vehicles:
        if v.status != 'CANCELLED':
            by_plate[v.plate].append(v)
        if v.status == 'OFFERED' and (v.offer_expires_at is None or v.offer_expires_at <= as_of):
            add('EXPIRED_OFFER', {'vehicle': view(v)})
        if v.status in ('ACTIVE', 'PAUSED', 'OFFERED') and not owner_validity[str(v.id)]:
            add('OWNER_AUTHORITY', {'vehicle': view(v), 'owner_valid': False})
    for plate, rows in by_plate.items():
        if len(rows) > 1:
            add('DUPLICATE_PLATE', {'plate': plate, 'vehicles': [view(v) for v in rows]})
    for slot in slots:
        if not slot.vehicle_id:
            continue
        assigned[slot.vehicle_id].append(slot)
        v = by_id.get(slot.vehicle_id)
        if (v is None or v.status not in ('ACTIVE', 'PAUSED') or slot.status != 'OPEN'
            or v.vehicle_type not in slot.vehicle_types or v.building_id != slot.building_id
            or not owner_validity[str(v.id)]):
            add('INVALID_SLOT', {'slot': view(slot), 'vehicle': view(v) if v else None,
                'owner_valid': owner_validity.get(str(slot.vehicle_id), False)})
    for vehicle_id, rows in assigned.items():
        if len(rows) > 1:
            add('DUPLICATE_ASSIGNMENT', {'vehicle_id': str(vehicle_id), 'slots': [view(s) for s in rows]})
    if require_slots:
        for v in held:
            if v.status in ('ACTIVE', 'PAUSED') and not assigned[v.id]:
                add('MISSING_SLOT', {'vehicle': view(v), 'owner_valid': owner_validity[str(v.id)], 'policy_reference': policy_reference})
    capacity_source = {'resource': view(resource), 'held': [view(v) for v in held], 'visitors': [view(v) for v in visitors]}
    if len(held) + len(visitors) > resource.capacity or len(slots) > resource.capacity:
        add('CAPACITY_EXCEEDED', {**capacity_source, 'slot_count': len(slots)})
    for unit_id, quantity in Counter(v.unit_id for v in held).items():
        if quantity > resource.policy['quota_per_unit']:
            add('QUOTA_EXCEEDED', {'unit_id': str(unit_id), 'quota': resource.policy['quota_per_unit'],
                'vehicles': [view(v) for v in held if v.unit_id == unit_id]})
    observations = defaultdict(list)
    for batch in batches:
        for entry in batch.entries:
            from datetime import datetime
            moment = datetime.fromisoformat(entry['occurred_at'])
            if not starts_at <= moment < ends_at:
                continue
            source = {'batch_id': str(batch.id), 'source_reference': batch.source_reference, 'entry': entry}
            observations[entry['event_reference']].append(source)
            matches = by_plate.get(entry['plate'], [])
            if len(matches) != 1:
                add('USAGE_UNMATCHED', source)
                continue
            v = matches[0]
            if (entry.get('unit_id') and entry['unit_id'] != str(v.unit_id) or
                entry.get('holder_account_id') and entry['holder_account_id'] != str(v.account_id)):
                add('USAGE_OWNER_MISMATCH', {**source, 'vehicle': view(v)})
            if entry.get('slot_code') and not any(s.code == entry['slot_code'] for s in assigned[v.id]):
                add('USAGE_SLOT_MISMATCH', {**source, 'vehicle': view(v), 'assigned_slots': [view(s) for s in assigned[v.id]]})
            if v.status != 'ACTIVE':
                add('USAGE_STATUS_REVIEW', {**source, 'vehicle': view(v)})
    for reference, entries in observations.items():
        if len(entries) > 1:
            add('DUPLICATE_USAGE', {'event_reference': reference, 'observations': entries})
    # COMPLETE applies only to declared source coverage; an empty/partial log is
    # never interpreted as a vehicle not using its registration.
    cursor = starts_at
    for start, end in sorted((b.starts_at, b.ends_at) for b in batches if b.completeness == 'COMPLETE'):
        if start > cursor:
            break
        cursor = max(cursor, end)
    snapshot['usage_data_status'] = 'COMPLETE' if cursor >= ends_at else 'PARTIAL' if batches else 'MISSING'
    snapshot['held_count'] = len(held); snapshot['visitor_count'] = len(visitors)
    snapshot['effective_offer_ids'] = [str(v.id) for v in held if v.status == 'OFFERED']
    return snapshot, sorted(findings, key=lambda f: f['fingerprint'])
