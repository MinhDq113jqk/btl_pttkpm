"""SAD steps 2/3: committed synthetic fixtures, independent actors and DB assertions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
import os
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from app.models.account import Account, AccountRole
from app.models.billing import ArLedgerEntry, BillingInvoice, BillingInvoiceItem, BillingRun, Payment, PaymentAllocation, OverpaymentCredit
from app.models.financial_control import BillingReview, FinanceCommand, AllocationReversal
from app.models.person import Person, UnitPersonRelationship
from app.models.property import LeaseContract, UnitProfileEpisode, PersonMerge
from app.models.resident_portal import PortalDeposit, LiabilityEpisode, PortalDossierEvent, PortalDossier, ResidentDelegation
from auth_test_support import mint_session_token
from test_step1_fee_proration import concurrent_case
from test_portal_workflows import post, action
from test_r4_billing_issue_integration import _policy

pytestmark=pytest.mark.skipif(os.getenv('GREENCITY_ISOLATED_SECURITY_TESTS')!='1',reason='Disposable PostgreSQL required')


@pytest.fixture
def controlled_case(concurrent_case,monkeypatch):
    monkeypatch.setattr('app.services.property.business_date',lambda:date(2026,10,9))
    case=concurrent_case
    with case['database'].get_session() as session:
        maker=session.scalar(select(Account).join(AccountRole,AccountRole.account_id==Account.id).where(
            Account.tenant_id==case['tenant'].id,AccountRole.role=='accountant'))
        owner=session.scalar(select(Person).join(UnitPersonRelationship,UnitPersonRelationship.person_id==Person.id).where(UnitPersonRelationship.unit_id==case['unit'].id))
        payer=Person(tenant_id=case['tenant'].id,full_name='Synthetic lessee',phone_masked='***',email_masked='***')
        checker=Account(tenant_id=case['tenant'].id,username='check_'+uuid4().hex,full_name='Synthetic checker',hashed_password='token-only-test-account')
        session.add_all([payer,checker]);session.flush()
        session.add(AccountRole(account_id=checker.id,site_id=case['site'].id,role='admin',building_id=None));session.commit()
    case['auth']['checker']={'Authorization':'Bearer '+mint_session_token(case['database'],checker.id,case['settings'].auth_secret(),claims={'active_site_id':str(case['site'].id)})}
    return {**case,'owner':owner,'payer':payer,'checker':checker,'maker':maker}


def dossier(case,kind,data,start='2026-09-01',end=None,actor='resident'):
    body={'unit_id':str(case['unit'].id),'kind':kind,'title':'Synthetic '+kind,'data':data,'valid_from':start,'valid_to':end}
    if actor!='resident':body['person_id']=str(case['owner'].id)
    r=post(case,'/dossiers',body,actor);assert r.status_code==201,r.text
    row=r.json()
    proof=case['client'].post('/api/v1/portal/documents',params={'unit_id':str(case['unit'].id),'dossier_id':row['id'],'title':'Synthetic evidence'},content=b'%PDF-1.4\nsynthetic\n%%EOF',headers={**case['auth'][actor],'Idempotency-Key':uuid4().hex,'Content-Type':'application/pdf','X-File-Name':'proof.pdf'})
    assert proof.status_code==201,proof.text
    return row


def approve_dossier(case,row):
    r=action(case,f"/dossiers/{row['id']}/actions",row,'APPROVE','checker');assert r.status_code==200,r.text
    return r.json()


def draft(case,rate=100):
    policy=_policy(case,effective_from='2025-01-01',rate=rate)
    r=case['client'].post('/api/v1/billing/runs',json={'accounting_period_id':str(case['period'].id),'fee_policy_version_id':policy['versions'][0]['id'],'run_key':uuid4().hex},headers={**case['auth']['accountant'],'Idempotency-Key':uuid4().hex})
    assert r.status_code==201,r.text
    assert r.json()['status']=='REVIEW',r.json()
    reviews=case['client'].get('/api/v1/portal/finance/reviews',headers=case['auth']['accountant']).json()['items']
    return next(v for v in reviews if v['billing_run_id']==r.json()['id'])


def next_action(case,resource,row,verb,actor='accountant',data=None,key=None):
    r=action(case,f"/finance/{resource}/{row['id']}/actions",row,verb,actor,data,key)
    assert r.status_code==200,r.text
    return r.json()


def issue(case,row):
    row=next_action(case,'reviews',row,'SUBMIT')
    row=next_action(case,'reviews',row,'APPROVE','checker')
    return next_action(case,'reviews',row,'ISSUE')


def finance(case,kind,target,amount=0,data=None,period=None):
    body={'kind':kind,'target_id':str(target),'period_id':str(period or case['period'].id),'amount_vnd':amount,'reason':'Synthetic decision','evidence_reference':'SYN-PROOF','data':data or {}}
    preview=post(case,'/finance/commands/preview',body,'accountant');assert preview.status_code==200,preview.text
    r=post(case,'/finance/commands',{**body,'expected_hash':preview.json()['calculation_hash']},'accountant');assert r.status_code==201,r.text
    return r.json()


def execute(case,row):
    row=next_action(case,'commands',row,'SUBMIT')
    row=next_action(case,'commands',row,'APPROVE','checker')
    return next_action(case,'commands',row,'EXECUTE',data={'execution_reference':'SYN-'+row['id']})


def payment(case,amount):
    r=case['client'].post('/api/v1/billing/payments',json={'billing_account_id':str(case['billing_account'].id),'accounting_period_id':str(case['period'].id),'payment_source':'BANK_TRANSFER','source_reference':uuid4().hex,'receipt_number':uuid4().hex,'amount_vnd':amount,'received_at':'2026-09-15T00:00:00Z'},headers={**case['auth']['accountant'],'Idempotency-Key':uuid4().hex})
    assert r.status_code==201,r.text
    return r.json()


def test_lease_revisions_do_not_change_residence_or_liability(controlled_case):
    c=controlled_case
    row=dossier(c,'LEASE',{'target_person_id':str(c['payer'].id),'contract_reference':'SYN-LEASE'},end='2026-10-01')
    approve_dossier(c,row)
    with c['database'].get_session() as s:
        contract=s.scalar(select(LeaseContract).where(LeaseContract.unit_id==c['unit'].id))
        assert s.scalar(select(func.count()).select_from(UnitPersonRelationship).where(UnitPersonRelationship.unit_id==c['unit'].id))==1
        assert not s.scalar(select(LiabilityEpisode.id).where(LiabilityEpisode.unit_id==c['unit'].id))
    amend=dossier(c,'LEASE_AMEND',{'lease_id':str(contract.id),'contract_reference':'SYN-ANNEX','terms':{'rent':'synthetic'}},start='2026-09-15',end='2026-10-01')
    approve_dossier(c,amend)
    with c['database'].get_session() as s:
        contracts=s.scalars(select(LeaseContract).where(LeaseContract.unit_id==c['unit'].id).order_by(LeaseContract.valid_from)).all()
        assert contracts[0].valid_to==date(2026,10,1) and contracts[0].status=='SUPERSEDED'
        assert contracts[1].previous_id==contract.id
    renew=dossier(c,'LEASE_RENEW',{'lease_id':str(contracts[1].id),'contract_reference':'SYN-RENEW'},start='2026-10-01',end='2027-01-01')
    approve_dossier(c,renew)
    with c['database'].get_session() as s:
        last=s.scalar(select(LeaseContract).where(LeaseContract.unit_id==c['unit'].id,LeaseContract.status=='ACTIVE'))
    end=dossier(c,'LEASE_TERMINATE',{'lease_id':str(last.id),'evidence_reference':'SYN-END'},start='2026-12-01')
    approve_dossier(c,end)
    with c['database'].get_session() as s:
        assert s.get(LeaseContract,last.id).terminated_on==date(2026,12,1)
        assert s.scalar(select(func.count()).select_from(UnitPersonRelationship).where(UnitPersonRelationship.unit_id==c['unit'].id))==1


def test_profile_and_liability_effective_dates_freeze_invoice(controlled_case):
    c=controlled_case
    approve_dossier(c,dossier(c,'UNIT_PROFILE',{'area_m2':'80.25','net_area_m2':'75.00','evidence_reference':'SYN-AREA'},start='2026-09-16'))
    approve_dossier(c,dossier(c,'LIABILITY_CHANGE',{'liable_person_id':str(c['owner'].id),'evidence_reference':'SYN-OWNER'},start='2025-01-01'))
    approve_dossier(c,dossier(c,'LIABILITY_CHANGE',{'liable_person_id':str(c['payer'].id),'evidence_reference':'SYN-PAYER'},start='2026-09-16'))
    row=draft(c,rate=10000)
    assert row['snapshot']['invoices'][0]['total_vnd']==651250
    assert len(row['snapshot']['invoices'][0]['responsibility']['episodes'])==2
    issued=issue(c,row)
    with c['database'].get_session() as s:
        invoice=s.get(BillingInvoice,UUID(issued['issued_invoice_ids'][0]))
        assert invoice.responsibility_snapshot['episodes'][1]['person_id']==str(c['payer'].id)
        with pytest.raises(DBAPIError),s.begin_nested():
            s.execute(text("UPDATE greencity.billing_invoices SET responsibility_snapshot='{}' WHERE id=:id"),{'id':invoice.id})
    old=dossier(c,'UNIT_PROFILE',{'area_m2':'90','evidence_reference':'SYN-AREA'},start='2026-09-20')
    assert action(c,f"/dossiers/{old['id']}/actions",old,'APPROVE','checker').status_code==409


def test_draft_no_debt_checker_staleness_and_atomic_issue(controlled_case):
    c=controlled_case;row=draft(c)
    with c['database'].get_session() as s:
        assert not s.scalar(select(BillingInvoice.id).where(BillingInvoice.billing_account_id==c['billing_account'].id))
        assert not s.scalar(select(ArLedgerEntry.id).where(ArLedgerEntry.billing_account_id==c['billing_account'].id))
    row=next_action(c,'reviews',row,'SUBMIT')
    assert action(c,f"/finance/reviews/{row['id']}/actions",row,'APPROVE','accountant').status_code==403
    row=next_action(c,'reviews',row,'APPROVE','checker')
    with c['database'].get_session() as s:
        unit=s.get(__import__('app.models.unit',fromlist=['Unit']).Unit,c['unit'].id);unit.area_m2=51;unit.version+=1;s.commit()
    assert action(c,f"/finance/reviews/{row['id']}/actions",row,'ISSUE','accountant').status_code==409
    row=next_action(c,'reviews',row,'REFRESH')
    row=next_action(c,'reviews',row,'SUBMIT');row=next_action(c,'reviews',row,'APPROVE','checker')
    key=uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: action(c,f"/finance/reviews/{row['id']}/actions",row,'ISSUE','accountant',key=key),range(2)))
    assert [r.status_code for r in results]==[200,200]
    assert results[0].json()['issued_invoice_ids']==results[1].json()['issued_invoice_ids']
    with c['database'].get_session() as s:
        assert s.scalar(select(func.count()).select_from(BillingInvoice).where(BillingInvoice.billing_account_id==c['billing_account'].id))==1


def test_deposit_decision_then_execution_and_replay(controlled_case):
    c=controlled_case
    with c['database'].get_session() as s:
        deposit=PortalDeposit(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,unit_id=c['unit'].id,account_id=c['checker'].id,source_kind='RENOVATION',source_id=uuid4(),required_vnd=1000,balance_vnd=1000,refundable_vnd=0,status='HELD')
        s.add(deposit);s.commit()
    assert post(c,f'/deposits/{deposit.id}/actions',{'action':'RELEASE','amount_vnd':300,'reference':'SYN-RELEASE','reason':'Synthetic','expected_version':1},'accountant').status_code==409
    row=finance(c,'DEPOSIT_RELEASE',deposit.id,400)
    row=next_action(c,'commands',row,'SUBMIT');row=next_action(c,'commands',row,'APPROVE','checker')
    with c['database'].get_session() as s:assert s.get(PortalDeposit,deposit.id).refundable_vnd==0
    row=next_action(c,'commands',row,'EXECUTE',data={'execution_reference':'SYN-REL'})
    refund=finance(c,'DEPOSIT_REFUND',deposit.id,400);execute(c,refund)
    with c['database'].get_session() as s:
        d=s.get(PortalDeposit,deposit.id);assert (d.balance_vnd,d.refundable_vnd)==(600,0)


def test_allocation_reversal_preserves_original_and_ledger(controlled_case):
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0]
    p=payment(c,5000)
    row=finance(c,'ALLOCATE',p['id'],data={'allocations':[{'invoice_id':invoice_id,'amount_vnd':5000}]})
    execute(c,row)
    reversal=finance(c,'PAYMENT_REVERSE',p['id']);execute(c,reversal)
    with c['database'].get_session() as s:
        assert s.get(Payment,UUID(p['id'])).status=='REVERSED'
        invoice=s.get(BillingInvoice,UUID(invoice_id));assert invoice.outstanding_vnd==invoice.total_vnd
        assert len(s.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id==UUID(p['id']))).all())==1
        assert s.scalar(select(AllocationReversal.id).join(PaymentAllocation,PaymentAllocation.id==AllocationReversal.allocation_id).where(PaymentAllocation.payment_id==UUID(p['id'])))
        assert s.scalar(select(func.sum(ArLedgerEntry.debit_vnd-ArLedgerEntry.credit_vnd)).where(ArLedgerEntry.billing_account_id==c['billing_account'].id))==invoice.total_vnd
    p2=payment(c,5000)
    execute(c,finance(c,'ALLOCATE',p2['id'],data={'allocations':[{'invoice_id':invoice_id,'amount_vnd':5000}]}))


def test_dispute_does_not_reduce_debt_and_reminder_policy(controlled_case):
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0]
    body={'invoice_id':invoice_id,'kind':'DISPUTE','amount_vnd':1000,'reason':'Synthetic dispute'}
    r=post(c,'/finance/ar',body);assert r.status_code==201,r.text
    reminder={'invoice_id':invoice_id,'kind':'REMINDER','amount_vnd':5000,'reason':'Synthetic reminder','include_disputed':False}
    assert post(c,'/finance/ar',reminder,'accountant').status_code==409
    reminder['amount_vnd']=4000
    assert post(c,'/finance/ar',reminder,'accountant').status_code==201
    ar=c['client'].get('/api/v1/portal/finance/ar',params={'unit_id':str(c['unit'].id)},headers=c['auth']['resident']).json()
    assert ar['items'][0]['outstanding_vnd']==5000 and ar['items'][0]['disputed_vnd']==1000
    assert c['client'].get('/api/v1/portal/finance/commands',headers=c['auth']['resident']).status_code==403


def test_scoped_reopen_preserves_lock_and_reports_delta(controlled_case):
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0]
    for status in ['CLOSING','CLOSED']:
        with c['database'].get_session() as s:p=s.get(__import__('app.models.billing',fromlist=['AccountingPeriod']).AccountingPeriod,c['period'].id)
        r=c['client'].post(f'/api/v1/billing/periods/{p.id}/transition',json={'status':status,'expected_version':p.version},headers=c['auth']['accountant']);assert r.status_code==200,r.text
    execute(c,finance(c,'PERIOD_LOCK',c['period'].id))
    assert post(c,'/finance/commands',{'kind':'CREDIT','period_id':str(c['period'].id),'target_id':invoice_id,'amount_vnd':100,'reason':'Synthetic','evidence_reference':'SYN'},'accountant').status_code==409
    grant=finance(c,'PERIOD_REOPEN',c['period'].id,data={'expires_at':(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'allowed_kinds':['CREDIT'],'target_ids':[invoice_id]})
    execute(c,grant);execute(c,finance(c,'CREDIT',invoice_id,100))
    with c['database'].get_session() as s:
        assert s.get(__import__('app.models.billing',fromlist=['AccountingPeriod']).AccountingPeriod,c['period'].id).status=='LOCKED'
    delta=c['client'].get(f"/api/v1/portal/finance/periods/{c['period'].id}/delta",headers=c['auth']['accountant']).json()
    assert delta['items'][0]['delta_balance_vnd']==-100


def test_merge_keeps_original_ids_and_owner_access(controlled_case):
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0]
    original_owner=c['owner'].id
    row=dossier(c,'PERSON_MERGE',{'source_person_id':str(original_owner),'target_person_id':str(c['payer'].id),'evidence_reference':'SYN-VERIFIED-DUPLICATE'},actor='accountant')
    assert action(c,f"/dossiers/{row['id']}/actions",row,'APPROVE','accountant').status_code==409
    approve_dossier(c,row)
    with c['database'].get_session() as s:
        assert s.get(Person,original_owner)
        assert s.scalar(select(UnitPersonRelationship.person_id).where(UnitPersonRelationship.unit_id==c['unit'].id))==original_owner
        assert s.get(BillingInvoice,UUID(invoice_id)).responsibility_snapshot['episodes'][0]['person_id']==str(original_owner)
    profile=c['client'].get('/api/v1/portal/profile',headers=c['auth']['resident'])
    assert profile.status_code==200,profile.text
    assert profile.json()['person']['id']==str(c['payer'].id)
    assert profile.json()['relationships'][0]['relationship_type']=='owner'
    assert post(c,'/dossiers',{'unit_id':str(c['unit'].id),'kind':'LEASE','title':'Synthetic after merge','valid_from':'2026-10-01','valid_to':'2027-01-01','data':{'target_person_id':str(original_owner),'contract_reference':'SYN-MERGED'}}).status_code==201


def test_handover_and_renovation_have_real_state_history(controlled_case):
    c=controlled_case
    bad=post(c,'/dossiers',{'unit_id':str(c['unit'].id),'person_id':str(c['owner'].id),'kind':'HANDOVER','title':'Synthetic handover','valid_from':'2026-09-01',
        'data':{'reference':'SYN-HO','checklist':['keys','meter'],'accepted_items':['keys'],'evidence_reference':'SYN-PROOF'}},'accountant')
    assert bad.status_code==422
    handover=dossier(c,'HANDOVER',{'reference':'SYN-HO','checklist':['keys'],'accepted_items':['keys'],'defects':[],'evidence_reference':'SYN-PROOF'},actor='accountant')
    approve_dossier(c,handover)
    row=dossier(c,'RENOVATION',{'description':'Synthetic works','contractor':'Synthetic company'},start='2026-10-01',end='2026-10-20')
    r=action(c,f"/dossiers/{row['id']}/deposit",row,'SET','accountant',{'required_vnd':0});assert r.status_code==200,r.text
    approved=approve_dossier(c,row)
    started=action(c,f"/dossiers/{row['id']}/actions",approved,'START','checker');assert started.status_code==200,started.text
    with c['database'].get_session() as s:
        from app.models.unit import Unit
        assert s.get(Unit,c['unit'].id).status=='UNDER_RENOVATION'
    finished=action(c,f"/dossiers/{row['id']}/actions",started.json(),'COMPLETE','checker');assert finished.status_code==200,finished.text
    with c['database'].get_session() as s:
        from app.models.unit import Unit
        assert s.get(Unit,c['unit'].id).status=='HANDED_OVER'
        assert s.scalar(select(PortalDossierEvent.id).where(PortalDossierEvent.dossier_id==UUID(row['id']),PortalDossierEvent.action=='START'))


def test_future_profile_worker_and_floor_unit_hierarchy(controlled_case,monkeypatch):
    c=controlled_case
    approve_dossier(c,dossier(c,'UNIT_PROFILE',{'area_m2':'75','evidence_reference':'SYN-AREA'},start='2026-10-10'))
    from app.models.unit import Unit
    with c['database'].get_session() as s:assert s.get(Unit,c['unit'].id).area_m2==50
    monkeypatch.setattr('app.services.property.business_date',lambda:date(2026,10,10))
    monkeypatch.setattr('app.services.portal_finance.business_date',lambda:date(2026,10,10))
    assert post(c,'/jobs/tick',{},'accountant').status_code==200
    with c['database'].get_session() as s:assert s.get(Unit,c['unit'].id).area_m2==75
    from test_steps4_5 import create, approve, record
    zone = create(c, '/property/nodes', {'kind': 'ZONE', 'code': 'SYN-ZONE', 'name': 'Synthetic zone', 'data': {}})
    approve(c, record(c, 'BUILDING_ZONE', {'zone_id': zone['id'], 'evidence_reference': 'SYN-ZONE-LINK'}))
    floor=post(c,'/property/nodes',{'kind':'FLOOR','code':'SYN-FLOOR','name':'Synthetic floor','building_id':str(c['building'].id),'parent_id':zone['id'],'data':{'floor_number':3}},'accountant')
    assert floor.status_code==200 or floor.status_code==201,floor.text
    new=post(c,'/property/units',{'floor_node_id':floor.json()['id'],'unit_number':'0301','area_m2':30},'accountant')
    assert new.status_code==201,new.text
    foreign=c['client'].get(f"/api/v1/portal/property/units/{new.json()['id']}/history",headers=c['auth']['resident']);assert foreign.status_code==404
    assert action(c,f"/property/nodes/{floor.json()['id']}/actions",floor.json(),'DEACTIVATE','accountant').status_code==409


def test_expired_approval_delegation_blocks_issue(controlled_case):
    c=controlled_case
    policy=post(c,'/finance/policies',{'code':'BILLING','purpose':'Synthetic director approval','approval_roles':['director'],'max_amount_vnd':10000},'accountant')
    assert policy.status_code==201,policy.text
    delegation=post(c,'/finance/delegations',{'delegate_account_id':str(c['checker'].id),'building_id':str(c['building'].id),'purpose':'BILLING',
        'valid_from':(datetime.now(UTC)-timedelta(hours=1)).isoformat(),'valid_to':(datetime.now(UTC)+timedelta(hours=1)).isoformat(),'reason':'Synthetic temporary approval'},'accountant')
    assert delegation.status_code==201,delegation.text
    row=next_action(c,'reviews',draft(c),'SUBMIT')
    row=next_action(c,'reviews',row,'APPROVE','checker')
    revoked=action(c,f"/finance/delegations/{delegation.json()['id']}/actions",delegation.json(),'REVOKE','accountant');assert revoked.status_code==200,revoked.text
    assert action(c,f"/finance/reviews/{row['id']}/actions",row,'ISSUE','accountant').status_code==403


def test_overpayment_credit_use_and_refund_reconciliation(controlled_case):
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0]
    p=payment(c,7000)
    # Existing automatic allocation creates a traceable overpayment source.
    r=c['client'].post(f"/api/v1/billing/payments/{p['id']}/allocate",headers={**c['auth']['accountant'],'Idempotency-Key':uuid4().hex});assert r.status_code==200,r.text
    credit=r.json()['overpayment_credit'];assert credit['remaining_vnd']==2000
    refund=finance(c,'PAYMENT_REFUND',p['id'],1000)
    refund=next_action(c,'commands',refund,'SUBMIT');refund=next_action(c,'commands',refund,'APPROVE','checker')
    refund=next_action(c,'commands',refund,'MARK_UNCERTAIN')
    with c['database'].get_session() as s:assert s.get(OverpaymentCredit,UUID(credit['id'])).remaining_vnd==2000
    refund=next_action(c,'commands',refund,'CONFIRM_EXECUTION',data={'execution_reference':'SYN-REFUND'})
    with c['database'].get_session() as s:
        assert s.get(OverpaymentCredit,UUID(credit['id'])).remaining_vnd==1000
        assert s.get(BillingInvoice,UUID(invoice_id)).outstanding_vnd==0
    body={'kind':'PAYMENT_REVERSE','target_id':p['id'],'period_id':str(c['period'].id),'reason':'Synthetic reversal','evidence_reference':'SYN'}
    assert post(c,'/finance/commands',body,'accountant').status_code==409


def test_partial_allocation_credit_use_same_invoice_and_reversal(controlled_case):
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0]
    p=payment(c,7000)
    execute(c,finance(c,'ALLOCATE',p['id'],data={'allocations':[{'invoice_id':invoice_id,'amount_vnd':3000}]}))
    with c['database'].get_session() as s:
        credit=s.scalar(select(OverpaymentCredit).where(OverpaymentCredit.payment_id==UUID(p['id'])))
        assert credit.remaining_vnd==4000
    execute(c,finance(c,'CREDIT_USE',credit.id,data={'allocations':[{'invoice_id':invoice_id,'amount_vnd':2000}]}))
    with c['database'].get_session() as s:
        assert s.get(BillingInvoice,UUID(invoice_id)).outstanding_vnd==0
        assert s.scalar(select(func.sum(ArLedgerEntry.debit_vnd-ArLedgerEntry.credit_vnd)).where(ArLedgerEntry.billing_account_id==c['billing_account'].id))==0
    execute(c,finance(c,'PAYMENT_REVERSE',p['id']))
    with c['database'].get_session() as s:
        assert s.get(BillingInvoice,UUID(invoice_id)).outstanding_vnd==5000
        assert s.scalar(select(func.sum(ArLedgerEntry.debit_vnd-ArLedgerEntry.credit_vnd)).where(ArLedgerEntry.billing_account_id==c['billing_account'].id))==5000
    p2=payment(c,5000)
    execute(c,finance(c,'ALLOCATE',p2['id'],data={'allocations':[{'invoice_id':invoice_id,'amount_vnd':5000}]}))


def test_refund_reservation_blocks_competing_use_and_allows_remaining_after_execution(controlled_case):
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0];p=payment(c,7000)
    execute(c,finance(c,'ALLOCATE',p['id'],data={'allocations':[{'invoice_id':invoice_id,'amount_vnd':3000}]}))
    with c['database'].get_session() as s:credit=s.scalar(select(OverpaymentCredit).where(OverpaymentCredit.payment_id==UUID(p['id'])))
    refund=finance(c,'PAYMENT_REFUND',p['id'],1000)
    refund=next_action(c,'commands',refund,'SUBMIT');refund=next_action(c,'commands',refund,'APPROVE','checker')
    use={'kind':'CREDIT_USE','target_id':str(credit.id),'period_id':str(c['period'].id),'reason':'Synthetic use',
        'evidence_reference':'SYN','data':{'allocations':[{'invoice_id':invoice_id,'amount_vnd':2000}]}}
    assert post(c,'/finance/commands',use,'accountant').status_code==409
    refund=next_action(c,'commands',refund,'MARK_UNCERTAIN')
    assert post(c,'/finance/commands',use,'accountant').status_code==409
    next_action(c,'commands',refund,'CONFIRM_EXECUTION',data={'execution_reference':'SYN-CASH-REFUND'})
    execute(c,finance(c,'CREDIT_USE',credit.id,data=use['data']))
    with c['database'].get_session() as s:assert s.get(OverpaymentCredit,credit.id).remaining_vnd==1000


def test_provider_refund_and_manual_commands_cannot_consume_same_source(controlled_case):
    from app.models.resident_portal import PortalFinancialAdjustment,PortalPaymentIntent
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0];p=payment(c,7000)
    execute(c,finance(c,'ALLOCATE',p['id'],data={'allocations':[{'invoice_id':invoice_id,'amount_vnd':5000}]}))
    with c['database'].get_session() as s:
        scope={'tenant_id':c['tenant'].id,'site_id':c['site'].id,'building_id':c['building'].id,'unit_id':c['unit'].id,'account_id':c['maker'].id}
        intent=PortalPaymentIntent(**scope,invoice_id=UUID(invoice_id),reference='SYN-'+uuid4().hex,
            amount_vnd=7000,status='PAID',expires_at=datetime.now(UTC)+timedelta(hours=1),payment_id=UUID(p['id']),provider_amount_vnd=7000)
        s.add(intent);s.flush()
        prior=PortalFinancialAdjustment(**scope,kind='REFUND',invoice_id=UUID(invoice_id),payment_intent_id=intent.id,
            period_id=c['period'].id,amount_vnd=1000,reason='Synthetic reserved provider refund',status='RECONCILIATION',
            requested_by_id=c['maker'].id,approved_by_id=c['checker'].id)
        s.add(prior);s.commit()
    for kind,amount in [('PAYMENT_REFUND',1000),('PAYMENT_REVERSE',0)]:
        r=post(c,'/finance/commands',{'kind':kind,'target_id':p['id'],'period_id':str(c['period'].id),
            'amount_vnd':amount,'reason':'Synthetic competing command','evidence_reference':'SYN'},'accountant')
        assert r.status_code==409 and r.json()['error']['code']=='ERR-PAYMENT-RESERVED',r.text
    with c['database'].get_session() as s:
        prior=s.get(PortalFinancialAdjustment,prior.id);prior.status='REJECTED';prior.provider_status='09';s.commit()
    execute(c,finance(c,'PAYMENT_REFUND',p['id'],1000))
    r=post(c,'/adjustments',{'unit_id':str(c['unit'].id),'kind':'REFUND','invoice_id':invoice_id,
        'payment_intent_id':str(intent.id),'amount_vnd':1000,'reason':'Synthetic duplicate refund'},'accountant')
    assert r.status_code==409 and r.json()['error']['code']=='ERR-PAYMENT-RESERVED',r.text


def test_controlled_void_and_invalid_policy_supplement(controlled_case):
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0]
    row=finance(c,'INVOICE_VOID',invoice_id)
    assert row['amount_vnd']==5000
    execute(c,row)
    with c['database'].get_session() as s:
        invoice=s.get(BillingInvoice,UUID(invoice_id))
        assert invoice.status=='VOID' and invoice.total_vnd==5000 and invoice.outstanding_vnd==0
        assert s.scalar(select(func.sum(ArLedgerEntry.debit_vnd-ArLedgerEntry.credit_vnd)).where(ArLedgerEntry.billing_account_id==c['billing_account'].id))==0
    policy=post(c,'/finance/policies',{'code':'CREDIT','purpose':'Synthetic approval','approval_roles':['admin'],'max_amount_vnd':10000},'accountant')
    assert policy.status_code==201,policy.text
    r=action(c,f"/finance/policies/{policy.json()['id']}/actions",policy.json(),'UPDATE','accountant',{'approval_roles':[]})
    assert r.status_code==422,r.text


def test_renovation_operation_restrictions_are_manager_decisions(controlled_case,monkeypatch):
    c=controlled_case
    monkeypatch.setattr('app.services.portal_finance.business_date',lambda:date.today())
    from test_portal_workflows import resource
    service=resource(c,'SERVICE')
    pending=post(c,'/enrollments',{'unit_id':str(c['unit'].id),'resource_id':service['id']},'resident')
    assert pending.status_code==201,pending.text
    row=dossier(c,'RENOVATION',{'description':'Synthetic works','contractor':'Synthetic company'},start='2026-10-01',end='2026-10-20')
    r=action(c,f"/dossiers/{row['id']}/deposit",row,'SET','accountant',{'required_vnd':0});assert r.status_code==200,r.text
    row=approve_dossier(c,row)
    r=action(c,f"/dossiers/{row['id']}/actions",row,'START','checker',{'allowed_operations':['LEASE']});assert r.status_code==200,r.text
    blocked=action(c,f"/enrollments/{pending.json()['id']}/actions",pending.json(),'APPROVE','accountant',{'effective_on':date.today().isoformat()})
    assert blocked.status_code==409 and blocked.json()['error']['code']=='ERR-RENOVATION-RESTRICTED',blocked.text
    assert post(c,'/dossiers',{'unit_id':str(c['unit'].id),'kind':'MOVE_IN','title':'Synthetic blocked move',
        'valid_from':'2026-10-10','data':{'target_person_id':str(c['payer'].id)}},'resident').status_code==409
    allowed=dossier(c,'LEASE',{'target_person_id':str(c['payer'].id),'contract_reference':'SYN-ALLOWED'},end='2026-11-01')
    approve_dossier(c,allowed)


def test_allocation_approval_limit_uses_derived_amount_and_rejects_boolean_money(controlled_case):
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0];p=payment(c,5000)
    policy=post(c,'/finance/policies',{'code':'ALLOCATE','purpose':'Synthetic threshold','approval_roles':['admin'],'max_amount_vnd':4999},'accountant')
    assert policy.status_code==201,policy.text
    row=finance(c,'ALLOCATE',p['id'],data={'allocations':[{'invoice_id':invoice_id,'amount_vnd':5000}]})
    assert row['amount_vnd']==5000
    row=next_action(c,'commands',row,'SUBMIT')
    denied=action(c,f"/finance/commands/{row['id']}/actions",row,'APPROVE','checker')
    assert denied.status_code==409 and denied.json()['error']['code']=='ERR-APPROVAL-LIMIT',denied.text
    invalid=post(c,'/finance/commands',{'kind':'CREDIT','target_id':invoice_id,'period_id':str(c['period'].id),
        'amount_vnd':True,'reason':'Synthetic bad money','evidence_reference':'SYN'},'accountant')
    assert invalid.status_code==422,invalid.text


def test_account_suspend_resume_and_close_require_settled_balance(controlled_case):
    c=controlled_case;invoice_id=issue(c,draft(c))['issued_invoice_ids'][0]
    from app.services.portal_finance import business_date
    data={'effective_on':str(business_date())}
    body={'kind':'ACCOUNT_CLOSE','target_id':str(c['billing_account'].id),'period_id':str(c['period'].id),
        'reason':'Synthetic close','evidence_reference':'SYN','data':data}
    assert post(c,'/finance/commands',body,'accountant').json()['error']['code']=='ERR-ACCOUNT-BALANCE'
    execute(c,finance(c,'ACCOUNT_SUSPEND',c['billing_account'].id,data=data))
    with c['database'].get_session() as s:
        from app.models.billing import BillingAccount
        assert s.get(BillingAccount,c['billing_account'].id).status=='SUSPENDED'
    execute(c,finance(c,'ACCOUNT_RESUME',c['billing_account'].id,data=data))
    p=payment(c,5000);execute(c,finance(c,'ALLOCATE',p['id'],data={'allocations':[{'invoice_id':invoice_id,'amount_vnd':5000}]}))
    execute(c,finance(c,'ACCOUNT_CLOSE',c['billing_account'].id,data=data))
    with c['database'].get_session() as s:assert s.get(BillingAccount,c['billing_account'].id).status=='CLOSED'


def test_delegation_context_filters_grantors_and_preserves_merged_ownership(controlled_case, monkeypatch):
    from app.core.policy import context_for_account
    from app.services.property import person_family

    c = controlled_case
    today = date.today()
    scope = dict(tenant_id=c['tenant'].id, site_id=c['site'].id,
                 building_id=c['building'].id, unit_id=c['unit'].id)
    with c['database'].get_session() as session:
        owner_account = session.scalar(select(Account).where(Account.person_id == c['owner'].id))
        people = [Person(tenant_id=c['tenant'].id, full_name='Synthetic identity ' + str(i),
                         phone_masked='***', email_masked='***') for i in range(9)]
        session.add_all(people); session.flush()
        delegate = Account(tenant_id=c['tenant'].id, person_id=people[0].id,
                           username='delegate_' + uuid4().hex, full_name='Synthetic delegate',
                           hashed_password='token-only-test-account')
        others = [Account(tenant_id=c['tenant'].id, person_id=person.id,
                          username='grantor_' + uuid4().hex, full_name='Synthetic grantor',
                          hashed_password='token-only-test-account') for person in people[3:]]
        session.add_all([delegate, *others]); session.flush()
        session.add(AccountRole(account_id=delegate.id, role='resident', site_id=c['site'].id,
                                building_id=c['building'].id))

        def record(grantor, recipient, permissions, **changes):
            dossier = PortalDossier(**scope, account_id=grantor.id, person_id=grantor.person_id,
                                    kind='DELEGATION', title='Synthetic authority', data={},
                                    valid_from=today - timedelta(days=10), status='APPROVED')
            session.add(dossier); session.flush()
            values = dict(delegate_person_id=recipient.id, permissions=permissions,
                          valid_from=today - timedelta(days=5), valid_to=today + timedelta(days=5))
            values.update(changes)
            delegation = ResidentDelegation(**scope, account_id=grantor.id,
                                           dossier_id=dossier.id, **values)
            session.add(delegation)
            return dossier

        proof = record(owner_account, people[1], ['requests'])
        session.add_all([
            PersonMerge(**scope, account_id=owner_account.id, dossier_id=proof.id,
                        source_person_id=people[1].id, target_person_id=people[0].id,
                        evidence_reference='SYN-DELEGATE-MERGE'),
            PersonMerge(**scope, account_id=owner_account.id, dossier_id=proof.id,
                        source_person_id=c['owner'].id, target_person_id=people[2].id,
                        evidence_reference='SYN-OWNER-MERGE'),
        ])
        owner_account.person_id = people[2].id
        record(others[0], people[1], ['finance'])  # Not an owner: cannot borrow the real owner's identity.
        record(others[1], people[1], ['finance'], valid_to=today)
        record(others[2], people[1], ['finance'], revoked_at=datetime.now(UTC))
        record(others[3], people[8], ['finance'])  # Recipient is another resident.
        record(others[4], people[1], ['finance']); others[4].is_active = False
        record(others[5], people[1], ['finance'], valid_from=today + timedelta(days=1))
        session.commit()
        consulted = []

        def tracked_family(db_session, tenant_id, person_id):
            consulted.append(person_id)
            return person_family(db_session, tenant_id, person_id)

        monkeypatch.setattr('app.services.property.person_family', tracked_family)
        context = context_for_account(session, delegate, c['site'].id)
        assert set(context.resident_delegations) == {(c['unit'].id, ('requests',))}
        assert set(consulted) == {delegate.person_id, owner_account.person_id, others[0].person_id}
        assert set(context.resident_delegation_grantors) == {(c['unit'].id, owner_account.id, ('requests',))}

        ownership = session.scalar(select(UnitPersonRelationship).where(
            UnitPersonRelationship.unit_id == c['unit'].id,
            UnitPersonRelationship.person_id == c['owner'].id))
        ownership.valid_to = today; session.flush()
        assert context_for_account(session, delegate, c['site'].id).resident_delegations == ()
        ownership.valid_to = None; owner_account.is_active = False; session.flush()
        consulted.clear()
        assert context_for_account(session, delegate, c['site'].id).resident_delegations == ()
        assert owner_account.person_id not in consulted
