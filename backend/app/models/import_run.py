"""Persistent, server-scoped CSV import runs for the R1 Unit import flow."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityTimestampMixin


class ImportRun(IdentityTimestampMixin, Base):
    """A bounded CSV import whose scope is derived from the authenticated session."""

    __tablename__ = "import_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["site_id", "tenant_id"],
            ["greencity.sites.id", "greencity.sites.tenant_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["building_id", "site_id"],
            ["greencity.buildings.id", "greencity.buildings.site_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "mode IN ('PARTIAL','ALL_OR_NOTHING')",
            name="mode_allowed",
        ),
        CheckConstraint(
            "status IN ('UPLOADED','VALIDATING','PREVIEWED','APPLYING','APPLIED','FAILED')",
            name="status_allowed",
        ),
        CheckConstraint(
            "source_size_bytes > 0 AND source_size_bytes <= 10485760",
            name="source_size_range",
        ),
        CheckConstraint(
            "total_rows >= 0 AND valid_rows >= 0 AND warning_rows >= 0 "
            "AND error_rows >= 0 AND skipped_rows >= 0 AND applied_rows >= 0",
            name="counts_nonnegative",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_import_runs_scope_status", "tenant_id", "site_id", "building_id", "status"),
        Index("ix_import_runs_source_sha256", "tenant_id", "site_id", "building_id", "source_sha256"),
        Index("ix_import_runs_created_by_id", "created_by_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False,
    )
    site_id: Mapped[UUID] = mapped_column(nullable=False)
    building_id: Mapped[UUID] = mapped_column(nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UPLOADED")
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    source_mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_is_quarantined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_quarantine_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mapping_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mapping_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    applied_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    processed_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    rows = relationship(
        "ImportRunRow",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ImportRunRow.row_number",
    )

    @property
    def error_file_available(self) -> bool:
        return self.error_storage_key is not None and not self.source_is_quarantined


class ImportRunRow(IdentityTimestampMixin, Base):
    """Sanitized per-row validation/result data; raw CSV stays in private storage."""

    __tablename__ = "import_run_rows"
    __table_args__ = (
        CheckConstraint("row_number > 0", name="row_number_positive"),
        CheckConstraint(
            "status IN ('VALIDATED','WARNING','ERROR','IMPORTED','SKIPPED')",
            name="status_allowed",
        ),
        UniqueConstraint("import_run_id", "row_number", name="uq_import_run_rows_run_row"),
        Index("ix_import_run_rows_run_status", "import_run_id", "status"),
    )

    import_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("greencity.import_runs.id", ondelete="CASCADE"), nullable=False,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    run = relationship("ImportRun", back_populates="rows")
