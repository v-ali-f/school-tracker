from __future__ import annotations
from datetime import date, datetime
from flask import current_app
from app.core.extensions import db
from app.models import MaxBinding
from app.services.bot_client import get_client as get_bot_client
from app.services.mail_settings_service import get_mail_config

def _portal_link(path: str) -> str:
    cfg = get_mail_config(); base = (cfg.get('login_url') or '').rstrip('/')
    return f'{base}{path}' if base else ''

def _fmt_date(value) -> str:
    if not value: return 'не указан'
    if isinstance(value, datetime): return value.strftime('%d.%m.%Y %H:%M') if (value.hour or value.minute) else value.strftime('%d.%m.%Y')
    if isinstance(value, date): return value.strftime('%d.%m.%Y')
    return str(value)

def build_familiarization_max_message(item, notification_type: str = 'new_familiarization') -> str:
    icon = {'new_familiarization':'📄','reminder':'⏰','acknowledged':'✅'}.get(notification_type,'📣')
    title = getattr(item, 'title', None) or 'Ознакомление'
    deadline = _fmt_date(getattr(item, 'deadline_at', None))
    link = _portal_link(f'/familiarizations/{getattr(item, "id", "")}') if getattr(item, 'id', None) else ''
    lines = [f'{icon} Новое ознакомление','',f'Документ: {title}',f'Срок ознакомления: {deadline}','','Откройте документ в портале и подтвердите ознакомление.']
    description = (getattr(item, 'description', None) or '').strip()
    if description: lines.extend(['', description[:500]])
    if link: lines.extend(['', f'Открыть в портале: {link}'])
    return '\n'.join(lines).strip()

def send_familiarization_max_notification(item, user, notification_type: str = 'new_familiarization') -> bool:
    client = get_bot_client()
    if not client._enabled(): return False
    user_id = getattr(user, 'id', None)
    if not user_id: return False
    try:
        binding = (MaxBinding.query.filter_by(user_id=user_id, status='done').filter(MaxBinding.max_chat_id.isnot(None)).order_by(MaxBinding.id.desc()).first())
    except Exception:
        db.session.rollback(); current_app.logger.exception('Familiarization MAX binding lookup failed'); return False
    if not binding or not binding.max_chat_id: return False
    text = build_familiarization_max_message(item, notification_type=notification_type)
    try:
        client.notify(chat_id=binding.max_chat_id, text=text)
        current_app.logger.info('Familiarization MAX notification sent: familiarization_id=%s user_id=%s chat_id=%s type=%s', getattr(item,'id',None), user_id, binding.max_chat_id, notification_type)
        return True
    except Exception:
        current_app.logger.exception('Familiarization MAX notification failed: familiarization_id=%s user_id=%s chat_id=%s type=%s', getattr(item,'id',None), user_id, binding.max_chat_id, notification_type)
        return False
