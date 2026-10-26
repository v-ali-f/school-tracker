"""Access and validation shared by safety passport routes."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import current_app

from sqlalchemy import or_

from app.core.extensions import db
from app.models import SafetyOfficerAssignment, SafetyPassport, SchoolClassroom, User
from app.models.safety_passport import utc_now


STATUS_LABELS = {
    "not_started": "Не начат",
    "draft": "Черновик",
    "in_review": "На проверке",
    "needs_work": "Требует доработки",
    "verified": "Проверен",
    "noncompliant": "Не соответствует",
    "needs_recheck": "Требует повторной проверки",
    "archived": "Архивный",
}
REVIEW_RESULTS = {
    "verified": "Проверен",
    "needs_work": "Требует доработки",
    "noncompliant": "Не соответствует",
}
COMPLIANCE_LABELS = {
    "fire": "Пожарная безопасность",
    "electric": "Электробезопасность",
    "lighting": "Освещение",
    "furniture": "Мебель",
    "room": "Состояние помещения",
}
ROW_SCHEMAS = {
    "inventory": ("name", "quantity", "inventory_number", "condition", "note"),
    "teaching_aids": ("kind", "title", "subject", "quantity"),
    "literature": ("category", "author", "title", "year", "quantity", "note"),
    "occupancy": ("weekday", "start", "end", "kind", "description"),
    "development": ("activity", "due_date", "responsible", "status", "result"),
}
TEXT_FIELDS = (
    "purpose", "safety_notes", "annual_year", "self_analysis",
    "method_evaluation", "conclusions",
)


def role_codes(user):
    values = set(getattr(user, "role_codes", None) or [])
    values.add(getattr(user, "role", ""))
    return {str(code).upper() for code in values if code}


def is_director(user):
    return "DIRECTOR" in role_codes(user)


def school_today():
    try:
        zone = ZoneInfo(current_app.config.get("SCHOOL_TIMEZONE", "Europe/Moscow"))
    except KeyError:
        zone = ZoneInfo("UTC")
    return datetime.now(zone).date()


def is_admin(user):
    return "ADMIN" in role_codes(user)


def is_officer(user, on_date=None):
    on_date = on_date or school_today()
    return (
        SafetyOfficerAssignment.query
        .filter(
            SafetyOfficerAssignment.user_id == user.id,
            SafetyOfficerAssignment.revoked_at.is_(None),
            SafetyOfficerAssignment.valid_from <= on_date,
            or_(SafetyOfficerAssignment.valid_to.is_(None), SafetyOfficerAssignment.valid_to >= on_date),
        )
        .first() is not None
    )


def is_assigned_teacher(user, classroom):
    return bool(classroom.is_active and user.id in classroom.assigned_teacher_ids)


def can_view(user, classroom):
    return is_director(user) or is_admin(user) or is_officer(user) or is_assigned_teacher(user, classroom)


def can_edit(user, classroom):
    return is_assigned_teacher(user, classroom)


def can_access_registry(user):
    if is_director(user) or is_admin(user) or is_officer(user):
        return True
    return (
        SchoolClassroom.query
        .filter(SchoolClassroom.is_active.is_(True))
        .filter(or_(
            SchoolClassroom.teacher_user_id == user.id,
            SchoolClassroom.teachers.any(User.id == user.id),
        ))
        .first() is not None
    )


def ensure_passport(classroom):
    passport = SafetyPassport.query.filter_by(classroom_id=classroom.id).first()
    template_code = "primary" if "начальн" in (classroom.room_type or "").strip().lower() else "general"
    if passport is None:
        passport = SafetyPassport(
            classroom_id=classroom.id,
            template_code=template_code,
            template_version=1,
        )
        db.session.add(passport)
        db.session.flush()
    elif passport.current_revision_number == 0 and passport.template_code != template_code:
        passport.template_code = template_code
    return passport


def current_revision(passport):
    if not passport or not passport.current_revision_number:
        return None
    return next((row for row in passport.revisions if row.number == passport.current_revision_number), None)


def _clean(value, max_length=5000):
    value = (value or "").strip()
    if len(value) > max_length:
        raise ValueError("Одно из полей превышает допустимую длину.")
    return value


def _parse_rows(form, section, columns):
    lists = {column: form.getlist(f"{section}_{column}[]") for column in columns}
    count = max((len(values) for values in lists.values()), default=0)
    if count > 100:
        raise ValueError("В одном разделе допускается не более 100 строк.")
    result = []
    for index in range(count):
        row = {
            column: _clean(lists[column][index] if index < len(lists[column]) else "", 255)
            for column in columns
        }
        if not any(row.values()):
            continue
        if not row[columns[0]]:
            raise ValueError("У каждой заполненной строки должен быть первый столбец.")
        if "quantity" in row and row["quantity"]:
            try:
                number = int(row["quantity"])
            except ValueError:
                raise ValueError("Количество должно быть целым числом.") from None
            if number <= 0 or number > 100000:
                raise ValueError("Количество должно быть положительным и не больше 100000.")
            row["quantity"] = number
        if section == "occupancy" and row["start"] and row["end"] and row["start"] >= row["end"]:
            raise ValueError("В занятости время окончания должно быть позже начала.")
        if section == "literature" and row["year"]:
            try:
                year = int(row["year"])
            except ValueError:
                raise ValueError("Укажите корректный год издания.") from None
            if year < 1800 or year > date.today().year + 1:
                raise ValueError("Укажите корректный год издания.")
            row["year"] = year
        result.append(row)
    return result


def parse_passport_form(form):
    data = {key: _clean(form.get(key), 100 if key == "annual_year" else 5000) for key in TEXT_FIELDS}
    data["compliance"] = {}
    for code in COMPLIANCE_LABELS:
        value = (form.get(f"compliance_{code}") or "").strip()
        if value not in {"", "yes", "no", "na"}:
            raise ValueError("Недопустимое значение самооценки.")
        data["compliance"][code] = {
            "value": value,
            "comment": _clean(form.get(f"compliance_{code}_comment"), 1000),
        }
    for section, columns in ROW_SCHEMAS.items():
        data[section] = _parse_rows(form, section, columns)
    return data


def form_data_for_display(form):
    """Keep entered values visible after a validation or edit conflict."""
    data = {key: form.get(key, "") for key in TEXT_FIELDS}
    data["compliance"] = {
        code: {
            "value": form.get(f"compliance_{code}", ""),
            "comment": form.get(f"compliance_{code}_comment", ""),
        }
        for code in COMPLIANCE_LABELS
    }
    for section, columns in ROW_SCHEMAS.items():
        values = {column: form.getlist(f"{section}_{column}[]") for column in columns}
        count = min(max((len(items) for items in values.values()), default=0), 100)
        data[section] = [
            {column: values[column][i] if i < len(values[column]) else "" for column in columns}
            for i in range(count)
        ]
    return data


def save_revision(passport, user, data, expected_number):
    from app.models import SafetyPassportRevision

    if passport.current_revision_number != expected_number:
        raise ValueError("Паспорт уже изменён другим сотрудником. Обновите страницу перед сохранением.")
    if passport.status == "in_review":
        raise ValueError("Редакция находится на проверке.")
    if passport.status == "archived":
        raise ValueError("Архивный паспорт нельзя изменять.")
    previous = current_revision(passport)
    if previous is not None and previous.data == data:
        return previous
    number = passport.current_revision_number + 1
    revision = SafetyPassportRevision(
        passport=passport,
        number=number,
        data=data,
        created_by_id=user.id,
    )
    db.session.add(revision)
    passport.current_revision_number = number
    passport.status = "needs_recheck" if passport.status == "verified" else "draft"
    passport.updated_at = utc_now()
    return revision
