from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

from flask import current_app

from app.core.extensions import db
from app.models import MailSettingsLog, OrganizationSettings, SystemMailSettings


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def get_active_mail_settings():
    try:
        rows = SystemMailSettings.query.filter_by(is_active=True).order_by(SystemMailSettings.id.desc()).all()
        for row in rows:
            if (row.smtp_host or '').strip() and (row.sender_email or row.smtp_username or '').strip():
                return row
    except Exception:
        db.session.rollback()
    return None


def get_mail_config():
    row = get_active_mail_settings()
    if row:
        return {
            'source': 'db',
            'provider': row.provider or '',
            'smtp_host': row.smtp_host or '',
            'smtp_port': int(row.smtp_port or 0),
            'smtp_username': row.smtp_username or '',
            'smtp_password': row.smtp_password or '',
            'sender_email': row.sender_email or row.smtp_username or '',
            'use_ssl': bool(row.use_ssl),
            'use_tls': bool(row.use_tls),
            'login_url': row.login_url or '',
            'settings_id': row.id,
        }

    host = current_app.config.get('SMTP_HOST') or os.getenv('SMTP_HOST') or ''
    port = int(current_app.config.get('SMTP_PORT') or os.getenv('SMTP_PORT') or 0)
    username = current_app.config.get('SMTP_USERNAME') or os.getenv('SMTP_USERNAME') or ''
    password = current_app.config.get('SMTP_PASSWORD') or os.getenv('SMTP_PASSWORD') or ''
    sender = current_app.config.get('SMTP_SENDER') or os.getenv('SMTP_SENDER') or username
    use_tls = _as_bool(current_app.config.get('SMTP_USE_TLS') or os.getenv('SMTP_USE_TLS'), default=True)
    use_ssl = _as_bool(current_app.config.get('SMTP_USE_SSL') or os.getenv('SMTP_USE_SSL'), default=False)
    login_url = current_app.config.get('TASK_LOGIN_URL') or current_app.config.get('APP_BASE_URL') or os.getenv('TASK_LOGIN_URL') or ''
    return {
        'source': 'env',
        'provider': '',
        'smtp_host': host,
        'smtp_port': port,
        'smtp_username': username,
        'smtp_password': password,
        'sender_email': sender,
        'use_ssl': use_ssl,
        'use_tls': use_tls,
        'login_url': login_url,
        'settings_id': None,
    }


def get_organization_name():
    try:
        row = OrganizationSettings.query.filter_by(is_active=True).order_by(OrganizationSettings.id.desc()).first()
        if row:
            return row.short_name or row.full_name or row.legal_name or 'school-tracker'
    except Exception:
        db.session.rollback()
    return 'school-tracker'


def log_mail_settings_action(action_type: str, *, recipient: str | None = None, subject: str | None = None, status: str | None = None, error_text: str | None = None, created_by_user_id: int | None = None):
    try:
        row = MailSettingsLog(
            action_type=(action_type or '')[:50],
            recipient=(recipient or '')[:255] or None,
            subject=(subject or '')[:255] or None,
            status=(status or '')[:50] or None,
            error_text=(error_text or '')[:2000] or None,
            created_by_user_id=created_by_user_id,
        )
        db.session.add(row)
        db.session.commit()
        return row
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Не удалось записать журнал почтовых настроек')
        return None


def send_mail_via_config(*, recipient: str, subject: str, body: str):
    cfg = get_mail_config()
    host = cfg.get('smtp_host') or ''
    port = int(cfg.get('smtp_port') or 0)
    username = cfg.get('smtp_username') or ''
    password = cfg.get('smtp_password') or ''
    sender = cfg.get('sender_email') or username
    use_ssl = bool(cfg.get('use_ssl'))
    use_tls = bool(cfg.get('use_tls'))

    if not recipient:
        raise ValueError('Не указан адрес получателя.')
    if not host or not port or not sender:
        raise ValueError('SMTP не настроен. Заполните сервер, порт и адрес отправителя.')

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient
    msg.set_content(body)

    if use_ssl:
        server = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        server = smtplib.SMTP(host, port, timeout=15)

    with server:
        server.ehlo()
        if use_tls and not use_ssl:
            server.starttls()
            server.ehlo()
        if username and password:
            server.login(username, password)
        server.send_message(msg)

    return True


def send_test_mail(recipient: str):
    organization_name = get_organization_name()
    cfg = get_mail_config()
    subject = f'Тестовое письмо — {organization_name}'
    body = (
        f'Здравствуйте!\n\n'
        f'Это тестовое письмо из системы {organization_name}.\n\n'
        f'Источник настроек: {"База данных" if cfg.get("source") == "db" else ".env"}.\n'
        f'Ссылка на систему: {cfg.get("login_url") or "не указана"}\n\n'
        f'Письмо сформировано автоматически {datetime.now().strftime("%d.%m.%Y %H:%M")}.\n'
    )
    return send_mail_via_config(recipient=recipient, subject=subject, body=body)
