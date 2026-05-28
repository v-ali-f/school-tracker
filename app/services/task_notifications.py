from __future__ import annotations

from datetime import datetime

from flask import current_app

from app.core.extensions import db
from app.models import MaxBinding, TaskEmailLog
from app.services.bot_client import get_client as get_bot_client
from app.services.mail_settings_service import get_mail_config, send_mail_via_config
from app.services.task_email_templates import build_task_email

IMPORTANT_NOTIFICATION_TYPES = {
    'new_task', 'deadline_changed', 'overdue', 'returned_for_rework', 'sent_to_review', 'closed', 'auto_created'
}

SENSITIVE_TASK_TYPE_NAMES = {'сппс', 'сопровождение', 'психолог', 'логопед', 'дефектолог', 'тьютор'}


def is_important_notification(notification_type: str) -> bool:
    return (notification_type or '').strip() in IMPORTANT_NOTIFICATION_TYPES


def is_sensitive_task(task) -> bool:
    title = (getattr(task, 'title', '') or '').lower()
    task_type = getattr(getattr(task, 'task_type', None), 'name', '') or ''
    task_type = task_type.lower()
    return bool(getattr(task, 'is_private', False) or any(x in title for x in SENSITIVE_TASK_TYPE_NAMES) or any(x in task_type for x in SENSITIVE_TASK_TYPE_NAMES))


def make_email_content(task, user, notification_type: str, title: str, message: str):
    return build_task_email(
        task,
        user,
        notification_type,
        title=title,
        message=message,
        is_sensitive=is_sensitive_task(task),
    )




def _task_link(task) -> str:
    cfg = get_mail_config()
    base = (cfg.get('login_url') or '').rstrip('/')
    task_id = getattr(task, 'id', None)
    if base and task_id:
        return f'{base}/tasks/{task_id}'
    return base or ''


def _fmt_due_for_max(value) -> str:
    if not value:
        return 'не указан'
    if isinstance(value, datetime):
        return value.strftime('%d.%m.%Y %H:%M') if (value.hour or value.minute) else value.strftime('%d.%m.%Y')
    return str(value)


def build_task_max_message(task, user, notification_type: str, title: str, message: str) -> str:
    icon_map = {
        'new_task': '📌',
        'deadline_changed': '⏰',
        'comment_added': '💬',
        'sent_to_review': '🔎',
        'returned_for_rework': '↩️',
        'closed': '✅',
        'overdue': '⚠️',
        'auto_created': '🤖',
        'task_updated': '✏️',
        'status_changed': '🔄',
    }
    icon = icon_map.get(notification_type, '📣')
    task_id = getattr(task, 'id', None)
    is_sensitive = is_sensitive_task(task)
    task_title = 'служебная задача' if is_sensitive else (getattr(task, 'title', None) or 'Без названия')
    status = getattr(task, 'status', None) or '—'
    priority = getattr(task, 'priority', None) or '—'
    due = _fmt_due_for_max(getattr(task, 'deadline_at', None))
    link = _task_link(task)

    lines = [
        f'{icon} {title or "Уведомление по задаче"}',
        '',
        f'Задача: {task_title}',
        f'№: {task_id or "—"}',
        f'Статус: {status}',
        f'Приоритет: {priority}',
        f'Срок: {due}',
    ]
    if message and not is_sensitive:
        lines.extend(['', str(message).strip()[:500]])
    if link:
        lines.extend(['', f'Открыть в портале: {link}'])
    else:
        lines.extend(['', 'Откройте задачу в портале.'])
    return '\n'.join(lines).strip()



def _send_task_attachments_to_max(client, chat_id, task):
    """Отправляет вложения задачи в MAX после основного текстового уведомления.

    Ошибки по отдельному файлу не должны ломать уведомление по задаче.
    """
    attachments = getattr(task, 'attachments', None) or []
    sent_count = 0

    for attachment in attachments:
        if getattr(attachment, 'is_deleted', False):
            continue

        file_path = getattr(attachment, 'file_path', None)
        filename = getattr(attachment, 'filename', None) or getattr(attachment, 'stored_filename', None)

        if not file_path:
            continue

        try:
            client.notify_file(
                chat_id=chat_id,
                file_path=file_path,
                filename=filename,
                caption=f'Вложение к задаче №{getattr(task, "id", "")}: {getattr(task, "title", "") or "Без названия"}'
            )
            sent_count += 1
        except Exception:
            current_app.logger.exception(
                'Task MAX attachment send failed: task_id=%s attachment_id=%s path=%s',
                getattr(task, 'id', None),
                getattr(attachment, 'id', None),
                file_path,
            )

    return sent_count

def send_task_max_notification(task, user, notification_type: str, title: str, message: str):
    """Отправляет уведомление по задаче в MAX, если пользователь привязал бот.

    Не заменяет внутренние уведомления и email: это дополнительный канал.
    Ошибки не должны ломать создание/обновление задачи.
    """
    client = get_bot_client()
    if not client._enabled():
        return False

    try:
        binding = (
            MaxBinding.query
            .filter_by(user_id=getattr(user, 'id', None), status='done')
            .filter(MaxBinding.max_chat_id.isnot(None))
            .order_by(MaxBinding.id.desc())
            .first()
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Task MAX notification binding lookup failed')
        return False

    if not binding or not binding.max_chat_id:
        return False

    text = build_task_max_message(task, user, notification_type, title, message)
    try:
        client.notify_with_button(
            chat_id=binding.max_chat_id,
            text=text,
            buttons=[{
                "text": "✅ Выполнено",
                "payload": f"task_done:{getattr(task, 'id', '')}:{getattr(user, 'id', '')}"
            }]
        )
        attachments_sent = _send_task_attachments_to_max(client, binding.max_chat_id, task)
        current_app.logger.info(
            'Task MAX notification sent: task_id=%s user_id=%s chat_id=%s type=%s attachments_sent=%s',
            getattr(task, 'id', None),
            getattr(user, 'id', None),
            binding.max_chat_id,
            notification_type,
            attachments_sent,
        )
        return True
    except Exception:
        current_app.logger.exception(
            'Task MAX notification failed: task_id=%s user_id=%s chat_id=%s type=%s',
            getattr(task, 'id', None),
            getattr(user, 'id', None),
            binding.max_chat_id,
            notification_type,
        )
        return False


def send_task_email(task, user, notification_type: str, title: str, message: str):
    email_to = (getattr(user, 'email', '') or '').strip()
    subject, body = make_email_content(task, user, notification_type, title, message)
    log = TaskEmailLog(task_id=getattr(task, 'id', None), user_id=getattr(user, 'id', None), notification_type=notification_type, email_to=email_to, subject=subject, status='pending')
    db.session.add(log)

    cfg = get_mail_config()
    sender = cfg.get('sender_email') or cfg.get('smtp_username')

    if not email_to:
        log.status = 'skipped'
        log.error_text = 'У пользователя не указан email.'
        return False
    if not cfg.get('smtp_host') or not cfg.get('smtp_port') or not sender:
        log.status = 'skipped'
        log.error_text = 'SMTP не настроен.'
        return False

    try:
        send_mail_via_config(recipient=email_to, subject=subject, body=body)
        log.status = 'sent'
        log.sent_at = datetime.utcnow()
        return True
    except Exception as exc:
        current_app.logger.exception('Task email send failed')
        log.status = 'error'
        log.error_text = str(exc)[:2000]
        return False
