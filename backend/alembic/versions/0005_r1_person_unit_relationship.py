"""Add AC-03 ratio and half-open validity to Person--Unit relationships.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SCHEMA = "greencity"
TABLE = "unit_person_relationships"


def upgrade():
    op.add_column(TABLE, sa.Column("ownership_ratio", sa.Numeric(5, 4), nullable=True), schema=SCHEMA)
    op.add_column(
        TABLE,
        sa.Column("valid_from", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(TABLE, sa.Column("valid_to", sa.Date(), nullable=True), schema=SCHEMA)
    # Persist the server-derived scope on each relationship.  The composite
    # foreign keys added below make a later parent re-parenting update fail
    # atomically instead of relying only on a trigger's visibility snapshot.
    op.add_column(TABLE, sa.Column("tenant_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("site_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("building_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.execute("""
        UPDATE greencity.unit_person_relationships
        SET ownership_ratio = CASE WHEN relationship_type = 'owner' THEN 1.0000 ELSE NULL END,
            valid_from = created_at::date,
            valid_to = CASE
                WHEN is_active THEN NULL
                ELSE GREATEST(created_at::date + 1, updated_at::date)
            END
    """)
    op.execute("""
        UPDATE greencity.unit_person_relationships relationship
        SET tenant_id = site.tenant_id,
            site_id = site.id,
            building_id = building.id
        FROM greencity.units unit
        JOIN greencity.buildings building ON building.id = unit.building_id
        JOIN greencity.sites site ON site.id = building.site_id
        WHERE unit.id = relationship.unit_id
    """)
    # A legacy schema has no ownership ratio.  Its active owners become 1.0000
    # in this migration, so any overlapping legacy owners would already break
    # the new invariant.  Fail before publishing a partially-valid schema.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM greencity.unit_person_relationships rel
                JOIN greencity.persons person ON person.id = rel.person_id
                JOIN greencity.units unit ON unit.id = rel.unit_id
                JOIN greencity.buildings building ON building.id = unit.building_id
                JOIN greencity.sites site ON site.id = building.site_id
                WHERE person.tenant_id <> site.tenant_id
            ) THEN
                RAISE EXCEPTION 'Legacy Person and Unit records cross tenant boundaries'
                    USING ERRCODE = '23514';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM greencity.unit_person_relationships left_owner
                JOIN greencity.unit_person_relationships right_owner
                  ON left_owner.unit_id = right_owner.unit_id
                 AND left_owner.id < right_owner.id
                WHERE left_owner.relationship_type = 'owner'
                  AND right_owner.relationship_type = 'owner'
                  AND left_owner.valid_from < COALESCE(right_owner.valid_to, 'infinity'::date)
                  AND right_owner.valid_from < COALESCE(left_owner.valid_to, 'infinity'::date)
            ) THEN
                RAISE EXCEPTION 'Legacy ownership records overlap and cannot be migrated safely'
                    USING ERRCODE = '23514';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM greencity.unit_person_relationships left_relation
                JOIN greencity.unit_person_relationships right_relation
                  ON left_relation.unit_id = right_relation.unit_id
                 AND left_relation.person_id = right_relation.person_id
                 AND left_relation.relationship_type = right_relation.relationship_type
                 AND left_relation.id < right_relation.id
                WHERE left_relation.valid_from < COALESCE(right_relation.valid_to, 'infinity'::date)
                  AND right_relation.valid_from < COALESCE(left_relation.valid_to, 'infinity'::date)
            ) THEN
                RAISE EXCEPTION 'Legacy Person relationship records overlap and cannot be migrated safely'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
    """)
    op.alter_column(TABLE, "valid_from", nullable=False, schema=SCHEMA)
    op.alter_column(TABLE, "tenant_id", nullable=False, schema=SCHEMA)
    op.alter_column(TABLE, "site_id", nullable=False, schema=SCHEMA)
    op.alter_column(TABLE, "building_id", nullable=False, schema=SCHEMA)
    op.drop_column(TABLE, "is_active", schema=SCHEMA)

    op.create_unique_constraint("uq_persons_id_tenant_id", "persons", ["id", "tenant_id"], schema=SCHEMA)
    op.drop_constraint(
        "fk_unit_person_relationships_person_id_persons", TABLE,
        schema=SCHEMA, type_="foreignkey",
    )
    op.drop_constraint(
        "fk_unit_person_relationships_unit_id_units", TABLE,
        schema=SCHEMA, type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_unit_person_relationships_tenant_id_tenants", TABLE, "tenants",
        ["tenant_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_unit_person_relationships_person_tenant", TABLE, "persons",
        ["person_id", "tenant_id"], ["id", "tenant_id"],
        source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_unit_person_relationships_unit_building", TABLE, "units",
        ["unit_id", "building_id"], ["id", "building_id"],
        source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_unit_person_relationships_building_site", TABLE, "buildings",
        ["building_id", "site_id"], ["id", "site_id"],
        source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_unit_person_relationships_site_tenant", TABLE, "sites",
        ["site_id", "tenant_id"], ["id", "tenant_id"],
        source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
    )

    op.create_check_constraint(
        "relationship_type_allowed",
        TABLE,
        "relationship_type IN ('owner', 'tenant', 'family_member')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "valid_interval",
        TABLE,
        "valid_to IS NULL OR valid_to > valid_from",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ownership_ratio_semantics",
        TABLE,
        "(relationship_type = 'owner' AND ownership_ratio > 0 AND ownership_ratio <= 1) "
        "OR (relationship_type <> 'owner' AND ownership_ratio IS NULL)",
        schema=SCHEMA,
    )
    op.create_unique_constraint(
        "uq_unit_person_relationships_episode",
        TABLE,
        ["unit_id", "person_id", "relationship_type", "valid_from"],
        schema=SCHEMA,
    )

    op.execute("""
        CREATE FUNCTION greencity.enforce_unit_person_relationship_scope_and_ratio()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            person_tenant uuid;
            unit_tenant uuid;
            unit_site uuid;
            unit_building uuid;
            exceeds_limit boolean;
        BEGIN
            SELECT tenant_id INTO person_tenant
            FROM greencity.persons
            WHERE id = NEW.person_id
            FOR SHARE;

            SELECT b.id, s.id, s.tenant_id
            INTO unit_building, unit_site, unit_tenant
            FROM greencity.units u
            JOIN greencity.buildings b ON b.id = u.building_id
            JOIN greencity.sites s ON s.id = b.site_id
            WHERE u.id = NEW.unit_id
            FOR UPDATE OF u, b, s;

            IF person_tenant IS NULL OR unit_tenant IS NULL OR person_tenant <> unit_tenant THEN
                RAISE EXCEPTION 'Person and Unit must belong to the same tenant'
                    USING ERRCODE = '23514';
            END IF;

            IF (NEW.tenant_id IS NOT NULL AND NEW.tenant_id IS DISTINCT FROM unit_tenant)
               OR (NEW.site_id IS NOT NULL AND NEW.site_id IS DISTINCT FROM unit_site)
               OR (NEW.building_id IS NOT NULL AND NEW.building_id IS DISTINCT FROM unit_building) THEN
                RAISE EXCEPTION 'Relationship scope must be derived from the Unit'
                    USING ERRCODE = '23514';
            END IF;
            NEW.tenant_id := unit_tenant;
            NEW.site_id := unit_site;
            NEW.building_id := unit_building;

            IF EXISTS (
                SELECT 1
                FROM greencity.unit_person_relationships rel
                WHERE rel.unit_id = NEW.unit_id
                  AND rel.person_id = NEW.person_id
                  AND rel.relationship_type = NEW.relationship_type
                  AND rel.id <> NEW.id
                  AND rel.valid_from < COALESCE(NEW.valid_to, 'infinity'::date)
                  AND NEW.valid_from < COALESCE(rel.valid_to, 'infinity'::date)
            ) THEN
                RAISE EXCEPTION 'Person relationship interval overlaps an existing episode'
                    USING ERRCODE = '23514';
            END IF;

            IF NEW.relationship_type = 'owner' THEN
                SELECT EXISTS (
                    WITH boundary_points AS (
                        SELECT NEW.valid_from AS point
                        UNION
                        SELECT rel.valid_from
                        FROM greencity.unit_person_relationships rel
                        WHERE rel.unit_id = NEW.unit_id
                          AND rel.relationship_type = 'owner'
                          AND rel.id <> NEW.id
                          AND rel.valid_from < COALESCE(NEW.valid_to, 'infinity'::date)
                          AND NEW.valid_from < COALESCE(rel.valid_to, 'infinity'::date)
                    )
                    SELECT 1
                    FROM boundary_points boundary
                    WHERE NEW.ownership_ratio + COALESCE((
                        SELECT SUM(rel.ownership_ratio)
                        FROM greencity.unit_person_relationships rel
                        WHERE rel.unit_id = NEW.unit_id
                          AND rel.relationship_type = 'owner'
                          AND rel.id <> NEW.id
                          AND rel.valid_from <= boundary.point
                          AND (rel.valid_to IS NULL OR rel.valid_to > boundary.point)
                    ), 0) > 1.0000
                ) INTO exceeds_limit;

                IF exceeds_limit THEN
                    RAISE EXCEPTION 'Total effective ownership ratio exceeds 1.0000'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_unit_person_relationship_scope_and_ratio
        BEFORE INSERT OR UPDATE ON greencity.unit_person_relationships
        FOR EACH ROW EXECUTE FUNCTION greencity.enforce_unit_person_relationship_scope_and_ratio()
    """)
    # These triggers provide a clear domain error.  The scope foreign keys above
    # remain the final, transaction-safe guard against parent re-parenting races.
    op.execute("""
        CREATE FUNCTION greencity.prevent_person_tenant_change_with_relationships()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
               AND EXISTS (
                    SELECT 1 FROM greencity.unit_person_relationships rel
                    WHERE rel.person_id = OLD.id
               ) THEN
                RAISE EXCEPTION 'Cannot move a Person with Unit relationships to another tenant'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_persons_prevent_tenant_change_with_relationships
        BEFORE UPDATE OF tenant_id ON greencity.persons
        FOR EACH ROW EXECUTE FUNCTION greencity.prevent_person_tenant_change_with_relationships()
    """)
    op.execute("""
        CREATE FUNCTION greencity.prevent_site_tenant_change_with_relationships()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
               AND EXISTS (
                    SELECT 1
                    FROM greencity.buildings building
                    JOIN greencity.units unit ON unit.building_id = building.id
                    JOIN greencity.unit_person_relationships rel ON rel.unit_id = unit.id
                    WHERE building.site_id = OLD.id
               ) THEN
                RAISE EXCEPTION 'Cannot move a Site with Unit relationships to another tenant'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_sites_prevent_tenant_change_with_relationships
        BEFORE UPDATE OF tenant_id ON greencity.sites
        FOR EACH ROW EXECUTE FUNCTION greencity.prevent_site_tenant_change_with_relationships()
    """)
    op.execute("""
        CREATE FUNCTION greencity.prevent_unit_cross_tenant_move_with_relationships()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            old_tenant uuid;
            new_tenant uuid;
        BEGIN
            IF NEW.building_id IS DISTINCT FROM OLD.building_id
               AND EXISTS (
                    SELECT 1 FROM greencity.unit_person_relationships rel
                    WHERE rel.unit_id = OLD.id
               ) THEN
                SELECT site.tenant_id INTO old_tenant
                FROM greencity.buildings building
                JOIN greencity.sites site ON site.id = building.site_id
                WHERE building.id = OLD.building_id;
                SELECT site.tenant_id INTO new_tenant
                FROM greencity.buildings building
                JOIN greencity.sites site ON site.id = building.site_id
                WHERE building.id = NEW.building_id;
                IF old_tenant IS DISTINCT FROM new_tenant THEN
                    RAISE EXCEPTION 'Cannot move a related Unit across tenants'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_units_prevent_cross_tenant_move_with_relationships
        BEFORE UPDATE OF building_id ON greencity.units
        FOR EACH ROW EXECUTE FUNCTION greencity.prevent_unit_cross_tenant_move_with_relationships()
    """)
    op.execute("""
        CREATE FUNCTION greencity.prevent_building_cross_tenant_move_with_relationships()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            old_tenant uuid;
            new_tenant uuid;
        BEGIN
            IF NEW.site_id IS DISTINCT FROM OLD.site_id
               AND EXISTS (
                    SELECT 1
                    FROM greencity.units unit
                    JOIN greencity.unit_person_relationships rel ON rel.unit_id = unit.id
                    WHERE unit.building_id = OLD.id
               ) THEN
                SELECT tenant_id INTO old_tenant FROM greencity.sites WHERE id = OLD.site_id;
                SELECT tenant_id INTO new_tenant FROM greencity.sites WHERE id = NEW.site_id;
                IF old_tenant IS DISTINCT FROM new_tenant THEN
                    RAISE EXCEPTION 'Cannot move a Building with Unit relationships across tenants'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_buildings_prevent_cross_tenant_move_with_relationships
        BEFORE UPDATE OF site_id ON greencity.buildings
        FOR EACH ROW EXECUTE FUNCTION greencity.prevent_building_cross_tenant_move_with_relationships()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_buildings_prevent_cross_tenant_move_with_relationships ON greencity.buildings")
    op.execute("DROP FUNCTION IF EXISTS greencity.prevent_building_cross_tenant_move_with_relationships()")
    op.execute("DROP TRIGGER IF EXISTS trg_units_prevent_cross_tenant_move_with_relationships ON greencity.units")
    op.execute("DROP FUNCTION IF EXISTS greencity.prevent_unit_cross_tenant_move_with_relationships()")
    op.execute("DROP TRIGGER IF EXISTS trg_sites_prevent_tenant_change_with_relationships ON greencity.sites")
    op.execute("DROP FUNCTION IF EXISTS greencity.prevent_site_tenant_change_with_relationships()")
    op.execute("DROP TRIGGER IF EXISTS trg_persons_prevent_tenant_change_with_relationships ON greencity.persons")
    op.execute("DROP FUNCTION IF EXISTS greencity.prevent_person_tenant_change_with_relationships()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_unit_person_relationship_scope_and_ratio "
        "ON greencity.unit_person_relationships"
    )
    op.execute("DROP FUNCTION IF EXISTS greencity.enforce_unit_person_relationship_scope_and_ratio()")
    op.drop_constraint(
        "fk_unit_person_relationships_site_tenant", TABLE,
        schema=SCHEMA, type_="foreignkey",
    )
    op.drop_constraint(
        "fk_unit_person_relationships_building_site", TABLE,
        schema=SCHEMA, type_="foreignkey",
    )
    op.drop_constraint(
        "fk_unit_person_relationships_unit_building", TABLE,
        schema=SCHEMA, type_="foreignkey",
    )
    op.drop_constraint(
        "fk_unit_person_relationships_person_tenant", TABLE,
        schema=SCHEMA, type_="foreignkey",
    )
    op.drop_constraint(
        "fk_unit_person_relationships_tenant_id_tenants", TABLE,
        schema=SCHEMA, type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_unit_person_relationships_unit_id_units", TABLE, "units",
        ["unit_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_unit_person_relationships_person_id_persons", TABLE, "persons",
        ["person_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="CASCADE",
    )
    op.drop_constraint("uq_persons_id_tenant_id", "persons", schema=SCHEMA, type_="unique")
    op.drop_constraint("uq_unit_person_relationships_episode", TABLE, schema=SCHEMA, type_="unique")
    op.drop_constraint(
        op.f("ck_unit_person_relationships_ownership_ratio_semantics"), TABLE,
        schema=SCHEMA, type_="check",
    )
    op.drop_constraint(
        op.f("ck_unit_person_relationships_valid_interval"), TABLE,
        schema=SCHEMA, type_="check",
    )
    op.drop_constraint(
        op.f("ck_unit_person_relationships_relationship_type_allowed"), TABLE,
        schema=SCHEMA, type_="check",
    )
    op.add_column(TABLE, sa.Column("is_active", sa.Boolean(), nullable=True), schema=SCHEMA)
    op.execute(
        "UPDATE greencity.unit_person_relationships "
        "SET is_active = (valid_from <= CURRENT_DATE "
        "AND (valid_to IS NULL OR valid_to > CURRENT_DATE))"
    )
    op.alter_column(TABLE, "is_active", nullable=False, server_default=sa.true(), schema=SCHEMA)
    op.drop_column(TABLE, "valid_to", schema=SCHEMA)
    op.drop_column(TABLE, "valid_from", schema=SCHEMA)
    op.drop_column(TABLE, "ownership_ratio", schema=SCHEMA)
    op.drop_column(TABLE, "building_id", schema=SCHEMA)
    op.drop_column(TABLE, "site_id", schema=SCHEMA)
    op.drop_column(TABLE, "tenant_id", schema=SCHEMA)
