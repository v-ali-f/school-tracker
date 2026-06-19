from __future__ import annotations

import os
from datetime import datetime

from flask import current_app
from sqlalchemy import bindparam, or_, text

from app.core.extensions import db
from app.models import (
    Appeal,
    FamiliarizationRecipient,
    MobilePushToken,
    Task,
    TaskNotification,
    TaskParticipant,
    User,
)
from app.models_legacy import IncidentNotification, SchoolOrder
from app.services.mail_settings_service import get_mail_config

_APPEAL_MANAGER_ROLES = {
    "ADMIN", "DEPUTY_DIRECTOR", "DIRECTOR", "SECRETARY_ACADEMIC", "SECRETARY",
}


def _task_access_filter(user_id: int):
    return or_(
        Task.responsible_user_id == user_id,
        Task.controller_user_id == user_id,
        Task.creator_user_id == user_id,
        Task.id.in_(
            db.session.query(TaskParticipant.task_id).filter(
                TaskParticipant.user_id == user_id
            )
        ),
    )


def _visible_appeals_query(user: User):
    query = Appeal.query
    if getattr(user, "role", None) in _APPEAL_MANAGER_ROLES:
        return query
    uid = getattr(user, "id", None)
    uid_text = str(uid or "")
    return query.filter(
        or_(
            Appeal.creator_user_id == uid,
            Appeal.responsible_user_id == uid,
            Appeal.responsible_user_ids == uid_text,
            Appeal.responsible_user_ids.like(f"{uid_text},%"),
            Appeal.responsible_user_ids.like(f"%,{uid_text},%"),
            Appeal.responsible_user_ids.like(f"%,{uid_text}"),
        )
    )


def _visible_orders_query(user: User):
    try:
        from app.orders import _allowed_order_sections

        sections = _allowed_order_sections("view", user=user)
    except TypeError:
        sections = _allowed_order_sections("view")
    except Exception:
        current_app.logger.exception("Mobile push order access lookup failed")
        sections = []
    if not sections:
        return None
    return SchoolOrder.query.filter(SchoolOrder.section.in_(sections))


def _mobile_read_keys(user_id: int, kind: str, entity_ids: list[int]) -> set[int]:
    ids = [int(value) for value in entity_ids if value]
    if not ids:
        return set()
    try:
        query = text(
            """
            SELECT entity_id
            FROM mobile_notification_read
            WHERE user_id = :user_id AND kind = :kind AND entity_id IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True))
        rows = db.session.execute(
            query,
            {"user_id": user_id, "kind": kind, "ids": ids},
        ).all()
        return {int(row[0]) for row in rows}
    except Exception:
        db.session.rollback()
        return set()


def _badge_count_for_user(user_id: int) -> int:
    user = db.session.get(User, user_id)
    if user is None:
        return 0

    completed_task_statuses = [
        Task.STATUS_DONE,
        Task.STATUS_CLOSED,
        Task.STATUS_CANCELLED,
    ]
    task_unread = (
        db.session.query(TaskNotification.task_id)
        .join(Task, Task.id == TaskNotification.task_id)
        .filter(
            TaskNotification.user_id == user_id,
            TaskNotification.is_read.is_(False),
            Task.status.notin_(completed_task_statuses),
            _task_access_filter(user_id),
        )
        .distinct()
        .count()
    )
    incident_unread = IncidentNotification.query.filter_by(
        user_id=user_id,
        is_read=False,
    ).count()
    familiarization_unread = (
        FamiliarizationRecipient.query.filter_by(
            user_id=user_id,
            acknowledged_at=None,
        )
        .join(FamiliarizationRecipient.familiarization)
        .count()
    )
    appeal_items = (
        _visible_appeals_query(user)
        .order_by(Appeal.created_at.desc())
        .limit(100)
        .all()
    )
    appeal_read_ids = _mobile_read_keys(user_id, "appeal", [item.id for item in appeal_items])
    appeal_unread = sum(1 for item in appeal_items if item.id not in appeal_read_ids)

    order_query = _visible_orders_query(user)
    order_items = [] if order_query is None else (
        order_query.order_by(SchoolOrder.order_date.desc(), SchoolOrder.id.desc())
        .limit(100)
        .all()
    )
    order_read_ids = _mobile_read_keys(user_id, "order", [item.id for item in order_items])
    order_unread = sum(1 for item in order_items if item.id not in order_read_ids)

    return (
        task_unread
        + incident_unread
        + familiarization_unread
        + appeal_unread
        + order_unread
    )


def _push_link(data: dict[str, str]) -> str:
    kind = (data.get("kind") or "").strip()
    if kind == "task" and data.get("task_id"):
        return f"/tasks/{data['task_id']}"
    if kind == "incident":
        if data.get("incident_id"):
            return f"/incidents/my?highlight={data['incident_id']}"
        return "/incidents/my"
    if kind == "appeal" and data.get("appeal_id"):
        return f"/appeals/{data['appeal_id']}"
    if kind == "order":
        return "/orders"
    if kind == "familiarization" and data.get("familiarization_id"):
        return f"/familiarizations/{data['familiarization_id']}"
    return "/"


def _https_base_url() -> str:
    cfg = get_mail_config()
    candidates = [
        (cfg.get("login_url") or "").strip(),
        (current_app.config.get("APP_BASE_URL") or "").strip(),
        (os.getenv("APP_BASE_URL") or "").strip(),
    ]
    for candidate in candidates:
        if candidate.startswith("https://"):
            return candidate.rstrip("/")
    return ""


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


def _firebase_message(messaging, platform: str, token: str, title: str, body: str, payload: dict[str, str]):
    if platform == "web":
        https_base = _https_base_url()
        link_path = payload.get("link") or "/"
        absolute_link = f"{https_base}{link_path}" if https_base else None
        icon_url = f"{https_base}/static/brand/altair/altair-app-icon-512.png" if https_base else None
        badge_url = f"{https_base}/static/brand/altair/altair-app-icon-128.png" if https_base else None
        return messaging.Message(
            token=token,
            data=payload,
            webpush=messaging.WebpushConfig(
                headers={"Urgency": "high"},
                data=payload,
                notification=messaging.WebpushNotification(
                    title=title[:255],
                    body=body[:2048],
                    icon=icon_url,
                    badge=badge_url,
                ),
                fcm_options=(
                    messaging.WebpushFCMOptions(link=absolute_link)
                    if absolute_link
                    else None
                ),
            ),
        )

    return messaging.Message(
        token=token,
        notification=messaging.Notification(
            title=title[:255],
            body=body[:2048],
        ),
        data=payload,
        android=messaging.AndroidConfig(priority="high"),
    )


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
    payload.setdefault("link", _push_link(payload))
    try:
        payload["unread_count"] = str(max(_badge_count_for_user(user_id), 0))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Mobile push unread count lookup failed: user_id=%s", user_id)
    for row in tokens:
        try:
            message = _firebase_message(
                messaging,
                (row.platform or "").strip().lower(),
                row.token,
                title,
                body,
                payload,
            )
            messaging.send(message)
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
