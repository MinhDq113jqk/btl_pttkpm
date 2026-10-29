"""Frozen legacy recovery fixture and reversible DDL on disposable PostgreSQL."""
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
    control = Database(Settings()); name = 'gc_account_parking_' + uuid4().hex[:12]
    with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    os.environ['DATABASE_URL'] = make_url(original).set(database=name).render_as_string(hide_password=False)
    database = Database(Settings())
    try:
        _migrate('upgrade', '0023')
        ids = {k: uuid4() for k in ('tenant', 'account', 'recovery')}
        with database.engine.begin() as conn:
            conn.execute(text("INSERT INTO greencity.tenants (id,name) VALUES (:tenant,'Synthetic')"), ids)
            conn.execute(text("INSERT INTO greencity.accounts (id,tenant_id,username,full_name,hashed_password,is_active) VALUES (:account,:tenant,'synthetic','Synthetic','token-only',true)"), ids)
            conn.execute(text("INSERT INTO greencity.account_recovery_requests (id,tenant_id,account_id,status,token_hash) VALUES (:recovery,:tenant,:account,'VERIFIED',repeat('x',64))"), ids)
        for _ in range(2):
            _migrate('upgrade', '0024'); _migrate('upgrade', '0024')
            with database.engine.connect() as conn:
                recovery = conn.execute(text('SELECT status,token_hash,issued_session_version FROM greencity.account_recovery_requests WHERE id=:recovery'), ids).one()
                assert recovery.status == 'REJECTED' and recovery.token_hash is None and recovery.issued_session_version is None
                profile = conn.execute(text('SELECT email,email_verified_at,profile_version FROM greencity.accounts WHERE id=:account'), ids).one()
                assert profile.email is None and profile.email_verified_at is None and profile.profile_version == 1
                assert conn.scalar(text('SELECT count(*) FROM greencity.parking_usage_batches')) == 0
            _migrate('downgrade', '0023')
            assert 'account_email_changes' not in inspect(database.engine).get_table_names(schema='greencity')
        _migrate('upgrade', '0024')
        print('0024 upgrade/repeat/downgrade/re-upgrade; old token invalidation and no inferred data: PASS')
    finally:
        database.close(); os.environ['DATABASE_URL'] = original
        with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.execute(text(f'DROP DATABASE "{name}"'))
        control.close()


if __name__ == '__main__':
    main()
