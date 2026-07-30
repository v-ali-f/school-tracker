from collections import defaultdict
from datetime import date
from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.core.feature_flags import WORKLOAD_WRITE, is_feature_enabled
from app.models import (
    Building,
    Department,
    OrganizationSettings,
    TariffCycle,
    TariffCalculationRun,
    TariffLine,
    TariffVersion,
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

from .access import can_use_workload_permission, require_workload_write
from .scopes import resolve_workload_scope


ZERO = Decimal("0")


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
                f"отменено {result['cancelled']}.",
                "success",
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
        department_id = request.args.get("department_id", type=int)
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
        if department_id:
            query = query.filter(
                WorkloadNeed.department_id == department_id
            )
        needs = query.order_by(
            WorkloadNeed.status.asc(),
            WorkloadNeed.education_activity_id.asc(),
        ).all()
        selected_need_id = request.args.get("selected_need_id", type=int)
        selected_need = next(
            (item for item in needs if item.id == selected_need_id),
            needs[0] if needs else None,
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
        departments, _ = _scope_options()
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
            selected_need=selected_need,
            selected_version=selected_version,
            versions=versions,
            selected_version_id=version_id,
            teacher_rows=_teacher_rows(assignments),
            totals=totals,
            departments=departments,
            selected_department_id=department_id,
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
