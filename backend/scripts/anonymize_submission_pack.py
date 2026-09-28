"""Create a generated local validation pack after the source passes its gate.

The source workbooks are read only. Source values and the in-memory surrogate
maps are never written to logs, reports, or the output manifest. The output
contains generated identifiers/text, approved enum values, original numeric
facts, and dates shifted five calendar years. A pack derived from real data is
not safe to distribute: rare amounts and event patterns can reidentify people.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from hashlib import sha256
import hmac
import json
from pathlib import Path
import re
import secrets
import shutil
from tempfile import mkdtemp
from typing import Mapping

from openpyxl import Workbook

from app.services.submission_data_contract import CONTRACT_VERSION, WORKBOOK_CONTRACTS, FieldContract
from app.services.submission_data_mapping import derive_fee_policy_code
from app.services.submission_data_normalization import normalize_date, normalize_enum, normalize_temporal
from app.services.submission_data_reader import SubmissionPack, iter_submission_rows, read_submission_pack
from scripts.submission_data_preflight import run_preflight


PACK_VERSION = "fcs17-local-validation-v3"
YEAR_SHIFT = -5
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_OUTPUT_DIRS = frozenset({".local", ".test-runtime"})
CODE_PREFIX = {
    "tenant_code": "SYN-TENANT", "site_code": "SYN-SITE", "building_code": "SYN-BLD",
    "unit_number": "SYN-U", "billing_account_number": "SYN-ACC",
    "resident_code": "SYN-RES", "work_code": "SYN-WORK",
    "employee_code": "SYN-EMP", "asset_code": "SYN-ASSET",
    "maintenance_plan_code": "SYN-PLAN", "shift_code": "SYN-SHIFT",
    "route_code": "SYN-ROUTE", "area_code": "SYN-AREA",
    "patrol_point_code": "SYN-POINT", "incident_code": "SYN-INC",
    "parcel_code": "SYN-PARCEL", "invoice_number": "SYN-INV",
    "billing_run_key": "SYN-RUN", "source_reference": "SYN-PAY",
    "receipt_number": "SYN-REC", "request_type": "SYN-CAT",
    "storage_location": "SYN-SHELF",
}
USERNAME_FIELDS = frozenset({
    "username", "reported_by_username", "assignee_username", "responsible_username",
    "guard_username", "owner_username", "received_by_username",
})
GENERATED_TEXT = {
    "title": "Synthetic work request", "description": "Synthetic operational description",
    "department": "Synthetic department", "site_name": "Synthetic site",
    "building_name": "Synthetic building", "asset_name": "Synthetic asset",
    "asset_type": "Synthetic equipment", "location": "Synthetic location",
    "vendor_name": "Synthetic vendor", "handoff_summary": "Synthetic handoff",
    "fee_policy_name": "Synthetic fee policy",
    "unmatched_reason": "Synthetic unmatched receipt",
}
CONTROLLED = {
    "event_type": ("CHECK_IN", "CHECK_OUT", "NOTE"),
    "billing_status": ("ACTIVE", "SUSPENDED", "CLOSED"),
    "policy_status": ("ACTIVE", "INACTIVE"),
    "status": (
        "ACTIVE", "INACTIVE", "RETIRED", "NEW", "TRIAGED", "IN_PROGRESS",
        "WAITING_INFO", "RESOLVED", "CLOSED", "CANCELLED", "DRAFT",
        "ASSIGNED", "ON_HOLD", "WAITING_ACCEPTANCE", "COMPLETED",
        "PLANNED", "RECEIVED", "READY_FOR_PICKUP", "HANDED_OVER",
        "RETURNED", "LOST", "DAMAGED", "PARTIALLY_ALLOCATED",
        "ALLOCATED", "UNMATCHED", "OVERPAID", "SUSPENDED",
    ),
}
PROHIBITED_TEXT = re.compile(r"(?i)(?:https?://|@(?!(?:example\.invalid)$)|(?:\d[\s().-]?){9,}|password|api[_ -]?key|secret|token)")


class AnonymizationError(ValueError):
    """Stable error code; never contain input values or paths."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _move_year(value: date | datetime) -> date | datetime:
    try:
        return value.replace(year=value.year + YEAR_SHIFT)
    except ValueError:
        # 29 February maps to 28 February in the target year.
        return value.replace(year=value.year + YEAR_SHIFT, day=28)


class Surrogates:
    def __init__(self, secret: bytes | None = None) -> None:
        self._secret = secret if secret is not None else secrets.token_bytes(32)
        self._maps: dict[str, dict[str, str]] = defaultdict(dict)

    def get(self, group: str, value: object, prefix: str) -> str:
        key = str(value).strip().casefold()
        bucket = self._maps[group]
        if key not in bucket:
            digest = hmac.new(self._secret, f"{group}\0{key}".encode("utf-8"), sha256).digest()[:16]
            # Letters only: a long hexadecimal digit run would fail the output's
            # conservative phone-number scan even though it is generated data.
            suffix = "".join(chr(97 + nibble) for byte in digest for nibble in (byte >> 4, byte & 15))
            bucket[key] = f"{prefix}-{suffix}"
        return bucket[key]


def _source_manifest_ok(pack: SubmissionPack, manifest_path: Path) -> bool:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest["workbooks"]
        by_name = {entry["file_name"]: entry for entry in entries}
        if len(entries) != len(pack.workbooks) or len(by_name) != len(entries):
            return False
        for workbook in pack.workbooks:
            entry = by_name.get(workbook.file_name)
            if entry is None or entry.get("sha256") != workbook.source_sha256:
                return False
            count = entry.get("row_count")
            if count is None:
                count = next((sheet.get("data_row_count") for sheet in entry.get("sheets", [])
                              if sheet.get("sheet_role") == "data"), None)
            if count != workbook.data_row_count:
                return False
        return True
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return False


def _fee_policy_aliases(pack: SubmissionPack, aliases: Surrogates) -> dict[str, str]:
    policy_rows = [row for workbook, _, row in iter_submission_rows(pack)
                   if workbook.file_name == "09_chinh_sach_phi.xlsx"]
    invoice_rows = [row for workbook, _, row in iter_submission_rows(pack)
                    if workbook.file_name == "10_hoa_don.xlsx"]
    linked: dict[str, str] = {}
    for row in invoice_rows:
        source_code = derive_fee_policy_code(row, policy_rows)
        source_line = str(row["line_code"]).strip()
        line_alias = aliases.get("line_code", source_line, "SYNLINE")
        key = source_code.casefold()
        previous = linked.get(key)
        if previous is not None and previous != line_alias:
            raise AnonymizationError("POLICY_LINE_AMBIGUOUS")
        linked[key] = line_alias
    return linked


def _transform_text(
    field: FieldContract, value: str, workbook_name: str,
    aliases: Surrogates, policy_lines: Mapping[str, str],
) -> str | None:
    name = field.source_name
    if name == "notes":
        return None
    if name in CODE_PREFIX:
        return aliases.get(name, value, CODE_PREFIX[name])
    if name == "matched_invoice_number":
        return aliases.get("invoice_number", value, CODE_PREFIX["invoice_number"])
    if name in USERNAME_FIELDS:
        return aliases.get("username", value, "syn_user")
    if name == "line_code":
        return aliases.get("line_code", value, "SYNLINE")
    if name == "fee_policy_code":
        prefix = policy_lines.get(value.casefold(), "SYNFEE")
        return aliases.get("fee_policy_code", value, prefix)
    if name == "period_key":
        match = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", value)
        if match is None:
            raise AnonymizationError("PERIOD_KEY_INVALID")
        return f"{int(match[1]) + YEAR_SHIFT:04d}-{match[2]}"
    if name == "full_name":
        label = "Synthetic Account" if workbook_name.startswith("02_") else "Synthetic Resident"
        return aliases.get(f"full_name:{workbook_name}", value, label)
    if name == "recipient_name_snapshot":
        return aliases.get("recipient_name_snapshot", value, "Synthetic Recipient")
    if name == "email":
        index = aliases.get("email", value, "syn_email").rsplit("-", 1)[-1]
        return f"user{index}@example.invalid"
    if name == "email_masked":
        index = aliases.get("email_masked", value, "syn_masked_email").rsplit("-", 1)[-1]
        return f"r***{index}@example.invalid"
    if name in {"phone", "phone_masked", "recipient_contact_masked"}:
        index = aliases.get(name, value, "syn_contact").rsplit("-", 1)[-1]
        return f"***{index}"
    if name == "line_description":
        return "UNIT AREA M2"
    if name in GENERATED_TEXT:
        return aliases.get(f"text:{name}", value, GENERATED_TEXT[name])
    if field.enum:
        return normalize_enum(value, field.enum, field=name, output_case="preserve")
    if name in CONTROLLED:
        return normalize_enum(value, CONTROLLED[name], field=name, output_case="preserve")
    raise AnonymizationError("TRANSFORM_FIELD_UNMAPPED")


def _transform(pack: SubmissionPack) -> dict[str, list[dict[str, object]]]:
    aliases = Surrogates()
    policy_lines = _fee_policy_aliases(pack, aliases)
    contracts = {contract.file_name: contract for contract in WORKBOOK_CONTRACTS}
    result: dict[str, list[dict[str, object]]] = defaultdict(list)
    for workbook, _, row in iter_submission_rows(pack):
        transformed: dict[str, object] = {}
        for field in contracts[workbook.file_name].fields:
            value = row[field.source_name]
            name = field.source_name
            if value is None or (isinstance(value, str) and not value.strip()):
                transformed[name] = None
            elif field.value_type == "string":
                transformed[name] = _transform_text(field, value, workbook.file_name, aliases, policy_lines)
            elif field.value_type == "date":
                transformed[name] = _move_year(normalize_date(value, field=name))
            elif field.value_type == "datetime":
                local = normalize_temporal(value, field=name).local.replace(tzinfo=None)
                transformed[name] = _move_year(local)
            elif field.value_type in {"integer", "decimal", "boolean"}:
                transformed[name] = value
            else:
                raise AnonymizationError("TRANSFORM_TYPE_UNMAPPED")
        result[workbook.file_name].append(transformed)
    return result


def _write_workbook(path: Path, rows: list[dict[str, object]], contract) -> None:
    workbook = Workbook()
    data = workbook.active
    data.title = contract.data_sheet
    data.append([field.source_name for field in contract.fields])
    for row in rows:
        data.append([row[field.source_name] for field in contract.fields])
    guide = workbook.create_sheet(contract.guide_sheet)
    guide.append(["Pack", "Class", "Version", "Purpose"])
    guide.append(["GreenCity", "Generated validation pack", PACK_VERSION, "Local validation only"])
    workbook.properties.creator = "GreenCity pack generator"
    workbook.properties.title = "GreenCity generated validation pack"
    workbook.properties.subject = "Generated aliases; original numeric facts; no distribution approval"
    workbook.save(path)
    workbook.close()


def _scan_pack(pack: SubmissionPack) -> None:
    for _, _, row in iter_submission_rows(pack):
        for value in row.values():
            if not isinstance(value, str):
                continue
            if PROHIBITED_TEXT.search(value):
                raise AnonymizationError("OUTPUT_SENSITIVE_PATTERN")


def anonymize_pack(source: Path, source_manifest: Path, output: Path, *, as_of_utc: datetime) -> dict[str, object]:
    resolved_output = output.resolve()
    if resolved_output.is_relative_to(PROJECT_ROOT.resolve()):
        relative_parts = resolved_output.relative_to(PROJECT_ROOT.resolve()).parts
        if not PRIVATE_OUTPUT_DIRS.intersection(relative_parts):
            raise AnonymizationError("OUTPUT_PATH_NOT_PRIVATE")
    if (output.exists() or output.with_name("approved_manifest.json").exists()
            or output.with_name("local_validation_manifest.json").exists()):
        raise AnonymizationError("OUTPUT_EXISTS")
    if source.resolve() == output.resolve() or source.resolve() in output.resolve().parents:
        raise AnonymizationError("OUTPUT_PATH_INVALID")
    if not source_manifest.is_file():
        raise AnonymizationError("SOURCE_MANIFEST_MISSING")
    pack = read_submission_pack(source)
    if not _source_manifest_ok(pack, source_manifest):
        raise AnonymizationError("SOURCE_CHECKSUM_MISMATCH")
    source_metadata = json.loads(source_manifest.read_text(encoding="utf-8"))
    source_kind = source_metadata.get("provenance_reference", {}).get(
        "classification", source_metadata.get("classification"),
    )
    if source_kind not in {"RESTRICTED_REAL_LOCAL_ONLY", "SYNTHETIC_TEST_ONLY"}:
        raise AnonymizationError("SOURCE_CLASSIFICATION_INVALID")
    # A caller-controlled manifest cannot attest that its source is synthetic.
    # This tool therefore never authorizes distribution, regardless of label.
    manifest_name = "local_validation_manifest.json"
    preflight = run_preflight(source, as_of_utc=as_of_utc, manifest_path=source_manifest)
    if (preflight.status != "PASS" or not preflight.source_checksum_verified
            or preflight.orphan_count or preflight.future_terminal_candidates
            or preflight.workbook_count != 12 or preflight.total_rows != 101
            or preflight.decided_rows != preflight.total_rows):
        raise AnonymizationError("SOURCE_PREFLIGHT_BLOCKED")
    transformed = _transform(pack)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(mkdtemp(prefix=".approved_pack_tmp_", dir=output.parent))
    staged_pack = temporary / "approved_pack"
    staged_pack.mkdir()
    published = False
    pack_renamed = False
    try:
        entries = []
        for contract in WORKBOOK_CONTRACTS:
            path = staged_pack / contract.file_name
            _write_workbook(path, transformed[contract.file_name], contract)
            entries.append({"file_name": contract.file_name, "sha256": sha256(path.read_bytes()).hexdigest(),
                            "row_count": len(transformed[contract.file_name])})
        warning_counts = Counter(issue.code for issue in preflight.issues if issue.severity == "WARNING")
        manifest = {
            "classification": "LOCAL_VALIDATION_ONLY",
            "distribution_allowed": False,
            "source_classification": source_kind,
            "validation_scope": "local preflight and generated-text scan; source classification is caller-declared and untrusted",
            "privacy_limitations": ("Original amounts, quantities and shifted event patterns remain linkable; "
                                    "real-derived output must stay local"),
            "pack_version": PACK_VERSION,
            "schema_version": CONTRACT_VERSION, "transformation": {
                "identifiers": "random-key aliases independent of row order; no reverse map retained",
                "free_text": "generated", "contacts": "generated example.invalid or masked",
                "dates": "shifted five calendar years backward; leap day clamps to February 28",
                "amounts_and_quantities": "preserved for reconciliation",
            },
            "source_preflight": {"status": preflight.status, "warning_count": sum(warning_counts.values()),
                                 "warning_codes": dict(sorted(warning_counts.items())), "orphan_count": preflight.orphan_count},
            "workbook_count": len(entries), "total_rows": sum(item["row_count"] for item in entries),
            "workbooks": entries,
        }
        staged_manifest = temporary / manifest_name
        staged_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        generated = read_submission_pack(staged_pack)
        _scan_pack(generated)
        checked = run_preflight(staged_pack, as_of_utc=as_of_utc, manifest_path=staged_manifest)
        if (checked.status != "PASS" or checked.orphan_count or not checked.source_checksum_verified
                or checked.total_rows != 101):
            raise AnonymizationError("OUTPUT_PREFLIGHT_BLOCKED")
        staged_pack.rename(output)
        pack_renamed = True
        staged_manifest.rename(output.with_name(manifest_name))
        published = True
        return manifest
    finally:
        # This directory is created here under output.parent; never touch the raw source.
        if temporary.resolve().parent == output.parent.resolve():
            shutil.rmtree(temporary, ignore_errors=True)
        if pack_renamed and not published and output.is_dir():
            # A rename can succeed before the second rename fails. Remove only
            # the known files generated by this invocation.
            for contract in WORKBOOK_CONTRACTS:
                (output / contract.file_name).unlink(missing_ok=True)
            output.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed GreenCity local validation pack builder")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--as-of", type=str)
    args = parser.parse_args()
    try:
        as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else datetime.now(UTC)
        manifest = anonymize_pack(args.source, args.source_manifest, args.output, as_of_utc=as_of)
    except Exception as error:
        print(f"FCS17_ANONYMIZE=FAIL code={getattr(error, 'code', 'ANONYMIZE_ERROR')}")
        return 1
    print(f"FCS17_LOCAL_PACK=PASS classification={manifest['classification']} "
          f"distribution_allowed={str(manifest['distribution_allowed']).lower()} "
          f"workbooks={manifest['workbook_count']} rows={manifest['total_rows']} "
          f"source_warnings={manifest['source_preflight']['warning_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
