from __future__ import annotations
import uuid
from datetime import datetime
from pathlib import Path
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from app.core.extensions import db
from app.models import Familiarization, FamiliarizationRecipient, User
from app.services.familiarization_notifications import send_familiarization_max_notification

familiarizations_bp = Blueprint('familiarizations', __name__, url_prefix='/familiarizations')
MANAGER_ROLES = {'ADMIN','DIRECTOR','DEPUTY_DIRECTOR','SECRETARY','SECRETARY_ACADEMIC'}

def _is_manager(): return getattr(current_user, 'role', None) in MANAGER_ROLES

def _user_label(user): return getattr(user,'fio',None) or getattr(user,'full_name',None) or getattr(user,'username',None) or f'ID {user.id}'

def _active_users():
    q=User.query
    if hasattr(User,'is_active_user'): q=q.filter(User.is_active_user.is_(True))
    return q.order_by(User.last_name.asc().nullslast(), User.first_name.asc().nullslast(), User.username.asc()).all()

def _parse_deadline(value):
    value=(value or '').strip()
    if not value:
        return None

    # В интерфейсе оставляем только дату. В базе храним конец выбранного дня,
    # чтобы просрочка считалась после завершения этой даты.
    try:
        if 'T' in value:
            dt = datetime.strptime(value, '%Y-%m-%dT%H:%M')
        else:
            dt = datetime.strptime(value, '%Y-%m-%d')
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt
    except ValueError:
        return None

def _upload_root():
    base=Path(current_app.config.get('UPLOAD_FOLDER') or 'uploads')/'familiarizations'
    base.mkdir(parents=True, exist_ok=True); return base

def _save_file(file_storage):
    if not file_storage or not file_storage.filename: return None, None, None, None
    original=secure_filename(file_storage.filename) or 'document'
    ext='.'+original.rsplit('.',1)[1].lower() if '.' in original else ''
    stored=f'{uuid.uuid4().hex}{ext}'
    path=_upload_root()/stored; file_storage.save(path)
    return original, stored, file_storage.mimetype, path.stat().st_size

def _recipient_for(item_id, user_id): return FamiliarizationRecipient.query.filter_by(familiarization_id=item_id, user_id=user_id).first()

@familiarizations_bp.route('/')
@login_required
def index():
    if not _is_manager(): return redirect(url_for('familiarizations.my'))
    items=Familiarization.query.order_by(Familiarization.created_at.desc()).all(); stats={}; now=datetime.utcnow()
    for item in items:
        total=len(item.recipients); done=sum(1 for r in item.recipients if r.acknowledged_at)
        overdue=sum(1 for r in item.recipients if not r.acknowledged_at and item.deadline_at and item.deadline_at < now)
        stats[item.id]={'total':total,'done':done,'pending':total-done,'overdue':overdue}
    return render_template('familiarizations_index.html', items=items, stats=stats, is_manager=True)

@familiarizations_bp.route('/my')
@login_required
def my():
    rows=(FamiliarizationRecipient.query.filter_by(user_id=current_user.id).join(Familiarization).order_by(Familiarization.created_at.desc()).all())
    return render_template('familiarizations_my.html', rows=rows, now=datetime.utcnow())

@familiarizations_bp.route('/new', methods=['GET','POST'])
@login_required
def new():
    if not _is_manager(): abort(403)
    users=_active_users()
    if request.method=='POST':
        title=(request.form.get('title') or '').strip()
        if not title:
            flash('Укажите тему ознакомления.', 'danger'); return redirect(url_for('familiarizations.new'))
        recipient_ids=[]
        for value in request.form.getlist('recipient_user_ids'):
            try: uid=int(value)
            except (TypeError, ValueError): continue
            if uid and uid not in recipient_ids: recipient_ids.append(uid)
        if not recipient_ids:
            flash('Выберите хотя бы одного получателя.', 'danger'); return redirect(url_for('familiarizations.new'))
        original,stored,content_type,file_size=_save_file(request.files.get('document'))
        item=Familiarization(title=title, description=request.form.get('description') or None, deadline_at=_parse_deadline(request.form.get('deadline_at')), author_user_id=current_user.id, original_filename=original, stored_filename=stored, content_type=content_type, file_size=file_size)
        db.session.add(item); db.session.flush()
        selected_users=[u for u in users if u.id in recipient_ids]
        selected_recipient_names=[_user_label(u) for u in selected_users]
        selected_recipient_ids={u.id for u in selected_users}

        for user in selected_users: db.session.add(FamiliarizationRecipient(familiarization_id=item.id, user_id=user.id))
        db.session.commit()

        # Обычные уведомления получателям: с кнопкой «Ознакомлен».
        for user in selected_users:
            try:
                send_familiarization_max_notification(item, user, notification_type='new_familiarization')
            except Exception as exc:
                current_app.logger.warning('Familiarization MAX notification failed: %s', exc)

        # Служебное уведомление директору: только если директор НЕ является получателем,
        # чтобы не приходил дубль. В тексте показываем ФИО адресатов.
        try:
            directors = User.query.filter_by(role='DIRECTOR', is_active_user=True).all()
            for director in directors:
                if director.id in selected_recipient_ids:
                    continue
                send_familiarization_max_notification(
                    item,
                    director,
                    notification_type='director_new_familiarization',
                    recipient_names=selected_recipient_names,
                )
        except Exception as exc:
            current_app.logger.warning('Director familiarization MAX notification failed: %s', exc)

        flash(f'Ознакомление создано. Получателей: {len(selected_users)}.', 'success')
        return redirect(url_for('familiarizations.detail', item_id=item.id))
    return render_template('familiarizations_form.html', users=users)

@familiarizations_bp.route('/<int:item_id>', methods=['GET','POST'])
@login_required
def detail(item_id):
    item=Familiarization.query.get_or_404(item_id); recipient=_recipient_for(item.id, current_user.id)
    if not _is_manager() and not recipient: abort(403)
    if request.method=='POST':
        if not recipient: abort(403)
        if not recipient.acknowledged_at:
            recipient.acknowledged_at=datetime.utcnow(); db.session.commit(); flash('Ознакомление подтверждено.', 'success')
        return redirect(url_for('familiarizations.detail', item_id=item.id))
    now=datetime.utcnow(); total=len(item.recipients); done=sum(1 for r in item.recipients if r.acknowledged_at); overdue=sum(1 for r in item.recipients if not r.acknowledged_at and item.deadline_at and item.deadline_at < now)
    return render_template('familiarizations_detail.html', item=item, recipient=recipient, is_manager=_is_manager(), total=total, done=done, overdue=overdue, user_label=_user_label)

@familiarizations_bp.route('/<int:item_id>/download')
@login_required
def download(item_id):
    item=Familiarization.query.get_or_404(item_id)
    if not _is_manager() and not _recipient_for(item.id, current_user.id): abort(403)
    if not item.stored_filename: abort(404)
    path=_upload_root()/item.stored_filename
    if not path.exists(): abort(404)
    return send_file(path, as_attachment=True, download_name=item.original_filename or item.stored_filename)

@familiarizations_bp.route('/<int:item_id>/delete', methods=['POST'])
@login_required
def delete(item_id):
    if not _is_manager(): abort(403)
    item=Familiarization.query.get_or_404(item_id)
    if item.stored_filename:
        try: (_upload_root()/item.stored_filename).unlink(missing_ok=True)
        except Exception: current_app.logger.exception('Familiarization file delete failed')
    db.session.delete(item); db.session.commit(); flash('Ознакомление удалено.', 'success')
    return redirect(url_for('familiarizations.index'))
