"""Add durable R5 outbox delivery state and notification read models.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

SCHEMA = "greencity"
DELIVERY_STATES = "'PENDING','PROCESSING','RETRY_SCHEDULED','PUBLISHED','DEAD_LETTER'"


def upgrade():
    op.add_column(
        "domain_events",
        sa.Column("delivery_status", sa.String(24), nullable=False, server_default="PENDING"),
        schema=SCHEMA,
    )
    op.add_column("domain_events", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"), schema=SCHEMA)
    op.add_column(
        "domain_events",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("timezone('UTC', now())")),
        schema=SCHEMA,
    )
    op.add_column("domain_events", sa.Column("last_error", sa.String(80), nullable=True), schema=SCHEMA)
    op.add_column("domain_events", sa.Column("delivery_lock_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.add_column("domain_events", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.create_check_constraint(
        "domain_events_delivery_status",
        "domain_events",
        f"delivery_status IN ({DELIVERY_STATES})",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_domain_events_dispatch_due",
        "domain_events",
        ["delivery_status", "next_attempt_at", "created_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "notification_read_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_account_id", sa.Uuid(), nullable=False),
        sa.Column("domain_event_id", sa.Uuid(), nullable=False),
        sa.Column("template_code", sa.String(80), nullable=False),
        sa.Column("template_snapshot", sa.JSON(), nullable=False),
        sa.Column("delivery_status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('UTC', now())")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('UTC', now())")),
        sa.CheckConstraint(f"delivery_status IN ({DELIVERY_STATES})", name="notification_read_models_delivery_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["greencity.tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_account_id"], ["greencity.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["domain_event_id"], ["greencity.domain_events.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id", "tenant_id"], ["greencity.sites.id", "greencity.sites.tenant_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_notification_read_models"),
        sa.UniqueConstraint("domain_event_id", name="uq_notification_read_models_domain_event"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_notification_read_models_recipient",
        "notification_read_models",
        ["recipient_account_id", "site_id", "read_at", "created_at"],
        schema=SCHEMA,
    )


def downgrade():
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM greencity.notification_read_models) THEN
                RAISE EXCEPTION 'Cannot downgrade R5 while notification read models exist';
            END IF;
            IF EXISTS (
                SELECT 1 FROM greencity.domain_events
                WHERE delivery_status <> 'PENDING' OR attempt_count <> 0
                   OR last_error IS NOT NULL OR delivery_lock_id IS NOT NULL OR locked_until IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade R5 while domain event delivery state exists';
            END IF;
        END;
        $$
    """)
    op.drop_index("ix_notification_read_models_recipient", table_name="notification_read_models", schema=SCHEMA)
    op.drop_table("notification_read_models", schema=SCHEMA)
    op.drop_index("ix_domain_events_dispatch_due", table_name="domain_events", schema=SCHEMA)
    op.drop_constraint("domain_events_delivery_status", "domain_events", type_="check", schema=SCHEMA)
    for column in ("locked_until", "delivery_lock_id", "last_error", "next_attempt_at", "attempt_count", "delivery_status"):
        op.drop_column("domain_events", column, schema=SCHEMA)
