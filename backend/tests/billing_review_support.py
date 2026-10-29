"""Regression setup follows the public maker/checker workflow, never a product bypass."""
from uuid import uuid4
import httpx
from app.models.account import Account, AccountRole
from auth_test_support import mint_session_token


def checker_headers(case):
    if 'director' in case['auth']:return case['auth']['director']
    if 'billing_checker' not in case['auth']:
        site=case.get('site') or case['sites'][0]
        with case['database'].get_session() as s:
            actor=Account(tenant_id=case['tenant'].id,username='regression_checker_'+uuid4().hex,
                full_name='Synthetic independent checker',hashed_password='token-only-test-account')
            s.add(actor);s.flush();s.add(AccountRole(account_id=actor.id,site_id=site.id,role='admin',building_id=None));s.commit()
        case['auth']['billing_checker']={'Authorization':'Bearer '+mint_session_token(case['database'],actor.id,
            case['settings'].auth_secret(),claims={'active_site_id':str(site.id)})}
    return case['auth']['billing_checker']


def finish_review(case,row,maker='accountant'):
    for verb,headers in [('SUBMIT',case['auth'][maker]),('APPROVE',checker_headers(case)),('ISSUE',case['auth'][maker])]:
        r=case['client'].post(f"/api/v1/portal/finance/reviews/{row['id']}/actions",json={
            'action':verb,'reason':'Synthetic regression workflow','expected_version':row['version'],'data':{}},
            headers={**headers,'Idempotency-Key':uuid4().hex})
        assert r.status_code==200,r.text
        row=r.json()
    return row


def finish_run(case,response):
    if response.status_code not in (200,201) or response.json()['status']!='REVIEW':return response
    rows=case['client'].get('/api/v1/portal/finance/reviews',headers=case['auth']['accountant']).json()['items']
    review=next(r for r in rows if r['billing_run_id']==response.json()['id'])
    finish_review(case,review)
    runs=case['client'].get('/api/v1/billing/runs',headers=case['auth']['accountant']).json()['items']
    result=next(r for r in runs if r['id']==response.json()['id'])
    return httpx.Response(response.status_code,json=result)


def finish_command(case,body,maker='accountant'):
    r=case['client'].post('/api/v1/portal/finance/commands',json=body,
        headers={**case['auth'][maker],'Idempotency-Key':uuid4().hex})
    assert r.status_code==201,r.text
    row=r.json()
    for verb,headers in [('SUBMIT',case['auth'][maker]),('APPROVE',checker_headers(case)),('EXECUTE',case['auth'][maker])]:
        r=case['client'].post(f"/api/v1/portal/finance/commands/{row['id']}/actions",json={
            'action':verb,'reason':'Synthetic regression decision','expected_version':row['version'],
            'data':{'execution_reference':'SYN-'+row['id']} if verb=='EXECUTE' else {}},
            headers={**headers,'Idempotency-Key':uuid4().hex})
        assert r.status_code==200,r.text
        row=r.json()
    return row
