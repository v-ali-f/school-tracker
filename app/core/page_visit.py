"""after_request handler — пишет каждый просмотр страницы в page_visit.

Skip:
- static / favicon / api endpoints (шум)
- ajax-поиск (бьётся на каждом нажатии клавиши)
- неавторизованные пользователи
- HEAD / OPTIONS
- редиректы 3xx без content (но 302 после POST оставляем — переход важен)
"""
from datetime import datetime
from urllib.parse import urlsplit

from flask import request
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app.core.extensions import db


SKIP_ENDPOINT_PREFIXES = ("static",)
SKIP_ENDPOINT_SUBSTR = (
    "search_ajax",
    "search_children_ajax",
    "_ajax",
    "by_class",
    "by_grade",
    "autocomplete",
    "_api",
    "ping",
    "healthcheck",
)
SKIP_PATH_PREFIXES = (
    "/static/",
    "/favicon",
    "/api/",
    "/children/search-ajax",
)
SKIP_METHODS = {"HEAD", "OPTIONS"}


def _should_skip(endpoint, path, method):
    if method in SKIP_METHODS:
        return True
    if not endpoint:
        return True
    for p in SKIP_ENDPOINT_PREFIXES:
        if endpoint == p or endpoint.startswith(p + "."):
            return True
    ep_low = endpoint.lower()
    for sub in SKIP_ENDPOINT_SUBSTR:
        if sub in ep_low:
            return True
    for p in SKIP_PATH_PREFIXES:
        if path.startswith(p):
            return True
    return False


def _resolve_referrer_endpoint(app, referrer_url):
    if not referrer_url:
        return None
    try:
        parts = urlsplit(referrer_url)
        ref_path = parts.path
        if not ref_path:
            return None
        adapter = app.url_map.bind(parts.netloc or "")
        endpoint, _args = adapter.match(ref_path, method="GET")
        return endpoint
    except Exception:
        return None


def init_page_visit_logger(app):
    @app.after_request
    def _log_page_visit(response):
        try:
            method = request.method
            endpoint = request.endpoint
            path = request.path or ""

            if _should_skip(endpoint, path, method):
                return response
            if 300 <= response.status_code < 400 and method == "GET":
                return response
            if not getattr(current_user, "is_authenticated", False):
                return response
            user_id = getattr(current_user, "id", None)
            if not user_id:
                return response

            from app.models import PageVisit

            ref_ep = _resolve_referrer_endpoint(app, request.referrer)
            full_path = request.full_path or path
            if full_path.endswith("?"):
                full_path = full_path[:-1]

            visit = PageVisit(
                user_id=user_id,
                endpoint=endpoint[:200],
                method=method[:10],
                path=full_path[:500],
                referrer_endpoint=(ref_ep[:200] if ref_ep else None),
                status_code=response.status_code,
                ts=datetime.utcnow(),
            )
            db.session.add(visit)
            db.session.commit()
        except SQLAlchemyError:
            try:
                db.session.rollback()
            except Exception:
                pass
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            app.logger.exception("page_visit log failed")
        return response
