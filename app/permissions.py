from flask_login import current_user


# =========================================================
# ROLES
# =========================================================
ADMIN = "ADMIN"
TEACHER = "TEACHER"
CLASS_TEACHER = "CLASS_TEACHER"
PSYCHOLOGIST = "PSYCHOLOGIST"
SOCIAL_PEDAGOG = "SOCIAL_PEDAGOG"
METHODIST = "METHODIST"


# =========================================================
# PERMISSIONS MATRIX
# =========================================================
PERMISSIONS = {
    "dashboard_view": {
        ADMIN, TEACHER, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG, METHODIST
    },

    "contingent_view": {
        ADMIN, TEACHER, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG, METHODIST
    },

    "children_registry_view": {
        ADMIN, TEACHER, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG, METHODIST
    },

    "child_card_view_basic": {
        ADMIN, TEACHER, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG, METHODIST
    },

    "child_card_view_full": {
        ADMIN, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG
    },

    "social_passport_view": {
        ADMIN, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG
    },

    "social_passport_edit": {
        ADMIN, CLASS_TEACHER, SOCIAL_PEDAGOG
    },

    "comment_add": {
        ADMIN, TEACHER, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG, METHODIST
    },

    "incident_add": {
        ADMIN, TEACHER, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG
    },

    "incident_registry_view": {
        ADMIN
    },

    "incident_dashboard_view": {
        ADMIN
    },

    "low_results_view": {
        ADMIN, TEACHER, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG, METHODIST
    },

    "low_results_edit": {
        ADMIN, TEACHER, CLASS_TEACHER, METHODIST
    },

    "debt_view": {
        ADMIN, TEACHER, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG, METHODIST
    },

    "debt_edit": {
        ADMIN, TEACHER, CLASS_TEACHER
    },

    "documents_view": {
        ADMIN, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG
    },

    "documents_upload": {
        ADMIN, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG
    },

    "documents_delete": {
        ADMIN
    },

    "child_create": {
        ADMIN
    },

    "child_edit_profile": {
        ADMIN
    },

    "child_delete": {
        ADMIN
    },

    "child_transfer": {
        ADMIN
    },

    "child_expel": {
        ADMIN
    },

    "registry_ovz_view": {
        ADMIN, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG
    },

    "registry_vshu_view": {
        ADMIN, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG
    },

    "registry_kdn_view": {
        ADMIN, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG
    },

    "registry_az_view": {
        ADMIN, TEACHER, CLASS_TEACHER, METHODIST
    },

    "registry_enrolled_view": {
        ADMIN, CLASS_TEACHER, PSYCHOLOGIST, SOCIAL_PEDAGOG
    },

    "registry_expelled_view": {
        ADMIN, PSYCHOLOGIST, SOCIAL_PEDAGOG
    },

    "social_passport_registry_view": {
        ADMIN, METHODIST, CLASS_TEACHER
    },

    "social_passport_dashboard_view": {
        ADMIN, METHODIST
    },

    "classes_manage": {
        ADMIN
    },

    "subjects_manage": {
        ADMIN
    },

    "buildings_manage": {
        ADMIN
    },

    "academic_year_manage": {
        ADMIN
    },

    "children_import": {
        ADMIN
    },

    "parents_import": {
        ADMIN
    },

    "subjects_import": {
        ADMIN
    },

    "control_works_view": {
        ADMIN, TEACHER, CLASS_TEACHER, METHODIST
    },

    "control_works_edit": {
        ADMIN, METHODIST
    },


    "olympiad_view": {
        ADMIN, TEACHER, CLASS_TEACHER, METHODIST
    },

    "olympiad_import": {
        ADMIN, METHODIST
    },

    "olympiad_edit": {
        ADMIN, METHODIST
    },

    "olympiad_dashboard_view": {
        ADMIN, TEACHER, CLASS_TEACHER, METHODIST
    },

    "olympiad_settings_manage": {
        ADMIN, METHODIST
    },

    "olympiad_department_summary_view": {
        ADMIN, METHODIST, TEACHER, CLASS_TEACHER
    },
}


# =========================================================
# BASIC ROLE HELPERS
# =========================================================
def _user_role_codes(user=None) -> set:
    user = user or current_user

    if not user or not getattr(user, "is_authenticated", False):
        return set()

    # Новая схема: user.roles -> список объектов с code
    if hasattr(user, "roles") and user.roles:
        codes = set()
        for r in user.roles:
            code = getattr(r, "code", None)
            if code:
                codes.add(str(code).upper())
        if codes:
            return codes

    # Временная совместимость со старой схемой: user.role = "ADMIN"
    single_role = getattr(user, "role", None)
    if single_role:
        return {str(single_role).upper()}

    return set()


def has_role(role_code: str, user=None) -> bool:
    return str(role_code).upper() in _user_role_codes(user)


def has_any_role(*role_codes, user=None) -> bool:
    user_codes = _user_role_codes(user)
    wanted = {str(x).upper() for x in role_codes}
    return bool(user_codes.intersection(wanted))


def has_all_roles(*role_codes, user=None) -> bool:
    user_codes = _user_role_codes(user)
    wanted = {str(x).upper() for x in role_codes}
    return wanted.issubset(user_codes)


def is_admin(user=None) -> bool:
    return has_role(ADMIN, user=user)


# =========================================================
# PERMISSION CHECK
# =========================================================
def has_permission(permission_code: str, user=None) -> bool:
    allowed_roles = PERMISSIONS.get(permission_code, set())
    user_codes = _user_role_codes(user)
    return bool(allowed_roles.intersection(user_codes))


# =========================================================
# CHILD / CLASS HELPERS
# =========================================================
def is_class_teacher_of_child(child, user=None) -> bool:
    user = user or current_user

    if not user or not getattr(user, "is_authenticated", False):
        return False

    if not child:
        return False

    current_class = getattr(child, "current_class", None)
    if not current_class:
        return False

    return getattr(current_class, "teacher_user_id", None) == getattr(user, "id", None)


def is_class_teacher_of_class(school_class, user=None) -> bool:
    user = user or current_user

    if not user or not getattr(user, "is_authenticated", False):
        return False

    if not school_class:
        return False

    return getattr(school_class, "teacher_user_id", None) == getattr(user, "id", None)


# =========================================================
# CHILD CARD RIGHTS
# =========================================================
def can_view_child_basic(child, user=None) -> bool:
    return has_permission("child_card_view_basic", user=user)


def can_view_child_full(child, user=None) -> bool:
    user = user or current_user

    if is_admin(user):
        return True

    if has_role(PSYCHOLOGIST, user=user):
        return True

    if has_role(SOCIAL_PEDAGOG, user=user):
        return True

    if has_role(CLASS_TEACHER, user=user) and is_class_teacher_of_child(child, user=user):
        return True

    return False


def can_view_social_passport(child, user=None) -> bool:
    user = user or current_user

    if is_admin(user):
        return True

    if has_role(CLASS_TEACHER, user=user) and is_class_teacher_of_child(child, user=user):
        return True

    if has_role(PSYCHOLOGIST, user=user):
        return True

    if has_role(SOCIAL_PEDAGOG, user=user):
        return True

    if has_role(METHODIST, user=user):
        return True

    return False


def can_edit_social_passport(child, user=None) -> bool:
    user = user or current_user

    if is_admin(user):
        return True

    if has_role(CLASS_TEACHER, user=user) and is_class_teacher_of_child(child, user=user):
        return True

    if has_role(PSYCHOLOGIST, user=user):
        return True

    if has_role(SOCIAL_PEDAGOG, user=user):
        return True

    return False


def can_edit_child_profile(child, user=None) -> bool:
    return is_admin(user)


def can_view_low_results(child, user=None) -> bool:
    return has_permission("low_results_view", user=user)

def can_edit_ovz(child, user=None) -> bool:
    return is_admin(user)


def can_edit_disabled(child, user=None) -> bool:
    return is_admin(user)


def can_edit_vshu(child, user=None) -> bool:
    return is_admin(user)

def can_edit_low_results(child, user=None) -> bool:
    user = user or current_user

    if is_admin(user):
        return True

    if has_role(TEACHER, user=user):
        return True

    if has_role(METHODIST, user=user):
        return True

    if has_role(CLASS_TEACHER, user=user) and is_class_teacher_of_child(child, user=user):
        return True

    return False


def can_view_debts(child, user=None) -> bool:
    return has_permission("debt_view", user=user)


def can_edit_debts(child, user=None) -> bool:
    user = user or current_user

    if is_admin(user):
        return True

    if has_role(TEACHER, user=user):
        return True

    if has_role(CLASS_TEACHER, user=user) and is_class_teacher_of_child(child, user=user):
        return True

    return False


def can_view_documents(child, user=None) -> bool:
    user = user or current_user

    if is_admin(user):
        return True

    if has_role(PSYCHOLOGIST, user=user):
        return True

    if has_role(SOCIAL_PEDAGOG, user=user):
        return True

    if has_role(CLASS_TEACHER, user=user) and is_class_teacher_of_child(child, user=user):
        return True

    return False

def can_upload_documents(child, user=None) -> bool:
    user = user or current_user

    if is_admin(user):
        return True

    if has_role(TEACHER, user=user):
        return True

    if has_role(PSYCHOLOGIST, user=user):
        return True

    if has_role(SOCIAL_PEDAGOG, user=user):
        return True

    if has_role(CLASS_TEACHER, user=user) and is_class_teacher_of_child(child, user=user):
        return True

    return False

def can_edit_ovz(child, user=None) -> bool:
    return is_admin(user)


def can_edit_disabled(child, user=None) -> bool:
    return is_admin(user)


def can_edit_vshu(child, user=None) -> bool:
    return is_admin(user)

def can_add_comment(child=None, user=None) -> bool:
    return has_permission("comment_add", user=user)


def can_add_incident(user=None) -> bool:
    return has_permission("incident_add", user=user)


# =========================================================
# REGISTRIES / MENUS
# =========================================================
def can_view_registry_ovz(user=None) -> bool:
    return has_permission("registry_ovz_view", user=user)


def can_view_registry_vshu(user=None) -> bool:
    return has_permission("registry_vshu_view", user=user)


def can_view_registry_kdn(user=None) -> bool:
    return has_permission("registry_kdn_view", user=user)


def can_view_registry_az(user=None) -> bool:
    return has_permission("registry_az_view", user=user)


def can_view_registry_enrolled(user=None) -> bool:
    return has_permission("registry_enrolled_view", user=user)


def can_view_registry_expelled(user=None) -> bool:
    return has_permission("registry_expelled_view", user=user)


def can_view_social_passport_registry(user=None) -> bool:
    return has_permission("social_passport_registry_view", user=user)


def can_view_social_passport_dashboard(user=None) -> bool:
    return has_permission("social_passport_dashboard_view", user=user)


def can_manage_classes(user=None) -> bool:
    return has_permission("classes_manage", user=user)


def can_manage_subjects(user=None) -> bool:
    return has_permission("subjects_manage", user=user)


def can_manage_buildings(user=None) -> bool:
    return has_permission("buildings_manage", user=user)


def can_manage_academic_year(user=None) -> bool:
    return has_permission("academic_year_manage", user=user)


def can_import_children(user=None) -> bool:
    return has_permission("children_import", user=user)


def can_import_parents(user=None) -> bool:
    return has_permission("parents_import", user=user)


def can_import_subjects(user=None) -> bool:
    return has_permission("subjects_import", user=user)


# =========================================================
# LIST FILTERING
# =========================================================
def should_limit_children_to_own_class(user=None) -> bool:
    user = user or current_user

    if is_admin(user):
        return False

    if has_role(PSYCHOLOGIST, user=user):
        return False

    if has_role(SOCIAL_PEDAGOG, user=user):
        return False

    if has_role(CLASS_TEACHER, user=user):
        return True

    return False


# =========================================================
# TEMPLATE FLAGS FOR CHILD CARD
# =========================================================
def build_child_card_flags(child, user=None) -> dict:
    user = user or current_user

    return {
        "can_view_basic": can_view_child_basic(child, user=user),
        "can_view_full": can_view_child_full(child, user=user),
        "can_view_social": can_view_social_passport(child, user=user),
        "can_edit_social": can_edit_social_passport(child, user=user),
        "can_edit_profile": can_edit_child_profile(child, user=user),

        "can_edit_ovz": can_edit_ovz(child, user=user),
        "can_edit_disabled": can_edit_disabled(child, user=user),
        "can_edit_vshu": can_edit_vshu(child, user=user),

        "can_view_low": can_view_low_results(child, user=user),
        "can_edit_low": can_edit_low_results(child, user=user),

        "can_view_debts": can_view_debts(child, user=user),
        "can_edit_debts": can_edit_debts(child, user=user),

        "can_view_documents": can_view_documents(child, user=user),
        "can_upload_documents": can_upload_documents(child, user=user),

        "can_add_comment": can_add_comment(child, user=user),
        "can_add_incident": can_add_incident(user=user),

        "is_admin": is_admin(user=user),
        "is_teacher": has_role(TEACHER, user=user),
        "is_class_teacher": has_role(CLASS_TEACHER, user=user),
        "is_psychologist": has_role(PSYCHOLOGIST, user=user),
        "is_social_pedagog": has_role(SOCIAL_PEDAGOG, user=user),
        "is_methodist": has_role(METHODIST, user=user),
    }


# =========================================================
# TEMPLATE FLAGS FOR MENU
# =========================================================
def build_menu_flags(user=None) -> dict:
    user = user or current_user

    return {
        "can_dashboard_view": has_permission("dashboard_view", user=user),
        "can_contingent_view": has_permission("contingent_view", user=user),
        "can_children_registry_view": has_permission("children_registry_view", user=user),
        "can_incident_add": has_permission("incident_add", user=user),
        "can_incident_registry_view": has_permission("incident_registry_view", user=user),
        "can_incident_dashboard_view": has_permission("incident_dashboard_view", user=user),
        "is_admin": is_admin(user=user),
        "can_social_passport_registry_view": can_view_social_passport_registry(user=user),
        "can_social_passport_dashboard_view": can_view_social_passport_dashboard(user=user),
        "can_registry_ovz_view": can_view_registry_ovz(user=user),
        "can_registry_vshu_view": can_view_registry_vshu(user=user),
        "can_registry_kdn_view": can_view_registry_kdn(user=user),
        "can_registry_az_view": can_view_registry_az(user=user),
        "can_registry_enrolled_view": can_view_registry_enrolled(user=user),
        "can_registry_expelled_view": can_view_registry_expelled(user=user),
        "can_manage_classes": can_manage_classes(user=user),
        "can_manage_subjects": can_manage_subjects(user=user),
        "can_manage_buildings": can_manage_buildings(user=user),
        "can_manage_academic_year": can_manage_academic_year(user=user),
        "can_import_children": can_import_children(user=user),
        "can_import_parents": can_import_parents(user=user),
        "can_import_subjects": can_import_subjects(user=user),
        "can_control_works_view": has_permission("control_works_view", user=user),
        "can_control_works_edit": has_permission("control_works_edit", user=user),
        "can_olympiad_view": has_permission("olympiad_view", user=user),
        "can_olympiad_import": has_permission("olympiad_import", user=user),
        "can_olympiad_dashboard_view": has_permission("olympiad_dashboard_view", user=user),
        "can_olympiad_settings_manage": has_permission("olympiad_settings_manage", user=user),
    }