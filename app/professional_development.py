"""Professional development dashboard and staff course records."""

from collections import Counter, defaultdict
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.core.extensions import db
from app.models import StaffCourseImport, User
from app.permissions import has_any_role
from app.services.professional_development_service import (
    course_status, current_pedagogical_ids, import_courses, imported_and_manual_courses,
    is_pedagogical, normalize_fio, staff_overview, year_label,
)


professional_development_bp = Blueprint(
    "professional_development", __name__, url_prefix="/professional-development"
)


def _can_manage():
    return has_any_role("ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR", "METHODIST", "HR_SPECIALIST")


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
    overview = staff_overview(users, by_user, pedagogical_ids=current_pedagogical_ids())
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
    filtered = [row for row in overview
                if (not term or term in (row["user"].fio or "").casefold())
                and (not status_filter or row["status"]["code"] == status_filter)]
    return render_template(
        "professional_development/index.html",
        overview=filtered,
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
