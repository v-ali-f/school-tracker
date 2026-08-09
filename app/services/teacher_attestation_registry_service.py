from dataclasses import dataclass
from datetime import date

from app.models import Department, User
from app.services.teacher_attestation_service import (
    TeacherAttestationOverview,
    attestation_overviews_for_teachers,
)
from app.services.teacher_mcko_registry_service import teacher_professional_roster


@dataclass(frozen=True)
class TeacherAttestationRegistryRow:
    teacher: User
    departments: tuple[Department, ...]
    overview: TeacherAttestationOverview

    @property
    def department_names(self):
        return ", ".join(item.name for item in self.departments) or "Без кафедры"

    @property
    def entered_by(self):
        record = self.overview.record
        if record is None:
            return "—"
        user = record.created_by_user
        return (user.fio or user.username) if user else "Не указано"


def teacher_attestation_registry_rows(
    *,
    search=None,
    department_id=None,
    category=None,
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
            if department_ids_by_teacher.get(teacher_id, set()).intersection(
                allowed_department_ids
            )
        }
    overviews = attestation_overviews_for_teachers(users.keys(), as_of=as_of)
    query_text = " ".join((search or "").casefold().split())
    rows = []
    for teacher in users.values():
        overview = overviews.get(teacher.id)
        if overview is None:
            continue
        teacher_department_ids = department_ids_by_teacher.get(teacher.id, set())
        if department_id and int(department_id) not in teacher_department_ids:
            continue
        if query_text and query_text not in f"{teacher.fio} {teacher.username}".casefold():
            continue
        if category and overview.category_code != category:
            continue
        if status and overview.status != status:
            continue
        if expiry == "SIX_MONTHS" and overview.status != "EXPIRING_SOON":
            continue
        if expiry == "EXPIRED" and overview.status != "EXPIRED":
            continue
        if expiry == "VALID" and overview.status not in {"ACTIVE", "INDEFINITE"}:
            continue
        teacher_departments = tuple(
            sorted(
                (
                    departments[item_id]
                    for item_id in teacher_department_ids
                    if item_id in departments
                ),
                key=lambda item: item.name.casefold(),
            )
        )
        rows.append(
            TeacherAttestationRegistryRow(
                teacher=teacher,
                departments=teacher_departments,
                overview=overview,
            )
        )
    return sorted(
        rows,
        key=lambda row: (row.teacher.fio or row.teacher.username).casefold(),
    )


def attestation_registry_summary(rows):
    counts = {
        key: 0
        for key in (
            "TOTAL",
            "ACTIVE",
            "INDEFINITE",
            "EXPIRING_SOON",
            "EXPIRED",
            "INCOMPLETE",
        )
    }
    counts["TOTAL"] = len(rows)
    for row in rows:
        status = row.overview.status
        counts[status] = counts.get(status, 0) + 1
    counts["VALID"] = counts["ACTIVE"] + counts["INDEFINITE"]
    return counts


def attestation_remaining_period_label(overview, *, as_of=None):
    due_at = overview.effective_valid_until
    if due_at is None:
        return "Бессрочно" if overview.status == "INDEFINITE" else "—"
    as_of = as_of or date.today()
    days = (due_at - as_of).days
    if days < 0:
        return f"просрочен на {abs(days)} дн."
    if days == 0:
        return "сегодня"
    if days < 31:
        return f"{days} дн."
    return f"≈ {days // 30} мес."
