"""Add the scoped billing, receivables and payment foundation for R4.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

SCHEMA = "greencity"


def identity_columns():
    return (
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def scope_columns():
    return (
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("building_id", sa.Uuid(), nullable=False),
    )


def scope_constraints(table_name):
    return (
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"],
                                name=f"fk_{table_name}_tenant_id_tenants", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "tenant_id"], [f"{SCHEMA}.sites.id", f"{SCHEMA}.sites.tenant_id"],
                                name=f"fk_{table_name}_site_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["building_id", "site_id"], [f"{SCHEMA}.buildings.id", f"{SCHEMA}.buildings.site_id"],
                                name=f"fk_{table_name}_building_site", ondelete="CASCADE"),
    )


def upgrade():
    op.create_table(
        "billing_accounts",
        *identity_columns(), *scope_columns(),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("account_number", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("opened_on", sa.Date(), nullable=False),
        sa.Column("closed_on", sa.Date(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("billing_accounts"),
        sa.ForeignKeyConstraint(["unit_id", "building_id"], [f"{SCHEMA}.units.id", f"{SCHEMA}.units.building_id"],
                                name="fk_billing_accounts_unit_building", ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('ACTIVE','SUSPENDED','CLOSED')", name="billing_accounts_status"),
        sa.PrimaryKeyConstraint("id", name="pk_billing_accounts"),
        sa.UniqueConstraint("id", "building_id", name="uq_billing_accounts_id_building"),
        sa.UniqueConstraint("building_id", "unit_id", name="uq_billing_accounts_building_unit"),
        sa.UniqueConstraint("site_id", "account_number", name="uq_billing_accounts_site_number"),
        schema=SCHEMA,
    )
    op.create_index("ix_billing_accounts_scope_status", "billing_accounts",
                    ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA)

    op.create_table(
        "billing_fee_policies",
        *identity_columns(), *scope_columns(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *scope_constraints("billing_fee_policies"),
        sa.PrimaryKeyConstraint("id", name="pk_billing_fee_policies"),
        sa.UniqueConstraint("id", "building_id", name="uq_billing_fee_policies_id_building"),
        sa.UniqueConstraint("building_id", "code", name="uq_billing_fee_policies_building_code"),
        schema=SCHEMA,
    )
    op.create_index("ix_billing_fee_policies_scope_active", "billing_fee_policies",
                    ["tenant_id", "site_id", "building_id", "is_active"], schema=SCHEMA)

    op.create_table(
        "billing_fee_policy_versions",
        *identity_columns(), *scope_columns(),
        sa.Column("fee_policy_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("unit_rate_vnd", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("billing_fee_policy_versions"),
        sa.ForeignKeyConstraint(["fee_policy_id", "building_id"],
                                [f"{SCHEMA}.billing_fee_policies.id", f"{SCHEMA}.billing_fee_policies.building_id"],
                                name="fk_billing_fee_policy_versions_policy_building", ondelete="RESTRICT"),
        sa.CheckConstraint("unit_rate_vnd >= 0", name="billing_fee_policy_versions_rate_nonnegative"),
        sa.CheckConstraint("version_number > 0", name="billing_fee_policy_versions_version_positive"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="billing_fee_policy_versions_dates"),
        sa.PrimaryKeyConstraint("id", name="pk_billing_fee_policy_versions"),
        sa.UniqueConstraint("id", "building_id", name="uq_billing_fee_policy_versions_id_building"),
        sa.UniqueConstraint("fee_policy_id", "version_number", name="uq_billing_fee_policy_versions_policy_version"),
        sa.UniqueConstraint("fee_policy_id", "effective_from", name="uq_billing_fee_policy_versions_policy_effective"),
        schema=SCHEMA,
    )
    op.create_index("ix_billing_fee_policy_versions_scope_effective", "billing_fee_policy_versions",
                    ["tenant_id", "site_id", "building_id", "effective_from"], schema=SCHEMA)

    op.create_table(
        "accounting_periods",
        *identity_columns(), *scope_columns(),
        sa.Column("period_key", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("accounting_periods"),
        sa.CheckConstraint("period_end >= period_start", name="accounting_periods_dates"),
        sa.CheckConstraint("status IN ('OPEN','CLOSING','CLOSED','LOCKED')", name="accounting_periods_status"),
        sa.PrimaryKeyConstraint("id", name="pk_accounting_periods"),
        sa.UniqueConstraint("id", "building_id", name="uq_accounting_periods_id_building"),
        sa.UniqueConstraint("building_id", "period_key", name="uq_accounting_periods_building_key"),
        schema=SCHEMA,
    )
    op.create_index("ix_accounting_periods_scope_status", "accounting_periods",
                    ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA)

    op.create_table(
        "billing_runs",
        *identity_columns(), *scope_columns(),
        sa.Column("accounting_period_id", sa.Uuid(), nullable=False),
        sa.Column("fee_policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("run_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("initiated_by_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("billing_runs"),
        sa.ForeignKeyConstraint(["accounting_period_id", "building_id"],
                                [f"{SCHEMA}.accounting_periods.id", f"{SCHEMA}.accounting_periods.building_id"],
                                name="fk_billing_runs_period_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fee_policy_version_id", "building_id"],
                                [f"{SCHEMA}.billing_fee_policy_versions.id", f"{SCHEMA}.billing_fee_policy_versions.building_id"],
                                name="fk_billing_runs_policy_version_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["initiated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('DRAFT','CALCULATING','REVIEW','POSTED','CANCELLED')", name="billing_runs_status"),
        sa.PrimaryKeyConstraint("id", name="pk_billing_runs"),
        sa.UniqueConstraint("id", "building_id", name="uq_billing_runs_id_building"),
        sa.UniqueConstraint("id", "accounting_period_id", "building_id", name="uq_billing_runs_id_period_building"),
        sa.UniqueConstraint("site_id", "run_key", name="uq_billing_runs_site_key"),
        sa.UniqueConstraint("building_id", "accounting_period_id", "fee_policy_version_id", name="uq_billing_runs_period_policy"),
        schema=SCHEMA,
    )
    op.create_index("ix_billing_runs_scope_status", "billing_runs",
                    ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA)

    op.create_table(
        "billing_invoices",
        *identity_columns(), *scope_columns(),
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("billing_run_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_period_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(80), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("total_vnd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("outstanding_vnd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("billing_invoices"),
        sa.ForeignKeyConstraint(["billing_account_id", "building_id"],
                                [f"{SCHEMA}.billing_accounts.id", f"{SCHEMA}.billing_accounts.building_id"],
                                name="fk_billing_invoices_account_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["billing_run_id", "accounting_period_id", "building_id"],
                                [f"{SCHEMA}.billing_runs.id", f"{SCHEMA}.billing_runs.accounting_period_id", f"{SCHEMA}.billing_runs.building_id"],
                                name="fk_billing_invoices_run_period_building", ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('DRAFT','ISSUED','PARTIALLY_PAID','PAID','VOID')", name="billing_invoices_status"),
        sa.CheckConstraint("total_vnd >= 0 AND outstanding_vnd >= 0 AND outstanding_vnd <= total_vnd", name="billing_invoices_amounts"),
        sa.PrimaryKeyConstraint("id", name="pk_billing_invoices"),
        sa.UniqueConstraint("id", "building_id", name="uq_billing_invoices_id_building"),
        sa.UniqueConstraint("site_id", "invoice_number", name="uq_billing_invoices_site_number"),
        sa.UniqueConstraint("billing_account_id", "accounting_period_id", name="uq_billing_invoices_account_period"),
        schema=SCHEMA,
    )
    op.create_index("ix_billing_invoices_scope_status", "billing_invoices",
                    ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA)

    op.create_table(
        "billing_invoice_items",
        *identity_columns(), *scope_columns(),
        sa.Column("billing_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("fee_policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("amount_vnd", sa.BigInteger(), nullable=False),
        *scope_constraints("billing_invoice_items"),
        sa.ForeignKeyConstraint(["billing_invoice_id", "building_id"],
                                [f"{SCHEMA}.billing_invoices.id", f"{SCHEMA}.billing_invoices.building_id"],
                                name="fk_billing_invoice_items_invoice_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fee_policy_version_id", "building_id"],
                                [f"{SCHEMA}.billing_fee_policy_versions.id", f"{SCHEMA}.billing_fee_policy_versions.building_id"],
                                name="fk_billing_invoice_items_policy_version_building", ondelete="RESTRICT"),
        sa.CheckConstraint("line_number > 0", name="billing_invoice_items_line_positive"),
        sa.CheckConstraint("amount_vnd >= 0", name="billing_invoice_items_amount_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_billing_invoice_items"),
        sa.UniqueConstraint("billing_invoice_id", "line_number", name="uq_billing_invoice_items_invoice_line"),
        schema=SCHEMA,
    )
    op.create_index("ix_billing_invoice_items_invoice", "billing_invoice_items",
                    ["billing_invoice_id", "line_number"], schema=SCHEMA)

    op.create_table(
        "payments",
        *identity_columns(), *scope_columns(),
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_period_id", sa.Uuid(), nullable=False),
        sa.Column("payment_source", sa.String(20), nullable=False),
        sa.Column("source_reference", sa.String(120), nullable=False),
        sa.Column("receipt_number", sa.String(80), nullable=False),
        sa.Column("amount_vnd", sa.BigInteger(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="RECEIVED"),
        sa.Column("received_by_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("payments"),
        sa.ForeignKeyConstraint(["billing_account_id", "building_id"],
                                [f"{SCHEMA}.billing_accounts.id", f"{SCHEMA}.billing_accounts.building_id"],
                                name="fk_payments_account_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accounting_period_id", "building_id"],
                                [f"{SCHEMA}.accounting_periods.id", f"{SCHEMA}.accounting_periods.building_id"],
                                name="fk_payments_period_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["received_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("payment_source IN ('CASH','BANK_TRANSFER','GATEWAY')", name="payments_source"),
        sa.CheckConstraint("status IN ('RECEIVED','ALLOCATING','PARTIALLY_ALLOCATED','ALLOCATED','UNMATCHED','OVERPAID','REVERSED')", name="payments_status"),
        sa.CheckConstraint("amount_vnd > 0", name="payments_amount_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint("id", "building_id", name="uq_payments_id_building"),
        sa.UniqueConstraint("tenant_id", "site_id", "payment_source", "source_reference", name="uq_payments_source_reference"),
        sa.UniqueConstraint("tenant_id", "site_id", "receipt_number", name="uq_payments_receipt_number"),
        schema=SCHEMA,
    )
    op.create_index("ix_payments_scope_received", "payments",
                    ["tenant_id", "site_id", "building_id", "received_at"], schema=SCHEMA)

    op.create_table(
        "payment_allocations",
        *identity_columns(), *scope_columns(),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("billing_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("amount_vnd", sa.BigInteger(), nullable=False),
        sa.Column("allocated_by_id", sa.Uuid(), nullable=True),
        *scope_constraints("payment_allocations"),
        sa.ForeignKeyConstraint(["payment_id", "building_id"],
                                [f"{SCHEMA}.payments.id", f"{SCHEMA}.payments.building_id"],
                                name="fk_payment_allocations_payment_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["billing_invoice_id", "building_id"],
                                [f"{SCHEMA}.billing_invoices.id", f"{SCHEMA}.billing_invoices.building_id"],
                                name="fk_payment_allocations_invoice_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["allocated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("amount_vnd > 0", name="payment_allocations_amount_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_payment_allocations"),
        sa.UniqueConstraint("payment_id", "billing_invoice_id", name="uq_payment_allocations_payment_invoice"),
        schema=SCHEMA,
    )
    op.create_index("ix_payment_allocations_invoice", "payment_allocations", ["billing_invoice_id"], schema=SCHEMA)

    op.create_table(
        "unmatched_payments",
        *identity_columns(), *scope_columns(),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("amount_vnd", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("unmatched_payments"),
        sa.ForeignKeyConstraint(["payment_id", "building_id"],
                                [f"{SCHEMA}.payments.id", f"{SCHEMA}.payments.building_id"],
                                name="fk_unmatched_payments_payment_building", ondelete="RESTRICT"),
        sa.CheckConstraint("amount_vnd > 0", name="unmatched_payments_amount_positive"),
        sa.CheckConstraint("status IN ('OPEN','RESOLVED','REFUNDED')", name="unmatched_payments_status"),
        sa.PrimaryKeyConstraint("id", name="pk_unmatched_payments"),
        sa.UniqueConstraint("payment_id", name="uq_unmatched_payments_payment"),
        schema=SCHEMA,
    )
    op.create_index("ix_unmatched_payments_scope_status", "unmatched_payments",
                    ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA)

    op.create_table(
        "overpayment_credits",
        *identity_columns(), *scope_columns(),
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("original_vnd", sa.BigInteger(), nullable=False),
        sa.Column("remaining_vnd", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("overpayment_credits"),
        sa.ForeignKeyConstraint(["billing_account_id", "building_id"],
                                [f"{SCHEMA}.billing_accounts.id", f"{SCHEMA}.billing_accounts.building_id"],
                                name="fk_overpayment_credits_account_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id", "building_id"],
                                [f"{SCHEMA}.payments.id", f"{SCHEMA}.payments.building_id"],
                                name="fk_overpayment_credits_payment_building", ondelete="RESTRICT"),
        sa.CheckConstraint("original_vnd > 0 AND remaining_vnd >= 0 AND remaining_vnd <= original_vnd", name="overpayment_credits_amounts"),
        sa.CheckConstraint("status IN ('OPEN','EXHAUSTED','VOID')", name="overpayment_credits_status"),
        sa.PrimaryKeyConstraint("id", name="pk_overpayment_credits"),
        sa.UniqueConstraint("payment_id", name="uq_overpayment_credits_payment"),
        schema=SCHEMA,
    )
    op.create_index("ix_overpayment_credits_scope_status", "overpayment_credits",
                    ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA)

    op.create_table(
        "ar_ledger_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *scope_columns(),
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_period_id", sa.Uuid(), nullable=False),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("debit_vnd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("credit_vnd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        *scope_constraints("ar_ledger_entries"),
        sa.ForeignKeyConstraint(["billing_account_id", "building_id"],
                                [f"{SCHEMA}.billing_accounts.id", f"{SCHEMA}.billing_accounts.building_id"],
                                name="fk_ar_ledger_entries_account_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accounting_period_id", "building_id"],
                                [f"{SCHEMA}.accounting_periods.id", f"{SCHEMA}.accounting_periods.building_id"],
                                name="fk_ar_ledger_entries_period_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("entry_type IN ('INVOICE_ISSUED','PAYMENT_RECEIVED','CREDIT_ISSUED','CREDIT_APPLIED','REVERSAL')", name="ar_ledger_entries_type"),
        sa.CheckConstraint("(debit_vnd > 0 AND credit_vnd = 0) OR (credit_vnd > 0 AND debit_vnd = 0)", name="ar_ledger_entries_one_sided"),
        sa.PrimaryKeyConstraint("id", name="pk_ar_ledger_entries"),
        sa.UniqueConstraint("source_type", "source_id", "entry_type", name="uq_ar_ledger_entries_source_type"),
        schema=SCHEMA,
    )
    op.create_index("ix_ar_ledger_entries_account_effective", "ar_ledger_entries",
                    ["billing_account_id", "effective_at", "id"], schema=SCHEMA)
    op.create_index("ix_ar_ledger_entries_scope_period", "ar_ledger_entries",
                    ["tenant_id", "site_id", "building_id", "accounting_period_id"], schema=SCHEMA)

    op.execute("""
        CREATE FUNCTION greencity.enforce_r4_payment_allocation_cap() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            payment_account uuid;
            payment_amount bigint;
            invoice_account uuid;
            invoice_open bigint;
            payment_allocated bigint;
            invoice_allocated bigint;
        BEGIN
            SELECT billing_account_id, amount_vnd
              INTO payment_account, payment_amount
              FROM greencity.payments
             WHERE id = NEW.payment_id
             FOR UPDATE;
            SELECT billing_account_id, outstanding_vnd
              INTO invoice_account, invoice_open
              FROM greencity.billing_invoices
             WHERE id = NEW.billing_invoice_id
             FOR UPDATE;
            IF payment_account IS DISTINCT FROM invoice_account THEN
                RAISE EXCEPTION 'Payment and Invoice must belong to the same Billing Account';
            END IF;
            SELECT COALESCE(SUM(amount_vnd), 0)
              INTO payment_allocated
              FROM greencity.payment_allocations
             WHERE payment_id = NEW.payment_id;
            SELECT COALESCE(SUM(amount_vnd), 0)
              INTO invoice_allocated
              FROM greencity.payment_allocations
             WHERE billing_invoice_id = NEW.billing_invoice_id;
            IF NEW.amount_vnd > payment_amount - payment_allocated
               OR NEW.amount_vnd > invoice_open - invoice_allocated THEN
                RAISE EXCEPTION 'Allocation exceeds available Payment or open Invoice balance';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_payment_allocations_cap
        BEFORE INSERT ON greencity.payment_allocations
        FOR EACH ROW EXECUTE FUNCTION greencity.enforce_r4_payment_allocation_cap()
    """)
    op.execute("""
        CREATE FUNCTION greencity.reject_r4_ledger_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'ar_ledger_entries are append-only';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_ar_ledger_entries_append_only
        BEFORE UPDATE OR DELETE ON greencity.ar_ledger_entries
        FOR EACH ROW EXECUTE FUNCTION greencity.reject_r4_ledger_mutation()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_payment_allocations_cap ON greencity.payment_allocations")
    op.execute("DROP FUNCTION IF EXISTS greencity.enforce_r4_payment_allocation_cap()")
    op.execute("DROP TRIGGER IF EXISTS trg_ar_ledger_entries_append_only ON greencity.ar_ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS greencity.reject_r4_ledger_mutation()")
    for table in (
        "ar_ledger_entries",
        "overpayment_credits",
        "unmatched_payments",
        "payment_allocations",
        "payments",
        "billing_invoice_items",
        "billing_invoices",
        "billing_runs",
        "accounting_periods",
        "billing_fee_policy_versions",
        "billing_fee_policies",
        "billing_accounts",
    ):
        op.drop_table(table, schema=SCHEMA)
