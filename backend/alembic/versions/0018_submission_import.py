"""Add the controlled submission-pack import ledger and external references.

Revision ID: 0018
Revises: 0017

The tables contain only manifest metadata and non-PII source keys.  Workbook
cells, notes, credentials, PINs and raw payloads are intentionally excluded.
"""

from alembic import op
import sqlalchemy as sa


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

SCHEMA = "greencity"


def upgrade() -> None:
    # Existing installations may already have tenants without a source code;
    # keep the backfill nullable and let the loader fail closed on ambiguity.
    op.add_column("tenants", sa.Column("code", sa.String(length=50), nullable=True), schema=SCHEMA)
    op.create_unique_constraint("uq_tenants_code", "tenants", ["code"], schema=SCHEMA)
    op.create_index("ix_tenants_code", "tenants", ["code"], schema=SCHEMA)

    op.create_table(
        "submission_import_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False, server_default="excel-data"),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("workbook_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('PREFLIGHTED','DRY_RUN','APPLYING','APPLIED','FAILED')",
            name="submission_import_runs_status",
        ),
        sa.CheckConstraint("workbook_count >= 0 AND total_rows >= 0", name="submission_import_runs_counts"),
        sa.CheckConstraint("version >= 1", name="submission_import_runs_version_positive"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_import_runs")),
        sa.UniqueConstraint("manifest_sha256", "stage", name="uq_submission_import_runs_manifest_stage"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_submission_import_runs_status", "submission_import_runs", ["status", "stage"], schema=SCHEMA,
    )

    op.create_table(
        "submission_external_references",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("import_run_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("source_key", sa.String(length=240), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["import_run_id"], [f"{SCHEMA}.submission_import_runs.id"],
            name="fk_submission_external_references_import_run", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], [f"{SCHEMA}.tenants.id"],
            name="fk_submission_external_references_tenant", ondelete="CASCADE",
        ),
        sa.CheckConstraint("length(trim(source_key)) > 0", name="submission_external_references_key_not_blank"),
        sa.CheckConstraint("version >= 1", name="submission_external_references_version_positive"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_external_references")),
        sa.UniqueConstraint(
            "tenant_id", "source", "entity_type", "source_key",
            name="uq_submission_external_references_identity",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_submission_external_references_target", "submission_external_references", ["entity_type", "target_id"], schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM {SCHEMA}.submission_external_references)
               OR EXISTS (SELECT 1 FROM {SCHEMA}.submission_import_runs) THEN
                RAISE EXCEPTION 'Cannot downgrade while submission import evidence exists'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
        """,
    )
    op.drop_index("ix_submission_external_references_target", table_name="submission_external_references", schema=SCHEMA)
    op.drop_table("submission_external_references", schema=SCHEMA)
    op.drop_index("ix_submission_import_runs_status", table_name="submission_import_runs", schema=SCHEMA)
    op.drop_table("submission_import_runs", schema=SCHEMA)
    op.drop_index("ix_tenants_code", table_name="tenants", schema=SCHEMA)
    op.drop_constraint("uq_tenants_code", "tenants", schema=SCHEMA, type_="unique")
    op.drop_column("tenants", "code", schema=SCHEMA)
