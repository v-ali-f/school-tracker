"""Professional development dashboard and staff course records."""

from collections import Counter, defaultdict
from datetime import date
from math import isfinite

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.core.extensions import db
from app.models import AcademicYear, StaffCourseImport, TeacherCourse, User
from app.permissions import has_any_role
from app.services.professional_development_service import (
    course_status, current_department_memberships, current_pedagogical_ids,
    current_preschool_teacher_ids, import_courses, imported_and_manual_courses, is_pedagogical,
    is_preschool_staff, normalize_fio, staff_overview, year_label,
)


professional_development_bp = Blueprint(
    "professional_development", __name__, url_prefix="/professional-development"
)


def _can_manage():
    return has_any_role("ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR", "METHODIST", "HR_SPECIALIST")


def _can_edit_for(user_id):
    return current_user.id == user_id or _can_manage()


def _course_record(kind, record_id):
    if kind == "imported":
        return db.session.get(StaffCourseImport, record_id)
    if kind == "manual":
        return db.session.get(TeacherCourse, record_id)
    abort(404)


def _course_form_values(kind):
    title = (request.form.get("title") or "").strip()
    provider = (request.form.get("provider") or "").strip()
    hours_raw = (request.form.get("hours") or "").strip().replace(",", ".")
    max_length = 512 if kind == "imported" else 255
    if not title or len(title) > max_length or len(provider) > max_length:
        raise ValueError("Проверьте название курса и организацию.")
    try:
        hours = float(hours_raw) if hours_raw else None
    except ValueError as exc:
        raise ValueError("Укажите число часов.") from exc
    if hours is not None and (not isfinite(hours) or hours <= 0 or hours > 10000):
        raise ValueError("Часы должны быть больше нуля и не более 10 000.")

    def parse_date(field):
        raw = (request.form.get(field) or "").strip()
        try:
            return date.fromisoformat(raw) if raw else None
        except ValueError as exc:
            raise ValueError("Проверьте даты курса.") from exc

    if kind == "imported":
        return dict(title=title, provider=provider, hours=hours,
                    completed_at=parse_date("completed_at"))
    start_date, end_date = parse_date("start_date"), parse_date("end_date")
    if start_date and end_date and end_date < start_date:
        raise ValueError("Дата окончания не может быть раньше даты начала.")
    notes = (request.form.get("notes") or "").strip()
    if len(notes) > 2000:
        raise ValueError("Примечание слишком длинное.")
    return dict(title=title, provider=provider, hours=hours,
                start_date=start_date, end_date=end_date, notes=notes)


def _course_return(teacher_id):
    if teacher_id == current_user.id:
        return redirect(url_for("professional_development.my"))
    return redirect(url_for("departments.teacher_profile", teacher_id=teacher_id))


def _active_staff():
    return (
        User.query.filter_by(is_active_user=True, employment_status="ACTIVE")
        .order_by(User.last_name, User.first_name, User.middle_name)
        .all()
    )


@professional_development_bp.get("/")
@login_required
def index():
    if not _can_manage():
        abort(403)
    users = [user for user in _active_staff() if user.last_name and user.first_name]
    by_user = imported_and_manual_courses([user.id for user in users])
    departments, memberships = current_department_memberships()
    preschool_group_ids = current_preschool_teacher_ids()
    departments_by_id = {item.id: item for item in departments}
    overview = staff_overview(users, by_user, pedagogical_ids=set(memberships))
    for row in overview:
        row["departments"] = tuple(
            departments_by_id[item_id] for item_id in sorted(memberships.get(row["user"].id, ()))
        )
        row["preschool"] = is_preschool_staff(
            row["user"], row["courses"], row["departments"], preschool_group_ids
        )
    department_filter = (request.args.get("department_id") or "").strip()
    if department_filter and department_filter != "none":
        if not department_filter.isdecimal() or int(department_filter) not in departments_by_id:
            abort(404)
        selected_department_id = int(department_filter)
        overview = [row for row in overview
                    if selected_department_id in memberships.get(row["user"].id, ())]
    elif department_filter == "none":
        overview = [row for row in overview if not row["departments"]]
    scope_filter = (request.args.get("scope") or "all").strip()
    if scope_filter not in {"all", "preschool", "other"}:
        scope_filter = "all"
    if scope_filter == "preschool":
        overview = [row for row in overview if row["preschool"]]
    elif scope_filter == "other":
        overview = [row for row in overview if not row["preschool"]]
    pedagogical = [row for row in overview if row["pedagogical"]]
    trained = sum(bool(row["count"]) for row in overview)
    covered = sum(row["status"]["code"] == "ok" for row in pedagogical)
    due = sum(row["status"]["code"] in {"due", "overdue"} for row in pedagogical)
    missing = sum(row["status"]["code"] == "no_data" for row in pedagogical)
    all_courses = [course for row in overview for course in row["courses"]]
    by_year = Counter()
    by_title = Counter()
    for course in all_courses:
        year = getattr(course, "source_year", None)
        if year is None:
            when = course.end_date or course.start_date
            if when:
                year = when.year if when.month >= 9 else when.year - 1
            elif course.academic_year and course.academic_year.start_date:
                year = course.academic_year.start_date.year
        if year:
            by_year[year] += 1
        by_title[course.title] += 1
    imported = StaffCourseImport.query.filter_by(is_archived=False).all()
    unmatched_names = {normalize_fio(fio=row.employee_name) for row in imported if not row.teacher_id}
    term = (request.args.get("q") or "").strip().casefold()
    status_filter = (request.args.get("status") or "").strip()
    if status_filter not in {"", "ok", "due", "overdue", "no_data"}:
        status_filter = ""
    entries = []
    for row in overview:
        if status_filter and row["status"]["code"] != status_filter:
            continue
        employee_match = term in (row["user"].fio or "").casefold()
        for course in row["courses"] or [None]:
            course_match = course is not None and any(
                term in (value or "").casefold()
                for value in (course.title, course.provider)
            )
            if not term or employee_match or course_match:
                entries.append({"staff": row, "course": course})
    previous_staff_id = None
    for entry in entries:
        staff_id = entry["staff"]["user"].id
        entry["first_for_staff"] = staff_id != previous_staff_id
        previous_staff_id = staff_id
    return render_template(
        "professional_development/index.html",
        overview=overview, entries=entries,
        totals={"staff": len(overview), "trained": trained,
                "trained_percent": round(100 * trained / len(overview)) if overview else 0,
                "pedagogical": len(pedagogical), "covered": covered,
                "covered_percent": round(100 * covered / len(pedagogical)) if pedagogical else 0,
                "due": due, "missing": missing, "courses": len(all_courses),
                "unmatched": len(unmatched_names)},
        years=[{"label": year_label(year), "count": count}
               for year, count in sorted(by_year.items())],
        top_courses=by_title.most_common(8),
        q=request.args.get("q", ""), status_filter=status_filter,
        departments=departments, department_filter=department_filter,
        scope_filter=scope_filter,
        workspace_page_title="Повышение квалификации",
        workspace_page_subtitle="Курсы сотрудников, охват и планирование обучения",
    )


@professional_development_bp.get("/my")
@login_required
def my():
    courses = imported_and_manual_courses([current_user.id]).get(current_user.id, [])
    status = course_status(courses)
    return render_template(
        "professional_development/my.html", courses=courses,
        status=status, pedagogical=is_pedagogical(current_user, courses, current_pedagogical_ids()),
        can_manage=_can_manage(),
        workspace_page_title="Мои курсы",
        workspace_page_subtitle="История повышения квалификации",
    )


@professional_development_bp.route("/course/new", methods=["GET", "POST"])
@login_required
def new_course():
    teacher_id = (request.values.get("teacher_id", type=int) or current_user.id) if _can_manage() else current_user.id
    teacher = db.session.get(User, teacher_id) if teacher_id else None
    if teacher is None or not _can_edit_for(teacher.id):
        abort(404 if teacher is None else 403)
    if request.method == "POST":
        try:
            values = _course_form_values("manual")
        except ValueError as exc:
            flash(str(exc), "danger")
        else:
            current_year = AcademicYear.query.filter_by(is_current=True).first()
            retention_until = None
            if current_year and current_year.end_date:
                try:
                    retention_until = current_year.end_date.replace(year=current_year.end_date.year + 7)
                except ValueError:
                    retention_until = current_year.end_date.replace(
                        year=current_year.end_date.year + 7, day=28
                    )
            row = TeacherCourse(
                teacher_id=teacher.id,
                academic_year_id=current_year.id if current_year else None,
                title=values["title"], provider=values["provider"] or None,
                hours=values["hours"], start_date=values["start_date"],
                end_date=values["end_date"], notes=values["notes"] or None,
                retention_until=retention_until,
            )
            db.session.add(row)
            db.session.commit()
            flash("Курс добавлен.", "success")
            return _course_return(teacher.id)
    return render_template(
        "professional_development/course_form.html", kind="manual", row=None,
        teacher=teacher, is_new=True, can_manage=_can_manage(),
        workspace_page_title="Добавить курс",
        workspace_page_subtitle=teacher.fio or teacher.username,
    )


@professional_development_bp.route("/course/<kind>/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
def edit_course(kind, record_id):
    row = _course_record(kind, record_id)
    if row is None or row.is_archived:
        abort(404)
    if row.teacher_id is None or not _can_edit_for(row.teacher_id):
        abort(403)
    if request.method == "POST":
        try:
            values = _course_form_values(kind)
        except ValueError as exc:
            flash(str(exc), "danger")
        else:
            if kind == "imported":
                row.title_override = values["title"] if values["title"] != row.source_title else None
                row.provider_override = (
                    values["provider"] if values["provider"] != (row.source_provider or "") else None
                )
                row.hours = values["hours"]
                row.completed_at = values["completed_at"]
            else:
                row.title = values["title"]
                row.provider = values["provider"] or None
                row.hours = values["hours"]
                row.start_date = values["start_date"]
                row.end_date = values["end_date"]
                row.notes = values["notes"] or None
            db.session.commit()
            flash("Изменения курса сохранены.", "success")
            return _course_return(row.teacher_id)
    return render_template(
        "professional_development/course_form.html", kind=kind, row=row,
        teacher=row.teacher, is_new=False, can_manage=_can_manage(),
        workspace_page_title="Редактировать курс",
        workspace_page_subtitle=row.teacher.fio or row.teacher.username,
    )


@professional_development_bp.post("/import")
@login_required
def upload():
    if not _can_manage():
        abort(403)
    files = [file for file in request.files.getlist("files") if file and file.filename]
    if not files or len(files) > 10:
        flash("Выберите от 1 до 10 файлов Excel.", "danger")
        return redirect(url_for("professional_development.index"))
    results = []
    try:
        for file in files:
            content = file.stream.read(16 * 1024 * 1024 + 1)
            results.append(import_courses(content, file.filename, commit=False))
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("professional_development.index"))
    for result in results:
        flash(
            f"{year_label(result['year'])}: {result['total']} курсов, "
            f"{result['linked']} привязано, {result['unlinked']} требуют проверки.",
            "success" if result["unlinked"] == 0 else "warning",
        )
    return redirect(url_for("professional_development.index"))


@professional_development_bp.get("/unmatched")
@login_required
def unmatched():
    if not _can_manage():
        abort(403)
    rows = StaffCourseImport.query.filter_by(teacher_id=None, is_archived=False).order_by(
        StaffCourseImport.employee_name, StaffCourseImport.source_year.desc()
    ).all()
    groups = defaultdict(list)
    for row in rows:
        groups[normalize_fio(fio=row.employee_name)].append(row)
    users = [user for user in _active_staff() if user.last_name and user.first_name]
    return render_template(
        "professional_development/unmatched.html",
        groups=list(groups.values()), users=users,
        workspace_page_title="Привязка курсов",
        workspace_page_subtitle="Проверьте сотрудников, которых не удалось найти однозначно",
    )


@professional_development_bp.post("/unmatched/link")
@login_required
def link():
    if not _can_manage():
        abort(403)
    name = normalize_fio(fio=request.form.get("employee_name"))
    user_id = request.form.get("user_id", type=int)
    user = db.session.get(User, user_id) if user_id else None
    if not name or user is None or not user.is_active_user:
        abort(400)
    rows = StaffCourseImport.query.filter_by(teacher_id=None, is_archived=False).all()
    matches = [row for row in rows if normalize_fio(fio=row.employee_name) == name]
    if not matches:
        abort(404)
    for row in matches:
        row.teacher_id = user.id
    db.session.commit()
    flash(f"Привязано курсов: {len(matches)}.", "success")
    return redirect(url_for("professional_development.unmatched"))
