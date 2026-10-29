"""Synthetic upgrade/repeat/legacy backfill/downgrade, restricted to disposable PG."""
import os
import subprocess
import sys
from uuid import uuid4
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from app.core.config import Settings
from app.core.database import Database
from scripts.test_migration_0018 import _assert_isolated

def _migrate(command, revision):
    result = subprocess.run([sys.executable, "-m", "scripts.migrate", command, revision], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    if result.returncode:
        # scripts.migrate emits only sanitized identifiers in isolated mode.
        print(result.stdout)
        raise RuntimeError("SAD migration failed")


def main():
    original = os.environ['DATABASE_URL']; _assert_isolated(original)
    control = Database(Settings()); name = 'gc_sad_migration_' + uuid4().hex[:12]
    with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    os.environ['DATABASE_URL'] = make_url(original).set(database=name).render_as_string(hide_password=False)
    database = Database(Settings())
    try:
        _migrate('upgrade', '0022')
        identifiers = {k: uuid4() for k in ('tenant', 'site', 'building', 'actor', 'meter')}
        with database.engine.begin() as conn:
            # Historical schema fixtures use frozen SQL, never current ORM columns.
            conn.execute(text("INSERT INTO greencity.tenants (id,name) VALUES (:tenant,'Synthetic')"), identifiers)
            conn.execute(text("INSERT INTO greencity.sites (id,tenant_id,code,name,address) VALUES (:site,:tenant,'SYN','Synthetic','Synthetic')"), identifiers)
            conn.execute(text("INSERT INTO greencity.buildings (id,site_id,code,name,floors_count) VALUES (:building,:site,'B1','Synthetic',1)"), identifiers)
            conn.execute(text("INSERT INTO greencity.accounts (id,tenant_id,username,full_name,hashed_password,is_active,must_change_password,session_version) VALUES (:actor,:tenant,'synthetic','Synthetic','token-only',true,false,1)"), identifiers)
            conn.execute(text("INSERT INTO greencity.operational_meters (id,tenant_id,site_id,building_id,account_id,version,code,commodity,serial,multiplier,baseline,valid_from,status) VALUES (:meter,:tenant,:site,:building,:actor,1,'OLD-METER','WATER','SYN',1,100,'2026-01-01','ACTIVE')"), identifiers)
        for _ in range(2):
            _migrate('upgrade', '0023'); _migrate('upgrade', '0023')
            with database.engine.connect() as conn:
                row = conn.execute(text("SELECT point, valid_from, unit_id, evidence_reference FROM greencity.meter_assignments WHERE meter_id=:meter"), identifiers).one()
                assert row.point == 'OLD-METER' and str(row.valid_from) == '2026-01-01' and row.unit_id is None
                assert row.evidence_reference == 'LEGACY_METER_FIELDS_ONLY'
                assert conn.scalar(text('SELECT count(*) FROM greencity.meter_assignments')) == 1
            _migrate('downgrade', '0022')
        _migrate('upgrade', '0023')
        print('0023 legacy copy, upgrade/repeat/downgrade/re-upgrade: PASS')
        return 0
    finally:
        database.close(); os.environ['DATABASE_URL'] = original
        with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.execute(text(f'DROP DATABASE "{name}"'))
        control.close()


if __name__ == '__main__':
    raise SystemExit(main())
