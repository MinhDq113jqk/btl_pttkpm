const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { chromium } = require('playwright');
const schemas = require('./fixtures/review-r04-schemas.json');
const output = path.resolve(__dirname, '../../documents/deploy_review/evidence/R04/browser');
const id = Object.fromEntries(['site','building','otherBuilding','unit','otherUnit','admin','director','accountant','period','account','payment','credit','invoice','deposit','lease','doc','meter','reading','stock','purchase','vendor','quote','wrongQuote','draftQuote','contract','content','conversation','category','request','csv','dataset','notice'].map(k => [k,randomUUID()]));
const buildings = [{id:id.building,name:'Tòa A',code:'A'},{id:id.otherBuilding,name:'Tòa B',code:'B'}];
const units = [{id:id.unit,unit_number:'A-101',building_id:id.building},{id:id.otherUnit,unit_number:'B-201',building_id:id.otherBuilding}];
const period = {id:id.period,building_id:id.building,period_key:'2026-10',status:'OPEN'};
const invoice = {id:id.invoice,building_id:id.building,billing_account_id:id.account,invoice_number:'INV-R04-01',status:'ISSUED',outstanding_vnd:100000,total_vnd:100000,version:1};
const deposit = {id:id.deposit,source_kind:'LEASE',unit_id:id.unit,building_id:id.building,required_vnd:100000,balance_vnd:100000,refundable_vnd:100000,status:'HELD',version:1,movements:[]};
const stock = {id:id.stock,building_id:id.building,name:'Vật tư kiểm tra',code:'STK-01',uom:'kg',quantity:'1.5000',reserved:'0.0000',minimum:'2.0000',version:3,unit_cost_vnd:20000};
const record = (key,kind,status,data={},related_id=null) => ({id:id[key],kind,status,title:`${kind} kiểm tra`,building_id:id.building,version:1,data,related_id,account_id:id.admin});
const records = [record('vendor','VENDOR','APPROVED'),record('purchase','PURCHASE','DRAFT',{budget_id:randomUUID(),quantity:'1',uom:'kg',estimated_vnd:100000,specification:'Vật tư kiểm tra'}),record('quote','QUOTATION','APPROVED',{vendor_id:id.vendor,quantity:'1',unit_price_vnd:100000},id.purchase),record('wrongQuote','QUOTATION','APPROVED',{},randomUUID()),record('draftQuote','QUOTATION','DRAFT',{},id.purchase),record('contract','CONTRACT','APPROVED',{vendor_id:id.vendor,milestone_items:[]})];
const commands=[], cases=[], movements=[], readings=[], documents=[], contents=[], conversations=[];
const checks=[],errors=[],unexpected=[];
const check=(task,name,value=true) => {assert.ok(value,`${task}: ${name}`);checks.push({task,name});console.log(`PASS ${task} ${name}`);};
const commonOptions = () => ({buildings,units,lease_contracts:[{id:id.lease,label:'Thuê cư trú A',building_id:id.building}],accounts:[{id:id.director,label:'Người duyệt',building_id:id.building}],operations_records:records.map(r=>({...r,label:r.title})),operational_stock_items:[{...stock,label:stock.name}],operational_meters:[{id:id.meter,label:'Đồng hồ A',building_id:id.building}],billing_fee_policy_versions:[],treasury_accounts:[],resident_documents:documents.map(r=>({...r,label:r.title}))});
const financeOptions = () => ({periods:[period],accounts:[{id:id.account,building_id:id.building,account_number:'BA-R04',status:'ACTIVE'}],payments:[{id:id.payment,building_id:id.building,billing_account_id:id.account,receipt_number:'RCPT-R04',status:'RECEIVED',amount_vnd:100000}],credits:[{id:id.credit,building_id:id.building,billing_account_id:id.account,status:'AVAILABLE',amount_vnd:20000}],invoices:[invoice],deposits:[deposit],staff_accounts:[]});
let rejectSave=false, currentDataset=null;
const notice={id:id.notice,domain_event_id:randomUUID(),template_code:'MANDATORY',template_snapshot:{title:'Thông báo bắt buộc R04',body:'Đã đọc vẫn cần xác nhận',requires_ack:true},delivery_status:'PUBLISHED',read_at:'2026-10-11T00:00:00Z',acknowledged_at:null,last_error:null,created_at:'2026-10-11T00:00:00Z'};

(async () => {
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true,channel:'msedge'});const contexts=[];
  const open=async role => {
    const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'vi-VN'});contexts.push(context);
    await context.route('**/api/v1/**',async route => {
      const req=route.request(),url=new URL(req.url()),api=url.pathname.replace('/api/v1','');
      const body=req.postData() && req.headers()['content-type']?.includes('application/json')?req.postDataJSON():null;
      const respond=(data,status=200) => route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
      const reject=(message,status=409) => respond({error:{code:'ERR-R04-FIXTURE',message,correlation_id:'R04-FIXTURE'}},status);
      if(api==='/auth/login')return respond({access_token:'r04-fixture-session'});
      if(api==='/auth/me')return respond({account_id:id[role],tenant_id:id.site,username:`${role}.review`,full_name:'Người kiểm tra',roles:[role],active_site_id:id.site,allowed_sites:[{id:id.site,code:'GC',name:'GreenCity'}]});
      assert.equal(req.headers().authorization,'Bearer r04-fixture-session');
      if(req.method()==='POST') {assert.ok(req.headers()['idempotency-key'],api);commands.push({api,body,role,key:req.headers()['idempotency-key']});}
      if(api==='/service-requests')return respond({items:[],page:1,page_size:20,total:0});
      if(api==='/notifications')return respond({items:[notice]});
      if(api==='/outbox/events')return respond({items:[]});
      if(api==='/dashboard')return respond({as_of:url.searchParams.get('as_of'),sla_overdue_count:0,maintenance_due_count:0,cleaning_rework_count:0,open_incident_count:0,ar_debt_vnd:0});
      if(!api.startsWith('/portal/')) {unexpected.push(api);return reject('API chưa có fixture',404);}
      const p=api.replace('/portal','');
      if(p==='/options')return respond({buildings,units});
      if(p==='/capabilities')return respond({items:[]});
      if(p===`/control/notifications/${id.notice}/ack`){notice.acknowledged_at='2026-10-11T01:00:00Z';return respond({id:id.notice,acknowledged_at:notice.acknowledged_at});}
      if(p==='/property/persons'||p==='/property/duplicates'||p==='/property/nodes')return respond({items:[]});
      if(p==='/property/buildings')return respond({items:buildings,units});
      if(p.startsWith('/property/units/'))return respond({leases:[],profiles:[],liabilities:[],relationships:[],events:[]});
      if(p==='/finance/options')return respond(financeOptions());
      if(p==='/finance/reviews')return respond({items:[]});
      if(p==='/finance/commands/preview') {
        const sum=body.data.allocations.reduce((s,a)=>s+a.amount_vnd,0);
        if(sum>invoice.outstanding_vnd)return reject('Phân bổ vượt số nợ còn lại.');
        return respond({amount_vnd:sum||body.amount_vnd,allocations:body.data.allocations,calculation_hash:`hash-${body.kind}`,requires_independent_approval:true});
      }
      if(p==='/finance/commands') {
        if(req.method()==='GET')return respond({items:commands.filter(r=>r.row).map(r=>r.row)});
        if(rejectSave)return reject('Nguồn thay đổi; cần xem trước lại.');
        assert.equal(body.expected_hash,`hash-${body.kind}`);
        const row={id:randomUUID(),...body,account_id:id[role],status:'DRAFT',version:1};commands.at(-1).row=row;return respond(row,201);
      }
      if(/^\/finance\/commands\/[^/]+\/actions$/.test(p)) {
        const row=commands.find(r=>r.row?.id===p.split('/')[3]).row;
        assert.equal(body.expected_version,row.version);
        if(body.action==='APPROVE'&&row.account_id===id[role])return reject('Người lập không được tự duyệt.',403);
        row.status={SUBMIT:'SUBMITTED',APPROVE:'APPROVED',EXECUTE:'EXECUTED',MARK_UNCERTAIN:'RECONCILIATION',CONFIRM_EXECUTION:'EXECUTED'}[body.action];row.version++;
        if(body.action==='APPROVE')row.approved_by_id=id[role];
        if(body.action==='EXECUTE'&&row.kind==='ALLOCATE')invoice.outstanding_vnd-=row.data.allocations.reduce((s,a)=>s+a.amount_vnd,0);
        if(body.data.execution_reference)row.data.execution_reference=body.data.execution_reference;
        return respond(row);
      }
      if(p.endsWith('/history'))return respond({items:[{id:randomUUID(),action:'CREATE',reason:'Căn cứ kiểm tra',actor_id:id.admin,created_at:'2026-10-11T00:00:00Z'}]});
      if(p.endsWith('/delta'))return respond({items:[]});
      if(p==='/finance/ar') {
        if(req.method()==='POST') {const row={id:randomUUID(),...body,status:'OPEN',version:1};cases.push(row);return respond(row,201);}
        return respond({as_of:'2026-10-11',aging:{CURRENT:invoice.outstanding_vnd},ledger_balance_vnd:invoice.outstanding_vnd,items:[invoice],cases,ledger:[]});
      }
      if(p==='/deposits')return respond({items:[deposit]});
      if(p==='/dossiers')return respond({items:[]});
      if(p==='/documents') {
        if(req.method()==='POST') {
          const row={id:randomUUID(),title:url.searchParams.get('title'),unit_id:url.searchParams.get('unit_id'),building_id:id.building,content_version:1,version:1,mime_type:req.headers()['content-type'],size_bytes:req.postDataBuffer().length,created_at:'2026-10-11T00:00:00Z',published:false};documents.push(row);return respond(row,201);
        }
        return respond({items:documents});
      }
      if(/\/documents\/[^/]+\/signed-link$/.test(p))return respond({token:'fixture-download',expires_at:'2030-01-01T00:00:00Z'});
      if(/\/documents\/[^/]+\/download$/.test(p))return route.fulfill({status:200,contentType:'application/pdf',headers:{'Content-Disposition':'attachment; filename="review.pdf"'},body:'%PDF-1.4\n%%EOF\n'});
      if(p==='/content') {
        if(req.method()==='POST'){const row={id:randomUUID(),...body,version:1,status:'DRAFT',minutes:{}};contents.push(row);return respond(row,201);}return respond({items:contents});
      }
      if(p.endsWith('/chain'))return respond({items:contents});
      if(p==='/community-tasks')return respond({items:[]});
      if(p==='/completion-options')return respond({...commonOptions(),csv_batches:[{id:id.csv,label:'Batch CSV đã áp dụng'}],loader_batches:[]});
      if(p==='/init-datasets') {
        if(req.method()==='POST'){assert.deepEqual(body.manifest.expected_counts,{csv_rows:1,units:1});currentDataset={id:id.dataset,...body,status:'DRAFT',effective_status:'DRAFT',version:1};return respond(currentDataset,201);}return respond({items:currentDataset?[currentDataset]:[]});
      }
      if(p==='/operations/catalog')return respond({items:schemas.records});
      if(p==='/control/catalog')return respond({items:schemas.controls});
      if(p==='/operations/options')return respond(commonOptions());
      if(p==='/operations/records') {
        if(req.method()==='POST'){const row={id:randomUUID(),...body,status:'DRAFT',version:1};records.push(row);return respond(row,201);}return respond({items:records.filter(r=>r.kind===url.searchParams.get('kind'))});
      }
      if(/^\/operations\/records\/[^/]+\/actions$/.test(p)) {
        const row=records.find(r=>r.id===p.split('/')[3]);assert.equal(body.expected_version,row.version);
        if(body.action==='SELECT_QUOTE'){const quote=records.find(r=>r.id===body.data.quotation_id);assert.equal(quote.related_id,row.id);assert.equal(quote.status,'APPROVED');row.data.selected_quote_id=quote.id;row.version++;}
        return respond(row);
      }
      if(p.endsWith('/contract-progress'))return respond({milestones:[{code:'M1',due_on:'2026-11-01',amount_vnd:100000,status:'PENDING',obligation:'Giao đủ vật tư'}],financial:{committed_vnd:100000,payable_vnd:0,paid_vnd:0}});
      if(p==='/operations/meters')return respond({items:[{id:id.meter,building_id:id.building,code:'MTR-WATER-01',status:'ACTIVE',version:1,commodity:'WATER'}]});
      if(p==='/operations/readings') {
        if(req.method()==='POST'){const row={id:randomUUID(),...body,building_id:id.building,status:'SUBMITTED',version:1,anomaly:false};readings.push(row);return respond(row,201);}return respond({items:readings});
      }
      if(p==='/operations/stock')return respond({items:[stock]});
      if(p==='/operations/stock-movements') {
        if(req.method()==='POST'){assert.equal(body.expected_version,stock.version);if(Number(body.quantity)>Number(stock.quantity))return reject('Xuất kho vượt tồn khả dụng.');const row={id:randomUUID(),...body,building_id:id.building,status:'POSTED',version:1};movements.push(row);stock.quantity=String(Number(stock.quantity)-Number(body.quantity));stock.version++;return respond(row,201);}return respond({items:movements});
      }
      if(p==='/assistant/conversations')return respond({items:conversations});
      if(p==='/assistant/options')return respond({units,requests:[],records:[],categories:[{id:id.category,label:'CSKH'}]});
      if(p==='/assistant/support') {
        let row=conversations.find(r=>r.id===body.conversation_id);if(!row){row={id:randomUUID(),title:body.query,version:0,messages:[]};conversations.push(row);}
        if(body.conversation_id)assert.equal(body.expected_version,row.version);
        row.messages.push({mode:body.mode,query:body.query,reply:body.mode==='HANDOFF'?'Đã chuyển đến CSKH: SR-R04-01':'Chưa tìm thấy nguồn phù hợp. Có thể chuyển đến CSKH.',needs_handoff:body.mode!=='HANDOFF',citations:body.mode==='HANDOFF'?[{source:'service_requests',id:id.request,title:'SR-R04-01',version:1}]:[]});row.version++;return respond(row);
      }
      if(p.startsWith('/assistant/sources/'))return respond({title:'SR-R04-01',status:'NEW',version:1,description:'Nội dung chuyển tiếp'});
      unexpected.push(p);return reject('API chưa có fixture',404);
    });
    const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
    await page.goto(process.env.UX_BASE_URL||'http://127.0.0.1:3100/');
    await page.getByLabel('Tên đăng nhập').fill(`${role}.review`);await page.getByLabel('Mật khẩu').fill('browser-only-password');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
    await page.getByRole('navigation',{name:'Điều hướng chính'}).getByRole('button',{name:'Dịch vụ cư dân',exact:true}).click();
    await page.getByLabel('Tòa nhà',{exact:true}).selectOption(id.building);await page.getByLabel('Căn hộ',{exact:true}).selectOption(id.unit);
    return page;
  };
  const tab=async (page,name) => page.getByRole('navigation',{name:'Phân hệ dịch vụ cư dân'}).getByRole('button',{name,exact:true}).click();
  const shot=async (page,name)=>page.screenshot({path:path.join(output,name),fullPage:true});
  const decision=async (page,row,action) => {
    const card=page.locator('.portal-record').filter({has:page.getByRole('heading',{name:row,exact:true})});
    await card.getByLabel('Thao tác',{exact:true}).selectOption(action);await card.getByLabel('Lý do quyết định',{exact:true}).fill('Quyết định kiểm tra');
    if(['EXECUTE','CONFIRM_EXECUTION'].includes(action))await card.getByLabel('Mã chứng từ thực hiện / thực chi').fill('CT-R04-01');
    await card.getByRole('button',{name:'Xác nhận',exact:true}).click();
  };
  try {
    const admin=await open('admin');await tab(admin,'Kiểm soát tài chính');await admin.getByRole('button',{name:'Hồ sơ tài chính',exact:true}).click();
    const proposal=admin.locator('form').filter({has:admin.getByRole('heading',{name:'Lập đề nghị tài chính',exact:true})});
    for(const kind of ['ALLOCATE','CREDIT_USE','INVOICE_VOID','CREDIT','WRITE_OFF','PAYMENT_REVERSE','PAYMENT_REFUND','DEPOSIT_DEDUCT','DEPOSIT_RELEASE','DEPOSIT_REFUND','PERIOD_LOCK','PERIOD_REOPEN','ACCOUNT_OPEN','ACCOUNT_SUSPEND','ACCOUNT_RESUME','ACCOUNT_CLOSE']) {
      await proposal.getByLabel('Nghiệp vụ',{exact:true}).selectOption(kind);await proposal.getByLabel('Kỳ kế toán',{exact:true}).selectOption(id.period);
      const target=kind.startsWith('DEPOSIT_')?id.deposit:['INVOICE_VOID','CREDIT','WRITE_OFF'].includes(kind)?id.invoice:kind==='CREDIT_USE'?id.credit:kind.startsWith('PERIOD_')?id.period:kind==='ACCOUNT_OPEN'?id.unit:kind.startsWith('ACCOUNT_')?id.account:id.payment;
      await proposal.getByLabel('Đối tượng nguồn',{exact:true}).selectOption(target);await proposal.getByLabel('Số tiền (VND)',{exact:true}).fill('10000');await proposal.getByLabel('Lý do',{exact:true}).fill('Đề nghị theo chứng từ');await proposal.getByLabel('Căn cứ / mã tài liệu').fill('CT-R04');
      if(['ALLOCATE','CREDIT_USE'].includes(kind))await proposal.getByLabel(/INV-R04-01 · Nợ/).fill('10000');
      if(kind.startsWith('ACCOUNT_'))await proposal.getByLabel('Ngày hiệu lực').fill('2026-10-11');
      if(kind==='ACCOUNT_OPEN')await proposal.getByLabel('Số tài khoản phí').fill('BA-NEW');
      if(kind==='PERIOD_REOPEN'){await proposal.getByLabel('Hạn mở kỳ').fill('2026-11-01T10:00');await proposal.getByLabel('Mã chứng từ được điều chỉnh (cách nhau bằng dấu phẩy)').fill(id.invoice);await proposal.getByLabel('Điều chỉnh ghi có',{exact:true}).check();}
      await proposal.getByRole('button',{name:'Xem trước đề nghị',exact:true}).click();await proposal.getByRole('heading',{name:'Xác nhận bản xem trước',exact:true}).waitFor();
      check(kind.startsWith('DEPOSIT_')?'FE-23.03':kind.startsWith('PERIOD_')?'FE-22.03':kind.startsWith('ACCOUNT_')?'FE-22.04':'FE-21.02',`Xem trước ${kind} gửi đúng nguồn và có hash`);
      await proposal.getByLabel('Lý do',{exact:true}).fill('Nội dung đã thay đổi');check('FE-21.05',`${kind}: sửa form xóa bản xem trước`,await proposal.getByRole('heading',{name:'Xác nhận bản xem trước',exact:true}).count()===0);
    }
    await proposal.getByLabel('Nghiệp vụ',{exact:true}).selectOption('ALLOCATE');await proposal.getByLabel('Kỳ kế toán',{exact:true}).selectOption(id.period);await proposal.getByLabel('Đối tượng nguồn',{exact:true}).selectOption(id.payment);await proposal.getByLabel(/INV-R04-01 · Nợ/).fill('10000');
    await proposal.getByRole('button',{name:'Xem trước đề nghị',exact:true}).click();await proposal.getByRole('button',{name:'Lưu đề nghị từ bản xem trước',exact:true}).waitFor();
    rejectSave=true;await proposal.getByRole('button',{name:'Lưu đề nghị từ bản xem trước',exact:true}).click();await proposal.getByRole('alert').filter({hasText:'Nguồn thay đổi'}).waitFor();check('FE-21.05','Nguồn thay đổi được hiển thị là lỗi, chưa tạo hồ sơ');
    rejectSave=false;await proposal.getByRole('button',{name:'Lưu đề nghị từ bản xem trước',exact:true}).click();await admin.locator('.portal-record').getByRole('heading',{name:'Phân bổ thu tiền',exact:true}).waitFor();
    await decision(admin,'Phân bổ thu tiền','SUBMIT');await admin.getByText('Đã gửi',{exact:true}).waitFor();await decision(admin,'Phân bổ thu tiền','APPROVE');await admin.getByRole('alert').filter({hasText:'Người lập không được tự duyệt.'}).waitFor();check('FE-21.05','Từ chối tự duyệt giữ trạng thái đã gửi');
    await shot(admin,'finance-maker-rejection.png');
    const director=await open('director');await tab(director,'Kiểm soát tài chính');await director.getByRole('button',{name:'Hồ sơ tài chính',exact:true}).click();await decision(director,'Phân bổ thu tiền','APPROVE');await director.getByText('Đã duyệt',{exact:true}).waitFor();await decision(director,'Phân bổ thu tiền','EXECUTE');await director.getByText('Chứng từ thực hiện: CT-R04-01',{exact:true}).waitFor();check('FE-21.02','Duyệt độc lập rồi thực hiện cập nhật fixture công nợ',invoice.outstanding_vnd===90000);
    await director.getByRole('button',{name:'Lịch sử quyết định',exact:true}).click();await director.getByText(/CREATE · Căn cứ kiểm tra/).waitFor();check('FE-21.03','Lịch sử quyết định còn đọc được');
    await director.getByRole('button',{name:'Công nợ',exact:true}).click();await director.getByRole('heading',{name:'Lập hồ sơ theo dõi nợ',exact:true}).waitFor();
    const ar=director.locator('form').filter({has:director.getByRole('heading',{name:'Lập hồ sơ theo dõi nợ',exact:true})});
    for(const kind of ['DISPUTE','PROMISE','REMINDER']){await ar.getByLabel('Loại',{exact:true}).selectOption(kind);await ar.getByLabel('Hóa đơn',{exact:true}).selectOption(id.invoice);await ar.getByLabel('Số tiền (VND)',{exact:true}).fill('10000');await ar.getByLabel('Lý do / nội dung').fill('Theo dõi số nợ');if(kind==='PROMISE')await ar.getByLabel('Ngày cam kết trả').fill('2030-01-01');if(kind==='REMINDER')await ar.getByLabel('Nhắc phần đang tranh chấp').selectOption('no');await ar.getByRole('button',{name:'Ghi nhận',exact:true}).click();await director.getByText(`${kind} · 10.000 ₫`,{exact:true}).waitFor();check('FE-22.02',`${kind} tải lại hồ sơ riêng, giữ nguyên số dư`,invoice.outstanding_vnd===90000);}
    await shot(director,'receivables.png');
    await tab(admin,'Cọc');await admin.getByRole('heading',{name:'Cọc hợp đồng thuê',exact:true}).waitFor();check('FE-23.01','Cọc thuê hiển thị đúng loại nguồn');check('FE-23.02','Hiển thị tiền yêu cầu, đang giữ và được hoàn',await admin.getByText(/Yêu cầu 100.000/).count()>0);await shot(admin,'lease-deposit.png');
    await tab(admin,'Tài liệu');const upload=admin.locator('form').filter({has:admin.getByLabel('Tên tài liệu',{exact:true})});await upload.getByLabel('Tên tài liệu',{exact:true}).fill('Tài liệu kiểm tra');await upload.getByLabel('Tệp PDF / PNG / JPEG (tối đa 10 MB)').setInputFiles({name:'bad.txt',mimeType:'text/plain',buffer:Buffer.from('invalid')});await admin.getByRole('alert').filter({hasText:'Chọn tệp PDF'}).waitFor();check('FE-24.01','Sai loại tệp bị chặn trước upload',documents.length===0);
    await upload.getByLabel('Tệp PDF / PNG / JPEG (tối đa 10 MB)').setInputFiles({name:'review.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\n%%EOF\n')});await upload.getByRole('button',{name:'Tải tài liệu',exact:true}).click();await admin.getByRole('heading',{name:'Tài liệu kiểm tra',exact:true}).waitFor();check('FE-24.01','Tài liệu hợp lệ tải lại trong danh sách và input được xóa',await upload.locator('input[type=file]').inputValue()==='');const download=admin.waitForEvent('download');await admin.getByRole('button',{name:'Tải xuống',exact:true}).click();await download;check('FE-24.01','Tải tài liệu qua lời gọi API được xác thực');await shot(admin,'documents.png');
    await tab(admin,'Nội dung');await admin.getByLabel('Loại nội dung').selectOption('NOTICE');await admin.getByLabel('Tiêu đề',{exact:true}).fill('Thông báo R04');await admin.getByLabel('Công bố từ').fill('2026-10-11T12:00');await admin.getByLabel('Nội dung',{exact:true}).fill('Nội dung kiểm tra');await admin.getByRole('button',{name:'Lưu bản nháp',exact:true}).click();await admin.getByRole('heading',{name:'Thông báo R04',exact:true}).waitFor();check('FE-24.02','Soạn nội dung tạo DRAFT, chưa coi là công bố',contents[0].status==='DRAFT');
    await tab(admin,'Dữ liệu khởi tạo');await admin.getByLabel('Tên bộ dữ liệu').fill('Bộ dữ liệu R04');await admin.getByLabel('Batch CSV').selectOption([id.csv]);const expectationValues=admin.getByLabel('Giá trị kỳ vọng',{exact:true});await expectationValues.nth(0).fill('1');await expectationValues.nth(1).fill('1');await admin.getByLabel('Chỉ tiêu',{exact:true}).nth(1).selectOption('csv_rows');await admin.getByRole('button',{name:'Lập bộ dữ liệu để đối chiếu',exact:true}).click();await admin.getByRole('alert').filter({hasText:'Mỗi chỉ tiêu'}).waitFor();check('FE-27.04','Chỉ tiêu trùng không bị ghi đè âm thầm',currentDataset===null);await admin.getByLabel('Chỉ tiêu',{exact:true}).nth(1).selectOption('units');await admin.getByRole('button',{name:'Lập bộ dữ liệu để đối chiếu',exact:true}).click();await admin.getByRole('heading',{name:'Bộ dữ liệu R04',exact:true}).waitFor();check('FE-27.04','Bộ khởi tạo gửi đúng kỳ vọng số lượng và batch');check('FE-27.05','Loader chọn batch có sẵn, không giả màn upload',await admin.locator('input[type=file]').count()===0);await shot(admin,'init-dataset.png');
    await tab(admin,'Vận hành & nguồn lực');
    for(const descriptor of [...schemas.controls,...schemas.records]){await admin.getByLabel('Nghiệp vụ',{exact:true}).selectOption(descriptor.kind);const form=admin.locator('.resident-page form').filter({has:admin.getByRole('button',{name:'Lưu hồ sơ',exact:true})});await form.waitFor();check(['DEPOSIT_POLICY','LEASE_DEPOSIT'].includes(descriptor.kind)?'FE-23.01':['MASTER_DATA','DATA_QUALITY'].includes(descriptor.kind)?'FE-27.03':descriptor.kind.startsWith('METER')||['meters','readings'].includes(descriptor.kind)?'FE-28.01':['stock','stock-movements','UOM_CONVERSION','TOOL_CUSTODY'].includes(descriptor.kind)?'FE-29.01':'FE-30.01',`Form ${descriptor.kind} render từ schema backend`,await form.locator('input,select,textarea').count()>0);}
    await admin.getByLabel('Nghiệp vụ',{exact:true}).selectOption('PURCHASE');await admin.getByRole('button',{name:'Chọn báo giá',exact:true}).click();const quoteSelect=admin.getByLabel('Báo giá được chọn',{exact:true});check('FE-30.02','Chỉ báo giá đã duyệt thuộc đề nghị mua xuất hiện',JSON.stringify(await quoteSelect.locator('option').evaluateAll(rows=>rows.map(r=>r.value).filter(Boolean)))===JSON.stringify([id.quote]));await quoteSelect.selectOption(id.quote);const quoteForm=admin.locator('form').filter({has:quoteSelect});await quoteForm.getByLabel('Lý do / kết luận').fill('Chọn báo giá phù hợp');await quoteForm.getByRole('button',{name:'Xác nhận chọn báo giá',exact:true}).click();check('FE-30.02','Chọn báo giá gửi đúng version',records.find(r=>r.id===id.purchase).data.selected_quote_id===id.quote);await shot(admin,'purchase-quote.png');
    await admin.getByLabel('Nghiệp vụ',{exact:true}).selectOption('CONTRACT');await admin.getByRole('button',{name:'Mốc nghiệm thu và nghĩa vụ còn lại',exact:true}).click();await admin.locator('summary').filter({hasText:'M1'}).click();await admin.getByText(/Giao đủ vật tư/).waitFor();check('FE-30.03','Tiến độ hợp đồng đọc nghĩa vụ và mốc nghiệm thu');
    await admin.getByLabel('Nghiệp vụ',{exact:true}).selectOption('readings');let form=admin.locator('form').filter({has:admin.getByRole('button',{name:'Lưu hồ sơ',exact:true})});await form.getByLabel('Đồng hồ',{exact:true}).selectOption(id.meter);await form.getByLabel('Ngày ghi chỉ số').fill('2026-10-11');await form.getByLabel('Chỉ số ghi').fill('1.2500');await form.getByLabel('Căn cứ / chứng từ').fill('MTR-R04');await form.getByRole('button',{name:'Lưu hồ sơ',exact:true}).click();await admin.getByRole('button',{name:'Xác minh độc lập',exact:true}).waitFor();check('FE-28.02','Chỉ số thập phân gửi nguyên chuỗi và chờ xác minh',readings[0].value==='1.2500'&&readings[0].status==='SUBMITTED');await shot(admin,'meter-readings.png');
    await admin.getByLabel('Nghiệp vụ',{exact:true}).selectOption('stock');await admin.getByText('Tồn khả dụng thấp hơn mức tối thiểu.',{exact:true}).waitFor();check('FE-29.04','Tồn thấp có cảnh báo và đề nghị bổ sung',await admin.getByRole('button',{name:'Lập đề nghị bổ sung từ tồn thấp',exact:true}).count()===1);
    await admin.getByLabel('Nghiệp vụ',{exact:true}).selectOption('stock-movements');form=admin.locator('form').filter({has:admin.getByRole('button',{name:'Lưu hồ sơ',exact:true})});await form.getByLabel('Vật tư',{exact:true}).selectOption(id.stock);await form.getByLabel('Loại nghiệp vụ',{exact:true}).selectOption('ISSUE');await form.getByLabel('Số lượng',{exact:true}).fill('2.0000');await form.getByLabel('Mã chứng từ',{exact:true}).fill('STK-R04');await form.getByLabel('Căn cứ / chứng từ').fill('Xuất vật tư');await form.getByRole('button',{name:'Lưu hồ sơ',exact:true}).click();await admin.getByRole('alert').filter({hasText:'Xuất kho vượt tồn'}).waitFor();check('FE-29.02','Vượt tồn hiển thị lỗi, không giảm tồn fixture',stock.quantity==='1.5000');await form.getByLabel('Số lượng',{exact:true}).fill('1.2500');await form.getByRole('button',{name:'Lưu hồ sơ',exact:true}).click();await admin.getByText('STK-R04',{exact:true}).first().waitFor();check('FE-29.02','Phiếu kho lưu số lẻ và version nguồn',movements[0].quantity==='1.2500'&&movements[0].expected_version===3);await shot(admin,'stock-movement.png');
    await tab(admin,'Trợ lý & CSKH');await admin.getByLabel('Nội dung cần hỗ trợ').fill('Tra cứu nội dung chưa có nguồn');await admin.getByRole('button',{name:'Tra cứu và lưu trao đổi',exact:true}).click();await admin.getByText('Chưa tìm thấy nguồn phù hợp. Có thể chuyển đến CSKH.',{exact:true}).waitFor();check('FE-26.01','Thiếu nguồn hiển thị nội dung thiếu căn cứ');await admin.getByLabel('Thao tác',{exact:true}).selectOption('HANDOFF');await admin.getByLabel('Danh mục tiếp nhận').selectOption(id.category);await admin.getByRole('button',{name:'Chuyển đến CSKH',exact:true}).click();await admin.getByText('Đã chuyển đến CSKH: SR-R04-01',{exact:true}).waitFor();check('FE-26.04','HANDOFF dùng cùng conversation và version hiện tại',commands.at(-1).body.conversation_id===conversations[0].id);await admin.getByRole('button',{name:'Xem nguồn',exact:true}).click();await admin.getByText('Nguồn khớp phiên bản phản hồi.',{exact:true}).waitFor();check('FE-26.04','Nguồn yêu cầu hỗ trợ mở được qua API xác thực');await shot(admin,'assistant-handoff.png');
    await admin.setViewportSize({width:390,height:844});await shot(admin,'assistant-mobile.png');check('COMMON','Trợ lý tại 390px không tràn ngang',await admin.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await admin.setViewportSize({width:1440,height:1000});await admin.getByRole('navigation',{name:'Điều hướng chính'}).getByRole('button',{name:'Thông báo',exact:true}).click();await admin.getByRole('button',{name:'Xác nhận tiếp nhận',exact:true}).waitFor();check('FE-25.01','Đọc đúng nội dung body từ backend',await admin.getByText('Đã đọc vẫn cần xác nhận',{exact:true}).count()===1);check('FE-25.02','Thông báo đã đọc vẫn cần ACK',notice.read_at && !notice.acknowledged_at);await admin.getByRole('button',{name:'Xác nhận tiếp nhận',exact:true}).click();await admin.getByText('Đã xác nhận tiếp nhận.',{exact:true}).waitFor();await admin.getByRole('button',{name:'Làm mới',exact:true}).click();await admin.getByText('Đã xác nhận tiếp nhận.',{exact:true}).waitFor();check('FE-25.02','ACK tải lại giữ trạng thái riêng và không còn nút xác nhận',await admin.getByRole('button',{name:'Xác nhận tiếp nhận',exact:true}).count()===0);await shot(admin,'staff-notification-ack.png');
    check('COMMON','Không có pageerror hay API ngoài fixture',errors.length===0&&unexpected.length===0);
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({source:'FIXTURE',passed:checks.length,checks,errors,unexpected,commands:commands.map(({api,body,role})=>({api,body,role}))},null,2));console.log(`R04 UX: ${checks.length} checks passed.`);
  } catch(error){for(const [i,c] of contexts.entries())for(const p of c.pages())await shot(p,`failure-${i}.png`);fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({source:'FIXTURE',checks,errors,unexpected,failure:error.message},null,2));throw error;}
  finally{await Promise.all(contexts.map(c=>c.close()));await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
