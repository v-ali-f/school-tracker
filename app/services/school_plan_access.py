from app.models import SchoolPlanEditorAccess


PROTECTED_PLAN_ROLES = {'DIRECTOR'}
IMPLICIT_PLAN_EDITOR_ROLES = {'ADMIN', 'DEPUTY_DIRECTOR', 'METHODIST'}
EDITOR_ADMIN_ROLES = {'ADMIN', 'DEPUTY_DIRECTOR'}


def _role_codes(user):
    return set(getattr(user, 'role_codes', []) or [])


def has_protected_plan_access(user):
    return bool(_role_codes(user).intersection(PROTECTED_PLAN_ROLES))


def has_implicit_plan_access(user):
    return bool(_role_codes(user).intersection(IMPLICIT_PLAN_EDITOR_ROLES))


def plan_access_record(user):
    user_id = getattr(user, 'id', None)
    if not user_id:
        return None
    return SchoolPlanEditorAccess.query.filter_by(user_id=user_id).first()


def can_fill_school_plan(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    if has_protected_plan_access(user):
        return True
    access = plan_access_record(user)
    if access is not None:
        return bool(access.is_enabled)
    return has_implicit_plan_access(user)


def can_manage_school_plan_editors(user):
    if has_protected_plan_access(user):
        return True
    return bool(_role_codes(user).intersection(EDITOR_ADMIN_ROLES)) and can_fill_school_plan(user)
