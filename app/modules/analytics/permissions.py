from flask_login import current_user

def can_view_analytics():
    return getattr(current_user, "role", None) in {"ADMIN", "MANAGEMENT", "DEPARTMENT_HEAD", "METHODIST"}
