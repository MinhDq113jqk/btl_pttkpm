"""Temporal meter points and equal-window reconciliation. Missing values stay unknown."""
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from app.core.exceptions import AppError
from app.models.operational_control import Meter, MeterReading, MeterAssignment
from app.services.resident_portal import view


def assignment_for_interval(session, meter, start, end):
    rows = session.scalars(select(MeterAssignment).where(MeterAssignment.meter_id == meter.id,
        MeterAssignment.valid_from <= start)).all()
    matches = [a for a in rows if a.valid_to is None or a.valid_to >= end]
    if len(matches) != 1:
        raise AppError('ERR-METER-ASSIGNMENT', 'Khoảng đo chưa có một lịch gắn đồng hồ phủ đầy đủ.', 409)
    return matches[0]


def reconciliation(session, parent, starts_on, ends_on):
    if ends_on <= starts_on:
        raise AppError('ERR-METER-INTERVAL', 'Cần hai mốc đo khác nhau.', 422)
    children = session.scalars(select(Meter).where(Meter.upstream_id == parent.id, Meter.tenant_id == parent.tenant_id, Meter.site_id == parent.site_id)).all()
    def measured(meter):
        rows = session.scalars(select(MeterReading).where(MeterReading.meter_id == meter.id,
            MeterReading.status == 'VERIFIED', MeterReading.read_on >= starts_on, MeterReading.read_on <= ends_on).order_by(MeterReading.read_on)).all()
        from app.services.meter_billing import effective_reading
        rows_for_value = [effective_reading(session, r) for r in rows]
        assignments = session.scalars(select(MeterAssignment).where(MeterAssignment.meter_id == meter.id, MeterAssignment.valid_from < ends_on)).all()
        assignments = sorted([a for a in assignments if a.valid_to is None or a.valid_to > starts_on], key=lambda a: a.valid_from)
        segments = []
        for assignment in assignments:
            start, end = max(starts_on, assignment.valid_from), min(ends_on, assignment.valid_to or ends_on)
            first = next((r.value for r in rows_for_value if r.read_on == start), meter.baseline if meter.valid_from == start else None)
            last = next((r.value for r in rows_for_value if r.read_on == end), None)
            segments.append({'assignment_id': str(assignment.id), 'point': assignment.point, 'unit_id': str(assignment.unit_id) if assignment.unit_id else None,
                'starts_on': start, 'ends_on': end, 'consumption': (last-first)*meter.multiplier if first is not None and last is not None else None})
        complete = bool(segments) and all(s['consumption'] is not None for s in segments)
        return {'meter_id': str(meter.id), 'replaces_id': str(meter.replaces_id) if meter.replaces_id else None, 'commodity': meter.commodity,
                'status': 'COMPLETE' if complete else 'MISSING_BOUNDARY_OR_ASSIGNMENT', 'segments': segments,
                'consumption': sum((s['consumption'] for s in segments), Decimal(0)) if complete else None, 'readings': [view(r) for r in rows]}
    upstream, downstream = measured(parent), [measured(c) for c in children]
    downstream = [c for c in downstream if c['segments']]
    def covers(items):
        spans = sorted((s['starts_on'], s['ends_on']) for item in items for s in item['segments'])
        cursor = starts_on
        for start, end in spans:
            if start != cursor: return False
            cursor = end
        return cursor == ends_on
    by_id = {c['meter_id']: c for c in downstream}
    groups = {}
    for child in downstream:
        root = child
        seen = set()
        while root['replaces_id'] in by_id and root['meter_id'] not in seen:
            seen.add(root['meter_id']); root = by_id[root['replaces_id']]
        groups.setdefault(root['meter_id'], []).append(child)
    complete = upstream['consumption'] is not None and covers([upstream]) and bool(groups) and all(c['consumption'] is not None and c['commodity'] == parent.commodity for c in downstream) and all(covers(group) for group in groups.values())
    difference = upstream['consumption'] - sum((c['consumption'] for c in downstream), Decimal(0)) if complete else None
    return {'starts_on': starts_on, 'ends_on': ends_on, 'upstream': upstream, 'downstream': downstream,
            'difference': difference, 'status': 'COMPLETE' if complete else 'INCOMPLETE',
            'needs_review': difference is None or difference != 0, 'policy_threshold': None}
