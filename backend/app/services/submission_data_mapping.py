"""FCS-05 mapping decisions and deterministic canonical-key derivation.

The source pack does not contain ``fee_policy_code`` in the invoice workbook
or ``period_key`` in the payment workbook.  Those values are derived from
non-PII keys in the policy/invoice workbooks.  Every derivation is explicit,
unique, and fail-closed; the loader never joins on names, contacts, amounts,
or free text.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Iterable, Literal, Mapping


MAPPING_VERSION = "fcs05-r2"
DecisionStatus = Literal["OPEN", "RESOLVED"]


class MappingDecisionError(ValueError):
    def __init__(self, decision_id: str) -> None:
        self.decision_id = decision_id
        super().__init__(f"OPEN_MAPPING_DECISION:{decision_id}")


class CanonicalDerivationError(ValueError):
    """A canonical input could not be resolved to exactly one value."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code}:{field}")


@dataclass(frozen=True)
class MappingDecision:
    decision_id: str
    scope: str
    status: DecisionStatus
    owner: str
    required_before_apply: bool
    source_fields: tuple[str, ...]
    allowed_resolution: str
    selected_resolution: str | None = None
    rationale: str | None = None


FCS05_DECISIONS: tuple[MappingDecision, ...] = (
    MappingDecision(
        "FCS05-CATEGORY-SLA", "01_cong_viec.xlsx", "RESOLVED", "Codex + domain owner", True,
        ("request_type", "created_at", "sla_due_at"),
        "Category code is request_type; SLA minutes are the single observed due-created delta per site/category.",
        "request_type -> ServiceCategory.code; sla_due_at - created_at -> sla_minutes",
        "The source supplies a stable non-PII request type and an explicit SLA deadline.",
    ),
    MappingDecision(
        "FCS05-WORK-ORDER-SOURCE", "01_cong_viec.xlsx", "RESOLVED", "Codex + domain owner", True,
        ("work_code", "status", "completed_at"),
        "Rows are ServiceRequest source facts; a WorkOrder is created only by the later replay command.",
        "ServiceRequest first; WorkOrder derived during FCS-12 replay",
        "The workbook has request identity and requester fields; it is not a complete work-order command log.",
    ),
    MappingDecision(
        "FCS05-COST-BEARER", "01_cong_viec.xlsx", "RESOLVED", "Codex + finance owner", True,
        ("cost_vnd",), "Source has no bearer or resident approval field; classify imported cost as MANAGEMENT and post only through the later command.",
        "MANAGEMENT",
        "Fail closed against resident billing when the source does not carry an approved bearer.",
    ),
    MappingDecision(
        "FCS05-MAINTENANCE-MASTER", "05_tai_san_bao_tri.xlsx", "RESOLVED", "Codex + maintenance owner", True,
        ("asset_type", "location", "vendor_name", "responsible_username"),
        "Asset.code/name are the identity; asset_type/location are validated metadata; vendor is validation-only; responsible_username resolves the actor.",
        "Asset metadata validation + responsible account resolution",
        "The current Asset model has no vendor/category/location columns; silently dropping them would hide a mapping.",
    ),
    MappingDecision(
        "FCS05-MAINTENANCE-PLAN-CODE", "05_tai_san_bao_tri.xlsx", "RESOLVED", "Codex + maintenance owner", True,
        ("maintenance_plan_code",), "Approve the identity of repeated plan codes and duplicate policy.",
        "asset_code + maintenance_plan_code",
        "The plan code is scoped by asset; the database unique constraint matches this identity.",
    ),
    MappingDecision(
        "FCS05-MAINTENANCE-CHECKLIST", "05_tai_san_bao_tri.xlsx", "RESOLVED", "Codex + maintenance owner", True,
        ("notes",), "Approve checklist/evidence template; free text remains ignored until then.",
        "Two-item deterministic template: visual inspection + operational check; evidence_required=true",
        "The source does not provide structured checklist columns, so notes remain ignored and cannot become a hidden rule.",
    ),
    MappingDecision(
        "FCS05-CLEANING-MASTER", "06_ve_sinh.xlsx", "RESOLVED", "Codex + cleaning owner", True,
        ("route_code", "area_code", "checklist_floor", "checklist_bins"),
        "Route and area are keyed by site/code; the two checklist fields create a stable route-stop template.",
        "site_code + route_code; site_code + area_code; checklist positions 1 and 2",
        "Codes are stable source identifiers and do not require a name-based join.",
    ),
    MappingDecision(
        "FCS05-PATROL-MASTER", "07_an_ninh_tuan_tra.xlsx", "RESOLVED", "Codex + security owner", True,
        ("patrol_point_code", "event_type"), "Patrol point is site/code; event_type is validated against the patrol log enum.",
        "site_code + patrol_point_code; event_type in CHECK_IN/CHECK_OUT/NOTE",
        "The source supplies explicit patrol point and event codes.",
    ),
    MappingDecision(
        "FCS05-PATROL-HANDOFF", "07_an_ninh_tuan_tra.xlsx", "RESOLVED", "Codex + security owner", True,
        ("handoff_summary",), "The guard account is handed-over-by; the next in-scope security account is resolved by the replay command.",
        "SecurityShiftHandoff command; no name join",
        "Handoff participants remain account keys, never free-text identities.",
    ),
    MappingDecision(
        "FCS05-INCIDENT", "08_su_co_an_ninh.xlsx", "RESOLVED", "Codex + security owner", True,
        ("incident_type", "location", "owner_username"), "incident_type is the model enum; location is retained in the title/description metadata; owner_username resolves the account.",
        "SecurityIncident.code + incident_type + structured location metadata",
        "The current model has no separate location column; the location value is retained in a bounded description field.",
    ),
    MappingDecision(
        "FCS05-PARCEL", "12_buu_pham.xlsx", "RESOLVED", "Codex + parcel owner", True,
        ("handed_over_at", "pin_attempt_count", "case_required"),
        "Replay parcel transitions through the Parcel command; generate a local PIN from a secret and persist only its hash; case_required creates a CaseRecord through its command.",
        "No source PIN is accepted; terminal handover requires command verification",
        "The workbook contains state evidence, not a PIN credential.",
    ),
    MappingDecision(
        "FCS05-FEE-POLICY-CODE", "10_hoa_don.xlsx", "RESOLVED", "Codex + finance owner", True,
        ("building_code", "policy_version"), "Derive fee_policy_code from exactly one policy row in file 09 for building + version.",
        "file09(building_code, version_number) -> fee_policy_code",
        "This is a deterministic non-PII join and fails on zero or multiple matches.",
    ),
    MappingDecision(
        "FCS05-PAYMENT-PERIOD", "11_thanh_toan.xlsx", "RESOLVED", "Codex + finance owner", True,
        ("matched_invoice_number", "received_at", "building_code"), "Use the matched invoice period; for an unmatched receipt derive YYYY-MM from received_at and require exactly one source period for the building.",
        "file10(invoice_number) -> period_key; unmatched -> received_at local YYYY-MM",
        "Unmatched receipts remain explicit and are never attached to an invoice by amount.",
    ),
)


def _norm(value: object) -> str:
    return "" if value is None else str(value).strip().casefold()


def derive_fee_policy_code(
    row: Mapping[str, object],
    policy_rows: Iterable[Mapping[str, object]],
) -> str:
    """Resolve the invoice policy code from file 09 by building/version."""

    building = _norm(row.get("building_code"))
    version = _norm(row.get("policy_version"))
    line_code = _norm(row.get("line_code"))
    matches = {
        str(policy.get("fee_policy_code")).strip()
        for policy in policy_rows
        if _norm(policy.get("building_code")) == building
        and _norm(policy.get("version_number")) == version
        and (not line_code or _norm(policy.get("fee_policy_code")).startswith(line_code + "-"))
    }
    matches.discard("None")
    if len(matches) != 1:
        raise CanonicalDerivationError(
            "CANONICAL_FEE_POLICY_AMBIGUOUS" if len(matches) > 1 else "CANONICAL_FEE_POLICY_MISSING",
            "fee_policy_code",
        )
    return next(iter(matches))


def derive_period_key(
    row: Mapping[str, object],
    invoice_rows: Iterable[Mapping[str, object]],
    policy_rows: Iterable[Mapping[str, object]],
) -> str:
    """Resolve the payment accounting period without amount/name matching."""

    invoice = _norm(row.get("matched_invoice_number"))
    site = _norm(row.get("site_code"))
    building = _norm(row.get("building_code"))
    if invoice:
        periods = {
            str(item.get("period_key")).strip()
            for item in invoice_rows
            if _norm(item.get("site_code")) == site
            and _norm(item.get("building_code")) == building
            and _norm(item.get("invoice_number")) == invoice
        }
    else:
        received = row.get("received_at")
        if hasattr(received, "strftime"):
            key = received.strftime("%Y-%m")
        else:
            text = str(received).strip()
            key = text[:7] if len(text) >= 7 else ""
        periods = {
            str(item.get("period_key")).strip()
            for item in policy_rows
            if _norm(item.get("building_code")) == building
            and str(item.get("period_key")).strip() == key
        }
    periods.discard("None")
    if len(periods) != 1:
        raise CanonicalDerivationError(
            "CANONICAL_PERIOD_AMBIGUOUS" if len(periods) > 1 else "CANONICAL_PERIOD_MISSING",
            "period_key",
        )
    return next(iter(periods))


def mapping_decisions_as_dict() -> dict[str, object]:
    return {
        "mapping_version": MAPPING_VERSION,
        "status": "PARTIAL" if open_decision_ids() else "RESOLVED",
        "decisions": [asdict(decision) for decision in FCS05_DECISIONS],
    }


def open_decision_ids() -> tuple[str, ...]:
    return tuple(decision.decision_id for decision in FCS05_DECISIONS if decision.status == "OPEN")


def require_resolved(decision_id: str) -> MappingDecision:
    for decision in FCS05_DECISIONS:
        if decision.decision_id == decision_id:
            if decision.status != "RESOLVED" and decision.required_before_apply:
                raise MappingDecisionError(decision_id)
            return decision
    raise MappingDecisionError(decision_id)


def mapping_fingerprint() -> str:
    payload = json.dumps(
        mapping_decisions_as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def validate_mapping_catalog() -> tuple[str, ...]:
    errors: list[str] = []
    ids = [decision.decision_id for decision in FCS05_DECISIONS]
    if len(ids) != len(set(ids)):
        errors.append("duplicate decision id")
    for decision in FCS05_DECISIONS:
        if not decision.source_fields:
            errors.append(f"{decision.decision_id}: missing source field")
        if decision.status == "RESOLVED" and not decision.selected_resolution:
            errors.append(f"{decision.decision_id}: resolved decision lacks selection")
    return tuple(errors)


if __name__ == "__main__":
    problems = validate_mapping_catalog()
    if problems:
        for problem in problems:
            print(problem)
        raise SystemExit(1)
    print(
        f"FCS05_MAPPING={'PASS' if not open_decision_ids() else 'PARTIAL'} "
        f"version={MAPPING_VERSION} open={len(open_decision_ids())} "
        f"fingerprint={mapping_fingerprint()}",
    )
