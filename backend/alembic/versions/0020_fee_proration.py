"""Preserve fee activation intervals and invoice calculation evidence.

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None
SCHEMA = "greencity"


def upgrade():
    op.add_column("portal_fee_sources", sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"), schema=SCHEMA)
    op.create_check_constraint("portal_fee_sources_status", "portal_fee_sources", "status IN ('ACTIVE','PAUSED','ENDED')", schema=SCHEMA)
    op.execute("UPDATE greencity.portal_fee_sources SET status='ENDED' WHERE valid_to IS NOT NULL")
    op.add_column("billing_invoice_items", sa.Column("calculation_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")), schema=SCHEMA)
    op.create_table("portal_fee_intervals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("fee_source_id", sa.Uuid(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("amount_vnd", sa.BigInteger(), nullable=False),
        sa.Column("rounding_unit_vnd", sa.BigInteger(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["fee_source_id"], ["greencity.portal_fee_sources.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="portal_fee_intervals_dates"),
        sa.CheckConstraint("amount_vnd >= 0 AND rounding_unit_vnd > 0", name="portal_fee_intervals_amounts"),
        schema=SCHEMA)
    op.create_index("ix_portal_fee_intervals_source_dates", "portal_fee_intervals", ["fee_source_id", "starts_on"], schema=SCHEMA)
    op.create_index("uq_portal_fee_intervals_open", "portal_fee_intervals", ["fee_source_id"], unique=True,
                    postgresql_where=sa.text("ends_on IS NULL"), schema=SCHEMA)
    # This backfill records existing source dates; issued amounts are untouched.
    op.execute("""INSERT INTO greencity.portal_fee_intervals
        (id, fee_source_id, starts_on, ends_on, amount_vnd)
        SELECT gen_random_uuid(), id, valid_from, valid_to, amount_vnd
        FROM greencity.portal_fee_sources WHERE recurring""")


def downgrade():
    op.drop_table("portal_fee_intervals", schema=SCHEMA)
    op.drop_column("billing_invoice_items", "calculation_snapshot", schema=SCHEMA)
    op.drop_constraint(op.f("ck_portal_fee_sources_portal_fee_sources_status"), "portal_fee_sources", type_="check", schema=SCHEMA)
    op.drop_column("portal_fee_sources", "status", schema=SCHEMA)
