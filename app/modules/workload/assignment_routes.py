from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import current_user, login_required
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.core.feature_flags import WORKLOAD_WRITE, is_feature_enabled
from app.models import (
    Building,
    Department,
    EducationActivity,
    OrganizationSettings,
    SchoolClass,
    TariffCycle,
    TariffCalculationRun,
    TariffLine,
    TariffVersion,
    TeacherLoad,
    TeacherMckoResult,
    User,
    WORKLOAD_ASSIGNMENT_KINDS,
    WORKLOAD_ASSIGNMENT_KIND_LABELS,
    WORKLOAD_ASSIGNMENT_STATUS_LABELS,
    WORKLOAD_NEED_STATUS_LABELS,
    WorkloadAssignment,
    WorkloadNeed,
)
from app.services.workload_distribution_service import (
    WorkloadDistributionError,
    add_assignment_change,
    assignment_snapshot,
    calculate_assignment_annual_hours,
    cancel_assignment,
    decimal_hours,
    generate_plan_needs,
    refresh_need_status,
    require_assignment_editable,
    teacher_totals,
    validate_assignment,
)
from app.services.workload_assignment_matrix_service import (
    PLAN_KIND_LABELS,
    build_workload_assignment_matrix,
    need_education_level,
    need_grades,
    need_matches_department,
)

from .access import can_use_workload_permission, require_workload_write
from .scopes import resolve_workload_scope


ZERO = Decimal("0")
WORKSPACE_FILTER_FIELDS = (
    "version_id",
    "view",
    "department_id",
    "building_id",
    "education_level",
    "grade",
)


def _current_organization_id():
    organization = (
        OrganizationSettings.query
        .filter_by(is_active=True)
        .order_by(OrganizationSettings.id.asc())
        .first()
    )
    return organization.id if organization else None


def _require_assignments_read():
    if not can_use_workload_permission("workload.read", current_user):
        abort(403)


def _require_assignments_update():
    require_workload_write()
    if not can_use_workload_permission(
        "workload.assignments.update",
        current_user,
    ):
        abort(403)


def _parse_date(value, label):
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise WorkloadDistributionError(
            f"Укажите корректную дату: {label}."
        ) from exc


def _draft_versions_query():
    organization_id = _current_organization_id()
    query = TariffVersion.query.join(TariffCycle).filter(
        TariffVersion.status == "DRAFT",
    )
    if organization_id is None:
        query = query.filter(TariffCycle.organization_id.is_(None))
    else:
        query = query.filter(TariffCycle.organization_id == organization_id)
    return query.order_by(TariffVersion.id.desc())


def _scoped_need_query():
    query = WorkloadNeed.query
    organization_id = _current_organization_id()
    if organization_id is None:
        query = query.filter(WorkloadNeed.organization_id.is_(None))
    else:
        query = query.filter(
            WorkloadNeed.organization_id == organization_id
        )
    scope = resolve_workload_scope(current_user)
    if not scope.unrestricted:
        if scope.department_ids:
            query = query.filter(
                WorkloadNeed.department_id.in_(scope.department_ids)
            )
        if scope.building_ids:
            query = query.filter(
                WorkloadNeed.building_id.in_(scope.building_ids)
            )
        if not scope.department_ids and not scope.building_ids:
            return query.filter(db.false())
    return query


def _get_need(need_id, *, for_update=False):
    if for_update:
        _require_assignments_update()
    else:
        _require_assignments_read()
    need = _scoped_need_query().filter(WorkloadNeed.id == need_id).first_or_404()
    return need


def _get_assignment(assignment_id, *, for_update=False):
    assignment = WorkloadAssignment.query.get_or_404(assignment_id)
    need = _get_need(assignment.workload_need_id, for_update=for_update)
    if assignment.workload_need_id != need.id:
        abort(404)
    return assignment


def _active_employees():
    return (
        User.query
        .filter(
            User.is_active_user.is_(True),
            User.employment_status == "ACTIVE",
            User.archived_at.is_(None),
        )
        .order_by(
            User.last_name.asc(),
            User.first_name.asc(),
            User.middle_name.asc(),
        )
        .all()
    )


def _scope_options():
    scope = resolve_workload_scope(current_user)
    departments = Department.query.order_by(Department.name.asc()).all()
    buildings = Building.query.order_by(Building.name.asc()).all()
    if not scope.unrestricted:
        if scope.department_ids:
            departments = [
                item for item in departments
                if item.id in scope.department_ids
            ]
        if scope.building_ids:
            buildings = [
                item for item in buildings
                if item.id in scope.building_ids
            ]
    return departments, buildings


def _workspace_redirect():
    values = {}
    for field in WORKSPACE_FILTER_FIELDS:
        value = (request.form.get(field) or "").strip()
        if value:
            values[field] = value
    return redirect(url_for("workload.assignment_workspace", **values))


def _workspace_state(version_id):
    key = f"workload_matrix_state_{version_id}"
    state = session.get(key)
    if not isinstance(state, dict):
        state = {"teacher_ids": [], "rows": []}
    state.setdefault("teacher_ids", [])
    state.setdefault("rows", [])
    return key, state


def _save_workspace_state(key, state):
    session[key] = state
    session.modified = True


def _filter_workspace_needs(
    needs,
    *,
    department_id=None,
    building_id=None,
    education_level=None,
    grade=None,
):
    result = []
    for need in needs:
        if building_id and need.building_id != building_id:
            continue
        if education_level and need_education_level(need) != education_level:
            continue
        if grade and grade not in need_grades(need):
            continue
        if not need_matches_department(need, department_id):
            continue
        result.append(need)
    return result


def _workspace_teacher_metadata(teachers, selected_version):
    teacher_ids = [teacher.id for teacher in teachers]
    if not teacher_ids or selected_version is None:
        return {}
    academic_year_id = selected_version.tariff_cycle.academic_year_id
    class_names = defaultdict(list)
    for item in (
        SchoolClass.query
        .filter(
            SchoolClass.academic_year_id == academic_year_id,
            SchoolClass.teacher_user_id.in_(teacher_ids),
            SchoolClass.is_active.is_(True),
            SchoolClass.is_archived.is_(False),
        )
        .order_by(SchoolClass.grade.asc(), SchoolClass.name.asc())
        .all()
    ):
        class_names[item.teacher_user_id].append(item.name)
    mcko_by_teacher = {}
    for item in (
        TeacherMckoResult.query
        .filter(
            TeacherMckoResult.teacher_id.in_(teacher_ids),
            TeacherMckoResult.is_archived.is_(False),
        )
        .order_by(
            TeacherMckoResult.teacher_id.asc(),
            TeacherMckoResult.id.desc(),
        )
        .all()
    ):
        mcko_by_teacher.setdefault(item.teacher_id, item)
    return {
        teacher_id: {
            "class_teacher": ", ".join(class_names.get(teacher_id, [])) or "—",
            "mcko": (
                mcko_by_teacher[teacher_id].level
                if teacher_id in mcko_by_teacher
                and mcko_by_teacher[teacher_id].level
                else "—"
            ),
            "mcko_expires": (
                mcko_by_teacher[teacher_id].expires_at
                if teacher_id in mcko_by_teacher
                else None
            ),
        }
        for teacher_id in teacher_ids
    }


def _workspace_teacher_choices(
    employees,
    selected_version,
    department_id,
    assignments,
):
    suggested_ids = {
        item.employee_user_id
        for item in assignments
        if item.employee_user_id is not None
        and (not department_id or item.department_id == department_id)
    }
    if selected_version is not None and department_id:
        academic_year_id = selected_version.tariff_cycle.academic_year_id
        suggested_ids.update(
            teacher_id
            for (teacher_id,) in (
                TeacherLoad.query
                .with_entities(TeacherLoad.teacher_id)
                .filter(
                    TeacherLoad.department_id == department_id,
                    TeacherLoad.is_archived.is_(False),
                    db.or_(
                        TeacherLoad.academic_year_id == academic_year_id,
                        TeacherLoad.academic_year_id.is_(None),
                    ),
                )
                .distinct()
                .all()
            )
        )
    return {
        "suggested": [
            item for item in employees if item.id in suggested_ids
        ],
        "other": [
            item for item in employees if item.id not in suggested_ids
        ],
    }


def _workspace_subject_options(needs):
    options = {}
    for need in needs:
        plan_kind = (
            need.teaching_group.source_plan_line.education_plan.plan_kind
            if need.teaching_group
            and need.teaching_group.source_plan_line
            and need.teaching_group.source_plan_line.education_plan
            else "CURRICULUM"
        )
        options[(need.education_activity_id, plan_kind)] = {
            "activity": need.education_activity,
            "plan_kind": plan_kind,
            "plan_kind_label": PLAN_KIND_LABELS.get(plan_kind, plan_kind),
        }
    return sorted(
        options.values(),
        key=lambda item: (
            item["plan_kind_label"].casefold(),
            item["activity"].name.casefold(),
        ),
    )


def _assignment_from_form(need, assignment=None):
    kind = (request.form.get("assignment_kind") or "").strip().upper()
    employee_id = request.form.get("employee_user_id", type=int)
    if kind == "VACANCY":
        employee_id = None
    weekly = decimal_hours(
        request.form.get("weekly_hours"),
        "часов в неделю",
    )
    annual_input = decimal_hours(
        request.form.get("annual_hours"),
        "часов за период",
        required=False,
    )
    annual = calculate_assignment_annual_hours(
        need,
        weekly,
        annual_input,
    )
    item = assignment or WorkloadAssignment(
        organization_id=need.organization_id,
        tariff_version_id=need.tariff_version_id,
        workload_need_id=need.id,
        created_by_user_id=current_user.id,
    )
    item.employee_user_id = employee_id
    item.position_code = (
        " ".join((request.form.get("position_code") or "").split()).upper()
        or "TEACHER"
    )
    item.position_title = (
        " ".join((request.form.get("position_title") or "").split())
        or ("Вакансия" if kind == "VACANCY" else "Учитель")
    )
    item.department_id = (
        request.form.get("department_id", type=int)
        or need.department_id
    )
    item.building_id = (
        request.form.get("building_id", type=int)
        or need.building_id
    )
    item.assignment_kind = kind
    item.date_from = _parse_date(
        request.form.get("date_from"),
        "начало назначения",
    )
    item.date_to = _parse_date(
        request.form.get("date_to"),
        "окончание назначения",
    )
    item.weekly_hours = weekly
    item.annual_hours = annual
    item.updated_by_user_id = current_user.id
    validate_assignment(
        need,
        item,
        exclude_assignment_id=item.id,
    )
    return item


def _render_assignment_form(need, assignment=None):
    departments, buildings = _scope_options()
    return render_template(
        "workload/assignment_form.html",
        need=need,
        assignment=assignment,
        employees=_active_employees(),
        departments=departments,
        buildings=buildings,
        assignment_kinds=WORKLOAD_ASSIGNMENT_KINDS,
        assignment_kind_labels=WORKLOAD_ASSIGNMENT_KIND_LABELS,
    )


def _teacher_rows(assignments):
    by_teacher = defaultdict(list)
    for assignment in assignments:
        if assignment.employee_user_id is not None:
            by_teacher[assignment.employee_user_id].append(assignment)
    rows = []
    for employee_id, items in by_teacher.items():
        totals = teacher_totals(items)
        employee = items[0].employee
        departments = sorted({
            item.department.name
            for item in items
            if item.department is not None
        })
        rows.append({
            "employee": employee,
            "assignments": items,
            "totals": totals,
            "departments": departments,
        })
    return sorted(rows, key=lambda row: row["employee"].fio.lower())


def register_assignment_routes(workload_bp):
    @workload_bp.get("/assignments/")
    @login_required
    def assignments():
        _require_assignments_read()
        query = _scoped_need_query()
        version_id = request.args.get("version_id", type=int)
        status = (request.args.get("status") or "").strip().upper()
        department_id = request.args.get("department_id", type=int)
        building_id = request.args.get("building_id", type=int)
        vacancies_only = request.args.get("vacancies") == "1"
        if version_id:
            query = query.filter(
                WorkloadNeed.tariff_version_id == version_id
            )
        if status in WORKLOAD_NEED_STATUS_LABELS:
            query = query.filter(WorkloadNeed.status == status)
        if department_id:
            query = query.filter(WorkloadNeed.department_id == department_id)
        if building_id:
            query = query.filter(WorkloadNeed.building_id == building_id)
        needs = (
            query
            .order_by(
                WorkloadNeed.status.asc(),
                WorkloadNeed.education_activity_id.asc(),
                WorkloadNeed.id.asc(),
            )
            .all()
        )
        if vacancies_only:
            needs = [
                need for need in needs
                if need.status in {"OPEN", "PARTIAL"}
            ]
        totals = {
            "weekly": sum(
                (Decimal(item.weekly_hours or ZERO) for item in needs),
                ZERO,
            ),
            "allocated": sum(
                (item.allocated_weekly_hours for item in needs),
                ZERO,
            ),
        }
        totals["remaining"] = totals["weekly"] - totals["allocated"]
        departments, buildings = _scope_options()
        selected_version = next(
            (
                version
                for version in _draft_versions_query().all()
                if version.id == version_id
            ),
            needs[0].tariff_version if needs else None,
        )
        return render_template(
            "workload/assignments.html",
            needs=needs,
            versions=_draft_versions_query().all(),
            selected_version=selected_version,
            totals=totals,
            departments=departments,
            buildings=buildings,
            status_labels=WORKLOAD_NEED_STATUS_LABELS,
            selected_version_id=version_id,
            selected_status=status,
            selected_department_id=department_id,
            selected_building_id=building_id,
            vacancies_only=vacancies_only,
            can_update=(
                is_feature_enabled(WORKLOAD_WRITE)
                and can_use_workload_permission(
                    "workload.assignments.update",
                    current_user,
                )
            ),
        )

    @workload_bp.post("/assignments/generate")
    @login_required
    def assignments_generate():
        _require_assignments_update()
        version_id = request.form.get("version_id", type=int)
        version = _draft_versions_query().filter(
            TariffVersion.id == version_id
        ).first_or_404()
        try:
            result = generate_plan_needs(
                version,
                user_id=current_user.id,
            )
            db.session.commit()
        except WorkloadDistributionError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash(
                "Потребность пересчитана: "
                f"создано {result['created']}, "
                f"обновлено {result['updated']}, "
                f"отменено {result['cancelled']}, "
                f"пустых строк пропущено {result['skipped_empty']}.",
                "success",
            )
        if request.form.get("return_to") == "workspace":
            return redirect(
                url_for(
                    "workload.assignment_workspace",
                    version_id=version.id,
                )
            )
        return redirect(url_for("workload.assignments", version_id=version.id))

    @workload_bp.get("/needs/<int:need_id>")
    @login_required
    def need_detail(need_id):
        need = _get_need(need_id)
        return render_template(
            "workload/need_detail.html",
            need=need,
            need_status_labels=WORKLOAD_NEED_STATUS_LABELS,
            assignment_kind_labels=WORKLOAD_ASSIGNMENT_KIND_LABELS,
            assignment_status_labels=WORKLOAD_ASSIGNMENT_STATUS_LABELS,
            can_update=(
                is_feature_enabled(WORKLOAD_WRITE)
                and can_use_workload_permission(
                    "workload.assignments.update",
                    current_user,
                )
                and need.tariff_version.status == "DRAFT"
                and need.status != "CANCELLED"
            ),
        )

    @workload_bp.route(
        "/needs/<int:need_id>/assignments/new",
        methods=["GET", "POST"],
    )
    @login_required
    def assignment_new(need_id):
        need = _get_need(need_id, for_update=True)
        if request.method == "POST":
            try:
                assignment = _assignment_from_form(need)
                db.session.add(assignment)
                db.session.flush()
                add_assignment_change(
                    assignment,
                    "CREATE",
                    user_id=current_user.id,
                )
                refresh_need_status(need)
                db.session.commit()
            except (WorkloadDistributionError, IntegrityError) as exc:
                db.session.rollback()
                message = (
                    str(exc)
                    if isinstance(exc, WorkloadDistributionError)
                    else "Не удалось сохранить назначение."
                )
                flash(message, "danger")
            else:
                flash("Назначение добавлено.", "success")
                return redirect(
                    url_for("workload.need_detail", need_id=need.id)
                )
        return _render_assignment_form(need)

    @workload_bp.route(
        "/assignments/<int:assignment_id>/edit",
        methods=["GET", "POST"],
    )
    @login_required
    def assignment_edit(assignment_id):
        assignment = _get_assignment(assignment_id, for_update=True)
        need = assignment.workload_need
        if request.method == "POST":
            try:
                require_assignment_editable(
                    assignment,
                    expected_revision=request.form.get(
                        "revision",
                        type=int,
                    ),
                )
                before = assignment_snapshot(assignment)
                reason = " ".join(
                    (request.form.get("reason") or "").split()
                )
                if not reason:
                    raise WorkloadDistributionError(
                        "Укажите основание изменения назначения."
                    )
                _assignment_from_form(need, assignment)
                assignment.revision += 1
                add_assignment_change(
                    assignment,
                    "UPDATE",
                    user_id=current_user.id,
                    before_data=before,
                    reason=reason,
                )
                refresh_need_status(need)
                db.session.commit()
            except (WorkloadDistributionError, IntegrityError) as exc:
                db.session.rollback()
                message = (
                    str(exc)
                    if isinstance(exc, WorkloadDistributionError)
                    else "Не удалось обновить назначение."
                )
                flash(message, "danger")
            else:
                flash("Назначение обновлено.", "success")
                return redirect(
                    url_for("workload.need_detail", need_id=need.id)
                )
        return _render_assignment_form(need, assignment)

    @workload_bp.post("/assignments/<int:assignment_id>/cancel")
    @login_required
    def assignment_cancel(assignment_id):
        assignment = _get_assignment(assignment_id, for_update=True)
        try:
            cancel_assignment(
                assignment,
                user_id=current_user.id,
                expected_revision=request.form.get("revision", type=int),
                reason=request.form.get("reason"),
            )
            db.session.commit()
        except WorkloadDistributionError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Назначение отменено.", "success")
        return redirect(
            url_for(
                "workload.need_detail",
                need_id=assignment.workload_need_id,
            )
        )

    @workload_bp.get("/teachers/")
    @login_required
    def workload_teachers():
        _require_assignments_read()
        need_ids = [
            item.id
            for item in _scoped_need_query()
            .filter(WorkloadNeed.status != "CANCELLED")
            .all()
        ]
        assignments = (
            WorkloadAssignment.query
            .filter(
                WorkloadAssignment.workload_need_id.in_(need_ids),
                WorkloadAssignment.status != "CANCELLED",
                WorkloadAssignment.assignment_kind != "VACANCY",
            )
            .all()
            if need_ids else []
        )
        return render_template(
            "workload/teachers.html",
            rows=_teacher_rows(assignments),
        )

    @workload_bp.get("/assignments/workspace")
    @login_required
    def assignment_workspace():
        _require_assignments_read()
        view_mode = (request.args.get("view") or "all").strip().lower()
        if view_mode not in {"all", "department"}:
            view_mode = "all"
        department_id = (
            request.args.get("department_id", type=int)
            if view_mode == "department"
            else None
        )
        building_id = request.args.get("building_id", type=int)
        education_level = (
            request.args.get("education_level") or ""
        ).strip().upper()
        if education_level not in {"NOO", "OOO", "SOO"}:
            education_level = ""
        grade = request.args.get("grade", type=int)
        if grade not in range(1, 12):
            grade = None
        versions = _draft_versions_query().all()
        version_id = request.args.get("version_id", type=int)
        if version_id is None and versions:
            version_id = versions[0].id
        selected_version = next(
            (item for item in versions if item.id == version_id),
            None,
        )
        query = _scoped_need_query().filter(
            WorkloadNeed.status.in_(("OPEN", "PARTIAL", "COVERED")),
        )
        if selected_version is not None:
            query = query.filter(
                WorkloadNeed.tariff_version_id == selected_version.id
            )
        all_needs = query.order_by(
            WorkloadNeed.status.asc(),
            WorkloadNeed.education_activity_id.asc(),
        ).all()
        needs = _filter_workspace_needs(
            all_needs,
            department_id=department_id,
            building_id=building_id,
            education_level=education_level or None,
            grade=grade,
        )
        need_ids = [item.id for item in needs]
        assignments = (
            WorkloadAssignment.query
            .filter(
                WorkloadAssignment.workload_need_id.in_(need_ids),
                WorkloadAssignment.status != "CANCELLED",
                WorkloadAssignment.assignment_kind != "VACANCY",
            )
            .all()
            if need_ids else []
        )
        state_key, state = _workspace_state(version_id or 0)
        employees = _active_employees()
        employee_by_id = {item.id: item for item in employees}
        extra_teachers = [
            employee_by_id[teacher_id]
            for teacher_id in state["teacher_ids"]
            if teacher_id in employee_by_id
        ]
        subject_options = _workspace_subject_options(needs)
        allowed_subject_keys = {
            (item["activity"].id, item["plan_kind"])
            for item in subject_options
        }
        activities = {
            item.id: item
            for item in EducationActivity.query.filter(
                EducationActivity.id.in_({
                    row.get("activity_id")
                    for row in state["rows"]
                    if row.get("activity_id")
                })
            ).all()
        } if state["rows"] else {}
        draft_rows = [
            (
                employee_by_id[row["teacher_id"]],
                activities[row["activity_id"]],
                row["plan_kind"],
            )
            for row in state["rows"]
            if row.get("teacher_id") in employee_by_id
            and row.get("activity_id") in activities
            and (
                row.get("activity_id"),
                row.get("plan_kind"),
            ) in allowed_subject_keys
        ]
        matrix_teachers = {
            assignment.employee_user_id: assignment.employee
            for assignment in assignments
            if assignment.employee_user_id is not None
        }
        matrix_teachers.update({
            item.id: item
            for item in extra_teachers
        })
        matrix = build_workload_assignment_matrix(
            needs,
            assignments,
            extra_teachers=extra_teachers,
            draft_rows=draft_rows,
            teacher_metadata=_workspace_teacher_metadata(
                list(matrix_teachers.values()),
                selected_version,
            ),
        )
        departments, buildings = _scope_options()
        totals = {
            "weekly": sum(
                (Decimal(item.weekly_hours or ZERO) for item in needs),
                ZERO,
            ),
            "allocated": sum(
                (item.allocated_weekly_hours for item in needs),
                ZERO,
            ),
        }
        totals["remaining"] = totals["weekly"] - totals["allocated"]
        return render_template(
            "workload/assignment_workspace.html",
            needs=needs,
            selected_version=selected_version,
            versions=versions,
            selected_version_id=version_id,
            matrix=matrix,
            totals=totals,
            departments=departments,
            buildings=buildings,
            view_mode=view_mode,
            selected_department_id=department_id,
            selected_building_id=building_id,
            selected_education_level=education_level,
            selected_grade=grade,
            teacher_choices=_workspace_teacher_choices(
                employees,
                selected_version,
                department_id,
                assignments,
            ),
            subject_options=subject_options,
            need_status_labels=WORKLOAD_NEED_STATUS_LABELS,
            assignment_kind_labels=WORKLOAD_ASSIGNMENT_KIND_LABELS,
            can_update=(
                is_feature_enabled(WORKLOAD_WRITE)
                and can_use_workload_permission(
                    "workload.assignments.update",
                    current_user,
                )
            ),
        )

    @workload_bp.post("/assignments/workspace/teachers")
    @login_required
    def assignment_workspace_teacher_add():
        _require_assignments_update()
        version_id = request.form.get("version_id", type=int)
        teacher_id = request.form.get("teacher_id", type=int)
        version = _draft_versions_query().filter(
            TariffVersion.id == version_id
        ).first_or_404()
        teacher = db.session.get(User, teacher_id) if teacher_id else None
        if (
            teacher is None
            or not teacher.is_active_user
            or teacher.employment_status != "ACTIVE"
        ):
            flash("Выберите работающего преподавателя.", "danger")
            return _workspace_redirect()
        key, state = _workspace_state(version.id)
        if teacher.id not in state["teacher_ids"]:
            state["teacher_ids"].append(teacher.id)
            _save_workspace_state(key, state)
        return _workspace_redirect()

    @workload_bp.post("/assignments/workspace/subjects")
    @login_required
    def assignment_workspace_subject_add():
        _require_assignments_update()
        version_id = request.form.get("version_id", type=int)
        teacher_id = request.form.get("teacher_id", type=int)
        activity_id = request.form.get("activity_id", type=int)
        plan_kind = (request.form.get("plan_kind") or "").strip().upper()
        version = _draft_versions_query().filter(
            TariffVersion.id == version_id
        ).first_or_404()
        teacher = db.session.get(User, teacher_id) if teacher_id else None
        activity = (
            db.session.get(EducationActivity, activity_id)
            if activity_id else None
        )
        if teacher is None or activity is None:
            flash("Выберите преподавателя и предмет.", "danger")
            return _workspace_redirect()
        if plan_kind not in PLAN_KIND_LABELS:
            flash("Выберите допустимую часть учебного плана.", "danger")
            return _workspace_redirect()
        has_need = (
            _scoped_need_query()
            .filter(
                WorkloadNeed.tariff_version_id == version.id,
                WorkloadNeed.education_activity_id == activity.id,
                WorkloadNeed.status.in_(("OPEN", "PARTIAL", "COVERED")),
            )
            .first()
        )
        if has_need is None:
            flash("В выбранной версии нет часов по этому предмету.", "danger")
            return _workspace_redirect()
        key, state = _workspace_state(version.id)
        if teacher.id not in state["teacher_ids"]:
            state["teacher_ids"].append(teacher.id)
        row = {
            "teacher_id": teacher.id,
            "activity_id": activity.id,
            "plan_kind": plan_kind,
        }
        if row not in state["rows"]:
            state["rows"].append(row)
        _save_workspace_state(key, state)
        return _workspace_redirect()

    @workload_bp.post("/assignments/workspace/assign")
    @login_required
    def assignment_workspace_assign():
        need_id = request.form.get("need_id", type=int)
        teacher_id = request.form.get("teacher_id", type=int)
        need = _get_need(need_id, for_update=True)
        teacher = db.session.get(User, teacher_id) if teacher_id else None
        if teacher is None:
            flash("Выберите преподавателя.", "danger")
            return _workspace_redirect()
        weekly = Decimal(need.remaining_weekly_hours or ZERO)
        annual = Decimal(need.remaining_annual_hours or ZERO)
        if weekly <= ZERO:
            flash("Эти часы уже распределены.", "warning")
            return _workspace_redirect()
        assignment = WorkloadAssignment(
            organization_id=need.organization_id,
            tariff_version_id=need.tariff_version_id,
            workload_need_id=need.id,
            employee_user_id=teacher.id,
            position_code="TEACHER",
            position_title="Учитель",
            department_id=(
                request.form.get("department_id", type=int)
                or need.department_id
            ),
            building_id=need.building_id,
            assignment_kind="MAIN",
            date_from=need.date_from,
            date_to=need.date_to,
            weekly_hours=weekly,
            annual_hours=annual,
            status="DRAFT",
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
        )
        try:
            validate_assignment(need, assignment)
            db.session.add(assignment)
            db.session.flush()
            add_assignment_change(
                assignment,
                "CREATE",
                user_id=current_user.id,
            )
            refresh_need_status(need)
            db.session.commit()
        except (WorkloadDistributionError, IntegrityError) as exc:
            db.session.rollback()
            flash(
                str(exc)
                if isinstance(exc, WorkloadDistributionError)
                else "Не удалось назначить преподавателя.",
                "danger",
            )
        else:
            flash(
                f"{need.education_activity.name}: "
                f"{teacher.fio} назначен на полный объём.",
                "success",
            )
        return _workspace_redirect()

    @workload_bp.post(
        "/assignments/workspace/<int:assignment_id>/cancel"
    )
    @login_required
    def assignment_workspace_cancel(assignment_id):
        assignment = _get_assignment(assignment_id, for_update=True)
        try:
            cancel_assignment(
                assignment,
                user_id=current_user.id,
                expected_revision=assignment.revision,
                reason="Снято в матрице распределения нагрузки",
            )
            db.session.commit()
        except WorkloadDistributionError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Назначение снято. Часы снова доступны.", "success")
        return _workspace_redirect()

    @workload_bp.get("/assignments/workspace/export.xlsx")
    @login_required
    def assignment_workspace_export():
        _require_assignments_read()
        version_id = request.args.get("version_id", type=int)
        version = _draft_versions_query().filter(
            TariffVersion.id == version_id
        ).first_or_404()
        view_mode = (request.args.get("view") or "all").strip().lower()
        department_id = (
            request.args.get("department_id", type=int)
            if view_mode == "department"
            else None
        )
        education_level = (
            request.args.get("education_level") or ""
        ).strip().upper()
        grade = request.args.get("grade", type=int)
        building_id = request.args.get("building_id", type=int)
        needs = _filter_workspace_needs(
            _scoped_need_query().filter(
                WorkloadNeed.tariff_version_id == version.id,
                WorkloadNeed.status.in_(("OPEN", "PARTIAL", "COVERED")),
            ).all(),
            department_id=department_id,
            building_id=building_id,
            education_level=education_level or None,
            grade=grade,
        )
        need_ids = [item.id for item in needs]
        assignments = (
            WorkloadAssignment.query
            .filter(
                WorkloadAssignment.workload_need_id.in_(need_ids),
                WorkloadAssignment.status != "CANCELLED",
                WorkloadAssignment.assignment_kind != "VACANCY",
            )
            .all()
            if need_ids else []
        )
        matrix = build_workload_assignment_matrix(needs, assignments)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Нагрузка"
        headers = [
            "Преподаватель",
            "Предмет / деятельность",
            "Всего",
            *[column["label"] for column in matrix["columns"]],
        ]
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="2F6FED")
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )
        for block in matrix["blocks"]:
            for row in block["rows"]:
                if row.get("placeholder"):
                    continue
                values = [
                    block["label"],
                    row["activity"].name,
                    float(row["total"]),
                ]
                for column in matrix["columns"]:
                    values.append(float(sum(
                        (
                            Decimal(segment["hours"] or ZERO)
                            for segment in row["cells"].get(
                                column["key"],
                                [],
                            )
                        ),
                        ZERO,
                    )))
                sheet.append(values)
        sheet.freeze_panes = "D2"
        sheet.column_dimensions["A"].width = 28
        sheet.column_dimensions["B"].width = 30
        sheet.column_dimensions["C"].width = 10
        for column_cells in sheet.iter_cols(
            min_col=4,
            max_col=sheet.max_column,
        ):
            sheet.column_dimensions[column_cells[0].column_letter].width = 12
        stream = BytesIO()
        workbook.save(stream)
        stream.seek(0)
        return send_file(
            stream,
            as_attachment=True,
            download_name=(
                "Altair_workload_"
                f"{version.tariff_cycle.academic_year.name.replace('/', '-')}"
                ".xlsx"
            ),
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    @workload_bp.get("/teachers/<int:user_id>")
    @login_required
    def workload_teacher_detail(user_id):
        scope = resolve_workload_scope(current_user)
        if scope.own_employee_only and current_user.id != user_id:
            abort(403)
        if not (
            can_use_workload_permission("workload.read", current_user)
            or (
                can_use_workload_permission(
                    "workload.self.read",
                    current_user,
                )
                and current_user.id == user_id
            )
        ):
            abort(403)
        employee = User.query.get_or_404(user_id)
        query = WorkloadAssignment.query.filter(
            WorkloadAssignment.employee_user_id == user_id,
            WorkloadAssignment.status != "CANCELLED",
        )
        if not scope.unrestricted:
            need_ids = [
                item.id for item in _scoped_need_query().all()
            ]
            query = query.filter(
                WorkloadAssignment.workload_need_id.in_(need_ids)
            )
        assignments = query.order_by(
            WorkloadAssignment.date_from.asc(),
            WorkloadAssignment.id.asc(),
        ).all()
        assignment_ids = [item.id for item in assignments]
        tariff_lines = {}
        if assignment_ids:
            calculated_lines = (
                TariffLine.query
                .join(TariffCalculationRun)
                .filter(
                    TariffLine.workload_assignment_id.in_(assignment_ids),
                    TariffCalculationRun.status == "SUCCEEDED",
                )
                .order_by(
                    TariffCalculationRun.id.desc(),
                    TariffLine.id.desc(),
                )
                .all()
            )
            for line in calculated_lines:
                tariff_lines.setdefault(
                    line.workload_assignment_id,
                    line,
                )
        calculated_fte = sum(
            (
                Decimal(line.fte_value or ZERO)
                for line in tariff_lines.values()
            ),
            ZERO,
        )
        calculated_amount = sum(
            (
                Decimal(line.total_amount or ZERO)
                for line in tariff_lines.values()
            ),
            ZERO,
        )
        can_view_finance = can_use_workload_permission(
            "workload.finance.read",
            current_user,
        )
        return render_template(
            "workload/teacher_detail.html",
            employee=employee,
            assignments=assignments,
            totals=teacher_totals(assignments),
            tariff_lines=tariff_lines,
            calculated_fte=calculated_fte,
            calculated_amount=calculated_amount,
            can_view_finance=can_view_finance,
            assignment_kind_labels=WORKLOAD_ASSIGNMENT_KIND_LABELS,
        )

    @workload_bp.get("/departments/")
    @login_required
    def workload_departments():
        _require_assignments_read()
        needs = (
            _scoped_need_query()
            .filter(WorkloadNeed.status != "CANCELLED")
            .all()
        )
        rows = defaultdict(lambda: {
            "department": None,
            "needs": [],
            "weekly": ZERO,
            "allocated": ZERO,
            "teachers": set(),
        })
        for need in needs:
            key = need.department_id or 0
            row = rows[key]
            row["department"] = need.department
            row["needs"].append(need)
            row["weekly"] += Decimal(need.weekly_hours or ZERO)
            row["allocated"] += need.allocated_weekly_hours
            row["teachers"].update(
                item.employee_user_id
                for item in need.active_assignments
                if item.employee_user_id is not None
                and item.assignment_kind != "VACANCY"
            )
        result = []
        for row in rows.values():
            row["remaining"] = row["weekly"] - row["allocated"]
            row["teacher_count"] = len(row["teachers"])
            result.append(row)
        result.sort(
            key=lambda item: (
                item["department"].name.lower()
                if item["department"] else "я"
            )
        )
        return render_template(
            "workload/departments.html",
            rows=result,
        )
