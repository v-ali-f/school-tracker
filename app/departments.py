from __future__ import annotations

from typing import Optional

import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for, abort
from flask_login import current_user, login_required
from openpyxl import load_workbook
from sqlalchemy import func

from . import db
from .models import (
    Building,
    ControlWork,
    ControlWorkAssignment,
    ControlWorkResult,
    AcademicYear,
    Department,
    DepartmentLeader,
    DepartmentSubject,
    Subject,
    TeacherCourse,
    TeacherLoad,
    TeacherMckoResult,
    User,
)
from .permissions import has_role, is_admin, METHODIST, TEACHER, CLASS_TEACHER
from .services.olympiad_stats_service import department_stats as olympiad_department_stats, dashboard_stats as olympiad_dashboard_stats


departments_bp = Blueprint("departments", __name__, url_prefix="/departments")


DEFAULT_DEPARTMENTS = [
    {
        "name": "Кафедра учителей начальных классов",
        "code": "primary",
        "subject_names": [],
        "description": "Автоподбор по нагрузке 1–4 классов, кроме физической культуры и музыки.",
    },
    {
        "name": "Кафедра учителей физической культуры и спорта",
        "code": "sport",
        "subject_names": ["Физическая культура", "Физкультура", "Спорт"],
    },
    {
        "name": "Кафедра учителей естественно-научного цикла",
        "code": "science",
        "subject_names": ["География", "Физика", "Химия", "Биология"],
    },
    {
        "name": "Кафедра математического образования",
        "code": "math",
        "subject_names": [
            "Математика",
            "Алгебра",
            "Геометрия",
            "Вероятность и статистика",
            "Алгебра и начала математического анализа",
            "Информатика",
        ],
    },
    {
        "name": "Кафедра словесности",
        "code": "philology",
        "subject_names": ["Русский язык", "Литература"],
        "description": "Для 5–11 классов.",
    },
    {
        "name": "Кафедра иностранного языка",
        "code": "foreign_language",
        "subject_names": [
            "Английский язык",
            "Немецкий язык",
            "Французский язык",
            "Испанский язык",
            "Китайский язык",
            "Иностранный язык",
        ],
    },
    {
        "name": "Кафедра эстетического образования",
        "code": "art",
        "subject_names": ["Изобразительное искусство", "ИЗО", "Труд", "Технология", "Музыка"],
    },
    {
        "name": "Кафедра общественных наук",
        "code": "social_science",
        "subject_names": ["История", "Обществознание"],
    },
]

PRIMARY_EXCLUDED = {"физическая культура", "физкультура", "музыка"}


def _normalize_subject_name(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def _extract_grade_from_class_text(class_text: Optional[str]):
    if not class_text:
        return None
    m = re.search(r"(?<!\d)(1[01]|[1-9])(?=\D|$)", str(class_text))
    return int(m.group(1)) if m else None


def _ensure_default_departments():
    changed = False
    for item in DEFAULT_DEPARTMENTS:
        dep = Department.query.filter_by(code=item["code"]).first()
        if not dep:
            dep = Department(name=item["name"], code=item["code"], description=item.get("description"))
            db.session.add(dep)
            db.session.flush()
            changed = True
        else:
            if not dep.name:
                dep.name = item["name"]
                changed = True
            if item.get("description") and not dep.description:
                dep.description = item.get("description")
                changed = True
        for subject_name in item.get("subject_names", []):
            subject = Subject.query.filter(func.lower(Subject.name) == subject_name.lower()).first()
            if not subject:
                subject = Subject(name=subject_name)
                db.session.add(subject)
                db.session.flush()
                changed = True
            exists = DepartmentSubject.query.filter_by(department_id=dep.id, subject_id=subject.id).first()
            if not exists:
                db.session.add(DepartmentSubject(department_id=dep.id, subject_id=subject.id))
                changed = True
    if changed:
        db.session.commit()


def _department_allowed(dep: Department) -> bool:
    if is_admin(current_user):
        return True
    if current_user.role == METHODIST:
        return DepartmentLeader.query.filter_by(department_id=dep.id, user_id=current_user.id).first() is not None
    if current_user.role in {TEACHER, CLASS_TEACHER}:
        return True
    return False


def _load_departments_for_user():
    _ensure_default_departments()
    deps = Department.query.order_by(Department.name.asc()).all()
    if is_admin(current_user):
        return deps
    if current_user.role == METHODIST:
        dep_ids = [x.department_id for x in DepartmentLeader.query.filter_by(user_id=current_user.id).all()]
        return [d for d in deps if d.id in dep_ids]
    return deps


def _subject_ids_for_department(dep: Department):
    return [link.subject_id for link in dep.subject_links]


def _teacher_ids_for_department(dep: Department, building_id=None):
    loads = TeacherLoad.query.filter_by(department_id=dep.id)
    if building_id:
        loads = loads.filter_by(building_id=building_id)
    return sorted({x.teacher_id for x in loads if x.teacher_id})


def _department_for_load(subject_name: Optional[str], grade: Optional[int]):
    normalized = _normalize_subject_name(subject_name)
    if grade and 1 <= grade <= 4 and normalized not in PRIMARY_EXCLUDED:
        return Department.query.filter_by(code="primary").first()

    for dep in Department.query.order_by(Department.id.asc()).all():
        if dep.code == "primary":
            continue
        names = {_normalize_subject_name(link.subject.name if link.subject else "") for link in dep.subject_links}
        if normalized in names:
            if dep.code == "philology" and grade and grade < 5:
                continue
            return dep
    return None


def _rebind_all_loads_to_departments():
    for load in TeacherLoad.query.all():
        dep = _department_for_load(load.subject_name, load.grade)
        load.department_id = dep.id if dep else None
    db.session.commit()


def _parse_excel_loads(file_storage):
    wb = load_workbook(file_storage, data_only=True)
    created = 0
    updated = 0
    skipped = 0

    current_year = AcademicYear.query.filter_by(is_current=True).first()
    retention_until = None
    if current_year and current_year.end_date:
        try:
            retention_until = current_year.end_date.replace(year=current_year.end_date.year + 7)
        except Exception:
            retention_until = None

    TeacherLoad.query.delete()
    db.session.flush()

    buildings = {b.name.lower(): b for b in Building.query.all() if b.name}
    users = {u.fio.lower(): u for u in User.query.all() if u.fio}
    subjects = {s.name.lower(): s for s in Subject.query.all()}

    for ws in wb.worksheets:
        building_name = re.sub(r"^Учителя\s+", "", ws.title or "").strip() or None
        building = buildings.get((building_name or "").lower())
        current_teacher = None
        teacher_total = None

        for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if row_idx == 1:
                continue
            first = row[0] if len(row) > 0 else None
            class_text = row[1] if len(row) > 1 else None
            subject_name = row[2] if len(row) > 2 else None
            group_name = row[3] if len(row) > 3 else None
            hours = row[4] if len(row) > 4 else None

            if isinstance(first, str) and first.strip() and not subject_name:
                fio = first.strip()
                current_teacher = users.get(fio.lower())
                if not current_teacher:
                    fio_parts = fio.split()
                    username = fio.lower().replace(" ", ".")
                    current_teacher = User(
                        username=username[:120],
                        last_name=fio_parts[0] if len(fio_parts) > 0 else fio,
                        first_name=fio_parts[1] if len(fio_parts) > 1 else "",
                        middle_name=" ".join(fio_parts[2:]) if len(fio_parts) > 2 else None,
                        role="TEACHER",
                    )
                    current_teacher.set_password("123456")
                    db.session.add(current_teacher)
                    db.session.flush()
                    users[fio.lower()] = current_teacher
                    created += 1
                teacher_total = float(hours or 0) if hours not in (None, "") else None
                continue

            if not current_teacher:
                skipped += 1
                continue
            if first in (None, ""):
                continue

            subject_text = str(subject_name or "").strip()
            if not subject_text:
                skipped += 1
                continue
            subject = subjects.get(subject_text.lower())
            if not subject:
                subject = Subject(name=subject_text)
                db.session.add(subject)
                db.session.flush()
                subjects[subject_text.lower()] = subject
                updated += 1

            class_text = str(class_text or "").strip() or None
            group_text = str(group_name or "").strip() or None
            grade = _extract_grade_from_class_text(class_text)
            is_meta_group = bool(class_text and any(sep in class_text for sep in [",", ";", "/", "+"]))
            is_whole_class = (group_text or "").strip().lower() == "весь класс"
            load = TeacherLoad(
                teacher_id=current_teacher.id,
                subject_id=subject.id,
                academic_year_id=current_year.id if current_year else None,
                subject_name=subject.name,
                class_name=class_text,
                group_name=group_text,
                hours=float(hours or 0),
                grade=grade,
                building_id=building.id if building else None,
                building_name=building_name,
                source_sheet=ws.title,
                row_number=row_idx,
                is_whole_class=is_whole_class,
                is_meta_group=is_meta_group,
                teacher_total_hours=teacher_total,
                retention_until=retention_until,
            )
            db.session.add(load)
            created += 1

    db.session.commit()
    _rebind_all_loads_to_departments()
    return created, updated, skipped


def _control_work_stats(dep: Department, teacher_id=None, academic_year_id=None):
    subject_ids = _subject_ids_for_department(dep)
    if not subject_ids:
        return {
            "total_results": 0,
            "avg_percent": None,
            "by_subject": [],
            "by_teacher": [],
        }

    results_q = (
        db.session.query(ControlWorkResult, ControlWork, Subject, ControlWorkAssignment, User)
        .join(ControlWork, ControlWork.id == ControlWorkResult.control_work_id)
        .join(Subject, Subject.id == ControlWork.subject_id)
        .outerjoin(
            ControlWorkAssignment,
            db.and_(
                ControlWorkAssignment.control_work_id == ControlWorkResult.control_work_id,
                ControlWorkAssignment.school_class_id == ControlWorkResult.school_class_id,
            ),
        )
        .outerjoin(User, User.id == ControlWorkAssignment.teacher_id)
        .filter(ControlWork.subject_id.in_(subject_ids))
    )
    if teacher_id:
        results_q = results_q.filter(ControlWorkAssignment.teacher_id == teacher_id)
    if academic_year_id:
        results_q = results_q.filter(ControlWorkResult.academic_year_id == academic_year_id)

    rows = results_q.all()
    percents = [r.ControlWorkResult.percent for r in rows if r.ControlWorkResult.percent is not None]
    by_subject = defaultdict(list)
    by_teacher = defaultdict(list)

    for row in rows:
        percent = row.ControlWorkResult.percent
        if percent is None:
            continue
        subj_name = row.Subject.name if row.Subject else "—"
        by_subject[subj_name].append(percent)
        teacher_name = row.User.fio if row.User else "Не указан"
        by_teacher[teacher_name].append(percent)

    subject_stats = [
        {"name": name, "avg": round(sum(vals) / len(vals), 1), "count": len(vals)}
        for name, vals in sorted(by_subject.items())
    ]
    teacher_stats = [
        {"name": name, "avg": round(sum(vals) / len(vals), 1), "count": len(vals)}
        for name, vals in sorted(by_teacher.items())
    ]
    return {
        "total_results": len(percents),
        "avg_percent": round(sum(percents) / len(percents), 1) if percents else None,
        "by_subject": subject_stats,
        "by_teacher": teacher_stats,
    }


def _teacher_scope_user_id():
    teacher_id = request.args.get("teacher_id", type=int)
    if is_admin(current_user) or current_user.role == METHODIST:
        return teacher_id
    return current_user.id


@departments_bp.before_request
def _bootstrap_departments():
    _ensure_default_departments()


@departments_bp.route("/")
@login_required
def index():
    deps = _load_departments_for_user()
    return render_template("departments/index.html", departments=deps)


@departments_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if not is_admin(current_user):
        abort(403)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        code = re.sub(r"[^a-z0-9_]+", "_", (request.form.get("code") or name).strip().lower()).strip("_")
        if not name:
            flash("Укажите название кафедры.", "danger")
            return redirect(url_for("departments.settings"))
        if Department.query.filter(db.func.lower(Department.name) == name.lower()).first():
            flash("Такая кафедра уже существует.", "warning")
            return redirect(url_for("departments.settings"))
        dep = Department(name=name, code=code or None, description=(request.form.get("description") or "").strip() or None)
        db.session.add(dep)
        db.session.commit()
        flash("Кафедра создана.", "success")
        return redirect(url_for("departments.settings"))

    departments = Department.query.order_by(Department.name.asc()).all()
    users = User.query.order_by(User.last_name.asc(), User.first_name.asc()).all()
    subjects = Subject.query.order_by(Subject.name.asc()).all()
    buildings = Building.query.order_by(Building.name.asc()).all()
    return render_template("departments/settings.html", departments=departments, users=users, subjects=subjects, buildings=buildings)


@departments_bp.route("/settings/<int:department_id>/update", methods=["POST"])
@login_required
def settings_update(department_id):
    if not is_admin(current_user):
        abort(403)
    dep = Department.query.get_or_404(department_id)
    dep.name = (request.form.get("name") or dep.name).strip()
    dep.description = (request.form.get("description") or "").strip() or None
    selected_subject_ids = {int(x) for x in request.form.getlist("subject_ids") if str(x).isdigit()}
    existing = {x.subject_id for x in dep.subject_links}
    for link in list(dep.subject_links):
        if link.subject_id not in selected_subject_ids:
            db.session.delete(link)
    for subject_id in selected_subject_ids - existing:
        db.session.add(DepartmentSubject(department_id=dep.id, subject_id=subject_id))
    db.session.commit()
    _rebind_all_loads_to_departments()
    flash("Настройки кафедры сохранены.", "success")
    return redirect(url_for("departments.settings"))


@departments_bp.route("/settings/<int:department_id>/leader/add", methods=["POST"])
@login_required
def add_leader(department_id):
    if not is_admin(current_user):
        abort(403)
    dep = Department.query.get_or_404(department_id)
    selected_user_ids = []
    for raw in request.form.getlist("user_ids"):
        try:
            value = int(raw)
        except Exception:
            continue
        if value not in selected_user_ids:
            selected_user_ids.append(value)
    building_id = request.form.get("building_id", type=int)
    if not selected_user_ids:
        flash("Выберите хотя бы одного руководителя кафедры.", "danger")
        return redirect(url_for("departments.settings"))

    added = 0
    skipped = 0
    for user_id in selected_user_ids:
        exists = DepartmentLeader.query.filter_by(department_id=dep.id, user_id=user_id, building_id=building_id).first()
        if exists:
            skipped += 1
            continue
        db.session.add(DepartmentLeader(department_id=dep.id, user_id=user_id, building_id=building_id))
        user = User.query.get(user_id)
        if user and user.role != "ADMIN":
            user.role = METHODIST
        added += 1

    db.session.commit()
    if added and skipped:
        flash("Руководители кафедры назначены. Часть уже была добавлена ранее.", "success")
    elif added:
        flash("Руководители кафедры назначены.", "success")
    else:
        flash("Все выбранные руководители уже были добавлены.", "warning")
    return redirect(url_for("departments.settings"))


@departments_bp.route("/settings/leader/<int:leader_id>/delete", methods=["POST"])
@login_required
def delete_leader(leader_id):
    if not is_admin(current_user):
        abort(403)
    leader = DepartmentLeader.query.get_or_404(leader_id)
    db.session.delete(leader)
    db.session.commit()
    flash("Руководитель кафедры удалён.", "success")
    return redirect(url_for("departments.settings"))


@departments_bp.route("/loads", methods=["GET", "POST"])
@login_required
def loads():
    if request.method == "POST":
        if not is_admin(current_user):
            abort(403)
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Выберите Excel-файл нагрузки.", "danger")
            return redirect(url_for("departments.loads"))
        created, updated, skipped = _parse_excel_loads(f)
        flash(f"Нагрузка импортирована. Строк обработано: {created}, новых предметов: {updated}, пропущено: {skipped}.", "success")
        return redirect(url_for("departments.loads"))

    q = (request.args.get("q") or "").strip().lower()
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    academic_year_id = request.args.get("academic_year_id", type=int) or (current_year.id if current_year else None)
    department_id = request.args.get("department_id", type=int)
    subject_id = request.args.get("subject_id", type=int)
    teacher_id = request.args.get("teacher_id", type=int)

    query = TeacherLoad.query
    teacher_view_only = current_user.role in {TEACHER, CLASS_TEACHER}
    if teacher_view_only:
        teacher_id = current_user.id
    if academic_year_id:
        query = query.filter(db.or_(TeacherLoad.academic_year_id == academic_year_id, TeacherLoad.academic_year_id.is_(None)))
    if department_id:
        query = query.filter_by(department_id=department_id)
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    if teacher_id:
        query = query.filter_by(teacher_id=teacher_id)
    if q:
        query = query.join(User, User.id == TeacherLoad.teacher_id).filter(
            db.or_(
                func.lower(TeacherLoad.subject_name).contains(q),
                func.lower(TeacherLoad.class_name).contains(q),
                func.lower(User.last_name + ' ' + func.coalesce(User.first_name, '') + ' ' + func.coalesce(User.middle_name, '')).contains(q),
            )
        )
    rows = query.order_by(TeacherLoad.subject_name.asc(), TeacherLoad.class_name.asc()).all()

    teacher_hours = defaultdict(float)
    for item in rows:
        if item.teacher:
            teacher_hours[item.teacher.fio] += float(item.hours or 0)

    olympiad_stats = {"total_results": 0, "unique_children": 0, "winners": 0, "prizers": 0, "by_subject": [], "by_teacher": []}

    return render_template(
        "departments/loads.html",
        rows=rows,
        departments=Department.query.order_by(Department.name.asc()).all(),
        subjects=Subject.query.order_by(Subject.name.asc()).all(),
        teachers=([current_user] if current_user.role in {TEACHER, CLASS_TEACHER} else User.query.order_by(User.last_name.asc(), User.first_name.asc()).all()),
        teacher_view_only=teacher_view_only,
        teacher_hours=sorted(teacher_hours.items()),
        department_id=department_id,
        subject_id=subject_id,
        teacher_id=teacher_id,
        q=q,
        buildings=Building.query.order_by(Building.name.asc()).all(),
        years=years,
        academic_year_id=academic_year_id,
        olympiad_stats=olympiad_stats,
    )


@departments_bp.route("/loads/new", methods=["POST"])
@login_required
def load_new():
    if not is_admin(current_user):
        abort(403)
    teacher_id = request.form.get("teacher_id", type=int)
    subject_id = request.form.get("subject_id", type=int)
    class_name = (request.form.get("class_name") or "").strip() or None
    group_name = (request.form.get("group_name") or "").strip() or None
    hours = request.form.get("hours", type=float) or 0
    building_id = request.form.get("building_id", type=int)
    teacher = User.query.get_or_404(teacher_id)
    subject = Subject.query.get_or_404(subject_id)
    grade = _extract_grade_from_class_text(class_name)
    dep = _department_for_load(subject.name, grade)
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    retention_until = None
    if current_year and current_year.end_date:
        try:
            retention_until = current_year.end_date.replace(year=current_year.end_date.year + 7)
        except Exception:
            retention_until = None
    db.session.add(TeacherLoad(
        teacher_id=teacher.id,
        subject_id=subject.id,
        academic_year_id=current_year.id if current_year else None,
        subject_name=subject.name,
        class_name=class_name,
        group_name=group_name,
        hours=hours,
        grade=grade,
        building_id=building_id,
        building_name=Building.query.get(building_id).name if building_id and Building.query.get(building_id) else None,
        is_whole_class=(group_name or "").strip().lower() == "весь класс",
        is_meta_group=bool(class_name and any(sep in class_name for sep in [",", ";", "/", "+"])),
        department_id=dep.id if dep else None,
        retention_until=retention_until,
    ))
    db.session.commit()
    flash("Нагрузка добавлена.", "success")
    return redirect(url_for("departments.loads"))


@departments_bp.route("/loads/<int:load_id>/update", methods=["POST"])
@login_required
def load_update(load_id):
    if not is_admin(current_user):
        abort(403)
    load = TeacherLoad.query.get_or_404(load_id)
    load.class_name = (request.form.get("class_name") or "").strip() or None
    load.group_name = (request.form.get("group_name") or "").strip() or None
    load.hours = request.form.get("hours", type=float) or 0
    grade = _extract_grade_from_class_text(load.class_name)
    load.grade = grade
    dep = _department_for_load(load.subject_name, grade)
    load.department_id = dep.id if dep else None
    db.session.commit()
    flash("Нагрузка обновлена.", "success")
    return redirect(url_for("departments.loads"))


@departments_bp.route("/loads/<int:load_id>/delete", methods=["POST"])
@login_required
def load_delete(load_id):
    if not is_admin(current_user):
        abort(403)
    load = TeacherLoad.query.get_or_404(load_id)
    db.session.delete(load)
    db.session.commit()
    flash("Строка нагрузки удалена.", "success")
    return redirect(url_for("departments.loads"))


@departments_bp.route("/summary")
@login_required
def summary():
    deps = _load_departments_for_user()
    selected_dep_id = request.args.get("department_id", type=int)
    selected_teacher_id = _teacher_scope_user_id()
    if current_user.role in {TEACHER, CLASS_TEACHER}:
        deps = [d for d in deps if TeacherLoad.query.filter_by(department_id=d.id, teacher_id=current_user.id).first()]

    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    academic_year_id = request.args.get("academic_year_id", type=int) or (current_year.id if current_year else None)
    dep = None
    if selected_dep_id:
        dep = Department.query.get_or_404(selected_dep_id)
        if not _department_allowed(dep):
            abort(403)
    elif deps:
        dep = deps[0]

    teacher_rows = []
    stats = {"total_results": 0, "avg_percent": None, "by_subject": [], "by_teacher": []}
    olympiad_stats = {"total_results": 0, "unique_children": 0, "winners": 0, "prizers": 0, "by_subject": [], "by_teacher": []}
    teacher_ids = []
    mcko_rows = []
    course_rows = []
    building_id = request.args.get("building_id", type=int)

    if dep:
        teacher_ids_q = TeacherLoad.query.filter_by(department_id=dep.id)
        if building_id:
            teacher_ids_q = teacher_ids_q.filter_by(building_id=building_id)
        if academic_year_id:
            teacher_ids_q = teacher_ids_q.filter(db.or_(TeacherLoad.academic_year_id == academic_year_id, TeacherLoad.academic_year_id.is_(None)))
        teacher_ids = sorted({x.teacher_id for x in teacher_ids_q.all() if x.teacher_id})
        if current_user.role in {TEACHER, CLASS_TEACHER}:
            teacher_ids = [x for x in teacher_ids if x == current_user.id]
        teacher_rows = User.query.filter(User.id.in_(teacher_ids)).order_by(User.last_name.asc(), User.first_name.asc()).all() if teacher_ids else []
        stats = _control_work_stats(dep, teacher_id=selected_teacher_id, academic_year_id=academic_year_id)
        mcko_q = TeacherMckoResult.query.filter(TeacherMckoResult.teacher_id.in_(teacher_ids)) if teacher_ids else TeacherMckoResult.query.filter(db.text("0=1"))
        if academic_year_id:
            mcko_q = mcko_q.filter(db.or_(TeacherMckoResult.academic_year_id == academic_year_id, TeacherMckoResult.academic_year_id.is_(None)))
        if selected_teacher_id:
            mcko_q = mcko_q.filter_by(teacher_id=selected_teacher_id)
        mcko_rows = mcko_q.order_by(TeacherMckoResult.passed_at.desc()).all()
        course_q = TeacherCourse.query.filter(TeacherCourse.teacher_id.in_(teacher_ids)) if teacher_ids else TeacherCourse.query.filter(db.text("0=1"))
        if academic_year_id:
            course_q = course_q.filter(db.or_(TeacherCourse.academic_year_id == academic_year_id, TeacherCourse.academic_year_id.is_(None)))
        if selected_teacher_id:
            course_q = course_q.filter_by(teacher_id=selected_teacher_id)
        course_rows = course_q.order_by(TeacherCourse.start_date.desc().nullslast(), TeacherCourse.created_at.desc()).all()
        olympiad_stats = olympiad_department_stats(academic_year_id=academic_year_id, department_id=dep.id)

    return render_template(
        "departments/summary.html",
        departments=deps,
        dep=dep,
        teachers=teacher_rows,
        all_teachers=User.query.order_by(User.last_name.asc(), User.first_name.asc()).all(),
        selected_teacher_id=selected_teacher_id,
        stats=stats,
        mcko_rows=mcko_rows,
        course_rows=course_rows,
        buildings=Building.query.order_by(Building.name.asc()).all(),
        building_id=building_id,
        years=years,
        academic_year_id=academic_year_id,
        olympiad_stats=olympiad_stats,
    )


@departments_bp.route("/teacher/mcko/add", methods=["POST"])
@login_required
def add_mcko():
    teacher_id = request.form.get("teacher_id", type=int) or current_user.id
    if not (is_admin(current_user) or current_user.role == METHODIST or teacher_id == current_user.id):
        abort(403)
    passed_at_raw = request.form.get("passed_at") or None
    passed_at = datetime.strptime(passed_at_raw, "%Y-%m-%d").date() if passed_at_raw else None
    subject_id = request.form.get("subject_id", type=int)
    level = (request.form.get("level") or "").strip() or None
    result_text = (request.form.get("result_text") or "").strip() or None
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    retention_until = None
    if current_year and current_year.end_date:
        try:
            retention_until = current_year.end_date.replace(year=current_year.end_date.year + 7)
        except Exception:
            retention_until = None
    db.session.add(TeacherMckoResult(
        teacher_id=teacher_id,
        subject_id=subject_id,
        academic_year_id=current_year.id if current_year else None,
        passed_at=passed_at,
        expires_at=(passed_at + timedelta(days=365*3)) if passed_at else None,
        level=level,
        result_text=result_text,
        retention_until=retention_until,
    ))
    db.session.commit()
    flash("Результат МЦКО сохранён.", "success")
    return redirect(url_for("departments.summary", department_id=request.form.get("department_id"), teacher_id=teacher_id))


@departments_bp.route("/teacher/course/add", methods=["POST"])
@login_required
def add_course():
    teacher_id = request.form.get("teacher_id", type=int) or current_user.id
    if not (is_admin(current_user) or current_user.role == METHODIST or teacher_id == current_user.id):
        abort(403)
    start_date_raw = request.form.get("start_date") or None
    end_date_raw = request.form.get("end_date") or None
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    retention_until = None
    if current_year and current_year.end_date:
        try:
            retention_until = current_year.end_date.replace(year=current_year.end_date.year + 7)
        except Exception:
            retention_until = None
    db.session.add(TeacherCourse(
        teacher_id=teacher_id,
        academic_year_id=current_year.id if current_year else None,
        title=(request.form.get("title") or "").strip(),
        provider=(request.form.get("provider") or "").strip() or None,
        hours=request.form.get("hours", type=float),
        start_date=datetime.strptime(start_date_raw, "%Y-%m-%d").date() if start_date_raw else None,
        end_date=datetime.strptime(end_date_raw, "%Y-%m-%d").date() if end_date_raw else None,
        notes=(request.form.get("notes") or "").strip() or None,
        retention_until=retention_until,
    ))
    db.session.commit()
    flash("Курс повышения квалификации сохранён.", "success")
    return redirect(url_for("departments.summary", department_id=request.form.get("department_id"), teacher_id=teacher_id))

