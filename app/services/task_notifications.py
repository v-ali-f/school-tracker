from __future__ import annotations

from datetime import datetime

from flask import current_app

from app.core.extensions import db
from app.models import TaskEmailLog
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
