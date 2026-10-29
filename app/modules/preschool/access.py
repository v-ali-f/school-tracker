"""Preschool access rules shared by routes and navigation."""

from flask_login import current_user
from sqlalchemy import select

from app.models_legacy import Building

from .models import PreschoolBuildingStaff, PreschoolGroup, PreschoolGroupAssignment, PreschoolResponsibility


CONTINGENT_MANAGER = "CONTINGENT_MANAGER"
CHIEF_EDUCATOR = "CHIEF_EDUCATOR"
SENIOR_EDUCATOR = "SENIOR_EDUCATOR"
RESPONSIBILITY_KINDS = (CONTINGENT_MANAGER, SENIOR_EDUCATOR, CHIEF_EDUCATOR)

MANAGEMENT_ROLES = {"ADMIN", "DIRECTOR"}
PRESCHOOL_ROLES = {"SENIOR_EDUCATOR", "EDUCATOR", "ASSISTANT_EDUCATOR"}


def role_codes(user=None):
    user = user or current_user
    return {str(code).upper() for code in getattr(user, "role_codes", [])}


def can_assign_responsibilities(user=None):
    user = user or current_user
    return bool(getattr(user, "is_authenticated", False) and role_codes(user) & MANAGEMENT_ROLES)


def responsibility_user_id(kind):
    row = PreschoolResponsibility.query.filter_by(kind=kind).first()
    return row.user_id if row else None


def is_responsible(user, kind):
    return bool(
        getattr(user, "id", None)
        and PreschoolResponsibility.query.filter_by(kind=kind, user_id=user.id).first()
    )


def can_manage_contingent(user=None):
    user = user or current_user
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(role_codes(user) & (MANAGEMENT_ROLES | {"SENIOR_EDUCATOR"})) or is_responsible(user, CONTINGENT_MANAGER)


def can_view_all_contingent(user=None):
    user = user or current_user
    return can_manage_contingent(user) or bool(
        getattr(user, "is_authenticated", False)
        and "DEPUTY_DIRECTOR" in role_codes(user)
    )


def assigned_group_ids(user=None):
    user = user or current_user
    if not getattr(user, "id", None):
        return set()
    positions = role_codes(user) & {"EDUCATOR", "ASSISTANT_EDUCATOR"}
    if not positions:
        return set()
    memberships = {
        (building_id, position)
        for building_id, position in PreschoolBuildingStaff.query.with_entities(
            PreschoolBuildingStaff.building_id, PreschoolBuildingStaff.position,
        ).filter(
            PreschoolBuildingStaff.user_id == user.id,
            PreschoolBuildingStaff.building_id.in_(select(Building.id).where(Building.is_preschool.is_(True))),
            PreschoolBuildingStaff.position.in_(positions),
            PreschoolBuildingStaff.is_active.is_(True),
        ).all()
    }
    return {
        group_id
        for group_id, building_id, position in PreschoolGroupAssignment.query.join(PreschoolGroup).with_entities(
            PreschoolGroupAssignment.group_id,
            PreschoolGroupAssignment.building_id,
            PreschoolGroupAssignment.position,
        ).filter(
            PreschoolGroupAssignment.user_id == user.id,
            PreschoolGroupAssignment.is_active.is_(True),
            PreschoolGroupAssignment.position.in_(positions),
            PreschoolGroup.is_archived.is_(False),
        ).all()
        if building_id is None or (building_id, position) in memberships
    }


def managed_building_ids(user=None):
    user = user or current_user
    if not getattr(user, "is_authenticated", False):
        return set()
    if role_codes(user) & MANAGEMENT_ROLES or is_responsible(user, CHIEF_EDUCATOR):
        return {building_id for building_id, in Building.query.with_entities(Building.id).filter_by(is_preschool=True).all()}
    if "SENIOR_EDUCATOR" not in role_codes(user):
        return set()
    return {
        building_id for building_id, in PreschoolBuildingStaff.query.with_entities(PreschoolBuildingStaff.building_id).filter(
            PreschoolBuildingStaff.user_id == user.id,
            PreschoolBuildingStaff.position == "SENIOR_EDUCATOR",
            PreschoolBuildingStaff.building_id.in_(select(Building.id).where(Building.is_preschool.is_(True))),
            PreschoolBuildingStaff.is_active.is_(True),
        ).all()
    }


def assigned_building_ids(user=None):
    user = user or current_user
    if not getattr(user, "id", None):
        return set()
    return {
        building_id for building_id, in PreschoolBuildingStaff.query.with_entities(PreschoolBuildingStaff.building_id).filter(
            PreschoolBuildingStaff.user_id == user.id,
            PreschoolBuildingStaff.building_id.in_(select(Building.id).where(Building.is_preschool.is_(True))),
            PreschoolBuildingStaff.is_active.is_(True),
        ).all()
    }


def can_manage_staff_in_building(building_id, user=None):
    return building_id is not None and building_id in managed_building_ids(user)


def manageable_group_building_ids(user=None):
    user = user or current_user
    if is_responsible(user, CONTINGENT_MANAGER):
        return {building_id for building_id, in Building.query.with_entities(Building.id).filter_by(is_preschool=True).all()}
    return managed_building_ids(user)


def can_manage_group_in_building(building_id, user=None):
    return building_id is not None and building_id in manageable_group_building_ids(user)


def can_view_own_group(user=None):
    user = user or current_user
    return bool(role_codes(user) & {"EDUCATOR", "ASSISTANT_EDUCATOR"} or assigned_group_ids(user))


def can_open_preschool(user=None):
    user = user or current_user
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(
        can_view_all_contingent(user)
        or role_codes(user) & ({"DEPUTY_DIRECTOR"} | PRESCHOOL_ROLES)
        or assigned_building_ids(user)
        or assigned_group_ids(user)
    )


def can_view_child(child, user=None):
    user = user or current_user
    return bool(
        can_view_all_contingent(user)
        or child.group_id in assigned_group_ids(user)
    )
