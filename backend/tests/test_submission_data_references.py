"""Pure FCS-08/FCS-10 checks that do not require a shared database."""

from app.services.submission_data_import import (
    SubmissionImportError,
    canonical_payload_sha256,
    manifest_summary,
)
from app.services.submission_data_contract import WORKBOOK_CONTRACTS


def _manifest():
    return {
        "schema_version": "fcs05-r2",
        "workbooks": [
            {"file_name": f"{index:02d}.xlsx", "sha256": str(index).zfill(64), "row_count": index}
            for index in range(1, 13)
        ],
    }


def test_manifest_summary_is_stable_and_metadata_only():
    summary = manifest_summary(_manifest())
    assert summary.workbook_count == 12
    assert summary.total_rows == sum(range(1, 13))
    assert len(summary.manifest_sha256) == 64
    assert canonical_payload_sha256({"code": "UNIT-001"}) != canonical_payload_sha256({"code": "UNIT-002"})


def test_manifest_rejects_missing_workbooks_before_any_transaction():
    manifest = _manifest()
    manifest["workbooks"] = manifest["workbooks"][:-1]
    try:
        manifest_summary(manifest)
    except SubmissionImportError as error:
        assert error.code == "MANIFEST_WORKBOOK_COUNT"
    else:
        raise AssertionError("invalid manifest was accepted")


def test_fcs11_contract_keeps_operational_rows_separate_from_replay_states():
    contracts = {item.file_name: item for item in WORKBOOK_CONTRACTS}
    assert {"CleaningRoute", "CleaningShift", "CleaningTask"}.issubset(
        contracts["06_ve_sinh.xlsx"].target_entities,
    )
    assert {"SecurityShift", "PatrolWindow", "PatrolLog"}.issubset(
        contracts["07_an_ninh_tuan_tra.xlsx"].target_entities,
    )
    assert "Parcel" in contracts["12_buu_pham.xlsx"].target_entities
    assert any(field.source_name == "status" and field.disposition == "Validate"
               for field in contracts["12_buu_pham.xlsx"].fields)
