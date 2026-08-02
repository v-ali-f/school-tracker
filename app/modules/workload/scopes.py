from dataclasses import dataclass

from app.models import DepartmentLeader, UserBuilding
from app.permissions import _user_role_codes

from .access import is_workload_global_editor


UNRESTRICTED_ROLES = frozenset({
    "ADMIN",
    "DIRECTOR",
    "DEPUTY_DIRECTOR",
    "METHODIST",
    "HR_SPECIALIST",
    "ECONOMIST",
    "AUDITOR",
})


@dataclass(frozen=True)
class WorkloadAccessScope:
    """Server-side boundary for all future workload queries."""

    unrestricted: bool = False
    organization_ids: frozenset[int] = frozenset()
    academic_year_ids: frozenset[int] = frozenset()
    building_ids: frozenset[int] = frozenset()
    department_ids: frozenset[int] = frozenset()
    own_employee_only: bool = False

    @property
    def is_empty(self) -> bool:
        return not (
            self.unrestricted
            or self.organization_ids
            or self.academic_year_ids
            or self.building_ids
            or self.department_ids
            or self.own_employee_only
        )


def resolve_workload_scope(user) -> WorkloadAccessScope:
    role_codes = _user_role_codes(user)
    if (
        role_codes.intersection(UNRESTRICTED_ROLES)
        or is_workload_global_editor(user)
    ):
        return WorkloadAccessScope(unrestricted=True)

    user_id = getattr(user, "id", None)
    if not user_id:
        return WorkloadAccessScope()

    if "DEPARTMENT_HEAD" in role_codes:
        try:
            links = DepartmentLeader.query.filter_by(user_id=user_id).all()
        except Exception:
            return WorkloadAccessScope()
        return WorkloadAccessScope(
            building_ids=frozenset(link.building_id for link in links if link.building_id),
            department_ids=frozenset(link.department_id for link in links if link.department_id),
        )

    if "TEACHER" in role_codes:
        try:
            building_links = UserBuilding.query.filter_by(user_id=user_id).all()
        except Exception:
            return WorkloadAccessScope()
        return WorkloadAccessScope(
            building_ids=frozenset(link.building_id for link in building_links if link.building_id),
            own_employee_only=True,
        )

    return WorkloadAccessScope()


__all__ = ["WorkloadAccessScope", "resolve_workload_scope"]
