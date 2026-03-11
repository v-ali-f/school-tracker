from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from .models import User
from . import db
from .roles import require_roles
from openpyxl import load_workbook

users_bp = Blueprint("users", __name__)

ROLE_OPTIONS = ["ADMIN", "CURATOR", "TEACHER", "VIEWER", "METHODIST"]


@users_bp.route("/admin/users")
@require_roles("ADMIN")
def users_list():
    status = (request.args.get("status") or "active").lower()
    q = (request.args.get("q") or "").strip().lower()
    query = User.query
    if status == "archived":
        query = query.filter(User.employment_status.in_(["DISMISSED", "ARCHIVED"]))
    elif status == "all":
        pass
    else:
        query = query.filter(~User.employment_status.in_(["DISMISSED", "ARCHIVED"]))
    if q:
        query = query.filter(db.or_(
            db.func.lower(db.func.coalesce(User.last_name, "")).contains(q),
            db.func.lower(db.func.coalesce(User.first_name, "")).contains(q),
            db.func.lower(db.func.coalesce(User.middle_name, "")).contains(q),
            db.func.lower(User.username).contains(q)
        ))
    users = query.order_by(User.last_name.asc(), User.first_name.asc(), User.username.asc()).all()
    return render_template("users_list.html", users=users, status=status, q=q)


@users_bp.route("/admin/users/new", methods=["GET", "POST"])
@require_roles("ADMIN")
def users_new():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        last_name = (request.form.get("last_name") or "").strip()
        first_name = (request.form.get("first_name") or "").strip()
        phone = (request.form.get("phone") or "").strip() or None
        role = (request.form.get("role") or "VIEWER").strip().upper()
        if not username or not password:
            flash("Заполните логин и пароль", "danger")
            return render_template("user_new.html", roles=ROLE_OPTIONS)
        if User.query.filter_by(username=username).first():
            flash("Пользователь уже существует", "danger")
            return render_template("user_new.html", roles=ROLE_OPTIONS)
        u = User(username=username, role=role, last_name=last_name, first_name=first_name, phone=phone)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        flash("Пользователь создан", "success")
        return redirect(url_for("users.users_list"))
    return render_template("user_new.html", roles=ROLE_OPTIONS)


@users_bp.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@require_roles("ADMIN")
def users_edit(user_id):
    u = User.query.get_or_404(user_id)
    if request.method == "POST":
        u.role = (request.form.get("role") or u.role).strip().upper()
        password = (request.form.get("password") or "").strip()
        u.last_name = (request.form.get("last_name") or "").strip()
        u.first_name = (request.form.get("first_name") or "").strip()
        u.phone = (request.form.get("phone") or "").strip() or None
        if password:
            u.set_password(password)
        db.session.commit()
        flash("Сохранено", "success")
        return redirect(url_for("users.users_list"))
    return render_template("user_edit.html", u=u, roles=ROLE_OPTIONS)


@users_bp.route("/admin/users/<int:user_id>/archive", methods=["POST"])
@require_roles("ADMIN")
def users_archive(user_id):
    u = User.query.get_or_404(user_id)
    if u.username == "admin":
        flash("Нельзя архивировать admin", "danger")
        return redirect(url_for("users.users_list"))
    u.employment_status = "ARCHIVED"
    u.is_active_user = False
    if not u.archived_at:
        u.archived_at = datetime.utcnow()
    if not u.dismissal_date:
        u.dismissal_date = datetime.utcnow().date()
    db.session.commit()
    flash("Сотрудник переведён в архив. Документы и история сохранены.", "success")
    return redirect(url_for("users.users_list", status="archived"))


@users_bp.route("/admin/users/<int:user_id>/restore", methods=["POST"])
@require_roles("ADMIN")
def users_restore(user_id):
    u = User.query.get_or_404(user_id)
    u.employment_status = "ACTIVE"
    u.is_active_user = True
    u.archived_at = None
    u.dismissal_date = None
    db.session.commit()
    flash("Сотрудник возвращён в активный список.", "success")
    return redirect(url_for("users.users_list", status="active"))


@users_bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@require_roles("ADMIN")
def users_delete(user_id):
    u = User.query.get_or_404(user_id)
    if u.username == "admin":
        flash("Нельзя удалить admin", "danger")
        return redirect(url_for("users.users_list"))
    u.employment_status = "ARCHIVED"
    u.is_active_user = False
    u.archived_at = datetime.utcnow()
    if not u.dismissal_date:
        u.dismissal_date = datetime.utcnow().date()
    db.session.commit()
    flash("Физическое удаление заменено архивированием. Сотрудник сохранён в истории.", "success")
    return redirect(url_for("users.users_list", status="archived"))


@users_bp.route("/admin/users/import", methods=["GET", "POST"])
@require_roles("ADMIN")
def users_import():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Выберите Excel файл", "danger")
            return redirect(url_for("users.users_import"))
        wb = load_workbook(f, data_only=True)
        ws = wb.active
        headers = [(str(cell.value).strip() if cell.value is not None else "") for cell in ws[1]]
        idx = {h: i for i, h in enumerate(headers)}
        required = ["username", "password", "role", "last_name", "first_name", "phone"]
        missing = [c for c in required if c not in idx]
        if missing:
            flash(f"Не хватает колонок: {', '.join(missing)}", "danger")
            return redirect(url_for("users.users_import"))
        created, updated, skipped = 0, 0, 0
        for r in range(2, ws.max_row + 1):
            row = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
            username = (row[idx["username"]] or "").strip() if isinstance(row[idx["username"]], str) else (str(row[idx["username"]]).strip() if row[idx["username"]] else "")
            password = row[idx["password"]]
            role = str(row[idx["role"]] or "VIEWER").strip().upper()
            last_name = str(row[idx["last_name"]] or "").strip()
            first_name = str(row[idx["first_name"]] or "").strip()
            phone = str(row[idx["phone"]] or "").strip() or None
            if not username:
                skipped += 1
                continue
            if role not in ROLE_OPTIONS:
                role = "VIEWER"
            u = User.query.filter_by(username=username).first()
            if not u:
                u = User(username=username)
                db.session.add(u)
                created += 1
            else:
                updated += 1
            u.role = role
            u.last_name = last_name
            u.first_name = first_name
            u.phone = phone
            u.employment_status = u.employment_status or "ACTIVE"
            if password:
                u.set_password(str(password).strip())
        db.session.commit()
        flash(f"Импорт завершён. Создано: {created}, обновлено: {updated}, пропущено: {skipped}", "success")
        return redirect(url_for("users.users_list"))
    return render_template("users_import.html")
