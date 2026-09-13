"""Add the R2 service-request, work-order, maintenance and evidence slice.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SCHEMA = "greencity"


def identity_columns():
    return (
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def scope_columns(*, building_nullable=False):
    return (
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("building_id", sa.Uuid(), nullable=building_nullable),
    )


def scope_constraints(table_name):
    return (
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"],
                                name=f"fk_{table_name}_tenant_id_tenants", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "tenant_id"],
                                [f"{SCHEMA}.sites.id", f"{SCHEMA}.sites.tenant_id"],
                                name=f"fk_{table_name}_site_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["building_id", "site_id"],
                                [f"{SCHEMA}.buildings.id", f"{SCHEMA}.buildings.site_id"],
                                name=f"fk_{table_name}_building_site", ondelete="CASCADE"),
    )


def upgrade():
    op.create_unique_constraint("uq_sites_id_tenant_id", "sites", ["id", "tenant_id"], schema=SCHEMA)
    op.create_unique_constraint("uq_accounts_id_tenant_id", "accounts", ["id", "tenant_id"], schema=SCHEMA)
    op.create_unique_constraint("uq_units_id_building_id", "units", ["id", "building_id"], schema=SCHEMA)

    op.create_table(
        "service_categories",
        *identity_columns(),
        *scope_columns(building_nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sla_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("service_categories"),
        sa.CheckConstraint("sla_minutes > 0 AND sla_minutes <= 525600", name="ck_service_categories_service_categories_sla_range"),
        sa.PrimaryKeyConstraint("id", name="pk_service_categories"),
        sa.UniqueConstraint("site_id", "code", name="uq_service_categories_site_code"),
        schema=SCHEMA,
    )

    op.create_table(
        "service_requests",
        *identity_columns(),
        *scope_columns(),
        sa.Column("unit_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("linked_request_id", sa.Uuid(), nullable=True),
        sa.Column("link_type", sa.String(30), nullable=True),
        sa.Column("link_reason", sa.String(500), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(30), nullable=False, server_default="NEW"),
        sa.Column("sla_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("sla_breached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_account_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("csat_score", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("service_requests"),
        sa.ForeignKeyConstraint(["unit_id", "building_id"], [f"{SCHEMA}.units.id", f"{SCHEMA}.units.building_id"],
                                name="fk_service_requests_unit_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], [f"{SCHEMA}.service_categories.id"],
                                name="fk_service_requests_category_id_service_categories", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["linked_request_id"], [f"{SCHEMA}.service_requests.id"],
                                name="fk_service_requests_linked_request_id_service_requests", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_account_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_service_requests_owner_account_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_service_requests_created_by_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_service_requests_updated_by_id_accounts", ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('NEW','TRIAGED','IN_PROGRESS','WAITING_INFO','RESOLVED','CLOSED','CANCELLED')",
                           name="ck_service_requests_service_requests_status"),
        sa.CheckConstraint("priority IN ('LOW','MEDIUM','HIGH','URGENT')",
                           name="ck_service_requests_service_requests_priority"),
        sa.CheckConstraint("sla_duration_minutes > 0 AND sla_duration_minutes <= 525600",
                           name="ck_service_requests_service_requests_sla_range"),
        sa.CheckConstraint(
            "(linked_request_id IS NULL AND link_type IS NULL AND link_reason IS NULL) OR "
            "(linked_request_id IS NOT NULL AND link_type IN ('DUPLICATE','SPLIT','MERGED') "
            "AND length(trim(link_reason)) > 0)",
            name=op.f("ck_service_requests_link_consistency"),
        ),
        sa.CheckConstraint("csat_score IS NULL OR csat_score BETWEEN 1 AND 5",
                           name="ck_service_requests_csat_score"),
        sa.PrimaryKeyConstraint("id", name="pk_service_requests"),
        sa.UniqueConstraint("site_id", "code", name="uq_service_requests_site_code"),
        schema=SCHEMA,
    )

    op.create_table(
        "assets",
        *identity_columns(),
        *scope_columns(),
        sa.Column("unit_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("assets"),
        sa.ForeignKeyConstraint(["unit_id", "building_id"], [f"{SCHEMA}.units.id", f"{SCHEMA}.units.building_id"],
                                name="fk_assets_unit_building", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_assets_created_by_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_assets_updated_by_id_accounts", ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE','RETIRED')", name="ck_assets_assets_status"),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.UniqueConstraint("site_id", "code", name="uq_assets_site_code"),
        schema=SCHEMA,
    )

    op.create_table(
        "maintenance_plans",
        *identity_columns(),
        *scope_columns(),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checklist_template", sa.JSON(), nullable=False),
        sa.Column("evidence_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("maintenance_plans"),
        sa.ForeignKeyConstraint(["asset_id"], [f"{SCHEMA}.assets.id"],
                                name="fk_maintenance_plans_asset_id_assets", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_maintenance_plans_created_by_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_maintenance_plans_updated_by_id_accounts", ondelete="RESTRICT"),
        sa.CheckConstraint("interval_days > 0 AND interval_days <= 3650",
                           name="ck_maintenance_plans_maintenance_plans_interval_range"),
        sa.PrimaryKeyConstraint("id", name="pk_maintenance_plans"),
        sa.UniqueConstraint("asset_id", "code", name="uq_maintenance_plans_asset_code"),
        schema=SCHEMA,
    )

    op.create_table(
        "maintenance_occurrences",
        *identity_columns(),
        *scope_columns(),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DUE"),
        sa.Column("defer_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("defer_reason", sa.String(500), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("maintenance_occurrences"),
        sa.ForeignKeyConstraint(["plan_id"], [f"{SCHEMA}.maintenance_plans.id"],
                                name="fk_maintenance_occurrences_plan_id_maintenance_plans", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_maintenance_occurrences_created_by_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_maintenance_occurrences_updated_by_id_accounts", ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('DUE','WO_CREATED','IN_PROGRESS','COMPLETED','DEFERRED','CANCELLED')",
                           name="ck_maintenance_occurrences_maintenance_occurrences_status"),
        sa.PrimaryKeyConstraint("id", name="pk_maintenance_occurrences"),
        sa.UniqueConstraint("plan_id", "due_at", name="uq_maintenance_occurrences_plan_due"),
        schema=SCHEMA,
    )

    op.create_table(
        "work_orders",
        *identity_columns(),
        *scope_columns(),
        sa.Column("service_request_id", sa.Uuid(), nullable=True),
        sa.Column("maintenance_occurrence_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_by_id", sa.Uuid(), nullable=True),
        sa.Column("acceptance_mode", sa.String(30), nullable=True),
        sa.Column("acceptance_reason", sa.String(500), nullable=True),
        sa.Column("acceptance_evidence_id", sa.Uuid(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_reason", sa.String(500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("work_orders"),
        sa.ForeignKeyConstraint(["service_request_id"], [f"{SCHEMA}.service_requests.id"],
                                name="fk_work_orders_service_request_id_service_requests", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["maintenance_occurrence_id"], [f"{SCHEMA}.maintenance_occurrences.id"],
                                name="fk_work_orders_maintenance_occurrence", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_work_orders_assigned_to_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_work_orders_created_by_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_work_orders_updated_by_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_work_orders_accepted_by_id_accounts", ondelete="RESTRICT"),
        sa.CheckConstraint("(service_request_id IS NULL) <> (maintenance_occurrence_id IS NULL)",
                           name="ck_work_orders_work_orders_one_source"),
        sa.CheckConstraint("status IN ('DRAFT','ASSIGNED','IN_PROGRESS','ON_HOLD','WAITING_ACCEPTANCE','COMPLETED','CLOSED','CANCELLED')",
                           name="ck_work_orders_work_orders_status"),
        sa.PrimaryKeyConstraint("id", name="pk_work_orders"),
        sa.UniqueConstraint("site_id", "code", name="uq_work_orders_site_code"),
        sa.UniqueConstraint("maintenance_occurrence_id", name="uq_work_orders_maintenance_occurrence"),
        schema=SCHEMA,
    )

    op.create_table(
        "work_order_checklist_items",
        *identity_columns(),
        sa.Column("work_order_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result", sa.String(500), nullable=True),
        sa.Column("completed_by_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["work_order_id"], [f"{SCHEMA}.work_orders.id"],
                                name="fk_work_order_checklist_items_work_order_id_work_orders", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completed_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_work_order_checklist_items_completed_by_id_accounts", ondelete="SET NULL"),
        sa.CheckConstraint("position > 0", name="ck_work_order_checklist_items_work_order_checklist_position_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_work_order_checklist_items"),
        sa.UniqueConstraint("work_order_id", "position", name="uq_work_order_checklist_position"),
        schema=SCHEMA,
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        *scope_columns(building_nullable=True),
        sa.Column("actor_account_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("before_data", sa.JSON(), nullable=True),
        sa.Column("after_data", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *scope_constraints("audit_events"),
        sa.ForeignKeyConstraint(["actor_account_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_audit_events_actor_account_id_accounts", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        schema=SCHEMA,
    )

    op.create_table(
        "domain_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("actor_account_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"],
                                name="fk_domain_events_tenant_id_tenants", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "tenant_id"], [f"{SCHEMA}.sites.id", f"{SCHEMA}.sites.tenant_id"],
                                name="fk_domain_events_site_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_account_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_domain_events_actor_account_id_accounts", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_domain_events"),
        schema=SCHEMA,
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("actor_account_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"],
                                name="fk_idempotency_records_tenant_id_tenants", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "tenant_id"], [f"{SCHEMA}.sites.id", f"{SCHEMA}.sites.tenant_id"],
                                name="fk_idempotency_records_site_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_account_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_idempotency_records_actor_account_id_accounts", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_records"),
        sa.UniqueConstraint("tenant_id", "site_id", "actor_account_id", "operation", "idempotency_key",
                            name="uq_idempotency_scope_operation_key"),
        schema=SCHEMA,
    )

    op.create_table(
        "attachments",
        *identity_columns(),
        *scope_columns(),
        sa.Column("work_order_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("is_quarantined", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("attachments"),
        sa.ForeignKeyConstraint(["work_order_id"], [f"{SCHEMA}.work_orders.id"],
                                name="fk_attachments_work_order_id_work_orders", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_attachments_uploaded_by_id_accounts", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_attachments"),
        sa.UniqueConstraint("storage_key", name="uq_attachments_storage_key"),
        schema=SCHEMA,
    )

    op.create_table(
        "cost_lines",
        *identity_columns(),
        sa.Column("work_order_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("amount_vnd", sa.Integer(), nullable=False),
        sa.Column("cost_bearer", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="SUBMITTED"),
        sa.Column("evidence_attachment_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["work_order_id"], [f"{SCHEMA}.work_orders.id"],
                                name="fk_cost_lines_work_order_id_work_orders", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evidence_attachment_id"], [f"{SCHEMA}.attachments.id"],
                                name="fk_cost_lines_evidence_attachment_id_attachments", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_cost_lines_created_by_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_cost_lines_updated_by_id_accounts", ondelete="RESTRICT"),
        sa.CheckConstraint("amount_vnd > 0", name="ck_cost_lines_cost_lines_amount_positive"),
        sa.CheckConstraint("cost_bearer IN ('RESIDENT','MANAGEMENT')", name="ck_cost_lines_cost_lines_bearer"),
        sa.CheckConstraint("status IN ('DRAFT','SUBMITTED','CANCELLED')", name="ck_cost_lines_cost_lines_status"),
        sa.PrimaryKeyConstraint("id", name="pk_cost_lines"),
        schema=SCHEMA,
    )

    op.create_table(
        "pending_charges",
        *identity_columns(),
        sa.Column("cost_line_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="SUBMITTED"),
        sa.Column("submitted_by_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.String(500), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["cost_line_id"], [f"{SCHEMA}.cost_lines.id"],
                                name="fk_pending_charges_cost_line_id_cost_lines", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_pending_charges_submitted_by_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_pending_charges_reviewed_by_id_accounts", ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('SUBMITTED','APPROVED','REJECTED','CANCELLED','POSTED','REVERSED')",
                           name="ck_pending_charges_pending_charges_status"),
        sa.PrimaryKeyConstraint("id", name="pk_pending_charges"),
        sa.UniqueConstraint("cost_line_id", name="uq_pending_charges_cost_line"),
        schema=SCHEMA,
    )

    op.create_table(
        "invoice_items",
        *identity_columns(),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("pending_charge_id", sa.Uuid(), nullable=False),
        sa.Column("posting_reference", sa.String(100), nullable=False),
        sa.Column("amount_vnd", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"],
                                name="fk_invoice_items_tenant_id_tenants", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], [f"{SCHEMA}.sites.id"],
                                name="fk_invoice_items_site_id_sites", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pending_charge_id"], [f"{SCHEMA}.pending_charges.id"],
                                name="fk_invoice_items_pending_charge_id_pending_charges", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_invoice_items_created_by_id_accounts", ondelete="RESTRICT"),
        sa.CheckConstraint("amount_vnd > 0", name="ck_invoice_items_invoice_items_amount_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_items"),
        sa.UniqueConstraint("pending_charge_id", name="uq_invoice_items_pending_charge"),
        sa.UniqueConstraint("site_id", "posting_reference", name="uq_invoice_items_site_reference"),
        schema=SCHEMA,
    )

    op.create_table(
        "cases",
        *identity_columns(),
        *scope_columns(),
        sa.Column("source_work_order_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("cases"),
        sa.ForeignKeyConstraint(["source_work_order_id"], [f"{SCHEMA}.work_orders.id"],
                                name="fk_cases_source_work_order_id_work_orders", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_cases_created_by_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_cases_updated_by_id_accounts", ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('NEW','TRIAGED','IN_PROGRESS','RESOLVED','CLOSED')",
                           name="ck_cases_cases_status"),
        sa.PrimaryKeyConstraint("id", name="pk_cases"),
        schema=SCHEMA,
    )

    op.create_table(
        "charge_reversals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pending_charge_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pending_charge_id"], [f"{SCHEMA}.pending_charges.id"],
                                name="fk_charge_reversals_pending_charge_id_pending_charges", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["case_id"], [f"{SCHEMA}.cases.id"],
                                name="fk_charge_reversals_case_id_cases", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_charge_reversals_created_by_id_accounts", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_charge_reversals"),
        sa.UniqueConstraint("pending_charge_id", name="uq_charge_reversals_pending_charge"),
        schema=SCHEMA,
    )

    op.create_table(
        "maintenance_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("occurrence_id", sa.Uuid(), nullable=False),
        sa.Column("work_order_id", sa.Uuid(), nullable=False),
        sa.Column("performed_by_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_by_id", sa.Uuid(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"],
                                name="fk_maintenance_history_tenant_id_tenants", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], [f"{SCHEMA}.sites.id"],
                                name="fk_maintenance_history_site_id_sites", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], [f"{SCHEMA}.assets.id"],
                                name="fk_maintenance_history_asset_id_assets", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["occurrence_id"], [f"{SCHEMA}.maintenance_occurrences.id"],
                                name="fk_maintenance_history_occurrence_id_maintenance_occurrences", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["work_order_id"], [f"{SCHEMA}.work_orders.id"],
                                name="fk_maintenance_history_work_order_id_work_orders", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["performed_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_maintenance_history_performed_by_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_by_id"], [f"{SCHEMA}.accounts.id"],
                                name="fk_maintenance_history_accepted_by_id_accounts", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_maintenance_history"),
        sa.UniqueConstraint("occurrence_id", name="uq_maintenance_history_occurrence"),
        schema=SCHEMA,
    )

    indexes = {
        "service_categories": [("scope", ["tenant_id", "site_id"])],
        "service_requests": [("scope_status", ["tenant_id", "site_id", "status"]),
                             ("category_id", ["category_id"]), ("linked_request_id", ["linked_request_id"]),
                             ("owner_account_id", ["owner_account_id"]), ("unit_id", ["unit_id"])],
        "assets": [("scope_status", ["tenant_id", "site_id", "status"]), ("unit_id", ["unit_id"])],
        "maintenance_plans": [("asset_id", ["asset_id"]),
                              ("due", ["site_id", "is_active", "next_due_at"])],
        "maintenance_occurrences": [("plan_id", ["plan_id"]),
                                    ("scope_status", ["tenant_id", "site_id", "status"])],
        "work_orders": [("service_request_id", ["service_request_id"]),
                        ("assignee_status", ["assigned_to_id", "status"]),
                        ("scope_status", ["tenant_id", "site_id", "status"])],
        "work_order_checklist_items": [("completed_by_id", ["completed_by_id"])],
        "audit_events": [("scope_created", ["tenant_id", "site_id", "created_at"]),
                         ("actor_account_id", ["actor_account_id"]),
                         ("resource", ["resource_type", "resource_id"])],
        "domain_events": [("unpublished", ["published_at", "created_at"]),
                          ("actor_account_id", ["actor_account_id"])],
        "idempotency_records": [],
        "attachments": [("work_order_created", ["work_order_id", "created_at"]),
                        ("uploaded_by_id", ["uploaded_by_id"])],
        "cost_lines": [("work_order", ["work_order_id"]),
                       ("evidence_attachment_id", ["evidence_attachment_id"])],
        "pending_charges": [("submitted_by_id", ["submitted_by_id"]),
                            ("reviewed_by_id", ["reviewed_by_id"])],
        "invoice_items": [("created_by_id", ["created_by_id"])],
        "cases": [("source_work_order", ["source_work_order_id"])],
        "charge_reversals": [("case_id", ["case_id"])],
        "maintenance_history": [("asset_completed", ["asset_id", "completed_at"]),
                                ("work_order_id", ["work_order_id"])],
    }
    for table, definitions in indexes.items():
        for suffix, columns in definitions:
            op.create_index(f"ix_{table}_{suffix}", table, columns, schema=SCHEMA)

    op.create_index("ix_idempotency_resource", "idempotency_records",
                    ["resource_type", "resource_id"], schema=SCHEMA)
    op.create_index("ix_work_order_checklist_work_order", "work_order_checklist_items",
                    ["work_order_id"], schema=SCHEMA)

    op.execute("""
        CREATE FUNCTION greencity.reject_audit_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events are append-only';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_audit_events_append_only
        BEFORE UPDATE OR DELETE ON greencity.audit_events
        FOR EACH ROW EXECUTE FUNCTION greencity.reject_audit_mutation()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_append_only ON greencity.audit_events")
    op.execute("DROP FUNCTION IF EXISTS greencity.reject_audit_mutation()")
    for table in (
        "maintenance_history", "charge_reversals", "cases", "invoice_items",
        "pending_charges", "cost_lines", "attachments", "idempotency_records",
        "domain_events", "audit_events", "work_order_checklist_items", "work_orders",
        "maintenance_occurrences", "maintenance_plans", "assets", "service_requests",
        "service_categories",
    ):
        op.drop_table(table, schema=SCHEMA)
    op.drop_constraint("uq_units_id_building_id", "units", schema=SCHEMA, type_="unique")
    op.drop_constraint("uq_accounts_id_tenant_id", "accounts", schema=SCHEMA, type_="unique")
    op.drop_constraint("uq_sites_id_tenant_id", "sites", schema=SCHEMA, type_="unique")
