# -*- coding: utf-8 -*-
"""Административная страница SMTP/email-уведомлений.

Сделано отдельным blueprint, чтобы восстановить видимую настройку почты
без ломки существующих модулей портала.
"""
from __future__ import annotations

import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from typing import Any

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import text

from app.core.extensions import db
from app.models import SystemMailSettings

admin_email_settings_bp = Blueprint("admin_email_settings", __name__, url_prefix="/admin")

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS system_email_settings (
    id INTEGER PRIMARY KEY,
    smtp_enabled BOOLEAN DEFAULT FALSE,
    smtp_host VARCHAR(255),
    smtp_port INTEGER DEFAULT 465,
    smtp_use_ssl BOOLEAN DEFAULT TRUE,
    smtp_use_tls BOOLEAN DEFAULT FALSE,
    smtp_username VARCHAR(255),
    smtp_password TEXT,
    mail_sender_email VARCHAR(255),
    mail_sender_name VARCHAR(255),
    task_email_notifications_enabled BOOLEAN DEFAULT TRUE,
    task_comment_email_enabled BOOLEAN DEFAULT TRUE,
    task_deadline_email_enabled BOOLEAN DEFAULT TRUE,
    email_last_test_at VARCHAR(64),
    email_last_test_status TEXT,
    created_at VARCHAR(64),
    updated_at VARCHAR(64)
)
"""


def _is_admin() -> bool:
    role = (getattr(current_user, "role", "") or "").upper()
    return role in {"ADMIN", "SUPERADMIN", "DEPUTY", "DEPUTY_DIRECTOR", "DIRECTOR"}


def _require_admin():
    if not current_user.is_authenticated or not _is_admin():
        from flask import abort
        abort(403)


def _ensure_table() -> None:
    db.session.execute(text(TABLE_SQL))
    row = db.session.execute(text("SELECT id FROM system_email_settings WHERE id = 1")).mappings().first()
    if not row:
        now = datetime.utcnow().isoformat()
        db.session.execute(text("""
            INSERT INTO system_email_settings
            (id, smtp_enabled, smtp_port, smtp_use_ssl, smtp_use_tls,
             task_email_notifications_enabled, task_comment_email_enabled, task_deadline_email_enabled,
             created_at, updated_at)
            VALUES (1, FALSE, 465, TRUE, FALSE, TRUE, TRUE, TRUE, :now, :now)
        """), {"now": now})
    db.session.commit()


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).lower() in {"1", "true", "yes", "on", "да"}


def get_email_settings() -> dict[str, Any]:
    _ensure_table()
    row = db.session.execute(text("SELECT * FROM system_email_settings WHERE id = 1")).mappings().first()
    return dict(row or {})


def _sync_system_mail_settings(params: dict[str, Any], *, updated_by_user_id: int | None = None) -> None:
    """Синхронизирует админскую форму с основной таблицей отправки писем.

    Уведомления задач используют сервис app.services.mail_settings_service,
    который читает модель SystemMailSettings / таблицу system_mail_settings.
    Поэтому одной служебной таблицы system_email_settings недостаточно.
    """
    row = SystemMailSettings.query.filter_by(is_active=True).order_by(SystemMailSettings.id.desc()).first()
    if row is None:
        row = SystemMailSettings(is_active=True)
        db.session.add(row)

    row.provider = "custom"
    row.smtp_host = (params.get("smtp_host") or "").strip() or None
    row.smtp_port = int(params.get("smtp_port") or 465)
    row.smtp_username = (params.get("smtp_username") or "").strip() or None
    row.smtp_password = params.get("smtp_password") or None
    row.sender_email = (params.get("mail_sender_email") or params.get("smtp_username") or "").strip() or None
    row.use_ssl = _as_bool(params.get("smtp_use_ssl"))
    row.use_tls = _as_bool(params.get("smtp_use_tls"))
    row.is_active = _as_bool(params.get("smtp_enabled"))
    row.updated_by_user_id = updated_by_user_id


def apply_email_settings_to_config() -> None:
    """Пробрасывает настройки в Flask config.

    Это помогает существующей логике отправки писем, если она читает MAIL_* или SMTP_*.
    """
    try:
        s = get_email_settings()
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("Email settings load failed: %s", exc)
        return

    enabled = _as_bool(s.get("smtp_enabled"))
    host = s.get("smtp_host") or ""
    port = int(s.get("smtp_port") or 465)
    use_ssl = _as_bool(s.get("smtp_use_ssl"))
    use_tls = _as_bool(s.get("smtp_use_tls"))
    username = s.get("smtp_username") or ""
    password = s.get("smtp_password") or ""
    sender_email = s.get("mail_sender_email") or username
    sender_name = s.get("mail_sender_name") or "Портал сопровождения обучающихся"

    current_app.config.update(
        SMTP_ENABLED=enabled,
        SMTP_HOST=host,
        SMTP_PORT=port,
        SMTP_USE_SSL=use_ssl,
        SMTP_USE_TLS=use_tls,
        SMTP_USERNAME=username,
        SMTP_PASSWORD=password,
        MAIL_SERVER=host,
        MAIL_PORT=port,
        MAIL_USE_SSL=use_ssl,
        MAIL_USE_TLS=use_tls,
        MAIL_USERNAME=username,
        MAIL_PASSWORD=password,
        MAIL_DEFAULT_SENDER=(sender_name, sender_email),
        MAIL_SENDER_EMAIL=sender_email,
        MAIL_SENDER_NAME=sender_name,
        TASK_EMAIL_NOTIFICATIONS_ENABLED=_as_bool(s.get("task_email_notifications_enabled")),
    )


@admin_email_settings_bp.before_app_request
def _before_request_apply_email_settings():
    apply_email_settings_to_config()


def _send_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    s = get_email_settings()
    if not _as_bool(s.get("smtp_enabled")):
        return False, "Отправка email-уведомлений выключена в настройках."

    host = (s.get("smtp_host") or "").strip()
    if not host:
        return False, "Не указан SMTP-сервер."
    port = int(s.get("smtp_port") or 465)
    username = (s.get("smtp_username") or "").strip()
    password = s.get("smtp_password") or ""
    sender_email = (s.get("mail_sender_email") or username).strip()
    sender_name = (s.get("mail_sender_name") or "Портал сопровождения обучающихся").strip()

    if not sender_email:
        return False, "Не указан email отправителя."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = to_email
    msg.set_content(body)

    try:
        if _as_bool(s.get("smtp_use_ssl")):
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                if _as_bool(s.get("smtp_use_tls")):
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                if username:
                    smtp.login(username, password)
                smtp.send_message(msg)
        return True, "Письмо успешно отправлено."
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("Test email failed")
        return False, str(exc)


@admin_email_settings_bp.route("/email-settings", methods=["GET", "POST"])
@admin_email_settings_bp.route("/email", methods=["GET", "POST"])
@login_required
def email_settings():
    _require_admin()
    _ensure_table()

    if request.method == "POST":
        old = get_email_settings()
        password_from_form = request.form.get("smtp_password") or ""
        password_value = password_from_form if password_from_form.strip() else (old.get("smtp_password") or "")
        now = datetime.utcnow().isoformat()

        params = {
            "smtp_enabled": True if request.form.get("smtp_enabled") else False,
            "smtp_host": (request.form.get("smtp_host") or "").strip(),
            "smtp_port": int(request.form.get("smtp_port") or 465),
            "smtp_use_ssl": True if request.form.get("smtp_use_ssl") else False,
            "smtp_use_tls": True if request.form.get("smtp_use_tls") else False,
            "smtp_username": (request.form.get("smtp_username") or "").strip(),
            "smtp_password": password_value,
            "mail_sender_email": (request.form.get("mail_sender_email") or "").strip(),
            "mail_sender_name": (request.form.get("mail_sender_name") or "").strip(),
            "task_email_notifications_enabled": True if request.form.get("task_email_notifications_enabled") else False,
            "task_comment_email_enabled": True if request.form.get("task_comment_email_enabled") else False,
            "task_deadline_email_enabled": True if request.form.get("task_deadline_email_enabled") else False,
            "updated_at": now,
        }
        db.session.execute(text("""
            UPDATE system_email_settings
            SET smtp_enabled=:smtp_enabled,
                smtp_host=:smtp_host,
                smtp_port=:smtp_port,
                smtp_use_ssl=:smtp_use_ssl,
                smtp_use_tls=:smtp_use_tls,
                smtp_username=:smtp_username,
                smtp_password=:smtp_password,
                mail_sender_email=:mail_sender_email,
                mail_sender_name=:mail_sender_name,
                task_email_notifications_enabled=:task_email_notifications_enabled,
                task_comment_email_enabled=:task_comment_email_enabled,
                task_deadline_email_enabled=:task_deadline_email_enabled,
                updated_at=:updated_at
            WHERE id=1
        """), params)
        _sync_system_mail_settings(params, updated_by_user_id=getattr(current_user, "id", None))
        db.session.commit()
        flash("Настройки электронной почты сохранены.", "success")
        return redirect(url_for("admin_email_settings.email_settings"))

    settings = get_email_settings()
    return render_template("admin/email_settings.html", settings=settings)


@admin_email_settings_bp.route("/email-settings/test", methods=["POST"])
@admin_email_settings_bp.route("/email/test", methods=["POST"])
@login_required
def test_email():
    _require_admin()
    to_email = (request.form.get("test_email") or "").strip()
    if not to_email:
        flash("Укажите адрес для тестового письма.", "danger")
        return redirect(url_for("admin_email_settings.email_settings"))

    ok, message = _send_email(
        to_email,
        "Тестовое письмо портала",
        "Это тестовое письмо из системы сопровождения обучающихся.\n\nЕсли вы получили это письмо, настройки SMTP работают корректно.",
    )
    now = datetime.utcnow().isoformat()
    db.session.execute(text("""
        UPDATE system_email_settings
        SET email_last_test_at=:at, email_last_test_status=:status, updated_at=:at
        WHERE id=1
    """), {"at": now, "status": ("OK: " if ok else "ERROR: ") + message})
    db.session.commit()

    flash(message, "success" if ok else "danger")
    return redirect(url_for("admin_email_settings.email_settings"))
