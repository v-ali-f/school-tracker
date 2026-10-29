"""Keep roles granted by preschool appointments in the shared user registry."""

from app.core.extensions import db
from app.models_legacy import Role

from .models import PreschoolBuildingStaff, PreschoolResponsibility, PreschoolRoleGrant


def ensure_preschool_role(user, role_code):
    if role_code in user.role_codes:
        return

    # User.role is the legacy primary role. Once the first secondary role is
    # added, User.role_codes reads user_role, so retain the primary there too.
    if not user.roles and user.role:
        primary = Role.query.filter_by(code=user.role).first()
        if primary is None:
            primary = Role(code=user.role, name=user.role)
            db.session.add(primary)
            db.session.flush()
        user.roles.append(primary)

    role = Role.query.filter_by(code=role_code).first()
    if role is None:
        role = Role(code=role_code, name=role_code)
        db.session.add(role)
        db.session.flush()
    if role not in user.roles:
        user.roles.append(role)
    if not PreschoolRoleGrant.query.filter_by(user_id=user.id, role_code=role_code).first():
        db.session.add(PreschoolRoleGrant(user_id=user.id, role_code=role_code))


def release_preschool_role_if_unused(user, role_code):
    grant = PreschoolRoleGrant.query.filter_by(user_id=user.id, role_code=role_code).first()
    if grant is None:
        return
    if PreschoolBuildingStaff.query.filter_by(
        user_id=user.id, position=role_code, is_active=True,
    ).first():
        return
    if role_code == "SENIOR_EDUCATOR" and PreschoolResponsibility.query.filter(
        PreschoolResponsibility.user_id == user.id,
        PreschoolResponsibility.kind.in_(("SENIOR_EDUCATOR", "CHIEF_EDUCATOR")),
    ).first():
        return
    if user.role != role_code:
        user.roles = [role for role in user.roles if role.code != role_code]
    db.session.delete(grant)
