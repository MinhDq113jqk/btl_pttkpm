"""Remaining SAD business workflows on disposable PostgreSQL, no external traffic."""
import os
from datetime import date, datetime, UTC, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from app.models.operational_control import OperationsRecord, TreasuryAccount, MeterReading, IntegrationDelivery
from app.models.sad_extensions import CommercialLedger, ExchangeReceipt, ExchangeState, AssistantConversation
from app.models.property import PropertyNode
from app.models.resident_portal import PortalContent, ResidentDocument
from app.models.operations import SecurityIncident
from app.models.service import ServiceCategory, ServiceRequest, WorkOrder
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.site import Site
from app.models.unit import Unit
from app.models.billing import Payment
from app.models.maintenance import Asset
from test_steps4_5 import controlled_case, create, act, record, approve, treasury
from test_step1_fee_proration import concurrent_case
from test_portal_workflows import post as portal_post, action, resource
from auth_test_support import mint_session_token

pytestmark = pytest.mark.skipif(os.getenv('GREENCITY_ISOLATED_SECURITY_TESTS') != '1', reason='Disposable PostgreSQL only')


def post(c, path, data, actor='cskh'):
    return portal_post(c, path, data, actor)


def get(c, path, actor='cskh', **params):
    response = c['client'].get('/api/v1/portal'+path, params=params, headers=c['auth'][actor])
    assert response.status_code == 200, response.text
    return response.json()


def node(c, kind='COMMERCIAL_SPACE'):
    with c['database'].get_session() as session:
        row = PropertyNode(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id, account_id=c['maker'].id,
                           kind=kind, name='Mặt bằng A', code=uuid4().hex, data={})
        session.add(row); session.commit(); return str(row.id)


def endpoint(c, kind, adapter='JSON_REGISTRY'):
    row = create(c, '/control/integrations', {'building_id':str(c['building'].id),'kind':kind,'code':uuid4().hex})
    r = post(c, f'/control/integrations/{row["id"]}/configure', {'expected_version':row['version'],'adapter':adapter,'status':'ACTIVE','reason':'Thiết lập trao đổi'})
    assert r.status_code == 200, r.text
    return r.json()


def test_commercial_lease_proration_ledger_receipts_and_deposit(controlled_case):
    c = controlled_case
    space = approve(c, record(c, 'COMMERCIAL_SPACE', {'property_node_id':node(c),'use_purpose':'Kinh doanh','area_m2':'50','asking_rent_vnd':3100,'operating_conditions':'Giờ hoạt động','evidence_reference':'HS-SPACE'}))
    proposal = approve(c, record(c, 'COMMERCIAL_PROPOSAL', {'space_id':space['id'],'party_kind':'ORGANIZATION','party_name':'Công ty A','legal_reference':'MST-A','contact':'Người liên hệ','starts_on':'2026-09-01','ends_on':'2027-09-01','purpose':'Cửa hàng','operating_plan':'Hoạt động ban ngày','rent_vnd':3000,'service_vnd':300,'deposit_vnd':1000,'evidence_reference':'HS-RENT'}))
    lease = approve(c, record(c, 'COMMERCIAL_LEASE', {'proposal_id':proposal['id'],'contract_number':'LEASE-A','terms':'Điều khoản thuê','rent_cycle':'MONTH','responsible_account_id':str(c['maker'].id),'handover_condition':'Nguyên trạng','evidence_reference':'HD-A'}))
    charge = approve(c, record(c, 'COMMERCIAL_CHARGE', {'lease_id':lease['id'],'starts_on':'2026-09-01','ends_on':'2026-09-16','due_on':'2026-09-20','evidence_reference':'KY-A'}))
    entries = get(c, '/operations/commercial-ledgers')['items']
    assert sorted(e['amount_vnd'] for e in entries) == [150,1000,1500]
    rent = next(e for e in entries if e['kind']=='RENT')
    approve(c, record(c, 'COMMERCIAL_MOVEMENT', {'charge_id':rent['id'],'amount_vnd':1000,'reference':'THU-A','operation':'RECEIPT','occurred_on':'2026-09-16','evidence_reference':'THU-A'}))
    bad = post(c, '/operations/records', {'building_id':str(c['building'].id),'kind':'COMMERCIAL_MOVEMENT','title':'Thu vượt','data':{'charge_id':rent['id'],'amount_vnd':501,'reference':'THU-B','operation':'RECEIPT','occurred_on':'2026-09-16','evidence_reference':'THU-B'}})
    assert bad.status_code == 409
    assert get(c, f'/operations/records/{lease["id"]}/progress')['debt_vnd'] == 650
    assert post(c, '/operations/records', {'building_id':str(c['building'].id),'kind':'COMMERCIAL_CHARGE','title':'Trùng kỳ','data':charge['data']}).status_code == 409
    assert action(c, f'/operations/records/{lease["id"]}/actions', lease, 'COMPLETE').status_code == 409


def project(c):
    budget = treasury(c,limit=1000)
    row = approve(c, record(c,'PROJECT', {'budget_id':budget['id'],'owner_account_id':str(c['maker'].id),'starts_on':'2026-09-01','ends_on':'2026-12-31','objectives':'Thay thiết bị','scope':'Khu chung','impact':'Ngừng thiết bị theo lịch','planned_vnd':500,'items':[{'code':'A1','description':'Lắp thiết bị','quantity':'2','uom':'piece','due_on':'2026-12-01','planned_vnd':500}],'evidence_reference':'DA-A'}))
    return row, budget


def test_project_commitment_partial_acceptance_and_budget_change(controlled_case):
    c = controlled_case; row,budget = project(c)
    with c['database'].get_session() as session: assert session.get(TreasuryAccount,UUID(budget['id'])).reserved_vnd == 500
    acceptance = approve(c, record(c,'PROJECT_ACCEPTANCE', {'project_id':row['id'],'item_code':'A1','accepted_quantity':'1','actual_vnd':200,'performed_on':'2026-09-15','evidence_reference':'NT-A'}))
    assert get(c, f'/operations/records/{row["id"]}/progress')['items'][0]['accepted'] == '1'
    data = {**{k:v for k,v in row['data'].items() if k not in ('remaining_commitment_vnd','settled_vnd')},'project_id':row['id'],'expected_project_version':row['version'],'planned_vnd':800,'items':[{'code':'A1','description':'Lắp thiết bị','quantity':'2','uom':'piece','due_on':'2026-12-01','planned_vnd':800}],'change_reason':'Tăng phạm vi'}
    approve(c, record(c,'PROJECT_CHANGE',data))
    with c['database'].get_session() as session: assert session.get(TreasuryAccount,UUID(budget['id'])).reserved_vnd == 800
    assert post(c,'/operations/records',{'building_id':str(c['building'].id),'kind':'PROJECT_CHANGE','title':'Phiên bản cũ','data':data}).status_code == 409
    bad = {**acceptance['data'],'accepted_quantity':'2'}
    assert post(c,'/operations/records',{'building_id':str(c['building'].id),'kind':'PROJECT_ACCEPTANCE','title':'Nghiệm thu vượt','data':bad}).status_code == 409
    assert action(c,f'/operations/records/{row["id"]}/actions',row,'COMPLETE').status_code in (409,)


def test_project_three_way_payment_handover_and_settlement(controlled_case):
    c = controlled_case; row,budget = project(c)
    approve(c, record(c,'PROJECT_ACCEPTANCE', {'project_id':row['id'],'item_code':'A1','accepted_quantity':'2','actual_vnd':400,'performed_on':'2026-09-15','evidence_reference':'NT-A'}))
    expense = create(c,'/operations/expenses', {'budget_id':budget['id'],'procurement_id':row['id'],'kind':'AP','amount_vnd':400,'reference':'CHI-A','evidence_reference':'CHI-A'})
    expense = act(c,f'/operations/expenses/{expense["id"]}/actions',expense,'SUBMIT')
    expense = act(c,f'/operations/expenses/{expense["id"]}/actions',expense,'APPROVE','checker')
    act(c,f'/operations/expenses/{expense["id"]}/actions',expense,'PAY','accountant',{'amount_vnd':400,'reference':'PAY-A'})
    with c['database'].get_session() as session:
        asset = Asset(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,code=uuid4().hex,name='Thiết bị A',location='Sảnh',status='ACTIVE',version=1,created_by_id=c['maker'].id,updated_by_id=c['maker'].id)
        doc = ResidentDocument(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,account_id=c['maker'].id,title='Hoàn công',original_name='hoan-cong.pdf',storage_key=uuid4().hex,mime_type='application/pdf',size_bytes=100,sha256='a'*64,verification_status='VERIFIED',verified_by_id=c['checker'].id)
        session.add_all([asset,doc]);session.commit()
    approve(c, record(c,'PROJECT_HANDOVER', {'project_id':row['id'],'as_built_document_ids':[str(doc.id)],'asset_ids':[str(asset.id)],'operating_instructions':'Hướng dẫn thiết bị','recipient_account_id':str(c['maker'].id),'warranty_until':'2028-01-01','warranty_contact':'Liên hệ nhà cung cấp','evidence_reference':'BG-A'}))
    approve(c, record(c,'PROJECT_SETTLEMENT', {'project_id':row['id'],'expense_ids':[expense['id']],'actual_vnd':400,'explanation':'Đối chiếu nghiệm thu','evidence_reference':'QT-A'}))
    with c['database'].get_session() as session:
        assert session.get(OperationsRecord,UUID(row['id'])).status == 'COMPLETED'
        budget = session.get(TreasuryAccount,UUID(budget['id'])); assert (budget.spent_vnd,budget.reserved_vnd)==(400,0)
        assert session.get(Asset,asset.id).warranty_until == date(2028,1,1)


def test_insurance_sent_is_not_accepted_or_paid(controlled_case):
    c = controlled_case
    with c['database'].get_session() as session:
        incident = SecurityIncident(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,code=uuid4().hex,
            incident_type='SECURITY',severity='LOW',status='NEW',title='Sự cố tài sản',description='Thiết bị hư',occurred_at=datetime(2026,9,15,tzinfo=UTC),reported_by_id=c['maker'].id)
        session.add(incident);session.commit()
    policy = approve(c,record(c,'INSURANCE_POLICY',{'starts_on':'2026-01-01','ends_on':'2027-01-01','insurer':'Bảo hiểm A','policy_number':'BH-A','insured_objects':['Thiết bị'],'coverage':'Thiệt hại thiết bị','exclusions':'Loại trừ hợp đồng','limit_vnd':1000,'deductible_vnd':50,'contact':'Đầu mối A','evidence_reference':'BH-A'}))
    claim = approve(c,record(c,'INSURANCE_CLAIM',{'policy_id':policy['id'],'incident_id':str(incident.id),'occurred_on':'2026-09-15','loss_vnd':500,'description':'Yêu cầu chi trả','handler_account_id':str(c['maker'].id),'evidence_reference':'BT-A'}))
    claim = act(c,f'/operations/records/{claim["id"]}/actions',claim,'CLAIM_SUBMIT')
    data = {'decision':'PAID','provider_reference':'QD-A','amount_vnd':400,'decided_on':'2026-09-20','evidence_reference':'QD-A'}
    assert action(c,f'/operations/records/{claim["id"]}/actions',claim,'CLAIM_OUTCOME','checker',data).status_code == 409
    claim = act(c,f'/operations/records/{claim["id"]}/actions',claim,'CLAIM_OUTCOME','checker',{**data,'decision':'ACCEPTED'})
    claim = act(c,f'/operations/records/{claim["id"]}/actions',claim,'CLAIM_OUTCOME','checker',data)
    assert claim['status']=='PAID'


def meter(c):
    return create(c,'/operations/meters',{'building_id':str(c['building'].id),'code':'Khu chung','serial':uuid4().hex,'commodity':'WATER','baseline':'100','valid_from':'2026-09-01'})


def target(c, m):
    return approve(c,record(c,'ENERGY_TARGET',{'area_id':node(c,'COMMON_AREA'),'commodity':'WATER','uom':'m3','meter_ids':[m['id']],'starts_on':'2026-09-01','ends_on':'2026-10-01','target_quantity':'60','tolerance_percent':'10','definition':'Chỉ số cuối trừ đầu','policy_reference':'DM-A','evidence_reference':'DM-A'}))


def test_energy_missing_sources_and_normalized_saving(controlled_case):
    c = controlled_case; m = meter(c); policy = target(c,m)
    missing = approve(c,record(c,'ENERGY_REPORT',{'target_id':policy['id'],'starts_on':'2026-09-01','ends_on':'2026-09-11','explanation':'Cần kiểm tra nguồn','evidence_reference':'BC-MISSING'}))
    assert missing['data']['analysis']['status']=='INCOMPLETE' and missing['data']['analysis']['actual'] is None
    for day,value in [('2026-09-01','100'),('2026-09-11','130'),('2026-09-21','150')]:
        reading = create(c,'/operations/readings',{'meter_id':m['id'],'read_on':day,'value':value,'evidence_reference':'CS-A'})
        act(c,f'/operations/readings/{reading["id"]}/actions',reading,'VERIFY','checker',{'anomaly_resolution':'Kiểm tra nguyên nhân'})
    before = approve(c,record(c,'ENERGY_REPORT',{'target_id':policy['id'],'starts_on':'2026-09-01','ends_on':'2026-09-11','explanation':'Đối chiếu khu chung','evidence_reference':'BC-A'}))
    assert before['data']['analysis']['actual']=='30.00000000' or Decimal(before['data']['analysis']['actual'])==30
    assert before['data']['analysis']['anomaly'] and before['data']['analysis']['cause_status']=='UNDETERMINED'
    after = approve(c,record(c,'ENERGY_REPORT',{'target_id':policy['id'],'starts_on':'2026-09-11','ends_on':'2026-09-21','explanation':'Đối chiếu kỳ sau','evidence_reference':'BC-B'}))
    measure = approve(c,record(c,'ENERGY_MEASURE',{'target_id':policy['id'],'description':'Sửa van','owner_account_id':str(c['maker'].id),'due_on':'2026-09-11','expected_saving':'10','cost_vnd':100,'evidence_reference':'BP-A'}))
    result = approve(c,record(c,'ENERGY_RESULT',{'measure_id':measure['id'],'baseline_report_id':before['id'],'result_report_id':after['id'],'starts_on':'2026-09-11','ends_on':'2026-09-21','conclusion':'Giảm một đơn vị mỗi ngày','evidence_reference':'KQ-A'}))
    assert Decimal(result['data']['saving_per_day'])==1


def test_integration_registry_acks_persisted_state_and_stale_commands(controlled_case):
    c=controlled_case; m=meter(c); ep=endpoint(c,'METER')
    body={'action':'QUEUE','expected_version':ep['version'],'reason':'Đồng bộ đồng hồ','data':{'source_type':'METER','source_id':m['id']}}
    r=post(c,f'/control/integrations/{ep["id"]}/sources',body);assert r.status_code==200,r.text; delivery=r.json()
    delivery=act(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'DISPATCH')
    assert delivery['status']=='CONFIRMED'
    with c['database'].get_session() as session:
        state=session.scalar(select(ExchangeState).where(ExchangeState.source_id==UUID(m['id'])));assert state.source_version==m['version']
        from app.models.operational_control import Meter
        meter_row=session.get(Meter,UUID(m['id']));meter_row.version+=1;session.commit()
    delivery=act(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'RETRY')
    assert delivery['status']=='SUPERSEDED'


def test_exchange_file_ack_needs_correlation_version_digest(controlled_case):
    c=controlled_case; m=meter(c);ep=endpoint(c,'METER','JSON_FILE')
    r=post(c,f'/control/integrations/{ep["id"]}/sources',{'action':'QUEUE','expected_version':ep['version'],'reason':'Đồng bộ','data':{'source_type':'METER','source_id':m['id']}});assert r.status_code==200;delivery=r.json()
    delivery=act(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'DISPATCH')
    package=get(c,f'/control/deliveries/{delivery["id"]}/package')
    data={k:package[k] for k in ('correlation_id','source_version','sha256')};data['external_reference']='ACK-A'
    assert action(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'RECONCILE','cskh',{**data,'sha256':'wrong'}).status_code==422
    result=act(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'RECONCILE',data=data);assert result['status']=='CONFIRMED'


def test_meter_feed_deduplicates_and_keeps_verification_pending(controlled_case):
    c=controlled_case;m=meter(c);ep=endpoint(c,'METER');path=f'/control/integrations/{ep["id"]}/readings'
    body={'external_id':'READ-A','meter_id':m['id'],'read_on':'2026-09-01','value':'110','evidence_reference':'CS-A'}
    response=post(c,path,body);assert response.status_code==200,response.text
    assert post(c,path,body).status_code==200
    assert post(c,path,{**body,'value':'111'}).status_code==409
    with c['database'].get_session() as session:
        rows=session.scalars(select(MeterReading).where(MeterReading.meter_id==UUID(m['id']))).all();assert len(rows)==1 and rows[0].status=='SUBMITTED'


def test_bank_feed_creates_one_received_payment_without_automatic_allocation(controlled_case):
    c=controlled_case;ep=endpoint(c,'BANK');path=f'/control/integrations/{ep["id"]}/bank-transactions'
    body={'external_id':'BANK-A','accounting_period_id':str(c['period'].id),'billing_account_id':str(c['billing_account'].id),'amount_vnd':100,'received_at':'2026-09-10T10:00:00+07:00','evidence_reference':'SAOKE-A'}
    r=post(c,path,body);assert r.status_code==200,r.text;assert post(c,path,body).status_code==200
    assert post(c,path,{**body,'amount_vnd':101}).status_code==409
    with c['database'].get_session() as session:
        payment=session.get(Payment,UUID(r.json()['result']['payment_id']));assert payment.amount_vnd==100 and payment.status=='RECEIVED'


def test_grounded_assistant_scope_history_idempotency_and_handoff(controlled_case):
    c=controlled_case
    with c['database'].get_session() as session:
        scope=dict(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,account_id=c['maker'].id)
        guide=PortalContent(**scope,kind='GUIDE',title='Nội quy bãi xe',body='Xe đỗ đúng vị trí đăng ký.',status='PUBLISHED',publish_at=datetime(2025,1,1,tzinfo=UTC))
        hidden=PortalContent(**scope,kind='GUIDE',title='Nội quy bãi xe chưa công bố',body='Không được trả nội dung này.',status='DRAFT',publish_at=datetime(2025,1,1,tzinfo=UTC))
        category=ServiceCategory(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,code=uuid4().hex,name='Hỗ trợ',sla_minutes=60)
        session.add_all([guide,hidden,category]);session.commit()
    body={'mode':'SEARCH','query':'Nội quy bãi xe','unit_id':str(c['unit'].id)}
    headers={**c['auth']['resident'],'Idempotency-Key':uuid4().hex}
    response=c['client'].post('/api/v1/portal/assistant/support',headers=headers,json=body);assert response.status_code==200,response.text
    row=response.json(); assert len(row['messages'][-1]['citations'])==1
    assert c['client'].post('/api/v1/portal/assistant/support',headers=headers,json=body).json()==row
    assert get(c,'/assistant/conversations','cskh')['items']==[]
    r=post(c,'/assistant/support',{'mode':'HANDOFF','query':'Cần CSKH hỗ trợ','unit_id':str(c['unit'].id),'category_id':str(category.id),'conversation_id':row['id'],'expected_version':row['version']},'resident')
    assert r.status_code==200,r.text;row=r.json();assert row['status']=='HANDED_OFF'
    status=post(c,'/assistant/support',{'mode':'STATUS','query':'Xem trạng thái','request_id':row['request_id']},'resident')
    assert status.status_code==200 and 'NEW' in status.json()['messages'][-1]['reply']
    assert post(c,'/assistant/support',{'mode':'DRAFT','query':'Soạn phản hồi'},'resident').status_code==403


@pytest.fixture
def assistant_staff_case(controlled_case):
    c = controlled_case
    with c['database'].get_session() as session:
        technician = Account(tenant_id=c['tenant'].id, username='assistant_tech_' + uuid4().hex,
            full_name='Synthetic technician', hashed_password='token-only-test-account')
        other_building = Building(site_id=c['site'].id, code='B2', name='Other building')
        other_site = Site(tenant_id=c['tenant'].id, code='AS-' + uuid4().hex[:8], name='Other site', address='Synthetic')
        session.add_all([technician, other_building, other_site]); session.flush()
        other_site_building = Building(site_id=other_site.id, code='B1', name='Other site building')
        session.add(other_site_building); session.flush()
        other_unit = Unit(building_id=other_building.id, unit_number='0201', floor=2, area_m2=50, status='occupied')
        other_site_unit = Unit(building_id=other_site_building.id, unit_number='0301', floor=3, area_m2=50, status='occupied')
        session.add_all([other_unit, other_site_unit, AccountRole(account_id=technician.id,
            site_id=c['site'].id, building_id=c['building'].id, role='technician')]); session.flush()
        categories = []
        for site, building in [(c['site'], c['building']), (c['site'], None), (c['site'], other_building), (other_site, other_site_building)]:
            category = ServiceCategory(tenant_id=c['tenant'].id, site_id=site.id, building_id=building.id if building else None,
                code=uuid4().hex, name='Synthetic assistant support', sla_minutes=60)
            session.add(category); categories.append(category)
        session.flush()
        requests = {}
        for label, unit, category, creator in [
            ('assigned', c['unit'], categories[0], c['maker']), ('own', c['unit'], categories[0], technician),
            ('unrelated', c['unit'], categories[0], c['maker']), ('other_building', other_unit, categories[2], c['maker']),
            ('other_site', other_site_unit, categories[3], c['maker'])]:
            row = ServiceRequest(tenant_id=c['tenant'].id, site_id=category.site_id, building_id=unit.building_id,
                unit_id=unit.id, category_id=category.id, code='AS-' + uuid4().hex[:12], title='Synthetic ' + label,
                description='Source description ' + label, priority='MEDIUM', status='NEW',
                sla_started_at=datetime.now(UTC), sla_duration_minutes=60, owner_account_id=creator.id,
                created_by_id=creator.id, updated_by_id=creator.id)
            session.add(row); requests[label] = row
        session.flush()
        session.add(WorkOrder(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id,
            service_request_id=requests['assigned'].id, code='WO-' + uuid4().hex[:12], title='Assigned work',
            description='Synthetic assignment', assigned_to_id=technician.id, status='ASSIGNED',
            created_by_id=c['maker'].id, updated_by_id=c['maker'].id))
        session.add(PortalContent(tenant_id=c['tenant'].id, site_id=c['site'].id, building_id=c['building'].id,
            account_id=c['maker'].id, kind='GUIDE', title='Hướng dẫn thiết bị', body='Kiểm tra theo quy trình đã công bố.',
            status='PUBLISHED', publish_at=datetime(2025, 1, 1, tzinfo=UTC)))
        session.commit()
    c['auth']['technician'] = {'Authorization': 'Bearer ' + mint_session_token(c['database'], technician.id,
        c['settings'].auth_secret(), claims={'active_site_id': str(c['site'].id)})}
    return {**c, 'technician': technician, 'assistant_requests': requests, 'assistant_categories': categories,
        'other_unit': other_unit, 'other_site_unit': other_site_unit}


def test_technician_assistant_options_and_sources_follow_existing_assignment_scope(assistant_staff_case):
    c = assistant_staff_case
    options = get(c, '/assistant/options', 'technician')
    assert {row['id'] for row in options['units']} == {str(c['unit'].id)}
    assert set(options['units'][0]) == {'id', 'unit_number', 'building_id', 'building_name'}
    assert {row['id'] for row in options['categories']} == {str(row.id) for row in c['assistant_categories'][:2]}
    assert {row['id'] for row in options['requests']} == {str(c['assistant_requests'][label].id) for label in ('assigned', 'own')}
    assert c['client'].get('/api/v1/portal/options', headers=c['auth']['technician']).status_code == 403
    for unit in (c['other_unit'], c['other_site_unit']):
        assert c['client'].get('/api/v1/portal/assistant/options', params={'unit_id': str(unit.id)}, headers=c['auth']['technician']).status_code == 404
    for label, row in c['assistant_requests'].items():
        response = c['client'].get(f'/api/v1/portal/assistant/sources/service-requests/{row.id}', headers=c['auth']['technician'])
        assert response.status_code == (200 if label in ('assigned', 'own') else 404), response.text
    resident_options = get(c, '/assistant/options', 'resident')
    assert {row['id'] for row in resident_options['units']} == {str(c['unit'].id)}
    assert resident_options['requests'] == []
    assert c['client'].get('/api/v1/portal/assistant/options', params={'unit_id': str(c['other_unit'].id)}, headers=c['auth']['resident']).status_code == 404


def test_technician_assistant_can_search_status_and_summarize_only_authorized_requests(assistant_staff_case):
    c = assistant_staff_case
    response = post(c, '/assistant/support', {'mode': 'SEARCH', 'query': 'Hướng dẫn thiết bị', 'unit_id': str(c['unit'].id)}, 'technician')
    assert response.status_code == 200, response.text
    assert response.json()['messages'][-1]['citations'][0]['source'] == 'portal_content'
    for mode in ('STATUS', 'SUMMARY'):
        for label in ('assigned', 'own', 'unrelated', 'other_building', 'other_site'):
            row = c['assistant_requests'][label]
            response = post(c, '/assistant/support', {'mode': mode, 'query': 'Kiểm tra diễn biến', 'request_id': str(row.id)}, 'technician')
            assert response.status_code == (200 if label in ('assigned', 'own') else 404), response.text
            if response.status_code == 200:
                assert row.description in response.json()['messages'][-1]['reply']
    assert post(c, '/assistant/support', {'mode': 'DRAFT', 'query': 'Soạn bản nháp'}, 'technician').status_code == 403


def test_technician_assistant_handoff_checks_unit_category_and_replays_one_request(assistant_staff_case):
    c = assistant_staff_case
    body = {'mode': 'HANDOFF', 'query': 'Cần CSKH phối hợp', 'unit_id': str(c['unit'].id),
        'category_id': str(c['assistant_categories'][0].id)}
    assert post(c, '/assistant/support', {**body, 'unit_id': str(c['other_unit'].id)}, 'technician').status_code == 404
    assert post(c, '/assistant/support', {**body, 'category_id': str(c['assistant_categories'][2].id)}, 'technician').status_code == 404
    key = 'assistant-handoff-' + uuid4().hex
    response = portal_post(c, '/assistant/support', body, 'technician', key=key)
    assert response.status_code == 200, response.text
    row = response.json()
    assert portal_post(c, '/assistant/support', body, 'technician', key=key).json() == row
    repeat = post(c, '/assistant/support', {**body, 'conversation_id': row['id'], 'expected_version': row['version']}, 'technician')
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()['request_id'] == row['request_id']
    with c['database'].get_session() as session:
        assert session.scalar(select(func.count(ServiceRequest.id)).where(ServiceRequest.created_by_id == c['technician'].id)) == 2  # Own fixture request plus one handoff.
        created = session.get(ServiceRequest, UUID(row['request_id']))
        assert created.unit_id == c['unit'].id and created.created_by_id == c['technician'].id
    status = post(c, '/assistant/support', {'mode': 'STATUS', 'query': 'Xem yêu cầu đã chuyển', 'request_id': row['request_id']}, 'technician')
    assert status.status_code == 200, status.text


def test_extension_catalog_report_permissions_and_sources(controlled_case):
    c=controlled_case
    catalog=get(c,'/operations/catalog')['items'];assert {'PROJECT','ENERGY_TARGET','COMMERCIAL_LEASE','INSURANCE_POLICY'} <= {r['kind'] for r in catalog}
    for kind in ('PROJECT','ENERGY','COMMERCIAL','INSURANCE'):
        response=post(c,'/control/reports',{'building_id':str(c['building'].id),'kind':kind})
        assert response.status_code==201,response.text
        assert response.json()['metrics']
    assert c['client'].get('/api/v1/portal/operations/commercial-ledgers',headers=c['auth']['resident']).status_code==403


def test_parking_feed_checks_enter_exit_order_and_deduplicates(controlled_case):
    c=controlled_case
    parking=resource(c,'PARKING',capacity=1)
    ep=endpoint(c,'PARKING');path=f'/control/integrations/{ep["id"]}/parking-events'
    body={'external_id':'IN-A','operation':'ENTER','resource_id':parking['id'],'plate':'30A 12345','vehicle_type':'car','occurred_at':'2026-09-10T10:00:00+07:00','rate_vnd':100,'evidence_reference':'XE-A'}
    r=post(c,path,body);assert r.status_code==200,r.text;assert post(c,path,body).status_code==200
    assert post(c,path,{**body,'external_id':'IN-B','plate':'30A 99999'}).status_code==409
    end={**body,'external_id':'OUT-A','operation':'EXIT','visitor_id':r.json()['result']['visitor_id'],'occurred_at':'2026-09-10T11:30:00+07:00'}
    assert post(c,path,{**end,'occurred_at':'2026-09-10T09:00:00+07:00'}).status_code==409
    result=post(c,path,end);assert result.status_code==200,result.text
    assert post(c,path,end).json()['id']==result.json()['id']
    rows=get(c,'/control/visitor-parking')['items'];assert rows[0]['fee_vnd']==200 and rows[0]['status']=='EXITED'


def test_project_progress_and_defect_repair_remain_separate_from_acceptance(controlled_case):
    c=controlled_case;project_row,budget=project(c)
    progress=approve(c,record(c,'PROJECT_PROGRESS',{'project_id':project_row['id'],'item_code':'A1','performed_on':'2026-09-11','actual_quantity':'1.5','issues':'Cần theo dõi thiết bị','operating_impact':'Ngừng một phần','notification_reference':'TB-A','evidence_reference':'TD-A'}))
    result=get(c,f'/operations/records/{project_row["id"]}/progress')['items'][0]
    assert result['accepted']=='0' and result['progress']['actual_quantity']=='1.5'
    acceptance=approve(c,record(c,'PROJECT_ACCEPTANCE',{'project_id':project_row['id'],'item_code':'A1','accepted_quantity':'1','defective_quantity':'1','defect_resolution':'Cần thay thế','actual_vnd':200,'performed_on':'2026-09-12','evidence_reference':'NT-A'}))
    data={'project_id':project_row['id'],'acceptance_id':acceptance['id'],'addressed_quantity':'1','resolution':'Đã thay thiết bị lỗi','responsible_account_id':str(c['maker'].id),'evidence_reference':'KP-A'}
    approve(c,record(c,'PROJECT_DEFECT_RESOLUTION',data))
    assert post(c,'/operations/records',{'building_id':str(c['building'].id),'kind':'PROJECT_DEFECT_RESOLUTION','title':'Khắc phục trùng','data':data}).status_code==409


def test_revocation_exchange_works_after_authority_expiry(controlled_case):
    c=controlled_case
    from app.models.resident_portal import ResidentCredential
    with c['database'].get_session() as session:
        from app.models.account import Account
        resident=session.scalar(select(Account).where(Account.tenant_id==c['tenant'].id,Account.person_id==c['owner'].id))
        card=ResidentCredential(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,unit_id=c['unit'].id,account_id=resident.id,
            code=uuid4().hex,status='REVOKED',valid_to=date(2025,1,1),access_scope=['LOBBY'])
        session.add(card);session.commit()
    ep=endpoint(c,'ACCESS')
    response=post(c,f'/control/integrations/{ep["id"]}/queue',{'action':'QUEUE','expected_version':ep['version'],'reason':'Thu hồi thẻ hết quyền','data':{'credential_id':str(card.id)}})
    assert response.status_code==200,response.text;delivery=response.json()
    delivery=act(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'DISPATCH')
    assert delivery['status']=='CONFIRMED' and delivery['desired_state']['areas']==[]


def test_exchange_failure_evidence_retry_and_ack_order(controlled_case):
    c=controlled_case;m=meter(c);ep=endpoint(c,'METER','JSON_FILE')
    r=post(c,f'/control/integrations/{ep["id"]}/sources',{'action':'QUEUE','expected_version':ep['version'],'reason':'Lập gói','data':{'source_type':'METER','source_id':m['id']}})
    assert r.status_code==200,r.text;delivery=r.json()
    package=get(c,f'/control/deliveries/{delivery["id"]}/package')
    data={k:package[k] for k in ('correlation_id','source_version','sha256')};data.update(external_reference='ERROR-A',error_code='SOURCE_NOT_FOUND')
    assert action(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'REPORT_FAILURE',data=data).status_code==422
    delivery=act(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'DISPATCH')
    delivery=act(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'REPORT_FAILURE',data=data)
    assert delivery['status']=='FAILED'
    delivery=act(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'RETRY')
    assert delivery['status']=='AWAITING_ACK' and delivery['attempts']==2
    delivery=act(c,f'/control/deliveries/{delivery["id"]}/actions',delivery,'RECONCILE',data=data)
    assert delivery['status']=='CONFIRMED'


def test_bank_external_reference_is_namespaced_by_endpoint(controlled_case):
    c=controlled_case
    body={'external_id':'BANK-SAME','accounting_period_id':str(c['period'].id),'billing_account_id':str(c['billing_account'].id),'amount_vnd':100,'received_at':'2026-09-10T10:00:00+07:00','evidence_reference':'SAOKE-A'}
    payments=[]
    for _ in range(2):
        ep=endpoint(c,'BANK')
        r=post(c,f'/control/integrations/{ep["id"]}/bank-transactions',body)
        assert r.status_code==200,r.text;payments.append(r.json()['result']['payment_id'])
    assert payments[0]!=payments[1]


def commercial_lease(c):
    space=approve(c,record(c,'COMMERCIAL_SPACE',{'property_node_id':node(c),'use_purpose':'Kinh doanh','area_m2':'50','asking_rent_vnd':3000,'operating_conditions':'Giờ hoạt động','evidence_reference':'MB-A'}))
    proposal=approve(c,record(c,'COMMERCIAL_PROPOSAL',{'space_id':space['id'],'party_kind':'ORGANIZATION','party_name':'Công ty A','legal_reference':'MST-A','contact':'Liên hệ A','starts_on':'2026-09-01','ends_on':'2026-10-01','purpose':'Cửa hàng','operating_plan':'Hoạt động ban ngày','rent_vnd':3000,'service_vnd':300,'deposit_vnd':1000,'evidence_reference':'DN-A'}))
    return approve(c,record(c,'COMMERCIAL_LEASE',{'proposal_id':proposal['id'],'contract_number':'HD-A','terms':'Điều khoản thuê','rent_cycle':'MONTH','responsible_account_id':str(c['maker'].id),'handover_condition':'Nguyên trạng','evidence_reference':'HD-A'}))


def test_lease_renewal_preserves_old_obligations_and_versions(controlled_case):
    c=controlled_case;lease=commercial_lease(c)
    approve(c,record(c,'LEASE_AMENDMENT',{**lease['data']['agreement'],'lease_id':lease['id'],'expected_lease_version':lease['version'],'operation':'RENEW','starts_on':'2026-10-01','ends_on':'2026-11-01','rent_vnd':6000,'obligations_explanation':'Gia hạn có đối chiếu','evidence_reference':'PL-A'}))
    approve(c,record(c,'COMMERCIAL_CHARGE',{'lease_id':lease['id'],'starts_on':'2026-09-01','ends_on':'2026-10-01','due_on':'2026-10-05','evidence_reference':'KY-CU'}))
    approve(c,record(c,'COMMERCIAL_CHARGE',{'lease_id':lease['id'],'starts_on':'2026-10-01','ends_on':'2026-11-01','due_on':'2026-11-05','evidence_reference':'KY-MOI'}))
    entries=get(c,'/operations/commercial-ledgers')['items']
    rent=sorted((e for e in entries if e['kind']=='RENT'),key=lambda e:e['starts_on'])
    assert [(e['amount_vnd'],e['snapshot']['agreement_version']) for e in rent]==[(3000,1),(6000,2)]
    saved=next(r for r in get(c,'/operations/records',kind='COMMERCIAL_LEASE')['items'] if r['id']==lease['id'])
    assert saved['data']['agreement_history'][0]['agreement']['starts_on']=='2026-09-01'


def test_lease_closure_requires_issued_settled_periods_and_return_condition(controlled_case):
    c=controlled_case;lease=commercial_lease(c)
    closure={**lease['data']['agreement'],'lease_id':lease['id'],'expected_lease_version':lease['version'],'operation':'TERMINATE','ends_on':'2026-09-16','obligations_explanation':'Đối chiếu đến ngày trả','return_condition':'Mặt bằng nguyên trạng','evidence_reference':'TL-A'}
    assert post(c,'/operations/records',{'building_id':str(c['building'].id),'kind':'LEASE_AMENDMENT','title':'Kết thúc','data':closure}).status_code==409
    approve(c,record(c,'COMMERCIAL_CHARGE',{'lease_id':lease['id'],'starts_on':'2026-09-01','ends_on':'2026-09-16','due_on':'2026-09-20','evidence_reference':'KY-A'}))
    for e in get(c,'/operations/commercial-ledgers')['items']:
        approve(c,record(c,'COMMERCIAL_MOVEMENT',{'charge_id':e['id'],'amount_vnd':e['amount_vnd'],'reference':'THU-'+e['id'],'operation':'RECEIPT','occurred_on':'2026-09-16','evidence_reference':'THU-A'}))
        if e['kind']=='DEPOSIT':
            approve(c,record(c,'COMMERCIAL_MOVEMENT',{'charge_id':e['id'],'amount_vnd':e['amount_vnd'],'reference':'HOAN-'+e['id'],'operation':'REFUND','occurred_on':'2026-09-16','evidence_reference':'HOAN-A'}))
    approve(c,record(c,'LEASE_AMENDMENT',closure))
    saved=next(r for r in get(c,'/operations/records',kind='COMMERCIAL_LEASE')['items'] if r['id']==lease['id'])
    assert saved['status']=='COMPLETED' and saved['data']['closed_on']=='2026-09-16'


def test_project_change_cannot_reduce_already_accepted_cost(controlled_case):
    c=controlled_case;row,budget=project(c)
    approve(c,record(c,'PROJECT_ACCEPTANCE',{'project_id':row['id'],'item_code':'A1','accepted_quantity':'1','actual_vnd':400,'performed_on':'2026-09-15','evidence_reference':'NT-A'}))
    change={**{k:v for k,v in row['data'].items() if k not in ('remaining_commitment_vnd','settled_vnd')},'project_id':row['id'],'expected_project_version':row['version'],'planned_vnd':300,'items':[{'code':'A1','description':'Lắp thiết bị','quantity':'2','uom':'piece','due_on':'2026-12-01','planned_vnd':300}],'change_reason':'Giảm dự toán'}
    assert post(c,'/operations/records',{'building_id':str(c['building'].id),'kind':'PROJECT_CHANGE','title':'Giảm dự toán','data':change}).status_code==409


def test_extension_options_do_not_expose_finance_or_resident_documents_to_technical_role(controlled_case):
    from sqlalchemy import delete
    from app.models.account import AccountRole
    c=controlled_case;commercial_lease(c)
    with c['database'].get_session() as session:
        docs=[]
        for unit,title in ((None,'Hồ sơ hoàn công'),(c['unit'].id,'Giấy tờ cá nhân')):
            doc=ResidentDocument(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,unit_id=unit,account_id=c['maker'].id,
                title=title,original_name='hoso.pdf',storage_key=uuid4().hex,mime_type='application/pdf',size_bytes=100,sha256='a'*64,verification_status='VERIFIED')
            session.add(doc);docs.append(doc)
        session.execute(delete(AccountRole).where(AccountRole.account_id==c['maker'].id))
        session.add(AccountRole(account_id=c['maker'].id,site_id=c['site'].id,building_id=c['building'].id,role='technical_lead'))
        session.commit()
    options=get(c,'/operations/options')
    assert 'commercial_ledgers' not in options
    assert [d['id'] for d in options['resident_documents']]==[str(docs[0].id)]


def test_assistant_record_status_and_sources_recheck_resident_ownership(controlled_case):
    from app.models.resident_portal import PortalDossier
    c=controlled_case
    r=post(c,'/dossiers',{'unit_id':str(c['unit'].id),'kind':'PROFILE_CHANGE','title':'Đổi thông tin cá nhân','data':{'full_name':'Cư dân cập nhật'},'valid_from':str(date.today())},'resident')
    assert r.status_code==201,r.text;own=r.json()
    with c['database'].get_session() as session:
        other=PortalDossier(tenant_id=c['tenant'].id,site_id=c['site'].id,building_id=c['building'].id,unit_id=c['unit'].id,
            account_id=c['maker'].id,person_id=c['payer'].id,kind='PROFILE_CHANGE',title='Hồ sơ người khác',data={'full_name':'Người khác'},valid_from=date.today())
        session.add(other);session.commit()
    refs=get(c,'/assistant/options','resident')['records']
    assert any(r['id']==own['id'] for r in refs) and not any(r['id']==str(other.id) for r in refs)
    body={'mode':'STATUS','query':'Xem tình trạng hồ sơ','record_source':'portal_dossiers','record_id':own['id']}
    response=post(c,'/assistant/support',body,'resident');assert response.status_code==200,response.text
    assert own['status'] in response.json()['messages'][-1]['reply']
    assert get(c,f'/assistant/sources/portal-dossiers/{own["id"]}','resident')['status']==own['status']
    assert post(c,'/assistant/support',{**body,'record_id':str(other.id)},'resident').status_code==404
    with c['database'].get_session() as session:
        doc=session.get(PortalDossier,UUID(own['id']));doc.account_id=c['maker'].id;session.commit()
    assert c['client'].get('/api/v1/portal/assistant/sources/portal-dossiers/'+own['id'],headers=c['auth']['resident']).status_code==404


def test_assistant_can_read_project_status_and_rejects_incomplete_or_unapproved_reference_types(controlled_case):
    c=controlled_case;row,budget=project(c)
    body={'mode':'STATUS','query':'Tiến độ hồ sơ dự án','record_source':'operations_records','record_id':row['id']}
    response=post(c,'/assistant/support',body);assert response.status_code==200,response.text
    assert 'APPROVED' in response.json()['messages'][-1]['reply']
    assert post(c,'/assistant/support',{**body,'record_source':'accounts'}).status_code==422
    assert post(c,'/assistant/support',{**body,'record_id':None}).status_code==422
    assert post(c,'/assistant/support',body,'resident').status_code==404
