"""Deterministic normalization boundary for the FCS-04 submission contract.

The loader will call this module before resolving database identities.  It is
deliberately independent from SQLAlchemy and from the XLSX reader so the same
rules can be used by preflight, dry-run and apply.  No function in this module
performs a database write or logs source values.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, tzinfo
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import Literal, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


NORMALIZATION_VERSION = "fcs04-r1"
DEFAULT_SITE_TIMEZONE = "Asia/Ho_Chi_Minh"
VND_QUANTUM = Decimal("1")
AREA_QUANTUM = Decimal("0.01")
QUANTITY_QUANTUM = Decimal("0.0001")
OWNERSHIP_QUANTUM = Decimal("0.0001")
AREA_STORAGE_POLICY = "FLOAT_QUANTIZED_0_01"

TokenCase = Literal["lower", "preserve"]
TemporalDisposition = Literal["historical_replay", "scheduled_future"]

ROLE_VALUES = (
    "admin", "director", "cskh", "accountant", "technical_lead",
    "technician", "cleaning", "security", "resident",
)
RELATIONSHIP_VALUES = ("owner", "tenant", "family_member")

# These fields are never allowed to become an identity key.  A name or a
# contact can change and is also PII; identity must use a source code/reference.
PII_KEY_FIELDS = frozenset({
    "full_name",
    "email",
    "email_masked",
    "phone",
    "phone_masked",
    "recipient_name_snapshot",
    "recipient_contact_masked",
})


class NormalizationError(ValueError):
    """A source value cannot satisfy the FCS-04 canonical form."""

    def __init__(self, code: str, field: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.message = message


def _error(code: str, field: str, message: str) -> NormalizationError:
    return NormalizationError(code, field, message)


def normalize_text(
    value: object,
    *,
    field: str,
    required: bool = True,
    max_length: int | None = None,
    strict: bool = True,
) -> str | None:
    """Return trimmed text and reject implicit PII/number coercion by default."""

    if value is None:
        if required:
            raise _error("REQUIRED", field, "Giá trị bắt buộc bị thiếu.")
        return None
    if isinstance(value, bool):
        raise _error("TEXT_NOT_STRING", field, "Giá trị phải là chuỗi.")
    if isinstance(value, str):
        text = value.strip()
    elif not strict and isinstance(value, (int, float, Decimal)):
        text = str(value).strip()
    else:
        raise _error("TEXT_NOT_STRING", field, "Giá trị phải là chuỗi.")
    if not text:
        if required:
            raise _error("REQUIRED", field, "Giá trị bắt buộc bị thiếu.")
        return None
    if max_length is not None and len(text) > max_length:
        raise _error("TEXT_TOO_LONG", field, "Giá trị vượt quá độ dài cho phép.")
    return text


def normalize_enum(
    value: object,
    allowed: tuple[str, ...] | frozenset[str],
    *,
    field: str,
    output_case: TokenCase = "lower",
) -> str:
    """Normalize an enum case-insensitively with an explicit output policy."""

    text = normalize_text(value, field=field)
    assert text is not None
    by_fold = {item.casefold(): item for item in allowed}
    canonical = by_fold.get(text.casefold())
    if canonical is None:
        raise _error("ENUM_INVALID", field, "Giá trị không thuộc enum đã khóa.")
    return canonical.casefold() if output_case == "lower" else canonical


def normalize_role(value: object) -> str:
    return normalize_enum(value, ROLE_VALUES, field="role", output_case="lower")


def normalize_relationship_type(value: object) -> str:
    return normalize_enum(
        value, RELATIONSHIP_VALUES, field="relationship_type", output_case="lower",
    )


def normalize_status(
    value: object,
    allowed: tuple[str, ...] | frozenset[str],
    *,
    field: str = "status",
) -> str:
    """Return the semantic status token in lowercase for comparison."""

    return normalize_enum(value, allowed, field=field, output_case="lower")


def target_enum(
    value: object,
    allowed: tuple[str, ...] | frozenset[str],
    *,
    field: str,
) -> str:
    """Return the exact target enum spelling after case-insensitive validation."""

    return normalize_enum(value, allowed, field=field, output_case="preserve")


def normalize_phone_text(value: object, *, field: str = "phone") -> str:
    """Read phone/contact columns as text so a leading zero is never invented."""

    result = normalize_text(value, field=field, strict=True, max_length=100)
    assert result is not None
    return result


def normalize_decimal(
    value: object,
    *,
    field: str,
    quantum: Decimal,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
    allow_none: bool = False,
) -> Decimal | None:
    """Parse through Decimal(str(value)) and quantize deterministically."""

    if value is None or (isinstance(value, str) and not value.strip()):
        if allow_none:
            return None
        raise _error("DECIMAL_REQUIRED", field, "Số thập phân bắt buộc bị thiếu.")
    if isinstance(value, bool):
        raise _error("DECIMAL_INVALID", field, "Giá trị số không hợp lệ.")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise _error("DECIMAL_INVALID", field, "Giá trị số không hợp lệ.") from None
    if not parsed.is_finite():
        raise _error("DECIMAL_INVALID", field, "Giá trị số không hữu hạn.")
    try:
        canonical = parsed.quantize(quantum, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise _error("DECIMAL_INVALID", field, "Giá trị số không thể chuẩn hóa.") from None
    if minimum is not None and canonical < minimum:
        raise _error("DECIMAL_RANGE", field, "Giá trị số nhỏ hơn giới hạn cho phép.")
    if maximum is not None and canonical > maximum:
        raise _error("DECIMAL_RANGE", field, "Giá trị số lớn hơn giới hạn cho phép.")
    return canonical


def normalize_money_vnd(value: object, *, field: str = "amount_vnd") -> Decimal:
    result = normalize_decimal(
        value, field=field, quantum=VND_QUANTUM, minimum=Decimal("0"),
    )
    assert result is not None
    return result


def normalize_quantity(value: object, *, field: str = "quantity") -> Decimal:
    result = normalize_decimal(
        value, field=field, quantum=QUANTITY_QUANTUM, minimum=Decimal("0"),
    )
    assert result is not None
    return result


def normalize_area_m2(value: object, *, field: str = "area_m2") -> Decimal:
    """Canonical area; the current Float column receives only this quantized value."""

    result = normalize_decimal(
        value,
        field=field,
        quantum=AREA_QUANTUM,
        minimum=AREA_QUANTUM,
        maximum=Decimal("100000"),
    )
    assert result is not None
    return result


def area_m2_storage_value(value: object, *, field: str = "area_m2") -> float:
    """Adapt canonical Decimal area to the current Unit.area_m2 Float column."""

    return float(normalize_area_m2(value, field=field))


def normalize_ownership_ratio(
    value: object,
    relationship_type: object,
    *,
    field: str = "ownership_ratio",
) -> Decimal | None:
    """Apply the database invariant: non-owner zero becomes SQL NULL."""

    relationship = normalize_relationship_type(relationship_type)
    if value is None or (isinstance(value, str) and not value.strip()):
        if relationship != "owner":
            return None
        raise _error("OWNERSHIP_REQUIRED", field, "Owner phải có ownership_ratio.")
    ratio = normalize_decimal(
        value,
        field=field,
        quantum=OWNERSHIP_QUANTUM,
        minimum=Decimal("0"),
        maximum=Decimal("1"),
    )
    assert ratio is not None
    if relationship != "owner":
        if ratio == 0:
            return None
        raise _error(
            "OWNERSHIP_NON_OWNER",
            field,
            "Non-owner chỉ được có ratio bằng 0 hoặc NULL.",
        )
    if ratio <= 0:
        raise _error("OWNERSHIP_OWNER_RANGE", field, "Owner phải có ratio lớn hơn 0.")
    return ratio


def _resolve_timezone(value: str | tzinfo) -> tzinfo:
    if isinstance(value, str):
        try:
            return ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise _error("TIMEZONE_INVALID", "site_timezone", "Timezone không được hỗ trợ.") from None
    if not isinstance(value, tzinfo):
        raise _error("TIMEZONE_INVALID", "site_timezone", "Timezone không được hỗ trợ.")
    return value


def _as_of_utc(value: datetime | None) -> datetime:
    result = datetime.now(UTC) if value is None else value
    if result.tzinfo is None or result.utcoffset() is None:
        raise _error("AS_OF_NAIVE", "as_of_utc", "Mốc as_of phải có timezone.")
    return result.astimezone(UTC)


@dataclass(frozen=True)
class TemporalNormalization:
    source_kind: Literal["date", "datetime"]
    local: datetime
    utc: datetime
    is_future: bool
    disposition: TemporalDisposition


def normalize_temporal(
    value: object,
    *,
    field: str,
    site_timezone: str | tzinfo = DEFAULT_SITE_TIMEZONE,
    as_of_utc: datetime | None = None,
    terminal_event: bool = False,
) -> TemporalNormalization:
    """Attach site timezone, convert to UTC and block future terminal events."""

    source_kind: Literal["date", "datetime"]
    if isinstance(value, datetime):
        source_kind = "datetime"
        parsed: datetime = value
    elif isinstance(value, date):
        source_kind = "date"
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        text = value.strip()
        try:
            if "T" in text or " " in text:
                source_kind = "datetime"
                parsed = datetime.fromisoformat(text)
            else:
                source_kind = "date"
                parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        except ValueError:
            raise _error("TIME_INVALID", field, "Giá trị ngày giờ không hợp lệ.") from None
    else:
        raise _error("TIME_INVALID", field, "Giá trị ngày giờ không hợp lệ.")

    timezone = _resolve_timezone(site_timezone)
    local = parsed.astimezone(timezone) if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone)
    utc = local.astimezone(UTC)
    is_future = utc > _as_of_utc(as_of_utc)
    if is_future and terminal_event:
        raise _error(
            "FUTURE_TERMINAL_EVENT",
            field,
            "Timestamp tương lai không được tạo terminal event.",
        )
    return TemporalNormalization(
        source_kind=source_kind,
        local=local,
        utc=utc,
        is_future=is_future,
        disposition="scheduled_future" if is_future else "historical_replay",
    )


def normalize_datetime_utc(
    value: object,
    *,
    field: str,
    site_timezone: str | tzinfo = DEFAULT_SITE_TIMEZONE,
    as_of_utc: datetime | None = None,
    terminal_event: bool = False,
) -> datetime:
    return normalize_temporal(
        value,
        field=field,
        site_timezone=site_timezone,
        as_of_utc=as_of_utc,
        terminal_event=terminal_event,
    ).utc


def normalize_date(value: object, *, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise _error("DATE_INVALID", field, "Giá trị ngày không hợp lệ.")


@dataclass(frozen=True)
class ExternalKeySpec:
    source: str
    scope_fields: tuple[str, ...]
    key_fields: tuple[str, ...]


EXTERNAL_KEY_SPECS: Mapping[str, ExternalKeySpec] = {
    "work": ExternalKeySpec("work", ("tenant_code", "site_code"), ("work_code",)),
    "employee": ExternalKeySpec("employee", ("tenant_code",), ("employee_code",)),
    "unit": ExternalKeySpec(
        "unit", ("tenant_code", "site_code", "building_code"), ("unit_number",),
    ),
    "resident": ExternalKeySpec("resident", ("tenant_code",), ("resident_code",)),
    "asset": ExternalKeySpec("asset", ("tenant_code", "site_code"), ("asset_code",)),
    "cleaning": ExternalKeySpec("cleaning", ("site_code",), ("shift_code",)),
    "patrol": ExternalKeySpec(
        "patrol", ("site_code", "building_code"),
        ("shift_code", "patrol_point_code", "window_start"),
    ),
    "incident": ExternalKeySpec("incident", ("site_code",), ("incident_code",)),
    "fee_policy": ExternalKeySpec(
        "fee_policy", ("site_code", "building_code"),
        ("fee_policy_code", "version_number"),
    ),
    "invoice": ExternalKeySpec(
        "invoice", ("site_code",), ("invoice_number", "line_code"),
    ),
    "payment": ExternalKeySpec(
        "payment", ("tenant_code", "site_code", "payment_source"),
        ("source_reference", "receipt_number"),
    ),
    "parcel": ExternalKeySpec("parcel", ("site_code",), ("parcel_code",)),
}


def _key_component(field: str, value: object) -> str:
    if field in PII_KEY_FIELDS:
        raise _error("PII_EXTERNAL_KEY", field, "Không được dùng trường PII làm external key.")
    if isinstance(value, datetime):
        text = value.astimezone(UTC).isoformat() if value.tzinfo is not None else value.isoformat()
    elif isinstance(value, date):
        text = value.isoformat()
    elif isinstance(value, (int, Decimal)) and not isinstance(value, bool):
        text = str(value)
    else:
        text = normalize_text(value, field=field, strict=True)
        assert text is not None
    return text.casefold()


def build_external_key(spec: ExternalKeySpec, values: Mapping[str, object]) -> str:
    """Build an idempotent, scope-aware key from non-PII source references."""

    fields = (*spec.scope_fields, *spec.key_fields)
    if len(fields) != len(set(fields)):
        raise _error("KEY_SPEC_INVALID", spec.source, "External key có field lặp.")
    if any(field in PII_KEY_FIELDS for field in fields):
        raise _error("PII_EXTERNAL_KEY", spec.source, "External key chứa trường PII.")
    missing = [field for field in fields if field not in values]
    if missing:
        raise _error("KEY_COMPONENT_MISSING", spec.source, "External key thiếu thành phần.")
    payload = {
        "version": "ek1",
        "source": spec.source,
        "scope": {field: _key_component(field, values[field]) for field in spec.scope_fields},
        "key": {field: _key_component(field, values[field]) for field in spec.key_fields},
    }
    return "ek1:" + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalization_rules_as_dict() -> dict[str, object]:
    return {
        "normalization_version": NORMALIZATION_VERSION,
        "token_case": "lower_for_semantic_comparison",
        "text": {"phone_and_text": "string", "phone_strict": True},
        "decimal": {
            "money_vnd_quantum": str(VND_QUANTUM),
            "area_m2_quantum": str(AREA_QUANTUM),
            "quantity_quantum": str(QUANTITY_QUANTUM),
            "ownership_quantum": str(OWNERSHIP_QUANTUM),
            "rounding": "ROUND_HALF_UP",
        },
        "ownership": "non_owner_zero_to_null",
        "datetime": {
            "default_site_timezone": DEFAULT_SITE_TIMEZONE,
            "storage_timezone": "UTC",
            "future_terminal": "reject",
            "future_non_terminal": "scheduled_future",
        },
        "area_storage_policy": AREA_STORAGE_POLICY,
        "external_keys": {
            name: asdict(spec) for name, spec in sorted(EXTERNAL_KEY_SPECS.items())
        },
    }


def normalization_fingerprint() -> str:
    payload = json.dumps(
        normalization_rules_as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def validate_normalization_rules() -> tuple[str, ...]:
    errors: list[str] = []
    if AREA_STORAGE_POLICY != "FLOAT_QUANTIZED_0_01":
        errors.append("area storage policy must be explicit")
    if DEFAULT_SITE_TIMEZONE != "Asia/Ho_Chi_Minh":
        errors.append("default site timezone must remain explicit")
    for name, spec in EXTERNAL_KEY_SPECS.items():
        if name != spec.source:
            errors.append(f"{name}: source mismatch")
        fields = (*spec.scope_fields, *spec.key_fields)
        if not fields or len(fields) != len(set(fields)):
            errors.append(f"{name}: invalid key fields")
        if any(field in PII_KEY_FIELDS for field in fields):
            errors.append(f"{name}: PII field in external key")
    return tuple(errors)


def _self_check() -> None:
    assert normalize_role(" Technician ") == "technician"
    assert normalize_relationship_type("OWNER") == "owner"
    assert normalize_money_vnd("1000.4") == Decimal("1000")
    assert normalize_area_m2("80.126") == Decimal("80.13")
    assert normalize_ownership_ratio("0", "tenant") is None
    assert normalize_ownership_ratio("0.5", "owner") == Decimal("0.5000")
    as_of = datetime(2026, 9, 26, 16, 59, 59, tzinfo=UTC)
    future = normalize_temporal(
        date(2026, 9, 27), field="scheduled_start", as_of_utc=as_of,
    )
    assert future.is_future and future.disposition == "scheduled_future"
    try:
        normalize_temporal(
            date(2026, 9, 27), field="completed_at", as_of_utc=as_of, terminal_event=True,
        )
    except NormalizationError as error:
        assert error.code == "FUTURE_TERMINAL_EVENT"
    else:
        raise AssertionError("future terminal event was accepted")
    key = build_external_key(
        EXTERNAL_KEY_SPECS["employee"],
        {"tenant_code": "tenant-a", "employee_code": "EMP-001"},
    )
    assert key.startswith("ek1:")
    patrol_key = build_external_key(
        EXTERNAL_KEY_SPECS["patrol"],
        {
            "site_code": "site-a",
            "building_code": "building-a",
            "shift_code": "shift-a",
            "patrol_point_code": "point-a",
            "window_start": datetime(2026, 9, 27, 8, 0),
        },
    )
    assert patrol_key.startswith("ek1:")
    assert not validate_normalization_rules()


if __name__ == "__main__":
    _self_check()
    print(
        f"FCS04_NORMALIZATION=PASS version={NORMALIZATION_VERSION} "
        f"fingerprint={normalization_fingerprint()} external_key_specs={len(EXTERNAL_KEY_SPECS)}",
    )
