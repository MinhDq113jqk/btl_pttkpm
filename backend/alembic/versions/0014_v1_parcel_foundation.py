"""Create the tenant-scoped parcel data foundation.

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

SCHEMA = "greencity"


def upgrade() -> None:
    op.create_table(
        "parcels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("building_id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_person_id", sa.Uuid(), nullable=True),
        sa.Column("parcel_code", sa.String(length=80), nullable=False),
        sa.Column("carrier_reference", sa.String(length=120), nullable=True),
        sa.Column("recipient_name_snapshot", sa.String(length=200), nullable=False),
        sa.Column("recipient_contact_snapshot", sa.String(length=200), nullable=True),
        sa.Column("storage_location", sa.String(length=120), nullable=True),
        sa.Column("pin_hash", sa.String(length=255), nullable=False),
        sa.Column("pin_attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pin_locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="RECEIVED", nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_for_pickup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handed_over_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handed_over_by_id", sa.Uuid(), nullable=True),
        sa.Column("exception_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], [f"{SCHEMA}.tenants.id"],
            name="fk_parcels_tenant_id_tenants", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["site_id", "tenant_id"], [f"{SCHEMA}.sites.id", f"{SCHEMA}.sites.tenant_id"],
            name="fk_parcels_site_tenant", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["building_id", "site_id"], [f"{SCHEMA}.buildings.id", f"{SCHEMA}.buildings.site_id"],
            name="fk_parcels_building_site", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id", "building_id"], [f"{SCHEMA}.units.id", f"{SCHEMA}.units.building_id"],
            name="fk_parcels_unit_building", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_person_id", "tenant_id"],
            [f"{SCHEMA}.persons.id", f"{SCHEMA}.persons.tenant_id"],
            name="fk_parcels_recipient_person_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id", "tenant_id"],
            [f"{SCHEMA}.accounts.id", f"{SCHEMA}.accounts.tenant_id"],
            name="fk_parcels_created_by_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id", "tenant_id"],
            [f"{SCHEMA}.accounts.id", f"{SCHEMA}.accounts.tenant_id"],
            name="fk_parcels_updated_by_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["handed_over_by_id", "tenant_id"],
            [f"{SCHEMA}.accounts.id", f"{SCHEMA}.accounts.tenant_id"],
            name="fk_parcels_handed_over_by_tenant", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("site_id", "parcel_code", name="uq_parcels_site_code"),
        sa.CheckConstraint("length(trim(parcel_code)) > 0", name="parcel_code_not_blank"),
        sa.CheckConstraint(
            "length(trim(recipient_name_snapshot)) > 0",
            name="recipient_name_snapshot_not_blank",
        ),
        sa.CheckConstraint("length(trim(pin_hash)) >= 32", name="pin_hash_min_length"),
        sa.CheckConstraint(
            "pin_attempt_count >= 0 AND pin_attempt_count <= 10",
            name="pin_attempts_range",
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
        sa.CheckConstraint(
            "status IN ('RECEIVED','READY_FOR_PICKUP','HANDED_OVER','RETURNED','LOST','DAMAGED')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "status NOT IN ('RETURNED','LOST','DAMAGED') OR "
            "(exception_reason IS NOT NULL AND length(trim(exception_reason)) > 0)",
            name="exception_reason_required",
        ),
        sa.CheckConstraint(
            "(status = 'HANDED_OVER' AND handed_over_at IS NOT NULL AND handed_over_by_id IS NOT NULL) OR "
            "(status <> 'HANDED_OVER' AND handed_over_at IS NULL AND handed_over_by_id IS NULL)",
            name="handover_fields_semantics",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_parcels"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_parcels_scope_status", "parcels",
        ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA,
    )
    op.create_index(
        "ix_parcels_unit_status_received", "parcels",
        ["unit_id", "status", "received_at"], schema=SCHEMA,
    )
    op.create_index(
        "ix_parcels_recipient_status", "parcels",
        ["recipient_person_id", "status"], schema=SCHEMA,
    )


def downgrade() -> None:
    # A downgrade must not silently discard the parcel history that later
    # workflows and audit evidence will reference.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM greencity.parcels) THEN
                RAISE EXCEPTION 'Cannot downgrade parcel foundation while parcel rows exist'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
        """
    )
    op.drop_index("ix_parcels_recipient_status", table_name="parcels", schema=SCHEMA)
    op.drop_index("ix_parcels_unit_status_received", table_name="parcels", schema=SCHEMA)
    op.drop_index("ix_parcels_scope_status", table_name="parcels", schema=SCHEMA)
    op.drop_table("parcels", schema=SCHEMA)
