"""Empty/repeated upgrade/downgrade and immutable export/data-loss guards."""
import os
from uuid import uuid4
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from app.core.config import Settings
from app.core.database import Database
from app.models.account import Account
from app.models.tenant import Tenant
from app.models.site import Site
from app.models.operational_control import ReportExport
from app.services.r2 import utc_now
from scripts.test_migration_0018 import _assert_isolated, _migrate


def main():
    original = os.environ['DATABASE_URL']; _assert_isolated(original)
    control = Database(Settings()); name = 'gc_operations_migration_' + uuid4().hex[:12]
    with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    os.environ['DATABASE_URL'] = make_url(original).set(database=name).render_as_string(hide_password=False)
    database = Database(Settings())
    try:
        _migrate('upgrade', '0021')
        for _ in range(2):
            _migrate('upgrade', '0022'); _migrate('upgrade', '0022')
            with database.engine.connect() as c:
                assert 'operational_meter_readings' in inspect(c).get_table_names(schema='greencity')
                assert c.scalar(text('SELECT count(*) FROM greencity.treasury_movements')) == 0
            _migrate('downgrade', '0021')
            with database.engine.connect() as c:
                assert 'operational_meter_readings' not in inspect(c).get_table_names(schema='greencity')
        _migrate('upgrade', '0022')
        with database.get_session() as s:
            tenant = Tenant(name='Synthetic guard'); s.add(tenant); s.flush()
            actor = Account(tenant_id=tenant.id, username=uuid4().hex, full_name='Synthetic', hashed_password='token-only-test-account')
            site = Site(tenant_id=tenant.id, code=uuid4().hex, name='Synthetic', address='Synthetic')
            s.add_all([actor, site]); s.flush()
            s.add(ReportExport(tenant_id=tenant.id, site_id=site.id, account_id=actor.id, kind='STOCK', as_of=utc_now(), rows=[], digest='0'*64)); s.commit()
        refused = False
        try:
            _migrate('downgrade', '0021')
        except Exception:
            refused = True
        assert refused
        with database.engine.connect() as c:
            assert c.scalar(text('SELECT version_num FROM greencity.alembic_version')) == '0022'
            assert c.scalar(text('SELECT count(*) FROM greencity.report_exports')) == 1
        print('0022 upgrade/repeat/downgrade/no synthetic backfill/data-loss guard: PASS')
        return 0
    finally:
        database.close(); os.environ['DATABASE_URL'] = original
        with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as c:
            c.execute(text(f'DROP DATABASE "{name}"'))
        control.close()


if __name__ == '__main__':
    raise SystemExit(main())
