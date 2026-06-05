from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.core.extensions import db
from app.models import DocumentRegistryAccess, DocumentRegistryRecord, User
from app.permissions import has_any_role


document_registers_bp = Blueprint("document_registers", __name__, url_prefix="/documents/registers")
document_registers_bp.url_map_strict_slashes = False


REGISTRIES = [
    ("incoming", "Входящие документы"),
    ("outgoing", "Исходящие документы"),
]
REGISTRY_MAP = dict(REGISTRIES)

STATUS_CHOICES = [
    ("registered", "Зарегистрирован"),
    ("in_progress", "В работе"),
    ("completed", "Исполнен"),
    ("archived", "Архив"),
]
STATUS_MAP = dict(STATUS_CHOICES)


def _is_document_registry_manager():
    return has_any_role("ADMIN", "DIRECTOR")


def _sorted_users():
    return User.query.order_by(User.last_name.asc(), User.first_name.asc(), User.middle_name.asc()).all()


def _allowed_registries(mode="view"):
    if _is_document_registry_manager():
        return [code for code, _label in REGISTRIES]

    access_types = ("editor",) if mode == "edit" else ("editor", "viewer")
    rows = (
        DocumentRegistryAccess.query
        .filter(
            DocumentRegistryAccess.user_id == getattr(current_user, "id", None),
            DocumentRegistryAccess.access_type.in_(access_types),
        )
        .order_by(DocumentRegistryAccess.registry_type.asc())
        .all()
    )
    valid = {code for code, _label in REGISTRIES}
    result = []
    for row in rows:
        if row.registry_type in valid and row.registry_type not in result:
            result.append(row.registry_type)
    return result


def _registry_or_404(registry_type):
    registry_type = (registry_type or "").strip()
    if registry_type not in REGISTRY_MAP:
        abort(404)
    return registry_type


def _can_view_registry(registry_type):
    return registry_type in _allowed_registries("view")


def _can_edit_registry(registry_type):
    return registry_type in _allowed_registries("edit")


def _registry_access_required(registry_type=None, mode="view"):
    if registry_type:
        registry_type = _registry_or_404(registry_type)
        allowed = _allowed_registries(mode)
        if registry_type not in allowed:
            abort(403)
        return registry_type

    if not _allowed_registries(mode):
        abort(403)
    return None


def _settings_required():
    if not _is_document_registry_manager():
        abort(403)


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _record_from_form(item, registry_type):
    item.registry_type = registry_type
    item.number = (request.form.get("number") or "").strip()
    item.doc_date = _parse_date(request.form.get("doc_date"))
    item.subject = (request.form.get("subject") or "").strip()
    item.correspondent = (request.form.get("correspondent") or "").strip() or None
    item.delivery_method = (request.form.get("delivery_method") or "").strip() or None
    item.status = (request.form.get("status") or "registered").strip()
    item.notes = (request.form.get("notes") or "").strip() or None

    responsible_raw = (request.form.get("responsible_user_id") or "").strip()
    try:
        item.responsible_user_id = int(responsible_raw) if responsible_raw else None
    except ValueError:
        item.responsible_user_id = None

    return item


def _validate_record(item):
    errors = []
    if not item.number:
        errors.append("Укажите регистрационный номер.")
    if not item.doc_date:
        errors.append("Укажите дату документа.")
    if not item.subject:
        errors.append("Укажите краткое содержание документа.")
    if item.status not in STATUS_MAP:
        errors.append("Выберите корректный статус.")
    return errors


@document_registers_bp.route("/")
@login_required
def index():
    _registry_access_required()
    allowed = _allowed_registries("view")
    first = allowed[0] if allowed else "incoming"
    return redirect(url_for("document_registers.registry", registry_type=first))


@document_registers_bp.route("/<registry_type>")
@login_required
def registry(registry_type):
    registry_type = _registry_access_required(registry_type, mode="view")

    allowed = _allowed_registries("view")
    visible_registries = [(code, label) for code, label in REGISTRIES if code in allowed]
    can_edit = _can_edit_registry(registry_type)

    query_text = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    responsible_id = request.args.get("responsible_id", type=int)

    query = DocumentRegistryRecord.query.filter_by(registry_type=registry_type)
    if query_text:
        like = f"%{query_text}%"
        query = query.filter(or_(
            DocumentRegistryRecord.number.ilike(like),
            DocumentRegistryRecord.subject.ilike(like),
            DocumentRegistryRecord.correspondent.ilike(like),
        ))
    if status in STATUS_MAP:
        query = query.filter(DocumentRegistryRecord.status == status)
    if responsible_id:
        query = query.filter(DocumentRegistryRecord.responsible_user_id == responsible_id)

    items = query.order_by(
        DocumentRegistryRecord.doc_date.desc(),
        DocumentRegistryRecord.number.desc(),
        DocumentRegistryRecord.id.desc(),
    ).all()

    return render_template(
        "document_registers_registry.html",
        registry_type=registry_type,
        registry_label=REGISTRY_MAP[registry_type],
        visible_registries=visible_registries,
        items=items,
        q=query_text,
        status=status,
        responsible_id=responsible_id,
        status_choices=STATUS_CHOICES,
        status_map=STATUS_MAP,
        users=_sorted_users(),
        can_edit=can_edit,
        is_manager=_is_document_registry_manager(),
    )


@document_registers_bp.route("/<registry_type>/new", methods=["GET", "POST"])
@login_required
def create(registry_type):
    registry_type = _registry_access_required(registry_type, mode="edit")
    users = _sorted_users()

    item = DocumentRegistryRecord(
        registry_type=registry_type,
        status="registered",
        created_by_id=getattr(current_user, "id", None),
    )

    if request.method == "POST":
        _record_from_form(item, registry_type)
        errors = _validate_record(item)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "document_registers_form.html",
                item=item,
                registry_type=registry_type,
                registry_label=REGISTRY_MAP[registry_type],
                status_choices=STATUS_CHOICES,
                users=users,
                read_only=False,
                can_edit=True,
            )
        db.session.add(item)
        db.session.commit()
        flash("Документ добавлен в реестр.", "success")
        return redirect(url_for("document_registers.registry", registry_type=registry_type))

    return render_template(
        "document_registers_form.html",
        item=None,
        registry_type=registry_type,
        registry_label=REGISTRY_MAP[registry_type],
        status_choices=STATUS_CHOICES,
        users=users,
        read_only=False,
        can_edit=True,
    )


@document_registers_bp.route("/<registry_type>/<int:record_id>")
@login_required
def detail(registry_type, record_id):
    registry_type = _registry_access_required(registry_type, mode="view")
    item = DocumentRegistryRecord.query.get_or_404(record_id)
    if item.registry_type != registry_type:
        abort(404)

    return render_template(
        "document_registers_form.html",
        item=item,
        registry_type=registry_type,
        registry_label=REGISTRY_MAP[registry_type],
        status_choices=STATUS_CHOICES,
        users=_sorted_users(),
        read_only=True,
        can_edit=_can_edit_registry(registry_type),
    )


@document_registers_bp.route("/<registry_type>/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
def edit(registry_type, record_id):
    registry_type = _registry_access_required(registry_type, mode="edit")
    item = DocumentRegistryRecord.query.get_or_404(record_id)
    if item.registry_type != registry_type:
        abort(404)
    users = _sorted_users()

    if request.method == "POST":
        _record_from_form(item, registry_type)
        errors = _validate_record(item)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "document_registers_form.html",
                item=item,
                registry_type=registry_type,
                registry_label=REGISTRY_MAP[registry_type],
                status_choices=STATUS_CHOICES,
                users=users,
                read_only=False,
                can_edit=True,
            )
        db.session.commit()
        flash("Изменения сохранены.", "success")
        return redirect(url_for("document_registers.registry", registry_type=registry_type))

    return render_template(
        "document_registers_form.html",
        item=item,
        registry_type=registry_type,
        registry_label=REGISTRY_MAP[registry_type],
        status_choices=STATUS_CHOICES,
        users=users,
        read_only=False,
        can_edit=True,
    )


@document_registers_bp.route("/<registry_type>/<int:record_id>/delete", methods=["POST"])
@login_required
def delete(registry_type, record_id):
    registry_type = _registry_access_required(registry_type, mode="edit")
    item = DocumentRegistryRecord.query.get_or_404(record_id)
    if item.registry_type != registry_type:
        abort(404)
    db.session.delete(item)
    db.session.commit()
    flash("Запись удалена.", "success")
    return redirect(url_for("document_registers.registry", registry_type=registry_type))


@document_registers_bp.route("/access", methods=["GET", "POST"])
@login_required
def access():
    _settings_required()

    if request.method == "POST":
        registry_type = _registry_or_404(request.form.get("registry_type"))
        DocumentRegistryAccess.query.filter_by(registry_type=registry_type).delete()

        editor_user_ids = set()
        seen_access = set()
        for access_type, field_name in (("editor", "editor_ids"), ("viewer", "viewer_ids")):
            for raw_user_id in request.form.getlist(field_name):
                try:
                    user_id = int(raw_user_id)
                except ValueError:
                    continue
                if access_type == "viewer" and user_id in editor_user_ids:
                    continue
                if (access_type, user_id) in seen_access:
                    continue
                if access_type == "editor":
                    editor_user_ids.add(user_id)
                seen_access.add((access_type, user_id))
                db.session.add(DocumentRegistryAccess(
                    registry_type=registry_type,
                    user_id=user_id,
                    access_type=access_type,
                ))

        db.session.commit()
        flash("Настройки доступа сохранены.", "success")
        return redirect(url_for("document_registers.access") + f"#registry-{registry_type}")

    editor_mapping = {}
    viewer_mapping = {}
    for row in DocumentRegistryAccess.query.order_by(DocumentRegistryAccess.registry_type.asc()).all():
        if row.access_type == "editor":
            editor_mapping.setdefault(row.registry_type, []).append(row.user_id)
        elif row.access_type == "viewer":
            viewer_mapping.setdefault(row.registry_type, []).append(row.user_id)

    return render_template(
        "document_registers_access.html",
        registries=REGISTRIES,
        users=_sorted_users(),
        editor_mapping=editor_mapping,
        viewer_mapping=viewer_mapping,
    )
