from dataclasses import dataclass
from datetime import date

from app.core.extensions import db
from app.models import TeacherMckoResult
from app.services.teacher_professional_service import (
    add_calendar_months,
    add_calendar_years,
    entry_source_label,
)


MCKO_LEVEL_LABELS = {
    "BELOW_BASIC": "Ниже базового",
    "BASIC": "Базовый",
    "HIGH": "Высокий",
    "EXPERT": "Экспертный",
}

MCKO_WARNING_MONTHS = 6

_MCKO_LEVEL_ALIASES = {
    "below_basic": "BELOW_BASIC",
    "ниже базового": "BELOW_BASIC",
    "нижебазового": "BELOW_BASIC",
    "basic": "BASIC",
    "базовый": "BASIC",
    "базовый уровень": "BASIC",
    "high": "HIGH",
    "высокий": "HIGH",
    "высокий уровень": "HIGH",
    "expert": "EXPERT",
    "экспертный": "EXPERT",
    "экспертный уровень": "EXPERT",
}


def normalize_mcko_level(value):
    normalized = " ".join((value or "").strip().lower().split())
    code = _MCKO_LEVEL_ALIASES.get(normalized)
    if code is None and (value or "").strip().upper() in MCKO_LEVEL_LABELS:
        code = (value or "").strip().upper()
    return code


def mcko_level_label(value):
    code = normalize_mcko_level(value)
    return MCKO_LEVEL_LABELS.get(code, value or "Не указан")


def mcko_expires_at(passed_at):
    return add_calendar_years(passed_at, 3)


@dataclass(frozen=True)
class MckoResultView:
    record: TeacherMckoResult
    activity_name: str
    level_code: str | None
    level_label: str
    expires_at: date | None
    status: str
    status_label: str
    source_label: str
    remaining_days: int | None

    @property
    def teacher(self):
        return self.record.teacher

    @property
    def passed_at(self):
        return self.record.passed_at

    @property
    def result_text(self):
        return self.record.result_text

    @property
    def certificate_number(self):
        return self.record.certificate_number

def mcko_result_view(record, *, as_of=None):
    as_of = as_of or date.today()
    expires_at = (
        mcko_expires_at(record.passed_at)
        if record.passed_at is not None
        else record.expires_at
    )
    if record.passed_at is None or expires_at is None:
        status = "INCOMPLETE"
        status_label = "Неполные данные"
    elif expires_at < as_of:
        status = "EXPIRED"
        status_label = "Срок истёк"
    elif expires_at <= add_calendar_months(as_of, MCKO_WARNING_MONTHS):
        status = "EXPIRING_SOON"
        status_label = "Истекает менее чем через 6 месяцев"
    else:
        status = "ACTIVE"
        status_label = "Действует"
    activity = record.education_activity
    if activity is None and record.subject is not None:
        activity = record.subject.education_activity
    return MckoResultView(
        record=record,
        activity_name=activity.name if activity else "Предмет не указан",
        level_code=normalize_mcko_level(record.level),
        level_label=mcko_level_label(record.level),
        expires_at=expires_at,
        status=status,
        status_label=status_label,
        source_label=entry_source_label(record.entry_source),
        remaining_days=(expires_at - as_of).days if expires_at else None,
    )


def mcko_results_for_teachers(
    teacher_ids,
    *,
    teacher_id=None,
    academic_year_id=None,
    as_of=None,
):
    teacher_ids = list(teacher_ids or [])
    if not teacher_ids:
        return []
    query = TeacherMckoResult.query.filter(
        TeacherMckoResult.teacher_id.in_(teacher_ids),
        TeacherMckoResult.is_archived.is_(False),
    )
    if teacher_id:
        query = query.filter(TeacherMckoResult.teacher_id == teacher_id)
    if academic_year_id is not None:
        query = query.filter(
            db.or_(
                TeacherMckoResult.academic_year_id == academic_year_id,
                TeacherMckoResult.academic_year_id.is_(None),
            ),
        )
    records = query.order_by(
        TeacherMckoResult.teacher_id.asc(),
        TeacherMckoResult.passed_at.desc().nullslast(),
        TeacherMckoResult.id.desc(),
    ).all()
    return [mcko_result_view(item, as_of=as_of) for item in records]


def current_mcko_by_teacher(teacher_ids, *, as_of=None):
    views = mcko_results_for_teachers(teacher_ids, as_of=as_of)
    result = {}
    seen_activities = set()
    for view in views:
        if view.status not in {"ACTIVE", "EXPIRING_SOON"}:
            continue
        activity_id = view.record.education_activity_id or view.record.subject_id
        key = (view.record.teacher_id, activity_id)
        if key in seen_activities:
            continue
        seen_activities.add(key)
        result.setdefault(view.record.teacher_id, []).append(view)
    return result
