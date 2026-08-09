from dataclasses import dataclass
from datetime import date

from app.models import (
    Department,
    TeacherAttestation,
    TeacherLoad,
    TeacherMckoResult,
    User,
    WorkloadAssignment,
)
from app.services.teacher_mcko_service import MckoResultView, mcko_result_view


MISSING_STATUS = "MISSING"


@dataclass(frozen=True)
class TeacherMckoRegistryRow:
    teacher: User
    departments: tuple[Department, ...]
    result: MckoResultView | None

    @property
    def status(self):
        return self.result.status if self.result else MISSING_STATUS

    @property
    def status_label(self):
        return self.result.status_label if self.result else "Диагностика отсутствует"

    @property
    def department_names(self):
        return ", ".join(item.name for item in self.departments) or "Без кафедры"

    @property
    def entered_by(self):
        if not self.result:
            return "—"
        user = self.result.record.created_by_user
        return (user.fio or user.username) if user else "Не указано"


def teacher_professional_roster():
    """Return active teaching staff and their workload-derived departments."""
    teacher_ids = set()
    department_ids_by_teacher = {}

    for user in User.query.filter_by(is_active_user=True, employment_status="ACTIVE").all():
        if set(user.role_codes).intersection({"TEACHER", "CLASS_TEACHER", "DEPARTMENT_HEAD"}):
            teacher_ids.add(user.id)

    assignments = WorkloadAssignment.query.with_entities(
        WorkloadAssignment.employee_user_id,
        WorkloadAssignment.department_id,
    ).filter(
        WorkloadAssignment.employee_user_id.isnot(None),
        WorkloadAssignment.status != "CANCELLED",
    ).all()
    for item in assignments:
        teacher_ids.add(item.employee_user_id)
        if item.department_id:
            department_ids_by_teacher.setdefault(item.employee_user_id, set()).add(item.department_id)

    legacy_loads = TeacherLoad.query.with_entities(
        TeacherLoad.teacher_id,
        TeacherLoad.department_id,
    ).filter_by(is_archived=False).distinct().all()
    for item in legacy_loads:
        teacher_ids.add(item.teacher_id)
        if item.department_id:
            department_ids_by_teacher.setdefault(item.teacher_id, set()).add(item.department_id)

    for teacher_id, in TeacherMckoResult.query.with_entities(TeacherMckoResult.teacher_id).distinct():
        teacher_ids.add(teacher_id)
    for teacher_id, in TeacherAttestation.query.with_entities(TeacherAttestation.teacher_id).distinct():
        teacher_ids.add(teacher_id)

    active_users = {
        item.id: item
        for item in User.query.filter(
            User.id.in_(teacher_ids or {-1}),
            User.is_active_user.is_(True),
            User.employment_status == "ACTIVE",
        ).all()
    }
    department_ids = {
        department_id
        for values in department_ids_by_teacher.values()
        for department_id in values
    }
    departments = {
        item.id: item
        for item in Department.query.filter(Department.id.in_(department_ids or {-1})).all()
    }
    return active_users, department_ids_by_teacher, departments


def teacher_mcko_registry_rows(
    *,
    search=None,
    department_id=None,
    activity_id=None,
    status=None,
    expiry=None,
    allowed_department_ids=None,
    as_of=None,
):
    as_of = as_of or date.today()
    users, department_ids_by_teacher, departments = teacher_professional_roster()
    allowed_department_ids = (
        {int(value) for value in allowed_department_ids}
        if allowed_department_ids is not None
        else None
    )
    if allowed_department_ids is not None:
        users = {
            teacher_id: teacher
            for teacher_id, teacher in users.items()
            if department_ids_by_teacher.get(teacher_id, set()).intersection(allowed_department_ids)
        }

    records_by_teacher = {}
    records = TeacherMckoResult.query.filter(
        TeacherMckoResult.teacher_id.in_(users.keys() or {-1}),
        TeacherMckoResult.is_archived.is_(False),
    ).order_by(
        TeacherMckoResult.teacher_id.asc(),
        TeacherMckoResult.passed_at.desc().nullslast(),
        TeacherMckoResult.id.desc(),
    ).all()
    for record in records:
        records_by_teacher.setdefault(record.teacher_id, []).append(mcko_result_view(record, as_of=as_of))

    query_text = " ".join((search or "").casefold().split())
    rows = []
    for teacher in users.values():
        teacher_departments = tuple(
            sorted(
                (
                    departments[item_id]
                    for item_id in department_ids_by_teacher.get(teacher.id, set())
                    if item_id in departments
                ),
                key=lambda item: item.name.casefold(),
            )
        )
        if department_id and int(department_id) not in department_ids_by_teacher.get(teacher.id, set()):
            continue
        if query_text and query_text not in f"{teacher.fio} {teacher.username}".casefold():
            continue

        views = records_by_teacher.get(teacher.id) or [None]
        for view in views:
            row = TeacherMckoRegistryRow(teacher=teacher, departments=teacher_departments, result=view)
            if activity_id:
                record_activity_id = None
                if view:
                    record_activity_id = view.record.education_activity_id
                    if record_activity_id is None and view.record.subject is not None:
                        record_activity_id = view.record.subject.education_activity_id
                if record_activity_id != int(activity_id):
                    continue
            if status and row.status != status:
                continue
            if expiry == "SIX_MONTHS" and row.status != "EXPIRING_SOON":
                continue
            if expiry == "EXPIRED" and row.status != "EXPIRED":
                continue
            if expiry == "VALID" and row.status != "ACTIVE":
                continue
            rows.append(row)

    return sorted(
        rows,
        key=lambda row: (
            (row.teacher.fio or row.teacher.username).casefold(),
            -(row.result.record.passed_at.toordinal() if row.result and row.result.record.passed_at else 0),
            -(row.result.record.id if row.result else 0),
        ),
    )


def mcko_registry_summary(rows):
    counts = {key: 0 for key in ("TOTAL", "ACTIVE", "EXPIRING_SOON", "EXPIRED", "INCOMPLETE", MISSING_STATUS)}
    counts["TOTAL"] = len({row.teacher.id for row in rows})
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


def remaining_period_label(result, *, as_of=None):
    if result is None or result.expires_at is None:
        return "—"
    as_of = as_of or date.today()
    days = (result.expires_at - as_of).days
    if days < 0:
        return f"просрочен на {abs(days)} дн."
    if days == 0:
        return "истекает сегодня"
    if days < 31:
        return f"{days} дн."
    months = days // 30
    return f"≈ {months} мес."
