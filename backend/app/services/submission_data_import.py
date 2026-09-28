"""Transactional/idempotent primitives shared by the submission loader.

This module deliberately does not know how to replay a domain state machine.
It owns the import-run envelope and the non-PII external-reference ledger so
master/reference stages can be retried without creating duplicate identities.
Callers must provide a SQLAlchemy transaction and invoke domain commands for
business mutations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any, Mapping
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.submission_import import SubmissionExternalReference, SubmissionImportRun


IMPORT_SERVICE_VERSION = "fcs08-r1"


class SubmissionImportError(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class ManifestSummary:
    manifest_sha256: str
    schema_version: str
    workbook_count: int
    total_rows: int


@dataclass(frozen=True)
class ImportRunResult:
    run: SubmissionImportRun
    replayed: bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_payload_sha256(payload: Mapping[str, Any]) -> str:
    """Hash canonical metadata; never persist the payload itself."""

    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SubmissionImportError("IMPORT_PAYLOAD_INVALID") from exc
    return sha256(encoded).hexdigest()


def manifest_summary(manifest: Mapping[str, Any]) -> ManifestSummary:
    """Validate a metadata-only manifest and derive its stable identity."""

    workbooks = manifest.get("workbooks")
    if not isinstance(workbooks, list) or len(workbooks) != 12:
        raise SubmissionImportError("MANIFEST_WORKBOOK_COUNT")
    schema_version = manifest.get("schema_version") or manifest.get("contract_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise SubmissionImportError("MANIFEST_SCHEMA_VERSION")
    total_rows = 0
    normalized: list[dict[str, Any]] = []
    for item in workbooks:
        if not isinstance(item, Mapping):
            raise SubmissionImportError("MANIFEST_ENTRY_INVALID")
        file_name = item.get("file_name")
        digest = item.get("sha256")
        rows = item.get("row_count", item.get("data_row_count"))
        if (
            not isinstance(file_name, str) or not file_name.endswith(".xlsx")
            or not isinstance(digest, str) or len(digest) != 64
            or not isinstance(rows, int) or rows < 0
        ):
            raise SubmissionImportError("MANIFEST_ENTRY_INVALID")
        total_rows += rows
        normalized.append({"file_name": file_name, "sha256": digest.lower(), "row_count": rows})
    normalized.sort(key=lambda item: item["file_name"])
    manifest_sha = canonical_payload_sha256({"schema_version": schema_version, "workbooks": normalized})
    return ManifestSummary(manifest_sha, schema_version, len(normalized), total_rows)


def start_import_run(
    session: Session,
    summary: ManifestSummary,
    *,
    stage: str,
    correlation_id: UUID | None = None,
) -> ImportRunResult:
    """Return the existing run for the same manifest/stage or create one."""

    normalized_stage = stage.strip().lower()
    if not normalized_stage or len(normalized_stage) > 40:
        raise SubmissionImportError("IMPORT_STAGE_INVALID")
    existing = session.scalar(
        select(SubmissionImportRun)
        .where(
            SubmissionImportRun.manifest_sha256 == summary.manifest_sha256,
            SubmissionImportRun.stage == normalized_stage,
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.schema_version != summary.schema_version:
            raise SubmissionImportError("IMPORT_MANIFEST_CONFLICT")
        return ImportRunResult(existing, True)
    run = SubmissionImportRun(
        id=uuid4(),
        manifest_sha256=summary.manifest_sha256,
        schema_version=summary.schema_version,
        stage=normalized_stage,
        status="PREFLIGHTED",
        correlation_id=correlation_id or uuid4(),
        workbook_count=summary.workbook_count,
        total_rows=summary.total_rows,
        version=1,
    )
    session.add(run)
    session.flush()
    return ImportRunResult(run, False)


def mark_run_status(
    run: SubmissionImportRun,
    status: str,
    *,
    failure_code: str | None = None,
) -> None:
    allowed = {"PREFLIGHTED", "DRY_RUN", "APPLYING", "APPLIED", "FAILED"}
    if status not in allowed:
        raise SubmissionImportError("IMPORT_STATUS_INVALID")
    run.status = status
    run.failure_code = failure_code
    run.updated_at = _utc_now()
    run.version += 1


def upsert_external_reference(
    session: Session,
    run: SubmissionImportRun,
    *,
    tenant_id: UUID,
    source: str,
    entity_type: str,
    source_key: str,
    target_id: UUID,
    payload: Mapping[str, Any],
) -> tuple[SubmissionExternalReference, bool]:
    """Insert or replay a reference; reject an identity with changed payload."""

    source = source.strip()
    entity_type = entity_type.strip()
    source_key = source_key.strip()
    if not source or not entity_type or not source_key or len(source_key) > 240:
        raise SubmissionImportError("IMPORT_REFERENCE_KEY_INVALID")
    payload_sha = canonical_payload_sha256(payload)
    existing = session.scalar(
        select(SubmissionExternalReference)
        .where(
            SubmissionExternalReference.tenant_id == tenant_id,
            SubmissionExternalReference.source == source,
            SubmissionExternalReference.entity_type == entity_type,
            SubmissionExternalReference.source_key == source_key,
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.payload_sha256 != payload_sha or existing.target_id != target_id:
            raise SubmissionImportError("IMPORT_REFERENCE_CONFLICT")
        return existing, True
    reference = SubmissionExternalReference(
        id=uuid4(),
        import_run_id=run.id,
        tenant_id=tenant_id,
        source=source,
        entity_type=entity_type,
        source_key=source_key,
        target_id=target_id,
        payload_sha256=payload_sha,
        version=1,
    )
    session.add(reference)
    session.flush()
    return reference, False


def assert_apply_allowed(run: SubmissionImportRun, *, manifest_sha256: str) -> None:
    """Guard apply against a different or failed preflight envelope."""

    if run.manifest_sha256 != manifest_sha256:
        raise SubmissionImportError("IMPORT_MANIFEST_CONFLICT")
    if run.status not in {"PREFLIGHTED", "DRY_RUN", "APPLYING", "APPLIED"}:
        raise SubmissionImportError("IMPORT_RUN_NOT_APPLYABLE")


__all__ = [
    "IMPORT_SERVICE_VERSION",
    "ImportRunResult",
    "ManifestSummary",
    "SubmissionImportError",
    "assert_apply_allowed",
    "canonical_payload_sha256",
    "manifest_summary",
    "mark_run_status",
    "start_import_run",
    "upsert_external_reference",
]
