from __future__ import annotations

import re
from typing import List, Optional, Tuple

from sqlalchemy import func

from ..models import (
    Child,
    ChildEnrollment,
    Department,
    DepartmentSubject,
    OlympiadSubjectMapping,
    SchoolClass,
    Subject,
    TeacherLoad,
)


def normalize_text(value) -> str:
    return " ".join(str(value or "").replace("ё", "е").replace("Ё", "Е").split()).strip()


def _norm_lower(value: str) -> str:
    return normalize_text(value).lower()


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


def _subject_by_name(subject_name: str):
    if not subject_name:
        return None, None
    norm = _norm_lower(subject_name)
    mapping = OlympiadSubjectMapping.query.filter(
        OlympiadSubjectMapping.is_active.is_(True),
        func.lower(OlympiadSubjectMapping.olympiad_subject_name) == norm,
    ).first()
    if mapping and mapping.subject:
        return mapping.subject, mapping.department

    exact = Subject.query.filter(func.lower(Subject.name) == norm).first()
    if exact:
        dep_link = DepartmentSubject.query.filter_by(subject_id=exact.id).first()
        return exact, dep_link.department if dep_link else None

    partial = Subject.query.filter(func.lower(Subject.name).like(f"%{norm}%")).first()
    if partial:
        dep_link = DepartmentSubject.query.filter_by(subject_id=partial.id).first()
        return partial, dep_link.department if dep_link else None

    for subj in Subject.query.order_by(Subject.name.asc()).all():
        subj_norm = _norm_lower(subj.name)
        if subj_norm in norm or norm in subj_norm:
            dep_link = DepartmentSubject.query.filter_by(subject_id=subj.id).first()
            return subj, dep_link.department if dep_link else None
    return None, None


def find_subject_for_row(row: dict, manual_subject_id: Optional[int] = None):
    if manual_subject_id:
        subject = Subject.query.get(manual_subject_id)
        dep_link = DepartmentSubject.query.filter_by(subject_id=manual_subject_id).first() if subject else None
        return subject, dep_link.department if dep_link else None, None
    raw_subject = _get_row_value(row, "subject", "subject_name", "raw_subject", default="")
    subject, department = _subject_by_name(str(raw_subject or ""))
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
        if subject:
            load = load.filter((TeacherLoad.subject_id == subject.id) | (func.lower(func.coalesce(TeacherLoad.subject_name, '')) == subject.name.lower()))
        if department:
            load = load.filter((TeacherLoad.department_id == department.id) | (TeacherLoad.department_id.is_(None)))
        best = load.order_by(TeacherLoad.hours.desc(), TeacherLoad.id.desc()).first()
        return best, None

    if not child or not subject:
        return None, "Не удалось определить учителя"

    school_class = resolve_school_class_for_child(child.id, academic_year_id=academic_year_id)
    class_name = school_class.name if school_class else normalize_text(_get_row_value(row, "class_study", "class_study_text", default=""))
    grade = school_class.grade if school_class and school_class.grade is not None else parse_grade(class_name)
    class_letter = school_class.letter if school_class else parse_class_parts(class_name)[1]

    q = TeacherLoad.query.filter(TeacherLoad.is_archived.is_(False))
    if academic_year_id:
        q = q.filter((TeacherLoad.academic_year_id == academic_year_id) | (TeacherLoad.academic_year_id.is_(None)))
    q = q.filter(
        (TeacherLoad.subject_id == subject.id)
        | (func.lower(func.coalesce(TeacherLoad.subject_name, "")) == subject.name.lower())
        | (func.lower(func.coalesce(TeacherLoad.subject_name, "")).like(f"%{subject.name.lower()}%"))
    )
    if department:
        q = q.filter((TeacherLoad.department_id == department.id) | (TeacherLoad.department_id.is_(None)))
    if teacher_binding_mode == "limited_auto" and selected_teacher_ids:
        q = q.filter(TeacherLoad.teacher_id.in_(selected_teacher_ids))

    candidates = q.all()
    if school_class:
        exact_class = [x for x in candidates if normalize_text(x.class_name).lower() == normalize_text(class_name).lower()]
        if len(exact_class) == 1:
            return exact_class[0], None
        if len(exact_class) > 1:
            return None, "Найдено несколько учителей для класса"
    if grade is not None:
        grade_candidates = [x for x in candidates if x.grade == grade]
        if class_letter:
            letter_candidates = [x for x in grade_candidates if class_letter.lower() in normalize_text(x.class_name).lower()]
            if len(letter_candidates) == 1:
                return letter_candidates[0], None
            if len(letter_candidates) > 1:
                return None, "Найдено несколько учителей для параллели"
        if len(grade_candidates) == 1:
            return grade_candidates[0], None
        if len(grade_candidates) > 1:
            return None, "Найдено несколько учителей для параллели"
    if len(candidates) == 1:
        return candidates[0], None
    if candidates:
        return None, "Найдено несколько учителей"
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
        ds = DepartmentSubject.query.filter_by(subject_id=subject.id).first()
        if ds and ds.department:
            return ds.department, None
    return None, "Кафедра не определена"
