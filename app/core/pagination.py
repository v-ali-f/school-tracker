from __future__ import annotations

from math import ceil
from flask import request

from .constants import DEFAULT_PER_PAGE, PER_PAGE_OPTIONS
from .utils import parse_int


class SimplePagination:
    def __init__(self, *, page: int, per_page, total: int):
        self.page = max(1, page)
        self.per_page = per_page
        self.total = max(0, total)
        self.per_page_num = total or 1 if per_page == "all" else max(1, int(per_page))
        self.pages = max(1, ceil(self.total / self.per_page_num)) if self.total else 1
        self.page = min(self.page, self.pages)
        self.has_prev = self.page > 1
        self.has_next = self.page < self.pages
        self.prev_num = self.page - 1 if self.has_prev else 1
        self.next_num = self.page + 1 if self.has_next else self.pages
        self.first_item = 0 if self.total == 0 else (self.page - 1) * self.per_page_num + 1
        self.last_item = min(self.total, self.page * self.per_page_num)


def resolve_pagination(default_per_page: int = DEFAULT_PER_PAGE):
    page = parse_int(request.args.get("page"), 1) or 1
    raw = request.args.get("per_page", str(default_per_page))
    if raw == "all":
        per_page = "all"
    else:
        value = parse_int(raw, default_per_page) or default_per_page
        allowed = [x for x in PER_PAGE_OPTIONS if isinstance(x, int)]
        per_page = value if value in allowed else default_per_page
    return page, per_page


def paginate_list(items, *, page: int, per_page):
    total = len(items)
    pagination = SimplePagination(page=page, per_page=per_page, total=total)
    if per_page == "all":
        return items, pagination
    start = (pagination.page - 1) * pagination.per_page_num
    end = start + pagination.per_page_num
    return items[start:end], pagination
