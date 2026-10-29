"""Upgrade/repeat/downgrade and data-loss guards on a sibling disposable database."""
import os
from uuid import uuid4
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from app.core.config import Settings
from app.core.database import Database
from app.models.account import Account
from app.models.tenant import Tenant
from app.models.financial_control import FinanceEvent
from scripts.test_migration_0018 import _assert_isolated, _migrate


def main():
    original=os.environ['DATABASE_URL'];_assert_isolated(original)
    control=Database(Settings());name='gc_control_migration_'+uuid4().hex[:12]
    with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as c:c.execute(text(f'CREATE DATABASE "{name}"'))
    os.environ['DATABASE_URL']=make_url(original).set(database=name).render_as_string(hide_password=False)
    database=Database(Settings())
    try:
        _migrate('upgrade','0020')
        for _ in range(2):
            _migrate('upgrade','0021');_migrate('upgrade','0021')
            with database.engine.connect() as c:
                assert 'billing_reviews' in inspect(c).get_table_names(schema='greencity')
                assert c.scalar(text('SELECT count(*) FROM greencity.unit_profile_episodes'))==0
                assert c.scalar(text('SELECT count(*) FROM greencity.lease_contracts'))==0
            _migrate('downgrade','0020')
            with database.engine.connect() as c:assert 'billing_reviews' not in inspect(c).get_table_names(schema='greencity')
        _migrate('upgrade','0021')
        with database.get_session() as s:
            tenant=Tenant(name='Synthetic guard '+uuid4().hex);s.add(tenant);s.flush()
            actor=Account(tenant_id=tenant.id,username=uuid4().hex,full_name='Synthetic',hashed_password='token-only-test-account')
            s.add(actor);s.flush();s.add(FinanceEvent(resource_type='FinanceCommand',resource_id=uuid4(),actor_id=actor.id,action='CREATE',reason='Synthetic guard',snapshot={}));s.commit()
        refused=False
        try:_migrate('downgrade','0020')
        except Exception:refused=True
        assert refused
        with database.engine.connect() as c:
            assert c.scalar(text('SELECT version_num FROM greencity.alembic_version'))=='0021'
            assert c.scalar(text('SELECT count(*) FROM greencity.finance_events'))==1
        print('0021 upgrade/repeat/downgrade/no inferred history/data guard: PASS')
        return 0
    finally:
        database.close();os.environ['DATABASE_URL']=original
        with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as c:c.execute(text(f'DROP DATABASE "{name}"'))
        control.close()


if __name__=='__main__':raise SystemExit(main())
