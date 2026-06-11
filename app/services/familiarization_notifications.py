from __future__ import annotations
from datetime import date, datetime
from flask import current_app
from app.core.extensions import db
from app.models import MaxBinding
from app.services.bot_client import get_client as get_bot_client
from app.services.mail_settings_service import get_mail_config
from pathlib import Path
from sqlalchemy import text

def _portal_link(path: str) -> str:
    cfg = get_mail_config()
    base = (cfg.get('login_url') or '').rstrip('/') or 'http://10.172.85.55'
    return f'{base}{path}' if base else ''

def _fmt_date(value) -> str:
    if not value: return 'не указан'
    if isinstance(value, datetime): return value.strftime('%d.%m.%Y %H:%M') if (value.hour or value.minute) else value.strftime('%d.%m.%Y')
    if isinstance(value, date): return value.strftime('%d.%m.%Y')
    return str(value)


def _get_familiarization_attachments(item):
    """Возвращает список файлов ознакомления: новые множественные + старый одиночный fallback."""
    attachments = []
    item_id = getattr(item, 'id', None)

    if item_id:
        try:
            rows = db.session.execute(
                text('''
                    SELECT id, original_filename, stored_filename, content_type, file_size
                    FROM familiarization_attachment
                    WHERE familiarization_id = :item_id
                    ORDER BY id ASC
                '''),
                {'item_id': item_id}
            ).mappings().all()

            for row in rows:
                stored = row.get('stored_filename')
                if stored:
                    attachments.append({
                        'id': row.get('id'),
                        'original_filename': row.get('original_filename') or stored,
                        'stored_filename': stored,
                        'content_type': row.get('content_type'),
                        'file_size': row.get('file_size'),
                    })
        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                'Familiarization attachments lookup failed: familiarization_id=%s',
                item_id,
            )

    # Совместимость со старыми ознакомлениями, где был один файл в familiarization.stored_filename
    legacy_stored = getattr(item, 'stored_filename', None)
    if legacy_stored and not any(a.get('stored_filename') == legacy_stored for a in attachments):
        attachments.insert(0, {
            'id': None,
            'original_filename': getattr(item, 'original_filename', None) or legacy_stored,
            'stored_filename': legacy_stored,
            'content_type': getattr(item, 'content_type', None),
            'file_size': getattr(item, 'file_size', None),
        })

    return attachments


def _display_filename_for_max(item, attachment, file_path):
    stored = attachment.get('stored_filename')
    display_filename = attachment.get('original_filename') or stored or 'document'

    try:
        raw_name = (display_filename or '').strip()
        raw_lower = raw_name.lower()
        title_name = (getattr(item, 'title', None) or 'document').strip() or 'document'

        bad_names = {'pdf', 'doc', 'docx', 'file', 'document', 'документ'}
        ext = Path(raw_name).suffix or Path(stored or '').suffix

        if not ext:
            try:
                head = file_path.read_bytes()[:8]
                if head.startswith(b'%PDF'):
                    ext = '.pdf'
                elif head.startswith(b'PK'):
                    ext = '.docx'
            except Exception:
                ext = ''

        if (not raw_name) or (raw_lower in bad_names) or (Path(raw_name).suffix == ''):
            safe_title = ''.join(ch for ch in title_name if ch not in '\\/:"*?<>|').strip()
            display_filename = safe_title or 'document'
            if ext and not display_filename.lower().endswith(ext.lower()):
                display_filename += ext
        elif ext and not raw_name.lower().endswith(ext.lower()):
            display_filename = raw_name + ext

    except Exception:
        pass

    return display_filename

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
            f'{icon} Документ для ознакомления',
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
            f'{icon} Документ для ознакомления',
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
            attachments = _get_familiarization_attachments(item)
            if len(attachments) <= 1:
                download_link = _portal_link(f'/familiarizations/{getattr(item, "id")}/download')
                if download_link:
                    lines.extend(['', 'Откройте карточку ознакомления в портале или скачайте файл ниже.'])
                    lines.extend(['', 'После ознакомления нажмите кнопку «Ознакомлен».'])
                    lines.extend(['', f'Карточка: {download_link}'])
            else:
                lines.extend(['', f'Файлов: {len(attachments)}'])
                lines.extend(['', 'После ознакомления нажмите кнопку «Ознакомлен».'])

    return '\n'.join(lines).strip()


def _send_familiarization_file_to_max(client, chat_id, item):
    """Отправляет все файлы ознакомления в MAX после текстового уведомления."""
    attachments = _get_familiarization_attachments(item)
    if not attachments:
        return False

    upload_root = Path(current_app.config.get('UPLOAD_FOLDER') or 'uploads') / 'familiarizations'
    sent_any = False

    for index, attachment in enumerate(attachments, start=1):
        stored = attachment.get('stored_filename')
        if not stored:
            continue

        try:
            file_path = upload_root / stored

            if not file_path.exists() or not file_path.is_file():
                current_app.logger.warning(
                    'Familiarization file missing for MAX send: familiarization_id=%s path=%s',
                    getattr(item, 'id', None),
                    file_path,
                )
                continue

            display_filename = _display_filename_for_max(item, attachment, file_path)

            caption = f'Документ для ознакомления: {getattr(item, "title", "") or "без названия"}'
            if len(attachments) > 1:
                caption += f' ({index} из {len(attachments)})'

            client.notify_file(
                chat_id=chat_id,
                file_path=str(file_path),
                filename=display_filename,
                caption=caption
            )
            sent_any = True

        except Exception:
            current_app.logger.exception(
                'Familiarization MAX file send failed: familiarization_id=%s chat_id=%s stored=%s',
                getattr(item, 'id', None),
                chat_id,
                stored,
            )

    return sent_any

def send_familiarization_max_notification(item, user, notification_type: str = 'new_familiarization', recipient_names=None) -> bool:
    client = get_bot_client()
    if not client._enabled():
        current_app.logger.warning(
            'Familiarization MAX notification skipped: bot disabled familiarization_id=%s user_id=%s type=%s',
            getattr(item, 'id', None),
            getattr(user, 'id', None),
            notification_type,
        )
        return False
    user_id = getattr(user, 'id', None)
    if not user_id:
        current_app.logger.warning(
            'Familiarization MAX notification skipped: missing user familiarization_id=%s type=%s',
            getattr(item, 'id', None),
            notification_type,
        )
        return False
    try:
        binding = (MaxBinding.query.filter_by(user_id=user_id, status='done').filter(MaxBinding.max_chat_id.isnot(None)).order_by(MaxBinding.id.desc()).first())
    except Exception:
        db.session.rollback(); current_app.logger.exception('Familiarization MAX binding lookup failed'); return False
    if not binding or not binding.max_chat_id:
        current_app.logger.warning(
            'Familiarization MAX notification skipped: no binding familiarization_id=%s user_id=%s type=%s',
            getattr(item, 'id', None),
            user_id,
            notification_type,
        )
        return False
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
