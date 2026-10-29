from datetime import datetime
from pathlib import Path
import os
import uuid
from zipfile import ZipFile

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from sqlalchemy import or_

from app.core.extensions import db
from app.models import Appeal, AppealAttachment, Task, User
from app.services.appeal_notifications import send_appeal_max_notification, send_appeal_mobile_push

appeals_bp = Blueprint('appeals', __name__, url_prefix='/appeals')


@appeals_bp.context_processor
def _appeals_workspace_context():
    from app.modules.hub.routes import build_home_context

    return {
        'workspace_nav': build_home_context(),
        'workspace_context_title': 'Обращения',
        'workspace_context_subtitle': 'Ответственные, сроки и результаты',
    }

ADMIN_ROLES = {'ADMIN', 'DEPUTY_DIRECTOR', 'DIRECTOR'}
SECRETARY_ROLES = {'SECRETARY_ACADEMIC', 'SECRETARY', 'ADMIN', 'DEPUTY_DIRECTOR', 'DIRECTOR'}
ALLOWED_EXT = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'zip', 'txt'}


def _can_view_all():
    return getattr(current_user, 'role', None) in ADMIN_ROLES | SECRETARY_ROLES


def _can_create():
    return getattr(current_user, 'role', None) in SECRETARY_ROLES


def _can_edit(appeal):
    uid = getattr(current_user, 'id', None)
    return _can_view_all() or uid in _appeal_responsible_ids(appeal) or appeal.creator_user_id == uid


def _responsible_match_filter(user_id):
    value = str(user_id)
    return or_(
        Appeal.responsible_user_id == user_id,
        Appeal.responsible_user_ids == value,
        Appeal.responsible_user_ids.like(f'{value},%'),
        Appeal.responsible_user_ids.like(f'%,{value},%'),
        Appeal.responsible_user_ids.like(f'%,{value}'),
    )


def _search_user_ids(text):
    text = (text or '').strip()
    if not text:
        return []
    like = f'%{text}%'
    users = (
        User.query
        .filter(or_(
            User.username.ilike(like),
            User.last_name.ilike(like),
            User.first_name.ilike(like),
            User.middle_name.ilike(like),
            User.role.ilike(like),
        ))
        .limit(100)
        .all()
    )
    return [user.id for user in users]


def _upload_root():
    root = current_app.config.get('UPLOAD_FOLDER') or os.path.abspath(os.path.join('data', 'uploads'))
    path = os.path.join(root, 'appeals')
    os.makedirs(path, exist_ok=True)
    return path


def _attachment_path(attachment):
    root = Path(current_app.config.get('UPLOAD_FOLDER') or os.path.abspath(os.path.join('data', 'uploads'))).resolve()
    path = (root / attachment.stored_path).resolve()
    if root not in path.parents:
        abort(404)
    return path


def _save_files(appeal, files):
    for f in files or []:
        if not f or not f.filename:
            continue
        ext = (Path(f.filename).suffix or '').lower().lstrip('.')
        if ext not in ALLOWED_EXT:
            flash(f'Файл {f.filename} пропущен: недопустимый тип.', 'warning')
            continue
        safe = secure_filename(f.filename) or 'file'
        name = f'{uuid.uuid4().hex}_{safe}'
        abs_path = os.path.join(_upload_root(), name)
        f.save(abs_path)
        db.session.add(AppealAttachment(
            appeal_id=appeal.id,
            original_filename=f.filename,
            stored_path=os.path.relpath(abs_path, current_app.config.get('UPLOAD_FOLDER') or os.path.abspath(os.path.join('data', 'uploads'))),
            uploaded_by_user_id=getattr(current_user, 'id', None),
        ))


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_responsible_ids():
    values = request.form.getlist('responsible_user_ids')
    if not values:
        legacy = request.form.get('responsible_user_id')
        values = [legacy] if legacy else []
    ids = []
    for value in values:
        try:
            uid = int(value)
        except (TypeError, ValueError):
            continue
        if uid and uid not in ids:
            ids.append(uid)
    return ids


def _apply_responsibles(appeal, responsible_ids):
    appeal.responsible_user_ids = ','.join(str(x) for x in responsible_ids) if responsible_ids else None
    appeal.responsible_user_id = responsible_ids[0] if responsible_ids else None


def _notify_new_responsibles(appeal, old_responsible_ids):
    old_ids = set(old_responsible_ids or [])
    for responsible_user in _appeal_responsible_users(appeal):
        if responsible_user.id not in old_ids:
            send_appeal_max_notification(appeal, user=responsible_user, notification_type='new_appeal')
            send_appeal_mobile_push(appeal, user=responsible_user, notification_type='new_appeal')


def _appeal_responsible_ids(appeal):
    ids = []
    raw = getattr(appeal, 'responsible_user_ids', None)
    if raw:
        for part in str(raw).split(','):
            try:
                uid = int(part.strip())
            except (TypeError, ValueError):
                continue
            if uid and uid not in ids:
                ids.append(uid)
    if getattr(appeal, 'responsible_user_id', None) and appeal.responsible_user_id not in ids:
        ids.insert(0, appeal.responsible_user_id)
    return ids


def _appeal_responsible_users(appeal):
    ids = _appeal_responsible_ids(appeal)
    if not ids:
        return []
    users = User.query.filter(User.id.in_(ids)).all()
    by_id = {u.id: u for u in users}
    return [by_id[i] for i in ids if i in by_id]


def _responsibles_text(appeal):
    users = _appeal_responsible_users(appeal)
    if not users:
        return 'не назначены'
    names = []
    for user in users:
        name = getattr(user, 'fio', None) or getattr(user, 'full_name', None) or getattr(user, 'display_name', None) or getattr(user, 'username', None) or f'ID {user.id}'
        names.append(name)
    return '\\n'.join(f'— {name}' for name in names)


def _responsibles_label(appeal):
    users = _appeal_responsible_users(appeal)
    if not users:
        return '—'
    names = []
    for user in users:
        name = getattr(user, 'fio', None) or getattr(user, 'full_name', None) or getattr(user, 'display_name', None) or getattr(user, 'username', None) or f'ID {user.id}'
        names.append(name)
    return ', '.join(names)


@appeals_bp.route('/')
@login_required
def index():
    q = Appeal.query
    if not _can_view_all():
        q = q.filter(_responsible_match_filter(current_user.id))
    status = request.args.get('status') or ''
    text = request.args.get('q') or ''
    if status:
        q = q.filter(Appeal.status == status)
    if text:
        like = f'%{text}%'
        search_filters = [
            Appeal.subject.ilike(like),
            Appeal.description.ilike(like),
            Appeal.applicant_name.ilike(like),
            Appeal.applicant_contact.ilike(like),
            Appeal.number.ilike(like),
            Appeal.result_text.ilike(like),
        ]
        for user_id in _search_user_ids(text):
            search_filters.append(_responsible_match_filter(user_id))
        q = q.filter(or_(*search_filters))
    appeals = q.order_by(Appeal.created_at.desc()).limit(300).all()
    for appeal in appeals:
        appeal.responsibles_label = _responsibles_label(appeal)
    counts = {
        'total': q.count(),
        'overdue': sum(1 for x in appeals if x.is_overdue),
        'new': sum(1 for x in appeals if x.status == 'Новое'),
        'closed': sum(1 for x in appeals if x.status == 'Закрыто'),
    }
    return render_template('appeals_index.html', appeals=appeals, counts=counts, statuses=Appeal.STATUS_CHOICES,
                           can_create=_can_create(), workspace_page_title='Реестр обращений',
                           workspace_page_subtitle='Заявители, ответственные, сроки и исполнение',
                           workspace_back_url=url_for('main.dashboard'), workspace_back_label='Главная')


@appeals_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if not _can_create():
        abort(403)
    users = User.query.filter_by(is_active_user=True).order_by(User.last_name.asc(), User.first_name.asc()).all()
    if request.method == 'POST':
        responsible_ids = _parse_responsible_ids()
        appeal = Appeal(
            number=request.form.get('number') or None,
            received_at=_parse_date(request.form.get('received_at')),
            applicant_name=request.form.get('applicant_name') or 'Без заявителя',
            applicant_contact=request.form.get('applicant_contact') or None,
            channel=request.form.get('channel') or None,
            subject=request.form.get('subject') or 'Обращение',
            description=request.form.get('description') or None,
            deadline_at=_parse_date(request.form.get('deadline_at')),
            status=request.form.get('status') or 'Новое',
            creator_user_id=current_user.id,
        )
        _apply_responsibles(appeal, responsible_ids)
        db.session.add(appeal)
        db.session.flush()
        _save_files(appeal, request.files.getlist('attachments'))
        if request.form.get('create_task') and appeal.responsible_user_id:
            task = Task(
                title=f'Подготовить ответ на обращение {appeal.number or appeal.id}',
                description=f'{appeal.subject}\n\n{appeal.description or ""}',
                creator_user_id=current_user.id,
                responsible_user_id=appeal.responsible_user_id,
                controller_user_id=current_user.id,
                deadline_at=datetime.combine(appeal.deadline_at, datetime.min.time()) if appeal.deadline_at else None,
                priority='обычный',
                status='Новая',
            )
            db.session.add(task)
            db.session.flush()
            appeal.linked_task_id = task.id
        db.session.commit()
        try:
            # Уведомляем всех ответственных
            _notify_new_responsibles(appeal, [])

            # Директору отправляем отдельное уведомление с перечнем ответственных
            directors = User.query.filter_by(role='DIRECTOR', is_active_user=True).all()
            for director in directors:
                send_appeal_max_notification(
                    appeal,
                    user=director,
                    notification_type='new_appeal',
                    extra_text="Ответственные:\n" + _responsibles_text(appeal)
                )
                send_appeal_mobile_push(
                    appeal,
                    user=director,
                    notification_type='new_appeal',
                    extra_text="Ответственные:\n" + _responsibles_text(appeal)
                )
        except Exception as exc:
            current_app.logger.warning("Appeal MAX notification failed: %s", exc)

        flash('Обращение добавлено.', 'success')
        return redirect(url_for('appeals.detail', appeal_id=appeal.id))
    return render_template('appeals_form.html', appeal=None, users=users, selected_responsible_ids=[],
                           selected_users=[], statuses=Appeal.STATUS_CHOICES, channels=Appeal.CHANNEL_CHOICES,
                           workspace_page_title='Новое обращение',
                           workspace_page_subtitle='Основные сведения и ответственные',
                           workspace_back_url=url_for('appeals.index'), workspace_back_label='К реестру')


@appeals_bp.route('/<int:appeal_id>', methods=['GET', 'POST'])
@login_required
def detail(appeal_id):
    appeal = Appeal.query.get_or_404(appeal_id)
    if not _can_edit(appeal):
        abort(403)
    users = User.query.filter_by(is_active_user=True).order_by(User.last_name.asc(), User.first_name.asc()).all()
    if request.method == 'POST':
        old_status = appeal.status
        old_responsible_ids = _appeal_responsible_ids(appeal)
        appeal.number = request.form.get('number') or None
        appeal.received_at = _parse_date(request.form.get('received_at'))
        appeal.applicant_name = request.form.get('applicant_name') or appeal.applicant_name
        appeal.applicant_contact = request.form.get('applicant_contact') or None
        appeal.channel = request.form.get('channel') or None
        appeal.subject = request.form.get('subject') or appeal.subject
        appeal.description = request.form.get('description') or None
        responsible_ids = _parse_responsible_ids()
        _apply_responsibles(appeal, responsible_ids)
        appeal.deadline_at = _parse_date(request.form.get('deadline_at'))
        appeal.status = 'Закрыто' if request.form.get('action') == 'close' else (request.form.get('status') or appeal.status)
        appeal.result_text = request.form.get('result_text') or None
        appeal.answered_at = _parse_date(request.form.get('answered_at'))
        if request.form.get('action') == 'close' and not appeal.answered_at:
            appeal.answered_at = datetime.utcnow().date()
        _save_files(appeal, request.files.getlist('attachments'))
        db.session.commit()

        try:
            _notify_new_responsibles(appeal, old_responsible_ids)
        except Exception as exc:
            current_app.logger.warning("Appeal responsible MAX notification failed: %s", exc)

        closed_statuses = {'Закрыто', 'Подготовлен ответ'}
        if old_status != appeal.status and appeal.status in closed_statuses:
            try:
                directors = User.query.filter_by(role='DIRECTOR', is_active_user=True).all()
                for director in directors:
                    send_appeal_max_notification(appeal, user=director, notification_type='appeal_closed')
                    send_appeal_mobile_push(appeal, user=director, notification_type='appeal_closed')
            except Exception as exc:
                current_app.logger.warning("Appeal close MAX notification failed: %s", exc)

        flash('Обращение сохранено.', 'success')
        return redirect(url_for('appeals.detail', appeal_id=appeal.id))
    attachments = [(attachment, _attachment_path(attachment).is_file()) for attachment in appeal.attachments]
    return render_template('appeals_detail.html', appeal=appeal, users=users,
                           selected_responsible_ids=_appeal_responsible_ids(appeal),
                           selected_users=_appeal_responsible_users(appeal),
                           attachments=attachments, statuses=Appeal.STATUS_CHOICES,
                           channels=Appeal.CHANNEL_CHOICES,
                           workspace_page_title=f'Обращение №{appeal.number or appeal.id}',
                           workspace_page_subtitle=f'{appeal.subject} · {appeal.applicant_name}',
                           workspace_back_url=url_for('appeals.index'), workspace_back_label='К реестру')


@appeals_bp.route('/<int:appeal_id>/delete', methods=['POST'])
@login_required
def delete(appeal_id):
    appeal = Appeal.query.get_or_404(appeal_id)
    role = getattr(current_user, 'role', None)
    if role not in (ADMIN_ROLES | SECRETARY_ROLES | {'DIRECTOR'}):
        abort(403)

    # Связанную задачу не удаляем автоматически, чтобы не потерять историю поручений.
    db.session.delete(appeal)
    db.session.commit()
    flash('Обращение удалено.', 'success')
    return redirect(url_for('appeals.index'))


@appeals_bp.route('/attachment/<int:attachment_id>')
@login_required
def download_attachment(attachment_id):
    att, path = _accessible_attachment(attachment_id)
    return send_file(path, as_attachment=True, download_name=att.original_filename)


def _accessible_attachment(attachment_id):
    att = AppealAttachment.query.get_or_404(attachment_id)
    if not _can_edit(att.appeal):
        abort(403)
    path = _attachment_path(att)
    if not path.is_file():
        current_app.logger.warning('Appeal attachment missing: attachment_id=%s appeal_id=%s', att.id, att.appeal_id)
        abort(404, description='Файл обращения отсутствует в хранилище.')
    return att, path


@appeals_bp.route('/attachment/<int:attachment_id>/inline')
@login_required
def inline_attachment(attachment_id):
    att, path = _accessible_attachment(attachment_id)
    ext = Path(att.original_filename or '').suffix.lower()
    mimetype = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}.get(ext)
    if not mimetype:
        abort(404)
    response = send_file(path, mimetype=mimetype, as_attachment=False, download_name=att.original_filename)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@appeals_bp.route('/attachment/<int:attachment_id>/preview')
@login_required
def preview_attachment(attachment_id):
    att, path = _accessible_attachment(attachment_id)
    ext = Path(att.original_filename or '').suffix.lower()
    preview_html = None
    inline_url = None
    archive_names = None
    preview_error = None

    try:
        if ext in {'.pdf', '.png', '.jpg', '.jpeg'}:
            inline_url = url_for('appeals.inline_attachment', attachment_id=att.id)
        elif ext in {'.txt', '.docx', '.xlsx'}:
            from app.documents import _render_docx_preview, _render_text_preview, _render_xlsx_preview
            renderer = {'.txt': _render_text_preview, '.docx': _render_docx_preview, '.xlsx': _render_xlsx_preview}[ext]
            preview_html = renderer(str(path))
        elif ext == '.zip':
            with ZipFile(path) as archive:
                archive_names = [item.filename for item in archive.infolist()[:100]]
        else:
            preview_error = 'Предпросмотр этого формата недоступен. Файл можно скачать.'
    except Exception:
        current_app.logger.exception('Appeal attachment preview failed: attachment_id=%s', att.id)
        preview_error = 'Не удалось открыть файл для просмотра. Файл можно скачать.'

    template = 'appeals_attachment_preview_embed.html' if request.args.get('embed') == '1' else 'appeals_attachment_preview.html'
    response = current_app.make_response(render_template(
        template, attachment=att, inline_url=inline_url,
        preview_html=preview_html, archive_names=archive_names, preview_error=preview_error,
        workspace_page_title=att.original_filename, workspace_page_subtitle='Файл обращения',
        workspace_back_url=url_for('appeals.detail', appeal_id=att.appeal_id), workspace_back_label='К обращению',
    ))
    response.headers['Cache-Control'] = 'no-store'
    return response
