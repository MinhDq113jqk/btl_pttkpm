"""Check fee-history backfill and legacy invoice preservation on a disposable DB."""
from datetime import date
import os
from uuid import uuid4

from sqlalchemy import inspect, text, MetaData, Table
from types import SimpleNamespace
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.database import Database
from app.models.account import Account
from app.models.billing import AccountingPeriod, BillingAccount, BillingInvoice, BillingRun, FeePolicy, FeePolicyVersion
from app.models.building import Building
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit
from scripts.test_migration_0018 import _assert_isolated, _migrate


def add_legacy(session, model, **values):
    table = Table(model.__tablename__, MetaData(), schema='greencity', autoload_with=session.get_bind())
    for column in model.__table__.columns:
        if column.name in table.c and column.name not in values and column.default is not None:
            values[column.name] = column.default.arg(None) if column.default.is_callable else column.default.arg
    values = {k: v for k, v in values.items() if k in table.c}
    session.execute(table.insert().values(**values))
    return SimpleNamespace(**values)


def main():
    original_url = os.environ['DATABASE_URL']
    _assert_isolated(original_url)
    control = Database(Settings())
    database_name = 'gc_fee_migration_' + uuid4().hex[:12]
    with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    # A sibling disposable database keeps immutable historical fixtures intact.
    os.environ['DATABASE_URL'] = make_url(original_url).set(database=database_name).render_as_string(hide_password=False)
    database = Database(Settings())
    try:
        _migrate('upgrade', '0019')
        with database.get_session() as session:
            tenant = Tenant(name='Migration 0020 ' + uuid4().hex)
            session.add(tenant); session.flush()
            site = Site(tenant_id=tenant.id, code='M20-' + uuid4().hex[:8], name='Synthetic', address='Synthetic')
            session.add(site); session.flush()
            building = Building(site_id=site.id, code='B1', name='Synthetic')
            session.add(building); session.flush()
            unit = Unit(building_id=building.id, unit_number='0101', floor=1, area_m2=50, status='occupied')
            actor = Account(tenant_id=tenant.id, username='migration20_' + uuid4().hex,
                full_name='Synthetic', hashed_password='token-only-test-account')
            session.add_all([unit, actor]); session.flush()
            scope = dict(tenant_id=tenant.id, site_id=site.id, building_id=building.id)
            account = BillingAccount(**scope, unit_id=unit.id, account_number='M20-' + uuid4().hex[:8], opened_on=date(2026, 1, 1))
            policy = FeePolicy(**scope, code='M20', name='Synthetic')
            period = AccountingPeriod(**scope, period_key='2026-09', period_start=date(2026, 9, 1), period_end=date(2026, 9, 30))
            session.add_all([account, policy, period]); session.flush()
            version = add_legacy(session, FeePolicyVersion,**scope, fee_policy_id=policy.id, version_number=1,
                effective_from=date(2026, 1, 1), unit_rate_vnd=52345, basis='SERVICE_UNIT', rounding_unit_vnd=1)
            session.flush()
            run = BillingRun(**scope, accounting_period_id=period.id, fee_policy_version_id=version.id,
                run_key='M20', status='POSTED', initiated_by_id=actor.id)
            session.add(run); session.flush()
            invoice = add_legacy(session, BillingInvoice,**scope, billing_account_id=account.id, billing_run_id=run.id,
                accounting_period_id=period.id, invoice_number='M20', issued_on=date(2026, 9, 30),
                total_vnd=52345, outstanding_vnd=52345, status='ISSUED')
            session.flush()
            item_id = uuid4()
            session.execute(text('''INSERT INTO greencity.billing_invoice_items
                (id, tenant_id, site_id, building_id, billing_invoice_id, fee_policy_version_id, line_number,
                 description, basis, basis_quantity, unit_rate_vnd_snapshot, rounding_unit_vnd_snapshot, amount_vnd)
                VALUES (:id, :tenant_id, :site_id, :building_id, :invoice, :version, 1,
                    'Legacy amount', 'SERVICE_UNIT', 1, 52345, 1, 52345)'''),
                dict(scope, id=item_id, invoice=invoice.id, version=version.id))
            source_ids = [uuid4(), uuid4()]
            for source_id, valid_to in zip(source_ids, [None, date(2026, 9, 11)]):
                session.execute(text('''INSERT INTO greencity.portal_fee_sources
                    (id, tenant_id, site_id, building_id, unit_id, account_id, source_kind, source_id,
                     description, amount_vnd, basis, recurring, valid_from, valid_to, policy_snapshot)
                    VALUES (:id, :tenant_id, :site_id, :building_id, :unit, :actor, 'SERVICE', :origin,
                        'Legacy source', 300000, 'SERVICE_UNIT', true, '2026-09-01', :stop, '{}')'''),
                    dict(scope, id=source_id, unit=unit.id, actor=actor.id, origin=uuid4(), stop=valid_to))
            session.commit()
        for _ in range(2):
            _migrate('upgrade', '0020')
            _migrate('upgrade', '0020')
            with database.engine.connect() as connection:
                rows = connection.execute(text('''SELECT s.id, s.status, i.starts_on, i.ends_on, i.amount_vnd
                    FROM greencity.portal_fee_sources s JOIN greencity.portal_fee_intervals i ON i.fee_source_id=s.id
                    WHERE s.tenant_id=:tenant'''), {'tenant': tenant.id}).all()
                assert set(rows) == {(source_ids[0], 'ACTIVE', date(2026, 9, 1), None, 300000),
                    (source_ids[1], 'ENDED', date(2026, 9, 1), date(2026, 9, 11), 300000)}
                assert connection.execute(text('SELECT amount_vnd, calculation_snapshot FROM greencity.billing_invoice_items WHERE id=:id'),
                    {'id': item_id}).one() == (52345, {})
            _migrate('downgrade', '0019')
            with database.engine.connect() as connection:
                assert 'portal_fee_intervals' not in inspect(connection).get_table_names(schema='greencity')
                assert connection.scalar(text('SELECT amount_vnd FROM greencity.billing_invoice_items WHERE id=:id'), {'id': item_id}) == 52345
        print('Fee proration migration backfill/downgrade/repeat: PASS')
        return 0
    finally:
        database.close()
        os.environ['DATABASE_URL'] = original_url
        try:
            with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
                connection.execute(text(f'DROP DATABASE "{database_name}"'))
        finally:
            control.close()


if __name__ == '__main__':
    raise SystemExit(main())
