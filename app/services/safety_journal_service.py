"""Roster snapshots and validation for ordinary safety journals."""

import hashlib
import json
import re
from datetime import datetime, time

from sqlalchemy import case, or_
from sqlalchemy.orm import joinedload

from app.core.extensions import db
from app.models import (
    AcademicYear, ChildEnrollment, EducationPlan, EducationPlanLine,
    PopulationSnapshotClass, SafetyInstructionVersion, SchoolClass,
    TariffCycle, TariffVersion, TeacherLoad, TeachingGroup, TeachingGroupClass,
    WorkloadAssignment,
)
from app.services.org_settings_service import get_active_organization_settings
from app.services.safety_passport_service import (
    is_admin, is_director, is_officer, role_codes, school_today,
)

CLASS_TEACHER_SUBJECT = "Классное руководство"


def can_create_journal(user):
    return bool(role_codes(user).intersection({"TEACHER", "CLASS_TEACHER", "ADMIN", "DIRECTOR"}))


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


def _workload_version(year):
    organization = get_active_organization_settings()
    query = TariffVersion.query.join(TariffCycle).filter(TariffCycle.academic_year_id == year.id)
    if organization is not None:
        query = query.filter(TariffCycle.organization_id == organization.id)
    return query.order_by(
        case((TariffVersion.status == "DRAFT", 0), (TariffVersion.status == "EFFECTIVE", 1), else_=2),
        TariffVersion.version_no.desc(),
    ).first()


def _legacy_class_tokens(value):
    return {
        re.sub(r"\s+", "", token).replace("ё", "е").casefold()
        for token in re.split(r"[,;|/\n]+", value or "")
        if token.strip()
    }


def _legacy_teacher_subjects(year, user, classes):
    rows = TeacherLoad.query.filter(
        TeacherLoad.is_archived.is_(False),
        or_(TeacherLoad.academic_year_id == year.id, TeacherLoad.academic_year_id.is_(None)),
    )
    if not (is_admin(user) or is_director(user)):
        rows = rows.filter(TeacherLoad.teacher_id == user.id)
    subjects = {item.id: set() for item in classes}
    normalized = {item.id: re.sub(r"\s+", "", item.name).replace("ё", "е").casefold() for item in classes}
    for load in rows.all():
        name = (load.education_activity.name if load.education_activity else load.subject_name or (load.subject.name if load.subject else "")).strip()
        if not name:
            continue
        tokens = _legacy_class_tokens(load.class_name)
        for classroom in classes:
            if normalized[classroom.id] in tokens:
                subjects[classroom.id].add(name)
    return subjects


def _group_class_ids(group):
    groups = [group]
    if group.group_type == "METAGROUP":
        groups.extend(link.source_group for link in group.metagroup_sources)
    return {
        link.population_snapshot_class.source_school_class_id
        for item in groups for link in item.source_classes
        if link.population_snapshot_class.source_school_class_id is not None
    }


def _teacher_subjects_from_workload(on_date, user, version):
    rows = WorkloadAssignment.query.filter(
        WorkloadAssignment.tariff_version_id == version.id,
        WorkloadAssignment.employee_user_id == user.id,
        WorkloadAssignment.status != "CANCELLED",
        WorkloadAssignment.assignment_kind != "VACANCY",
        WorkloadAssignment.date_from <= on_date,
        WorkloadAssignment.date_to >= on_date,
    ).all()
    result = {}
    for assignment in rows:
        need = assignment.workload_need
        group = need.teaching_group if need else None
        if not group or not (need.date_from <= on_date <= need.date_to and group.valid_from <= on_date <= group.valid_to):
            continue
        if group.status == "CLOSED" or group.source_plan_line.education_plan.plan_kind != "CURRICULUM":
            continue
        name = (need.education_activity.name or "").strip()
        for class_id in _group_class_ids(group):
            result.setdefault(class_id, set()).add(name)
    return result


def journal_classes_for_user(on_date, user, grade=None, *, trip=False, homeroom=False):
    classes = available_classes(on_date, grade)
    if trip or is_admin(user) or is_director(user):
        return classes
    year = year_for_date(on_date)
    version = _workload_version(year)
    subjects = (
        _teacher_subjects_from_workload(on_date, user, version)
        if version else _legacy_teacher_subjects(year, user, classes)
    )
    return [item for item in classes if subjects.get(item.id) or (homeroom and item.teacher_user_id == user.id)]


def journal_subjects_for_class(on_date, user, classroom, *, trip=False):
    if trip:
        return sorted({item.instruction.category for item in effective_instruction_versions(on_date)}, key=str.casefold)
    year = year_for_date(on_date)
    version = _workload_version(year)
    if version is None:
        subjects = _legacy_teacher_subjects(year, user, [classroom]).get(classroom.id, set())
    elif is_admin(user) or is_director(user):
        groups = (
            TeachingGroup.query
            .join(TeachingGroupClass, TeachingGroupClass.teaching_group_id == TeachingGroup.id)
            .join(PopulationSnapshotClass, PopulationSnapshotClass.id == TeachingGroupClass.population_snapshot_class_id)
            .join(EducationPlanLine, EducationPlanLine.id == TeachingGroup.source_plan_line_id)
            .join(EducationPlan, EducationPlan.id == EducationPlanLine.education_plan_id)
            .filter(
                TeachingGroup.tariff_version_id == version.id,
                PopulationSnapshotClass.source_school_class_id == classroom.id,
                EducationPlan.plan_kind == "CURRICULUM",
                TeachingGroup.status != "CLOSED",
                TeachingGroup.valid_from <= on_date,
                TeachingGroup.valid_to >= on_date,
            ).all()
        )
        subjects = {group.education_activity.name for group in groups}
    else:
        subjects = _teacher_subjects_from_workload(on_date, user, version).get(classroom.id, set())
    return sorted((name for name in subjects if name), key=str.casefold)


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
    if draft.briefing_at is None:
        raise ValueError("Укажите дату и время проведения инструктажа.")
    on_date = draft.instructed_on
    if on_date is None or on_date > school_today():
        raise ValueError("Укажите дату учёта для подбора состава и инструкции.")
    version = draft.instruction_version
    library_item = None
    subject = (draft.subject or (version.instruction.category if version else "")).strip()
    if draft.library_item_id:
        if version or draft.trip_assignment_id is not None:
            raise ValueError("Укажите один источник инструкции.")
        from app.modules.safety_instructions.routes import journal_library_item
        library_item = journal_library_item(
            draft.library_item_id,
            None if draft.journal_kind in {"trip", "class_teacher"} else subject,
            section="class_teacher" if draft.journal_kind == "class_teacher" else None,
        )
        library_full_title = (library_item.get("title") or "").strip()
        library_number, _, library_title = library_full_title.partition(" ")
        library_title = library_title.strip() or library_full_title
        if not library_full_title or len(library_title) > 500 or len(library_number) > 80:
            raise ValueError("У PDF из перечня нет корректного номера или названия.")
    elif not instruction_is_effective(version, on_date):
        raise ValueError("Выберите действующую на эту дату инструкцию.")
    briefing_kind = (draft.briefing_kind or (version.instruction.briefing_kind if version else "")).strip().casefold()
    if briefing_kind not in {"первичный", "повторный", "внеплановый", "целевой"}:
        raise ValueError("Выберите вид инструктажа.")
    header_note = (draft.header_note or "").strip()
    if len(header_note) > 500:
        raise ValueError("Дополнительная информация должна быть не длиннее 500 символов.")
    if not draft.class_ids:
        raise ValueError("Выберите хотя бы один класс.")
    if not draft.selected_child_ids:
        raise ValueError("Добавьте хотя бы одного участника.")
    if draft.trip_assignment_id is None and draft.journal_kind != "trip":
        allowed_classes = {item.id: item for item in journal_classes_for_user(on_date, author, homeroom=draft.journal_kind == "class_teacher")}
        if len(draft.class_ids) != 1 or draft.class_ids[0] not in allowed_classes:
            raise ValueError("Выбранный класс больше не доступен в нагрузке.")
        if draft.journal_kind == "class_teacher":
            if subject != CLASS_TEACHER_SUBJECT:
                raise ValueError("Выберите инструкцию для классного руководства.")
        elif not any(item.strip().casefold() == subject.casefold() for item in journal_subjects_for_class(on_date, author, allowed_classes[draft.class_ids[0]])):
            raise ValueError("Выбранный предмет больше не доступен для класса.")
        if version and version.instruction.category.strip().casefold() != subject.casefold():
            raise ValueError("Инструкция не соответствует выбранному предмету.")
    trip = None
    if draft.journal_kind == "trip" and draft.trip_order_id is None:
        trip = draft.manual_trip or {}
        if not trip.get("trip_kind") or not trip.get("destination") or not trip.get("trip_date"):
            raise ValueError("Укажите вид, место и дату выезда.")
        if not set(draft.class_ids).issubset({item.id for item in journal_classes_for_user(on_date, author, trip=True)}):
            raise ValueError("Один из классов выезда больше не доступен.")
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
    if draft.journal_kind == "trip" and draft.trip_order_id is None:
        if {item["class_id"] for item in snapshots} != set(draft.class_ids):
            raise ValueError("Состав классов выезда изменился. Обновите список участников.")
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
        "briefing_at": draft.briefing_at.isoformat(),
        "instruction_version_id": version.id if version else None,
        "library_item_id": draft.library_item_id if library_item else None,
        "subject": subject,
        "instruction_number": version.instruction.number if version else library_number,
        "instruction_title": version.title_snapshot if version else library_title,
        "instruction_summary": version.summary if version else library_title,
        "instruction_file_sha256": version.file_sha256 if version else draft.library_item_id,
        "instruction_version_number": version.version_number if version else 0,
        "briefing_kind": briefing_kind,
        "header_note": header_note,
        "organization_name": org_name,
        "instructor_name": author.fio,
        "group_label": group_label,
        "participants": snapshots,
    }
    if draft.trip_assignment_id is not None:
        payload["trip"] = trip_snapshot(trip, assignment)
    elif trip is not None:
        payload["trip"] = trip
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return payload, hashlib.sha256(encoded).hexdigest()
