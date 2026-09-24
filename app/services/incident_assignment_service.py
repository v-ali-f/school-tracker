"""Shared assignee lookup for every incident assignment surface."""

from app.core.extensions import db
from app.models_legacy import Role, User, UserRole


INCIDENT_ASSIGNEE_ROLE_CODES = (
    "ADMIN",
    "DEPUTY_DIRECTOR",
    "PSYCHOLOGIST",
    "SOCIAL_PEDAGOG",
    "METHODIST",
    "CLASS_TEACHER",
    "TEACHER",
)


def incident_assignee_candidates():
    """Return the same candidate list for cards, tables and edit forms.

    The portal still supports both the legacy ``user.role`` column and the
    normalized ``user_role`` relationship. A user assigned through either
    scheme must therefore appear in every incident assignee picker.
    """

    users_via_roles = (
        db.session.query(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(Role.code.in_(INCIDENT_ASSIGNEE_ROLE_CODES))
    )
    return (
        User.query
        .filter(
            User.role.in_(INCIDENT_ASSIGNEE_ROLE_CODES)
            | User.id.in_(users_via_roles)
        )
        .order_by(User.last_name, User.first_name, User.middle_name, User.username)
        .all()
    )
