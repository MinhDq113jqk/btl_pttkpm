"""Add durable, scoped Unit CSV import runs.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

SCHEMA = "greencity"


def upgrade():
    op.create_table(
        "import_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("building_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="UPLOADED"),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("source_storage_key", sa.String(255), nullable=False),
        sa.Column("source_mime_type", sa.String(80), nullable=False),
        sa.Column("source_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_is_quarantined", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_quarantine_reason", sa.String(100), nullable=True),
        sa.Column("mapping_json", sa.JSON(), nullable=True),
        sa.Column("mapping_hash", sa.String(64), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("applied_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_filename", sa.String(255), nullable=True),
        sa.Column("error_storage_key", sa.String(255), nullable=True),
        sa.Column("error_sha256", sa.String(64), nullable=True),
        sa.Column("error_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column("processed_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "tenant_id"], [f"{SCHEMA}.sites.id", f"{SCHEMA}.sites.tenant_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["building_id", "site_id"], [f"{SCHEMA}.buildings.id", f"{SCHEMA}.buildings.site_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("mode IN ('PARTIAL','ALL_OR_NOTHING')", name="mode_allowed"),
        sa.CheckConstraint("status IN ('UPLOADED','VALIDATING','PREVIEWED','APPLYING','APPLIED','FAILED')", name="status_allowed"),
        sa.CheckConstraint("source_size_bytes > 0 AND source_size_bytes <= 10485760", name="source_size_range"),
        sa.CheckConstraint("total_rows >= 0 AND valid_rows >= 0 AND warning_rows >= 0 AND error_rows >= 0 AND skipped_rows >= 0 AND applied_rows >= 0", name="counts_nonnegative"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_import_runs"),
        sa.UniqueConstraint("source_storage_key", name="uq_import_runs_source_storage_key"),
        schema=SCHEMA,
    )
    op.create_index("ix_import_runs_scope_status", "import_runs", ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA)
    op.create_index("ix_import_runs_source_sha256", "import_runs", ["tenant_id", "site_id", "building_id", "source_sha256"], schema=SCHEMA)
    op.create_index("ix_import_runs_created_by_id", "import_runs", ["created_by_id"], schema=SCHEMA)

    op.create_table(
        "import_run_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("import_run_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["import_run_id"], [f"{SCHEMA}.import_runs.id"], ondelete="CASCADE"),
        sa.CheckConstraint("row_number > 0", name="row_number_positive"),
        sa.CheckConstraint("status IN ('VALIDATED','WARNING','ERROR','IMPORTED','SKIPPED')", name="status_allowed"),
        sa.PrimaryKeyConstraint("id", name="pk_import_run_rows"),
        sa.UniqueConstraint("import_run_id", "row_number", name="uq_import_run_rows_run_row"),
        schema=SCHEMA,
    )
    op.create_index("ix_import_run_rows_run_status", "import_run_rows", ["import_run_id", "status"], schema=SCHEMA)


def downgrade():
    op.drop_table("import_run_rows", schema=SCHEMA)
    op.drop_table("import_runs", schema=SCHEMA)
