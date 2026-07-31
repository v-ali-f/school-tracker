from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.core.extensions import db
from app.core.feature_flags import WORKLOAD_WRITE, is_feature_enabled
from app.models import (
    AcademicYear,
    EducationPlan,
    OrganizationSettings,
    PopulationSnapshotClass,
    PopulationSnapshotEnrollment,
    TariffCycle,
    TariffVersion,
)
from app.services.education_plan_binding_service import (
    PlanBindingValidationError,
    class_plan_allocations,
    plan_matches_snapshot_class,
    replace_class_plan_assignments,
    replace_plan_binding_members,
)
from app.services.class_plan_matrix_service import (
    EDUCATION_LEVEL_GRADES,
    EDUCATION_LEVEL_LABELS,
    build_class_plan_matrix,
)
from app.services.teaching_group_service import (
    GroupValidationError,
    build_population_snapshot,
    current_population_snapshot,
    population_registry_status,
)

from .access import can_use_workload_permission, require_workload_write
from .scopes import resolve_workload_scope


def _current_organization_id():
    organization = (
        OrganizationSettings.query
        .filter_by(is_active=True)
        .order_by(OrganizationSettings.id.asc())
        .first()
    )
    return organization.id if organization else None


def _require_bindings_read():
    if not can_use_workload_permission("workload.read", current_user):
        abort(403)


def _require_bindings_update():
    require_workload_write()
    if not can_use_workload_permission(
        "workload.plan_bindings.update",
        current_user,
    ):
        abort(403)


def _available_versions():
    query = TariffVersion.query.join(TariffCycle)
    organization_id = _current_organization_id()
    if organization_id is None:
        query = query.filter(TariffCycle.organization_id.is_(None))
    else:
        query = query.filter(
            TariffCycle.organization_id == organization_id
        )
    return query.order_by(
        (TariffVersion.status == "DRAFT").desc(),
        TariffCycle.academic_year_id.desc(),
        TariffVersion.version_no.desc(),
    ).all()


def _selected_version(versions, version_id):
    if version_id:
        return next(
            (item for item in versions if item.id == version_id),
            None,
        )
    return next(
        (item for item in versions if item.status == "DRAFT"),
        versions[0] if versions else None,
    )


def _snapshot_classes(snapshot):
    if snapshot is None:
        return []
    query = PopulationSnapshotClass.query.filter_by(
        population_snapshot_id=snapshot.id
    )
    scope = resolve_workload_scope(current_user)
    if not scope.unrestricted:
        query = query.filter(
            PopulationSnapshotClass.building_id.in_(scope.building_ids)
        )
    return query.order_by(
        PopulationSnapshotClass.grade_snapshot.asc(),
        PopulationSnapshotClass.name_snapshot.asc(),
    ).all()


def _curriculum_plans(version):
    if version is None:
        return []
    return (
        EducationPlan.query
        .filter_by(
            tariff_version_id=version.id,
            plan_kind="CURRICULUM",
            root_plan_id=None,
        )
        .order_by(
            EducationPlan.education_level.asc(),
            EducationPlan.name.asc(),
        )
        .all()
    )


def _compatible_plans(version, snapshot_class, plans=None):
    if version is None or snapshot_class is None:
        return []
    plans = plans if plans is not None else _curriculum_plans(version)
    return [
        plan
        for plan in plans
        if plan_matches_snapshot_class(plan, snapshot_class)
    ]


def _validate_binding_target(version, snapshot_class):
    if version not in _available_versions():
        abort(403)
    snapshot = current_population_snapshot(version.id)
    if (
        snapshot is None
        or snapshot_class.population_snapshot_id != snapshot.id
    ):
        abort(400)
    scope = resolve_workload_scope(current_user)
    if (
        not scope.unrestricted
        and snapshot_class.building_id not in scope.building_ids
    ):
        abort(403)


def _class_binding_rows(classes, version):
    all_plans = _curriculum_plans(version)
    rows = []
    unassigned_total = 0
    for snapshot_class in classes:
        plans = _compatible_plans(version, snapshot_class, all_plans)
        _, student_plan_ids = class_plan_allocations(
            snapshot_class,
            plans,
        )
        enrollment_ids = {
            item.id for item in snapshot_class.enrollments
        }
        assigned_count = sum(
            1 for item in enrollment_ids if item in student_plan_ids
        )
        assigned_plan_ids = {
            student_plan_ids[item]
            for item in enrollment_ids
            if item in student_plan_ids
        }
        uniform_plan_id = (
            next(iter(assigned_plan_ids))
            if (
                enrollment_ids
                and assigned_count == len(enrollment_ids)
                and len(assigned_plan_ids) == 1
            )
            else None
        )
        unassigned_count = len(enrollment_ids) - assigned_count
        unassigned_total += unassigned_count
        rows.append({
            "snapshot_class": snapshot_class,
            "plans": plans,
            "student_plan_ids": student_plan_ids,
            "assigned_count": assigned_count,
            "unassigned_count": unassigned_count,
            "uniform_plan_id": uniform_plan_id,
            "has_individual_assignments": (
                assigned_count > 0 and uniform_plan_id is None
            ),
        })
    return rows, all_plans, unassigned_total


def register_plan_binding_routes(workload_bp):
    @workload_bp.get("/plan-bindings/")
    @login_required
    def plan_bindings():
        _require_bindings_read()
        versions = _available_versions()
        version = _selected_version(
            versions,
            request.args.get("version_id", type=int),
        )
        snapshot = (
            current_population_snapshot(version.id)
            if version else None
        )
        registry_status = (
            population_registry_status(version, snapshot)
            if version else {
                "class_count": 0,
                "student_count": 0,
                "snapshot_class_count": 0,
                "snapshot_student_count": 0,
                "is_stale": False,
            }
        )
        classes = _snapshot_classes(snapshot)
        selected_class_id = request.args.get("class_id", type=int)
        selected_class = next(
            (item for item in classes if item.id == selected_class_id),
            None,
        )
        class_rows, plans, unassigned_count = _class_binding_rows(
            classes,
            version,
        )
        class_row_by_id = {
            item["snapshot_class"].id: item for item in class_rows
        }
        selected_class_row = (
            class_row_by_id.get(selected_class.id)
            if selected_class else None
        )

        enrollments = (
            PopulationSnapshotEnrollment.query
            .filter_by(
                population_snapshot_class_id=selected_class.id
            )
            .order_by(PopulationSnapshotEnrollment.fio_snapshot.asc())
            .all()
            if selected_class else []
        )
        can_update = (
            version is not None
            and version.status == "DRAFT"
            and is_feature_enabled(WORKLOAD_WRITE)
            and can_use_workload_permission(
                "workload.plan_bindings.update",
                current_user,
            )
        )
        return render_template(
            "workload/plan_bindings.html",
            versions=versions,
            selected_version=version,
            snapshot=snapshot,
            classes=classes,
            class_rows=class_rows,
            selected_class=selected_class,
            selected_class_row=selected_class_row,
            plans=plans,
            enrollments=enrollments,
            unassigned_count=unassigned_count,
            class_count=len(classes),
            registry_status=registry_status,
            can_update=can_update,
            academic_years=AcademicYear.query.order_by(
                AcademicYear.start_date.desc()
            ).all(),
        )

    @workload_bp.get("/plan-bindings/matrix")
    @login_required
    def plan_bindings_matrix():
        _require_bindings_read()
        versions = _available_versions()
        version = _selected_version(
            versions,
            request.args.get("version_id", type=int),
        )
        snapshot = (
            current_population_snapshot(version.id)
            if version else None
        )
        registry_status = (
            population_registry_status(version, snapshot)
            if version else {
                "class_count": 0,
                "student_count": 0,
                "snapshot_class_count": 0,
                "snapshot_student_count": 0,
                "is_stale": False,
            }
        )
        classes = _snapshot_classes(snapshot)
        plans = _curriculum_plans(version)
        _, _, unassigned_count = _class_binding_rows(classes, version)
        level_counts = {
            level: sum(
                1
                for item in classes
                if item.grade_snapshot in grades
            )
            for level, grades in EDUCATION_LEVEL_GRADES.items()
        }
        selected_level = (
            request.args.get("level") or ""
        ).strip().upper()
        if selected_level not in EDUCATION_LEVEL_GRADES:
            selected_level = next(
                (
                    level
                    for level in EDUCATION_LEVEL_GRADES
                    if level_counts[level]
                ),
                "NOO",
            )
        matrix = build_class_plan_matrix(
            snapshot,
            plans,
            selected_level,
        )
        return render_template(
            "workload/plan_bindings_matrix.html",
            versions=versions,
            selected_version=version,
            snapshot=snapshot,
            plans=plans,
            matrix=matrix,
            selected_level=selected_level,
            level_labels=EDUCATION_LEVEL_LABELS,
            level_counts=level_counts,
            class_count=len(classes),
            unassigned_count=unassigned_count,
            registry_status=registry_status,
            academic_years=AcademicYear.query.order_by(
                AcademicYear.start_date.desc()
            ).all(),
        )

    @workload_bp.post("/plan-bindings/snapshot/refresh")
    @login_required
    def plan_bindings_snapshot_refresh():
        _require_bindings_update()
        version_id = request.form.get("version_id", type=int)
        versions = _available_versions()
        version = _selected_version(versions, version_id)
        if version is None or version.id != version_id:
            abort(404)
        try:
            snapshot = build_population_snapshot(
                version,
                user_id=current_user.id,
            )
            db.session.commit()
        except GroupValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash(
                f"Контингент обновлён, снимок № {snapshot.revision_no}.",
                "success",
            )
        return redirect(url_for(
            "workload.plan_bindings",
            version_id=version.id,
        ))

    @workload_bp.post("/plan-bindings/class")
    @login_required
    def plan_bindings_assign_class():
        _require_bindings_update()
        version_id = request.form.get("version_id", type=int)
        class_id = request.form.get("class_id", type=int)
        plan_id = request.form.get("plan_id", type=int)
        version = db.session.get(TariffVersion, version_id)
        snapshot_class = db.session.get(PopulationSnapshotClass, class_id)
        if version is None or snapshot_class is None:
            abort(404)
        _validate_binding_target(version, snapshot_class)
        plans = _compatible_plans(version, snapshot_class)
        if plan_id is not None and plan_id not in {item.id for item in plans}:
            abort(400)
        assignments = (
            {item.id: plan_id for item in snapshot_class.enrollments}
            if plan_id is not None else {}
        )
        try:
            replace_class_plan_assignments(
                snapshot_class,
                plans,
                assignments,
                user_id=current_user.id,
            )
            db.session.commit()
        except PlanBindingValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash(
                f"Учебный план для {snapshot_class.name_snapshot} обновлён.",
                "success",
            )
        return redirect(url_for(
            "workload.plan_bindings",
            version_id=version.id,
        ))

    @workload_bp.post("/plan-bindings/student")
    @login_required
    def plan_bindings_assign_student():
        _require_bindings_update()
        version_id = request.form.get("version_id", type=int)
        class_id = request.form.get("class_id", type=int)
        enrollment_id = request.form.get("enrollment_id", type=int)
        plan_id = request.form.get("plan_id", type=int)
        version = db.session.get(TariffVersion, version_id)
        snapshot_class = db.session.get(PopulationSnapshotClass, class_id)
        enrollment = db.session.get(
            PopulationSnapshotEnrollment,
            enrollment_id,
        )
        if (
            version is None
            or snapshot_class is None
            or enrollment is None
            or enrollment.population_snapshot_class_id != snapshot_class.id
        ):
            abort(404)
        _validate_binding_target(version, snapshot_class)
        plans = _compatible_plans(version, snapshot_class)
        if plan_id is not None and plan_id not in {item.id for item in plans}:
            abort(400)
        _, assignments = class_plan_allocations(snapshot_class, plans)
        if plan_id is None:
            assignments.pop(enrollment.id, None)
        else:
            assignments[enrollment.id] = plan_id
        try:
            replace_class_plan_assignments(
                snapshot_class,
                plans,
                assignments,
                user_id=current_user.id,
            )
            db.session.commit()
        except PlanBindingValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        return redirect(url_for(
            "workload.plan_bindings",
            version_id=version.id,
            class_id=snapshot_class.id,
        ))

    @workload_bp.post("/plan-bindings/save")
    @login_required
    def plan_bindings_save():
        _require_bindings_update()
        version_id = request.form.get("version_id", type=int)
        class_id = request.form.get("class_id", type=int)
        plan_id = request.form.get("plan_id", type=int)
        version = db.session.get(TariffVersion, version_id)
        snapshot_class = db.session.get(PopulationSnapshotClass, class_id)
        plan = db.session.get(EducationPlan, plan_id)
        if version is None or snapshot_class is None or plan is None:
            abort(404)
        if version not in _available_versions():
            abort(403)
        if plan.tariff_version_id != version.id:
            abort(400)
        scope = resolve_workload_scope(current_user)
        if (
            not scope.unrestricted
            and snapshot_class.building_id not in scope.building_ids
        ):
            abort(403)

        selected_ids = set(
            request.form.getlist("snapshot_enrollment_ids", type=int)
        )
        try:
            replace_plan_binding_members(
                plan,
                snapshot_class,
                selected_ids,
                user_id=current_user.id,
            )
            db.session.commit()
        except PlanBindingValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Привязка учебного плана сохранена.", "success")
        return redirect(url_for(
            "workload.plan_bindings",
            version_id=version.id,
            class_id=snapshot_class.id,
            plan_id=plan.id,
        ))


__all__ = ["register_plan_binding_routes"]
