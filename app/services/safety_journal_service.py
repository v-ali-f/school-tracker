"""Roster snapshots and validation for ordinary safety journals."""

import hashlib
import json
from datetime import datetime, time

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.models import (
    AcademicYear, ChildEnrollment,
    SafetyInstructionVersion, SchoolClass,
)
from app.services.org_settings_service import get_active_organization_settings
from app.services.safety_passport_service import (
    is_admin, is_director, is_officer, role_codes, school_today,
)


def can_create_journal(user):
    return bool(role_codes(user).intersection({"TEACHER", "CLASS_TEACHER"}))


def can_view_page(user, page):
    return page.author_id == user.id or is_officer(user) or is_director(user) or is_admin(user)


def instruction_is_effective(version, on_date):
    return bool(
        version
        and version.status == "active"
        and version.approved_on <= on_date
        and version.effective_from <= on_date
        and (version.effective_to is None or version.effective_to >= on_date)
    )


def effective_instruction_versions(on_date):
    return (
        SafetyInstructionVersion.query
        .options(joinedload(SafetyInstructionVersion.instruction))
        .filter(
            SafetyInstructionVersion.status == "active",
            SafetyInstructionVersion.approved_on <= on_date,
            SafetyInstructionVersion.effective_from <= on_date,
            or_(SafetyInstructionVersion.effective_to.is_(None), SafetyInstructionVersion.effective_to >= on_date),
        )
        .all()
    )


def year_for_date(on_date):
    year = (
        AcademicYear.query
        .filter(AcademicYear.start_date <= on_date, AcademicYear.end_date >= on_date)
        .order_by(AcademicYear.id.desc())
        .first()
    )
    if year is not None:
        return year
    current = AcademicYear.query.filter_by(is_current=True).first()
    if current is not None and (current.start_date is None or current.start_date <= on_date) and (current.end_date is None or current.end_date >= on_date):
        return current
    raise ValueError("Для даты инструктажа не найден учебный год.")


def available_classes(on_date=None, grade=None):
    on_date = on_date or school_today()
    year = year_for_date(on_date)
    query = SchoolClass.query.filter_by(academic_year_id=year.id, is_active=True)
    if grade:
        query = query.filter(SchoolClass.grade == grade)
    return query.order_by(SchoolClass.grade, SchoolClass.name).all()


def _enrollments_on_date(on_date, class_ids=None, child_ids=None):
    year = year_for_date(on_date)
    day_start = datetime.combine(on_date, time.min)
    day_end = datetime.combine(on_date, time.max)
    query = (
        ChildEnrollment.query
        .options(joinedload(ChildEnrollment.child), joinedload(ChildEnrollment.school_class))
        .filter(
            ChildEnrollment.academic_year_id == year.id,
            ChildEnrollment.school_class_id.isnot(None),
            ChildEnrollment.enrolled_at <= day_end,
            or_(ChildEnrollment.ended_at.is_(None), ChildEnrollment.ended_at >= day_start),
        )
    )
    if class_ids is not None:
        query = query.filter(ChildEnrollment.school_class_id.in_(class_ids))
    if child_ids is not None:
        query = query.filter(ChildEnrollment.child_id.in_(child_ids))
    result = {}
    for item in query.order_by(ChildEnrollment.enrolled_at.desc(), ChildEnrollment.id.desc()).all():
        result.setdefault(item.child_id, item)
    return result


def roster_for_classes(on_date, class_ids):
    if not class_ids:
        return {}
    classes = available_classes(on_date)
    available_ids = {item.id for item in classes}
    if not set(class_ids).issubset(available_ids):
        raise ValueError("Один из выбранных классов недоступен на дату инструктажа.")
    return _enrollments_on_date(on_date, class_ids=class_ids)


def selected_enrollments(on_date, child_ids):
    child_ids = [int(value) for value in child_ids]
    if not child_ids or len(child_ids) > 120 or len(child_ids) != len(set(child_ids)):
        raise ValueError("Выберите от 1 до 120 обучающихся без повторов.")
    result = _enrollments_on_date(on_date, child_ids=child_ids)
    if set(result) != set(child_ids):
        raise ValueError("Состав контингента изменился. Обновите список участников.")
    return result


def search_students(on_date, text, limit=30):
    text = (text or "").strip()
    if len(text) < 2:
        return []
    all_enrollments = _enrollments_on_date(on_date)
    needle = text.casefold()
    results = [
        enrollment for enrollment in all_enrollments.values()
        if needle in enrollment.child.fio.casefold()
        or needle in enrollment.school_class.name.casefold()
        or needle == str(enrollment.child_id)
    ]
    results.sort(key=lambda item: (item.child.fio.casefold(), item.child_id))
    return results[:limit]


def age_on_date(birth_date, on_date):
    return on_date.year - birth_date.year - ((on_date.month, on_date.day) < (birth_date.month, birth_date.day))


def participant_snapshots(on_date, child_ids):
    enrollments = selected_enrollments(on_date, child_ids)
    result = []
    for child_id in child_ids:
        item = enrollments[int(child_id)]
        child = item.child
        if child.birth_date is None:
            raise ValueError(f"У обучающегося {child.fio} не указана дата рождения в контингенте.")
        result.append({
            "child_id": child.id,
            "full_name": child.fio,
            "birth_date": child.birth_date.isoformat(),
            "class_id": item.school_class_id,
            "class_name": item.school_class.name,
            "building_id": item.school_class.building_id,
            "signature_rule": "acquainted" if age_on_date(child.birth_date, on_date) < 14 else "handwritten",
        })
    result.sort(key=lambda item: (item["class_name"].casefold(), item["full_name"].casefold(), item["child_id"]))
    return result


def organization_full_name():
    settings = get_active_organization_settings()
    return (getattr(settings, "full_name", None) or getattr(settings, "legal_name", None) or "").strip()


def preview_payload(draft, author):
    if draft.status != "draft":
        raise ValueError("Эта страница уже сформирована.")
    on_date = draft.instructed_on
    if on_date is None or on_date > school_today():
        raise ValueError("Укажите дату проведённого инструктажа.")
    version = draft.instruction_version
    if not instruction_is_effective(version, on_date):
        raise ValueError("Выберите действующую на эту дату инструкцию.")
    if not draft.class_ids:
        raise ValueError("Выберите хотя бы один класс.")
    if not draft.selected_child_ids:
        raise ValueError("Добавьте хотя бы одного участника.")
    trip = None
    if draft.trip_assignment_id is not None:
        from app.services.safety_trip_service import trip_snapshot
        trip = draft.trip_order
        assignment = draft.trip_assignment
        if not trip or not assignment or not assignment.is_active or assignment.order_id != trip.order_id or assignment.user_id != author.id or trip.cancelled_at is not None:
            raise ValueError("Назначение по выезду больше не действует.")
        if draft.trip_order_revision != trip.revision_number:
            raise ValueError("Приказ о выезде изменился. Создайте новый черновик из карточки выезда.")
        if on_date > trip.trip_date:
            raise ValueError("Инструктаж по выезду должен пройти не позднее даты выезда.")
    snapshots = participant_snapshots(on_date, draft.selected_child_ids)
    if not (author.last_name or "").strip() or not (author.first_name or "").strip():
        raise ValueError("Заполните полное ФИО в профиле педагога.")
    org_name = organization_full_name()
    if not org_name:
        raise ValueError("Сначала укажите полное наименование организации в настройках.")
    class_names = sorted({item["class_name"] for item in snapshots})
    group_label = ", ".join(class_names)
    if len(group_label) > 255:
        raise ValueError("Для одной страницы выбрано слишком много разных классов.")
    payload = {
        "date": on_date.isoformat(),
        "instruction_version_id": version.id,
        "instruction_number": version.instruction.number,
        "instruction_title": version.title_snapshot,
        "instruction_summary": version.summary,
        "instruction_file_sha256": version.file_sha256,
        "instruction_version_number": version.version_number,
        "organization_name": org_name,
        "instructor_name": author.fio,
        "group_label": group_label,
        "participants": snapshots,
    }
    if trip is not None:
        payload["trip"] = trip_snapshot(trip, assignment)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return payload, hashlib.sha256(encoded).hexdigest()
