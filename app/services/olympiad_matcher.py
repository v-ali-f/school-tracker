from __future__ import annotations

import re
from typing import List, Optional, Tuple

from sqlalchemy import func

from app.core.extensions import db

from ..models import (
    Child,
    ChildEnrollment,
    Department,
    DepartmentSubject,
    EducationActivity,
    OlympiadSubjectMapping,
    SchoolClass,
    TeacherLoad,
)
from app.services.education_activity_service import (
    get_subject_activity,
    resolve_education_activity,
    sync_subject_from_activity,
)


def normalize_text(value) -> str:
    return " ".join(str(value or "").replace("ё", "е").replace("Ё", "Е").split()).strip()


def _norm_lower(value: str) -> str:
    return normalize_text(value).lower()


def _canon_class(value: str) -> str:
    text = normalize_text(value).upper().replace("КЛАСС", "")
    text = re.sub(r"[^0-9A-ZА-ЯЁ]", "", text)
    return text


def parse_grade(value) -> Optional[int]:
    text = normalize_text(value)
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else None


def parse_class_parts(value) -> Tuple[Optional[int], Optional[str], str]:
    text = normalize_text(value).upper().replace("КЛАСС", "").strip()
    if not text:
        return None, None, ""
    m = re.search(r"(\d+)\s*[-–—]?\s*([А-ЯA-ZЁ]{1,5})?", text)
    if not m:
        return None, None, text
    grade = int(m.group(1)) if m.group(1) else None
    letter = (m.group(2) or "").strip(" .") or None
    return grade, letter, text


def parse_short_fio(text: str) -> dict:
    text = normalize_text(text)
    if not text:
        return {"last_name": "", "first_initial": "", "middle_initial": ""}
    parts = text.split()
    last_name = parts[0] if parts else ""
    initials = " ".join(parts[1:])
    letters = re.findall(r"[А-ЯA-ZЁ]", initials, flags=re.IGNORECASE)
    first_initial = letters[0].upper() if len(letters) >= 1 else ""
    middle_initial = letters[1].upper() if len(letters) >= 2 else ""
    return {
        "last_name": last_name,
        "first_initial": first_initial,
        "middle_initial": middle_initial,
    }


def _get_row_value(row: dict, *keys, default=None):
    for key in keys:
        if row.get(key) not in (None, ""):
            return row.get(key)
    return default


def _mapping_grade_matches(mapping, grade: Optional[int]) -> bool:
    if grade is None:
        return True
    g_from = getattr(mapping, "grade_from", None)
    g_to = getattr(mapping, "grade_to", None)
    if g_from is None and g_to is None:
        return True
    if g_from is not None and grade < g_from:
        return False
    if g_to is not None and grade > g_to:
        return False
    return True


def _mapping_activity_ids(mapping) -> List[int]:
    values = mapping.linked_education_activity_id_list()
    seen = set()
    result = []
    for item in values:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _subject_names_for_mapping(mapping) -> List[str]:
    names = []
    for activity_id in _mapping_activity_ids(mapping):
        activity = get_subject_activity(activity_id)
        if activity and activity.name:
            names.append(activity.name)
    return names


def _find_mapping_for_subject_name(subject_name: str, grade: Optional[int] = None):
    if not subject_name:
        return None
    norm = _norm_lower(subject_name)
    mappings = OlympiadSubjectMapping.query.filter(
        OlympiadSubjectMapping.is_active.is_(True),
        func.lower(OlympiadSubjectMapping.olympiad_subject_name) == norm,
    ).order_by(
        OlympiadSubjectMapping.priority.asc(),
        OlympiadSubjectMapping.grade_from.asc().nullsfirst(),
        OlympiadSubjectMapping.id.asc(),
    ).all()
    for mapping in mappings:
        if _mapping_grade_matches(mapping, grade):
            return mapping
    return mappings[0] if mappings else None


def _subject_by_name(subject_name: str, grade: Optional[int] = None):
    if not subject_name:
        return None, None, None
    norm = _norm_lower(subject_name)
    mapping = _find_mapping_for_subject_name(subject_name, grade=grade)
    if mapping and mapping.education_activity:
        subject = sync_subject_from_activity(mapping.education_activity)
        return subject, mapping.department, mapping

    match = resolve_education_activity(
        subject_name,
        source_module="OLYMPIAD",
    )
    activity = match.activity
    if activity is None:
        activity = EducationActivity.query.filter(
            EducationActivity.activity_kind == "SUBJECT",
            EducationActivity.is_active.is_(True),
            func.lower(EducationActivity.name).like(f"%{norm}%"),
        ).order_by(EducationActivity.name.asc()).first()
    if activity is None:
        for item in EducationActivity.query.filter(
            EducationActivity.activity_kind == "SUBJECT",
            EducationActivity.is_active.is_(True),
        ).order_by(EducationActivity.name.asc()).all():
            item_norm = _norm_lower(item.name)
            if item_norm in norm or norm in item_norm:
                activity = item
                break
    if activity:
        subject = sync_subject_from_activity(activity)
        dep_link = DepartmentSubject.query.filter_by(
            education_activity_id=activity.id,
        ).first()
        return subject, dep_link.department if dep_link else None, None
    return None, None, None


def find_subject_for_row(row: dict, manual_subject_id: Optional[int] = None):
    if manual_subject_id:
        activity = get_subject_activity(manual_subject_id)
        subject = sync_subject_from_activity(activity) if activity else None
        dep_link = (
            DepartmentSubject.query.filter_by(
                education_activity_id=manual_subject_id,
            ).first()
            if subject else None
        )
        return subject, dep_link.department if dep_link else None, None
    raw_subject = _get_row_value(row, "subject", "subject_name", "raw_subject", default="")
    grade = parse_grade(_get_row_value(row, "class_study", "class_study_text", "class_participation", default=""))
    subject, department, mapping = _subject_by_name(str(raw_subject or ""), grade=grade)
    if subject:
        return subject, department, None
    return None, None, "Предмет не сопоставлен"


def resolve_school_class_for_child(child_id: int, academic_year_id: Optional[int] = None):
    q = ChildEnrollment.query.filter(ChildEnrollment.child_id == child_id)
    if academic_year_id:
        q = q.filter(ChildEnrollment.academic_year_id == academic_year_id)
    enrollment = q.order_by(ChildEnrollment.id.desc()).first()
    return enrollment.school_class if enrollment and enrollment.school_class else None


def find_child_for_row(row: dict, academic_year_id: Optional[int] = None):
    raw_fio = normalize_text(_get_row_value(row, "fio", "raw_fio", default=""))
    if not raw_fio:
        return None, "ФИО отсутствует"

    parsed = parse_short_fio(raw_fio)
    last_name = normalize_text(parsed["last_name"])
    first_initial = parsed["first_initial"]
    middle_initial = parsed["middle_initial"]
    grade, letter, _ = parse_class_parts(_get_row_value(row, "class_study", "class_study_text", "class_participation", default=""))

    if not last_name:
        return None, "Не удалось выделить фамилию"

    q = Child.query.join(ChildEnrollment, ChildEnrollment.child_id == Child.id).join(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
    if academic_year_id:
        q = q.filter(ChildEnrollment.academic_year_id == academic_year_id)
    q = q.filter(func.lower(Child.last_name) == last_name.lower())
    if grade is not None:
        q = q.filter(SchoolClass.grade == grade)
    if letter:
        q = q.filter(func.lower(func.coalesce(SchoolClass.letter, '')) == letter.lower())

    candidates = q.all()
    if not candidates and letter:
        q2 = Child.query.join(ChildEnrollment, ChildEnrollment.child_id == Child.id).join(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
        if academic_year_id:
            q2 = q2.filter(ChildEnrollment.academic_year_id == academic_year_id)
        q2 = q2.filter(func.lower(Child.last_name) == last_name.lower())
        if grade is not None:
            q2 = q2.filter(SchoolClass.grade == grade)
        candidates = q2.all()

    exact: List[Child] = []
    for child in candidates:
        fn = normalize_text(getattr(child, "first_name", ""))
        mn = normalize_text(getattr(child, "middle_name", ""))
        ok_first = not first_initial or (fn and fn[:1].upper() == first_initial)
        ok_middle = not middle_initial or (mn and mn[:1].upper() == middle_initial)
        if ok_first and ok_middle:
            exact.append(child)

    if len(exact) == 1:
        return exact[0], None
    if len(candidates) == 1:
        return candidates[0], None
    if len(exact) > 1:
        return None, f"Найдено несколько учеников с фамилией {last_name}"
    return None, f"Ученик не найден: {raw_fio}"


def _collapse_loads(loads: List[TeacherLoad]):
    by_teacher = {}
    for load in loads:
        by_teacher.setdefault(load.teacher_id, []).append(load)
    return by_teacher


def _pick_best_teacher_load(loads: List[TeacherLoad]):
    if not loads:
        return None, None
    by_teacher = _collapse_loads(loads)
    if len(by_teacher) == 1:
        teacher_loads = next(iter(by_teacher.values()))
        best = sorted(teacher_loads, key=lambda x: ((x.hours or 0), x.id), reverse=True)[0]
        return best, None
    return None, "Найдено несколько учителей"


def find_teacher_for_row(
    row: dict,
    child=None,
    subject=None,
    academic_year_id: Optional[int] = None,
    department=None,
    teacher_binding_mode: str = "auto",
    selected_teacher_id: Optional[int] = None,
    selected_teacher_ids: Optional[list] = None,
):
    selected_teacher_ids = [int(x) for x in (selected_teacher_ids or []) if str(x).isdigit()]

    if teacher_binding_mode == "none":
        return None, None
    if teacher_binding_mode == "fixed" and selected_teacher_id:
        load = TeacherLoad.query.filter_by(
            teacher_id=selected_teacher_id,
            academic_year_id=academic_year_id,
            is_archived=False,
        )
        if subject and subject.education_activity_id:
            load = load.filter(
                TeacherLoad.education_activity_id
                == subject.education_activity_id
            )
        if department:
            load = load.filter((TeacherLoad.department_id == department.id) | (TeacherLoad.department_id.is_(None)))
        best = load.order_by(TeacherLoad.hours.desc(), TeacherLoad.id.desc()).first()
        return best, None

    if not child or not subject:
        return None, "Не удалось определить учителя"

    school_class = resolve_school_class_for_child(child.id, academic_year_id=academic_year_id)
    class_name = school_class.name if school_class else normalize_text(_get_row_value(row, "class_study", "class_study_text", default=""))
    class_token = _canon_class(class_name)
    grade = school_class.grade if school_class and school_class.grade is not None else parse_grade(class_name)
    class_letter = school_class.letter if school_class else parse_class_parts(class_name)[1]

    q = TeacherLoad.query.filter(TeacherLoad.is_archived.is_(False))
    if academic_year_id:
        q = q.filter((TeacherLoad.academic_year_id == academic_year_id) | (TeacherLoad.academic_year_id.is_(None)))

    raw_subject = _get_row_value(row, "subject", "subject_name", "raw_subject", default="")
    mapping = _find_mapping_for_subject_name(str(raw_subject or ""), grade=grade)
    activity_ids = (
        [subject.education_activity_id]
        if subject and subject.education_activity_id
        else []
    )
    subject_names = [subject.name] if subject and subject.name else []
    if mapping:
        for activity_id in _mapping_activity_ids(mapping):
            if activity_id not in activity_ids:
                activity_ids.append(activity_id)
        for item in _subject_names_for_mapping(mapping):
            if item not in subject_names:
                subject_names.append(item)
        if not department and getattr(mapping, "department", None):
            department = mapping.department

    filters = []
    if activity_ids:
        filters.append(TeacherLoad.education_activity_id.in_(activity_ids))
    lowered_names = [normalize_text(name).lower() for name in subject_names if name]
    for name in lowered_names:
        filters.append(func.lower(func.coalesce(TeacherLoad.subject_name, "")) == name)
        filters.append(func.lower(func.coalesce(TeacherLoad.subject_name, "")).like(f"%{name}%"))
    if filters:
        q = q.filter(filters[0]) if len(filters) == 1 else q.filter(db.or_(*filters))
    if department:
        q = q.filter((TeacherLoad.department_id == department.id) | (TeacherLoad.department_id.is_(None)))
    if teacher_binding_mode == "limited_auto" and selected_teacher_ids:
        q = q.filter(TeacherLoad.teacher_id.in_(selected_teacher_ids))

    candidates = q.order_by(TeacherLoad.hours.desc(), TeacherLoad.id.desc()).all()
    if not candidates:
        return None, "Не найден предмет нагрузки"

    exact_class = [x for x in candidates if _canon_class(x.class_name) == class_token and class_token]
    best, error = _pick_best_teacher_load(exact_class)
    if best:
        return best, None
    if exact_class and error:
        return None, "Найдено несколько учителей для класса"

    if grade is not None:
        grade_candidates = [x for x in candidates if x.grade == grade]
        if class_letter:
            letter_candidates = [x for x in grade_candidates if _canon_class(x.class_name) == _canon_class(f"{grade}{class_letter}") or class_letter.lower() in normalize_text(x.class_name).lower()]
            best, error = _pick_best_teacher_load(letter_candidates)
            if best:
                return best, None
            if letter_candidates and error:
                return None, "Найдено несколько учителей для класса"
        best, error = _pick_best_teacher_load(grade_candidates)
        if best:
            return best, None
        if grade_candidates and error:
            return None, "Найдено несколько учителей для параллели"

    best, error = _pick_best_teacher_load(candidates)
    if best:
        return best, None
    if error:
        return None, error
    return None, "Учитель не найден"


def find_department_for_row(row: dict, teacher_load=None, subject=None, subject_department=None, selected_department_id=None):
    if teacher_load and teacher_load.department:
        return teacher_load.department, None
    if teacher_load and teacher_load.department_id:
        dep = Department.query.get(teacher_load.department_id)
        if dep:
            return dep, None
    if selected_department_id:
        dep = Department.query.get(selected_department_id)
        if dep:
            return dep, None
    if subject_department:
        return subject_department, None
    if subject:
        ds = DepartmentSubject.query.filter_by(
            education_activity_id=subject.education_activity_id,
        ).first()
        if ds and ds.department:
            return ds.department, None
    return None, "Кафедра не определена"
