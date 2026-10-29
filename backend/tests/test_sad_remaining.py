"""Remaining SAD workflows: synthetic data, disposable PG, no provider/browser/UAT."""
import os
from datetime import UTC,datetime,timedelta
from types import SimpleNamespace
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from app.models.account import Account,AccountRole
from app.models.service import ServiceCategory,ServiceRequest,WorkOrder
from app.models.resident_portal import PortalContent
from app.models.sad_completion import JobEffect
from app.models.maintenance import Asset,MaintenancePlan
from app.models.operational_control import JobSchedule,TreasuryAccount,ReportExport
from app.models.import_run import ImportRun
from app.services.sad_completion import sla_deadline
from app.services.report_metrics import metrics
from test_sad_tasks_10_11 import case
from test_step1_fee_proration import concurrent_case
from test_portal_workflows import post,action

isolated=pytest.mark.skipif(os.getenv('GREENCITY_ISOLATED_SECURITY_TESTS')!='1',reason='Disposable PostgreSQL only')


@pytest.fixture
def remaining_case(case):
    # Intake requires CSKH specifically; the baseline synthetic maker is admin/accountant.
    with case['database'].get_session() as s:
        s.add(AccountRole(account_id=case['maker'].id,role='cskh',site_id=case['site'].id,building_id=case['building'].id));s.commit()
    return case


def get(c,path,actor='cskh',**params):
    r=c['client'].get('/api/v1/portal'+path,params=params,headers=c['auth'][actor]);assert r.status_code==200,r.text;return r.json()


def create(c,path,body,actor='cskh'):
    r=post(c,path,body,actor);assert r.status_code in (200,201),r.text;return r.json()


def act(c,path,row,name,actor='cskh',data=None):
    r=action(c,path,row,name,actor,data);assert r.status_code==200,r.text;return r.json()


def test_calendar_sla_oracle_weekend_and_authorized_pause():
    # Friday 16:30 GMT+7 +120 work minutes => Monday 09:30.
    row=SimpleNamespace(sla_started_at=datetime(2026,10,9,9,30,tzinfo=UTC),sla_duration_minutes=120,
        sla_policy_snapshot={'weekdays':[1,2,3,4,5],'opens_minute':480,'closes_minute':1020},sla_pauses=[])
    assert sla_deadline(row)==datetime(2026,10,12,2,30,tzinfo=UTC)
    row.sla_pauses=[{'started_at':'2026-10-12T01:00:00+00:00','ended_at':'2026-10-12T02:00:00+00:00'}]
    assert sla_deadline(row)==datetime(2026,10,12,3,30,tzinfo=UTC)


def test_money_metrics_do_not_count_rows_or_coerce_missing_to_zero():
    rows=[{'source':'billing_invoices','data':{'status':'ISSUED','total_vnd':900,'outstanding_vnd':700}},
        {'source':'payments','data':{'status':'RECEIVED','amount_vnd':300}},
        {'source':'payment_allocations','data':{'amount_vnd':200}},
        {'source':'payment_allocation_reversals','data':{'allocation_id':'synthetic','amount_vnd':50}}]
    result=metrics('FINANCIAL',rows)
    assert result['invoiced_vnd']['value']==900 and result['allocated_vnd']['value']==150
    assert result['receivable_vnd']['value']==700 and result['cash_received_vnd']['value']==300
    assert result['external_accounting']['value'] is None
    assert metrics('SERVICE',[])['csat']['value'] is None
    expenses=[{'source':'operational_expenses','data':{'id':'advance','kind':'ADVANCE','status':'SETTLED','amount_vnd':1000,'paid_vnd':1000}}]
    assert metrics('FINANCIAL',expenses)['actual_expense_vnd']['value'] is None
    expenses.append({'source':'operations_records','data':{'kind':'ADVANCE_SETTLEMENT','status':'COMPLETED','data':{'expense_id':'advance','actual_vnd':600}}})
    assert metrics('FINANCIAL',expenses)['actual_expense_vnd']['value']==600
    huge=metrics('FINANCIAL',[{'source':'payments','data':{'status':'UNMATCHED','amount_vnd':9007199254740993}}])
    assert huge['cash_received_vnd']['value']=='9007199254740993'


def test_domain_metrics_keep_units_separate_and_missing_meter_units_explicit():
    rows=[{'source':'operational_stock_items','data':{'uom':uom,'quantity':'2.2500','reserved':'0.2500','damaged_quantity':'0','minimum':'3'}} for uom in ('kg','piece')]
    kpis=metrics('STOCK',rows)
    assert kpis['quantities_by_uom']['kg']['available']=='2.0000' and kpis['below_minimum_items']['value']==2
    meters=[{'source':'operational_meters','data':{'id':'synthetic','commodity':'WATER'}},
        {'source':'operational_meter_readings','data':{'meter_id':'synthetic','status':'VERIFIED','consumption':'20.0000'}}]
    assert metrics('METER',meters)['consumption_by_commodity_uom']['WATER/UNKNOWN'] is None
    assert metrics('METER',meters)['meter_units']['data_status']=='MISSING'


def test_capabilities_use_configuration_guards_without_provider_calls():
    from app.api.sad_completion import capabilities
    from app.core.config import Settings
    from pydantic import SecretStr
    settings=Settings(_env_file=None,app_env='test',database_url='postgresql://fixture@127.0.0.1/fixture?sslmode=require',smtp_enabled=True,smtp_host='',smtp_from_email='',smtp_username='',smtp_password=None,
        vnpay_enabled=True,vnpay_tmn_code='',vnpay_hash_secret=None,vnpay_payment_url='https://sandbox.vnpayment.vn/paymentv2/vpcpay.html')
    from unittest.mock import MagicMock
    tenant=uuid4();context=SimpleNamespace(tenant_id=tenant,assert_role=lambda *roles:None,roles=('admin',),scope_conditions=lambda model:(),role_grants=[SimpleNamespace(role='admin',building_id=None)])
    database=MagicMock();database.get_session.return_value.__enter__.return_value.scalars.return_value.all.return_value=[]
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings,database=database)))
    states=lambda:{r['name']:r['status'] for r in capabilities(request,context)['items']}
    assert states()['VNPay']==states()['SMTP email']=='NOT_CONFIGURED'
    settings.smtp_host='mail.invalid';settings.smtp_from_email='noreply@example.invalid'
    settings.vnpay_tmn_code='SYNTHETIC';settings.vnpay_hash_secret=SecretStr('synthetic-only')
    settings.vnpay_tenant_id=tenant;settings.vnpay_service_account_id=uuid4();settings.vnpay_return_url='https://example.invalid/return'
    assert states()['VNPay']==states()['SMTP email']=='CONFIGURED'
    settings.vnpay_tenant_id=uuid4();settings.smtp_username='synthetic';settings.smtp_password=None
    assert states()['VNPay']==states()['SMTP email']=='NOT_CONFIGURED'


@isolated
def test_community_revision_preserves_history_and_requires_decision_results(case):
    c=case;body={'building_id':str(c['building'].id),'kind':'MEETING','title':'Synthetic meeting','body':'Synthetic meeting body','publish_at':(datetime.now(UTC)-timedelta(minutes=1)).isoformat()}
    row=create(c,'/content',body)
    draft=create(c,f"/content/{row['id']}/revision",{'expected_version':row['version'],'reason':'Synthetic edit','content':{**body,'title':'Edited meeting'}})
    row=act(c,f"/content/{draft['id']}/actions",draft,'SUBMIT');row=act(c,f"/content/{row['id']}/actions",row,'APPROVE','director');row=act(c,f"/content/{row['id']}/actions",row,'PUBLISH')
    assert action(c,f"/content/{row['id']}/actions",row,'CLOSE').status_code==409
    minutes={'participants':['Synthetic person'],'result_basis':'Synthetic signed result','decisions':[{'key':'D1','title':'Repair shared space','owner_id':str(c['director'].id),'due_at':datetime.now(UTC).isoformat()}]}
    row=act(c,f"/content/{row['id']}/minutes",row,'RECORD_MINUTES',data=minutes)
    assert action(c,f"/content/{row['id']}/actions",row,'CLOSE').status_code==409
    task=get(c,'/community-tasks')['items'][0]
    assert action(c,f"/community-tasks/{task['id']}/actions",task,'COMPLETE','director').status_code==422
    act(c,f"/community-tasks/{task['id']}/actions",task,'COMPLETE','director',{'evidence_reference':'Synthetic result evidence'})
    row=act(c,f"/content/{row['id']}/actions",row,'CLOSE')
    revised=create(c,f"/content/{row['id']}/revision",{'expected_version':row['version'],'reason':'Synthetic correction','content':{**body,'title':'Replacement meeting'}})
    revised=act(c,f"/content/{revised['id']}/actions",revised,'SUBMIT');revised=act(c,f"/content/{revised['id']}/actions",revised,'APPROVE','director');revised=act(c,f"/content/{revised['id']}/actions",revised,'PUBLISH')
    chain=get(c,f"/content/{revised['id']}/chain")['items'];assert len(chain)==2 and chain[0]['status']=='WITHDRAWN' and chain[0]['title']=='Edited meeting'
    assert post(c,f"/content/{revised['id']}/revision",{'expected_version':1,'reason':'Stale edit','content':body},'cskh').status_code==409


def category(c):
    with c['database'].get_session() as s:
        row=ServiceCategory(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,code='SYN-'+uuid4().hex[:12],name='Synthetic category',sla_minutes=60);s.add(row);s.commit();return row


@isolated
def test_completion_options_and_site_meeting_can_reach_closed(case):
    c=case;cat=category(c)
    options=get(c,'/completion-options',building_id=str(c['building'].id))
    assert str(cat.id) in {r['id'] for r in options['categories']}
    assert str(c['director'].id) in {r['id'] for r in options['accounts']}
    assert str(c['worker'].id) not in {r['id'] for r in options['accounts']}
    assert c['client'].get('/api/v1/portal/completion-options',params={'building_id':str(uuid4())},headers=c['auth']['admin']).status_code==404
    assert c['client'].get('/api/v1/portal/completion-options',params={'building_id':str(c['building'].id)},headers=c['auth']['resident']).status_code==403
    site_options=get(c,'/completion-options','admin')
    assert str(c['director'].id) in {r['id'] for r in site_options['accounts']}
    assert site_options['requests']==site_options['csv_batches']==site_options['loader_batches']==[]
    row=create(c,'/content',{'kind':'MEETING','title':'Synthetic site meeting','body':'Synthetic site body','publish_at':(datetime.now(UTC)-timedelta(minutes=1)).isoformat()},'admin')
    row=act(c,f"/content/{row['id']}/actions",row,'SUBMIT','admin')
    row=act(c,f"/content/{row['id']}/actions",row,'APPROVE','director')
    row=act(c,f"/content/{row['id']}/actions",row,'PUBLISH','admin')
    row=act(c,f"/content/{row['id']}/minutes",row,'RECORD_MINUTES','admin',{'participants':['Synthetic attendee'],'result_basis':'Synthetic site decision','decisions':[{'key':'SITE1','title':'Synthetic site task','owner_id':str(c['director'].id),'due_at':datetime.now(UTC).isoformat()}]})
    task=next(r for r in get(c,'/community-tasks','admin')['items'] if r['content_id']==row['id'])
    assert task['building_id'] is None
    act(c,f"/community-tasks/{task['id']}/actions",task,'COMPLETE','director',{'evidence_reference':'Synthetic completion'})
    assert act(c,f"/content/{row['id']}/actions",row,'CLOSE','admin')['status']=='CLOSED'


def request(c,cat):
    r=c['client'].post('/api/v1/service-requests',json={'building_id':str(c['building'].id),'category_id':str(cat.id),'title':'Synthetic request','description':'Synthetic request body'},headers={**c['auth']['cskh'],'Idempotency-Key':uuid4().hex});assert r.status_code==201,r.text;return r.json()


@isolated
def test_sla_snapshot_pause_handoff_ack_and_escalation(remaining_case):
    c=remaining_case;cat=category(c)
    definition={'minutes':480,'weekdays':[1,2,3,4,5],'opens_minute':480,'closes_minute':1020,'pause_reasons':['WAITING_CONFIRMED'],'confirmed_reference':'Synthetic BQL policy','handoff_minutes':1}
    policy=create(c,'/sla-policies',{'building_id':str(c['building'].id),'category_id':str(cat.id),'definition':definition})
    assert action(c,f"/sla-policies/{policy['id']}/actions",policy,'PUBLISH').status_code==403
    act(c,f"/sla-policies/{policy['id']}/actions",policy,'PUBLISH','director')
    row=request(c,cat);row=get(c,f"/requests/{row['id']}/control")
    assert row['sla_policy_snapshot']['minutes']==480
    replacement=create(c,'/sla-policies',{'building_id':str(c['building'].id),'category_id':str(cat.id),'definition':{**definition,'minutes':60}})
    act(c,f"/sla-policies/{replacement['id']}/actions",replacement,'PUBLISH','director')
    assert get(c,f"/requests/{row['id']}/control")['sla_policy_snapshot']['minutes']==480
    scoped=c['client'].get('/api/v1/service-requests',params={'building_id':str(uuid4())},headers=c['auth']['cskh']);assert scoped.json()['items']==[]
    assert action(c,f"/requests/{row['id']}/control",row,'PAUSE',data={'pause_reason':'WAITING_INFO'}).status_code==409
    row=act(c,f"/requests/{row['id']}/control",row,'PAUSE',data={'pause_reason':'WAITING_CONFIRMED'})
    row=act(c,f"/requests/{row['id']}/control",row,'RESUME')
    owner=row['owner_account_id'];row=act(c,f"/requests/{row['id']}/control",row,'TRANSFER',data={'owner_id':str(c['director'].id),'department':'Synthetic technical team'})
    assert row['owner_account_id']==owner
    assert action(c,f"/requests/{row['id']}/control",row,'ACK').status_code==403
    cutoff=datetime.now(UTC)+timedelta(minutes=2)
    response=c['client'].post('/api/v1/service-requests/sla/run',json={'as_of':cutoff.isoformat()},headers=c['auth']['admin']);assert response.status_code==200,response.text
    row=get(c,f"/requests/{row['id']}/control");assert row['handoff']['status']=='ESCALATED' and row['owner_account_id']==owner
    row=act(c,f"/requests/{row['id']}/control",row,'ACK','director');assert row['owner_account_id']==str(c['director'].id)
    row=act(c,f"/requests/{row['id']}/control",row,'REPEAT_CAUSE','director');assert get(c,'/service-quality',building_id=str(c['building'].id))['items'][0]['csat_average'] is None
    denied=c['client'].get(f"/api/v1/portal/requests/{row['id']}/control",headers=c['auth']['resident']).status_code
    assert denied in (403,404)


@isolated
def test_jobs_partial_retry_only_failures_and_dedupe_across_schedules(case,monkeypatch):
    c=case
    with c['database'].get_session() as s:
        assets=[Asset(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,code='SYN-'+uuid4().hex[:10],name='Synthetic asset',status='ACTIVE',inspection_due_on=datetime.now(UTC).date(),created_by_id=c['maker'].id,updated_by_id=c['maker'].id) for _ in range(2)];s.add_all(assets);s.commit()
    body={'building_id':str(c['building'].id),'name':'Synthetic inspection reminders','kind':'ASSET_DEADLINE','interval_minutes':5,'next_run_at':(datetime.now(UTC)-timedelta(seconds=1)).isoformat()}
    schedule=create(c,'/control/jobs',body)
    from app.services import business_jobs
    original=business_jobs.perform;attempts=[]
    def fail_one(*args):
        attempts.append(args[-1]['source_id'])
        if args[-1]['source_id']==str(assets[1].id):raise RuntimeError('synthetic only')
        return original(*args)
    monkeypatch.setattr(business_jobs,'perform',fail_one)
    run=act(c,f"/control/jobs/{schedule['id']}/actions",schedule,'RUN');assert run['status']=='PARTIAL' and run['result']['failed']==1
    monkeypatch.setattr(business_jobs,'perform',original)
    with c['database'].get_session() as s:a=s.get(Asset,assets[1].id);a.version+=1;s.commit()
    stale=act(c,f"/control/jobs/{schedule['id']}/actions",schedule,'RETRY')
    assert stale['status']=='PARTIAL' and next(i for i in stale['result']['items'] if i['status']=='FAILED')['error_code']=='ERR-JOB-SOURCE-STALE'
    rebased=act(c,f"/control/job-runs/{stale['id']}/actions",stale,'REBASE_FAILURES')
    retried=act(c,f"/control/job-runs/{rebased['id']}/actions",rebased,'RETRY');assert retried['status']=='SUCCEEDED'
    another=create(c,'/control/jobs',body);run2=act(c,f"/control/jobs/{another['id']}/actions",another,'RUN')
    assert all(item['result']['replayed'] for item in run2['result']['items'])
    with c['database'].get_session() as s:assert s.scalar(select(func.count(JobEffect.id)).where(JobEffect.building_id==c['building'].id))==2


@isolated
def test_maintenance_job_reuses_dispatcher_one_wo(case):
    c=case
    with c['database'].get_session() as s:
        asset=Asset(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,code='SYN-'+uuid4().hex[:10],name='Synthetic asset',status='ACTIVE',created_by_id=c['maker'].id,updated_by_id=c['maker'].id);s.add(asset);s.flush()
        plan=MaintenancePlan(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,asset_id=asset.id,code='SYN-'+uuid4().hex[:10],title='Synthetic plan',interval_days=30,next_due_at=datetime.now(UTC)-timedelta(days=1),checklist_template=[{'label':'Synthetic check','required':True}],evidence_required=True,created_by_id=c['maker'].id,updated_by_id=c['maker'].id);s.add(plan);s.commit()
    body={'building_id':str(c['building'].id),'name':'Synthetic maintenance schedule','kind':'MAINTENANCE','interval_minutes':5,'next_run_at':(datetime.now(UTC)-timedelta(seconds=1)).isoformat()}
    for _ in range(2):
        schedule=create(c,'/control/jobs',body);run=act(c,f"/control/jobs/{schedule['id']}/actions",schedule,'RUN');assert run['status']=='SUCCEEDED',run
    with c['database'].get_session() as s:assert s.scalar(select(func.count(WorkOrder.id)).where(WorkOrder.asset_id==asset.id))==1


@isolated
def test_dataset_applied_not_accepted_hash_guard_and_three_people(case):
    c=case
    with c['database'].get_session() as s:
        batch=ImportRun(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,created_by_id=c['maker'].id,mode='ALL_OR_NOTHING',status='APPLIED',source_filename='synthetic.csv',source_storage_key='synthetic-'+uuid4().hex,source_mime_type='text/csv',source_size_bytes=10,source_sha256='a'*64,total_rows=2,valid_rows=2,applied_rows=2);s.add(batch);s.commit()
    row=create(c,'/init-datasets',{'building_id':str(c['building'].id),'name':'Synthetic dataset','manifest':{'csv_run_ids':[str(batch.id)],'expected_counts':{'csv_rows':2,'units':1}}})
    assert row['status']=='DRAFT';row=act(c,f"/init-datasets/{row['id']}/actions",row,'SUBMIT')
    assert action(c,f"/init-datasets/{row['id']}/actions",row,'CHECK').status_code==403
    row=act(c,f"/init-datasets/{row['id']}/actions",row,'CHECK','director')
    assert action(c,f"/init-datasets/{row['id']}/actions",row,'CONFIRM','director').status_code==403
    row=act(c,f"/init-datasets/{row['id']}/actions",row,'CONFIRM','admin');assert row['status']=='ACCEPTED'
    with c['database'].get_session() as s:b=s.get(ImportRun,batch.id);b.source_sha256='b'*64;b.version+=1;s.commit()
    assert get(c,f"/init-datasets/{row['id']}")['effective_status']=='STALE'
    assert get(c,'/init-datasets')['items'][0]['effective_status']=='STALE'
    assert action(c,f"/init-datasets/{row['id']}/actions",row,'CONFIRM','admin2').status_code==409
    row=act(c,f"/init-datasets/{row['id']}/actions",row,'REFRESH');assert row['status']=='DRAFT' and row['confirmer_id'] is None
    with c['database'].get_session() as s:b=s.get(ImportRun,batch.id);b.status='PREVIEWED';b.version+=1;s.commit()
    row=act(c,f"/init-datasets/{row['id']}/actions",row,'REFRESH');row=act(c,f"/init-datasets/{row['id']}/actions",row,'SUBMIT')
    assert action(c,f"/init-datasets/{row['id']}/actions",row,'CHECK','director').status_code==409


@isolated
def test_report_snapshot_totals_source_change_and_scope_rechecked(case):
    c=case
    with c['database'].get_session() as s:
        fund=TreasuryAccount(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,account_id=c['maker'].id,kind='FUND',code='SYN-'+uuid4().hex[:10],purpose='Synthetic restricted purpose',starts_on=datetime.now(UTC).date(),ends_on=(datetime.now(UTC)+timedelta(days=30)).date(),balance_vnd=123400,status='ACTIVE');s.add(fund);s.commit()
    row=create(c,'/control/reports',{'building_id':str(c['building'].id),'kind':'FINANCIAL','statuses':{'treasury_accounts':['ACTIVE']}},'accountant')
    assert row['metrics']['fund_balance_vnd']['value']==123400 and row['definition_version']=='SAD-1'
    with c['database'].get_session() as s:f=s.get(TreasuryAccount,fund.id);f.balance_vnd=234500;f.version+=1;s.commit()
    live=get(c,f"/control/reports/{row['id']}/sources/treasury_accounts/{fund.id}",'accountant')
    assert live['current_differs'] and live['snapshot']['balance_vnd']==123400 and live['current']['balance_vnd']==234500
    assert get(c,f"/control/reports/{row['id']}",'accountant')['metrics']['fund_balance_vnd']['value']==123400
    download=c['client'].get(f"/api/v1/portal/control/reports/{row['id']}/download",headers=c['auth']['accountant']);assert download.json()['digest']==row['digest']
    denied=c['client'].get(f"/api/v1/portal/control/reports/{row['id']}/sources/treasury_accounts/{fund.id}",headers=c['auth']['resident']).status_code
    assert denied in (403,404)
    assert post(c,'/control/reports',{'building_id':str(c['building'].id),'kind':'FINANCIAL','statuses':{'unknown':['ACTIVE']}},'accountant').status_code==422
    with c['database'].get_session() as s:f=s.get(TreasuryAccount,fund.id);f.balance_vnd=9007199254740993;f.version+=1;s.commit()
    huge=create(c,'/control/reports',{'building_id':str(c['building'].id),'kind':'FINANCIAL','statuses':{'treasury_accounts':['ACTIVE']}},'accountant')
    assert huge['metrics']['fund_balance_vnd']['value']=='9007199254740993'
    assert next(r['data'] for r in huge['rows'] if r['source']=='treasury_accounts')['balance_vnd']=='9007199254740993'
    detail=get(c,f"/control/reports/{huge['id']}/sources/treasury_accounts/{fund.id}",'accountant')
    assert detail['snapshot']['balance_vnd']==detail['current']['balance_vnd']=='9007199254740993' and not detail['current_differs']
