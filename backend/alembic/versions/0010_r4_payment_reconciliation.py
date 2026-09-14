"""Make unmatched receipts explicit and fix allocation capacity accounting.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

SCHEMA = "greencity"


def _create_original_allocation_cap() -> None:
    """Restore 0009's function exactly when this migration is downgraded."""
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
              FROM greencity.payments WHERE id = NEW.payment_id FOR UPDATE;
            SELECT billing_account_id, outstanding_vnd
              INTO invoice_account, invoice_open
              FROM greencity.billing_invoices WHERE id = NEW.billing_invoice_id FOR UPDATE;
            IF payment_account IS DISTINCT FROM invoice_account THEN
                RAISE EXCEPTION 'Payment and Invoice must belong to the same Billing Account';
            END IF;
            SELECT COALESCE(SUM(amount_vnd), 0) INTO payment_allocated
              FROM greencity.payment_allocations WHERE payment_id = NEW.payment_id;
            SELECT COALESCE(SUM(amount_vnd), 0) INTO invoice_allocated
              FROM greencity.payment_allocations WHERE billing_invoice_id = NEW.billing_invoice_id;
            IF NEW.amount_vnd > payment_amount - payment_allocated
               OR NEW.amount_vnd > invoice_open - invoice_allocated THEN
                RAISE EXCEPTION 'Allocation exceeds available Payment or open Invoice balance';
            END IF;
            RETURN NEW;
        END;
        $$
    """)


def upgrade():
    op.alter_column("payments", "billing_account_id", nullable=True, schema=SCHEMA)
    op.execute("DROP TRIGGER IF EXISTS trg_payment_allocations_cap ON greencity.payment_allocations")
    op.execute("DROP FUNCTION IF EXISTS greencity.enforce_r4_payment_allocation_cap()")
    op.execute("""
        CREATE FUNCTION greencity.enforce_r4_payment_allocation_cap() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            payment_account uuid;
            payment_amount bigint;
            invoice_account uuid;
            invoice_total bigint;
            invoice_open bigint;
            invoice_status text;
            payment_allocated bigint;
            invoice_allocated bigint;
        BEGIN
            SELECT billing_account_id, amount_vnd
              INTO payment_account, payment_amount
              FROM greencity.payments WHERE id = NEW.payment_id FOR UPDATE;
            SELECT billing_account_id, total_vnd, outstanding_vnd, status
              INTO invoice_account, invoice_total, invoice_open, invoice_status
              FROM greencity.billing_invoices WHERE id = NEW.billing_invoice_id FOR UPDATE;
            IF payment_account IS NULL OR payment_account IS DISTINCT FROM invoice_account THEN
                RAISE EXCEPTION 'Payment and Invoice must belong to the same Billing Account';
            END IF;
            IF invoice_status NOT IN ('ISSUED', 'PARTIALLY_PAID') THEN
                RAISE EXCEPTION 'Allocation requires an open Invoice';
            END IF;
            SELECT COALESCE(SUM(amount_vnd), 0) INTO payment_allocated
              FROM greencity.payment_allocations WHERE payment_id = NEW.payment_id;
            SELECT COALESCE(SUM(amount_vnd), 0) INTO invoice_allocated
              FROM greencity.payment_allocations WHERE billing_invoice_id = NEW.billing_invoice_id;
            IF NEW.amount_vnd > payment_amount - payment_allocated
               OR NEW.amount_vnd > LEAST(invoice_open, invoice_total - invoice_allocated) THEN
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


def downgrade():
    # A 0009 schema cannot represent an unmatched payment. Refuse rather than
    # silently attach it to an arbitrary account or discard reconciliation data.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM greencity.unmatched_payments)
               OR EXISTS (SELECT 1 FROM greencity.payments WHERE billing_account_id IS NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade R4 payment reconciliation while unmatched payments exist';
            END IF;
        END;
        $$
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_payment_allocations_cap ON greencity.payment_allocations")
    op.execute("DROP FUNCTION IF EXISTS greencity.enforce_r4_payment_allocation_cap()")
    _create_original_allocation_cap()
    op.execute("""
        CREATE TRIGGER trg_payment_allocations_cap
        BEFORE INSERT ON greencity.payment_allocations
        FOR EACH ROW EXECUTE FUNCTION greencity.enforce_r4_payment_allocation_cap()
    """)
    op.alter_column("payments", "billing_account_id", nullable=False, schema=SCHEMA)
