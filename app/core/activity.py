from datetime import datetime, timedelta

from flask import request
from flask_login import current_user
from sqlalchemy import text

from app.core.extensions import db

THROTTLE = timedelta(hours=1)

SKIP_ENDPOINT_PREFIXES = ("static",)


def _should_skip(endpoint: str | None) -> bool:
    if endpoint is None:
        return True
    for prefix in SKIP_ENDPOINT_PREFIXES:
        if endpoint == prefix or endpoint.startswith(prefix + "."):
            return True
    return False


def init_user_activity(app):
    @app.before_request
    def _track_user_activity():
        try:
            if _should_skip(request.endpoint):
                return
            if not getattr(current_user, "is_authenticated", False):
                return
            user_id = getattr(current_user, "id", None)
            if not user_id:
                return

            now = datetime.utcnow()
            throttle_before = now - THROTTLE

            db.session.execute(
                text(
                    'UPDATE "user" '
                    'SET last_seen_at = :now, '
                    '    active_days_count = active_days_count + CASE '
                    '      WHEN last_seen_at IS NULL THEN 1 '
                    '      WHEN DATE(last_seen_at) < DATE(:now) THEN 1 '
                    '      ELSE 0 '
                    '    END '
                    'WHERE id = :uid '
                    '  AND (last_seen_at IS NULL OR last_seen_at < :throttle_before)'
                ),
                {"now": now, "uid": user_id, "throttle_before": throttle_before},
            )
            db.session.commit()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            app.logger.exception("track_user_activity failed")
