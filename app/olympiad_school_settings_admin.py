from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.core.extensions import db

olympiad_school_settings_bp = Blueprint(
    "olympiad_school_settings_admin",
    __name__,
    url_prefix="/admin",
)


def _is_admin_user() -> bool:
    return bool(getattr(current_user, "is_authenticated", False)) and getattr(current_user, "role", None) in {
        "ADMIN",
        "DEPUTY_DIRECTOR",
        "DEPUTY",
        "SYSTEM_ADMIN",
    }


def _ensure_columns() -> None:
    """Добавляет поля без Alembic-миграции, чтобы патч можно было поставить на рабочий сервер."""
    stmts = [
        "ALTER TABLE organization_settings ADD COLUMN IF NOT EXISTS olympiad_school_login VARCHAR(80)",
        "ALTER TABLE organization_settings ADD COLUMN IF NOT EXISTS olympiad_ekis_code VARCHAR(80)",
        "ALTER TABLE organization_settings ADD COLUMN IF NOT EXISTS olympiad_school_name VARCHAR(255)",
    ]
    for stmt in stmts:
        db.session.execute(db.text(stmt))
    db.session.commit()


def _active_settings_row():
    _ensure_columns()
    try:
        return db.session.execute(
            db.text(
                """
                SELECT id, short_name, full_name,
                       olympiad_school_login, olympiad_ekis_code, olympiad_school_name
                FROM organization_settings
                ORDER BY COALESCE(is_active, FALSE) DESC, id DESC
                LIMIT 1
                """
            )
        ).mappings().first()
    except Exception:
        # если в старой схеме нет is_active
        db.session.rollback()
        _ensure_columns()
        return db.session.execute(
            db.text(
                """
                SELECT id, short_name, full_name,
                       olympiad_school_login, olympiad_ekis_code, olympiad_school_name
                FROM organization_settings
                ORDER BY id DESC
                LIMIT 1
                """
            )
        ).mappings().first()


@olympiad_school_settings_bp.route("/olympiad-school-settings", methods=["GET", "POST"])
@login_required
def olympiad_school_settings():
    if not _is_admin_user():
        flash("Недостаточно прав для изменения настроек организации.", "danger")
        return redirect("/")

    row = _active_settings_row()
    if not row:
        flash("Сначала создайте запись настроек организации.", "warning")
        return redirect("/")

    if request.method == "POST":
        login = (request.form.get("olympiad_school_login") or "").strip()
        ekis = (request.form.get("olympiad_ekis_code") or "").strip()
        name = (request.form.get("olympiad_school_name") or "").strip()

        db.session.execute(
            db.text(
                """
                UPDATE organization_settings
                SET olympiad_school_login = :login,
                    olympiad_ekis_code = :ekis,
                    olympiad_school_name = :name,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "login": login or None,
                "ekis": ekis or None,
                "name": name or None,
                "updated_at": datetime.utcnow(),
                "id": row["id"],
            },
        )
        db.session.commit()
        flash("Данные школы для импорта олимпиад сохранены.", "success")
        return redirect(url_for("olympiad_school_settings_admin.olympiad_school_settings"))

    return render_template("admin/olympiad_school_settings.html", settings=row)
