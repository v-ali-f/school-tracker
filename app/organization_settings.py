import os
import uuid
from flask import Blueprint, flash, redirect, render_template, request, url_for, current_app, send_from_directory
from app.core.extensions import db
from app.models import OrganizationSettings
from app.roles import require_roles
from app.services.org_settings_service import get_active_organization_settings, ensure_single_active_organization_settings, get_organization_header_lines, get_organization_signature_block
from werkzeug.utils import secure_filename

organization_settings_bp = Blueprint('organization_settings', __name__)

FIELDS = [
    'parent_org_name', 'full_name', 'short_name', 'legal_name',
    'city', 'address', 'postal_code', 'phone', 'fax', 'email', 'website',
    'okpo', 'ogrn', 'inn', 'kpp', 'director_name', 'director_position',
]
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'svg'}


def _value(name: str) -> str:
    return (request.form.get(name) or '').strip()


def _organization_media_dir() -> str:
    upload_root = current_app.config.get('UPLOAD_FOLDER') or os.path.abspath(os.path.join('data', 'uploads'))
    media_dir = os.path.join(upload_root, 'organization')
    os.makedirs(media_dir, exist_ok=True)
    return media_dir


def _is_allowed_image(filename: str) -> bool:
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def _remove_existing(relative_path: str | None) -> None:
    if not relative_path:
        return
    upload_root = current_app.config.get('UPLOAD_FOLDER') or os.path.abspath(os.path.join('data', 'uploads'))
    abs_path = os.path.join(upload_root, relative_path)
    try:
        if os.path.isfile(abs_path):
            os.remove(abs_path)
    except Exception:
        current_app.logger.exception('Не удалось удалить старый файл организации: %s', abs_path)


def _save_image(file_storage, prefix: str, current_path: str | None = None) -> str | None:
    if not file_storage or not getattr(file_storage, 'filename', ''):
        return current_path

    filename = secure_filename(file_storage.filename)
    if not _is_allowed_image(filename):
        raise ValueError('Допустимы только PNG, JPG, JPEG и SVG.')

    ext = filename.rsplit('.', 1)[1].lower()
    new_name = f'{prefix}_{uuid.uuid4().hex}.{ext}'
    media_dir = _organization_media_dir()
    file_storage.save(os.path.join(media_dir, new_name))

    if current_path and current_path != os.path.join('organization', new_name):
        _remove_existing(current_path)

    return os.path.join('organization', new_name)


@organization_settings_bp.route('/uploads/organization/<path:filename>')
def uploaded_media(filename):
    return send_from_directory(_organization_media_dir(), filename)



def ensure_olympiad_school_columns():
    try:
        db.session.execute(db.text("ALTER TABLE organization_settings ADD COLUMN IF NOT EXISTS olympiad_school_login VARCHAR(80)"))
        db.session.execute(db.text("ALTER TABLE organization_settings ADD COLUMN IF NOT EXISTS olympiad_ekis_code VARCHAR(80)"))
        db.session.execute(db.text("ALTER TABLE organization_settings ADD COLUMN IF NOT EXISTS olympiad_school_name VARCHAR(255)"))
        db.session.commit()
    except Exception:
        db.session.rollback()

@organization_settings_bp.route('/admin/organization-settings', methods=['GET', 'POST'])
@require_roles('ADMIN')
def edit():
    ensure_olympiad_school_columns()
    settings = OrganizationSettings.query.filter_by(is_active=True).order_by(OrganizationSettings.id.desc()).first()

    if request.method == 'POST':
        if not settings:
            settings = OrganizationSettings(is_active=True)
            db.session.add(settings)
            db.session.flush()

        for field in FIELDS:
            setattr(settings, field, _value(field) or None)

        make_active = (request.form.get('is_active') or '1').strip()
        settings.is_active = make_active not in {'0', 'false', 'False'}

        try:
            settings.logo_path = _save_image(request.files.get('logo_file'), 'logo', settings.logo_path)
            settings.emblem_path = _save_image(request.files.get('emblem_file'), 'emblem', settings.emblem_path)
        except ValueError as exc:
            flash(str(exc), 'danger')
            active_settings = settings or get_active_organization_settings()
            return render_template(
                'organization_settings_form.html',
                settings=active_settings,
                preview_header_lines=get_organization_header_lines(active_settings),
                preview_signature=get_organization_signature_block(active_settings),
            )

        if settings.is_active:
            others = OrganizationSettings.query.filter(OrganizationSettings.id != settings.id, OrganizationSettings.is_active.is_(True)).all() if settings.id else OrganizationSettings.query.filter_by(is_active=True).all()
            for item in others:
                item.is_active = False

        db.session.commit()
        try:
            ensure_single_active_organization_settings()
            db.session.commit()
        except Exception:
            db.session.rollback()

        settings.olympiad_school_login = (request.form.get('olympiad_school_login') or '').strip() or None
        settings.olympiad_ekis_code = (request.form.get('olympiad_ekis_code') or '').strip() or None
        settings.olympiad_school_name = (request.form.get('olympiad_school_name') or '').strip() or None

        flash('Настройки организации сохранены.', 'success')
        return redirect(url_for('organization_settings.edit'))

    active_settings = settings or get_active_organization_settings()
    return render_template(
        'organization_settings_form.html',
        settings=active_settings,
        preview_header_lines=get_organization_header_lines(active_settings),
        preview_signature=get_organization_signature_block(active_settings),
    )
