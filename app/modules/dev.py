"""
Dev-панель быстрого входа — только в DEBUG-режиме.
Доступна по адресу: /dev/login-as
"""
from flask import Blueprint, abort, current_app, redirect, render_template_string, request, url_for
from flask_login import login_user

dev_bp = Blueprint("dev", __name__, url_prefix="/dev")

# Описание тестовых пользователей для подсказки на странице
_DEV_USERS = [
    {"username": "admin",              "password": "admin123", "role": "ADMIN",          "label": "Администратор"},
    {"username": "test_class_teacher", "password": "test123",  "role": "CLASS_TEACHER",  "label": "Классный руководитель"},
    {"username": "test_psychologist",  "password": "test123",  "role": "PSYCHOLOGIST",   "label": "Психолог"},
    {"username": "test_social",        "password": "test123",  "role": "SOCIAL_PEDAGOG", "label": "Социальный педагог"},
    {"username": "test_teacher",       "password": "test123",  "role": "TEACHER",        "label": "Учитель"},
    {"username": "KPP",                "password": "123",       "role": "KPP",            "label": "КПП"},
]

_TEMPLATE = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>DEV — Быстрый вход</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
  <style>
    body { background: #f1f5f9; }
    .dev-card { max-width: 560px; margin: 60px auto; }
    .role-badge { font-size: .7rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
    .creds { font-family: monospace; font-size: .82rem; color: #64748b; }
  </style>
</head>
<body>
<div class="dev-card">
  <div class="card shadow-sm border-0 rounded-4 overflow-hidden">
    <div class="card-header bg-warning bg-opacity-25 py-3">
      <h5 class="mb-0">⚠️ DEV — Быстрый вход по роли</h5>
      <small class="text-muted">Доступно только в режиме DEBUG. На сервер не деплоится.</small>
    </div>
    <div class="card-body p-4">
      {% if message %}
      <div class="alert alert-danger">{{ message }}</div>
      {% endif %}
      <div class="d-grid gap-2">
        {% for u in users %}
        <form method="post">
          <input type="hidden" name="username" value="{{ u.username }}">
          <button type="submit" class="btn btn-outline-secondary w-100 text-start d-flex justify-content-between align-items-center py-2 px-3">
            <span>
              <strong>{{ u.label }}</strong>
              <span class="creds ms-2">{{ u.username }} / {{ u.password }}</span>
            </span>
            <span class="badge bg-secondary bg-opacity-25 text-secondary role-badge">{{ u.role }}</span>
          </button>
        </form>
        {% endfor %}
      </div>
    </div>
  </div>
</div>
</body>
</html>
"""


@dev_bp.route("/login-as", methods=["GET", "POST"])
def login_as():
    if not current_app.debug:
        abort(404)

    message = None

    if request.method == "POST":
        from app.models import User
        username = request.form.get("username", "").strip()
        user = User.query.filter_by(username=username).first()
        if user:
            login_user(user)
            return redirect(url_for("main.dashboard"))
        message = f"Пользователь «{username}» не найден. Создайте его через init_admin.py или скрипт создания тестовых пользователей."

    return render_template_string(_TEMPLATE, users=_DEV_USERS, message=message)
