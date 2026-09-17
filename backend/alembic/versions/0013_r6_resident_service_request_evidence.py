"""Attach resident evidence directly to a service request.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

SCHEMA = "greencity"
TABLE = "attachments"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("service_request_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.alter_column(TABLE, "work_order_id", existing_type=sa.Uuid(), nullable=True, schema=SCHEMA)
    op.create_foreign_key(
        "fk_attachments_service_request_id_service_requests", TABLE, "service_requests",
        ["service_request_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.create_check_constraint(op.f("ck_attachments_attachments_one_parent"), TABLE,
                               "num_nonnulls(work_order_id, service_request_id) = 1", schema=SCHEMA)
    op.create_index("ix_attachments_service_request_created", TABLE,
                    ["service_request_id", "created_at"], unique=False, schema=SCHEMA)


def downgrade() -> None:
    # A downgrade must not silently orphan private resident evidence.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM greencity.attachments WHERE service_request_id IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade resident evidence while service request attachments exist'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
    """)
    op.drop_index("ix_attachments_service_request_created", table_name=TABLE, schema=SCHEMA)
    op.drop_constraint(op.f("ck_attachments_attachments_one_parent"), TABLE, schema=SCHEMA, type_="check")
    op.drop_constraint("fk_attachments_service_request_id_service_requests", TABLE,
                       schema=SCHEMA, type_="foreignkey")
    op.alter_column(TABLE, "work_order_id", existing_type=sa.Uuid(), nullable=False, schema=SCHEMA)
    op.drop_column(TABLE, "service_request_id", schema=SCHEMA)
