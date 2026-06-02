from __future__ import annotations

from datetime import date, datetime

from flask import current_app

from app.core.extensions import db
from app.models import MaxBinding
from app.services.bot_client import get_client as get_bot_client
from app.services.mail_settings_service import get_mail_config


def _portal_link(path: str) -> str:
    cfg = get_mail_config()
    base = (cfg.get('login_url') or '').rstrip('/')
    return f'{base}{path}' if base else ''


def _fmt_date(value) -> str:
    if not value:
        return 'не указан'
    if isinstance(value, datetime):
        return value.strftime('%d.%m.%Y %H:%M') if (value.hour or value.minute) else value.strftime('%d.%m.%Y')
    if isinstance(value, date):
        return value.strftime('%d.%m.%Y')
    return str(value)


def build_appeal_max_message(appeal, notification_type: str = 'new_appeal') -> str:
    icon_map = {
        'new_appeal': '📨',
        'appeal_updated': '✏️',
        'appeal_deadline_changed': '⏰',
        'appeal_status_changed': '🔄',
        'appeal_overdue': '⚠️',
        'appeal_closed': '✅',
    }
    icon = icon_map.get(notification_type, '📣')
    appeal_id = getattr(appeal, 'id', None)
    number = getattr(appeal, 'number', None) or appeal_id or '—'
    subject = getattr(appeal, 'subject', None) or 'Обращение'
    applicant = getattr(appeal, 'applicant_name', None) or 'не указан'
    channel = getattr(appeal, 'channel', None) or 'не указан'
    status = getattr(appeal, 'status', None) or '—'
    deadline = _fmt_date(getattr(appeal, 'deadline_at', None))
    received = _fmt_date(getattr(appeal, 'received_at', None))
    link = _portal_link(f'/appeals/{appeal_id}') if appeal_id else ''

    lines = [
        f'{icon} Новое обращение',
        '',
        f'Обращение: {subject}',
        f'№: {number}',
        f'Заявитель: {applicant}',
        f'Канал: {channel}',
        f'Дата поступления: {received}',
        f'Статус: {status}',
        f'Срок ответа: {deadline}',
        '',
        'Вам назначено обращение для отработки.',
    ]
    description = (getattr(appeal, 'description', None) or '').strip()
    if description:
        lines.extend(['', description[:500]])
    if link:
        lines.extend(['', f'Открыть обращение в портале: {link}'])
    else:
        lines.extend(['', 'Откройте обращение в портале.'])
    return '\n'.join(lines).strip()


def send_appeal_max_notification(appeal, user=None, notification_type: str = 'new_appeal') -> bool:
    """Отправляет MAX-уведомление ответственному по обращению.

    Ошибки отправки не должны ломать создание/сохранение обращения.
    """
    client = get_bot_client()
    if not client._enabled():
        return False

    user_id = getattr(user, 'id', None) or getattr(appeal, 'responsible_user_id', None)
    if not user_id:
        return False

    try:
        binding = (
            MaxBinding.query
            .filter_by(user_id=user_id, status='done')
            .filter(MaxBinding.max_chat_id.isnot(None))
            .order_by(MaxBinding.id.desc())
            .first()
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Appeal MAX notification binding lookup failed')
        return False

    if not binding or not binding.max_chat_id:
        return False

    text = build_appeal_max_message(appeal, notification_type=notification_type)
    try:
        client.notify(chat_id=binding.max_chat_id, text=text)
        current_app.logger.info(
            'Appeal MAX notification sent: appeal_id=%s user_id=%s chat_id=%s type=%s',
            getattr(appeal, 'id', None),
            user_id,
            binding.max_chat_id,
            notification_type,
        )
        return True
    except Exception:
        current_app.logger.exception(
            'Appeal MAX notification failed: appeal_id=%s user_id=%s chat_id=%s type=%s',
            getattr(appeal, 'id', None),
            user_id,
            binding.max_chat_id,
            notification_type,
        )
        return False
