"""AJAX-эндпоинты для именованных видов фильтров (SavedView).

Используются JS-ом на /incidents/registry и /incidents/my для
сохранения/загрузки/удаления персональных видов. Работает по AJAX,
данные хранятся в `saved_view` per-user, переносятся между устройствами.
"""
from urllib.parse import parse_qsl, urlencode

from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.models.saved_view import SavedView


saved_views_bp = Blueprint("saved_views", __name__, url_prefix="/api/saved-views")

_ALLOWED_SCOPES = {"inc_my", "inc_registry"}
_MAX_VIEWS_PER_SCOPE = 12

# Whitelist параметров qs (пересечение фильтров /incidents/my и /registry).
# Все остальные ключи отбрасываются — защита от мусора и случайных секретов
# в URL вместе с видом.
_QS_ALLOWED = {
    "view", "tab", "status", "group_by", "category", "class_id",
    "grade", "q", "sort", "page",
}
_QS_MAX_LEN = 1000
_QS_MAX_VALUE_LEN = 200


def _normalize_qs(raw):
    if not raw:
        return ""
    pairs = parse_qsl(raw[:_QS_MAX_LEN], keep_blank_values=False)
    clean = [(k, v[:_QS_MAX_VALUE_LEN]) for k, v in pairs if k in _QS_ALLOWED and v]
    return urlencode(clean)


@saved_views_bp.route("", methods=["GET"])
@login_required
def list_views():
    scope = (request.args.get("scope") or "").strip()
    if scope not in _ALLOWED_SCOPES:
        return jsonify({"error": "invalid_scope"}), 400
    rows = (
        SavedView.query
        .filter_by(user_id=current_user.id, scope=scope)
        .order_by(SavedView.sort_order.asc(), SavedView.id.asc())
        .all()
    )
    return jsonify({"items": [{"id": v.id, "name": v.name, "qs": v.qs} for v in rows]})


@saved_views_bp.route("", methods=["POST"])
@login_required
def create_view():
    scope = (request.form.get("scope") or "").strip()
    name = (request.form.get("name") or "").strip()[:80]
    qs = _normalize_qs((request.form.get("qs") or "").strip())
    if scope not in _ALLOWED_SCOPES:
        return jsonify({"error": "invalid_scope"}), 400
    if not name:
        return jsonify({"error": "empty_name"}), 400
    if not qs:
        return jsonify({"error": "empty_qs"}), 400
    cnt = SavedView.query.filter_by(user_id=current_user.id, scope=scope).count()
    if cnt >= _MAX_VIEWS_PER_SCOPE:
        return jsonify({"error": "limit_reached", "limit": _MAX_VIEWS_PER_SCOPE}), 400
    v = SavedView(user_id=current_user.id, scope=scope, name=name, qs=qs, sort_order=cnt)
    db.session.add(v)
    try:
        db.session.commit()
    except IntegrityError:
        # s81: UNIQUE(user_id, scope, name) — двойной клик/гонка ловится здесь.
        db.session.rollback()
        existing = SavedView.query.filter_by(
            user_id=current_user.id, scope=scope, name=name
        ).first()
        if existing:
            return jsonify({"ok": True, "id": existing.id, "name": existing.name, "qs": existing.qs})
        return jsonify({"error": "conflict"}), 409
    return jsonify({"ok": True, "id": v.id, "name": v.name, "qs": v.qs})


@saved_views_bp.route("/<int:view_id>", methods=["DELETE"])
@login_required
def delete_view(view_id):
    v = SavedView.query.get_or_404(view_id)
    if v.user_id != current_user.id:
        abort(403)
    db.session.delete(v)
    db.session.commit()
    return jsonify({"ok": True})
