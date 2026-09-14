"""Add scoped cleaning and security operations foundations for R3.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SCHEMA = "greencity"


def identity_columns():
    return (
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def scope_columns():
    return (
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("building_id", sa.Uuid(), nullable=False),
    )


def scope_constraints(table_name):
    return (
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"],
                                name=f"fk_{table_name}_tenant_id_tenants", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "tenant_id"], [f"{SCHEMA}.sites.id", f"{SCHEMA}.sites.tenant_id"],
                                name=f"fk_{table_name}_site_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["building_id", "site_id"], [f"{SCHEMA}.buildings.id", f"{SCHEMA}.buildings.site_id"],
                                name=f"fk_{table_name}_building_site", ondelete="CASCADE"),
    )


def upgrade():
    op.create_table(
        "cleaning_routes",
        *identity_columns(), *scope_columns(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("cleaning_routes"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_cleaning_routes"),
        sa.UniqueConstraint("site_id", "code", name="uq_cleaning_routes_site_code"),
        schema=SCHEMA,
    )
    op.create_index("ix_cleaning_routes_scope_active", "cleaning_routes", ["tenant_id", "site_id", "is_active"], schema=SCHEMA)

    op.create_table(
        "cleaning_areas",
        *identity_columns(), *scope_columns(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("cleaning_areas"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_cleaning_areas"),
        sa.UniqueConstraint("site_id", "code", name="uq_cleaning_areas_site_code"),
        schema=SCHEMA,
    )
    op.create_index("ix_cleaning_areas_scope_active", "cleaning_areas", ["tenant_id", "site_id", "is_active"], schema=SCHEMA)

    op.create_table(
        "cleaning_route_stops",
        *identity_columns(), *scope_columns(),
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("cleaning_area_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("checklist_template", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("cleaning_route_stops"),
        sa.ForeignKeyConstraint(["route_id"], [f"{SCHEMA}.cleaning_routes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cleaning_area_id"], [f"{SCHEMA}.cleaning_areas.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("position > 0", name="cleaning_route_stops_position_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_cleaning_route_stops"),
        sa.UniqueConstraint("route_id", "cleaning_area_id", name="uq_cleaning_route_stops_route_area"),
        sa.UniqueConstraint("route_id", "position", name="uq_cleaning_route_stops_route_position"),
        schema=SCHEMA,
    )
    op.create_index("ix_cleaning_route_stops_route", "cleaning_route_stops", ["route_id", "position"], schema=SCHEMA)

    op.create_table(
        "cleaning_shifts",
        *identity_columns(), *scope_columns(),
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNED"),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("cleaning_shifts"),
        sa.ForeignKeyConstraint(["route_id"], [f"{SCHEMA}.cleaning_routes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("scheduled_end_at > scheduled_start_at", name="cleaning_shifts_window_valid"),
        sa.CheckConstraint("status IN ('PLANNED','IN_PROGRESS','COMPLETED','CANCELLED')", name="cleaning_shifts_status"),
        sa.PrimaryKeyConstraint("id", name="pk_cleaning_shifts"),
        sa.UniqueConstraint("route_id", "scheduled_start_at", name="uq_cleaning_shifts_route_start"),
        schema=SCHEMA,
    )
    op.create_index("ix_cleaning_shifts_scope_start", "cleaning_shifts", ["tenant_id", "site_id", "building_id", "scheduled_start_at"], schema=SCHEMA)

    op.create_table(
        "cleaning_tasks",
        *identity_columns(), *scope_columns(),
        sa.Column("shift_id", sa.Uuid(), nullable=False),
        sa.Column("route_stop_id", sa.Uuid(), nullable=False),
        sa.Column("rework_of_task_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNED"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("cleaning_tasks"),
        sa.ForeignKeyConstraint(["shift_id"], [f"{SCHEMA}.cleaning_shifts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["route_stop_id"], [f"{SCHEMA}.cleaning_route_stops.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rework_of_task_id"], [f"{SCHEMA}.cleaning_tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_to_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('PLANNED','ASSIGNED','IN_PROGRESS','SUBMITTED','ACCEPTED','MISSED','REWORK_REQUIRED','CANCELLED')",
            name="cleaning_tasks_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cleaning_tasks"),
        sa.UniqueConstraint("shift_id", "route_stop_id", name="uq_cleaning_tasks_shift_stop"),
        sa.UniqueConstraint("rework_of_task_id", name="uq_cleaning_tasks_rework_source"),
        schema=SCHEMA,
    )
    op.create_index("ix_cleaning_tasks_scope_status", "cleaning_tasks", ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA)
    op.create_index("ix_cleaning_tasks_assignee_status", "cleaning_tasks", ["assigned_to_id", "status"], schema=SCHEMA)

    op.create_table(
        "cleaning_checklist_results",
        *identity_columns(),
        sa.Column("cleaning_task_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("result", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("performed_by_id", sa.Uuid(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["cleaning_task_id"], [f"{SCHEMA}.cleaning_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["performed_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("position > 0", name="cleaning_checklist_results_position_positive"),
        sa.CheckConstraint("result IN ('PENDING','PASS','FAIL','NOT_APPLICABLE')", name="cleaning_checklist_results_result"),
        sa.PrimaryKeyConstraint("id", name="pk_cleaning_checklist_results"),
        sa.UniqueConstraint("cleaning_task_id", "position", name="uq_cleaning_checklist_results_task_position"),
        schema=SCHEMA,
    )
    op.create_index("ix_cleaning_checklist_results_task", "cleaning_checklist_results", ["cleaning_task_id", "position"], schema=SCHEMA)

    op.create_table(
        "security_shifts",
        *identity_columns(), *scope_columns(),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNED"),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("security_shifts"),
        sa.ForeignKeyConstraint(["assigned_to_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("scheduled_end_at > scheduled_start_at", name="security_shifts_window_valid"),
        sa.CheckConstraint("status IN ('PLANNED','IN_PROGRESS','COMPLETED','CANCELLED')", name="security_shifts_status"),
        sa.PrimaryKeyConstraint("id", name="pk_security_shifts"),
        sa.UniqueConstraint("building_id", "scheduled_start_at", name="uq_security_shifts_building_start"),
        schema=SCHEMA,
    )
    op.create_index("ix_security_shifts_scope_start", "security_shifts", ["tenant_id", "site_id", "building_id", "scheduled_start_at"], schema=SCHEMA)

    op.create_table(
        "security_shift_handoffs",
        *identity_columns(), *scope_columns(),
        sa.Column("security_shift_id", sa.Uuid(), nullable=False),
        sa.Column("handed_over_by_id", sa.Uuid(), nullable=False),
        sa.Column("received_by_id", sa.Uuid(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        *scope_constraints("security_shift_handoffs"),
        sa.ForeignKeyConstraint(["security_shift_id"], [f"{SCHEMA}.security_shifts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["handed_over_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["received_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_security_shift_handoffs"),
        schema=SCHEMA,
    )
    op.create_index("ix_security_shift_handoffs_shift", "security_shift_handoffs", ["security_shift_id", "created_at"], schema=SCHEMA)

    op.create_table(
        "security_visitor_logs",
        *identity_columns(), *scope_columns(),
        sa.Column("security_shift_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_by_id", sa.Uuid(), nullable=False),
        sa.Column("visitor_name", sa.String(200), nullable=False),
        sa.Column("visit_purpose", sa.String(500), nullable=False),
        sa.Column("document_reference", sa.String(100), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=False),
        *scope_constraints("security_visitor_logs"),
        sa.ForeignKeyConstraint(["security_shift_id"], [f"{SCHEMA}.security_shifts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_security_visitor_logs"),
        schema=SCHEMA,
    )
    op.create_index("ix_security_visitor_logs_shift_created", "security_visitor_logs", ["security_shift_id", "created_at"], schema=SCHEMA)

    op.create_table(
        "patrol_points",
        *identity_columns(), *scope_columns(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("patrol_points"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_patrol_points"),
        sa.UniqueConstraint("site_id", "code", name="uq_patrol_points_site_code"),
        schema=SCHEMA,
    )
    op.create_index("ix_patrol_points_scope_active", "patrol_points", ["tenant_id", "site_id", "is_active"], schema=SCHEMA)

    op.create_table(
        "patrol_windows",
        *identity_columns(), *scope_columns(),
        sa.Column("security_shift_id", sa.Uuid(), nullable=False),
        sa.Column("patrol_point_id", sa.Uuid(), nullable=False),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="SCHEDULED"),
        sa.Column("missed_reason", sa.String(500), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("patrol_windows"),
        sa.ForeignKeyConstraint(["security_shift_id"], [f"{SCHEMA}.security_shifts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patrol_point_id"], [f"{SCHEMA}.patrol_points.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("window_end_at > window_start_at", name="patrol_windows_window_valid"),
        sa.CheckConstraint("status IN ('SCHEDULED','COMPLETED','MISSED','CANCELLED')", name="patrol_windows_status"),
        sa.CheckConstraint("status <> 'MISSED' OR length(trim(missed_reason)) > 0", name="patrol_windows_missed_reason"),
        sa.PrimaryKeyConstraint("id", name="pk_patrol_windows"),
        sa.UniqueConstraint("security_shift_id", "patrol_point_id", "window_start_at", name="uq_patrol_windows_shift_point_start"),
        schema=SCHEMA,
    )
    op.create_index("ix_patrol_windows_scope_status", "patrol_windows", ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA)
    op.create_index("ix_patrol_windows_due", "patrol_windows", ["security_shift_id", "window_end_at", "status"], schema=SCHEMA)

    op.create_table(
        "patrol_logs",
        *identity_columns(),
        sa.Column("patrol_window_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_by_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patrol_window_id"], [f"{SCHEMA}.patrol_windows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("event_type IN ('CHECK_IN','CHECK_OUT','NOTE')", name="patrol_logs_event_type"),
        sa.PrimaryKeyConstraint("id", name="pk_patrol_logs"),
        schema=SCHEMA,
    )
    op.create_index("ix_patrol_logs_window_created", "patrol_logs", ["patrol_window_id", "created_at"], schema=SCHEMA)

    op.create_table(
        "security_incidents",
        *identity_columns(), *scope_columns(),
        sa.Column("patrol_window_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("incident_type", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reported_by_id", sa.Uuid(), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *scope_constraints("security_incidents"),
        sa.ForeignKeyConstraint(["patrol_window_id"], [f"{SCHEMA}.patrol_windows.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reported_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("incident_type IN ('SECURITY','FIRE')", name="security_incidents_type"),
        sa.CheckConstraint("severity IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="security_incidents_severity"),
        sa.CheckConstraint("status IN ('NEW','TRIAGED','IN_PROGRESS','RESOLVED','CLOSED')", name="security_incidents_status"),
        sa.PrimaryKeyConstraint("id", name="pk_security_incidents"),
        sa.UniqueConstraint("site_id", "code", name="uq_security_incidents_site_code"),
        schema=SCHEMA,
    )
    op.create_index("ix_security_incidents_scope_status", "security_incidents", ["tenant_id", "site_id", "building_id", "status"], schema=SCHEMA)
    op.create_index("ix_security_incidents_scope_severity", "security_incidents", ["tenant_id", "site_id", "severity"], schema=SCHEMA)

    op.create_table(
        "incident_escalations",
        *identity_columns(),
        sa.Column("security_incident_id", sa.Uuid(), nullable=False),
        sa.Column("target_role", sa.String(20), nullable=False),
        sa.Column("escalated_by_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.ForeignKeyConstraint(["security_incident_id"], [f"{SCHEMA}.security_incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["escalated_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("target_role IN ('security','director')", name="incident_escalations_target_role"),
        sa.PrimaryKeyConstraint("id", name="pk_incident_escalations"),
        sa.UniqueConstraint("security_incident_id", "target_role", name="uq_incident_escalations_incident_role"),
        schema=SCHEMA,
    )
    op.create_index("ix_incident_escalations_incident", "incident_escalations", ["security_incident_id", "created_at"], schema=SCHEMA)

    op.create_table(
        "incident_escalation_acknowledgements",
        *identity_columns(),
        sa.Column("incident_escalation_id", sa.Uuid(), nullable=False),
        sa.Column("acknowledged_by_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["incident_escalation_id"], [f"{SCHEMA}.incident_escalations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["acknowledged_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_incident_escalation_acknowledgements"),
        sa.UniqueConstraint("incident_escalation_id", name="uq_incident_escalation_acknowledgements_escalation"),
        schema=SCHEMA,
    )
    op.create_index("ix_incident_escalation_acknowledgements_escalation", "incident_escalation_acknowledgements", ["incident_escalation_id", "created_at"], schema=SCHEMA)

    op.create_table(
        "security_incident_evidence",
        *identity_columns(),
        sa.Column("security_incident_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_by_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("storage_reference", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["security_incident_id"], [f"{SCHEMA}.security_incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], [f"{SCHEMA}.accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("evidence_type IN ('NOTE','IMAGE','REPORT')", name="security_incident_evidence_type"),
        sa.CheckConstraint("length(trim(description)) > 0", name="security_incident_evidence_description"),
        sa.PrimaryKeyConstraint("id", name="pk_security_incident_evidence"),
        schema=SCHEMA,
    )
    op.create_index("ix_security_incident_evidence_incident", "security_incident_evidence", ["security_incident_id", "created_at"], schema=SCHEMA)

    op.add_column("work_orders", sa.Column("cleaning_task_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.drop_constraint(op.f("ck_work_orders_ck_work_orders_work_orders_one_source"), "work_orders", schema=SCHEMA, type_="check")
    op.create_foreign_key("fk_work_orders_cleaning_task_id_cleaning_tasks", "work_orders", "cleaning_tasks", ["cleaning_task_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="RESTRICT")
    op.create_unique_constraint("uq_work_orders_cleaning_task", "work_orders", ["cleaning_task_id"], schema=SCHEMA)
    op.create_check_constraint("work_orders_one_source", "work_orders", "num_nonnulls(service_request_id, maintenance_occurrence_id, cleaning_task_id) = 1", schema=SCHEMA)

    op.execute("""
        CREATE FUNCTION greencity.reject_r3_timeline_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
        END;
        $$
    """)
    for table in (
        "security_shift_handoffs",
        "security_visitor_logs",
        "patrol_logs",
        "incident_escalations",
        "incident_escalation_acknowledgements",
        "security_incident_evidence",
    ):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_append_only
            BEFORE UPDATE OR DELETE ON {SCHEMA}.{table}
            FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.reject_r3_timeline_mutation()
        """)


def downgrade():
    for table in (
        "security_shift_handoffs",
        "security_visitor_logs",
        "patrol_logs",
        "incident_escalations",
        "incident_escalation_acknowledgements",
        "security_incident_evidence",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {SCHEMA}.{table}")
    op.execute("DROP FUNCTION IF EXISTS greencity.reject_r3_timeline_mutation()")

    op.drop_constraint(op.f("ck_work_orders_work_orders_one_source"), "work_orders", schema=SCHEMA, type_="check")
    op.drop_constraint(op.f("uq_work_orders_cleaning_task"), "work_orders", schema=SCHEMA, type_="unique")
    op.drop_constraint(op.f("fk_work_orders_cleaning_task_id_cleaning_tasks"), "work_orders", schema=SCHEMA, type_="foreignkey")
    op.drop_column("work_orders", "cleaning_task_id", schema=SCHEMA)
    op.create_check_constraint(
        op.f("ck_work_orders_ck_work_orders_work_orders_one_source"),
        "work_orders",
        "(service_request_id IS NULL) <> (maintenance_occurrence_id IS NULL)",
        schema=SCHEMA,
    )

    for table in (
        "security_incident_evidence",
        "incident_escalation_acknowledgements",
        "incident_escalations",
        "security_incidents",
        "patrol_logs",
        "patrol_windows",
        "patrol_points",
        "security_visitor_logs",
        "security_shift_handoffs",
        "security_shifts",
        "cleaning_checklist_results",
        "cleaning_tasks",
        "cleaning_shifts",
        "cleaning_route_stops",
        "cleaning_areas",
        "cleaning_routes",
    ):
        op.drop_table(table, schema=SCHEMA)
