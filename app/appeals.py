from datetime import datetime
from pathlib import Path
import os
import uuid

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from sqlalchemy import or_

from app.core.extensions import db
from app.models import Appeal, AppealAttachment, Task, User
from app.services.appeal_notifications import send_appeal_max_notification

appeals_bp = Blueprint('appeals', __name__, url_prefix='/appeals')

ADMIN_ROLES = {'ADMIN', 'DEPUTY_DIRECTOR', 'DIRECTOR'}
SECRETARY_ROLES = {'SECRETARY_ACADEMIC', 'SECRETARY', 'ADMIN', 'DEPUTY_DIRECTOR', 'DIRECTOR'}
ALLOWED_EXT = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'zip', 'txt'}


def _can_view_all():
    return getattr(current_user, 'role', None) in ADMIN_ROLES | SECRETARY_ROLES


def _can_create():
    return getattr(current_user, 'role', None) in SECRETARY_ROLES


def _can_edit(appeal):
    uid = getattr(current_user, 'id', None)
    return _can_view_all() or appeal.responsible_user_id == uid or appeal.creator_user_id == uid


def _upload_root():
    root = current_app.config.get('UPLOAD_FOLDER') or os.path.abspath(os.path.join('data', 'uploads'))
    path = os.path.join(root, 'appeals')
    os.makedirs(path, exist_ok=True)
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


@appeals_bp.route('/')
@login_required
def index():
    q = Appeal.query
    if not _can_view_all():
        q = q.filter(Appeal.responsible_user_id == current_user.id)
    status = request.args.get('status') or ''
    text = request.args.get('q') or ''
    if status:
        q = q.filter(Appeal.status == status)
    if text:
        like = f'%{text}%'
        q = q.filter(or_(Appeal.subject.ilike(like), Appeal.applicant_name.ilike(like), Appeal.number.ilike(like)))
    appeals = q.order_by(Appeal.created_at.desc()).limit(300).all()
    counts = {
        'total': q.count(),
        'overdue': sum(1 for x in appeals if x.is_overdue),
        'new': sum(1 for x in appeals if x.status == 'Новое'),
    }
    return render_template('appeals_index.html', appeals=appeals, counts=counts, statuses=Appeal.STATUS_CHOICES, can_create=_can_create())


@appeals_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if not _can_create():
        abort(403)
    users = User.query.filter_by(is_active_user=True).order_by(User.last_name.asc(), User.first_name.asc()).all()
    if request.method == 'POST':
        appeal = Appeal(
            number=request.form.get('number') or None,
            received_at=_parse_date(request.form.get('received_at')),
            applicant_name=request.form.get('applicant_name') or 'Без заявителя',
            applicant_contact=request.form.get('applicant_contact') or None,
            channel=request.form.get('channel') or None,
            subject=request.form.get('subject') or 'Обращение',
            description=request.form.get('description') or None,
            responsible_user_id=int(request.form.get('responsible_user_id') or 0) or None,
            deadline_at=_parse_date(request.form.get('deadline_at')),
            status=request.form.get('status') or 'Новое',
            creator_user_id=current_user.id,
        )
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
            send_appeal_max_notification(appeal, notification_type='new_appeal')
        except Exception as exc:
            current_app.logger.warning("Appeal MAX notification failed: %s", exc)

        flash('Обращение добавлено.', 'success')
        return redirect(url_for('appeals.detail', appeal_id=appeal.id))
    return render_template('appeals_form.html', appeal=None, users=users, statuses=Appeal.STATUS_CHOICES, channels=Appeal.CHANNEL_CHOICES)


@appeals_bp.route('/<int:appeal_id>', methods=['GET', 'POST'])
@login_required
def detail(appeal_id):
    appeal = Appeal.query.get_or_404(appeal_id)
    if not _can_edit(appeal):
        abort(403)
    users = User.query.filter_by(is_active_user=True).order_by(User.last_name.asc(), User.first_name.asc()).all()
    if request.method == 'POST':
        appeal.number = request.form.get('number') or None
        appeal.received_at = _parse_date(request.form.get('received_at'))
        appeal.applicant_name = request.form.get('applicant_name') or appeal.applicant_name
        appeal.applicant_contact = request.form.get('applicant_contact') or None
        appeal.channel = request.form.get('channel') or None
        appeal.subject = request.form.get('subject') or appeal.subject
        appeal.description = request.form.get('description') or None
        appeal.responsible_user_id = int(request.form.get('responsible_user_id') or 0) or None
        appeal.deadline_at = _parse_date(request.form.get('deadline_at'))
        appeal.status = request.form.get('status') or appeal.status
        appeal.result_text = request.form.get('result_text') or None
        appeal.answered_at = _parse_date(request.form.get('answered_at'))
        _save_files(appeal, request.files.getlist('attachments'))
        db.session.commit()
        flash('Обращение сохранено.', 'success')
        return redirect(url_for('appeals.detail', appeal_id=appeal.id))
    return render_template('appeals_detail.html', appeal=appeal, users=users, statuses=Appeal.STATUS_CHOICES, channels=Appeal.CHANNEL_CHOICES)


@appeals_bp.route('/attachment/<int:attachment_id>')
@login_required
def download_attachment(attachment_id):
    att = AppealAttachment.query.get_or_404(attachment_id)
    if not _can_edit(att.appeal):
        abort(403)
    root = current_app.config.get('UPLOAD_FOLDER') or os.path.abspath(os.path.join('data', 'uploads'))
    return send_file(os.path.join(root, att.stored_path), as_attachment=True, download_name=att.original_filename)
