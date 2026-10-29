"""SMTP delivery uses only an address verified by an authenticated manager."""
import smtplib
import ssl
from email.message import EmailMessage

from app.core.exceptions import AppError


def require_smtp(settings):
    if (not settings.smtp_enabled or not settings.smtp_host or not settings.smtp_from_email
            or any(c in settings.smtp_host + settings.smtp_from_email for c in '\r\n')
            or (settings.smtp_username and not settings.smtp_password)):
        raise AppError("ERR-MAIL-NOT-CONFIGURED", "SMTP chưa được cấu hình đầy đủ.", 503)


def send_recovery(settings, email, request_id, token, expires_at):
    return send_message(settings, email, 'GreenCity - Khôi phục tài khoản',
        f'Yêu cầu khôi phục: {request_id}\nMã dùng một lần: {token}\nHết hạn: {expires_at.isoformat()}\n'
        f'Mở {settings.portal_public_url.rstrip("/")} rồi chọn hỗ trợ đăng nhập để đặt mật khẩu mới.\nKhông chia sẻ mã này.')


def send_invitation(settings, email, request_id, token, expires_at):
    return send_message(settings, email, 'GreenCity - Mời kích hoạt tài khoản',
        f'Mã lời mời: {request_id}\nMã kích hoạt dùng một lần: {token}\nHết hạn: {expires_at.isoformat()}\n'
        f'Mở {settings.portal_public_url.rstrip("/")} rồi chọn kích hoạt tài khoản.\nKhông chia sẻ mã này.')


def send_email_verification(settings, email, request_id, token, expires_at):
    return send_message(settings, email, 'GreenCity - Xác minh email tài khoản',
        f'Mã yêu cầu: {request_id}\nMã xác minh email dùng một lần: {token}\nHết hạn: {expires_at.isoformat()}\n'
        f'Mở {settings.portal_public_url.rstrip("/")} rồi vào Tài khoản để xác nhận.\nKhông chia sẻ mã này.')


def send_message(settings, email, subject, body):
    require_smtp(settings)
    message = EmailMessage()
    message['From'] = settings.smtp_from_email
    message['To'] = email
    message['Subject'] = subject
    message.set_content(body)
    transport = smtplib.SMTP_SSL if settings.smtp_security == 'ssl' else smtplib.SMTP
    kwargs = {'timeout': settings.smtp_timeout_seconds}
    if settings.smtp_security == 'ssl':
        kwargs['context'] = ssl.create_default_context()
    with transport(settings.smtp_host, settings.smtp_port, **kwargs) as connection:
        if settings.smtp_security == 'starttls':
            connection.ehlo()
            connection.starttls(context=ssl.create_default_context())
            connection.ehlo()
        if settings.smtp_username:
            connection.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        rejected = connection.send_message(message)
        if rejected:
            raise smtplib.SMTPException('Recipient rejected')
