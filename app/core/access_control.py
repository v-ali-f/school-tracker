from __future__ import annotations

from flask import flash, jsonify, redirect, request, session, url_for
from flask_login import current_user, logout_user


_LOGIN_ENDPOINTS = {"auth.login", "auth.logout", "mobile_api.login"}


def is_user_account_enabled(user) -> bool:
    """Return True only for an employee who may still use the system."""
    if not user:
        return False
    employment_status = (getattr(user, "employment_status", "") or "").upper()
    return bool(
        getattr(user, "is_active_user", False)
        and employment_status == "ACTIVE"
        and getattr(user, "archived_at", None) is None
    )


def init_user_access_guard(app) -> None:
    """Revoke an existing Flask-Login session as soon as an account is disabled."""

    @app.before_request
    def reject_disabled_user():
        # Flask-Login considers an inactive User unauthenticated before the request
        # reaches us, but its id may still remain in the signed session cookie.
        # Checking the session id lets us remove that stale access immediately.
        if request.endpoint == "static" or not session.get("_user_id"):
            return None
        if is_user_account_enabled(current_user):
            return None

        logout_user()

        # Let the user immediately sign in with another account.
        if request.endpoint in _LOGIN_ENDPOINTS:
            return None

        if request.blueprint == "mobile_api" or request.path.startswith("/mobile/api/"):
            return jsonify(
                {
                    "ok": False,
                    "error": "Учётная запись отключена.",
                    "code": "inactive_user",
                }
            ), 403

        flash(
            "Учётная запись отключена. Доступ к системе прекращён. Обратитесь к администратору.",
            "danger",
        )
        return redirect(url_for("auth.login"))
