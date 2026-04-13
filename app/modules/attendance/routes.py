"""v71 modular attendance routes.

The legacy implementation still lives in app.attendance, but the blueprint is
now imported through this module so the package structure stays stable for
future refactors.
"""
from app.attendance import attendance_bp
from . import api  # noqa: F401
