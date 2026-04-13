from __future__ import annotations

from flask import request


def build_registry_url_filters(*, page=None, per_page=None):
    params = {}
    for key in ("grade", "class_id", "q", "status", "month", "year", "building_id", "mode"):
        value = request.args.get(key)
        if value not in (None, ""):
            params[key] = value
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    return params
