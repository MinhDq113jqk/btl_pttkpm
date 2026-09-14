"""Add R4's executable fee, period and invoice-snapshot controls.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SCHEMA = "greencity"


def upgrade():
    op.add_column(
        "billing_fee_policy_versions",
        sa.Column("basis", sa.String(30), nullable=False, server_default="UNIT_AREA_M2"),
        schema=SCHEMA,
    )
    op.add_column(
        "billing_fee_policy_versions",
        sa.Column("rounding_unit_vnd", sa.BigInteger(), nullable=False, server_default="1"),
        schema=SCHEMA,
    )
    op.add_column(
        "billing_fee_policy_versions",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "billing_fee_policy_versions_basis",
        "billing_fee_policy_versions",
        "basis IN ('UNIT_AREA_M2')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "billing_fee_policy_versions_rounding_unit",
        "billing_fee_policy_versions",
        "rounding_unit_vnd > 0",
        schema=SCHEMA,
    )

    op.add_column(
        "accounting_periods",
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("timezone('UTC', now())")),
        schema=SCHEMA,
    )

    op.drop_constraint("billing_runs_status", "billing_runs", type_="check", schema=SCHEMA)
    op.create_check_constraint(
        "billing_runs_status",
        "billing_runs",
        "status IN ('DRAFT','CALCULATING','REVIEW','POSTED','FAILED','CANCELLED')",
        schema=SCHEMA,
    )
    op.add_column(
        "billing_runs",
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("timezone('UTC', now())")),
        schema=SCHEMA,
    )
    op.add_column("billing_runs", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"), schema=SCHEMA)
    op.add_column("billing_runs", sa.Column("failure_code", sa.String(80), nullable=True), schema=SCHEMA)
    op.add_column("billing_runs", sa.Column("failure_detail", sa.String(500), nullable=True), schema=SCHEMA)
    op.add_column("billing_runs", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("billing_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)

    op.add_column("billing_invoices", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("billing_invoices", sa.Column("voided_by_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.add_column("billing_invoices", sa.Column("void_reason", sa.String(500), nullable=True), schema=SCHEMA)
    op.create_foreign_key(
        "fk_billing_invoices_voided_by_id_accounts",
        "billing_invoices",
        "accounts",
        ["voided_by_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )

    op.add_column("billing_invoice_items", sa.Column("source_pending_charge_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.add_column(
        "billing_invoice_items",
        sa.Column("basis", sa.String(30), nullable=False, server_default="UNIT_AREA_M2"),
        schema=SCHEMA,
    )
    op.add_column(
        "billing_invoice_items",
        sa.Column("basis_quantity", sa.Numeric(12, 2), nullable=False, server_default="0"),
        schema=SCHEMA,
    )
    op.add_column(
        "billing_invoice_items",
        sa.Column("unit_rate_vnd_snapshot", sa.BigInteger(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )
    op.add_column(
        "billing_invoice_items",
        sa.Column("rounding_unit_vnd_snapshot", sa.BigInteger(), nullable=False, server_default="1"),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_billing_items_pending_charge",
        "billing_invoice_items",
        "pending_charges",
        ["source_pending_charge_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_billing_invoice_items_source_charge",
        "billing_invoice_items",
        ["source_pending_charge_id"],
        schema=SCHEMA,
    )

    op.execute("""
        CREATE FUNCTION greencity.reject_r4_invoice_item_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'billing_invoice_items are immutable snapshots';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_billing_invoice_items_immutable
        BEFORE UPDATE OR DELETE ON greencity.billing_invoice_items
        FOR EACH ROW EXECUTE FUNCTION greencity.reject_r4_invoice_item_mutation()
    """)
    op.execute("""
        CREATE FUNCTION greencity.enforce_r4_invoice_snapshot() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.billing_account_id IS DISTINCT FROM OLD.billing_account_id
               OR NEW.billing_run_id IS DISTINCT FROM OLD.billing_run_id
               OR NEW.accounting_period_id IS DISTINCT FROM OLD.accounting_period_id
               OR NEW.invoice_number IS DISTINCT FROM OLD.invoice_number
               OR NEW.total_vnd IS DISTINCT FROM OLD.total_vnd THEN
                RAISE EXCEPTION 'issued invoice snapshot fields are immutable';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_billing_invoices_snapshot_immutable
        BEFORE UPDATE ON greencity.billing_invoices
        FOR EACH ROW WHEN (OLD.status <> 'DRAFT')
        EXECUTE FUNCTION greencity.enforce_r4_invoice_snapshot()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_billing_invoices_snapshot_immutable ON greencity.billing_invoices")
    op.execute("DROP FUNCTION IF EXISTS greencity.enforce_r4_invoice_snapshot()")
    op.execute("DROP TRIGGER IF EXISTS trg_billing_invoice_items_immutable ON greencity.billing_invoice_items")
    op.execute("DROP FUNCTION IF EXISTS greencity.reject_r4_invoice_item_mutation()")
    op.drop_constraint("uq_billing_invoice_items_source_charge", "billing_invoice_items", type_="unique", schema=SCHEMA)
    op.drop_constraint(
        "fk_billing_items_pending_charge",
        "billing_invoice_items",
        type_="foreignkey",
        schema=SCHEMA,
    )
    for column in (
        "rounding_unit_vnd_snapshot", "unit_rate_vnd_snapshot", "basis_quantity", "basis", "source_pending_charge_id",
    ):
        op.drop_column("billing_invoice_items", column, schema=SCHEMA)

    op.drop_constraint("fk_billing_invoices_voided_by_id_accounts", "billing_invoices", type_="foreignkey", schema=SCHEMA)
    for column in ("void_reason", "voided_by_id", "voided_at"):
        op.drop_column("billing_invoices", column, schema=SCHEMA)

    for column in ("completed_at", "failed_at", "failure_detail", "failure_code", "retry_count", "cutoff_at"):
        op.drop_column("billing_runs", column, schema=SCHEMA)
    op.drop_constraint("billing_runs_status", "billing_runs", type_="check", schema=SCHEMA)
    op.create_check_constraint(
        "billing_runs_status",
        "billing_runs",
        "status IN ('DRAFT','CALCULATING','REVIEW','POSTED','CANCELLED')",
        schema=SCHEMA,
    )

    op.drop_column("accounting_periods", "cutoff_at", schema=SCHEMA)
    op.drop_constraint("billing_fee_policy_versions_rounding_unit", "billing_fee_policy_versions", type_="check", schema=SCHEMA)
    op.drop_constraint("billing_fee_policy_versions_basis", "billing_fee_policy_versions", type_="check", schema=SCHEMA)
    for column in ("published_at", "rounding_unit_vnd", "basis"):
        op.drop_column("billing_fee_policy_versions", column, schema=SCHEMA)
