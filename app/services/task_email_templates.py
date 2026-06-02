from __future__ import annotations

from datetime import datetime

from app.services.mail_settings_service import get_mail_config, get_organization_name

EVENT_LABELS = {
    'new_task': 'назначено новое поручение',
    'deadline_changed': 'изменен срок исполнения поручения',
    'comment_added': 'добавлен комментарий к поручению',
    'sent_to_review': 'поручение отправлено на проверку',
    'returned_for_rework': 'поручение возвращено на доработку',
    'closed': 'поручение закрыто',
    'overdue': 'поручение стало просроченным',
    'auto_created': 'автоматическое поручение создано системой',
}

TEMPLATES = {
    'new_task': {
        'subject': 'Вам назначено новое поручение',
        'full': '''Здравствуйте!

В системе {organization_name} для вас создано новое поручение.

Инициатор: {author_name}
Поручение: {task_title}
Срок исполнения: {due_date}

Для просмотра деталей и работы с поручением перейдите в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
        'safe': '''Здравствуйте!

В системе {organization_name} для вас создано новое поручение.

Подробности поручения доступны после входа в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
    },
    'deadline_changed': {
        'subject': 'Изменен срок исполнения поручения',
        'full': '''Здравствуйте!

В системе {organization_name} изменен срок исполнения поручения.

Поручение: {task_title}
Новый срок исполнения: {due_date}

Для просмотра деталей перейдите в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
        'safe': '''Здравствуйте!

В системе {organization_name} изменены параметры поручения.

Подробности доступны после входа в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
    },
    'comment_added': {
        'subject': 'Добавлен комментарий к поручению',
        'full': '''Здравствуйте!

В системе {organization_name} добавлен новый комментарий к поручению.

Поручение: {task_title}
Автор комментария: {author_name}

Для просмотра комментария перейдите в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
        'safe': '''Здравствуйте!

В системе {organization_name} добавлен новый комментарий к поручению.

Подробности доступны после входа в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
    },
    'sent_to_review': {
        'subject': 'Поручение ожидает проверки',
        'full': '''Здравствуйте!

В системе {organization_name} поручение переведено в статус проверки.

Поручение: {task_title}
Исполнитель: {executor_name}

Для просмотра деталей перейдите в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
        'safe': '''Здравствуйте!

В системе {organization_name} одно из поручений ожидает проверки.

Подробности доступны после входа в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
    },
    'returned_for_rework': {
        'subject': 'Поручение возвращено на доработку',
        'full': '''Здравствуйте!

В системе {organization_name} поручение возвращено на доработку.

Поручение: {task_title}
Проверяющий: {author_name}

Для просмотра замечаний и продолжения работы перейдите в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
        'safe': '''Здравствуйте!

В системе {organization_name} одно из поручений возвращено на доработку.

Подробности доступны после входа в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
    },
    'closed': {
        'subject': 'Поручение закрыто',
        'full': '''Здравствуйте!

В системе {organization_name} поручение закрыто.

Поручение: {task_title}

Для просмотра информации перейдите в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
        'safe': '''Здравствуйте!

В системе {organization_name} обновлен статус одного из поручений.

Подробности доступны после входа в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
    },
    'overdue': {
        'subject': 'Напоминание о просроченном поручении',
        'full': '''Здравствуйте!

В системе {organization_name} зафиксировано просроченное поручение.

Поручение: {task_title}
Срок исполнения истек: {due_date}

Для просмотра деталей и выполнения поручения перейдите в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
        'safe': '''Здравствуйте!

В системе {organization_name} имеется просроченное поручение, требующее внимания.

Подробности доступны после входа в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
    },
    'auto_created': {
        'subject': 'Создано новое системное поручение',
        'full': '''Здравствуйте!

В системе {organization_name} для вас автоматически создано новое поручение.

Поручение: {task_title}
Срок исполнения: {due_date}

Для просмотра деталей перейдите в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
        'safe': '''Здравствуйте!

В системе {organization_name} для вас создано новое системное поручение.

Подробности доступны после входа в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
    },
}


def _fmt_date(value):
    if not value:
        return 'не указан'
    if isinstance(value, datetime):
        if value.hour == 0 and value.minute == 0:
            return value.strftime('%d.%m.%Y')
        return value.strftime('%d.%m.%Y %H:%M')
    return str(value)


def _clean_lines(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    out = []
    empty = False
    for line in lines:
        if line.strip():
            out.append(line)
            empty = False
        else:
            if not empty:
                out.append('')
            empty = True
    return '\n'.join(out).strip() + '\n'


def _safe_value(value, fallback='не указано') -> str:
    if value is None:
        return fallback
    value = str(value).strip()
    return value or fallback


def build_task_email(task, user, notification_type: str, *, title: str | None = None, message: str | None = None, is_sensitive: bool = False):
    organization_name = get_organization_name() or 'school-tracker'
    cfg = get_mail_config()
    login_url = cfg.get('login_url') or ''
    author = getattr(getattr(task, 'creator', None), 'full_name', None) or getattr(getattr(task, 'creator', None), 'username', None) or ''
    executor = getattr(getattr(task, 'responsible_user', None), 'full_name', None) or getattr(getattr(task, 'responsible_user', None), 'username', None) or getattr(user, 'full_name', None) or getattr(user, 'username', None) or ''
    task_title = getattr(task, 'title', None) or title or 'Без названия'
    due_date = _fmt_date(getattr(task, 'deadline_at', None))

    template = TEMPLATES.get(notification_type, {
        'subject': title or 'Уведомление по поручению',
        'full': '''Здравствуйте!

В системе {organization_name} произошло обновление по поручению.

Событие: {event_label}
Поручение: {task_title}
Срок исполнения: {due_date}

Для просмотра информации перейдите в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
        'safe': '''Здравствуйте!

В системе {organization_name} имеется новое уведомление по поручению.

Подробности доступны после входа в систему:
{login_url}

Это письмо сформировано автоматически.
{organization_name}''',
    })

    values = {
        'organization_name': organization_name,
        'login_url': login_url,
        'author_name': _safe_value(author, 'не указан'),
        'executor_name': _safe_value(executor, 'не указан'),
        'task_title': _safe_value(task_title, 'Без названия'),
        'due_date': due_date,
        'comment_text': _safe_value(message, ''),
        'task_number': str(getattr(task, 'id', '') or ''),
        'event_label': EVENT_LABELS.get(notification_type, title or 'обновление по поручению'),
    }
    subject = (template['subject'] or title or 'Уведомление по поручению').format(**values)[:255]
    body_template = template['safe' if is_sensitive else 'full']
    body = _clean_lines(body_template.format(**values))
    return subject, body
