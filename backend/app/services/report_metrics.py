"""Money metrics are computed from the frozen rows, never separate live queries."""
from collections import Counter
from datetime import datetime, UTC
from decimal import Decimal


DEFINITION = 'SAD-1'


def number_safe_json(value):
    """Preserve decimal quantities and integers outside JavaScript's exact range."""
    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(value, custom_encoder={Decimal:str, int:lambda n: str(n) if abs(n)>9007199254740991 else n})


def metrics(kind, rows, *, as_of=None):
    by={}
    for row in rows:by.setdefault(row['source'],[]).append(row['data'])
    counts=dict(Counter(r['source'] for r in rows))
    result={'record_counts':counts}
    if kind in ('PROJECT','COMMERCIAL','ENERGY','INSURANCE'):
        records = [r for r in by.get('operations_records', []) if r['status'] in ('APPROVED','IN_PROGRESS','COMPLETED','SENT','ACCEPTED','PAID')]
        def metric(value, unit, definition):
            return {'value':value,'unit':unit,'definition':definition,'data_status':'AVAILABLE'}
        if kind == 'PROJECT':
            projects = [r for r in records if r['kind'] == 'PROJECT']
            result['planned_vnd'] = metric(sum(r['data']['planned_vnd'] for r in projects),'VND','Tổng dự toán hiện hành của dự án được chọn.')
            result['accepted_vnd'] = metric(sum(r['data']['actual_vnd'] for r in records if r['kind']=='PROJECT_ACCEPTANCE'),'VND','Giá trị nghiệm thu được duyệt trong bộ lọc.')
            result['settled_vnd'] = metric(sum(r['data'].get('settled_vnd',0) for r in projects),'VND','Quyết toán đã đối chiếu chi phí và nghiệm thu.')
        elif kind == 'COMMERCIAL':
            entries = by.get('commercial_ledgers', [])
            result['receivable_vnd'] = metric(sum(r['amount_vnd']-r['received_vnd'] for r in entries if r['kind'] != 'DEPOSIT'),'VND','Tiền thuê và dịch vụ còn phải thu; tách tiền cọc.')
            result['deposit_held_vnd'] = metric(sum(r['received_vnd']-r['released_vnd']-r['deducted_vnd'] for r in entries if r['kind'] == 'DEPOSIT'),'VND','Cọc đã nhận trừ đã hoàn và khấu trừ.')
            result['cash_received_vnd'] = metric(sum(r['received_vnd'] for r in entries),'VND','Tiền thực nhận của các nghĩa vụ được chọn.')
        elif kind == 'ENERGY':
            # Each period keeps its own scope and definition; overlapping reports are never added.
            result['periods'] = [{'id':r['id'],'starts_on':r['data']['starts_on'],'ends_on':r['data']['ends_on'],**r['data']['analysis']} for r in records if r['kind']=='ENERGY_REPORT']
            result['savings'] = [{'id':r['id'], 'value':r['data']['saving_per_day'], 'unit':r['data']['uom']+'/day'} for r in records if r['kind']=='ENERGY_RESULT']
        else:
            result['accepted_vnd'] = metric(sum(r['data'].get('outcome',{}).get('amount_vnd',0) for r in records if r['kind']=='INSURANCE_CLAIM' and r['status'] in ('ACCEPTED','PAID')),'VND','Số được bên bảo hiểm chấp nhận; gửi hồ sơ không được tính.')
            result['paid_vnd'] = metric(sum(r['data']['outcome']['amount_vnd'] for r in records if r['kind']=='INSURANCE_CLAIM' and r['status']=='PAID'),'VND','Khoản bảo hiểm đã có chứng từ chi trả.')
        return result
    if kind=='FINANCIAL':
        cutoff=(as_of or datetime.now(UTC)).date().isoformat()
        invoices=[r for r in by.get('billing_invoices',[]) if r['status'] in ('ISSUED','PARTIALLY_PAID','PAID')]
        payments=[r for r in by.get('payments',[]) if r['status'] in ('RECEIVED','PARTIALLY_ALLOCATED','ALLOCATED','UNMATCHED')]
        allocations=by.get('payment_allocations',[])
        reversals=by.get('payment_allocation_reversals',[])
        expenses=[r for r in by.get('operational_expenses',[]) if r['status'] in ('APPROVED','PART_PAID','PAID','SETTLED')]
        settlements={r['data']['expense_id']:r['data']['actual_vnd'] for r in by.get('operations_records',[]) if r['kind']=='ADVANCE_SETTLEMENT' and r['status']=='COMPLETED'}
        actual=sum(r['paid_vnd'] for r in expenses if r['kind']!='ADVANCE')+sum(settlements.get(r['id'],0) for r in expenses if r['kind']=='ADVANCE' and r['status']=='SETTLED')
        missing_settlements=[r['id'] for r in expenses if r['kind']=='ADVANCE' and r['status']=='SETTLED' and r['id'] not in settlements]
        refunds=sum(r['amount_vnd'] for r in by.get('finance_commands',[]) if r['kind']=='PAYMENT_REFUND' and r['status']=='EXECUTED')
        funds=[r for r in by.get('treasury_accounts',[]) if r['kind']=='FUND' and r['status']=='ACTIVE']
        budgets=[r for r in by.get('treasury_accounts',[]) if r['kind']=='BUDGET' and r['status']=='ACTIVE']
        def metric(value,definition,window='FILTERED_ROWS'):
            if isinstance(value,int) and abs(value)>9007199254740991:value=str(value)
            return {'value':value,'unit':'VND','definition':definition,'window':window,'data_status':'AVAILABLE'}
        result.update({
            'invoiced_vnd':metric(sum(r['total_vnd'] for r in invoices),'Tổng hóa đơn phát hành trong bộ lọc.'),
            'receivable_vnd':metric(sum(r['outstanding_vnd'] for r in invoices),'Số còn phải thu của các hóa đơn đã chọn tại mốc chụp.'),
            'cash_received_vnd':metric(sum(r['amount_vnd'] for r in payments),'Tiền nhận có trạng thái hợp lệ; không phải tổng phân bổ.'),
            'cash_refunded_vnd':metric(refunds,'Hoàn tiền đã thực thi trong bộ lọc cho các khoản thu đã chọn.'),
            'cash_net_received_vnd':metric(sum(r['amount_vnd'] for r in payments)-refunds,'Tiền nhận hợp lệ trừ hoàn tiền thực thi cùng dataset; đảo nguồn thu được loại theo trạng thái.'),
            'allocated_vnd':metric(sum(r['amount_vnd'] for r in allocations)-sum(r['amount_vnd'] for r in reversals if r.get('allocation_id')),'Phân bổ tiền thu trừ đảo phân bổ có trong snapshot.'),
            'fund_balance_vnd':metric(sum(r['balance_vnd'] for r in funds),'Số dư quỹ hoạt động theo mục đích tại mốc chụp.','AT_CAPTURE'),
            'budget_commitment_vnd':metric(sum(r['reserved_vnd'] for r in budgets),'Ngân sách đã giữ cho cam kết chưa chi.','AT_CAPTURE'),
            'actual_expense_vnd':metric(None if missing_settlements else actual,'Chi phí đã trả của chứng từ chọn; tạm ứng đã quyết toán dùng actual_vnd, chưa quyết toán được tách riêng.'),
            'advance_pending_vnd':metric(sum(r['paid_vnd'] for r in expenses if r['kind']=='ADVANCE' and r['status']!='SETTLED'),'Tạm ứng đã trả và chưa quyết toán; không coi là chi phí thực tế.'),
            'expense_obligation_vnd':metric(sum(r['amount_vnd']-r['paid_vnd'] for r in expenses if r['kind']!='ADVANCE'),'Nghĩa vụ chi còn lại; không cộng vào thực chi.'),
            'disputed_vnd':metric(sum(r['amount_vnd'] for r in by.get('ar_cases',[]) if r['kind']=='DISPUTE' and r['status']=='OPEN'),'Khoản đang tranh chấp; nằm trong phải thu, không trừ hai lần.'),
            'ar_ledger_balance_vnd':metric(sum(r['debit_vnd']-r['credit_vnd'] for r in by.get('ar_ledger_entries',[])),'Phát sinh nợ thuần trong bộ lọc; không thay số còn phải thu.'),
            'external_accounting':{'value':None,'data_status':'NOT_CONFIGURED','definition':'Chưa chọn hợp đồng hệ thống kế toán đích.'}})
        result['funds_by_purpose']=[{'id':r['id'],'purpose':r['purpose'],'balance_vnd':r['balance_vnd']} for r in funds]
        if missing_settlements:result['actual_expense_vnd'].update({'data_status':'MISSING','missing_source_ids':missing_settlements})
        missing_due=any(r['outstanding_vnd'] and not r.get('due_on') for r in invoices)
        result['overdue_receivable_vnd']=metric(None if missing_due else sum(r['outstanding_vnd'] for r in invoices if r.get('due_on') and r['due_on']<cutoff),'Nợ quá hạn của hóa đơn chọn, dựa vào due_on tại mốc chụp; thiếu hạn trả được báo thiếu nguồn.')
        if missing_due:result['overdue_receivable_vnd']['data_status']='MISSING'
    elif kind=='SERVICE':
        requests=by.get('service_requests',[]); scores=[r['csat_score'] for r in requests if r.get('csat_score') is not None]
        result['csat']={'value':sum(scores)/len(scores) if scores else None,'data_status':'AVAILABLE' if scores else 'MISSING','definition':'Điểm CSAT trung bình của yêu cầu có đánh giá trong snapshot.'}
        result['sla_breaches']={'value':sum(bool(r.get('sla_breached_at')) for r in requests),'unit':'REQUEST','definition':'Yêu cầu đã ghi vi phạm SLA trong bộ lọc.'}
        result['repeat_causes']=dict(Counter(r.get('repeat_cause') or 'UNCLASSIFIED' for r in requests))
    elif kind=='RESIDENT':
        result['active_vehicle_registrations']={'value':sum(r['status']=='ACTIVE' for r in by.get('resident_vehicles',[])),'unit':'REGISTRATION','definition':'Đăng ký xe đang hoạt động trong bộ lọc.'}
        result['active_credentials']={'value':sum(r['status']=='ACTIVE' for r in by.get('resident_credentials',[])),'unit':'CREDENTIAL','definition':'Thẻ có trạng thái hoạt động; không xác nhận đồng bộ thiết bị.'}
        result['booking_statuses']=dict(Counter(r['status'] for r in by.get('resident_bookings',[])))
    elif kind=='OPERATIONS':
        cleaning=by.get('cleaning_tasks',[]);decided=[r for r in cleaning if r['status'] in ('ACCEPTED','REWORK_REQUIRED')]
        result['cleaning_acceptance_rate']={'value':sum(r['status']=='ACCEPTED' for r in decided)*100/len(decided) if decided else None,'unit':'PERCENT','data_status':'AVAILABLE' if decided else 'MISSING','definition':'Tỷ lệ đạt trong số nhiệm vụ đã có kết luận kiểm tra; chưa kết luận được tách riêng.'}
        result['incident_statuses']=dict(Counter(r['status'] for r in by.get('security_incidents',[])))
        result['cleaning_statuses']=dict(Counter(r['status'] for r in cleaning))
    elif kind=='STOCK':
        items=by.get('operational_stock_items',[]);units={}
        for row in items:
            uom=row['uom'];totals=units.setdefault(uom,{'on_hand':Decimal(0),'available':Decimal(0),'damaged':Decimal(0)})
            quantity=Decimal(str(row['quantity']));reserved=Decimal(str(row['reserved']));damaged=Decimal(str(row.get('damaged_quantity',0)))
            totals['on_hand']+=quantity;totals['available']+=quantity-reserved;totals['damaged']+=damaged
        result['quantities_by_uom']={uom:{k:str(v) for k,v in totals.items()} for uom,totals in units.items()}
        result['below_minimum_items']={'value':sum(Decimal(str(r['quantity']))-Decimal(str(r['reserved']))<Decimal(str(r['minimum'])) for r in items),'unit':'ITEM','definition':'Vật tư có tồn khả dụng dưới mức tối thiểu trong snapshot.'}
    elif kind=='METER':
        readings=by.get('operational_meter_readings',[]);meters={r['id']:r for r in by.get('operational_meters',[])};consumption={}
        for reading in readings:
            meter=meters.get(reading['meter_id'])
            if reading['status']=='VERIFIED' and meter:
                key=meter['commodity']+'/'+meter.get('uom','UNKNOWN');consumption[key]=consumption.get(key,Decimal(0))+Decimal(str(reading['consumption']))
        result['consumption_by_commodity_uom']={key:str(value) if not key.endswith('/UNKNOWN') else None for key,value in consumption.items()}
        result['meter_units']={'value':None,'data_status':'MISSING','definition':'Đơn vị đo chưa có trong metadata đồng hồ của snapshot; không cộng các lượng chưa xác định đơn vị.'} if any(key.endswith('/UNKNOWN') for key in consumption) else {'value':'Đã có đơn vị cho các lượng tổng hợp','data_status':'AVAILABLE','definition':'Không cộng chéo loại hoặc đơn vị đo.'}
        result['unverified_readings']={'value':sum(r['status']!='VERIFIED' for r in readings),'unit':'READING','definition':'Chỉ số đã ghi và chưa xác minh; không suy diễn số chỉ số chưa được ghi.'}
    elif kind=='DOSSIERS':
        result['records_by_kind_status']=dict(Counter(r['kind']+'/'+r['status'] for r in by.get('operations_records',[])))
    return result
