"""Track revocable API sessions and require demo-account password rotation.

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

SCHEMA = "greencity"
DEMO_ACCOUNT_USERNAMES = (
    "admin_demo", "director_west", "cskh_west", "cskh_east", "accountant_west",
    "techlead_west", "technician_west", "cleaning_west", "security_west", "resident_west",
)


def upgrade() -> None:
    op.add_column("accounts", sa.Column(
        "session_version", sa.Integer(), server_default="1", nullable=False,
    ), schema=SCHEMA)
    op.add_column("accounts", sa.Column(
        "must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False,
    ), schema=SCHEMA)
    usernames = ", ".join(f"'{username}'" for username in DEMO_ACCOUNT_USERNAMES)
    op.execute(
        f"UPDATE {SCHEMA}.accounts SET must_change_password = TRUE "
        f"WHERE username IN ({usernames})"
    )
    op.create_check_constraint(
        "accounts_session_version_positive", "accounts", "session_version >= 1", schema=SCHEMA,
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("session_version >= 1", name="session_version_positive"),
        sa.CheckConstraint("expires_at > created_at", name="expires_after_creation"),
        sa.ForeignKeyConstraint(
            ["account_id"], [f"{SCHEMA}.accounts.id"], ondelete="CASCADE",
            name="fk_auth_sessions_account_id_accounts",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_auth_sessions_account_expires", "auth_sessions", ["account_id", "expires_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM {SCHEMA}.auth_sessions)
                OR EXISTS (SELECT 1 FROM {SCHEMA}.accounts WHERE must_change_password) THEN
                RAISE EXCEPTION 'Cannot downgrade while revocable sessions or forced password changes exist'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
        """
    )
    op.drop_index("ix_auth_sessions_account_expires", table_name="auth_sessions", schema=SCHEMA)
    op.drop_table("auth_sessions", schema=SCHEMA)
    op.drop_constraint(op.f("ck_accounts_accounts_session_version_positive"), "accounts", schema=SCHEMA, type_="check")
    op.drop_column("accounts", "must_change_password", schema=SCHEMA)
    op.drop_column("accounts", "session_version", schema=SCHEMA)
