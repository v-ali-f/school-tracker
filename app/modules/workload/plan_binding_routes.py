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
    replace_plan_binding_members,
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


def _compatible_plans(version, snapshot_class):
    if version is None or snapshot_class is None:
        return []
    plans = (
        EducationPlan.query
        .filter_by(
            tariff_version_id=version.id,
            plan_kind="CURRICULUM",
        )
        .order_by(
            EducationPlan.education_level.asc(),
            EducationPlan.name.asc(),
        )
        .all()
    )
    return [
        plan
        for plan in plans
        if plan_matches_snapshot_class(plan, snapshot_class)
    ]


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
            classes[0] if classes else None,
        )
        plans = _compatible_plans(version, selected_class)
        selected_plan_id = request.args.get("plan_id", type=int)
        selected_plan = next(
            (item for item in plans if item.id == selected_plan_id),
            plans[0] if plans else None,
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
        allocations, student_plan_ids = (
            class_plan_allocations(selected_class, plans)
            if selected_class else ({}, {})
        )
        plan_by_id = {plan.id: plan for plan in plans}
        selected_member_ids = (
            allocations.get(selected_plan.id, set())
            if selected_plan else set()
        )
        plan_counts = {
            plan.id: len(allocations.get(plan.id, set()))
            for plan in plans
        }
        unassigned_count = sum(
            1
            for enrollment in enrollments
            if enrollment.id not in student_plan_ids
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
            selected_class=selected_class,
            plans=plans,
            selected_plan=selected_plan,
            enrollments=enrollments,
            allocations=allocations,
            student_plan_ids=student_plan_ids,
            selected_member_ids=selected_member_ids,
            plan_counts=plan_counts,
            plan_by_id=plan_by_id,
            unassigned_count=unassigned_count,
            class_count=len(classes),
            registry_status=registry_status,
            can_update=can_update,
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
