from functools import wraps
from flask import abort
from flask_login import login_required

from app.permissions import has_any_role


def require_roles(*roles):
    """Пропускает только пользователей с указанными ролями.

    Использует has_any_role() из permissions.py — корректно работает
    как со старой схемой (user.role), так и с новой (user_role m2m).
    """
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not has_any_role(*roles):
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator
