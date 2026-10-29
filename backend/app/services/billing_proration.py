"""Calendar-day proration with exact arithmetic and one rounding per rule."""
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction


def calculate_proration(period_start: date, period_end: date, segments: list[dict]) -> dict:
    """Periods include both dates; source intervals use [starts_on, ends_on)."""
    if period_end < period_start:
        raise ValueError("Invalid accounting period")
    period_stop = period_end + timedelta(days=1)
    period_days = (period_stop - period_start).days
    items = []
    previous_stop = None
    for segment in sorted(segments, key=lambda row: (row["starts_on"], str(row["key"]))):
        start = max(period_start, segment["starts_on"])
        stop = min(period_stop, segment.get("ends_on") or period_stop)
        if stop <= start:
            continue
        if previous_stop is not None and start < previous_stop:
            raise ValueError("Overlapping fee intervals")
        previous_stop = stop
        days = (stop - start).days
        quantity = Decimal(str(segment.get("quantity", 1)))
        rate = segment["amount_vnd"]
        unit = segment.get("rounding_unit_vnd", 1)
        if quantity <= 0 or type(rate) is not int or rate < 0 or type(unit) is not int or unit < 1:
            raise ValueError("Invalid fee basis or rounding rule")
        raw = Fraction(quantity) * rate * Fraction(days, period_days)
        items.append({"key": str(segment["key"]), "starts_on": start.isoformat(),
            "ends_on": stop.isoformat(), "days": days, "quantity": str(quantity),
            "rate_vnd": rate, "rounding_unit_vnd": unit,
            "raw_numerator": raw.numerator, "raw_denominator": raw.denominator,
            "amount_vnd": (raw.numerator // (raw.denominator * unit)) * unit})
    groups = []
    for unit in sorted({item["rounding_unit_vnd"] for item in items}):
        group = [item for item in items if item["rounding_unit_vnd"] == unit]
        raw = sum((Fraction(item["raw_numerator"], item["raw_denominator"]) for item in group), Fraction())
        rounded = ((2 * raw.numerator + raw.denominator * unit) // (2 * raw.denominator * unit)) * unit
        remainder = (rounded - sum(item["amount_vnd"] for item in group)) // unit
        order = sorted(group, key=lambda item: (
            -(Fraction(item["raw_numerator"], item["raw_denominator"]) / unit - item["amount_vnd"] // unit), item["key"]))
        for item in order[:remainder]:
            item["amount_vnd"] += unit
        groups.append({"rounding_unit_vnd": unit, "raw_numerator": raw.numerator,
            "raw_denominator": raw.denominator, "amount_vnd": rounded})
    return {"method": "ACTUAL_DAYS", "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(), "period_days": period_days,
        "active_days": sum(item["days"] for item in items), "segments": items,
        "rounding_groups": groups, "amount_vnd": sum(item["amount_vnd"] for item in items)}
