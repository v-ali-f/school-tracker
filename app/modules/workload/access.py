from flask import abort

from app.core.feature_flags import (
    WORKLOAD_MODULE,
    WORKLOAD_WRITE,
    is_feature_enabled,
)
from app.models import WorkloadEditorAccess
from app.models.role_access import RoleModuleAccess
from app.permissions import _user_role_codes, has_permission


WORKLOAD_MODULE_CODE = "workload"
WORKLOAD_DEFAULT_ROLES = frozenset({
    "ADMIN",
    "DIRECTOR",
    "DEPUTY_DIRECTOR",
    "METHODIST",
    "DEPARTMENT_HEAD",
    "HR_SPECIALIST",
    "ECONOMIST",
    "AUDITOR",
    "TEACHER",
})
WORKLOAD_DEFAULT_EDITOR_ROLES = frozenset({
    "ADMIN",
    "DIRECTOR",
    "DEPUTY_DIRECTOR",
})
WORKLOAD_WRITE_PERMISSIONS = frozenset({
    "workload.plan.update",
    "workload.plan_bindings.update",
    "workload.groups.update",
    "workload.assignments.update",
    "workload.calculate",
    "workload.documents.generate",
})


def _assigned_role_codes(user) -> set[str]:
    roles = getattr(user, "roles", None)
    if roles:
        codes = {
            str(role.code).upper()
            for role in roles
            if getattr(role, "code", None)
        }
        if codes:
            return codes

    role_code = getattr(user, "role", None)
    return {str(role_code).upper()} if role_code else set()


def _module_is_visible(user) -> bool:
    assigned_codes = _assigned_role_codes(user)
    if not assigned_codes:
        return False

    try:
        rows = RoleModuleAccess.query.filter(
            RoleModuleAccess.role_code.in_(assigned_codes),
            RoleModuleAccess.module_code == WORKLOAD_MODULE_CODE,
            RoleModuleAccess.is_active.is_(True),
        ).all()
    except Exception:
        return False
    rows_by_role = {row.role_code.upper(): row for row in rows}

    for role_code in assigned_codes:
        row = rows_by_role.get(role_code)
        if row is not None:
            if row.is_visible and row.is_enabled and row.access_level != "hidden":
                return True
            continue
        if role_code in WORKLOAD_DEFAULT_ROLES:
            return True
    return False


def _has_workload_editor_assignment(user) -> bool:
    user_id = getattr(user, "id", None)
    if not user_id:
        return False
    try:
        return WorkloadEditorAccess.query.filter_by(
            user_id=user_id,
            is_active=True,
        ).first() is not None
    except Exception:
        return False


def can_access_workload_module(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _has_workload_editor_assignment(user):
        return True
    if not (
        has_permission("workload.read", user=user)
        or has_permission("workload.self.read", user=user)
    ):
        return False
    return _module_is_visible(user)


def is_workload_global_editor(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _assigned_role_codes(user).intersection(WORKLOAD_DEFAULT_EDITOR_ROLES):
        return True
    return _has_workload_editor_assignment(user)


def can_use_workload_permission(permission_code: str, user) -> bool:
    if not can_access_workload_module(user):
        return False
    if permission_code in WORKLOAD_WRITE_PERMISSIONS:
        if is_workload_global_editor(user):
            return True
        if permission_code == "workload.assignments.update":
            return "DEPARTMENT_HEAD" in _assigned_role_codes(user)
        return False
    return has_permission(permission_code, user=user)


def require_workload_module() -> None:
    if not is_feature_enabled(WORKLOAD_MODULE):
        abort(404)


def require_workload_write() -> None:
    require_workload_module()
    if not is_feature_enabled(WORKLOAD_WRITE):
        abort(404)


__all__ = [
    "WORKLOAD_MODULE_CODE",
    "WORKLOAD_DEFAULT_ROLES",
    "WORKLOAD_DEFAULT_EDITOR_ROLES",
    "can_access_workload_module",
    "can_use_workload_permission",
    "is_workload_global_editor",
    "require_workload_module",
    "require_workload_write",
]
