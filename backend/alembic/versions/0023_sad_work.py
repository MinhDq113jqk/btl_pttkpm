"""Add SAD T01-T08 relations; legacy assignments copy only existing fields."""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

UPGRADE_SQL = "\nALTER TABLE greencity.buildings ADD COLUMN zone_id uuid REFERENCES greencity.property_nodes(id);\nALTER TABLE greencity.billing_fee_policy_versions ADD COLUMN created_by_id uuid REFERENCES greencity.accounts(id);\nALTER TABLE greencity.billing_fee_policy_versions ADD COLUMN tariff json NOT NULL DEFAULT '{}';\nALTER TABLE greencity.work_orders ADD COLUMN asset_id uuid REFERENCES greencity.assets(id);\nALTER TABLE greencity.work_orders ADD COLUMN asset_snapshot json;\nCREATE INDEX ix_work_orders_asset_id ON greencity.work_orders(asset_id);\nALTER TABLE greencity.operational_stock_items ADD COLUMN damaged_quantity numeric(18,4) NOT NULL DEFAULT 0;\nALTER TABLE greencity.operational_stock_items ADD CONSTRAINT ck_operational_stock_items_stock_damaged_nonnegative CHECK (damaged_quantity >= 0);\nALTER TABLE greencity.operational_stock_movements ADD COLUMN custody json NOT NULL DEFAULT '{}';\nDO $$ DECLARE c record; BEGIN FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='greencity.assets'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%status%' LOOP EXECUTE format('ALTER TABLE greencity.assets DROP CONSTRAINT %I', c.conname); END LOOP; END $$;\nALTER TABLE greencity.assets ADD CONSTRAINT ck_assets_assets_status CHECK (status IN ('ACTIVE','INACTIVE','RETIRED','DISPOSED'));\n\nCREATE TABLE greencity.meter_assignments (\n\tmeter_id UUID NOT NULL, \n\tpoint VARCHAR(200) NOT NULL, \n\tvalid_from DATE NOT NULL, \n\tvalid_to DATE, \n\tevidence_reference VARCHAR(300) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tsite_id UUID NOT NULL, \n\tbuilding_id UUID, \n\tunit_id UUID, \n\taccount_id UUID NOT NULL, \n\tversion INTEGER DEFAULT '1' NOT NULL, \n\tCONSTRAINT pk_meter_assignments PRIMARY KEY (id), \n\tCONSTRAINT fk_meter_assignments_site FOREIGN KEY(site_id, tenant_id) REFERENCES greencity.sites (id, tenant_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_meter_assignments_building FOREIGN KEY(building_id, site_id) REFERENCES greencity.buildings (id, site_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_meter_assignments_unit FOREIGN KEY(unit_id, building_id) REFERENCES greencity.units (id, building_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_meter_assignments_account FOREIGN KEY(account_id, tenant_id) REFERENCES greencity.accounts (id, tenant_id) ON DELETE RESTRICT, \n\tCONSTRAINT uq_meter_assignments_scope UNIQUE (id, tenant_id, site_id), \n\tCONSTRAINT ck_meter_assignments_meter_assignments_version CHECK (version > 0), \n\tCONSTRAINT ck_meter_assignments_meter_assignments_unit_scope CHECK (unit_id IS NULL OR building_id IS NOT NULL), \n\tCONSTRAINT ck_meter_assignments_meter_assignment_interval CHECK (valid_to IS NULL OR valid_to > valid_from), \n\tCONSTRAINT fk_meter_assignments_meter_id_operational_meters FOREIGN KEY(meter_id) REFERENCES greencity.operational_meters (id)\n)\n\n;\nCREATE INDEX ix_meter_assignment_interval ON greencity.meter_assignments (meter_id, valid_from, valid_to);\nCREATE INDEX ix_meter_assignments_scope ON greencity.meter_assignments (tenant_id, site_id, building_id, unit_id);\n\nINSERT INTO greencity.meter_assignments (id, tenant_id, site_id, building_id, unit_id, account_id, version, meter_id, point, valid_from, valid_to, evidence_reference)\nSELECT gen_random_uuid(), tenant_id, site_id, building_id, unit_id, account_id, 1, id, code, valid_from, valid_to, 'LEGACY_METER_FIELDS_ONLY' FROM greencity.operational_meters;\n"

DOWNGRADE_SQL = "\nDROP TABLE greencity.meter_assignments;\nALTER TABLE greencity.buildings DROP COLUMN zone_id;\nALTER TABLE greencity.billing_fee_policy_versions DROP COLUMN tariff, DROP COLUMN created_by_id;\nDROP INDEX greencity.ix_work_orders_asset_id;\nALTER TABLE greencity.work_orders DROP COLUMN asset_snapshot, DROP COLUMN asset_id;\nALTER TABLE greencity.operational_stock_movements DROP COLUMN custody;\nALTER TABLE greencity.operational_stock_items DROP COLUMN damaged_quantity;\nDO $$ DECLARE c record; BEGIN FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='greencity.assets'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%status%' LOOP EXECUTE format('ALTER TABLE greencity.assets DROP CONSTRAINT %I', c.conname); END LOOP; END $$;\nALTER TABLE greencity.assets ADD CONSTRAINT ck_assets_assets_status CHECK (status IN ('ACTIVE','INACTIVE','RETIRED'));\n"

UPGRADE_SQL += """
ALTER TABLE greencity.buildings ADD COLUMN status varchar(20) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE greencity.buildings ADD COLUMN version integer NOT NULL DEFAULT 1;
CREATE FUNCTION greencity.guard_meter_assignment() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Meter assignment history cannot be deleted'; END IF;
  PERFORM id FROM greencity.operational_meters WHERE id=NEW.meter_id AND tenant_id=NEW.tenant_id
    AND site_id=NEW.site_id AND building_id=NEW.building_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Meter assignment scope differs from device'; END IF;
  IF TG_OP = 'UPDATE' AND ((NEW.meter_id,NEW.tenant_id,NEW.site_id,NEW.building_id,NEW.unit_id,NEW.point,NEW.valid_from,NEW.account_id,NEW.evidence_reference)
    IS DISTINCT FROM (OLD.meter_id,OLD.tenant_id,OLD.site_id,OLD.building_id,OLD.unit_id,OLD.point,OLD.valid_from,OLD.account_id,OLD.evidence_reference)
    OR OLD.valid_to IS NOT NULL AND NEW.valid_to IS DISTINCT FROM OLD.valid_to) THEN
    RAISE EXCEPTION 'Closed assignment and its origin are immutable';
  END IF;
  IF EXISTS (SELECT 1 FROM greencity.meter_assignments a WHERE a.meter_id=NEW.meter_id AND a.id<>NEW.id
    AND daterange(a.valid_from,a.valid_to,'[)') && daterange(NEW.valid_from,NEW.valid_to,'[)')) THEN
    RAISE EXCEPTION 'Meter assignment intervals overlap';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER meter_assignment_guard BEFORE INSERT OR UPDATE OR DELETE ON greencity.meter_assignments
  FOR EACH ROW EXECUTE FUNCTION greencity.guard_meter_assignment();
"""
DOWNGRADE_SQL = """
DROP TRIGGER meter_assignment_guard ON greencity.meter_assignments;
DROP FUNCTION greencity.guard_meter_assignment();
ALTER TABLE greencity.buildings DROP COLUMN status, DROP COLUMN version;
""" + DOWNGRADE_SQL

def upgrade():
    op.execute(UPGRADE_SQL)

def downgrade():
    op.execute(DOWNGRADE_SQL)
