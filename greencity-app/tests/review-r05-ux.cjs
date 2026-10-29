const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID, createHash } = require('node:crypto');
const { chromium } = require('playwright');
const schemas = require('./fixtures/review-r05-schemas.json');
const output = path.resolve(__dirname, '../../documents/deploy_review/evidence/R05/browser');
const ids = Object.fromEntries(['site','building','otherBuilding','unit','user','maker','staff','training','meter','endpoint','delivery','claim','risk','quote','purchase','roster','wo','cleaning'].map(key => [key,randomUUID()]));
const tasks = {
  'FE-31': ['treasury','expenses','BUDGET_REVISION','BUDGET_VARIANCE','ADVANCE_SETTLEMENT'],
  'FE-32': ['RULE','VIOLATION','RISK','INSPECTION'],
  'FE-33': ['INSURANCE_POLICY','INSURANCE_CLAIM'],
  'FE-34': ['VISITOR','CONTRACTOR','EMERGENCY_PLAN','DRILL','KEY_CUSTODY'],
  'FE-35': ['WASTE','LANDSCAPE','PEST','ENV_INCIDENT'],
  'FE-36': ['STAFF','ROSTER','SOP','TRAINING','WORK_ASSIGNMENT'],
  'FE-37': ['PROJECT','PROJECT_PROGRESS','PROJECT_CHANGE','PROJECT_ACCEPTANCE','PROJECT_DEFECT_RESOLUTION','PROJECT_HANDOVER','PROJECT_SETTLEMENT'],
  'FE-38': ['COMMERCIAL_SPACE','COMMERCIAL_PROPOSAL','COMMERCIAL_LEASE','LEASE_AMENDMENT','COMMERCIAL_CHARGE','COMMERCIAL_MOVEMENT','commercial-ledgers'],
  'FE-39': ['ENERGY_TARGET','ENERGY_REPORT','ENERGY_MEASURE','ENERGY_RESULT'],
  'FE-40': ['integrations','deliveries'],
};
const endpoints = ['METER','ACCOUNTING','BANK','ACCESS','PARKING'].map((kind,i) => ({ id:i ? randomUUID() : ids.endpoint, building_id:ids.building, kind, code:kind+'-R05', adapter:'JSON_FILE', status:'DISABLED', version:1 }));
const claim = { id:ids.claim, building_id:ids.building, kind:'INSURANCE_CLAIM', title:'Bồi thường R05', status:'SENT', version:1, account_id:ids.maker, data:{ loss_vnd:50000 } };
const risk = { id:ids.risk, building_id:ids.building, kind:'RISK', title:'Rủi ro R05', status:'APPROVED', version:1, data:{ findings:[] } };
const training = { id:ids.training, kind:'TRAINING', title:'Đào tạo SOP R05', status:'APPROVED', version:1, data:{ staff_ids:[ids.staff], acknowledgements:{} }, my_acknowledgement:null };
const packageData = { contract:'GREENCITY-JSON-1', correlation_id:ids.delivery, endpoint_id:ids.endpoint, source_type:'METER', source_id:ids.meter, source_version:7, payload:{value:'1.2500'} };
packageData.sha256 = createHash('sha256').update(JSON.stringify(packageData.payload)).digest('hex');
const delivery = { id:ids.delivery, building_id:ids.building, status:'AWAITING_ACK', source_type:'METER', source_id:ids.meter, source_version:7, version:1 };
const records = [claim,risk]; const commands=[], checks=[], errors=[], unexpected=[], receipts=[];
let releaseConfigure, failReceipt=true, staleDelivery=false;
const check=(task,name,pass=true) => { assert.ok(pass,`${task}: ${name}`); checks.push({task,name}); console.log(`PASS ${task} ${name}`); };

(async () => {
  fs.mkdirSync(output,{recursive:true});
  const { operationKinds } = await import('../src/data/operationalForms.js');
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'vi-VN',acceptDownloads:true});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  const apiOptions={ buildings:[{id:ids.building,name:'Tòa R05',code:'R05'},{id:ids.otherBuilding,name:'Tòa khác',code:'OTHER'}], units:[{id:ids.unit,building_id:ids.building,unit_number:'R05-101'}], accounts:[{id:ids.user,building_id:ids.building,label:'Người nhận R05'}], operational_meters:[{id:ids.meter,building_id:ids.building,label:'Đồng hồ R05'}], operations_records:[{id:ids.roster,kind:'ROSTER',building_id:ids.building,label:'Ca R05'}], work_orders:[{id:ids.wo,building_id:ids.building,label:'WO R05'}], cleaning_tasks:[{id:ids.cleaning,building_id:ids.building,label:'Vệ sinh R05'}], treasury_accounts:[] };
  await context.route('**/api/v1/**',async route => {
    const req=route.request(), url=new URL(req.url()), api=url.pathname.replace('/api/v1','');
    const body=req.postData()?req.postDataJSON():null;
    const respond=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
    const reject=(message,status=409)=>respond({error:{code:'ERR-R05-FIXTURE',message,correlation_id:'R05-FIXTURE'}},status);
    if(api==='/auth/login')return respond({access_token:'r05-synthetic-session'});
    if(api==='/auth/me')return respond({account_id:ids.user,tenant_id:ids.site,username:'director.review',full_name:'Người kiểm tra R05',roles:['director'],active_site_id:ids.site,allowed_sites:[{id:ids.site,code:'GC-R05',name:'GreenCity R05'}]});
    assert.equal(req.headers().authorization,'Bearer r05-synthetic-session');
    if(req.method()==='POST'){assert.ok(req.headers()['idempotency-key']);commands.push({api,body,key:req.headers()['idempotency-key']});}
    if(api==='/service-requests')return respond({items:[],page:1,page_size:20,total:0});
    if(api==='/notifications'||api==='/outbox/events')return respond({items:[]});
    if(api==='/dashboard')return respond({as_of:url.searchParams.get('as_of'),sla_overdue_count:0,maintenance_due_count:0,cleaning_rework_count:0,open_incident_count:0,ar_debt_vnd:0});
    if(api==='/portal/options'||api==='/portal/operations/options')return respond(apiOptions);
    if(api==='/portal/capabilities')return respond({items:[]});
    if(api==='/portal/property/persons'||api==='/portal/property/duplicates'||api==='/portal/property/nodes')return respond({items:[]});
    if(api==='/portal/property/buildings')return respond({items:apiOptions.buildings,units:apiOptions.units});
    if(api==='/portal/operations/catalog')return respond({items:Object.values(tasks).flat().filter(k=>schemas.records[k]).map(kind=>({kind,schema:schemas.records[kind]}))});
    if(api==='/portal/control/catalog')return respond({items:['treasury','expenses','integrations','commercial-ledgers'].map(k=>schemas.controls[k])});
    if(api==='/portal/operations/records' && req.method()==='GET')return respond({items:records.filter(r=>r.kind===url.searchParams.get('kind'))});
    if(api==='/portal/operations/records' && req.method()==='POST') { const row={id:randomUUID(),version:1,status:'DRAFT',...body};records.push(row);return respond(row,201); }
    if(api==='/portal/control/integrations')return respond({items:endpoints});
    if(api==='/portal/control/integrations/contract')return respond(schemas.exchange);
    if(api.endsWith('/received'))return respond({items:receipts});
    if(api.endsWith('/configure')) {
      const ep=endpoints.find(r=>api.includes(r.id));assert.equal(body.expected_version,ep.version);
      await new Promise(resolve=>{releaseConfigure=resolve;}); Object.assign(ep,{adapter:body.adapter,status:body.status,version:ep.version+1});return respond(ep);
    }
    if(api.endsWith('/sources')) {
      assert.equal(body.expected_version,endpoints[0].version);assert.equal(body.data.source_type,'METER');assert.equal(body.data.source_id,ids.meter);return respond(delivery);
    }
    if(api.endsWith('/readings') && req.method()==='POST') {
      assert.equal(endpoints[0].status,'ACTIVE');
      assert.equal(body.meter_id,ids.meter);assert.equal(body.value,'1.2500');
      if(failReceipt){failReceipt=false;return route.abort('connectionreset');}
      const result={id:randomUUID(),kind:'METER_READING',status:'APPLIED',payload:body};receipts.push(result);return respond(result);
    }
    if(api==='/portal/control/deliveries')return respond({items:[delivery]});
    if(api.endsWith('/package'))return respond(packageData);
    if(api===`/portal/control/deliveries/${ids.delivery}/actions`) {
      if(staleDelivery){delivery.status='SUPERSEDED';delivery.version++;return respond(delivery);}
      if(body.action==='RECONCILE') {
        if(body.data.sha256!==packageData.sha256)return reject('Checksum không khớp gói dữ liệu.');
        assert.equal(body.data.correlation_id,ids.delivery);assert.equal(body.data.source_version,7);
        delivery.status='CONFIRMED';delivery.version++;return respond(delivery);
      }
      return reject('Thao tác chưa có fixture.');
    }
    if(api===`/portal/operations/records/${ids.claim}/actions`) {
      assert.equal(body.action,'CLAIM_OUTCOME');assert.equal(body.expected_version,claim.version);
      assert.equal(body.data.decision,claim.status==='SENT'?'ACCEPTED':'PAID');assert.equal(body.data.amount_vnd,40000);
      claim.status=body.data.decision;claim.version++;claim.data.outcome=body.data;return respond(claim);
    }
    if(api===`/portal/operations/records/${ids.risk}/actions`) {
      assert.equal(body.action,'COMPLETE');assert.ok(body.data.result);assert.ok(body.data.completion_evidence_reference);
      risk.status='COMPLETED';risk.version++;risk.data.completion=body.data;return respond(risk);
    }
    if(api==='/portal/operations/my-work')return respond({items:[training],handoffs:[]});
    if(api==='/portal/operations/eligible-workers')return respond({items:[{roster_id:ids.roster,name:'Nhân viên R05',eligible:true}]});
    if(api===`/portal/operations/my-work/${ids.training}/acknowledge`) {
      assert.equal(body.action,'ACK_TRAINING');assert.equal(body.expected_version,training.version);assert.equal(training.my_acknowledgement,null);
      training.my_acknowledgement={...body.data,actor_id:ids.user};training.version++;return respond(training);
    }
    if(api.includes('/history')||api.includes('/sources')||api.includes('/source-links')||api.endsWith('/progress'))return respond({items:[]});
    if(api==='/portal/operations/treasury'||api==='/portal/operations/expenses'||api==='/portal/operations/commercial-ledgers'||api==='/portal/control/job-runs')return respond({items:[]});
    unexpected.push(api);return reject('Chưa có fixture cho '+api,404);
  });
  const nav=()=>page.getByRole('navigation',{name:'Điều hướng chính'});
  const openOperations=async()=>{
    await nav().getByRole('button',{name:'Dịch vụ cư dân',exact:true}).click();
    await page.getByLabel('Tòa nhà',{exact:true}).selectOption(ids.building);
    await page.getByRole('navigation',{name:'Phân hệ dịch vụ cư dân'}).getByRole('button',{name:'Vận hành & nguồn lực',exact:true}).click();
    await page.getByLabel('Nghiệp vụ',{exact:true}).waitFor();
  };
  const catalog=async kind=>{await page.getByLabel('Nghiệp vụ',{exact:true}).selectOption(kind);await page.getByRole('heading',{name:operationKinds[kind],exact:true}).waitFor();};
  const card=title=>page.locator('.portal-record').filter({has:page.getByRole('heading',{name:title,exact:true})});
  const shot=name=>page.screenshot({path:path.join(output,name),fullPage:true});
  const ensureOpen=async details=>{await details.waitFor();if(await details.getAttribute('open')===null)await details.locator('summary').first().click();};
  try {
    await page.goto(process.env.UX_BASE_URL||'http://127.0.0.1:3100');await page.getByLabel('Tên đăng nhập').fill('director.review');await page.getByLabel('Mật khẩu').fill('fixture-only');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await openOperations();await page.waitForLoadState('networkidle');
    for(const [task,kinds] of Object.entries(tasks)) for(const kind of kinds){await catalog(kind);check(task,`${kind}: khung và schema hiện hành tải được`);}
    await catalog('WORK_ASSIGNMENT');const assignment=page.locator('form.portal-form').first();
    await assignment.getByLabel('Loại công việc',{exact:true}).selectOption('WORK_ORDER');await assignment.getByLabel('Công việc nhận phân công').selectOption(ids.wo);await assignment.getByLabel('Kỹ năng yêu cầu').fill('electricity');await assignment.getByLabel('Ca được phân công').selectOption(ids.roster);
    await assignment.getByLabel('Loại công việc',{exact:true}).selectOption('CLEANING');check('FE-36.04','Đổi loại công việc xóa đích và ca cũ',await assignment.getByLabel('Công việc nhận phân công').inputValue()==='' && await assignment.getByLabel('Ca được phân công').inputValue()==='');
    await assignment.getByLabel('Công việc nhận phân công').selectOption(ids.cleaning);await assignment.getByLabel('Ca được phân công').selectOption(ids.roster);await assignment.getByLabel('Kỹ năng yêu cầu').fill('cleaning');check('FE-36.04','Đổi năng lực yêu cầu xóa ca đã chọn',await assignment.getByLabel('Ca được phân công').inputValue()==='');await shot('assignment-context.png');
    await catalog('INSURANCE_CLAIM');let claimCard=card(claim.title);
    for(const decision of ['ACCEPTED','PAID']) {
      await claimCard.getByLabel('Kết quả của bên bảo hiểm').selectOption(decision);
      await claimCard.getByLabel('Mã quyết định / chứng từ chi trả').fill('INS-R05');await claimCard.getByLabel('Số tiền theo quyết định (VND)').fill('40000');await claimCard.getByLabel('Căn cứ đối chiếu').fill('BB-R05');await claimCard.getByLabel('Ngày kết quả').fill('2026-10-01');
      await claimCard.getByRole('button',{name:'Ghi kết quả bảo hiểm',exact:true}).click();
      if(decision==='ACCEPTED')await claimCard.getByLabel('Kết quả của bên bảo hiểm').locator('option[value="PAID"]').waitFor({state:'attached'});else await claimCard.getByText('Đã thanh toán',{exact:true}).waitFor();
      check('FE-33.04',`Kết quả ${decision} gửi đúng version và VND rồi tải lại fixture`);
    }
    await shot('insurance-outcome.png');
    await catalog('RISK');let riskCard=card(risk.title);await riskCard.getByRole('button',{name:'Ghi nhận hoàn thành',exact:true}).click();
    await riskCard.getByLabel('Kết quả',{exact:true}).fill('Đã khắc phục');await riskCard.getByLabel('Bằng chứng hoàn thành',{exact:true}).fill('BB-RESULT');await riskCard.getByLabel('Lý do / kết luận',{exact:true}).fill('Đối chiếu kết quả');await riskCard.getByRole('button',{name:/^Xác nhận /}).click();await riskCard.getByText('Hoàn tất',{exact:true}).waitFor();check('FE-32.05','Hoàn thành gửi kết quả và bằng chứng trước khi tải lại');
    await catalog('integrations');let endpointCard=card('METER-R05');let exchange=endpointCard.locator('details').filter({has:page.locator('summary').filter({hasText:'Thiết lập & trao đổi dữ liệu'})});await exchange.locator('summary').click();
    check('FE-40.01','Endpoint tạm dừng hiển thị đúng DISABLED',await exchange.getByLabel('Trạng thái',{exact:true}).inputValue()==='DISABLED');
    for(const kind of ['METER','ACCOUNTING','BANK'])check('FE-40.01',`${kind} không có lệnh đồng bộ thẻ`,await card(kind+'-R05').getByRole('button',{name:'Lập lệnh đồng bộ thẻ',exact:true}).count()===0);
    for(const kind of ['ACCESS','PARKING'])check('FE-40.01',`${kind} còn lệnh đồng bộ thẻ`,await card(kind+'-R05').getByRole('button',{name:'Lập lệnh đồng bộ thẻ',exact:true}).count()===1);
    await exchange.getByLabel('Kênh nhận',{exact:true}).selectOption('JSON_REGISTRY');await exchange.getByRole('button',{name:'Lưu cấu hình',exact:true}).click();await exchange.locator('fieldset[disabled]').waitFor();check('FE-40.01','Khóa cấu hình/nguồn/loại bản tin khi chờ lệnh',await exchange.getByLabel('Tiếp nhận dữ liệu').isDisabled() && await exchange.getByLabel('Mã hồ sơ nguồn').isDisabled());releaseConfigure();
    await endpointCard.getByText('Đã ghi nhận thao tác.',{exact:true}).count();await page.waitForLoadState('networkidle');await exchange.locator('summary').click();
    check('FE-40.01','Sau tải lại giữ adapter mới và trạng thái tạm dừng',await exchange.getByLabel('Kênh nhận').inputValue()==='JSON_REGISTRY' && await exchange.getByLabel('Trạng thái',{exact:true}).inputValue()==='DISABLED');
    await shot('endpoint-paused.png');
    await exchange.getByLabel('Trạng thái',{exact:true}).selectOption('ACTIVE');await exchange.getByRole('button',{name:'Lưu cấu hình',exact:true}).click();await exchange.locator('fieldset[disabled]').waitFor();releaseConfigure();await page.waitForLoadState('networkidle');await exchange.locator('summary').click();check('FE-40.01','Chỉ bật kết nối khi người dùng chọn ACTIVE và lưu rõ ràng',await exchange.getByLabel('Trạng thái',{exact:true}).inputValue()==='ACTIVE');
    await exchange.getByLabel('Nguồn trao đổi').selectOption('METER');await exchange.getByLabel('Mã hồ sơ nguồn').fill(ids.meter);await exchange.getByRole('button',{name:'Lập gói trao đổi',exact:true}).click();await page.waitForLoadState('networkidle');await ensureOpen(exchange);check('FE-40.02','Lập gói đồng hồ qua /control với source_type/source_id đúng');
    await exchange.getByLabel('Tiếp nhận dữ liệu').selectOption('readings');await exchange.getByLabel('Mã bản tin bên gửi').fill('READ-R05');await exchange.getByLabel('Đồng hồ',{exact:true}).selectOption(ids.meter);await exchange.getByLabel('Ngày ghi chỉ số').fill('2026-10-01');await exchange.getByLabel('Chỉ số ghi').fill('1.2500');await exchange.getByLabel('Căn cứ / chứng từ',{exact:true}).fill('READ-EVIDENCE');
    await exchange.getByRole('button',{name:'Nhận và kiểm tra bản tin',exact:true}).click();await page.getByRole('alert').waitFor();
    await exchange.getByRole('button',{name:'Nhận và kiểm tra bản tin',exact:true}).click();await page.waitForLoadState('networkidle');await ensureOpen(exchange);await exchange.getByText('APPLIED',{exact:true}).waitFor();let incoming=commands.filter(c=>c.api.endsWith('/readings'));check('FE-40.03','Nhận lại bản tin giữ key/payload và có sổ nhận',incoming.length===2 && incoming[0].key===incoming[1].key && receipts.length===1);
    await shot('incoming-retry.png');
    await catalog('deliveries');let deliveryCard=page.locator('.portal-record').filter({has:page.getByRole('heading',{name:'Lệnh đồng bộ',exact:true})});await deliveryCard.getByRole('button',{name:'Mở gói dữ liệu & mã đối chiếu',exact:true}).click();await deliveryCard.getByText(packageData.sha256,{exact:true}).waitFor();
    const downloading=page.waitForEvent('download');await deliveryCard.getByRole('button',{name:'Tải gói JSON',exact:true}).click();const downloaded=await downloading;const saved=path.join(output,'exchange.json');await downloaded.saveAs(saved);assert.deepEqual(JSON.parse(fs.readFileSync(saved,'utf8')),packageData);check('FE-40.02','JSON tải xuống khớp correlation/version/checksum và payload API');
    await deliveryCard.getByRole('button',{name:'Ghi xác nhận hệ thống nhận',exact:true}).click();const ack=deliveryCard.locator('.portal-inline-action').filter({has:page.getByRole('button',{name:'Ghi xác nhận hệ thống nhận',exact:true})});
    for(const [label,value] of [['Mã đối chiếu',ids.delivery],['Phiên bản nguồn','7'],['Checksum SHA-256','bad-hash'],['Chứng từ hệ thống nhận','EXT-R05'],['Lý do / kết luận','Đối chiếu gói nhận']])await ack.getByLabel(label,{exact:true}).fill(value);
    await ack.getByRole('button',{name:/^Xác nhận /}).click();await page.getByRole('alert').filter({hasText:'Checksum không khớp'}).waitFor();check('FE-40.04','ACK sai hash hiện lỗi, chưa coi đã xác nhận',delivery.status==='AWAITING_ACK');await ack.getByLabel('Checksum SHA-256').fill(packageData.sha256);await ack.getByRole('button',{name:/^Xác nhận /}).click();await deliveryCard.getByText('Đã xác nhận',{exact:true}).waitFor();check('FE-40.04','ACK hợp lệ gửi đủ căn cứ và tải lại CONFIRMED');await shot('delivery-ack.png');
    staleDelivery=true;delivery.status='AWAITING_ACK';await page.getByRole('button',{name:'Làm mới',exact:true}).click();await deliveryCard.getByRole('button',{name:'Ghi xác nhận hệ thống nhận',exact:true}).click();
    for(const [label,value] of [['Mã đối chiếu',ids.delivery],['Phiên bản nguồn','7'],['Checksum SHA-256',packageData.sha256],['Chứng từ hệ thống nhận','EXT-R05'],['Lý do / kết luận','Đối chiếu nguồn đã đổi']])await ack.getByLabel(label,{exact:true}).fill(value);
    await ack.getByRole('button',{name:/^Xác nhận /}).click();await deliveryCard.getByText('Đã được thay thế',{exact:true}).waitFor();check('FE-40.04','Nguồn đã đổi hiển thị SUPERSEDED và bỏ các nút ACK');
    await nav().getByRole('button',{name:'Đào tạo & Nhận việc',exact:true}).click();let trainingCard=card(training.title);await trainingCard.getByLabel('Kết quả / nội dung đã tiếp nhận').fill('Đã tiếp nhận SOP');await trainingCard.getByLabel('Căn cứ xác nhận').fill('TRAIN-ACK');await trainingCard.getByRole('button',{name:'Xác nhận đào tạo đúng phiên bản',exact:true}).click();await trainingCard.getByText('Đã xác nhận đào tạo đúng phiên bản.',{exact:true}).waitFor();check('FE-36.02','Sau ACK đào tạo hiện căn cứ, bỏ nút xác nhận lặp',await trainingCard.getByRole('button',{name:'Xác nhận đào tạo đúng phiên bản',exact:true}).count()===0);await shot('training-acknowledged.png');
    await nav().getByRole('button',{name:'Dịch vụ cư dân',exact:true}).click();await nav().getByRole('button',{name:'Đào tạo & Nhận việc',exact:true}).click();await trainingCard.getByText('Đã xác nhận đào tạo đúng phiên bản.',{exact:true}).waitFor();check('FE-36.02','Rời trang rồi tải lại fixture vẫn giữ trạng thái cá nhân, không gửi ACK thứ hai',commands.filter(c=>c.api.endsWith('/acknowledge')).length===1);
    await page.setViewportSize({width:390,height:844});await shot('workforce-mobile.png');check('FE-36.02','Trang nhận việc vừa màn hình 390 px',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);check('COMMON','Không có pageerror hoặc request ngoài fixture');
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({source:'FIXTURE',passed:checks.length,checks,commands,pageErrors:errors,unexpectedApi:unexpected},null,2));console.log(`REVIEW R05 UX: ${checks.length} checks passed.`);
  }catch(error){await shot('failure.png');fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({error:error.message,checks,commands,pageErrors:errors,unexpectedApi:unexpected},null,2));throw error;}
  finally{await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
