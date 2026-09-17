"""Link parcels to the shared Case/Incident and private evidence abstractions.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

SCHEMA = "greencity"


def upgrade() -> None:
    # A Case can now originate either from an existing Work Order or directly
    # from a parcel exception. Existing R2/R3 rows continue to satisfy the
    # one-source invariant because source_work_order_id remains populated.
    op.add_column("cases", sa.Column("source_parcel_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.alter_column("cases", "source_work_order_id", existing_type=sa.Uuid(), nullable=True, schema=SCHEMA)
    op.create_foreign_key(
        "fk_cases_source_parcel_id_parcels", "cases", "parcels",
        ["source_parcel_id"], ["id"], source_schema=SCHEMA,
        referent_schema=SCHEMA, ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_cases_cases_one_source"), "cases",
        "num_nonnulls(source_work_order_id, source_parcel_id) = 1", schema=SCHEMA,
    )
    op.create_index("ix_cases_source_parcel", "cases", ["source_parcel_id"], schema=SCHEMA)
    op.create_unique_constraint("uq_cases_source_parcel_id", "cases", ["source_parcel_id"], schema=SCHEMA)

    op.add_column("security_incidents", sa.Column("parcel_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.create_foreign_key(
        "fk_security_incidents_parcel_id_parcels", "security_incidents", "parcels",
        ["parcel_id"], ["id"], source_schema=SCHEMA,
        referent_schema=SCHEMA, ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_security_incidents_parcel_id", "security_incidents", ["parcel_id"], schema=SCHEMA,
    )
    op.create_index("ix_security_incidents_parcel", "security_incidents", ["parcel_id"], schema=SCHEMA)

    # Attachment is a shared private-evidence record. Extend its parent union
    # without weakening the exactly-one-parent database invariant.
    op.add_column("attachments", sa.Column("parcel_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.drop_constraint(op.f("ck_attachments_attachments_one_parent"), "attachments",
                       schema=SCHEMA, type_="check")
    op.create_foreign_key(
        "fk_attachments_parcel_id_parcels", "attachments", "parcels",
        ["parcel_id"], ["id"], source_schema=SCHEMA,
        referent_schema=SCHEMA, ondelete="CASCADE",
    )
    op.create_check_constraint(
        op.f("ck_attachments_attachments_one_parent"), "attachments",
        "num_nonnulls(work_order_id, service_request_id, parcel_id) = 1", schema=SCHEMA,
    )
    op.create_index("ix_attachments_parcel_created", "attachments",
                    ["parcel_id", "created_at"], schema=SCHEMA)


def downgrade() -> None:
    # Do not silently orphan parcel cases, incidents, or private evidence.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM greencity.cases WHERE source_parcel_id IS NOT NULL)
                OR EXISTS (SELECT 1 FROM greencity.security_incidents WHERE parcel_id IS NOT NULL)
                OR EXISTS (SELECT 1 FROM greencity.attachments WHERE parcel_id IS NOT NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade parcel case/evidence while linked rows exist'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
        """
    )

    op.drop_index("ix_attachments_parcel_created", table_name="attachments", schema=SCHEMA)
    op.drop_constraint(op.f("ck_attachments_attachments_one_parent"), "attachments",
                       schema=SCHEMA, type_="check")
    op.drop_constraint("fk_attachments_parcel_id_parcels", "attachments",
                       schema=SCHEMA, type_="foreignkey")
    op.create_check_constraint(
        op.f("ck_attachments_attachments_one_parent"), "attachments",
        "num_nonnulls(work_order_id, service_request_id) = 1", schema=SCHEMA,
    )
    op.drop_column("attachments", "parcel_id", schema=SCHEMA)

    op.drop_index("ix_security_incidents_parcel", table_name="security_incidents", schema=SCHEMA)
    op.drop_constraint("uq_security_incidents_parcel_id", "security_incidents",
                       schema=SCHEMA, type_="unique")
    op.drop_constraint("fk_security_incidents_parcel_id_parcels", "security_incidents",
                       schema=SCHEMA, type_="foreignkey")
    op.drop_column("security_incidents", "parcel_id", schema=SCHEMA)

    op.drop_constraint("uq_cases_source_parcel_id", "cases", schema=SCHEMA, type_="unique")
    op.drop_index("ix_cases_source_parcel", table_name="cases", schema=SCHEMA)
    op.drop_constraint(op.f("ck_cases_cases_one_source"), "cases", schema=SCHEMA, type_="check")
    op.drop_constraint("fk_cases_source_parcel_id_parcels", "cases",
                       schema=SCHEMA, type_="foreignkey")
    op.drop_column("cases", "source_parcel_id", schema=SCHEMA)
    op.alter_column("cases", "source_work_order_id", existing_type=sa.Uuid(), nullable=False, schema=SCHEMA)
