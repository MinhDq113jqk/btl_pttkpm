"""Link resident accounts to Persons without trusting client identity claims.

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

SCHEMA = "greencity"
TABLE = "accounts"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("person_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    # A Person may back one resident login per tenant.  PostgreSQL allows the
    # existing staff accounts with NULL person_id to remain independent.
    op.create_unique_constraint("uq_accounts_tenant_id_person_id", TABLE,
                                ["tenant_id", "person_id"], schema=SCHEMA)
    op.create_index(op.f("ix_greencity_accounts_person_id"), TABLE, ["person_id"],
                    unique=False, schema=SCHEMA)
    op.create_foreign_key(
        "fk_accounts_person_tenant", TABLE, "persons",
        ["person_id", "tenant_id"], ["id", "tenant_id"],
        source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="RESTRICT",
    )


def downgrade() -> None:
    # Dropping an identity link would silently widen or sever a resident's
    # scope.  A release must explicitly unlink every account before downgrade.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM greencity.accounts WHERE person_id IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade resident identity while account links exist'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
    """)
    op.drop_constraint("fk_accounts_person_tenant", TABLE, schema=SCHEMA, type_="foreignkey")
    op.drop_index(op.f("ix_greencity_accounts_person_id"), table_name=TABLE, schema=SCHEMA)
    op.drop_constraint("uq_accounts_tenant_id_person_id", TABLE, schema=SCHEMA, type_="unique")
    op.drop_column(TABLE, "person_id", schema=SCHEMA)
