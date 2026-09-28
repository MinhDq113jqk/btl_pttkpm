"""Persistence metadata for the approved submission-pack loader."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityTimestampMixin


class SubmissionImportRun(IdentityTimestampMixin, Base):
    __tablename__ = "submission_import_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PREFLIGHTED','DRY_RUN','APPLYING','APPLIED','FAILED')",
            name="submission_import_runs_status",
        ),
        CheckConstraint("workbook_count >= 0 AND total_rows >= 0", name="submission_import_runs_counts"),
        CheckConstraint("version >= 1", name="submission_import_runs_version_positive"),
        UniqueConstraint("manifest_sha256", "stage", name="uq_submission_import_runs_manifest_stage"),
        Index("ix_submission_import_runs_status", "status", "stage"),
    )

    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="excel-data")
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PREFLIGHTED")
    correlation_id: Mapped[UUID] = mapped_column(nullable=False)
    workbook_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    external_references = relationship(
        "SubmissionExternalReference", back_populates="import_run", cascade="all, delete-orphan",
    )


class SubmissionExternalReference(IdentityTimestampMixin, Base):
    __tablename__ = "submission_external_references"
    __table_args__ = (
        CheckConstraint("length(trim(source_key)) > 0", name="submission_external_references_key_not_blank"),
        CheckConstraint("version >= 1", name="submission_external_references_version_positive"),
        UniqueConstraint(
            "tenant_id", "source", "entity_type", "source_key",
            name="uq_submission_external_references_identity",
        ),
        Index("ix_submission_external_references_target", "entity_type", "target_id"),
    )

    import_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("greencity.submission_import_runs.id", ondelete="CASCADE"), nullable=False,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_key: Mapped[str] = mapped_column(String(240), nullable=False)
    target_id: Mapped[UUID] = mapped_column(nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    import_run = relationship("SubmissionImportRun", back_populates="external_references")
