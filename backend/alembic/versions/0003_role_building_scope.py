"""Add explicit per-role building scope without granting access to legacy rows.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_buildings_id_site_id", "buildings", ["id", "site_id"], schema="greencity")
    op.add_column("account_roles", sa.Column("building_id", sa.Uuid(), nullable=True), schema="greencity")
    op.create_index("ix_account_roles_building_id", "account_roles", ["building_id"], schema="greencity")
    op.create_check_constraint(op.f("ck_account_roles_building_requires_site"), "account_roles",
                               "building_id IS NULL OR site_id IS NOT NULL", schema="greencity")
    op.create_foreign_key("fk_account_roles_building_site", "account_roles", "buildings",
                          ["building_id", "site_id"], ["id", "site_id"],
                          source_schema="greencity", referent_schema="greencity", ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("fk_account_roles_building_site", "account_roles", schema="greencity", type_="foreignkey")
    op.drop_constraint(op.f("ck_account_roles_building_requires_site"), "account_roles", schema="greencity", type_="check")
    op.drop_index("ix_account_roles_building_id", table_name="account_roles", schema="greencity")
    op.drop_column("account_roles", "building_id", schema="greencity")
    op.drop_constraint("uq_buildings_id_site_id", "buildings", schema="greencity", type_="unique")
