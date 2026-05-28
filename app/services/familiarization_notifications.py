from __future__ import annotations
from datetime import date, datetime
from flask import current_app
from app.core.extensions import db
from app.models import MaxBinding
from app.services.bot_client import get_client as get_bot_client
from app.services.mail_settings_service import get_mail_config
from pathlib import Path

def _portal_link(path: str) -> str:
    cfg = get_mail_config()
    base = (cfg.get('login_url') or '').rstrip('/') or 'http://10.172.85.55'
    return f'{base}{path}' if base else ''

def _fmt_date(value) -> str:
    if not value: return 'не указан'
    if isinstance(value, datetime): return value.strftime('%d.%m.%Y %H:%M') if (value.hour or value.minute) else value.strftime('%d.%m.%Y')
    if isinstance(value, date): return value.strftime('%d.%m.%Y')
    return str(value)

def build_familiarization_max_message(item, notification_type: str = 'new_familiarization') -> str:
    icon = {
        'new_familiarization': '📄',
        'director_new_familiarization': '📄',
        'reminder': '⏰',
        'acknowledged': '✅'
    }.get(notification_type, '📣')

    title = getattr(item, 'title', None) or 'Ознакомление'
    deadline = _fmt_date(getattr(item, 'deadline_at', None))
    link = _portal_link(f'/familiarizations/{getattr(item, "id", "")}') if getattr(item, 'id', None) else ''
    description = (getattr(item, 'description', None) or '').strip()

    if notification_type == 'director_new_familiarization':
        recipients = list(getattr(item, 'recipients', []) or [])
        total = len(recipients)
        author = getattr(item, 'author', None)
        author_name = (
            getattr(author, 'fio', None)
            or getattr(author, 'full_name', None)
            or getattr(author, 'username', None)
            or 'не указан'
        ) if author else 'не указан'

        lines = [
            f'{icon} Новое ознакомление сотрудников',
            '',
            f'Документ: {title}',
            f'Кто направил: {author_name}',
            f'Получателей: {total}',
            f'Срок ознакомления: {deadline}',
            '',
            'Документ и ход ознакомления доступны в портале.'
        ]
    else:
        lines = [
            f'{icon} Новое ознакомление',
            '',
            f'Документ: {title}',
            f'Срок ознакомления: {deadline}',
            '',
            'Откройте документ в портале и подтвердите ознакомление.'
        ]

    if description:
        lines.extend(['', description[:500]])
    # Ссылки оставляем только обычному получателю.
    # В директорском служебном уведомлении файл приходит отдельным вложением,
    # а карточку можно открыть из портала, поэтому ссылки убираем для компактности.
    if link and notification_type != 'director_new_familiarization':
        lines.extend(['', f'Открыть в портале: {link}'])

        if getattr(item, 'id', None):
            download_link = _portal_link(f'/familiarizations/{getattr(item, "id")}/download')
            if download_link:
                lines.extend(['', f'Скачать документ: {download_link}'])

    return '\n'.join(lines).strip()


def _send_familiarization_file_to_max(client, chat_id, item):
    """Отправляет файл ознакомления в MAX после текстового уведомления."""
    stored = getattr(item, 'stored_filename', None)
    if not stored:
        return False

    try:
        upload_root = Path(current_app.config.get('UPLOAD_FOLDER') or 'uploads') / 'familiarizations'
        file_path = upload_root / stored

        if not file_path.exists() or not file_path.is_file():
            current_app.logger.warning(
                'Familiarization file missing for MAX send: familiarization_id=%s path=%s',
                getattr(item, 'id', None),
                file_path,
            )
            return False

        display_filename = getattr(item, 'original_filename', None) or stored

        # Нормализуем имя файла для MAX.
        # Иногда браузер/форма сохраняет имя как просто "pdf" без точки и без нормального названия.
        # Тогда MAX показывает вложение некрасиво. Берём название ознакомления и добавляем расширение.
        try:
            raw_name = (display_filename or '').strip()
            raw_lower = raw_name.lower()
            title_name = (getattr(item, 'title', None) or 'document').strip() or 'document'

            bad_names = {'pdf', 'doc', 'docx', 'file', 'document', 'документ'}
            ext = Path(raw_name).suffix or Path(stored).suffix

            # Если расширение не удалось взять из имени/пути — определяем по содержимому.
            if not ext:
                try:
                    head = file_path.read_bytes()[:8]
                    if head.startswith(b'%PDF'):
                        ext = '.pdf'
                    elif head.startswith(b'PK'):
                        ext = '.docx'
                except Exception:
                    ext = ''

            # Если имя совсем техническое или без расширения — используем название ознакомления.
            if (not raw_name) or (raw_lower in bad_names) or (Path(raw_name).suffix == ''):
                safe_title = ''.join(ch for ch in title_name if ch not in '\\/:"*?<>|').strip()
                display_filename = safe_title or 'document'
                if ext and not display_filename.lower().endswith(ext.lower()):
                    display_filename += ext
            elif ext and not raw_name.lower().endswith(ext.lower()):
                display_filename = raw_name + ext

        except Exception:
            pass

        client.notify_file(
            chat_id=chat_id,
            file_path=str(file_path),
            filename=display_filename,
            caption=f'Документ для ознакомления: {getattr(item, "title", "") or "без названия"}'
        )
        return True
    except Exception:
        current_app.logger.exception(
            'Familiarization MAX file send failed: familiarization_id=%s chat_id=%s',
            getattr(item, 'id', None),
            chat_id,
        )
        return False

def send_familiarization_max_notification(item, user, notification_type: str = 'new_familiarization', recipient_names=None) -> bool:
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

    # В служебном уведомлении директору показываем, кому направлено ознакомление.
    if notification_type == 'director_new_familiarization' and recipient_names:
        names = [str(x).strip() for x in (recipient_names or []) if str(x).strip()]
        if names:
            shown = names[:10]
            text += "\n\nКому направлено:\n" + "\n".join(f"• {name}" for name in shown)
            if len(names) > len(shown):
                text += f"\n… и ещё {len(names) - len(shown)}"
    try:
        # Для получателя ознакомления отправляем кнопку «Ознакомлен».
        # Для директорского/служебного уведомления кнопка не нужна.
        if notification_type == 'new_familiarization':
            client.notify_with_button(
                chat_id=binding.max_chat_id,
                text=text,
                buttons=[{
                    "text": "✅ Ознакомлен",
                    "payload": f"fam_ack:{getattr(item, 'id', '')}:{user_id}",
                }]
            )
        else:
            client.notify(chat_id=binding.max_chat_id, text=text)

        file_sent = _send_familiarization_file_to_max(client, binding.max_chat_id, item)
        current_app.logger.info('Familiarization MAX notification sent: familiarization_id=%s user_id=%s chat_id=%s type=%s file_sent=%s', getattr(item,'id',None), user_id, binding.max_chat_id, notification_type, file_sent)
        return True
    except Exception:
        current_app.logger.exception('Familiarization MAX notification failed: familiarization_id=%s user_id=%s chat_id=%s type=%s', getattr(item,'id',None), user_id, binding.max_chat_id, notification_type)
        return False
