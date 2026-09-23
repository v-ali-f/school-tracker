import re
from datetime import date, datetime

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload

from app.core.extensions import db
from app.models import (
    AcademicYear,
    DepartmentLeader,
    LessonVisit,
    TeacherLoad,
    User,
    WorkloadAssignment,
)
from app.services.teacher_mcko_registry_service import teacher_professional_roster


lesson_visits_bp = Blueprint(
    "lesson_visits",
    __name__,
    url_prefix="/lesson-visits",
)

MANAGEMENT_ROLES = frozenset({"ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR", "METHODIST"})
REVIEWER_ROLES = MANAGEMENT_ROLES | {"DEPARTMENT_HEAD"}

CHECKLIST_SECTIONS = (
    ("organizational_moment", "Организационный момент", (("present", "Присутствует"), ("absent", "Отсутствует")), False),
    ("homework_check", "Проверка домашнего задания", (("performed", "Производится"), ("not_performed", "Не производится")), False),
    ("problem_statement", "Постановка проблемы", (("teacher", "Учителем"), ("students", "Обучающимися"), ("absent", "Не озвучена")), False),
    ("lesson_goal", "Цель урока", (("teacher", "Учителем"), ("students", "Обучающимися"), ("absent", "Не озвучена")), False),
    ("lesson_topic", "Тема урока", (("teacher", "Учителем"), ("students", "Обучающимися"), ("absent", "Не озвучена")), False),
    ("topic_matches_plan", "Соответствие теме КТП", (("yes", "Соответствует"), ("no", "Не соответствует")), False),
    ("visualization", "Средства визуализации", (("used", "Используются"), ("not_used", "Не используются")), False),
    ("activities", "Виды деятельности", (("frontal", "Фронтальная"), ("individual", "Индивидуальная"), ("group", "Групповая"), ("pairs", "Работа в парах")), True),
    ("class_coverage", "Охват класса работой", (("all", "Весь класс"), ("70_99", "70–99%"), ("50_69", "50–69%"), ("under_50", "Менее 50%")), False),
    ("assessment", "Оценивание", (("performed", "Производится"), ("not_performed", "Не производится")), False),
    ("assessment_type", "Вид оценивания", (("formal", "Формальное"), ("justified", "Обоснованное"), ("cumulative", "Накопительное")), False),
    ("reflection", "Рефлексия", (("teacher", "Учителя"), ("students", "Обучающихся"), ("absent", "Отсутствует")), False),
    ("homework_announced", "Домашнее задание", (("yes", "Озвучено"), ("no", "Не озвучено")), False),
    ("notebook_work", "Работа в тетрадях", (("systematic", "Системная"), ("episodic", "Эпизодичная")), False),
)


def _role_codes(user=None):
    user = user or current_user
    codes = {str(code).upper() for code in getattr(user, "role_codes", []) if code}
    primary = getattr(user, "role", None)
    if primary:
        codes.add(str(primary).upper())
    return codes


def _is_management():
    return bool(_role_codes().intersection(MANAGEMENT_ROLES))


def _is_reviewer():
    return bool(_role_codes().intersection(REVIEWER_ROLES))


def _managed_department_ids():
    if _is_management():
        return None
    if "DEPARTMENT_HEAD" not in _role_codes():
        return set()
    return {
        row.department_id
        for row in DepartmentLeader.query.filter_by(user_id=current_user.id).all()
        if row.department_id
    }


def _reviewable_teacher_ids():
    if _is_management():
        return None
    department_ids = _managed_department_ids()
    if not department_ids:
        return set()
    users, department_ids_by_teacher, _departments = teacher_professional_roster()
    return {
        teacher_id
        for teacher_id in users
        if department_ids_by_teacher.get(teacher_id, set()).intersection(department_ids)
    }


def _can_view_visit(visit):
    if _is_management():
        return True
    if visit.teacher_id == current_user.id:
        return True
    allowed_ids = _reviewable_teacher_ids()
    return visit.teacher_id in allowed_ids


def _can_edit_visit(visit):
    if _is_management():
        return True
    return _is_reviewer() and visit.observer_id == current_user.id and _can_view_visit(visit)


def _require_module_access():
    if _is_reviewer():
        return
    if _role_codes().intersection({"TEACHER", "CLASS_TEACHER"}):
        return
    if LessonVisit.query.filter_by(teacher_id=current_user.id).first() is None:
        abort(403)


def _workspace_context():
    from app.modules.hub.routes import build_home_context

    return {
        "workspace_nav": build_home_context(),
        "workspace_context_title": "Посещение уроков",
        "workspace_context_subtitle": "Карты наблюдения и история обратной связи",
    }


def _parse_date(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parallel_from_class(class_name):
    match = re.match(r"\s*(\d{1,2})", class_name or "")
    value = int(match.group(1)) if match else None
    return value if value and 1 <= value <= 11 else None


def _teacher_options():
    users, department_ids_by_teacher, _departments = teacher_professional_roster()
    allowed_ids = _reviewable_teacher_ids()
    if allowed_ids is not None:
        users = {teacher_id: user for teacher_id, user in users.items() if teacher_id in allowed_ids}
    return sorted(users.values(), key=lambda item: (item.fio or item.username).casefold())


def _checklist_from_form():
    result = {}
    missing = []
    for code, title, options, multiple in CHECKLIST_SECTIONS:
        allowed = {value for value, _label in options}
        if multiple:
            values = [value for value in request.form.getlist(f"check_{code}") if value in allowed]
            if not values:
                missing.append(title)
            result[code] = values
            continue
        value = (request.form.get(f"check_{code}") or "").strip()
        if code == "assessment_type" and request.form.get("check_assessment") == "not_performed":
            result[code] = None
            continue
        if value not in allowed:
            missing.append(title)
        else:
            result[code] = value
    if missing:
        raise ValueError("Заполните пункты чек-листа: " + ", ".join(missing) + ".")
    return result


def _apply_form(visit):
    teacher_id = request.form.get("teacher_id", type=int)
    allowed_ids = _reviewable_teacher_ids()
    teacher = User.query.filter_by(
        id=teacher_id,
        is_active_user=True,
        employment_status="ACTIVE",
    ).first()
    if teacher is None or (allowed_ids is not None and teacher.id not in allowed_ids):
        raise ValueError("Выберите доступного педагога.")

    visit_date = _parse_date(request.form.get("visit_date"))
    if visit_date is None:
        raise ValueError("Укажите корректную дату посещения.")
    if visit_date > date.today():
        raise ValueError("Нельзя сохранить посещение с будущей датой.")

    class_name = (request.form.get("class_name") or "").strip()
    subject_name = (request.form.get("subject_name") or "").strip()
    topic = (request.form.get("topic") or "").strip()
    strengths = (request.form.get("strengths") or "").strip()
    growth_areas = (request.form.get("growth_areas") or "").strip()
    if not class_name:
        raise ValueError("Укажите класс или учебную группу.")
    if not subject_name:
        raise ValueError("Укажите предмет.")
    if not topic:
        raise ValueError("Укажите тему урока.")
    if not strengths:
        raise ValueError("Укажите значимые сильные стороны урока.")
    if not growth_areas:
        raise ValueError("Укажите зоны роста или напишите, что они не выявлены.")
    repeat_raw = (request.form.get("repeat_required") or "").strip().lower()
    if repeat_raw not in {"yes", "no"}:
        raise ValueError("Укажите, требуется ли повторное посещение.")

    assignment_id = request.form.get("workload_assignment_id", type=int)
    assignment = None
    if assignment_id:
        assignment = WorkloadAssignment.query.filter_by(
            id=assignment_id,
            employee_user_id=teacher.id,
        ).first()

    current_year = AcademicYear.query.filter_by(is_current=True).order_by(AcademicYear.id.desc()).first()
    visit.teacher_id = teacher.id
    visit.academic_year_id = current_year.id if current_year else None
    visit.workload_assignment_id = assignment.id if assignment else None
    visit.visit_date = visit_date
    visit.parallel = _parallel_from_class(class_name)
    visit.class_name = class_name
    visit.subject_name = subject_name
    visit.topic = topic
    visit.checklist = _checklist_from_form()
    visit.strengths = strengths
    visit.growth_areas = growth_areas
    visit.repeat_required = repeat_raw == "yes"
    return visit


def _workload_options(teacher_id, visit_date=None):
    visit_date = visit_date or date.today()
    options = []
    seen = set()
    assignments = (
        WorkloadAssignment.query
        .options(
            selectinload(WorkloadAssignment.workload_need),
        )
        .filter(
            WorkloadAssignment.employee_user_id == teacher_id,
            WorkloadAssignment.status != "CANCELLED",
            WorkloadAssignment.date_from <= visit_date,
            WorkloadAssignment.date_to >= visit_date,
        )
        .order_by(WorkloadAssignment.id.desc())
        .all()
    )
    for assignment in assignments:
        need = assignment.workload_need
        group = need.teaching_group if need else None
        activity = need.education_activity if need else None
        class_name = (group.name if group else "").strip()
        subject_name = (activity.name if activity else "").strip()
        if not class_name or not subject_name:
            continue
        key = (class_name.casefold(), subject_name.casefold())
        if key in seen:
            continue
        seen.add(key)
        options.append({
            "assignment_id": assignment.id,
            "class_name": class_name,
            "parallel": _parallel_from_class(class_name),
            "subject_name": subject_name,
            "source": "Нагрузка",
        })

    legacy_query = TeacherLoad.query.filter_by(teacher_id=teacher_id, is_archived=False)
    current_year = AcademicYear.query.filter_by(is_current=True).order_by(AcademicYear.id.desc()).first()
    if current_year:
        legacy_query = legacy_query.filter(
            db.or_(TeacherLoad.academic_year_id == current_year.id, TeacherLoad.academic_year_id.is_(None))
        )
    for load in legacy_query.order_by(TeacherLoad.class_name.asc(), TeacherLoad.subject_name.asc()).all():
        class_name = (load.class_name or load.group_name or "").strip()
        subject_name = (
            (load.education_activity.name if load.education_activity else None)
            or (load.subject.name if load.subject else None)
            or load.subject_name
            or ""
        ).strip()
        if not class_name or not subject_name:
            continue
        key = (class_name.casefold(), subject_name.casefold())
        if key in seen:
            continue
        seen.add(key)
        options.append({
            "assignment_id": None,
            "class_name": class_name,
            "parallel": load.grade or _parallel_from_class(class_name),
            "subject_name": subject_name,
            "source": "Нагрузка",
        })
    return sorted(options, key=lambda item: (item["parallel"] or 99, item["class_name"], item["subject_name"]))


def _form_context(visit=None):
    return {
        **_workspace_context(),
        "visit": visit,
        "teachers": _teacher_options(),
        "checklist_sections": CHECKLIST_SECTIONS,
        "today": date.today(),
    }


@lesson_visits_bp.get("/")
@login_required
def index():
    _require_module_access()
    query = LessonVisit.query.options(
        selectinload(LessonVisit.teacher),
        selectinload(LessonVisit.observer),
    )
    if not _is_management():
        allowed_ids = _reviewable_teacher_ids()
        visible_ids = {current_user.id} | (allowed_ids or set())
        query = query.filter(LessonVisit.teacher_id.in_(visible_ids))

    search_terms = (request.args.get("q") or "").split()
    if search_terms:
        query = query.join(User, LessonVisit.teacher_id == User.id)
        for term in search_terms:
            query = query.filter(
                db.or_(
                    User.last_name.ilike(f"%{term}%"),
                    User.first_name.ilike(f"%{term}%"),
                    User.middle_name.ilike(f"%{term}%"),
                    User.username.ilike(f"%{term}%"),
                )
            )
    repeat_filter = (request.args.get("repeat") or "").strip().lower()
    if repeat_filter == "yes":
        query = query.filter(LessonVisit.repeat_required.is_(True))
    elif repeat_filter == "no":
        query = query.filter(LessonVisit.repeat_required.is_(False))
    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))
    if date_from:
        query = query.filter(LessonVisit.visit_date >= date_from)
    if date_to:
        query = query.filter(LessonVisit.visit_date <= date_to)

    visits = query.order_by(LessonVisit.visit_date.desc(), LessonVisit.id.desc()).all()
    teacher_count = len({item.teacher_id for item in visits})
    repeat_count = sum(1 for item in visits if item.repeat_required)
    return render_template(
        "lesson_visits/index.html",
        visits=visits,
        summary={
            "total": len(visits),
            "teachers": teacher_count,
            "repeat": repeat_count,
            "closed": len(visits) - repeat_count,
        },
        can_create=_is_reviewer(),
        **_workspace_context(),
    )


@lesson_visits_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if not _is_reviewer():
        abort(403)
    visit = LessonVisit(observer_id=current_user.id, visit_date=date.today())
    if request.method == "POST":
        try:
            _apply_form(visit)
            db.session.add(visit)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Карта посещения сохранена. Педагог видит результат в своей истории.", "success")
            return redirect(url_for("lesson_visits.detail", visit_id=visit.id))
    return render_template("lesson_visits/form.html", **_form_context(visit))


@lesson_visits_bp.route("/<int:visit_id>/edit", methods=["GET", "POST"])
@login_required
def edit(visit_id):
    visit = LessonVisit.query.get_or_404(visit_id)
    if not _can_edit_visit(visit):
        abort(403)
    if request.method == "POST":
        try:
            _apply_form(visit)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Карта посещения обновлена.", "success")
            return redirect(url_for("lesson_visits.detail", visit_id=visit.id))
    return render_template("lesson_visits/form.html", **_form_context(visit))


@lesson_visits_bp.get("/<int:visit_id>")
@login_required
def detail(visit_id):
    visit = LessonVisit.query.options(
        selectinload(LessonVisit.teacher),
        selectinload(LessonVisit.observer),
    ).get_or_404(visit_id)
    if not _can_view_visit(visit):
        abort(403)
    return render_template(
        "lesson_visits/detail.html",
        visit=visit,
        checklist_sections=CHECKLIST_SECTIONS,
        can_edit=_can_edit_visit(visit),
        **_workspace_context(),
    )


@lesson_visits_bp.get("/api/teachers/<int:teacher_id>/workload")
@login_required
def teacher_workload(teacher_id):
    if not _is_reviewer():
        abort(403)
    allowed_ids = _reviewable_teacher_ids()
    if allowed_ids is not None and teacher_id not in allowed_ids:
        abort(403)
    target_date = _parse_date(request.args.get("date")) or date.today()
    return jsonify({"items": _workload_options(teacher_id, target_date)})
