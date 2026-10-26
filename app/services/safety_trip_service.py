"""Excursion order validation, task synchronization and readiness status."""

from datetime import date, datetime, time

from app.core.extensions import db
from app.models import (
    SafetyTripAssignment, SafetyTripEvent, SafetyTripOrder,
    Task, TaskHistory, User,
)
from app.models.safety_passport import utc_now
from app.services.safety_passport_service import is_admin, is_director, is_officer


def parse_trip_data(form, order_date, responsible_ids):
    try:
        trip_date = date.fromisoformat(form.get("trip_date", ""))
    except ValueError as exc:
        raise ValueError("Укажите дату выезда.") from exc
    destination = (form.get("trip_destination") or "").strip()
    kind = (form.get("trip_kind") or "").strip()
    if not destination or len(destination) > 500:
        raise ValueError("Укажите место выезда (до 500 символов).")
    if not kind or len(kind) > 120:
        raise ValueError("Укажите вид выезда (до 120 символов).")
    if trip_date < order_date:
        raise ValueError("Дата выезда не может быть раньше даты приказа.")
    if not responsible_ids or len(responsible_ids) > 10:
        raise ValueError("Назначьте от одного до десяти ответственных сотрудников.")
    users = User.query.filter(User.id.in_(responsible_ids), User.is_active_user.is_(True)).all()
    if len(users) != len(set(responsible_ids)):
        raise ValueError("Один из ответственных сотрудников недоступен.")
    return {"trip_date": trip_date, "destination": destination, "trip_kind": kind}


def _task_text(trip):
    order = trip.order
    title = f"Журнал выезда по приказу № {order.number}"[:255]
    description = (
        f"{order.title}. {trip.trip_kind}; {trip.destination}; дата выезда {trip.trip_date.strftime('%d.%m.%Y')}. "
        f"Откройте карточку выезда в разделе «Журналы инструктажей» и сформируйте страницу."
    )
    return title, description


def _record_task(task, message, event_type):
    db.session.add(TaskHistory(task_id=task.id, event_type=event_type, message=message))


def _notify_task(task, notification_type, title, message):
    from app.tasks import _deliver_notifications
    _deliver_notifications(task, notification_type, title, message)


def _create_task(trip, user_id, actor_id):
    title, description = _task_text(trip)
    task = Task(
        title=title, description=description, priority="высокий", status=Task.STATUS_NEW,
        creator_user_id=actor_id, responsible_user_id=user_id, is_private=True,
        deadline_at=datetime.combine(trip.trip_date, time(8, 0)),
    )
    db.session.add(task)
    db.session.flush()
    _record_task(task, "Задача создана из приказа о выезде", "created")
    _notify_task(task, "new_task", "Журнал выезда", f"Вам назначен журнал по приказу № {trip.order.number}.")
    return task


def _refresh_task(trip, assignment, *, changed):
    task = assignment.task
    if task is None:
        task = _create_task(trip, assignment.user_id, trip.order.created_by_id or assignment.user_id)
        assignment.task_id = task.id
        return
    if not changed:
        return
    task.title, task.description = _task_text(trip)
    task.deadline_at = datetime.combine(trip.trip_date, time(8, 0))
    if task.status in {Task.STATUS_DONE, Task.STATUS_CLOSED, Task.STATUS_CANCELLED}:
        task.status = Task.STATUS_REWORK
        task.completed_at = None
    _record_task(task, "Приказ о выезде изменён; проверьте страницу журнала", "trip_order_changed")
    _notify_task(task, "task_updated", "Обновлён приказ о выезде", f"Проверьте журнал по приказу № {trip.order.number}.")


def sync_trip_order(order, values, responsible_ids, actor_id, *, prior_order_fields=None):
    """Synchronize one excursion order and its responsible tasks in the current transaction."""
    trip = db.session.get(SafetyTripOrder, order.id)
    created = trip is None
    if created:
        trip = SafetyTripOrder(order_id=order.id, **values)
        db.session.add(trip)
        db.session.flush()
    else:
        if trip.cancelled_at is not None:
            raise ValueError("Отменённый выезд нельзя изменять. Создайте новый приказ.")
        prior_trip_fields = (trip.trip_date, trip.destination, trip.trip_kind)
        trip.trip_date = values["trip_date"]
        trip.destination = values["destination"]
        trip.trip_kind = values["trip_kind"]
        changed = prior_trip_fields != (trip.trip_date, trip.destination, trip.trip_kind)
        if prior_order_fields is not None:
            changed = changed or prior_order_fields != (order.number, order.order_date, order.title)
        if changed:
            trip.revision_number += 1
    changed = created or (not created and changed)
    assignments = {item.user_id: item for item in trip.assignments}
    desired = set(responsible_ids)
    for user_id in desired:
        item = assignments.get(user_id)
        if item is None:
            task = _create_task(trip, user_id, actor_id)
            db.session.add(SafetyTripAssignment(order_id=order.id, user_id=user_id, task_id=task.id))
            db.session.add(SafetyTripEvent(order_id=order.id, actor_id=actor_id, action="responsible_added", details={"user_id": user_id, "task_id": task.id}))
        elif not item.is_active:
            item.is_active = True
            item.retired_at = None
            item.current_page_id = None
            _refresh_task(trip, item, changed=True)
            db.session.add(SafetyTripEvent(order_id=order.id, actor_id=actor_id, action="responsible_restored", details={"user_id": user_id}))
        else:
            _refresh_task(trip, item, changed=changed)
    for user_id, item in assignments.items():
        if user_id in desired or not item.is_active:
            continue
        item.is_active = False
        item.retired_at = utc_now()
        if item.task is not None:
            item.task.status = Task.STATUS_CANCELLED
            item.task.completed_at = None
            _record_task(item.task, "Ответственный исключён из приказа о выезде", "trip_responsible_removed")
        db.session.add(SafetyTripEvent(order_id=order.id, actor_id=actor_id, action="responsible_removed", details={"user_id": user_id}))
    db.session.add(SafetyTripEvent(order_id=order.id, actor_id=actor_id, action="created" if created else "updated", details={"revision": trip.revision_number, "changed": changed}))
    db.session.flush()
    return trip


def cancel_trip(trip, actor_id):
    if trip.cancelled_at is not None:
        return
    trip.cancelled_at = utc_now()
    trip.cancelled_by_id = actor_id
    for assignment in trip.assignments:
        if not assignment.is_active:
            continue
        assignment.is_active = False
        assignment.retired_at = utc_now()
        if assignment.task is not None:
            assignment.task.status = Task.STATUS_CANCELLED
            assignment.task.completed_at = None
            _record_task(assignment.task, "Приказ о выезде отменён", "trip_cancelled")
    db.session.add(SafetyTripEvent(order_id=trip.order_id, actor_id=actor_id, action="cancelled"))


def trip_status(trip):
    if trip.cancelled_at is not None:
        return "cancelled"
    assignments = [item for item in trip.assignments if item.is_active]
    if not assignments:
        return "waiting"
    pages = [item.current_page for item in assignments]
    if any(page and page.trip_order_revision != trip.revision_number for page in pages):
        return "requires_update"
    if any(page is None or page.status == "annulled" for page in pages):
        return "waiting"
    return "printed" if all(page.status == "printed" for page in pages) else "generated"


def can_view_trip(user, trip):
    if is_officer(user) or is_director(user) or is_admin(user):
        return True
    return any(item.is_active and item.user_id == user.id for item in trip.assignments)


def active_assignment(trip, user):
    if trip.cancelled_at is not None:
        return None
    return next((item for item in trip.assignments if item.is_active and item.user_id == user.id), None)


def trip_snapshot(trip, assignment):
    order = trip.order
    return {
        "order_id": order.id, "order_number": order.number,
        "order_date": order.order_date.isoformat(), "order_title": order.title,
        "trip_date": trip.trip_date.isoformat(), "destination": trip.destination,
        "trip_kind": trip.trip_kind, "responsible_user_id": assignment.user_id,
        "revision": trip.revision_number,
    }


def complete_assignment_task(assignment, page):
    trip = assignment.trip
    if not assignment.is_active or trip.cancelled_at is not None or assignment.current_page_id != page.id or page.trip_order_revision != trip.revision_number:
        return
    task = assignment.task
    if task is not None and task.status != Task.STATUS_DONE:
        task.status = Task.STATUS_DONE
        task.completed_at = datetime.utcnow()
        _record_task(task, f"Страница журнала {page.number} распечатана", "trip_journal_printed")


def reopen_assignment_task(assignment):
    task = assignment.task
    if task is not None and assignment.is_active and assignment.trip.cancelled_at is None:
        task.status = Task.STATUS_REWORK
        task.completed_at = None
        _record_task(task, "Страница журнала аннулирована; требуется новая", "trip_journal_annulled")


STATUS_LABELS = {
    "waiting": "Ожидает журнала",
    "generated": "Сформирован",
    "printed": "Распечатан",
    "requires_update": "Требует обновления",
    "cancelled": "Приказ отменён",
}
