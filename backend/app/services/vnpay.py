"""VNPay 2.1.0 signing. Browser Return never confirms a financial receipt.

Protocol: https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/pay.html
"""
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

from app.core.exceptions import AppError

VN_TIMEZONE = timezone(timedelta(hours=7))


def canonical_parameters(parameters):
    return urlencode(sorted((key, str(value)) for key, value in parameters.items()
        if key.startswith("vnp_") and key not in {"vnp_SecureHash", "vnp_SecureHashType"} and value not in {None, ""}))


def sign(parameters, secret):
    return hmac.new(secret.encode(), canonical_parameters(parameters).encode(), hashlib.sha512).hexdigest()


def verify(parameters, secret):
    supplied = parameters.get("vnp_SecureHash", "")
    return isinstance(supplied, str) and len(supplied) == 128 and hmac.compare_digest(sign(parameters, secret), supplied.lower())


def require_configuration(settings, tenant_id):
    if (not settings.vnpay_enabled or not settings.vnpay_tmn_code or not settings.vnpay_hash_secret
            or settings.vnpay_tenant_id != tenant_id or settings.vnpay_service_account_id is None
            or not settings.vnpay_return_url):
        raise AppError("ERR-PAYMENT-NOT-CONFIGURED", "Thanh toán VNPay chưa được cấu hình cho khu đô thị.", 503)
    target, callback = urlsplit(settings.vnpay_payment_url), urlsplit(settings.vnpay_return_url)
    if (target.scheme != "https" or target.username or target.password or target.query or target.fragment
            or target.hostname not in {"sandbox.vnpayment.vn", "pay.vnpay.vn"}):
        raise AppError("ERR-PAYMENT-NOT-CONFIGURED", "Địa chỉ VNPay không hợp lệ.", 503)
    if callback.scheme != "https" and not (settings.app_env != "production" and callback.hostname in {"localhost", "127.0.0.1"}):
        raise AppError("ERR-PAYMENT-NOT-CONFIGURED", "Địa chỉ nhận kết quả thanh toán cần HTTPS.", 503)


def payment_url(intent, settings, ip_address):
    require_configuration(settings, intent.tenant_id)
    created = intent.created_at or datetime.now(UTC)
    parameters = {
        "vnp_Version": "2.1.0", "vnp_Command": "pay", "vnp_TmnCode": settings.vnpay_tmn_code,
        "vnp_Amount": str(intent.amount_vnd * 100), "vnp_CurrCode": "VND", "vnp_TxnRef": intent.reference,
        "vnp_OrderInfo": "Thanh toan hoa don GreenCity " + intent.reference,
        "vnp_OrderType": "other", "vnp_Locale": "vn", "vnp_IpAddr": ip_address,
        "vnp_CreateDate": created.astimezone(VN_TIMEZONE).strftime("%Y%m%d%H%M%S"),
        "vnp_ExpireDate": intent.expires_at.astimezone(VN_TIMEZONE).strftime("%Y%m%d%H%M%S"),
        "vnp_ReturnUrl": settings.vnpay_return_url,
    }
    return settings.vnpay_payment_url + "?" + canonical_parameters(parameters) + "&vnp_SecureHash=" + sign(parameters, settings.vnpay_hash_secret.get_secret_value())


def payment_time(value):
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=VN_TIMEZONE).astimezone(UTC)
    except (TypeError, ValueError):
        raise AppError("ERR-PAYMENT-DATE", "Thời gian giao dịch VNPay không hợp lệ.", 422) from None


def pipe_sign(parameters, fields, secret):
    material = '|'.join(str(parameters.get(field, '')) for field in fields)
    return hmac.new(secret.encode(), material.encode(), hashlib.sha512).hexdigest()


def transaction_request(intent, settings, request_id, *, refund=None, created_by='', created_at=None):
    command = 'refund' if refund else 'querydr'
    payload = {'vnp_RequestId': request_id, 'vnp_Version': '2.1.0', 'vnp_Command': command,
        'vnp_TmnCode': settings.vnpay_tmn_code, 'vnp_TxnRef': intent.reference,
        'vnp_TransactionDate': intent.created_at.astimezone(VN_TIMEZONE).strftime('%Y%m%d%H%M%S'),
        'vnp_CreateDate': (created_at or datetime.now(UTC)).astimezone(VN_TIMEZONE).strftime('%Y%m%d%H%M%S'),
        'vnp_IpAddr': settings.vnpay_server_ip, 'vnp_OrderInfo': 'GreenCity ' + command + ' ' + intent.reference}
    fields = ['vnp_RequestId', 'vnp_Version', 'vnp_Command', 'vnp_TmnCode']
    if refund:
        payload.update(vnp_TransactionType='02' if refund == intent.provider_amount_vnd else '03',
            vnp_Amount=str(refund * 100), vnp_TransactionNo=intent.provider_transaction, vnp_CreateBy=created_by)
        fields += ['vnp_TransactionType', 'vnp_TxnRef', 'vnp_Amount', 'vnp_TransactionNo', 'vnp_TransactionDate', 'vnp_CreateBy']
    else:
        fields += ['vnp_TxnRef', 'vnp_TransactionDate']
    fields += ['vnp_CreateDate', 'vnp_IpAddr', 'vnp_OrderInfo']
    payload['vnp_SecureHash'] = pipe_sign(payload, fields, settings.vnpay_hash_secret.get_secret_value())
    return payload


def verify_transaction_response(payload, settings, intent, command):
    fields = ['vnp_ResponseId', 'vnp_Command', 'vnp_ResponseCode', 'vnp_Message', 'vnp_TmnCode',
        'vnp_TxnRef', 'vnp_Amount', 'vnp_BankCode', 'vnp_PayDate', 'vnp_TransactionNo',
        'vnp_TransactionType', 'vnp_TransactionStatus', 'vnp_OrderInfo']
    if command == 'querydr':
        fields += ['vnp_PromotionCode', 'vnp_PromotionAmount']
    expected = pipe_sign(payload, fields, settings.vnpay_hash_secret.get_secret_value())
    supplied = payload.get('vnp_SecureHash', '')
    return (isinstance(supplied, str) and hmac.compare_digest(expected, supplied.lower())
        and payload.get('vnp_TmnCode') == settings.vnpay_tmn_code
        and payload.get('vnp_TxnRef') == intent.reference and payload.get('vnp_Command') == command)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def call_transaction(settings, payload):
    target = urlsplit(settings.vnpay_api_url)
    payment = urlsplit(settings.vnpay_payment_url)
    if (target.scheme != 'https' or target.hostname != payment.hostname
            or target.hostname not in {'sandbox.vnpayment.vn', 'pay.vnpay.vn'}
            or target.path != '/merchant_webapi/api/transaction' or target.query or target.fragment
            or target.username or target.password):
        raise AppError('ERR-PAYMENT-NOT-CONFIGURED', 'API VNPay không hợp lệ.', 503)
    try:
        request = Request(settings.vnpay_api_url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            content = response.read(65537)
        if len(content) > 65536:
            raise ValueError('response too large')
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError('invalid response')
        return result
    except (OSError, ValueError):
        raise AppError('ERR-PAYMENT-PROVIDER', 'Chưa nhận được kết quả xác thực từ VNPay. Cần đối soát.', 502) from None
