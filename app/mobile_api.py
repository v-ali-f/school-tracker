from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request, send_file, session
from flask_login import current_user, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import bindparam, or_, text

from app.auth import _client_ip, _login_is_blocked, _record_failed_login, _reset_failed_login
from app.children import INCIDENT_CATEGORIES
from app.core.extensions import csrf, db
from app.models import (
    AcademicYear,
    Appeal,
    AppealAttachment,
    Child,
    ChildEnrollment,
    Familiarization,
    SchoolClass,
    Task,
    TaskAttachment,
    TaskComment,
    TaskHistory,
    TaskNotification,
    TaskParticipant,
    TaskType,
    User,
    FamiliarizationRecipient,
)
from app.models_legacy import (
    Incident,
    IncidentChild,
    IncidentNote,
    IncidentNotification,
    SchoolOrder,
)
from app.permissions import has_permission

mobile_api_bp = Blueprint("mobile_api", __name__, url_prefix="/mobile/api")
csrf.exempt(mobile_api_bp)

try:
    from zoneinfo import ZoneInfo

    _MSK_TZ = ZoneInfo("Europe/Moscow")
except Exception:  # pragma: no cover - fallback for minimal runtimes
    _MSK_TZ = timezone(timedelta(hours=3))

_MOBILE_TOKEN_MAX_AGE = 90 * 24 * 60 * 60
_TASK_CREATOR_ROLES = {
    "ADMIN", "DEPUTY_DIRECTOR", "METHODIST", "DIRECTOR", "CLASS_TEACHER",
    "TEACHER", "SPECIALIST", "SOCIAL_PEDAGOGUE", "LOGOPEDIST", "PSYCHOLOGIST",
    "DEFECTOLOGIST", "TUTOR", "ASSISTANT", "EDUCATOR", "SENIOR_EDUCATOR",
    "SECRETARY_ACADEMIC",
}
_APPEAL_MANAGER_ROLES = {
    "ADMIN", "DEPUTY_DIRECTOR", "DIRECTOR", "SECRETARY_ACADEMIC", "SECRETARY",
}
_FAMILIARIZATION_MANAGER_ROLES = {
    "ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR", "SECRETARY", "SECRETARY_ACADEMIC",
}
_TASK_ADMIN_ROLES = {"ADMIN", "DEPUTY_DIRECTOR", "METHODIST", "DIRECTOR"}


def _ensure_mobile_read_table():
    engine_name = db.engine.dialect.name
    if engine_name == "postgresql":
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS mobile_notification_read (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                kind VARCHAR(32) NOT NULL,
                entity_id INTEGER NOT NULL,
                read_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, kind, entity_id)
            )
        """))
    else:
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS mobile_notification_read (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind VARCHAR(32) NOT NULL,
                entity_id INTEGER NOT NULL,
                read_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, kind, entity_id)
            )
        """))


def _mobile_read_keys(kind: str, entity_ids: list[int]) -> set[int]:
    ids = [int(value) for value in entity_ids if value]
    if not ids:
        return set()
    try:
        _ensure_mobile_read_table()
        query = text("""
            SELECT entity_id
            FROM mobile_notification_read
            WHERE user_id = :user_id AND kind = :kind AND entity_id IN :ids
        """).bindparams(bindparam("ids", expanding=True))
        rows = db.session.execute(
            query,
            {"user_id": current_user.id, "kind": kind, "ids": ids},
        ).all()
        return {int(row[0]) for row in rows}
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Mobile notification read lookup failed")
        return set()


def _mark_mobile_read(kind: str, entity_id: int):
    if kind not in {"appeal", "order"}:
        return
    try:
        _ensure_mobile_read_table()
        exists = db.session.execute(
            text("""
                SELECT id
                FROM mobile_notification_read
                WHERE user_id = :user_id AND kind = :kind AND entity_id = :entity_id
                LIMIT 1
            """),
            {"user_id": current_user.id, "kind": kind, "entity_id": entity_id},
        ).first()
        if not exists:
            db.session.execute(
                text("""
                    INSERT INTO mobile_notification_read (user_id, kind, entity_id, read_at)
                    VALUES (:user_id, :kind, :entity_id, :read_at)
                """),
                {
                    "user_id": current_user.id,
                    "kind": kind,
                    "entity_id": entity_id,
                    "read_at": datetime.utcnow(),
                },
            )
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Mobile notification read mark failed")


def _mobile_user_from_any_token():
    user = _user_from_mobile_token()
    if user is not None:
        return user
    token = (request.args.get("token") or "").strip()
    if not token:
        return None
    try:
        data = _mobile_serializer().loads(token, max_age=_MOBILE_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    user = db.session.get(User, data.get("user_id"))
    if not user or getattr(user, "is_active_user", True) is False:
        return None
    if data.get("password") != (user.password_hash or "")[-24:]:
        return None
    return user


def _can_manage_familiarizations(user=None) -> bool:
    user = user or current_user
    return getattr(user, "role", None) in _FAMILIARIZATION_MANAGER_ROLES


def _is_task_participant(task: Task, user_id: int | None) -> bool:
    if not user_id:
        return False
    if user_id in {task.creator_user_id, task.responsible_user_id, task.controller_user_id}:
        return True
    return any(p.user_id == user_id for p in (task.participants or []))


def _can_view_task(task: Task, user=None) -> bool:
    user = user or current_user
    if getattr(user, "role", None) in _TASK_ADMIN_ROLES:
        return True
    return _is_task_participant(task, getattr(user, "id", None))


def _can_edit_task(task: Task, user=None) -> bool:
    user = user or current_user
    if getattr(user, "role", None) in _TASK_ADMIN_ROLES:
        return True
    uid = getattr(user, "id", None)
    if uid in {task.creator_user_id, task.responsible_user_id, task.controller_user_id}:
        return True
    return any(
        p.user_id == uid
        and p.role in {Task.PARTICIPANT_ROLE_COEXECUTOR, Task.PARTICIPANT_ROLE_CONTROLLER}
        for p in (task.participants or [])
    )


def _can_view_appeal(item: Appeal, user=None) -> bool:
    user = user or current_user
    if getattr(user, "role", None) in _APPEAL_MANAGER_ROLES:
        return True
    uid = getattr(user, "id", None)
    if uid in {item.creator_user_id, item.responsible_user_id}:
        return True
    ids = {
        int(value)
        for value in (item.responsible_user_ids or "").split(",")
        if value.strip().isdigit()
    }
    return uid in ids


def _now_msk_naive() -> datetime:
    return datetime.now(_MSK_TZ).replace(tzinfo=None)


def _current_year():
    return AcademicYear.query.filter_by(is_current=True).first()


def _json_error(message: str, status: int = 400, code: str = "bad_request"):
    return jsonify({"ok": False, "error": code, "message": message}), status


def _mobile_serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="altair-mobile-auth")


def _mobile_token(user: User) -> str:
    return _mobile_serializer().dumps(
        {"user_id": user.id, "password": (user.password_hash or "")[-24:]}
    )


def _user_from_mobile_token():
    header = (request.headers.get("Authorization") or "").strip()
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    if not token:
        return None
    try:
        data = _mobile_serializer().loads(token, max_age=_MOBILE_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    user = db.session.get(User, data.get("user_id"))
    if not user or getattr(user, "is_active_user", True) is False:
        return None
    if data.get("password") != (user.password_hash or "")[-24:]:
        return None
    return user


def _require_mobile_login(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not getattr(current_user, "is_authenticated", False):
            token_user = _user_from_mobile_token()
            if token_user is None:
                return _json_error("Требуется вход в систему.", 401, "unauthorized")
            login_user(token_user, remember=False, force=True)
        return view(*args, **kwargs)

    return wrapper


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "fio": getattr(user, "fio", None) or user.username,
        "role": user.role,
        "email": user.email,
        "phone": user.phone,
    }


def _class_to_dict(item: SchoolClass) -> dict:
    return {"id": item.id, "name": item.name, "grade": item.grade}


def _child_to_dict(child: Child) -> dict:
    return {
        "id": child.id,
        "fio": getattr(child, "fio", None)
        or " ".join(
            part
            for part in [child.last_name or "", child.first_name or "", child.middle_name or ""]
            if part
        ),
    }


def _incident_to_dict(incident: Incident) -> dict:
    children = []
    for link in getattr(incident, "links", []) or []:
        if link.child:
            children.append(_child_to_dict(link.child))
    return {
        "id": incident.id,
        "occurred_at": incident.occurred_at.isoformat() if incident.occurred_at else None,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "category": incident.category,
        "description": incident.description,
        "status": incident.status,
        "status_label": incident.status_label,
        "children": children,
        "author": _user_to_dict(incident.author) if incident.author else None,
        "assignee": _user_to_dict(incident.assignee) if incident.assignee else None,
    }


def _task_to_dict(task: Task) -> dict:
    coexecutors = [
        _user_to_dict(participant.user)
        for participant in (task.participants or [])
        if participant.user and participant.role == Task.PARTICIPANT_ROLE_COEXECUTOR
    ]
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "display_status": task.display_status,
        "priority": task.priority,
        "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "is_overdue": bool(task.is_overdue),
        "checklist_total": task.checklist_total,
        "checklist_done": task.checklist_done,
        "responsible": _user_to_dict(task.responsible) if task.responsible else None,
        "coexecutors": coexecutors,
        "creator": _user_to_dict(task.creator) if task.creator else None,
    }


def _task_detail_to_dict(task: Task) -> dict:
    data = _task_to_dict(task)
    can_edit = _can_edit_task(task)
    transitions = [
        status for status in Task.STATUS_CHOICES if task.can_transition_to(status) and status != task.status
    ] if can_edit else []
    data.update(
        {
            "can_edit": can_edit,
            "available_statuses": transitions,
            "participants": [
                {
                    "id": participant.id,
                    "role": participant.role,
                    "role_label": Task.PARTICIPANT_ROLE_LABELS.get(participant.role, participant.role),
                    "user": _user_to_dict(participant.user) if participant.user else None,
                }
                for participant in (task.participants or [])
            ],
            "comments": [
                {
                    "id": item.id,
                    "text": item.comment_text,
                    "is_system": bool(item.is_system_comment),
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "author": _user_to_dict(item.author) if item.author else None,
                }
                for item in TaskComment.query.filter_by(task_id=task.id)
                .order_by(TaskComment.created_at.desc())
                .limit(50)
                .all()
            ],
            "history": [
                {
                    "id": item.id,
                    "message": item.message,
                    "event_type": item.event_type,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "actor": _user_to_dict(item.actor) if item.actor else None,
                }
                for item in TaskHistory.query.filter_by(task_id=task.id)
                .order_by(TaskHistory.created_at.desc())
                .limit(30)
                .all()
            ],
            "attachments": [
                {
                    "id": item.id,
                    "filename": item.filename,
                    "file_kind": item.file_kind,
                    "file_size": item.file_size,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in (task.attachments or [])
                if not item.is_deleted
            ],
        }
    )
    return data


def _task_notification_to_dict(item: TaskNotification) -> dict:
    return {
        "id": item.id,
        "kind": "task",
        "entity_id": item.task_id,
        "type": item.notification_type,
        "title": item.title,
        "message": item.message,
        "is_read": bool(item.is_read),
        "is_important": bool(item.is_important),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _incident_notification_to_dict(item: IncidentNotification) -> dict:
    return {
        "id": item.id,
        "kind": "incident",
        "entity_id": item.incident_id,
        "type": item.notification_type,
        "title": item.title,
        "message": item.message,
        "is_read": bool(item.is_read),
        "is_important": False,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _appeal_to_dict(item: Appeal, detail: bool = False) -> dict:
    data = {
        "id": item.id,
        "number": item.number,
        "subject": item.subject,
        "applicant_name": item.applicant_name,
        "applicant_contact": item.applicant_contact,
        "channel": item.channel,
        "status": item.status,
        "received_at": item.received_at.isoformat() if item.received_at else None,
        "deadline_at": item.deadline_at.isoformat() if item.deadline_at else None,
        "answered_at": item.answered_at.isoformat() if item.answered_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "is_overdue": bool(item.is_overdue),
        "responsible": _user_to_dict(item.responsible) if item.responsible else None,
        "creator": _user_to_dict(item.creator) if item.creator else None,
        "linked_task_id": item.linked_task_id,
    }
    if detail:
        data.update(
            {
                "description": item.description,
                "result_text": item.result_text,
                "attachments": [
                    {
                        "id": attachment.id,
                        "filename": attachment.original_filename,
                        "created_at": attachment.created_at.isoformat()
                        if attachment.created_at
                        else None,
                    }
                    for attachment in (item.attachments or [])
                ],
            }
        )
    return data


def _familiarization_attachments(item: Familiarization) -> list[dict]:
    try:
        from app.familiarizations import _attachment_rows

        rows = _attachment_rows(item.id)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Mobile familiarization attachments lookup failed")
        rows = []
    attachments = [
        {
            "id": row.get("id") if hasattr(row, "get") else row["id"],
            "filename": (row.get("original_filename") if hasattr(row, "get") else row["original_filename"])
            or (row.get("stored_filename") if hasattr(row, "get") else row["stored_filename"]),
            "content_type": row.get("content_type") if hasattr(row, "get") else row["content_type"],
            "file_size": row.get("file_size") if hasattr(row, "get") else row["file_size"],
        }
        for row in rows
    ]
    if item.stored_filename and not any(row.get("id") is None for row in attachments):
        attachments.insert(
            0,
            {
                "id": None,
                "filename": item.original_filename or item.stored_filename,
                "content_type": item.content_type,
                "file_size": item.file_size,
            },
        )
    return attachments


def _familiarization_to_dict(item: Familiarization, recipient=None, detail: bool = False) -> dict:
    total = len(item.recipients or [])
    done = sum(1 for row in (item.recipients or []) if row.acknowledged_at)
    data = {
        "id": item.id,
        "recipient_id": recipient.id if recipient else None,
        "title": item.title,
        "description": item.description,
        "deadline_at": item.deadline_at.isoformat() if item.deadline_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "acknowledged_at": recipient.acknowledged_at.isoformat()
        if recipient and recipient.acknowledged_at
        else None,
        "is_recipient": recipient is not None,
        "can_acknowledge": recipient is not None and recipient.acknowledged_at is None,
        "stats": {"total": total, "done": done, "pending": total - done},
        "author": _user_to_dict(item.author) if item.author else None,
    }
    if detail:
        data["attachments"] = _familiarization_attachments(item)
        data["recipients"] = [
            {
                "id": row.id,
                "acknowledged_at": row.acknowledged_at.isoformat()
                if row.acknowledged_at
                else None,
                "user": _user_to_dict(row.user) if row.user else None,
            }
            for row in (item.recipients or [])
        ] if _can_manage_familiarizations() else []
    return data


def _payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    data = request.form.to_dict(flat=True) if request.form else {}
    if request.form:
        data["child_ids"] = request.form.getlist("child_ids")
    return data


def _list_from_payload(data: dict, key: str) -> list:
    value = data.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


@mobile_api_bp.post("/auth/login")
def login():
    ip = _client_ip()
    if _login_is_blocked(ip):
        return _json_error(
            "Слишком много неудачных попыток. Подождите 5 минут и попробуйте снова.",
            429,
            "rate_limited",
        )

    data = _payload()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        _record_failed_login(ip)
        return _json_error("Неверный логин или пароль.", 401, "invalid_credentials")

    if getattr(user, "is_active_user", True) is False:
        return _json_error("Пользователь отключен.", 403, "inactive_user")

    _reset_failed_login(ip)
    user.last_login_at = datetime.utcnow()
    db.session.commit()

    session.permanent = True
    login_user(user)
    return jsonify({"ok": True, "user": _user_to_dict(user), "token": _mobile_token(user)})


@mobile_api_bp.post("/auth/logout")
@_require_mobile_login
def logout():
    logout_user()
    return jsonify({"ok": True})


@mobile_api_bp.get("/me")
@_require_mobile_login
def me():
    return jsonify(
        {
            "ok": True,
            "user": _user_to_dict(current_user),
            "permissions": {
                "can_add_incident": has_permission("incident_add", user=current_user),
                "can_view_incident_registry": has_permission("incident_registry_view", user=current_user),
                "can_view_incident_dashboard": has_permission("incident_dashboard_view", user=current_user),
            },
        }
    )


@mobile_api_bp.get("/notifications")
@_require_mobile_login
def notifications():
    limit = min(max(request.args.get("limit", default=30, type=int), 1), 100)
    task_unread = TaskNotification.query.filter_by(user_id=current_user.id, is_read=False).count()
    incident_unread = IncidentNotification.query.filter_by(user_id=current_user.id, is_read=False).count()
    familiarization_unread = FamiliarizationRecipient.query.filter_by(
        user_id=current_user.id, acknowledged_at=None
    ).count()
    task_items = (
        TaskNotification.query.filter_by(user_id=current_user.id)
        .order_by(TaskNotification.created_at.desc())
        .limit(limit)
        .all()
    )
    incident_items = (
        IncidentNotification.query.filter_by(user_id=current_user.id)
        .order_by(IncidentNotification.created_at.desc())
        .limit(limit)
        .all()
    )
    familiarization_items = (
        FamiliarizationRecipient.query.filter_by(user_id=current_user.id)
        .join(FamiliarizationRecipient.familiarization)
        .order_by(FamiliarizationRecipient.created_at.desc())
        .limit(limit)
        .all()
    )
    appeal_items = []
    if getattr(current_user, "role", None) in _APPEAL_MANAGER_ROLES:
        appeal_items = Appeal.query.order_by(Appeal.created_at.desc()).limit(20).all()
    appeal_read_ids = _mobile_read_keys("appeal", [item.id for item in appeal_items])
    order_items = (
        SchoolOrder.query.order_by(SchoolOrder.order_date.desc(), SchoolOrder.id.desc())
        .limit(20)
        .all()
    )
    order_read_ids = _mobile_read_keys("order", [item.id for item in order_items])
    appeal_unread = sum(1 for item in appeal_items if item.id not in appeal_read_ids)
    order_unread = sum(1 for item in order_items if item.id not in order_read_ids)
    items = [_task_notification_to_dict(x) for x in task_items]
    items.extend(_incident_notification_to_dict(x) for x in incident_items)
    items.extend(
        {
            "id": row.id,
            "kind": "familiarization",
            "entity_id": row.familiarization_id,
            "type": "familiarization",
            "title": "Документ для ознакомления",
            "message": row.familiarization.title,
            "is_read": row.acknowledged_at is not None,
            "is_important": row.acknowledged_at is None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in familiarization_items
    )
    items.extend(
        {
            "id": item.id,
            "kind": "appeal",
            "entity_id": item.id,
            "type": "appeal",
            "title": "Обращение",
            "message": f"{item.subject} · {item.status}",
            "is_read": item.id in appeal_read_ids,
            "is_important": bool(item.is_overdue),
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in appeal_items
    )
    items.extend(
        {
            "id": item.id,
            "kind": "order",
            "entity_id": item.id,
            "type": "order",
            "title": "Приказ",
            "message": f"№ {item.number or '—'} · {item.title or ''}",
            "is_read": item.id in order_read_ids,
            "is_important": False,
            "created_at": item.order_date.isoformat() if item.order_date else None,
        }
        for item in order_items
    )
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return jsonify(
        {
            "ok": True,
            "unread": task_unread
            + incident_unread
            + familiarization_unread
            + appeal_unread
            + order_unread,
            "counts": {
                "tasks": task_unread,
                "incidents": incident_unread,
                "familiarizations": familiarization_unread,
                "appeals": appeal_unread,
                "orders": order_unread,
                "total": task_unread
                + incident_unread
                + familiarization_unread
                + appeal_unread
                + order_unread,
            },
            "items": items[:limit],
        }
    )


@mobile_api_bp.post("/notifications/<kind>/<int:entity_id>/read")
@_require_mobile_login
def read_mobile_notification(kind: str, entity_id: int):
    if kind not in {"appeal", "order"}:
        return _json_error("Такое уведомление отмечается автоматически.", 400, "unsupported_kind")
    _mark_mobile_read(kind, entity_id)
    db.session.commit()
    return jsonify({"ok": True})


@mobile_api_bp.get("/tasks/mine")
@_require_mobile_login
def my_tasks():
    limit = min(max(request.args.get("limit", default=100, type=int), 1), 200)
    selected_filter = (request.args.get("filter") or "active").strip().lower()
    completed_statuses = [Task.STATUS_DONE, Task.STATUS_CLOSED, Task.STATUS_CANCELLED]
    query = Task.query.filter(
        or_(
            Task.responsible_user_id == current_user.id,
            Task.controller_user_id == current_user.id,
            Task.creator_user_id == current_user.id,
            Task.id.in_(
                db.session.query(TaskParticipant.task_id).filter(
                    TaskParticipant.user_id == current_user.id
                )
            ),
        )
    )

    if selected_filter == "active":
        query = query.filter(Task.status.notin_(completed_statuses)).filter(
            or_(Task.deadline_at.is_(None), Task.deadline_at >= datetime.utcnow())
        )
    elif selected_filter == "overdue":
        query = query.filter(
            Task.status.notin_(completed_statuses),
            Task.deadline_at.isnot(None),
            Task.deadline_at < datetime.utcnow(),
        )
    elif selected_filter == "completed":
        query = query.filter(Task.status.in_(completed_statuses))
    elif selected_filter != "all":
        return _json_error("Неизвестный фильтр задач.", 400, "invalid_task_filter")

    items = (
        query.order_by(
            Task.deadline_at.is_(None),
            Task.deadline_at.asc(),
            Task.created_at.desc(),
        )
        .limit(limit)
        .all()
    )
    return jsonify(
        {
            "ok": True,
            "filter": selected_filter,
            "items": [_task_to_dict(item) for item in items],
        }
    )


@mobile_api_bp.get("/tasks/meta")
@_require_mobile_login
def task_meta():
    can_create = getattr(current_user, "role", None) in _TASK_CREATOR_ROLES
    users = (
        User.query.filter_by(is_active_user=True)
        .order_by(User.last_name.asc(), User.first_name.asc(), User.username.asc())
        .all()
    )
    task_types = (
        TaskType.query.filter_by(is_active=True)
        .order_by(TaskType.sort_order.asc(), TaskType.name.asc())
        .all()
    )
    return jsonify(
        {
            "ok": True,
            "can_create": can_create,
            "priorities": Task.PRIORITY_CHOICES,
            "users": [_user_to_dict(user) for user in users],
            "task_types": [{"id": item.id, "name": item.name} for item in task_types],
        }
    )


@mobile_api_bp.post("/tasks")
@_require_mobile_login
def create_task():
    if getattr(current_user, "role", None) not in _TASK_CREATOR_ROLES:
        return _json_error("Нет права на создание задач.", 403, "forbidden")

    data = _payload()
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip() or None
    priority = (data.get("priority") or "обычный").strip()
    responsible_user_id = data.get("responsible_user_id")
    task_type_id = data.get("task_type_id")
    coexecutor_ids = []
    for raw in _list_from_payload(data, "coexecutor_user_ids"):
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            continue
        if uid and uid not in coexecutor_ids:
            coexecutor_ids.append(uid)

    try:
        responsible_user_id = int(responsible_user_id)
    except (TypeError, ValueError):
        responsible_user_id = None
    try:
        task_type_id = int(task_type_id) if task_type_id else None
    except (TypeError, ValueError):
        task_type_id = None

    if not title:
        return _json_error("Укажите название задачи.", 400, "missing_title")
    responsible = db.session.get(User, responsible_user_id) if responsible_user_id else None
    if not responsible or getattr(responsible, "is_active_user", True) is False:
        return _json_error("Выберите ответственного.", 400, "invalid_responsible")

    deadline_at = None
    deadline_raw = (data.get("deadline_at") or "").strip()
    if deadline_raw:
        try:
            deadline_at = datetime.fromisoformat(deadline_raw.replace("Z", "+00:00"))
            if deadline_at.tzinfo:
                deadline_at = deadline_at.astimezone(_MSK_TZ).replace(tzinfo=None)
        except ValueError:
            return _json_error("Неверный формат срока задачи.", 400, "invalid_deadline")

    task = Task(
        title=title,
        description=description,
        task_type_id=task_type_id,
        priority=priority if priority in Task.PRIORITY_CHOICES else "обычный",
        status=Task.STATUS_NEW,
        creator_user_id=current_user.id,
        responsible_user_id=responsible.id,
        deadline_at=deadline_at,
        is_control_required=bool(data.get("is_control_required")),
        is_private=bool(data.get("is_private")),
    )
    db.session.add(task)
    db.session.flush()
    for user in User.query.filter(User.id.in_(coexecutor_ids)).all() if coexecutor_ids else []:
        if user.id != responsible.id and getattr(user, "is_active_user", True) is not False:
            db.session.add(
                TaskParticipant(
                    task_id=task.id,
                    user_id=user.id,
                    role=Task.PARTICIPANT_ROLE_COEXECUTOR,
                )
            )
    try:
        from app.tasks import _deliver_notifications

        _deliver_notifications(
            task,
            "new_task",
            "Новая задача",
            f"Вам назначена задача «{task.title}».",
            extra_user_ids=coexecutor_ids,
        )
    except Exception:
        current_app.logger.exception("Mobile task notification delivery failed")
        db.session.add(
            TaskNotification(
                task_id=task.id,
                user_id=responsible.id,
                notification_type="new_task",
                title="Новая задача",
                message=f"Вам назначена задача «{task.title}».",
                is_important=priority in {"срочный", "критический"},
            )
        )
    db.session.commit()
    return jsonify({"ok": True, "task": _task_to_dict(task)}), 201


@mobile_api_bp.get("/tasks/<int:task_id>")
@_require_mobile_login
def task_detail(task_id: int):
    task = Task.query.get_or_404(task_id)
    if not _can_view_task(task):
        return _json_error("Нет доступа к задаче.", 403, "forbidden")
    TaskNotification.query.filter_by(
        task_id=task.id, user_id=current_user.id, is_read=False
    ).update(
        {TaskNotification.is_read: True, TaskNotification.read_at: datetime.utcnow()},
        synchronize_session=False,
    )
    db.session.commit()
    return jsonify({"ok": True, "task": _task_detail_to_dict(task)})


@mobile_api_bp.post("/tasks/<int:task_id>/status")
@_require_mobile_login
def mobile_task_status(task_id: int):
    task = Task.query.filter_by(id=task_id).with_for_update().first()
    if task is None:
        return _json_error("Задача не найдена.", 404, "not_found")
    if not _can_edit_task(task):
        return _json_error("Нет права менять задачу.", 403, "forbidden")
    data = _payload()
    status = (data.get("status") or "").strip()
    if status not in Task.STATUS_CHOICES:
        return _json_error("Недопустимый статус.", 400, "invalid_status")
    if not task.can_transition_to(status):
        return _json_error("Недопустимый переход между статусами.", 400, "invalid_status_transition")
    old_status = task.status
    task.status = status
    if status in {Task.STATUS_DONE, Task.STATUS_CLOSED}:
        task.completed_at = datetime.utcnow()
    elif old_status in {Task.STATUS_DONE, Task.STATUS_CLOSED} and status == Task.STATUS_REWORK:
        task.completed_at = None
    comment_text = (data.get("comment") or "").strip() or f"Изменен статус: {status}"
    db.session.add(
        TaskComment(
            task_id=task.id,
            author_user_id=current_user.id,
            comment_text=comment_text,
            is_system_comment=True,
        )
    )
    db.session.add(
        TaskHistory(
            task_id=task.id,
            actor_user_id=current_user.id,
            event_type="status_changed",
            field_name="status",
            old_value=old_status,
            new_value=status,
            message=f"Изменен статус: {old_status} → {status}",
        )
    )
    notification_type = "status_changed"
    notification_title = "Изменение статуса задачи"
    notification_message = f"По задаче «{task.title}» установлен статус «{status}»."
    if status == Task.STATUS_REWORK:
        notification_type = "returned_for_rework"
        notification_title = "Задача возвращена на доработку"
        notification_message = f"Задача «{task.title}» возвращена на доработку."
    elif status in {Task.STATUS_DONE, Task.STATUS_CLOSED}:
        notification_type = "closed"
        notification_title = "Задача закрыта"
        notification_message = f"Задача «{task.title}» закрыта."
    try:
        from app.tasks import _deliver_notifications

        _deliver_notifications(task, notification_type, notification_title, notification_message)
    except Exception:
        current_app.logger.exception("Mobile task status notification delivery failed")
        db.session.add(
            TaskNotification(
                task_id=task.id,
                user_id=task.responsible_user_id,
                notification_type=notification_type,
                title=notification_title,
                message=notification_message,
                is_important=status == Task.STATUS_REWORK,
            )
        )
    db.session.commit()
    return jsonify({"ok": True, "task": _task_detail_to_dict(task)})


@mobile_api_bp.post("/tasks/<int:task_id>/comments")
@_require_mobile_login
def mobile_task_comment(task_id: int):
    task = Task.query.get_or_404(task_id)
    if not _can_view_task(task):
        return _json_error("Нет доступа к задаче.", 403, "forbidden")
    text_value = (_payload().get("text") or "").strip()
    if not text_value:
        return _json_error("Введите комментарий.", 400, "missing_comment")
    db.session.add(TaskComment(task_id=task.id, author_user_id=current_user.id, comment_text=text_value))
    db.session.add(
        TaskHistory(
            task_id=task.id,
            actor_user_id=current_user.id,
            event_type="comment_added",
            message="Добавлен комментарий",
        )
    )
    db.session.commit()
    return jsonify({"ok": True, "task": _task_detail_to_dict(task)})


@mobile_api_bp.get("/orders")
@_require_mobile_login
def orders():
    try:
        from app.orders import _allowed_order_sections

        sections = _allowed_order_sections("view")
    except Exception:
        current_app.logger.exception("Mobile orders access lookup failed")
        sections = []
    if not sections:
        return jsonify({"ok": True, "items": []})
    rows = (
        SchoolOrder.query.filter(SchoolOrder.section.in_(sections))
        .order_by(SchoolOrder.order_date.desc(), SchoolOrder.number.desc())
        .limit(100)
        .all()
    )
    read_ids = _mobile_read_keys("order", [item.id for item in rows])
    return jsonify(
        {
            "ok": True,
            "items": [
                {
                    "id": item.id,
                    "number": item.number,
                    "title": item.title,
                    "section": item.section,
                    "order_date": item.order_date.isoformat() if item.order_date else None,
                    "executor": item.executor,
                    "is_read": item.id in read_ids,
                }
                for item in rows
            ],
        }
    )


@mobile_api_bp.get("/appeals")
@_require_mobile_login
def appeals():
    query = Appeal.query
    if getattr(current_user, "role", None) not in _APPEAL_MANAGER_ROLES:
        uid = current_user.id
        uid_text = str(uid)
        query = query.filter(
            or_(
                Appeal.creator_user_id == uid,
                Appeal.responsible_user_id == uid,
                Appeal.responsible_user_ids == uid_text,
                Appeal.responsible_user_ids.like(f"{uid_text},%"),
                Appeal.responsible_user_ids.like(f"%,{uid_text},%"),
                Appeal.responsible_user_ids.like(f"%,{uid_text}"),
            )
        )
    rows = query.order_by(Appeal.created_at.desc()).limit(100).all()
    read_ids = _mobile_read_keys("appeal", [item.id for item in rows])
    return jsonify(
        {
            "ok": True,
            "items": [
                {**_appeal_to_dict(item), "is_read": item.id in read_ids}
                for item in rows
            ],
        }
    )


@mobile_api_bp.get("/appeals/<int:appeal_id>")
@_require_mobile_login
def appeal_detail(appeal_id: int):
    item = Appeal.query.get_or_404(appeal_id)
    if not _can_view_appeal(item):
        return _json_error("Нет доступа к обращению.", 403, "forbidden")
    _mark_mobile_read("appeal", item.id)
    db.session.commit()
    return jsonify({"ok": True, "appeal": _appeal_to_dict(item, detail=True)})


@mobile_api_bp.get("/familiarizations/mine")
@_require_mobile_login
def my_familiarizations():
    if _can_manage_familiarizations():
        items = Familiarization.query.order_by(Familiarization.created_at.desc()).limit(200).all()
        rows_by_item = {
            row.familiarization_id: row
            for row in FamiliarizationRecipient.query.filter_by(user_id=current_user.id).all()
        }
        payload_items = [
            _familiarization_to_dict(item, rows_by_item.get(item.id)) for item in items
        ]
    else:
        rows = (
            FamiliarizationRecipient.query.filter_by(user_id=current_user.id)
            .join(FamiliarizationRecipient.familiarization)
            .order_by(FamiliarizationRecipient.created_at.desc())
            .limit(100)
            .all()
        )
        payload_items = [_familiarization_to_dict(row.familiarization, row) for row in rows]
    return jsonify(
        {
            "ok": True,
            "is_manager": _can_manage_familiarizations(),
            "unread": sum(1 for item in payload_items if item.get("can_acknowledge")),
            "items": payload_items,
        }
    )


@mobile_api_bp.get("/familiarizations/<int:item_id>")
@_require_mobile_login
def familiarization_detail(item_id: int):
    item = Familiarization.query.get_or_404(item_id)
    recipient = FamiliarizationRecipient.query.filter_by(
        familiarization_id=item.id, user_id=current_user.id
    ).first()
    if not _can_manage_familiarizations() and recipient is None:
        return _json_error("Нет доступа к ознакомлению.", 403, "forbidden")
    return jsonify({"ok": True, "familiarization": _familiarization_to_dict(item, recipient, detail=True)})


@mobile_api_bp.post("/familiarizations/<int:item_id>/acknowledge")
@_require_mobile_login
def acknowledge_familiarization(item_id: int):
    row = FamiliarizationRecipient.query.filter_by(
        familiarization_id=item_id, user_id=current_user.id
    ).first()
    if row is None:
        return _json_error("Ознакомление не найдено.", 404, "not_found")
    if row.acknowledged_at is None:
        row.acknowledged_at = datetime.utcnow()
        db.session.commit()
    return jsonify({"ok": True})


@mobile_api_bp.get("/familiarizations/<int:item_id>/attachments/<attachment_id>/download")
def familiarization_attachment_download(item_id: int, attachment_id: str):
    user = _mobile_user_from_any_token()
    if user is None:
        return _json_error("Требуется вход в систему.", 401, "unauthorized")
    item = Familiarization.query.get_or_404(item_id)
    recipient = FamiliarizationRecipient.query.filter_by(
        familiarization_id=item.id, user_id=user.id
    ).first()
    if not _can_manage_familiarizations(user) and recipient is None:
        return _json_error("Нет доступа к ознакомлению.", 403, "forbidden")
    try:
        from app.familiarizations import _attachment_rows, _upload_root

        if attachment_id == "main":
            stored = item.stored_filename
            filename = item.original_filename or item.stored_filename
        else:
            row = next(
                (
                    value
                    for value in _attachment_rows(item.id)
                    if str(value.get("id") if hasattr(value, "get") else value["id"]) == attachment_id
                ),
                None,
            )
            if not row:
                return _json_error("Файл не найден.", 404, "not_found")
            stored = row.get("stored_filename") if hasattr(row, "get") else row["stored_filename"]
            filename = (
                row.get("original_filename") if hasattr(row, "get") else row["original_filename"]
            ) or stored
        if not stored:
            return _json_error("Файл не найден.", 404, "not_found")
        path = _upload_root() / stored
        if not path.exists():
            return _json_error("Файл не найден.", 404, "not_found")
        return send_file(path, as_attachment=False, download_name=filename)
    except Exception:
        current_app.logger.exception("Mobile familiarization attachment download failed")
        return _json_error("Не удалось открыть файл.", 500, "download_failed")


@mobile_api_bp.post("/notifications/incident/<int:notification_id>/read")
@_require_mobile_login
def read_incident_notification(notification_id: int):
    item = IncidentNotification.query.get_or_404(notification_id)
    if item.user_id != current_user.id:
        return _json_error("Нет доступа к уведомлению.", 403, "forbidden")
    if not item.is_read:
        item.is_read = True
        item.read_at = datetime.utcnow()
        db.session.commit()
    return jsonify({"ok": True})


@mobile_api_bp.get("/incidents/meta")
@_require_mobile_login
def incident_meta():
    grades = []
    year = _current_year()
    if year:
        rows = (
            db.session.query(SchoolClass.grade)
            .filter(SchoolClass.academic_year_id == year.id)
            .filter(SchoolClass.grade.isnot(None))
            .distinct()
            .order_by(SchoolClass.grade.asc())
            .all()
        )
        grades = [row[0] for row in rows]
    return jsonify({"ok": True, "categories": INCIDENT_CATEGORIES, "grades": grades})


@mobile_api_bp.get("/classes")
@_require_mobile_login
def classes():
    grade = request.args.get("grade", type=int)
    year = _current_year()
    if not year:
        return jsonify({"ok": True, "items": []})
    query = SchoolClass.query.filter(SchoolClass.academic_year_id == year.id)
    if grade:
        query = query.filter(SchoolClass.grade == grade)
    items = query.order_by(SchoolClass.grade.asc(), SchoolClass.name.asc()).all()
    return jsonify({"ok": True, "items": [_class_to_dict(x) for x in items]})


@mobile_api_bp.get("/classes/<int:class_id>/children")
@_require_mobile_login
def class_children(class_id: int):
    year = _current_year()
    if not year:
        return jsonify({"ok": True, "items": []})
    rows = (
        ChildEnrollment.query.join(Child, ChildEnrollment.child_id == Child.id)
        .filter(
            ChildEnrollment.academic_year_id == year.id,
            ChildEnrollment.school_class_id == class_id,
            ChildEnrollment.ended_at.is_(None),
        )
        .order_by(Child.last_name.asc(), Child.first_name.asc(), Child.middle_name.asc())
        .all()
    )
    return jsonify({"ok": True, "items": [_child_to_dict(row.child) for row in rows if row.child]})


@mobile_api_bp.get("/incidents/mine")
@_require_mobile_login
def my_incidents():
    limit = min(max(request.args.get("limit", default=50, type=int), 1), 100)
    authored = (
        Incident.query.filter(Incident.author_id == current_user.id)
        .order_by(Incident.occurred_at.desc(), Incident.id.desc())
        .limit(limit)
        .all()
    )
    assigned = (
        Incident.query.filter(Incident.assignees.any(id=current_user.id))
        .order_by(Incident.occurred_at.desc(), Incident.id.desc())
        .limit(limit)
        .all()
    )
    registry = []
    if has_permission("incident_registry_view", user=current_user):
        registry = (
            Incident.query.order_by(Incident.occurred_at.desc(), Incident.id.desc())
            .limit(limit)
            .all()
        )
    return jsonify(
        {
            "ok": True,
            "authored": [_incident_to_dict(item) for item in authored],
            "assigned": [_incident_to_dict(item) for item in assigned],
            "registry": [_incident_to_dict(item) for item in registry],
        }
    )


@mobile_api_bp.post("/incidents")
@_require_mobile_login
def create_incident():
    if not has_permission("incident_add", user=current_user):
        return _json_error("Нет права на создание инцидентов.", 403, "forbidden")

    data = _payload()
    category = (data.get("category") or "").strip()
    description = (data.get("description") or "").strip()
    initial_work = (data.get("initial_work") or "").strip()

    child_ids = []
    for raw in _list_from_payload(data, "child_ids"):
        try:
            child_id = int(raw)
        except (TypeError, ValueError):
            continue
        if child_id not in child_ids:
            child_ids.append(child_id)

    occurred_at_raw = (data.get("occurred_at") or "").strip()
    if occurred_at_raw:
        try:
            occurred_at = datetime.fromisoformat(occurred_at_raw.replace("Z", "+00:00"))
            if occurred_at.tzinfo:
                occurred_at = occurred_at.astimezone(_MSK_TZ).replace(tzinfo=None)
        except ValueError:
            return _json_error("Неверный формат даты/времени.", 400, "invalid_occurred_at")
    else:
        occurred_date = (data.get("occurred_date") or "").strip()
        occurred_time = (data.get("occurred_time") or "").strip()
        if not occurred_date or not occurred_time:
            return _json_error("Укажите дату и время инцидента.", 400, "missing_occurred_at")
        try:
            occurred_at = datetime.strptime(f"{occurred_date} {occurred_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            return _json_error("Неверный формат даты/времени.", 400, "invalid_occurred_at")

    if category not in INCIDENT_CATEGORIES:
        return _json_error("Выберите категорию инцидента.", 400, "invalid_category")
    if not description:
        return _json_error("Заполните описание инцидента.", 400, "missing_description")
    if not child_ids:
        return _json_error("Добавьте хотя бы одного ребенка.", 400, "missing_children")

    now = _now_msk_naive()
    if occurred_at < now - timedelta(hours=48):
        return _json_error(
            "Дата инцидента не должна быть раньше, чем за 48 часов до момента подачи заявки.",
            400,
            "occurred_at_too_old",
        )
    if occurred_at > now + timedelta(minutes=5):
        return _json_error("Дата инцидента не может быть в будущем.", 400, "occurred_at_in_future")

    children = Child.query.filter(Child.id.in_(child_ids)).all()
    found_ids = {child.id for child in children}
    missing_ids = [child_id for child_id in child_ids if child_id not in found_ids]
    if missing_ids:
        return _json_error("Один или несколько учеников не найдены.", 400, "children_not_found")

    incident = Incident(
        occurred_at=occurred_at,
        category=category,
        description=description,
        status=Incident.STATUS_NEW,
        author_id=current_user.id,
        created_at=datetime.utcnow(),
    )
    db.session.add(incident)
    db.session.flush()

    for child_id in child_ids:
        db.session.add(IncidentChild(incident_id=incident.id, child_id=child_id))

    if initial_work:
        db.session.add(
            IncidentNote(
                incident_id=incident.id,
                author_id=current_user.id,
                text=f"[Сделано автором] {initial_work}",
            )
        )

    db.session.commit()
    return jsonify({"ok": True, "incident": _incident_to_dict(incident)}), 201
