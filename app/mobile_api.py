from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import or_

from app.auth import _client_ip, _login_is_blocked, _record_failed_login, _reset_failed_login
from app.children import INCIDENT_CATEGORIES
from app.core.extensions import csrf, db
from app.models import (
    AcademicYear,
    Appeal,
    Child,
    ChildEnrollment,
    SchoolClass,
    Task,
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
        "creator": _user_to_dict(task.creator) if task.creator else None,
    }


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
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return jsonify(
        {
            "ok": True,
            "unread": task_unread + incident_unread + familiarization_unread,
            "items": items[:limit],
        }
    )


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
    return jsonify(
        {
            "ok": True,
            "items": [
                {
                    "id": item.id,
                    "number": item.number,
                    "subject": item.subject,
                    "applicant_name": item.applicant_name,
                    "status": item.status,
                    "deadline_at": item.deadline_at.isoformat() if item.deadline_at else None,
                    "is_overdue": bool(item.is_overdue),
                }
                for item in rows
            ],
        }
    )


@mobile_api_bp.get("/familiarizations/mine")
@_require_mobile_login
def my_familiarizations():
    rows = (
        FamiliarizationRecipient.query.filter_by(user_id=current_user.id)
        .join(FamiliarizationRecipient.familiarization)
        .order_by(FamiliarizationRecipient.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        {
            "ok": True,
            "unread": sum(1 for row in rows if not row.acknowledged_at),
            "items": [
                {
                    "id": row.familiarization.id,
                    "recipient_id": row.id,
                    "title": row.familiarization.title,
                    "description": row.familiarization.description,
                    "deadline_at": row.familiarization.deadline_at.isoformat()
                    if row.familiarization.deadline_at
                    else None,
                    "created_at": row.familiarization.created_at.isoformat()
                    if row.familiarization.created_at
                    else None,
                    "acknowledged_at": row.acknowledged_at.isoformat()
                    if row.acknowledged_at
                    else None,
                }
                for row in rows
            ],
        }
    )


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
