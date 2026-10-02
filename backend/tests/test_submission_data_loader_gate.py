"""Fail-closed submission loader stage controls, without a database."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
import shutil
import json
import sys
from uuid import uuid4

import pytest

from scripts import load_submission_data as loader
from app.services.submission_data_import import SubmissionImportError


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "submission_data"
PACK = FIXTURE_ROOT / "synthetic"
MANIFEST = FIXTURE_ROOT / "synthetic_manifest.json"


def _stub_preflight(monkeypatch, issues):
    pack = loader.read_submission_pack(PACK)
    monkeypatch.setattr(loader, "read_submission_pack", lambda _source: pack)
    monkeypatch.setattr(loader, "run_preflight", lambda _source, **_kwargs: SimpleNamespace(
        issues=issues, status="FAIL" if any(i.severity == "ERROR" for i in issues) else "PARTIAL",
        total_rows=101, orphan_count=0, source_checksum_verified=True,
    ))
    monkeypatch.setattr(loader, "manifest_summary", lambda _manifest: SimpleNamespace(manifest_sha256="0" * 64))


def test_all_and_replay_reject_future_terminal_event(monkeypatch):
    _stub_preflight(monkeypatch, [SimpleNamespace(code="FUTURE_TERMINAL_EVENT", severity="ERROR")])
    for stage in ("all", "replay"):
        with pytest.raises(SubmissionImportError, match="PREFLIGHT_BLOCKED"):
            loader._preflight_ok_for_stage(PACK, stage)


def test_master_and_references_defer_terminal_but_never_other_errors(monkeypatch):
    _stub_preflight(monkeypatch, [SimpleNamespace(code="FUTURE_TERMINAL_EVENT", severity="ERROR")])
    for stage in ("master", "references"):
        loader._preflight_ok_for_stage(PACK, stage)
    _stub_preflight(monkeypatch, [SimpleNamespace(code="ORPHAN_UNIT", severity="ERROR")])
    with pytest.raises(SubmissionImportError, match="PREFLIGHT_BLOCKED"):
        loader._preflight_ok_for_stage(PACK, "master")


def test_future_schedule_warning_does_not_block_stage(monkeypatch):
    _stub_preflight(monkeypatch, [SimpleNamespace(code="FUTURE_SCHEDULE", severity="WARNING")])
    for stage in ("master", "references", "replay", "all"):
        loader._preflight_ok_for_stage(PACK, stage)


def test_loader_requires_manifest_for_renamed_pack(tmp_path):
    source = tmp_path / "renamed"
    shutil.copytree(PACK, source)
    with pytest.raises(SubmissionImportError, match="SOURCE_MANIFEST_REQUIRED"):
        loader.dry_run(source, stage="all")
    checked = loader.dry_run(source, stage="all", manifest_path=MANIFEST)
    assert checked["status"] == "PASS" and checked["database_write"] is False


def test_loader_rejects_changed_workbook_against_manifest(tmp_path):
    source = tmp_path / "synthetic"
    shutil.copytree(PACK, source)
    shutil.copyfile(MANIFEST, tmp_path / "synthetic_manifest.json")
    workbook = source / "01_cong_viec.xlsx"
    with workbook.open("ab") as target:
        target.write(b"\n")
    for stage in ("master", "references", "replay", "all"):
        with pytest.raises(SubmissionImportError, match="SOURCE_CHECKSUM_MISMATCH"):
            loader.dry_run(source, stage=stage)
    for action in (loader.apply, loader.verify):
        with pytest.raises(SubmissionImportError, match="SOURCE_CHECKSUM_MISMATCH"):
            action(source, stage="all")


def test_loader_passes_manifest_to_preflight(monkeypatch):
    observed = []
    original = loader.run_preflight

    def tracked(source, **kwargs):
        observed.append(kwargs.get("manifest_path"))
        return original(source, **kwargs)

    monkeypatch.setattr(loader, "run_preflight", tracked)
    loader.dry_run(PACK, stage="all")
    assert observed == [MANIFEST]


def test_loader_rejects_preflight_checksum_failure_even_for_deferred_stage(monkeypatch):
    _stub_preflight(monkeypatch, [SimpleNamespace(code="FUTURE_TERMINAL_EVENT", severity="ERROR")])
    monkeypatch.setattr(loader, "run_preflight", lambda _source, **_kwargs: SimpleNamespace(
        issues=[SimpleNamespace(code="FUTURE_TERMINAL_EVENT", severity="ERROR")],
        status="FAIL", total_rows=101, orphan_count=0, source_checksum_verified=False,
    ))
    with pytest.raises(SubmissionImportError, match="SOURCE_CHECKSUM_MISMATCH"):
        loader._preflight_ok_for_stage(PACK, "master")


def test_loader_resolves_raw_manifest_format_without_reading_raw_data(tmp_path):
    source = tmp_path / "excel-data"
    shutil.copytree(PACK, source)
    synthetic = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw_format = {
        "workbooks": [
            {
                "file_name": entry["file_name"],
                "sha256": entry["sha256"],
                "size_bytes": (source / entry["file_name"]).stat().st_size,
                "sheets": [{"sheet_role": "data", "data_row_count": entry["row_count"]}],
            }
            for entry in synthetic["workbooks"]
        ],
    }
    (tmp_path / "DATA_SOURCE_MANIFEST.json").write_text(json.dumps(raw_format), encoding="utf-8")
    assert loader.dry_run(source, stage="all")["status"] == "PASS"


def test_loader_normalizes_source_datetime_to_utc():
    value = datetime.fromisoformat("2026-09-27T09:00:00+07:00")
    assert loader._utc(value, field="created_at") == datetime(2026, 9, 27, 2, tzinfo=UTC)


def test_security_shift_reference_payload_is_stable_across_patrol_statuses(monkeypatch):
    """A shift reference must not depend on any individual patrol window state."""

    start = datetime(2026, 9, 27, 2, tzinfo=UTC)
    source_rows = {
        "03_toa_nha_can_ho.xlsx": [
            {"tenant_code": "T1", "site_code": "SITE-1", "building_code": "BUILDING-1"},
        ],
        "07_an_ninh_tuan_tra.xlsx": [
            {
                "site_code": "SITE-1", "building_code": "BUILDING-1", "guard_username": "guard-1",
                "shift_code": "SHIFT-1", "scheduled_start": start,
                "scheduled_end": start.replace(hour=4), "patrol_point_code": "POINT-1",
                "window_start": start, "window_end": start.replace(hour=3),
                "patrol_status": "COMPLETED",
            },
            {
                "site_code": "SITE-1", "building_code": "BUILDING-1", "guard_username": "guard-1",
                "shift_code": "SHIFT-1", "scheduled_start": start,
                "scheduled_end": start.replace(hour=4), "patrol_point_code": "POINT-2",
                "window_start": start.replace(hour=3), "window_end": start.replace(hour=4),
                "patrol_status": "MISSED",
            },
        ],
    }
    tenant = SimpleNamespace(id=uuid4())
    site = SimpleNamespace(id=uuid4(), code="SITE-1")
    building = SimpleNamespace(id=uuid4(), code="BUILDING-1")
    guard = SimpleNamespace(id=uuid4())
    captured = []

    class Session:
        def __init__(self):
            self.shift = None

        def query(self, _model):
            return SimpleNamespace(count=lambda: 0)

        def scalar(self, statement):
            entity = statement.column_descriptions[0].get("entity")
            return self.shift if getattr(entity, "__name__", "") == "SecurityShift" else None

        def add(self, value):
            if type(value).__name__ == "SecurityShift":
                value.id = uuid4()
                self.shift = value

        def flush(self):
            pass

    monkeypatch.setattr(loader, "_rows", lambda _pack, file_name: source_rows.get(file_name, []))
    monkeypatch.setattr(loader, "_reference_site_building", lambda *_args: (tenant, site, building))
    monkeypatch.setattr(loader, "_reference_account_with_role", lambda *_args, **_kwargs: guard)
    monkeypatch.setattr(
        loader,
        "upsert_external_reference",
        lambda _session, _run, **kwargs: captured.append(kwargs),
    )

    session = Session()
    loader.load_references(session, object(), SimpleNamespace())

    assert len(captured) == 2
    assert {reference["target_id"] for reference in captured} == {session.shift.id}
    assert [reference["payload"] for reference in captured] == [
        {"shift_code": "SHIFT-1"},
        {"shift_code": "SHIFT-1"},
    ]


def test_replay_helper_includes_service_requests_before_other_domains(monkeypatch):
    order = []
    monkeypatch.setattr(loader, "_rows", lambda _pack, name: name)
    monkeypatch.setattr(loader, "_rows_with_tenant", lambda _pack, name: name)
    monkeypatch.setattr(loader, "_evidence_provider_from_env", lambda: None)
    monkeypatch.setattr(loader, "replay_service_requests", lambda *args, **kwargs: (
        order.append("service"), {"service_requests": 1},
    )[1])
    monkeypatch.setattr(loader, "replay_maintenance_cleaning", lambda *args, **kwargs: (
        order.append("maintenance"), {"maintenance_rows": 1},
    )[1])
    monkeypatch.setattr(loader, "replay_security_parcels", lambda *args, **kwargs: (
        order.append("security"), {"security_rows": 1},
    )[1])
    monkeypatch.setattr(loader, "replay_billing_run", lambda *args, **kwargs: (
        order.append("billing"), {"invoice_count": 1},
    )[1])
    monkeypatch.setattr(loader, "replay_payment_allocations", lambda *args, **kwargs: (
        order.append("payment"), {"payment_rows": 1},
    )[1])
    result = loader._replay_operations(
        object(), object(), object(), as_of_utc=datetime(2026, 9, 27, tzinfo=UTC),
        evidence_storage_root=Path("unused"), written_evidence_paths=[],
    )
    assert order == ["service", "maintenance", "security", "billing", "payment"]
    assert result["service_requests"] == 1
    assert result["fcs16_payments"]["payment_rows"] == 1


def test_tenant_enrichment_is_source_scoped_and_rejects_ambiguity(monkeypatch):
    source_rows = {
        "03_toa_nha_can_ho.xlsx": [
            {"tenant_code": "T1", "site_code": "S1", "building_code": "B1"},
        ],
        "06_ve_sinh.xlsx": [{"site_code": "S1", "building_code": "B1", "route_code": "R1"}],
    }
    monkeypatch.setattr(loader, "_rows", lambda _pack, name: source_rows[name])
    enriched = loader._rows_with_tenant(object(), "06_ve_sinh.xlsx")
    assert enriched[0]["tenant_code"] == "T1"
    assert "tenant_code" not in source_rows["06_ve_sinh.xlsx"][0]
    source_rows["03_toa_nha_can_ho.xlsx"].append(
        {"tenant_code": "T2", "site_code": "S1", "building_code": "B1"},
    )
    with pytest.raises(SubmissionImportError, match="STRUCTURE_CONTEXT_AMBIGUOUS"):
        loader._rows_with_tenant(object(), "06_ve_sinh.xlsx")


def test_verify_cli_writes_metadata_only_reconciliation_report(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    report_dir = tmp_path / "report"
    monkeypatch.setattr(loader, "verify", lambda _source, *, stage, manifest_path: {
        "status": "PASS", "stage": stage, "manifest_sha256": "0" * 64,
        "workbooks": 12, "rows": 101,
        "reconciliation": {"replay_invoices": 8, "invoice_delta_vnd": 0, "ar_delta_vnd": 0},
        "database_write": False,
    })
    monkeypatch.setattr(sys, "argv", ["load_submission_data.py", "--source", str(source),
                                      "--stage", "all", "--verify", "--report-dir", str(report_dir)])
    assert loader.main() == 0
    report = json.loads((report_dir / "submission-data-reconciliation.json").read_text(encoding="utf-8"))
    assert report["rows"] == 101 and report["reconciliation"]["ar_delta_vnd"] == 0
    assert set(report) == {"status", "stage", "manifest_sha256", "workbooks", "rows",
                           "reconciliation", "database_write"}
