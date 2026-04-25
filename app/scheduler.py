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

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

_scheduler: BackgroundScheduler | None = None


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
    sched.start()
    app.logger.info("Scheduler started: kubok_weekly_refresh + page_visit_retention")
    _scheduler = sched
    return sched
