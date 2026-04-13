import os
from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, abort, current_app, send_from_directory
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.core.extensions import db
from .models import KnowledgeArticle
from .permissions import is_admin
from .roles import require_roles

knowledge_bp = Blueprint("knowledge", __name__, url_prefix="/knowledge")

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "pptx", "xlsx", "png", "jpg", "jpeg"}

ALL_ROLES = [
    ("ADMIN", "Администратор"),
    ("CLASS_TEACHER", "Классный руководитель"),
    ("TEACHER", "Учитель"),
    ("PSYCHOLOGIST", "Педагог-психолог"),
    ("SOCIAL_PEDAGOG", "Социальный педагог"),
    ("METHODIST", "Методист"),
    ("KPP", "КПП"),
    ("DEPUTY_DIRECTOR", "Заместитель директора"),
    ("VIEWER", "Просмотр"),
]


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _user_roles():
    """Возвращает список кодов ролей текущего пользователя."""
    if not current_user.is_authenticated:
        return []
    from .permissions import _user_role_codes
    return _user_role_codes(current_user)


# ─────────────────────────────────────────────
# ПУБЛИЧНАЯ ЧАСТЬ
# ─────────────────────────────────────────────

@knowledge_bp.route("/")
@login_required
def knowledge_list():
    roles = _user_roles()
    articles = (
        KnowledgeArticle.query
        .filter(KnowledgeArticle.is_published == True)
        .order_by(KnowledgeArticle.sort_order.asc(), KnowledgeArticle.id.asc())
        .all()
    )
    # Показываем статью если её список ролей пустой (для всех) ИЛИ
    # хотя бы одна роль пользователя есть в списке статьи.
    # Администратор видит все опубликованные статьи.
    admin = is_admin()
    visible = [
        a for a in articles
        if admin or not a.target_roles or any(r in a.target_roles for r in roles)
    ]
    # Группируем по первой совпадающей роли для отображения секций
    sections = {}
    role_order = [code for code, _ in ALL_ROLES]
    role_labels = dict(ALL_ROLES)
    for article in visible:
        if not article.target_roles:
            key = "__all__"
            label = "Для всех"
        else:
            # Берём первую роль из списка статьи для группировки
            key = article.target_roles[0]
            label = role_labels.get(key, key)
        if key not in sections:
            sections[key] = {"label": label, "articles": []}
        sections[key]["articles"].append(article)

    # Сортируем секции по порядку ролей
    def section_sort(item):
        k = item[0]
        if k == "__all__":
            return -1
        return role_order.index(k) if k in role_order else 999

    sorted_sections = sorted(sections.items(), key=section_sort)
    return render_template(
        "knowledge_list.html",
        sorted_sections=sorted_sections,
        total=len(visible),
    )


@knowledge_bp.route("/<int:article_id>")
@login_required
def knowledge_view(article_id):
    article = KnowledgeArticle.query.get_or_404(article_id)
    if not article.is_published and not is_admin():
        abort(404)
    roles = _user_roles()
    if article.target_roles and not is_admin():
        if not any(r in article.target_roles for r in roles):
            abort(403)
    return render_template("knowledge_article.html", article=article)


@knowledge_bp.route("/files/<path:filename>")
@login_required
def knowledge_file(filename):
    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "knowledge")
    return send_from_directory(upload_dir, filename)


# ─────────────────────────────────────────────
# ADMIN CRUD
# ─────────────────────────────────────────────

@knowledge_bp.route("/admin")
@require_roles("ADMIN")
def knowledge_admin():
    articles = (
        KnowledgeArticle.query
        .order_by(KnowledgeArticle.sort_order.asc(), KnowledgeArticle.id.asc())
        .all()
    )
    return render_template("knowledge_admin.html", articles=articles, all_roles=ALL_ROLES)


@knowledge_bp.route("/admin/new", methods=["GET", "POST"])
@require_roles("ADMIN")
def knowledge_new():
    if request.method == "POST":
        return _save_article(None)
    return render_template("knowledge_form.html", article=None, all_roles=ALL_ROLES)


@knowledge_bp.route("/admin/<int:article_id>/edit", methods=["GET", "POST"])
@require_roles("ADMIN")
def knowledge_edit(article_id):
    article = KnowledgeArticle.query.get_or_404(article_id)
    if request.method == "POST":
        return _save_article(article)
    return render_template("knowledge_form.html", article=article, all_roles=ALL_ROLES)


@knowledge_bp.route("/admin/<int:article_id>/delete", methods=["POST"])
@require_roles("ADMIN")
def knowledge_delete(article_id):
    article = KnowledgeArticle.query.get_or_404(article_id)
    if article.file_path:
        _delete_file(article.file_path)
    db.session.delete(article)
    db.session.commit()
    flash("Материал удалён.", "success")
    return redirect(url_for("knowledge.knowledge_admin"))


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _save_article(article):
    title = (request.form.get("title") or "").strip()
    body = (request.form.get("body") or "").strip()
    link = (request.form.get("link") or "").strip()
    kind = request.form.get("kind", "article")
    sort_order = int(request.form.get("sort_order") or 0)
    is_published = bool(request.form.get("is_published"))
    target_roles = request.form.getlist("target_roles")

    if not title:
        flash("Укажите заголовок.", "danger")
        return render_template(
            "knowledge_form.html", article=article, all_roles=ALL_ROLES
        )

    if article is None:
        article = KnowledgeArticle()
        db.session.add(article)

    article.title = title
    article.body = body or None
    article.link = link or None
    article.kind = kind
    article.sort_order = sort_order
    article.is_published = is_published
    article.target_roles = target_roles
    article.updated_at = datetime.utcnow()

    # Загрузка файла
    file = request.files.get("file")
    if file and file.filename and _allowed_file(file.filename):
        upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "knowledge")
        os.makedirs(upload_dir, exist_ok=True)
        filename = secure_filename(file.filename)
        # Уникальное имя
        base, ext = os.path.splitext(filename)
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename = f"{base}_{ts}{ext}"
        file.save(os.path.join(upload_dir, filename))
        if article.file_path:
            _delete_file(article.file_path)
        article.file_path = filename

    db.session.commit()
    flash("Материал сохранён.", "success")
    return redirect(url_for("knowledge.knowledge_admin"))


def _delete_file(filename):
    try:
        upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "knowledge")
        path = os.path.join(upload_dir, filename)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
