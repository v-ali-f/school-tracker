from __future__ import annotations
import uuid
from datetime import datetime
from pathlib import Path
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from app.core.extensions import db
from sqlalchemy import text
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

    if not file_storage or not file_storage.filename:

        return None, None, None, None

    # original_filename храним как пользовательское имя файла, включая кириллицу.

    # secure_filename используем только для технического имени на диске.

    raw_original = (file_storage.filename or "document").replace("\\", "/").split("/")[-1].strip()

    original = raw_original or "document"

    # Ограничиваем длину отображаемого имени, чтобы не упереться в VARCHAR(255).

    if len(original) > 240:

        stem = Path(original).stem[:200] or "document"

        suffix = Path(original).suffix[:20]

        original = f"{stem}{suffix}"

    safe_name = secure_filename(raw_original) or "document"

    ext = Path(safe_name).suffix or Path(original).suffix

    if len(ext) > 20:

        ext = ""

    stored = f"{uuid.uuid4().hex}{ext}"

    path = _upload_root() / stored

    file_storage.save(path)

    return original, stored, file_storage.mimetype, path.stat().st_size



def _ensure_attachment_table():
    engine_name = db.engine.dialect.name
    if engine_name == 'postgresql':
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS familiarization_attachment (
                id SERIAL PRIMARY KEY,
                familiarization_id INTEGER NOT NULL REFERENCES familiarization(id) ON DELETE CASCADE,
                original_filename VARCHAR(255),
                stored_filename VARCHAR(255) NOT NULL,
                content_type VARCHAR(255),
                file_size INTEGER,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        '''))
    else:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS familiarization_attachment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                familiarization_id INTEGER NOT NULL,
                original_filename VARCHAR(255),
                stored_filename VARCHAR(255) NOT NULL,
                content_type VARCHAR(255),
                file_size INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        '''))


def _attachment_rows(item_id):
    _ensure_attachment_table()
    rows = db.session.execute(
        text('''
            SELECT id, familiarization_id, original_filename, stored_filename, content_type, file_size, created_at
            FROM familiarization_attachment
            WHERE familiarization_id = :item_id
            ORDER BY id ASC
        '''),
        {'item_id': item_id}
    ).mappings().all()
    return list(rows)


def _insert_attachment(item_id, original, stored, content_type, file_size):
    _ensure_attachment_table()
    db.session.execute(
        text('''
            INSERT INTO familiarization_attachment
                (familiarization_id, original_filename, stored_filename, content_type, file_size)
            VALUES
                (:item_id, :original, :stored, :content_type, :file_size)
        '''),
        {
            'item_id': item_id,
            'original': original,
            'stored': stored,
            'content_type': content_type,
            'file_size': file_size,
        }
    )

def _recipient_for(item_id, user_id): return FamiliarizationRecipient.query.filter_by(familiarization_id=item_id, user_id=user_id).first()


def _notify_directors_about_familiarization(item, recipient_names=None):
    try:
        directors = (
            User.query
            .filter(User.role == 'DIRECTOR')
            .filter(User.is_active_user.isnot(False))
            .all()
        )
        for director in directors:
            send_familiarization_max_notification(
                item,
                director,
                notification_type='director_new_familiarization',
                recipient_names=recipient_names or [],
            )
    except Exception as exc:
        current_app.logger.warning('Director familiarization MAX notification failed: %s', exc)

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
        if len(title) > 240:
            flash('Тема документа слишком длинная. Сократите название до 240 символов.', 'danger')
            return redirect(url_for('familiarizations.new'))
        recipient_ids=[]
        for value in request.form.getlist('recipient_user_ids'):
            try: uid=int(value)
            except (TypeError, ValueError): continue
            if uid and uid not in recipient_ids: recipient_ids.append(uid)
        if not recipient_ids:
            flash('Выберите хотя бы одного получателя.', 'danger'); return redirect(url_for('familiarizations.new'))
        uploaded_files = [f for f in request.files.getlist('documents') if f and f.filename]
        if not uploaded_files:
            legacy_file = request.files.get('document')
            uploaded_files = [legacy_file] if legacy_file and legacy_file.filename else []

        saved_files = []
        for file_storage in uploaded_files:
            original, stored, content_type, file_size = _save_file(file_storage)
            if stored:
                saved_files.append((original, stored, content_type, file_size))

        first_file = saved_files[0] if saved_files else (None, None, None, None)
        original, stored, content_type, file_size = first_file

        item=Familiarization(title=title, description=request.form.get('description') or None, deadline_at=_parse_deadline(request.form.get('deadline_at')), author_user_id=current_user.id, original_filename=original, stored_filename=stored, content_type=content_type, file_size=file_size)
        db.session.add(item); db.session.flush()

        for original, stored, content_type, file_size in saved_files:
            _insert_attachment(item.id, original, stored, content_type, file_size)
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

        # Служебное уведомление директору: отдельный контрольный канал,
        # даже если директор также был среди получателей.
        _notify_directors_about_familiarization(item, selected_recipient_names)

        flash(f'Ознакомление создано. Получателей: {len(selected_users)}.', 'success')
        return redirect(url_for('familiarizations.detail', item_id=item.id))
    return render_template('familiarizations_form.html', users=users)


@familiarizations_bp.route('/<int:item_id>/forward', methods=['GET', 'POST'])
@login_required
def forward(item_id):
    item = Familiarization.query.get_or_404(item_id)
    recipient = _recipient_for(item.id, current_user.id)

    # Перенаправить может тот, кто сам имеет доступ к ознакомлению,
    # а также менеджер/директор/администратор.
    if not _is_manager() and not recipient:
        abort(403)

    existing_recipient_ids = {r.user_id for r in item.recipients}

    users = (
        User.query
        .filter(User.is_active_user.is_(True))
        .filter(User.id != current_user.id)
        .order_by(User.last_name.asc(), User.first_name.asc(), User.username.asc())
        .all()
    )

    available_users = [u for u in users if u.id not in existing_recipient_ids]

    if request.method == 'POST':
        recipient_ids = []
        for value in request.form.getlist('recipient_user_ids'):
            try:
                uid = int(value)
            except (TypeError, ValueError):
                continue

            if uid and uid not in recipient_ids and uid not in existing_recipient_ids:
                recipient_ids.append(uid)

        if not recipient_ids:
            flash('Выберите хотя бы одного нового получателя.', 'danger')
            return redirect(url_for('familiarizations.forward', item_id=item.id))

        selected_users = [u for u in available_users if u.id in recipient_ids]

        for user in selected_users:
            db.session.add(FamiliarizationRecipient(
                familiarization_id=item.id,
                user_id=user.id
            ))

        db.session.commit()

        # Уведомляем новых получателей в MAX.
        for user in selected_users:
            try:
                send_familiarization_max_notification(
                    item,
                    user,
                    notification_type='new_familiarization'
                )
            except Exception as exc:
                current_app.logger.warning('Forwarded familiarization MAX notification failed: %s', exc)

        _notify_directors_about_familiarization(
            item,
            [_user_label(user) for user in selected_users],
        )

        flash(f'Ознакомление перенаправлено. Новых получателей: {len(selected_users)}.', 'success')
        return redirect(url_for('familiarizations.detail', item_id=item.id))

    return render_template(
        'familiarizations_forward.html',
        item=item,
        users=available_users,
        user_label=_user_label,
    )



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
    attachments = _attachment_rows(item.id)
    if not attachments and item.stored_filename:
        attachments = [{
            'id': None,
            'original_filename': item.original_filename,
            'stored_filename': item.stored_filename,
            'content_type': item.content_type,
            'file_size': item.file_size,
        }]
    return render_template('familiarizations_detail.html', item=item, recipient=recipient, is_manager=_is_manager(), total=total, done=done, overdue=overdue, user_label=_user_label, attachments=attachments)

@familiarizations_bp.route('/<int:item_id>/download')
@login_required
def download(item_id):
    item=Familiarization.query.get_or_404(item_id)
    if not _is_manager() and not _recipient_for(item.id, current_user.id): abort(403)
    if not item.stored_filename: abort(404)
    path=_upload_root()/item.stored_filename
    if not path.exists(): abort(404)
    inline = request.args.get('inline') == '1'
    return send_file(path, as_attachment=not inline, download_name=item.original_filename or item.stored_filename)


@familiarizations_bp.route('/<int:item_id>/download/<int:attachment_id>')
@login_required
def download_attachment(item_id, attachment_id):
    item=Familiarization.query.get_or_404(item_id)
    if not _is_manager() and not _recipient_for(item.id, current_user.id): abort(403)

    _ensure_attachment_table()
    row = db.session.execute(
        text('''
            SELECT id, original_filename, stored_filename
            FROM familiarization_attachment
            WHERE id = :attachment_id AND familiarization_id = :item_id
        '''),
        {'attachment_id': attachment_id, 'item_id': item.id}
    ).mappings().first()

    if not row:
        abort(404)

    path = _upload_root() / row['stored_filename']
    if not path.exists():
        abort(404)

    return send_file(path, as_attachment=True, download_name=row['original_filename'] or row['stored_filename'])

@familiarizations_bp.route('/<int:item_id>/delete', methods=['POST'])
@login_required
def delete(item_id):
    item = Familiarization.query.get_or_404(item_id)
    if not _is_manager() and item.author_user_id != current_user.id:
        abort(403)
    try:
        for row in _attachment_rows(item.id):
            stored = row.get('stored_filename') if hasattr(row, 'get') else row['stored_filename']
            if stored:
                (_upload_root()/stored).unlink(missing_ok=True)
    except Exception:
        current_app.logger.exception('Familiarization attachments delete failed')

    if item.stored_filename:
        try: (_upload_root()/item.stored_filename).unlink(missing_ok=True)
        except Exception: current_app.logger.exception('Familiarization file delete failed')

    db.session.execute(text('DELETE FROM familiarization_attachment WHERE familiarization_id = :item_id'), {'item_id': item.id})
    db.session.delete(item); db.session.commit(); flash('Ознакомление удалено.', 'success')
    return redirect(url_for('familiarizations.index'))
