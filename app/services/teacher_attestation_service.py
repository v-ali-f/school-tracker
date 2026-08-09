from dataclasses import dataclass
from datetime import date

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
