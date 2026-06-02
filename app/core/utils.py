from __future__ import annotations

from urllib.parse import urlencode


def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def merge_query_args(args, **updates):
    """Return query string preserving current filters and applying updates."""
    data = dict(args)
    for key, value in updates.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return urlencode(data)
