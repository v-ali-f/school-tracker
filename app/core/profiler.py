"""
Request profiler middleware.
Logs time for every request; highlights slow ones (>500ms).
Also counts SQL queries per request via SQLAlchemy event listeners.
"""
import time
import logging

from flask import g, request
from sqlalchemy import event

logger = logging.getLogger("profiler")

SLOW_THRESHOLD = 0.5  # seconds


def init_profiler(app, db_engine):
    """Register before/after request hooks and SQLAlchemy query counter."""

    @app.before_request
    def _start_timer():
        g._req_start = time.perf_counter()
        g._sql_count = 0

    @app.after_request
    def _log_request(response):
        elapsed = time.perf_counter() - getattr(g, "_req_start", time.perf_counter())
        sql_count = getattr(g, "_sql_count", 0)
        status = response.status_code

        # skip static files
        if request.path.startswith("/static"):
            return response

        tag = "SLOW" if elapsed > SLOW_THRESHOLD else "OK"
        logger.info(
            "[%s] %s %s — %.0fms, %d SQL, status %d",
            tag,
            request.method,
            request.path,
            elapsed * 1000,
            sql_count,
            status,
        )
        return response

    @event.listens_for(db_engine, "before_cursor_execute")
    def _count_query(conn, cursor, statement, parameters, context, executemany):
        try:
            if hasattr(g, "_sql_count"):
                g._sql_count += 1
        except RuntimeError:
            pass  # outside request context
