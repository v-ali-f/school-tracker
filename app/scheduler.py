"""Фоновый планировщик задач (APScheduler).

Задачи:
- `kubok_weekly_refresh` — каждый понедельник в 09:00 МСК тянет свежие данные
  из Google Sheets и перезаписывает локальный кеш Кубка школы.

Запуск только в основном процессе:
- В Flask debug-режиме werkzeug стартует child-процесс с reloader.
  В дочернем процессе переменная `WERKZEUG_RUN_MAIN == 'true'`,
  только в нём планировщик и должен подняться (иначе запустится дважды).
- В проде (gunicorn / nginx + uwsgi) запускается всегда.

Чтобы не мешать тестам/CLI: можно отключить через ENV `KUBOK_SCHEDULER_DISABLED=1`.
"""
from __future__ import annotations

import os
import time
from threading import RLock

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

_scheduler: BackgroundScheduler | None = None

# Brute-force защита MaxBinding: 6-значный код можно перебирать через
# `/start <код>` с разных MAX-аккаунтов. Считаем неудачные попытки по
# chat_id; после порога — игнорируем bind-запросы от этого chat_id.
_BIND_FAILS: dict[str, list[float]] = {}
_BIND_FAILS_LOCK = RLock()
_BIND_WINDOW_SECONDS = 300         # 5 минут на накопление неудач
_BIND_MAX_FAILS = 5                # порог
_BIND_BLOCK_SECONDS = 3600         # 1 час lockout


def _bind_chat_blocked(chat_id) -> bool:
    if not chat_id:
        return False
    key = str(chat_id)
    now = time.time()
    with _BIND_FAILS_LOCK:
        fails = [t for t in _BIND_FAILS.get(key, []) if now - t < _BIND_BLOCK_SECONDS]
        _BIND_FAILS[key] = fails
        recent = [t for t in fails if now - t < _BIND_WINDOW_SECONDS]
        return len(recent) >= _BIND_MAX_FAILS


def _bind_record_fail(chat_id) -> None:
    if not chat_id:
        return
    key = str(chat_id)
    with _BIND_FAILS_LOCK:
        _BIND_FAILS.setdefault(key, []).append(time.time())


def _bind_reset(chat_id) -> None:
    if not chat_id:
        return
    with _BIND_FAILS_LOCK:
        _BIND_FAILS.pop(str(chat_id), None)


def _kubok_weekly_refresh(app):
    with app.app_context():
        try:
            from app.kubok import refresh_cache
            count, ts = refresh_cache()
            app.logger.info(
                "Kubok weekly refresh OK: %s классов обновлено в %s UTC",
                count, ts.isoformat(timespec="seconds"),
            )
        except Exception as exc:  # noqa: BLE001
            app.logger.error("Kubok weekly refresh FAILED: %s", exc)


def _page_visit_retention(app, days: int = 30):
    with app.app_context():
        try:
            from datetime import datetime, timedelta
            from app.core.extensions import db
            from app.models.page_visit import PageVisit
            cutoff = datetime.utcnow() - timedelta(days=days)
            deleted = (
                PageVisit.query
                .filter(PageVisit.ts < cutoff)
                .delete(synchronize_session=False)
            )
            db.session.commit()
            app.logger.info("PageVisit retention OK: удалено %s записей старше %s дней", deleted, days)
        except Exception as exc:  # noqa: BLE001
            app.logger.error("PageVisit retention FAILED: %s", exc)


def _bind_payload_for_user(user):
    """Профиль пользователя для бота.

    students — ВСЕ ученики школы за текущий учебный год (актуальные зачисления),
    чтобы бот мог делать локальный поиск по фамилии без round-trip к порталу.
    classes_meta — классы, где пользователь является классным руководителем
    (оставлено для обратной совместимости; бот сам фильтрует по нужному классу).
    """
    from app.models import SchoolClass, ChildEnrollment, Child
    from app.children import _get_current_year  # noqa: WPS437
    try:
        year = _get_current_year()
    except Exception:
        year = None

    classes_meta = []
    students = []
    if year:
        own_classes = (
            SchoolClass.query
            .filter_by(teacher_user_id=user.id, academic_year_id=year.id, is_archived=False)
            .all()
        )
        classes_meta = [{"id": c.id, "name": c.name} for c in own_classes]

        # Все классы школы за год → имена для меток.
        all_classes = (
            SchoolClass.query
            .filter_by(academic_year_id=year.id, is_archived=False)
            .all()
        )
        class_name_by_id = {c.id: c.name for c in all_classes}

        # Все активные зачисления текущего года.
        ens = (
            ChildEnrollment.query
            .join(Child, ChildEnrollment.child_id == Child.id)
            .filter(
                ChildEnrollment.academic_year_id == year.id,
                ChildEnrollment.ended_at.is_(None),
            )
            .order_by(Child.last_name.asc(), Child.first_name.asc())
            .all()
        )
        for en in ens:
            ch = en.child
            if not ch:
                continue
            students.append({
                "id": ch.id,
                "fio": ch.fio,
                "class_id": en.school_class_id,
                "class_name": class_name_by_id.get(en.school_class_id),
            })

    role = getattr(user, "role", None)
    return {
        "user_id": user.id,
        "full_name": user.fio or user.username,
        "role": role,
        "class_ids_meta": classes_meta,
        "students": students,
    }


def _parse_familiarization_ack_item(ack_item):
    """Разбирает нажатие «Ознакомлен» из MAX-бота.

    Бот в разных версиях может вернуть уже разобранные поля или исходный
    callback payload вида `fam_ack:<familiarization_id>:<user_id>`.
    """
    ack_id = (
        ack_item.get("ack_id")
        or ack_item.get("id")
        or ack_item.get("queue_id")
        or ack_item.get("callback_id")
    )
    familiarization_id = (
        ack_item.get("familiarization_id")
        or ack_item.get("familiarizationId")
        or ack_item.get("fam_id")
    )
    user_id = ack_item.get("user_id") or ack_item.get("userId")

    callback = ack_item.get("callback") if isinstance(ack_item.get("callback"), dict) else {}
    update = ack_item.get("update") if isinstance(ack_item.get("update"), dict) else {}
    update_callback = update.get("callback") if isinstance(update.get("callback"), dict) else {}
    payload = (
        ack_item.get("payload")
        or ack_item.get("data")
        or ack_item.get("callback_payload")
        or callback.get("payload")
        or update_callback.get("payload")
        or ""
    )

    if payload and (not familiarization_id or not user_id):
        parts = str(payload).split(":")
        if len(parts) >= 3 and parts[0] in {"fam_ack", "familiarization_ack"}:
            familiarization_id = familiarization_id or parts[1]
            user_id = user_id or parts[2]

    return ack_id, familiarization_id, user_id, payload


def _poll_bot_queue(app):
    with app.app_context():
        try:
            from datetime import datetime
            from app.core.extensions import db
            from app.models import MaxBinding, User, Incident, Child
            from app.models_legacy import IncidentChild, IncidentNote
            from app.services.bot_client import get_client

            client = get_client()
            if not client._enabled():  # noqa: SLF001
                return  # env не настроен — тихо

            # ---------- 1. Привязки ----------
            try:
                pending = client.pending_binds()
            except Exception as e:
                app.logger.warning("bot pending_binds failed: %s", e)
                pending = []

            now = datetime.utcnow()
            for b in pending:
                code = b.get("code")
                chat_id = b.get("chat_id")
                full_name = b.get("full_name") or ""
                if not code or not chat_id:
                    continue
                if _bind_chat_blocked(chat_id):
                    # Слишком много неудачных попыток с этого MAX-чата — игнорируем,
                    # боту уже отвечали ok=False, у пользователя сообщение есть.
                    app.logger.warning("MAX bind blocked: chat_id=%s (brute-force lockout)", chat_id)
                    try:
                        client.bind_result(chat_id=chat_id, code=code, ok=False)
                    except Exception as e:
                        app.logger.warning("bind_result(blocked) failed: %s", e)
                    continue
                binding = (
                    MaxBinding.query
                    .filter_by(code=code, status="pending")
                    .filter(MaxBinding.expires_at > now)
                    .order_by(MaxBinding.id.desc())
                    .first()
                )
                if not binding:
                    _bind_record_fail(chat_id)
                    try:
                        client.bind_result(chat_id=chat_id, code=code, ok=False)
                    except Exception as e:
                        app.logger.warning("bind_result(ok=False) failed: %s", e)
                    continue

                # Снимаем прежние done-привязки того же портала-юзера и того же chat_id
                (
                    MaxBinding.query
                    .filter(MaxBinding.user_id == binding.user_id, MaxBinding.id != binding.id)
                    .filter(MaxBinding.status.in_(("done", "pending")))
                    .update({"status": "revoked"}, synchronize_session=False)
                )
                (
                    MaxBinding.query
                    .filter(MaxBinding.max_chat_id == chat_id, MaxBinding.id != binding.id)
                    .filter(MaxBinding.status == "done")
                    .update({"status": "revoked"}, synchronize_session=False)
                )
                binding.status = "done"
                binding.max_chat_id = chat_id
                binding.max_full_name = full_name
                binding.bound_at = now
                db.session.commit()

                user = User.query.get(binding.user_id)
                if not user:
                    try:
                        client.bind_result(chat_id=chat_id, code=code, ok=False)
                    except Exception as e:
                        app.logger.warning("bind_result no-user failed: %s", e)
                    continue
                payload = _bind_payload_for_user(user)
                try:
                    client.bind_result(chat_id=chat_id, code=code, ok=True, **payload)
                    _bind_reset(chat_id)
                    app.logger.info("MAX bind OK: user_id=%s chat_id=%s", user.id, chat_id)
                except Exception as e:
                    app.logger.warning("bind_result(ok=True) send failed: %s", e)

            # ---------- 2. Очередь инцидентов ----------
            try:
                items = client.pending()
            except Exception as e:
                app.logger.warning("bot pending failed: %s", e)
                items = []

            for q in items:
                qid = q.get("queue_id")
                chat_id = q.get("chat_id")
                payload = q.get("payload") or {}
                if not qid or not chat_id:
                    continue

                binding = (
                    MaxBinding.query
                    .filter_by(max_chat_id=chat_id, status="done")
                    .order_by(MaxBinding.id.desc())
                    .first()
                )
                if not binding:
                    try:
                        client.ack(qid, ok=False, error="binding_revoked")
                    except Exception as e:
                        app.logger.warning("ack(no-bind) failed: %s", e)
                    continue

                try:
                    occurred_at = datetime.fromisoformat(payload.get("occurred_at"))
                    if occurred_at.tzinfo is not None:
                        import pytz as _pytz
                        occurred_at = occurred_at.astimezone(_pytz.timezone("Europe/Moscow")).replace(tzinfo=None)
                except Exception:
                    occurred_at = now

                inc = Incident(
                    occurred_at=occurred_at,
                    category=payload.get("category") or "Другое",
                    description=(payload.get("description") or "")[:5000] or "(из MAX-бота)",
                    status="new",
                    author_id=binding.user_id,
                    created_at=now,
                )
                db.session.add(inc)
                db.session.flush()

                # Список учеников: поддерживаем новый формат student_ids (list)
                # и старый student_id (single) для обратной совместимости.
                sids = payload.get("student_ids")
                if not sids:
                    sid = payload.get("student_id")
                    sids = [sid] if sid else []
                seen = set()
                for raw in sids:
                    try:
                        cid = int(raw)
                    except (TypeError, ValueError):
                        continue
                    if cid in seen:
                        continue
                    seen.add(cid)
                    ch = Child.query.get(cid)
                    if ch:
                        db.session.add(IncidentChild(incident_id=inc.id, child_id=ch.id))

                # «Что уже сделано» — первая запись в журнале работы.
                initial_work = (payload.get("initial_work") or "").strip()
                if initial_work:
                    db.session.add(IncidentNote(
                        incident_id=inc.id,
                        author_id=binding.user_id,
                        text=initial_work[:5000],
                    ))

                attachments = payload.get("attachments") or []
                saved_atts = 0
                rejected_atts = 0
                if attachments:
                    from app.children import _save_max_attachment
                    note = IncidentNote(
                        incident_id=inc.id,
                        author_id=binding.user_id,
                        text=f"[Из MAX-бота] Вложения: {len(attachments)} шт.",
                    )
                    db.session.add(note)
                    db.session.flush()
                    for idx, a in enumerate(attachments):
                        try:
                            data, ct = client.fetch_attachment(qid, idx)
                        except Exception as e:
                            app.logger.warning("MAX fetch_attachment %s/%s failed: %s", qid, idx, e)
                            rejected_atts += 1
                            continue
                        try:
                            _save_max_attachment(note, a.get("filename") or f"attachment_{idx+1}", data, hint_mime=a.get("mime"))
                            saved_atts += 1
                        except Exception as e:
                            app.logger.warning("MAX save_attachment %s/%s rejected: %s", qid, idx, e)
                            rejected_atts += 1
                    note.text = f"[Из MAX-бота] Вложения: сохранено {saved_atts} из {len(attachments)}" + (
                        f" (отклонено: {rejected_atts})" if rejected_atts else ""
                    )

                db.session.commit()

                base = os.getenv("PORTAL_BASE_URL", "").rstrip("/")
                link = f"{base}/incidents/{inc.id}/edit" if base else None
                try:
                    client.ack(qid, ok=True, incident_id=inc.id, link=link)
                    app.logger.info("MAX queue ack: inc_id=%s qid=%s", inc.id, qid)
                except Exception as e:
                    app.logger.warning("ack(ok=True) failed: %s", e)

            # 3) Нажатия кнопки «Ознакомлен» в MAX по документам ознакомления
            try:
                fam_acks = client.pending_familiarization_acks()
            except Exception as e:
                app.logger.warning("MAX pending_familiarization_acks failed: %s", e)
                fam_acks = []

            for ack_item in fam_acks:
                ack_id, familiarization_id, user_id, payload = _parse_familiarization_ack_item(ack_item)

                try:
                    # Импорт внутри функции, чтобы не ломать запуск при старых миграциях/структуре.
                    try:
                        from app.models.familiarizations import FamiliarizationRecipient
                    except Exception:
                        try:
                            from app.models_legacy import FamiliarizationRecipient
                        except Exception:
                            from app.models import FamiliarizationRecipient

                    if not ack_id or not familiarization_id or not user_id:
                        raise ValueError(f"bad ack payload: {ack_item}")

                    rec = FamiliarizationRecipient.query.filter_by(
                        familiarization_id=int(familiarization_id),
                        user_id=int(user_id),
                    ).first()

                    if not rec:
                        raise LookupError(
                            f"FamiliarizationRecipient not found familiarization_id={familiarization_id} user_id={user_id}"
                        )

                    if not getattr(rec, "acknowledged_at", None):
                        rec.acknowledged_at = datetime.utcnow()
                        db.session.commit()

                    client.ack_familiarization_ack(ack_id=ack_id, ok=True)
                    app.logger.info(
                        "MAX familiarization ack processed: ack_id=%s familiarization_id=%s user_id=%s payload=%s",
                        ack_id,
                        familiarization_id,
                        user_id,
                        payload,
                    )

                except Exception as e:
                    db.session.rollback()
                    app.logger.exception("MAX familiarization ack failed: %s item=%s", e, ack_item)
                    try:
                        if ack_id:
                            client.ack_familiarization_ack(ack_id=ack_id, ok=False, error=str(e))
                    except Exception as ack_exc:
                        app.logger.warning("MAX familiarization ack error notify failed: %s", ack_exc)


            # 4) Нажатия кнопки «Выполнено» в MAX по задачам
            try:
                task_acks = client.pending_task_acks()
            except Exception as e:
                app.logger.warning("MAX pending_task_acks failed: %s", e)
                task_acks = []

            for ack_item in task_acks:
                ack_id = ack_item.get("ack_id")
                task_id = ack_item.get("task_id")
                user_id = ack_item.get("user_id")

                try:
                    from app.models.tasks import Task
                    try:
                        from app.models.tasks import TaskHistory
                    except Exception:
                        TaskHistory = None

                    if not ack_id or not task_id or not user_id:
                        raise ValueError(f"bad task ack payload: {ack_item}")

                    task = Task.query.get(int(task_id))
                    if not task:
                        raise LookupError(f"Task not found task_id={task_id}")

                    user_id_int = int(user_id)

                    # Проверяем, что кнопку нажал реальный адресат задачи:
                    # ответственный, контролёр или участник.
                    is_recipient = (
                        getattr(task, "responsible_user_id", None) == user_id_int
                        or getattr(task, "controller_user_id", None) == user_id_int
                        or any(getattr(participant, "user_id", None) == user_id_int for participant in (getattr(task, "participants", None) or []))
                    )
                    if not is_recipient:
                        raise PermissionError(f"user_id={user_id_int} is not task recipient task_id={task_id}")

                    old_status = getattr(task, "status", None)

                    if task.status != Task.STATUS_DONE:
                        task.status = Task.STATUS_DONE
                        task.completed_at = datetime.utcnow()
                        if hasattr(task, "updated_at"):
                            task.updated_at = datetime.utcnow()

                        if TaskHistory is not None:
                            try:
                                hist = TaskHistory(
                                    task_id=task.id,
                                    user_id=user_id_int,
                                    event_type="status",
                                    text=f"MAX-бот: задача отмечена как выполненная. Статус: {old_status} → {Task.STATUS_DONE}",
                                )
                                db.session.add(hist)
                            except TypeError:
                                # Если в этой версии у TaskHistory другие поля — не ломаем обработку.
                                pass

                        db.session.commit()
                    else:
                        db.session.commit()

                    client.ack_task_ack(ack_id=ack_id, ok=True)
                    app.logger.info(
                        "MAX task ack processed: ack_id=%s task_id=%s user_id=%s",
                        ack_id,
                        task_id,
                        user_id,
                    )

                except Exception as e:
                    db.session.rollback()
                    app.logger.exception("MAX task ack failed: %s item=%s", e, ack_item)
                    try:
                        if ack_id:
                            client.ack_task_ack(ack_id=ack_id, ok=False, error=str(e))
                    except Exception as ack_exc:
                        app.logger.warning("MAX task ack error notify failed: %s", ack_exc)


        except Exception as exc:  # noqa: BLE001
            app.logger.exception("poll_bot_queue FAILED: %s", exc)


def _should_start() -> bool:
    if os.getenv("KUBOK_SCHEDULER_DISABLED") == "1":
        return False
    if os.getenv("FLASK_DEBUG", "0") == "1" or os.getenv("FLASK_ENV") == "development":
        return os.getenv("WERKZEUG_RUN_MAIN") == "true"
    return True


def init_scheduler(app):
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    if not _should_start():
        app.logger.info("Scheduler skipped (debug reloader stub or KUBOK_SCHEDULER_DISABLED=1)")
        return None

    try:
        import pytz
        tz = pytz.timezone("Europe/Moscow")
    except Exception:
        tz = None

    sched = BackgroundScheduler(timezone=tz) if tz else BackgroundScheduler()
    sched.add_job(
        func=lambda: _kubok_weekly_refresh(app),
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=tz),
        id="kubok_weekly_refresh",
        name="Kubok weekly refresh (Mon 09:00 MSK)",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    sched.add_job(
        func=lambda: _page_visit_retention(app, days=30),
        trigger=CronTrigger(hour=4, minute=10, timezone=tz),
        id="page_visit_retention",
        name="PageVisit retention 30d (04:10 MSK daily)",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    if os.getenv("BOT_API_URL") and os.getenv("BOT_SHARED_SECRET"):
        sched.add_job(
            func=lambda: _poll_bot_queue(app),
            trigger=IntervalTrigger(seconds=15),
            id="poll_bot_queue",
            name="Poll MAX-bot binds + queue (15s)",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=10,
        )
        app.logger.info("Scheduler: poll_bot_queue (15s) registered")
    else:
        app.logger.info("Scheduler: poll_bot_queue skipped (BOT_API_URL/BOT_SHARED_SECRET не заданы)")

    sched.start()
    app.logger.info("Scheduler started: kubok_weekly_refresh + page_visit_retention")
    _scheduler = sched
    return sched
