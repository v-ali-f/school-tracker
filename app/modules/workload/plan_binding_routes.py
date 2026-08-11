from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload

from app.core.extensions import db
from app.core.feature_flags import WORKLOAD_WRITE, is_feature_enabled
from app.models import (
    AcademicYear,
    EducationPlan,
    EducationPlanBinding,
    OrganizationSettings,
    PopulationSnapshotClass,
    PopulationSnapshotEnrollment,
    TariffCycle,
    TariffVersion,
)
from app.services.education_plan_binding_service import (
    PlanBindingValidationError,
    assign_class_plan,
    class_level_plan_ids,
    class_plan_option_ids,
    class_plan_allocations,
    effective_binding_member_ids,
    plan_matches_snapshot_class,
    replace_class_plan_assignments,
    replace_class_plan_options,
    replace_plan_binding_members,
)
from app.services.class_plan_matrix_service import (
    EDUCATION_LEVEL_GRADES,
    EDUCATION_LEVEL_LABELS,
    build_class_plan_matrix,
    snapshot_building_options,
)
from app.services.class_plan_matrix_export_service import (
    build_class_plan_matrix_pdf,
    build_class_plan_matrix_xlsx,
)
from app.services.teaching_group_service import (
    GroupValidationError,
    build_population_snapshot,
    current_population_snapshot,
    ensure_population_snapshot,
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


def _is_binding_ajax_request():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _binding_success_response(snapshot_class, plans, message):
    _, student_plan_ids = class_plan_allocations(snapshot_class, plans)
    if _is_binding_ajax_request():
        return jsonify({
            "ok": True,
            "message": message,
            "assigned_count": len(student_plan_ids),
            "student_count": len(snapshot_class.enrollments),
        })
    flash(message, "success")
    return None


def _binding_error_response(message):
    if _is_binding_ajax_request():
        return jsonify({
            "ok": False,
            "message": message,
        }), 422
    flash(message, "danger")
    return None


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
    query = (
        PopulationSnapshotClass.query
        .options(selectinload(PopulationSnapshotClass.enrollments))
        .filter_by(population_snapshot_id=snapshot.id)
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


def _binding_filter_selection(requested_level, requested_grade):
    selected_level = (requested_level or "").strip().upper() or None
    if selected_level not in EDUCATION_LEVEL_GRADES:
        selected_level = None

    grade_options = list(
        EDUCATION_LEVEL_GRADES.get(selected_level, range(1, 12))
    )
    try:
        selected_grade = int(requested_grade)
    except (TypeError, ValueError):
        selected_grade = None
    if selected_grade not in grade_options:
        selected_grade = None
    return selected_level, selected_grade, grade_options


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
    class_ids = [item.id for item in classes]
    plan_ids = [item.id for item in all_plans]
    bindings_by_class = {}
    if class_ids and plan_ids:
        bindings = (
            EducationPlanBinding.query
            .options(selectinload(EducationPlanBinding.members))
            .filter(
                EducationPlanBinding.population_snapshot_class_id.in_(
                    class_ids
                ),
                EducationPlanBinding.education_plan_id.in_(plan_ids),
            )
            .all()
        )
        for binding in bindings:
            bindings_by_class.setdefault(
                binding.population_snapshot_class_id,
                [],
            ).append(binding)
    rows = []
    unassigned_total = 0
    for snapshot_class in classes:
        plans = _compatible_plans(version, snapshot_class, all_plans)
        compatible_plan_ids = {item.id for item in plans}
        class_bindings = [
            item
            for item in bindings_by_class.get(snapshot_class.id, ())
            if item.education_plan_id in compatible_plan_ids
        ]
        whole_class_plan_ids = {
            item.education_plan_id
            for item in class_bindings
            if item.binding_mode == "CLASS"
        }
        selected_plan_ids = {
            item.education_plan_id for item in class_bindings
        }
        is_multi_plan_class = snapshot_class.grade_snapshot in {10, 11}
        enrollment_ids = {
            item.id for item in snapshot_class.enrollments
        }
        student_plan_ids = {}
        for binding in class_bindings:
            for enrollment_id in effective_binding_member_ids(
                binding,
                enrollment_ids,
            ):
                student_plan_ids[enrollment_id] = (
                    binding.education_plan_id
                )
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
        if not enrollment_ids and len(whole_class_plan_ids) == 1:
            uniform_plan_id = next(iter(whole_class_plan_ids))
        unassigned_count = len(enrollment_ids) - assigned_count
        unassigned_total += unassigned_count
        rows.append({
            "snapshot_class": snapshot_class,
            "plans": plans,
            "student_plans": (
                [
                    item for item in plans
                    if item.id in selected_plan_ids
                ]
                if is_multi_plan_class else plans
            ),
            "selected_plan_ids": selected_plan_ids,
            "is_multi_plan_class": is_multi_plan_class,
            "student_plan_ids": student_plan_ids,
            "assigned_count": assigned_count,
            "unassigned_count": unassigned_count,
            "uniform_plan_id": uniform_plan_id,
            "has_individual_assignments": (
                assigned_count > 0 and uniform_plan_id is None
            ),
        })
    return rows, all_plans, unassigned_total


def _matrix_context(
    version_id,
    requested_level,
    requested_grade=None,
    requested_building_id=None,
):
    versions = _available_versions()
    version = _selected_version(versions, version_id)
    snapshot = (
        ensure_population_snapshot(
            version,
            user_id=current_user.id,
        )[0]
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
    scope = resolve_workload_scope(current_user)
    allowed_building_ids = (
        None if scope.unrestricted else set(scope.building_ids)
    )
    building_options = snapshot_building_options(
        snapshot,
        allowed_building_ids,
    )
    building_ids = {item["id"] for item in building_options}
    try:
        selected_building_id = int(requested_building_id)
    except (TypeError, ValueError):
        selected_building_id = None
    if selected_building_id not in building_ids:
        selected_building_id = None

    def matches_selected_building(item):
        if selected_building_id is None:
            return True
        if selected_building_id < 0:
            return item.building_id is None
        return item.building_id == selected_building_id

    level_counts = {
        level: sum(
            1
            for item in classes
            if (
                item.grade_snapshot in grades
                and matches_selected_building(item)
            )
        )
        for level, grades in EDUCATION_LEVEL_GRADES.items()
    }
    selected_level = (requested_level or "").strip().upper()
    if selected_level not in EDUCATION_LEVEL_GRADES:
        selected_level = next(
            (
                level
                for level in EDUCATION_LEVEL_GRADES
                if level_counts[level]
            ),
            "NOO",
        )
    level_grades = sorted(EDUCATION_LEVEL_GRADES[selected_level])
    try:
        selected_grade = int(requested_grade)
    except (TypeError, ValueError):
        selected_grade = None
    if selected_grade not in EDUCATION_LEVEL_GRADES[selected_level]:
        selected_grade = None
    matrix = build_class_plan_matrix(
        snapshot,
        plans,
        selected_level,
        grade=selected_grade,
        building_id=selected_building_id,
        allowed_building_ids=allowed_building_ids,
    )
    unassigned_count = sum(
        column["student_count"]
        for column in matrix["columns"]
        if column["is_unassigned"]
    )
    building_tone_by_id = {
        item["id"]: item.get("matrix_tone", 0)
        for item in building_options
    }
    return {
        "versions": versions,
        "selected_version": version,
        "snapshot": snapshot,
        "plans": plans,
        "matrix": matrix,
        "selected_level": selected_level,
        "selected_grade": selected_grade,
        "selected_building_id": selected_building_id,
        "building_options": building_options,
        "building_tone_by_id": building_tone_by_id,
        "level_grades": level_grades,
        "level_labels": EDUCATION_LEVEL_LABELS,
        "level_counts": level_counts,
        "class_count": matrix["class_count"],
        "unassigned_count": unassigned_count,
        "registry_status": registry_status,
        "academic_years": AcademicYear.query.order_by(
            AcademicYear.start_date.desc()
        ).all(),
    }


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
        selected_level, selected_grade, grade_options = (
            _binding_filter_selection(
                request.args.get("level"),
                request.args.get("grade"),
            )
        )
        classes = [
            item
            for item in _snapshot_classes(snapshot)
            if (
                (
                    selected_level is None
                    or item.grade_snapshot
                    in EDUCATION_LEVEL_GRADES[selected_level]
                )
                and (
                    selected_grade is None
                    or item.grade_snapshot == selected_grade
                )
            )
        ]
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
            selected_level=selected_level,
            selected_grade=selected_grade,
            grade_options=grade_options,
            level_labels=EDUCATION_LEVEL_LABELS,
            academic_years=AcademicYear.query.order_by(
                AcademicYear.start_date.desc()
            ).all(),
        )

    @workload_bp.get("/plan-bindings/matrix")
    @login_required
    def plan_bindings_matrix():
        _require_bindings_read()
        context = _matrix_context(
            request.args.get("version_id", type=int),
            request.args.get("level"),
            request.args.get("grade"),
            request.args.get("building_id"),
        )
        return render_template(
            "workload/plan_bindings_matrix.html",
            **context,
        )

    @workload_bp.get("/plan-bindings/matrix/export.xlsx")
    @login_required
    def plan_bindings_matrix_export_xlsx():
        _require_bindings_read()
        context = _matrix_context(
            request.args.get("version_id", type=int),
            request.args.get("level"),
            request.args.get("grade"),
            request.args.get("building_id"),
        )
        version = context["selected_version"]
        if version is None:
            abort(404)
        year_name = version.tariff_cycle.academic_year.name
        stream = build_class_plan_matrix_xlsx(
            context["matrix"],
            year_name,
        )
        grade_suffix = (
            f"_{context['selected_grade']}_grade"
            if context["selected_grade"] else ""
        )
        building_suffix = (
            f"_building_{context['selected_building_id']}"
            if context["selected_building_id"] else ""
        )
        return send_file(
            stream,
            as_attachment=True,
            download_name=(
                f"Altair_class_plan_summary_"
                f"{year_name.replace('/', '-')}_"
                f"{context['selected_level']}"
                f"{grade_suffix}"
                f"{building_suffix}"
                f".xlsx"
            ),
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    @workload_bp.get("/plan-bindings/matrix/export.pdf")
    @login_required
    def plan_bindings_matrix_export_pdf():
        _require_bindings_read()
        context = _matrix_context(
            request.args.get("version_id", type=int),
            request.args.get("level"),
            request.args.get("grade"),
            request.args.get("building_id"),
        )
        version = context["selected_version"]
        if version is None:
            abort(404)
        year_name = version.tariff_cycle.academic_year.name
        stream = build_class_plan_matrix_pdf(
            context["matrix"],
            year_name,
        )
        grade_suffix = (
            f"_{context['selected_grade']}_grade"
            if context["selected_grade"] else ""
        )
        building_suffix = (
            f"_building_{context['selected_building_id']}"
            if context["selected_building_id"] else ""
        )
        return send_file(
            stream,
            as_attachment=True,
            download_name=(
                f"Altair_class_plan_summary_"
                f"{year_name.replace('/', '-')}_"
                f"{context['selected_level']}"
                f"{grade_suffix}"
                f"{building_suffix}"
                f".pdf"
            ),
            mimetype="application/pdf",
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
                "Состав классов синхронизирован со сводным контингентом.",
                "success",
            )
        return redirect(url_for(
            "workload.plan_bindings",
            version_id=version.id,
            level=request.form.get("level") or None,
            grade=request.form.get("grade", type=int),
        ))

    @workload_bp.post("/plan-bindings/class")
    @login_required
    def plan_bindings_assign_class():
        _require_bindings_update()
        version_id = request.form.get("version_id", type=int)
        if "plan_id" not in request.form:
            response = _binding_error_response(
                "Не передан выбранный учебный план. Обновите страницу."
            )
            if response is not None:
                return response
            return redirect(url_for(
                "workload.plan_bindings",
                version_id=version_id,
                level=request.form.get("level") or None,
                grade=request.form.get("grade", type=int),
            ))
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
        try:
            assign_class_plan(
                snapshot_class,
                plans,
                plan_id,
                user_id=current_user.id,
            )
            db.session.commit()
        except PlanBindingValidationError as exc:
            db.session.rollback()
            response = _binding_error_response(str(exc))
            if response is not None:
                return response
        else:
            response = _binding_success_response(
                snapshot_class,
                plans,
                (
                    f"Учебный план для "
                    f"{snapshot_class.name_snapshot} сохранён."
                ),
            )
            if response is not None:
                return response
        return redirect(url_for(
            "workload.plan_bindings",
            version_id=version.id,
            level=request.form.get("level") or None,
            grade=request.form.get("grade", type=int),
        ))

    @workload_bp.post("/plan-bindings/class-plans")
    @login_required
    def plan_bindings_assign_class_plans():
        _require_bindings_update()
        version_id = request.form.get("version_id", type=int)
        class_id = request.form.get("class_id", type=int)
        version = db.session.get(TariffVersion, version_id)
        snapshot_class = db.session.get(PopulationSnapshotClass, class_id)
        if version is None or snapshot_class is None:
            abort(404)
        _validate_binding_target(version, snapshot_class)
        plans = _compatible_plans(version, snapshot_class)
        selected_plan_ids = set(
            request.form.getlist("plan_ids", type=int)
        )
        try:
            replace_class_plan_options(
                snapshot_class,
                plans,
                selected_plan_ids,
                user_id=current_user.id,
            )
            db.session.commit()
        except PlanBindingValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash(
                f"Набор учебных планов для "
                f"{snapshot_class.name_snapshot} сохранён.",
                "success",
            )
        return redirect(url_for(
            "workload.plan_bindings",
            version_id=version.id,
            level=request.form.get("level") or None,
            grade=request.form.get("grade", type=int),
            class_id=snapshot_class.id,
        ))

    @workload_bp.post("/plan-bindings/student")
    @login_required
    def plan_bindings_assign_student():
        _require_bindings_update()
        version_id = request.form.get("version_id", type=int)
        if "plan_id" not in request.form:
            response = _binding_error_response(
                "Не передан выбранный учебный план. Обновите страницу."
            )
            if response is not None:
                return response
            return redirect(url_for(
                "workload.plan_bindings",
                version_id=version_id,
                level=request.form.get("level") or None,
                grade=request.form.get("grade", type=int),
            ))
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
        if snapshot_class.grade_snapshot in {10, 11}:
            selected_plan_ids = class_plan_option_ids(
                snapshot_class,
                plans,
            )
            plans = [
                item for item in plans
                if item.id in selected_plan_ids
            ]
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
            response = _binding_error_response(str(exc))
            if response is not None:
                return response
        else:
            response = _binding_success_response(
                snapshot_class,
                plans,
                f"Учебный план ученика {enrollment.fio_snapshot} сохранён.",
            )
            if response is not None:
                return response
        return redirect(url_for(
            "workload.plan_bindings",
            version_id=version.id,
            level=request.form.get("level") or None,
            grade=request.form.get("grade", type=int),
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
            level=request.form.get("level") or None,
            grade=request.form.get("grade", type=int),
            class_id=snapshot_class.id,
            plan_id=plan.id,
        ))


__all__ = ["register_plan_binding_routes"]
