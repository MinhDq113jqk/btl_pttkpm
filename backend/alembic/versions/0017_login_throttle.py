"""Persist opaque login-attempt cooldown state across application workers.

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

SCHEMA = "greencity"


def upgrade() -> None:
    op.create_table(
        "login_throttles",
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("failure_count >= 1", name="failure_count_positive"),
        sa.PrimaryKeyConstraint("identity_key", name=op.f("pk_login_throttles")),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_login_throttles_updated_at", "login_throttles", ["updated_at"], schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM {SCHEMA}.login_throttles) THEN
                RAISE EXCEPTION 'Cannot downgrade while login cooldown state exists'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
        """
    )
    op.drop_index("ix_login_throttles_updated_at", table_name="login_throttles", schema=SCHEMA)
    op.drop_table("login_throttles", schema=SCHEMA)
