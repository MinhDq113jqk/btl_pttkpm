"""Verify new DDL independently of the persistent assignment database."""
import os
from uuid import uuid4
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from app.core.config import Settings
from app.core.database import Database
from scripts.test_migration_0018 import _assert_isolated
from scripts.test_migration_0023 import _migrate


def main():
    original = os.environ['DATABASE_URL']; _assert_isolated(original)
    control = Database(Settings()); name = 'gc_sad_extensions_' + uuid4().hex[:12]
    with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn: conn.execute(text(f'CREATE DATABASE "{name}"'))
    os.environ['DATABASE_URL'] = make_url(original).set(database=name).render_as_string(hide_password=False)
    database = Database(Settings())
    try:
        _migrate('upgrade', '0025')
        tables = set(inspect(database.engine).get_table_names(schema='greencity'))
        for _ in range(2):
            _migrate('upgrade', '0026'); _migrate('upgrade', '0026')
            added = set(inspect(database.engine).get_table_names(schema='greencity')) - tables
            assert added == {'commercial_ledgers','exchange_object_states','exchange_receipts','assistant_conversations'}
            _migrate('downgrade','0025')
            assert set(inspect(database.engine).get_table_names(schema='greencity')) == tables
        _migrate('upgrade','0026'); print('0026 migration upgrade/repeat/downgrade/re-upgrade: PASS')
    finally:
        database.close(); os.environ['DATABASE_URL'] = original
        with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn: conn.execute(text(f'DROP DATABASE "{name}"'))
        control.close()


if __name__ == '__main__': main()
