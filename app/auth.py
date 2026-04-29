import time
from datetime import datetime
from threading import RLock

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from .models import User
from .core.extensions import db

auth_bp = Blueprint("auth", __name__)

# In-memory rate-limit для /login — sliding window 60 с, порог 5 неудачных попыток
# на IP. После порога запросы отдают 429 на `_LOGIN_BLOCK_SECONDS`. Проц-локальный
# словарь с RLock'ом достаточен: Flask запускается одним процессом (см. run.py).
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_ATTEMPTS_LOCK = RLock()
_LOGIN_WINDOW_SECONDS = 60
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_BLOCK_SECONDS = 300  # 5 минут


def _client_ip() -> str:
    # За nginx-proxy X-Forwarded-For содержит реальный IP. Берём первый, если есть.
    xff = request.headers.get("X-Forwarded-For", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _login_is_blocked(ip: str) -> bool:
    now = time.time()
    with _LOGIN_ATTEMPTS_LOCK:
        attempts = _LOGIN_ATTEMPTS.get(ip, [])
        # Держим только попытки в окне
        attempts = [t for t in attempts if now - t < _LOGIN_BLOCK_SECONDS]
        _LOGIN_ATTEMPTS[ip] = attempts
        recent = [t for t in attempts if now - t < _LOGIN_WINDOW_SECONDS]
        return len(recent) >= _LOGIN_MAX_ATTEMPTS


def _record_failed_login(ip: str) -> None:
    with _LOGIN_ATTEMPTS_LOCK:
        _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.time())


def _reset_failed_login(ip: str) -> None:
    with _LOGIN_ATTEMPTS_LOCK:
        _LOGIN_ATTEMPTS.pop(ip, None)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = _client_ip()
        if _login_is_blocked(ip):
            current_app.logger.warning("LOGIN: rate-limit hit for ip=%s", ip)
            flash("Слишком много неудачных попыток. Подождите 5 минут и попробуйте снова.", "danger")
            return render_template("login.html"), 429

        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(username=username).first()

        if not user:
            _record_failed_login(ip)
            current_app.logger.info("LOGIN: user not found: %s (ip=%s)", username, ip)
            flash("Неверный логин или пароль", "danger")
            return render_template("login.html")

        if not user.check_password(password):
            _record_failed_login(ip)
            current_app.logger.info("LOGIN: password mismatch for: %s (ip=%s)", username, ip)
            flash("Неверный логин или пароль", "danger")
            return render_template("login.html")

        _reset_failed_login(ip)

        try:
            user.last_login_at = datetime.utcnow()
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Failed to update last_login_at for %s", username)

        session.permanent = True
        login_user(user)
        return redirect(url_for("main.dashboard"))

    return render_template("login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


# Гибкие режимы уведомлений по инцидентам. См. children._notify_user.
NOTIFY_INCIDENT_MODES = [
    ("all", "На каждое действие",
     "Все события: назначения, смена статуса, заметки, ответы в журнале."),
    ("status", "Только смена статуса",
     "Только события смены статуса, включая финальное закрытие."),
    ("open_close", "Появление и закрытие",
     "Только когда инцидент появился у вас (назначение) и когда закрыт."),
    ("close_only", "Только закрытие",
     "Только когда инцидент переведён в статус «Отработан» или «Закрыт»."),
]

# Гибкие режимы уведомлений по задачам. См. tasks._deliver_notifications.
NOTIFY_TASK_MODES = [
    ("all", "На каждое действие",
     "Все события: новая задача, смена статуса, срок, просрочка, "
     "комментарии, файлы, закрытие."),
    ("status", "Только смена статуса",
     "Смена статуса, отправка на проверку, возврат на доработку, "
     "изменение срока, просрочка и закрытие. Без комментариев и файлов."),
    ("open_close", "Появление и закрытие",
     "Только когда на вас назначили новую задачу и когда задача закрыта."),
    ("close_only", "Только закрытие",
     "Только когда задача переведена в финальный статус «Закрыта»."),
]


@auth_bp.route("/profile/settings", methods=["GET"])
@login_required
def profile_settings():
    current_inc_mode = getattr(current_user, "notify_incident_mode", None) or "all"
    current_task_mode = getattr(current_user, "notify_task_mode", None) or "all"
    return render_template(
        "profile_settings.html",
        incident_modes=NOTIFY_INCIDENT_MODES,
        task_modes=NOTIFY_TASK_MODES,
        current_incident_mode=current_inc_mode,
        current_task_mode=current_task_mode,
    )


@auth_bp.route("/profile/settings/notifications", methods=["POST"])
@login_required
def profile_settings_notifications():
    valid_modes = {code for code, _, _ in NOTIFY_INCIDENT_MODES}
    inc_mode = (request.form.get("incident_mode") or "").strip()
    task_mode = (request.form.get("task_mode") or "").strip()
    if inc_mode not in valid_modes or task_mode not in valid_modes:
        flash("Неверный режим уведомлений", "danger")
        return redirect(url_for("auth.profile_settings") + "#notifications")
    try:
        current_user.notify_incident_mode = inc_mode
        current_user.notify_task_mode = task_mode
        db.session.commit()
        flash("Настройки уведомлений сохранены", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to save notify modes for %s", current_user.username
        )
        flash("Не удалось сохранить настройки, попробуйте ещё раз", "danger")
    return redirect(url_for("auth.profile_settings") + "#notifications")


@auth_bp.route("/profile/settings/password", methods=["POST"])
@login_required
def profile_settings_password():
    current_pw = request.form.get("current_password") or ""
    new_pw = request.form.get("new_password") or ""
    confirm_pw = request.form.get("confirm_password") or ""

    anchor = "#password"
    if not current_user.check_password(current_pw):
        flash("Текущий пароль введён неверно", "danger")
        return redirect(url_for("auth.profile_settings") + anchor)
    if len(new_pw) < 8:
        flash("Новый пароль должен быть не короче 8 символов", "danger")
        return redirect(url_for("auth.profile_settings") + anchor)
    if new_pw != confirm_pw:
        flash("Новый пароль и повтор не совпадают", "danger")
        return redirect(url_for("auth.profile_settings") + anchor)
    if new_pw == current_pw:
        flash("Новый пароль совпадает с текущим", "danger")
        return redirect(url_for("auth.profile_settings") + anchor)

    try:
        current_user.set_password(new_pw)
        db.session.commit()
        flash("Пароль обновлён", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to change password for %s", current_user.username
        )
        flash("Не удалось сохранить пароль, попробуйте ещё раз", "danger")
    return redirect(url_for("auth.profile_settings") + anchor)


@auth_bp.route("/profile/notifications", methods=["GET", "POST"])
@login_required
def profile_notifications():
    return redirect(url_for("auth.profile_settings") + "#notifications", code=301)


# =====================================================================
# Привязка MAX (бот для подачи инцидентов)
# =====================================================================
@auth_bp.route("/profile/max", methods=["GET"])
@login_required
def profile_max():
    from app.models import MaxBinding
    active = (
        MaxBinding.query
        .filter_by(user_id=current_user.id, status="done")
        .order_by(MaxBinding.id.desc())
        .first()
    )
    pending = (
        MaxBinding.query
        .filter_by(user_id=current_user.id, status="pending")
        .filter(MaxBinding.expires_at > datetime.utcnow())
        .order_by(MaxBinding.id.desc())
        .first()
    )
    from datetime import timedelta as _td
    pending_msk = (pending.expires_at + _td(hours=3)) if pending else None
    bound_msk = (active.bound_at + _td(hours=3)) if (active and active.bound_at) else None
    return render_template(
        "profile_max.html",
        active=active,
        pending=pending,
        pending_msk=pending_msk,
        bound_msk=bound_msk,
        bot_url="https://max.ru/reguestsbot",
    )


@auth_bp.route("/profile/max/status", methods=["GET"])
@login_required
def profile_max_status():
    from flask import jsonify
    from app.models import MaxBinding
    active = (
        MaxBinding.query
        .filter_by(user_id=current_user.id, status="done")
        .order_by(MaxBinding.id.desc())
        .first()
    )
    if active:
        return jsonify({"status": "done", "max_full_name": active.max_full_name or ""})
    pending = (
        MaxBinding.query
        .filter_by(user_id=current_user.id, status="pending")
        .filter(MaxBinding.expires_at > datetime.utcnow())
        .order_by(MaxBinding.id.desc())
        .first()
    )
    if pending:
        return jsonify({"status": "pending"})
    return jsonify({"status": "none"})


@auth_bp.route("/profile/max/generate", methods=["POST"])
@login_required
def profile_max_generate():
    import secrets as _secrets
    from datetime import timedelta
    from app.models import MaxBinding

    # Старые pending этого пользователя — в expired
    (
        MaxBinding.query
        .filter_by(user_id=current_user.id, status="pending")
        .update({"status": "expired"}, synchronize_session=False)
    )
    # Уникальный 6-значный код среди активных pending всех пользователей
    code = None
    for _ in range(20):
        c = "".join(str(_secrets.randbelow(10)) for _ in range(6))
        exists = (
            MaxBinding.query
            .filter_by(code=c, status="pending")
            .filter(MaxBinding.expires_at > datetime.utcnow())
            .first()
        )
        if not exists:
            code = c
            break
    if not code:
        db.session.rollback()
        flash("Не удалось сгенерировать код, попробуйте ещё раз", "danger")
        return redirect(url_for("auth.profile_max"))

    # TTL 15 минут — синхронизировано с ботом (BIND_TTL_MIN=15 в bot.py).
    binding = MaxBinding(
        user_id=current_user.id,
        code=code,
        status="pending",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db.session.add(binding)
    db.session.commit()
    return redirect(url_for("auth.profile_max"))


@auth_bp.route("/profile/max/revoke", methods=["POST"])
@login_required
def profile_max_revoke():
    from app.models import MaxBinding
    from app.services.bot_client import get_client
    chat_ids = list({
        b.max_chat_id for b in (
            MaxBinding.query
            .filter_by(user_id=current_user.id)
            .all()
        )
        if b.max_chat_id
    })
    (
        MaxBinding.query
        .filter_by(user_id=current_user.id)
        .filter(MaxBinding.status.in_(("done", "pending")))
        .update({"status": "revoked"}, synchronize_session=False)
    )
    db.session.commit()

    if chat_ids:
        client = get_client()
        if client._enabled():  # noqa: SLF001
            for chat_id in chat_ids:
                try:
                    client.revoke(chat_id=chat_id)
                except Exception as e:
                    current_app.logger.warning("bot revoke failed for chat_id=%s: %s", chat_id, e)

    flash("Привязка отменена", "success")
    return redirect(url_for("auth.profile_max"))
