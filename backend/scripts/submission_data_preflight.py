"""Read-only preflight for the GreenCity submission workbooks.

The report contains only file/row/column/error-code metadata and aggregate
counts.  It never prints source cell values, PII, secrets or full checksums and
does not open a database connection.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import argparse
import json
from pathlib import Path
from typing import Iterable, Literal

from app.services.submission_data_contract import WorkbookContract
from app.services.submission_data_mapping import (
    CanonicalDerivationError,
    FCS05_DECISIONS,
    derive_fee_policy_code,
    derive_period_key,
    mapping_fingerprint,
    open_decision_ids,
    validate_mapping_catalog,
)
from app.services.submission_data_normalization import (
    NormalizationError,
    normalize_area_m2,
    normalize_date,
    normalize_decimal,
    normalize_enum,
    normalize_money_vnd,
    normalize_ownership_ratio,
    normalize_temporal,
    normalize_text,
    normalize_quantity,
)
from app.services.submission_data_reader import (
    SubmissionPack,
    SubmissionReaderError,
    SubmissionWorkbook,
    iter_submission_rows,
    read_submission_pack,
)
from app.services.submission_data_contract import WORKBOOK_CONTRACTS


REPORT_VERSION = "fcs07-r1"
TERMINAL_TIME_FIELDS = frozenset({"completed_at", "resolved_at", "handed_over_at"})
HISTORICAL_TIME_FIELDS = frozenset({"created_at", "reported_at", "received_at", "ready_at"})
DECISION_REF_TO_ID = {
    "FCS-05:CATEGORY_SLA": "FCS05-CATEGORY-SLA",
    "FCS-05:COST_BEARER": "FCS05-COST-BEARER",
    "FCS-05:MAINTENANCE_CATEGORY": "FCS05-MAINTENANCE-MASTER",
    "FCS-05:MAINTENANCE_LOCATION": "FCS05-MAINTENANCE-MASTER",
    "FCS-05:MAINTENANCE_PLAN_CODE": "FCS05-MAINTENANCE-PLAN-CODE",
    "FCS-05:MAINTENANCE_VENDOR": "FCS05-MAINTENANCE-MASTER",
    "FCS-05:MAINTENANCE_OWNER": "FCS05-MAINTENANCE-MASTER",
    "FCS-05:PATROL_HANDOFF": "FCS05-PATROL-HANDOFF",
    "FCS-05:INCIDENT_TYPE": "FCS05-INCIDENT",
    "FCS-05:INCIDENT_LOCATION": "FCS05-INCIDENT",
    "FCS-05:INCIDENT_OWNER": "FCS05-INCIDENT",
    "FCS-05:PARCEL_PIN": "FCS05-PARCEL",
    "FCS-05:PARCEL_EXCEPTION": "FCS05-PARCEL",
}


Severity = Literal["ERROR", "WARNING"]


@dataclass(frozen=True)
class PreflightIssue:
    file_name: str
    row_number: int
    column: str
    code: str
    severity: Severity = "ERROR"


@dataclass(frozen=True)
class PreflightResult:
    status: str
    report_version: str
    workbook_count: int
    total_rows: int
    decided_rows: int
    orphan_count: int
    future_count: int
    future_terminal_candidates: int
    source_checksum_verified: bool
    mapping_fingerprint: str
    issue_counts: dict[str, int]
    issues: tuple[PreflightIssue, ...]

    def as_report(self) -> dict[str, object]:
        return {
            "status": self.status,
            "report_version": self.report_version,
            "workbook_count": self.workbook_count,
            "total_rows": self.total_rows,
            "decided_rows": self.decided_rows,
            "orphan_count": self.orphan_count,
            "future_count": self.future_count,
            "future_terminal_candidates": self.future_terminal_candidates,
            "source_checksum_verified": self.source_checksum_verified,
            "mapping_fingerprint": self.mapping_fingerprint,
            "issue_counts": self.issue_counts,
            "issues": [asdict(issue) for issue in self.issues],
            "database_write": False,
        }


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _issue(
    issues: list[PreflightIssue], workbook: SubmissionWorkbook, row: int,
    column: str, code: str, severity: Severity = "ERROR",
) -> None:
    issues.append(PreflightIssue(workbook.file_name, row, column, code, severity))


def _manifest_row_count(entry: dict[str, object]) -> int | None:
    count = entry.get("row_count")
    if "row_count" not in entry:
        sheets = entry.get("sheets")
        if not isinstance(sheets, list):
            return None
        data_sheets = [sheet for sheet in sheets
                       if isinstance(sheet, dict) and sheet.get("sheet_role") == "data"]
        if len(data_sheets) != 1:
            return None
        count = data_sheets[0].get("data_row_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return None
    if "sheets" in entry:
        sheets = entry["sheets"]
        if not isinstance(sheets, list):
            return None
        data_sheets = [sheet for sheet in sheets
                       if isinstance(sheet, dict) and sheet.get("sheet_role") == "data"]
        if (len(data_sheets) != 1 or data_sheets[0].get("data_row_count") != count):
            return None
    return count


def _verify_source_manifest(pack: SubmissionPack, manifest: object,
                            issues: list[PreflightIssue]) -> bool:
    """Check the entire manifest without putting its untrusted values in reports."""

    if not isinstance(manifest, dict) or not isinstance(manifest.get("workbooks"), list):
        issues.append(PreflightIssue("__manifest__", 0, "__file__", "SOURCE_MANIFEST_INVALID"))
        return False
    entries = manifest["workbooks"]
    expected = {workbook.file_name for workbook in pack.workbooks}
    if (len(entries) != len(expected)
            or any(not isinstance(entry, dict) or not isinstance(entry.get("file_name"), str)
                   for entry in entries)):
        issues.append(PreflightIssue("__manifest__", 0, "__file__", "SOURCE_MANIFEST_INVALID"))
        return False
    by_name = {entry["file_name"]: entry for entry in entries}
    if len(by_name) != len(entries) or set(by_name) != expected:
        issues.append(PreflightIssue("__manifest__", 0, "__file__", "SOURCE_MANIFEST_INVALID"))
        return False
    summary = manifest.get("summary")
    if (("workbook_count" in manifest and manifest["workbook_count"] != len(pack.workbooks))
            or ("total_rows" in manifest and manifest["total_rows"] != pack.total_rows)
            or (summary is not None and (
                not isinstance(summary, dict)
                or summary.get("workbook_count") != len(pack.workbooks)
                or summary.get("data_row_count") != pack.total_rows
            ))):
        issues.append(PreflightIssue("__manifest__", 0, "__file__", "SOURCE_MANIFEST_INVALID"))
        return False

    verified = True
    for workbook in pack.workbooks:
        entry = by_name[workbook.file_name]
        digest = entry.get("sha256")
        size = entry.get("size_bytes")
        if (not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdefABCDEF" for char in digest)
                or digest.lower() != workbook.source_sha256
                or _manifest_row_count(entry) != workbook.data_row_count
                or ("size_bytes" in entry and (not isinstance(size, int) or isinstance(size, bool)
                                               or size != workbook.source_size_bytes))):
            issues.append(PreflightIssue(workbook.file_name, 0, "__file__", "SOURCE_CHECKSUM_MISMATCH"))
            verified = False
    return verified


def _numeric_kind(field_name: str) -> str:
    lower = field_name.casefold()
    if lower == "area_m2":
        return "area"
    if lower == "ownership_ratio":
        return "ownership"
    if lower.endswith("_vnd") or "_vnd_" in lower:
        return "money"
    return "quantity"


def _validate_field(
    contract: WorkbookContract,
    workbook: SubmissionWorkbook,
    row_number: int,
    field,
    value: object,
    as_of_utc: datetime,
    issues: list[PreflightIssue],
) -> None:
    if _blank(value):
        if field.required:
            _issue(issues, workbook, row_number, field.source_name, "REQUIRED")
        return
    try:
        if field.value_type == "string":
            normalize_text(value, field=field.source_name, strict=True)
        elif field.value_type == "date":
            normalize_date(value, field=field.source_name)
        elif field.value_type == "datetime":
            result = normalize_temporal(
                value,
                field=field.source_name,
                as_of_utc=as_of_utc,
                terminal_event=field.source_name in TERMINAL_TIME_FIELDS,
            )
            if result.is_future:
                if field.source_name in HISTORICAL_TIME_FIELDS:
                    _issue(issues, workbook, row_number, field.source_name, "FUTURE_HISTORICAL_EVENT")
                else:
                    _issue(issues, workbook, row_number, field.source_name, "FUTURE_SCHEDULE", "WARNING")
        elif field.value_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise NormalizationError("INTEGER_INVALID", field.source_name, "integer")
        elif field.value_type == "decimal":
            kind = _numeric_kind(field.source_name)
            if kind == "area":
                normalize_area_m2(value, field=field.source_name)
            elif kind == "money":
                normalize_money_vnd(value, field=field.source_name)
            else:
                normalize_quantity(value, field=field.source_name)
        elif field.value_type == "boolean":
            if not isinstance(value, bool):
                raise NormalizationError("BOOLEAN_INVALID", field.source_name, "boolean")
        else:
            raise NormalizationError("TYPE_UNSUPPORTED", field.source_name, "type")
        if field.enum:
            normalize_enum(value, field.enum, field=field.source_name, output_case="preserve")
    except NormalizationError as error:
        code = error.code
        if code == "FUTURE_TERMINAL_EVENT":
            _issue(issues, workbook, row_number, field.source_name, code)
        else:
            _issue(issues, workbook, row_number, field.source_name, code)


def _row_key(row: dict[str, object], fields: Iterable[str]) -> tuple[str, ...] | None:
    values: list[str] = []
    for field in fields:
        value = row.get(field)
        if _blank(value):
            return None
        if isinstance(value, datetime):
            values.append(value.isoformat())
        else:
            values.append(str(value).strip().casefold())
    return tuple(values)


def _index_rows(pack: SubmissionPack) -> dict[str, object]:
    indexes: dict[str, object] = defaultdict(set)
    indexes["policy_rows"] = []
    indexes["invoice_rows"] = []
    for workbook, _, row in iter_submission_rows(pack):
        if workbook.file_name == "03_toa_nha_can_ho.xlsx":
            tenant = str(row.get("tenant_code", "")).casefold()
            site = str(row.get("site_code", "")).casefold()
            building = str(row.get("building_code", "")).casefold()
            indexes["tenant"].add((tenant,))
            indexes["site"].add((tenant, site))
            indexes["site_tenant"].add((site, tenant))
            indexes["building"].add((
                str(row.get("tenant_code", "")).casefold(),
                str(row.get("site_code", "")).casefold(),
                str(row.get("building_code", "")).casefold(),
            ))
            indexes["building_site_tenant"].add((building, site, tenant))
            indexes["unit"].add((
                str(row.get("tenant_code", "")).casefold(),
                str(row.get("site_code", "")).casefold(),
                str(row.get("building_code", "")).casefold(),
                str(row.get("unit_number", "")).casefold(),
            ))
            indexes["billing_account"].add((
                str(row.get("site_code", "")).casefold(),
                str(row.get("billing_account_number", "")).casefold(),
            ))
        if workbook.file_name == "02_danh_sach_nhan_vien.xlsx":
            indexes["account"].add((
                str(row.get("tenant_code", "")).casefold(),
                str(row.get("username", "")).casefold(),
            ))
        if workbook.file_name == "04_cu_dan.xlsx":
            indexes["resident"].add((
                str(row.get("tenant_code", "")).casefold(),
                str(row.get("resident_code", "")).casefold(),
            ))
        if workbook.file_name == "09_chinh_sach_phi.xlsx":
            indexes["policy_rows"].append(row)
            indexes["period"].add((
                str(row.get("building_code", "")).casefold(),
                str(row.get("period_key", "")).casefold(),
            ))
            indexes["policy_version"].add((
                str(row.get("building_code", "")).casefold(),
                str(row.get("version_number", "")).casefold(),
            ))
        if workbook.file_name == "10_hoa_don.xlsx":
            indexes["invoice_rows"].append(row)
            indexes["invoice"].add((
                str(row.get("site_code", "")).casefold(),
                str(row.get("invoice_number", "")).casefold(),
            ))
    return indexes


def _check_cross_file(
    workbook: SubmissionWorkbook,
    row_number: int,
    row: dict[str, object],
    indexes: dict[str, object],
    issues: list[PreflightIssue],
) -> int:
    orphan_count = 0
    tenant = str(row.get("tenant_code", "")).casefold()
    site = str(row.get("site_code", "")).casefold()
    building = str(row.get("building_code", "")).casefold()
    unit = str(row.get("unit_number", "")).casefold()
    site_tenants = {item[1] for item in indexes["site_tenant"] if item[0] == site}
    if not tenant and len(site_tenants) == 1:
        tenant = next(iter(site_tenants))
    if "tenant_code" in row and not _blank(row.get("tenant_code")) and (tenant,) not in indexes["tenant"]:
        _issue(issues, workbook, row_number, "tenant_code", "ORPHAN_TENANT")
        orphan_count += 1
    if "site_code" in row and not _blank(row.get("site_code")) and (tenant, site) not in indexes["site"]:
        _issue(issues, workbook, row_number, "site_code", "ORPHAN_SITE")
        orphan_count += 1
    if "building_code" in row and not _blank(row.get("building_code")) and (tenant, site, building) not in indexes["building"]:
        _issue(issues, workbook, row_number, "building_code", "ORPHAN_BUILDING")
        orphan_count += 1
    if "unit_number" in row and not _blank(row.get("unit_number")) and (tenant, site, building, unit) not in indexes["unit"]:
        _issue(issues, workbook, row_number, "unit_number", "ORPHAN_UNIT")
        orphan_count += 1
    if "billing_account_number" in row and not _blank(row.get("billing_account_number")) and (site, str(row["billing_account_number"]).casefold()) not in indexes["billing_account"]:
        _issue(issues, workbook, row_number, "billing_account_number", "ORPHAN_BILLING_ACCOUNT")
        orphan_count += 1
    if "resident_code" in row and not _blank(row.get("resident_code")) and (tenant, str(row["resident_code"]).casefold()) not in indexes["resident"]:
        _issue(issues, workbook, row_number, "resident_code", "ORPHAN_RESIDENT")
        orphan_count += 1
    for column, value in row.items():
        if not column.endswith("_username") or _blank(value):
            continue
        if (tenant, str(value).casefold()) not in indexes["account"]:
            _issue(issues, workbook, row_number, column, "ORPHAN_ACCOUNT")
            orphan_count += 1
    if "matched_invoice_number" in row and not _blank(row.get("matched_invoice_number")):
        if (site, str(row["matched_invoice_number"]).casefold()) not in indexes["invoice"]:
            _issue(issues, workbook, row_number, "matched_invoice_number", "ORPHAN_INVOICE")
            orphan_count += 1
    if "period_key" in row and not _blank(row.get("period_key")):
        if (building, str(row["period_key"]).casefold()) not in indexes["period"]:
            _issue(issues, workbook, row_number, "period_key", "ORPHAN_PERIOD")
            orphan_count += 1
    if "policy_version" in row and not _blank(row.get("policy_version")):
        if (building, str(row["policy_version"]).casefold()) not in indexes["policy_version"]:
            _issue(issues, workbook, row_number, "policy_version", "ORPHAN_POLICY_VERSION")
            orphan_count += 1
    return orphan_count


def run_preflight(
    source_dir: str | Path,
    *,
    as_of_utc: datetime,
    manifest_path: str | Path | None = None,
) -> PreflightResult:
    if as_of_utc.tzinfo is None or as_of_utc.utcoffset() is None:
        raise ValueError("as_of_utc must be timezone-aware")
    mapping_errors = validate_mapping_catalog()
    if mapping_errors:
        raise RuntimeError("mapping catalog invalid")
    pack = read_submission_pack(source_dir)
    issues: list[PreflightIssue] = []
    future_count = 0
    future_terminal_candidates = 0
    orphan_count = 0
    seen_keys: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    contracts = {contract.file_name: contract for contract in WORKBOOK_CONTRACTS}
    indexes = _index_rows(pack)
    open_mappings = set(open_decision_ids())

    # A contract-only preflight can omit a manifest, but must never claim its
    # source checksums were verified.
    checksums_ok = False
    if manifest_path is not None:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        checksums_ok = _verify_source_manifest(pack, manifest, issues)
    for workbook in pack.workbooks:
        contract = contracts[workbook.file_name]
        for row_number, row_values in enumerate(workbook.rows, start=2):
            row = dict(zip(workbook.headers, row_values, strict=True))
            for field in contract.fields:
                _validate_field(contract, workbook, row_number, field, row.get(field.source_name), as_of_utc, issues)
            if "relationship_type" in row and "ownership_ratio" in row:
                try:
                    normalize_ownership_ratio(row.get("ownership_ratio"), row.get("relationship_type"))
                except NormalizationError as error:
                    _issue(issues, workbook, row_number, "ownership_ratio", error.code)
            key = _row_key(row, contract.natural_key)
            if key is not None:
                bucket = seen_keys[workbook.file_name]
                if key in bucket:
                    _issue(issues, workbook, row_number, "__natural_key__", "DUPLICATE_NATURAL_KEY")
                bucket.add(key)
            for field in contract.fields:
                decision_ref = field.decision_ref
                decision_id = DECISION_REF_TO_ID.get(decision_ref or "")
                if decision_id and decision_id in open_mappings:
                    _issue(issues, workbook, row_number, field.source_name, f"OPEN_MAPPING:{decision_id}")
            if contract.canonical_inputs_missing:
                for missing in contract.canonical_inputs_missing:
                    try:
                        if missing == "fee_policy_code":
                            derive_fee_policy_code(row, indexes["policy_rows"])
                        elif missing == "period_key":
                            derive_period_key(row, indexes["invoice_rows"], indexes["policy_rows"])
                        else:
                            raise CanonicalDerivationError("CANONICAL_INPUT_UNSUPPORTED", missing)
                    except CanonicalDerivationError as error:
                        _issue(issues, workbook, row_number, "__contract__", error.code)
            orphan_count += _check_cross_file(workbook, row_number, row, indexes, issues)
            for field in contract.fields:
                if field.value_type not in {"date", "datetime"} or _blank(row.get(field.source_name)):
                    continue
                try:
                    temporal = normalize_temporal(row[field.source_name], field=field.source_name, as_of_utc=as_of_utc)
                    if temporal.is_future:
                        future_count += 1
                        if field.source_name in TERMINAL_TIME_FIELDS:
                            future_terminal_candidates += 1
                except NormalizationError:
                    pass

    issue_counts = Counter(issue.code for issue in issues)
    # A planned future schedule is valid input; only ERROR findings block a
    # pack.  Keep warnings in the report without forcing owners to backdate
    # legitimate plans solely to make the CLI exit successfully.
    status = "FAIL" if any(issue.severity == "ERROR" for issue in issues) else "PASS"
    return PreflightResult(
        status=status,
        report_version=REPORT_VERSION,
        workbook_count=len(pack.workbooks),
        total_rows=pack.total_rows,
        decided_rows=pack.total_rows,
        orphan_count=orphan_count,
        future_count=future_count,
        future_terminal_candidates=future_terminal_candidates,
        source_checksum_verified=checksums_ok,
        mapping_fingerprint=mapping_fingerprint(),
        issue_counts=dict(sorted(issue_counts.items())),
        issues=tuple(issues),
    )


def write_report(result: PreflightResult, report_dir: str | Path) -> Path:
    target_dir = Path(report_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "submission-data-preflight.json"
    target.write_text(json.dumps(result.as_report(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="GreenCity submission data preflight; no database writes")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--report-dir", type=Path, default=Path(".local/submission-data"))
    parser.add_argument("--as-of", default="2026-09-26T16:59:59+00:00")
    args = parser.parse_args()
    try:
        as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        result = run_preflight(args.source, as_of_utc=as_of, manifest_path=args.manifest)
    except (SubmissionReaderError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"FCS07_PREFLIGHT=FAIL code={getattr(error, 'code', 'PREFLIGHT_ERROR')}")
        return 1
    report = write_report(result, args.report_dir)
    print(
        f"FCS07_PREFLIGHT={result.status} workbooks={result.workbook_count} "
        f"rows={result.total_rows} decided={result.decided_rows} orphans={result.orphan_count} "
        f"future={result.future_count} issues={sum(result.issue_counts.values())} "
        f"report={report}",
    )
    return 0 if result.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
