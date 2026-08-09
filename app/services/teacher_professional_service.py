from datetime import date


ENTRY_SOURCE_SELF = "SELF_REPORTED"
ENTRY_SOURCE_ADMINISTRATION = "ADMINISTRATION"
ENTRY_SOURCE_LEGACY = "LEGACY"

ENTRY_SOURCE_LABELS = {
    ENTRY_SOURCE_SELF: "Внесено педагогом",
    ENTRY_SOURCE_ADMINISTRATION: "Внесено администрацией",
    ENTRY_SOURCE_LEGACY: "Ранее внесённые данные",
}


def professional_entry_source(*, teacher_id, actor_id):
    if teacher_id is not None and teacher_id == actor_id:
        return ENTRY_SOURCE_SELF
    return ENTRY_SOURCE_ADMINISTRATION


def entry_source_label(value):
    return ENTRY_SOURCE_LABELS.get(value, "Источник не указан")


def add_calendar_years(value: date | None, years: int) -> date | None:
    if value is None:
        return None
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def add_calendar_months(value: date | None, months: int) -> date | None:
    if value is None:
        return None
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = value.day
    while day > 28:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
    return date(year, month, day)
