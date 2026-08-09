from dataclasses import dataclass
from datetime import date

from app.models import TeacherAttestation, User
from app.services.teacher_professional_service import (
    add_calendar_months,
    add_calendar_years,
    entry_source_label,
)


ATTESTATION_CATEGORY_LABELS = {
    "POSITION_COMPLIANCE": "Соответствие занимаемой должности",
    "FIRST": "Первая квалификационная категория",
    "HIGHEST": "Высшая квалификационная категория",
}

ATTESTATION_WARNING_MONTHS = 6


def position_compliance_due_at(
    employment_start_date: date | None,
    *,
    last_decision_date: date | None = None,
) -> date | None:
    basis = last_decision_date or employment_start_date
    return add_calendar_years(basis, 2)


@dataclass(frozen=True)
class AttestationView:
    record: object
    category_label: str
    effective_valid_until: date | None
    status: str
    status_label: str
    source_label: str

    @property
    def teacher(self):
        return self.record.teacher


@dataclass(frozen=True)
class TeacherAttestationOverview:
    teacher: User
    current: AttestationView | None
    status: str
    status_label: str
    category_code: str
    category_label: str
    effective_valid_until: date | None
    basis_label: str

    @property
    def teacher_id(self):
        return self.teacher.id

    @property
    def record(self):
        return self.current.record if self.current else None


def attestation_view(record, *, as_of=None):
    as_of = as_of or date.today()
    category = (record.category or "").strip().upper()
    is_indefinite = bool(record.is_indefinite)
    valid_until = record.valid_until
    if category == "POSITION_COMPLIANCE" and not is_indefinite:
        valid_until = valid_until or position_compliance_due_at(
            None,
            last_decision_date=record.decision_date,
        )

    if category not in ATTESTATION_CATEGORY_LABELS or not record.decision_date:
        status = "INCOMPLETE"
        status_label = "Неполные данные"
    elif is_indefinite:
        status = "INDEFINITE"
        status_label = "Бессрочно"
    elif valid_until is None:
        status = "INCOMPLETE"
        status_label = "Не указан срок"
    elif valid_until < as_of:
        status = "EXPIRED"
        status_label = "Срок истёк"
    elif valid_until <= add_calendar_months(as_of, ATTESTATION_WARNING_MONTHS):
        status = "EXPIRING_SOON"
        status_label = "Истекает менее чем через 6 месяцев"
    else:
        status = "ACTIVE"
        status_label = "Действует"

    return AttestationView(
        record=record,
        category_label=ATTESTATION_CATEGORY_LABELS.get(
            category,
            record.category or "Не указано",
        ),
        effective_valid_until=valid_until,
        status=status,
        status_label=status_label,
        source_label=entry_source_label(record.entry_source),
    )


def _employment_requirement(teacher, *, as_of):
    due_at = position_compliance_due_at(teacher.employment_start_date)
    if due_at is None:
        return TeacherAttestationOverview(
            teacher=teacher,
            current=None,
            status="INCOMPLETE",
            status_label="Не указана дата приёма",
            category_code="MISSING",
            category_label="—",
            effective_valid_until=None,
            basis_label="Дата приёма не указана",
        )
    if due_at < as_of:
        status = "EXPIRED"
        status_label = "Необходимо пройти аттестацию"
    elif due_at <= add_calendar_months(as_of, ATTESTATION_WARNING_MONTHS):
        status = "EXPIRING_SOON"
        status_label = "Аттестация нужна менее чем через 6 месяцев"
    else:
        status = "ACTIVE"
        status_label = "Срок аттестации не наступил"
    return TeacherAttestationOverview(
        teacher=teacher,
        current=None,
        status=status,
        status_label=status_label,
        category_code="MISSING",
        category_label="—",
        effective_valid_until=due_at,
        basis_label="От даты приёма",
    )


def attestation_overviews_for_teachers(teacher_ids, *, as_of=None):
    """Return the current attestation state for every requested teacher.

    An active first or highest category suppresses the two-year position
    compliance reminder. Otherwise the latest position-compliance decision is
    used, followed by the employment date when no decision exists.
    """
    as_of = as_of or date.today()
    teacher_ids = sorted({int(value) for value in (teacher_ids or []) if value})
    if not teacher_ids:
        return {}
    teachers = {
        item.id: item
        for item in User.query.filter(User.id.in_(teacher_ids)).all()
    }
    records = TeacherAttestation.query.filter(
        TeacherAttestation.teacher_id.in_(teacher_ids),
        TeacherAttestation.is_archived.is_(False),
    ).order_by(
        TeacherAttestation.teacher_id.asc(),
        TeacherAttestation.decision_date.desc(),
        TeacherAttestation.id.desc(),
    ).all()
    grouped = {}
    for record in records:
        grouped.setdefault(record.teacher_id, []).append(
            attestation_view(record, as_of=as_of)
        )

    result = {}
    valid_category_statuses = {"ACTIVE", "EXPIRING_SOON", "INDEFINITE"}
    for teacher_id in teacher_ids:
        teacher = teachers.get(teacher_id)
        if teacher is None:
            continue
        views = grouped.get(teacher_id, [])
        category_view = next(
            (
                item
                for item in views
                if (item.record.category or "").upper() in {"FIRST", "HIGHEST"}
            ),
            None,
        )
        position_view = next(
            (
                item
                for item in views
                if (item.record.category or "").upper() == "POSITION_COMPLIANCE"
            ),
            None,
        )
        if category_view and category_view.status in valid_category_statuses:
            selected = category_view
            basis_label = "Действующая квалификационная категория"
        elif position_view:
            selected = position_view
            basis_label = "От последней аттестации"
        elif category_view:
            selected = category_view
            basis_label = "Квалификационная категория"
        else:
            result[teacher_id] = _employment_requirement(teacher, as_of=as_of)
            continue
        category_code = (selected.record.category or "").upper()
        result[teacher_id] = TeacherAttestationOverview(
            teacher=teacher,
            current=selected,
            status=selected.status,
            status_label=selected.status_label,
            category_code=category_code,
            category_label=selected.category_label,
            effective_valid_until=selected.effective_valid_until,
            basis_label=basis_label,
        )
    return result
