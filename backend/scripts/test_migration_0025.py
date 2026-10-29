"""Reversible migration on an explicitly disposable empty/legacy database."""
import os
from uuid import uuid4
from sqlalchemy import inspect,text
from sqlalchemy.engine import make_url
from app.core.config import Settings
from app.core.database import Database
from scripts.test_migration_0018 import _assert_isolated
from scripts.test_migration_0023 import _migrate


def main():
    original=os.environ['DATABASE_URL'];_assert_isolated(original)
    control=Database(Settings());name='gc_sad_completion_'+uuid4().hex[:12]
    with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:conn.execute(text(f'CREATE DATABASE "{name}"'))
    os.environ['DATABASE_URL']=make_url(original).set(database=name).render_as_string(hide_password=False)
    database=Database(Settings())
    try:
        _migrate('upgrade','0024')
        identifiers={k:uuid4() for k in ('tenant','site','account','content','report')}
        with database.engine.begin() as conn:
            conn.execute(text("INSERT INTO greencity.tenants (id,name) VALUES (:tenant,'Synthetic')"),identifiers)
            conn.execute(text("INSERT INTO greencity.sites (id,tenant_id,code,name,address) VALUES (:site,:tenant,'SYN','Synthetic','Synthetic')"),identifiers)
            conn.execute(text("INSERT INTO greencity.accounts (id,tenant_id,username,full_name,hashed_password,is_active) VALUES (:account,:tenant,'synthetic','Synthetic','token-only',true)"),identifiers)
            conn.execute(text("INSERT INTO greencity.portal_content (id,tenant_id,site_id,account_id,kind,title,body,status,publish_at) VALUES (:content,:tenant,:site,:account,'NOTICE','Synthetic legacy notice','Synthetic retained body','PUBLISHED',now())"),identifiers)
            conn.execute(text("INSERT INTO greencity.report_exports (id,tenant_id,site_id,account_id,kind,as_of,rows,digest) VALUES (:report,:tenant,:site,:account,'DOSSIERS',now(),'[]',repeat('a',64))"),identifiers)
        for _ in range(2):
            _migrate('upgrade','0025');_migrate('upgrade','0025')
            with database.engine.connect() as conn:
                for table in ('community_tasks','sla_policies','init_datasets','job_effects'):assert conn.scalar(text('SELECT count(*) FROM greencity.'+table))==0
                assert conn.scalar(text("SELECT column_default FROM information_schema.columns WHERE table_schema='greencity' AND table_name='service_requests' AND column_name='sla_pauses'")) is not None
                old=conn.execute(text('SELECT body,previous_id,minutes FROM greencity.portal_content WHERE id=:content'),identifiers).one()
                assert old.body=='Synthetic retained body' and old.previous_id is None and old.minutes=={}
                report=conn.execute(text('SELECT definition_version,metrics,rows FROM greencity.report_exports WHERE id=:report'),identifiers).one()
                assert report.definition_version=='LEGACY-COUNTS' and report.metrics=={} and report.rows==[]
            _migrate('downgrade','0024');assert 'community_tasks' not in inspect(database.engine).get_table_names(schema='greencity')
        _migrate('upgrade','0025');print('0025 upgrade/repeat/downgrade/re-upgrade; no inferred acceptance/policy: PASS')
    finally:
        database.close();os.environ['DATABASE_URL']=original
        with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:conn.execute(text(f'DROP DATABASE "{name}"'))
        control.close()


if __name__=='__main__':main()
