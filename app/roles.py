from functools import wraps
from flask import abort
from flask_login import current_user, login_required

def require_roles(*roles):
    """Пропускает только пользователей с указанными ролями."""
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            role = getattr(current_user, "role", None)
            if role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator
