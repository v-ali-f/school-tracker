from __future__ import annotations

import os
from datetime import datetime

from flask import current_app

from app.core.extensions import db
from app.models import MobilePushToken


def _firebase_messaging():
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
    except Exception:
        current_app.logger.info("Mobile push skipped: firebase-admin is not installed")
        return None

    if not firebase_admin._apps:
        credential_path = (
            current_app.config.get("FIREBASE_SERVICE_ACCOUNT_FILE")
            or os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE")
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        try:
            if credential_path:
                firebase_admin.initialize_app(
                    credentials.Certificate(credential_path)
                )
            else:
                firebase_admin.initialize_app()
        except Exception:
            current_app.logger.warning(
                "Mobile push skipped: Firebase Admin credentials are not configured"
            )
            return None
    return messaging


def send_mobile_push_to_user(
    user_id: int | None,
    title: str,
    body: str,
    *,
    data: dict | None = None,
) -> int:
    if not user_id:
        return 0

    messaging = _firebase_messaging()
    if messaging is None:
        return 0

    tokens = MobilePushToken.query.filter_by(
        user_id=user_id,
        is_active=True,
    ).all()
    if not tokens:
        return 0

    sent = 0
    payload = {str(k): str(v) for k, v in (data or {}).items() if v is not None}
    for row in tokens:
        try:
            messaging.send(
                messaging.Message(
                    token=row.token,
                    notification=messaging.Notification(
                        title=title[:255],
                        body=body[:2048],
                    ),
                    data=payload,
                    android=messaging.AndroidConfig(priority="high"),
                )
            )
            row.last_seen_at = datetime.utcnow()
            sent += 1
        except Exception as exc:
            message = str(exc).lower()
            if "not found" in message or "unregistered" in message:
                row.is_active = False
            current_app.logger.warning(
                "Mobile push failed: user_id=%s token_id=%s error=%s",
                user_id,
                row.id,
                exc,
            )
    return sent
