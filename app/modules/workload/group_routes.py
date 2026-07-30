from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.core.feature_flags import WORKLOAD_WRITE, is_feature_enabled
from app.models import (
    Building,
    Department,
    EducationActivity,
    EducationPlan,
    EducationPlanLine,
    GROUP_COMPOSITION_MODES,
    GROUP_COMPOSITION_MODE_LABELS,
    OrganizationSettings,
    PopulationSnapshotClass,
    PopulationSnapshotEnrollment,
    TariffCycle,
    TariffVersion,
    TEACHING_GROUP_STATUSES,
    TEACHING_GROUP_STATUS_LABELS,
    TEACHING_GROUP_TYPES,
    TEACHING_GROUP_TYPE_LABELS,
    TeachingGroup,
)
from app.services.teaching_group_service import (
    GROUP_TYPES_BY_PLAN_KIND,
    GroupValidationError,
    add_group_history,
    build_population_snapshot,
    change_group_status,
    current_population_snapshot,
    group_coverage,
    normalize_group_code,
    replace_group_composition,
    require_group_editable,
    touch_group,
    validate_group_members,
    validate_group_period,
    validate_group_sources,
    validate_group_type,
    validate_member_conflicts,
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


def _require_groups_read():
    if not can_use_workload_permission("workload.read", current_user):
        abort(403)


def _require_groups_update():
    require_workload_write()
    if not can_use_workload_permission(
        "workload.groups.update",
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
        raise GroupValidationError(f"Укажите корректную дату: {label}.") from exc


def _parse_nonnegative_int(value, label, *, required=False):
    text = str(value or "").strip()
    if not text:
        if required:
            raise GroupValidationError(f"Укажите {label}.")
        return None
    try:
        number = int(text)
    except ValueError as exc:
        raise GroupValidationError(
            f"Поле «{label}» должно быть целым числом."
        ) from exc
    if number < 0:
        raise GroupValidationError(
            f"Поле «{label}» не может быть отрицательным."
        )
    return number


def _get_group(group_id, *, for_update=False):
    group = TeachingGroup.query.get_or_404(group_id)
    if for_update:
        _require_groups_update()
    else:
        _require_groups_read()
    scope = resolve_workload_scope(current_user)
    if not scope.unrestricted:
        if group.building_id is None or group.building_id not in scope.building_ids:
            abort(403)
    return group


def _available_plan_lines():
    organization_id = _current_organization_id()
    query = (
        EducationPlanLine.query
        .join(EducationPlan)
        .join(TariffVersion)
        .join(TariffCycle)
        .filter(
            TariffVersion.status == "DRAFT",
            EducationPlan.status.in_(("DRAFT", "READY")),
        )
    )
    if organization_id is None:
        query = query.filter(TariffCycle.organization_id.is_(None))
    else:
        query = query.filter(TariffCycle.organization_id == organization_id)
    scope = resolve_workload_scope(current_user)
    if not scope.unrestricted:
        query = query.filter(
            EducationPlan.building_id.in_(scope.building_ids)
        )
    return (
        query
        .join(EducationActivity)
        .order_by(
            EducationActivity.name.asc(),
            EducationPlanLine.sort_order.asc(),
        )
        .all()
    )


def _snapshot_for_line(plan_line):
    return current_population_snapshot(
        plan_line.education_plan.tariff_version_id
    )


def _snapshot_data(snapshot):
    if snapshot is None:
        return [], []
    classes = (
        PopulationSnapshotClass.query
        .filter_by(population_snapshot_id=snapshot.id)
        .order_by(
            PopulationSnapshotClass.grade_snapshot.asc(),
            PopulationSnapshotClass.name_snapshot.asc(),
        )
        .all()
    )
    class_ids = [item.id for item in classes]
    enrollments = (
        PopulationSnapshotEnrollment.query
        .filter(
            PopulationSnapshotEnrollment.population_snapshot_class_id.in_(
                class_ids
            )
        )
        .order_by(PopulationSnapshotEnrollment.fio_snapshot.asc())
        .all()
        if class_ids else []
    )
    return classes, enrollments


def _group_form_payload(plan_line, snapshot, *, exclude_group_id=None):
    if snapshot is None:
        raise GroupValidationError(
            "Сначала сформируйте снимок контингента для этой версии."
        )
    if snapshot.tariff_version_id != plan_line.education_plan.tariff_version_id:
        raise GroupValidationError(
            "Снимок контингента относится к другой версии."
        )

    group_type = (request.form.get("group_type") or "").strip().upper()
    validate_group_type(plan_line, group_type)
    code = normalize_group_code(request.form.get("code"))
    name = " ".join((request.form.get("name") or "").split())
    if not code or not name:
        raise GroupValidationError("Укажите код и название группы.")
    composition_mode = (
        request.form.get("composition_mode") or ""
    ).strip().upper()
    planned_size = _parse_nonnegative_int(
        request.form.get("planned_size"),
        "плановую численность",
    )
    actual_size = _parse_nonnegative_int(
        request.form.get("actual_size"),
        "фактическую численность",
        required=composition_mode == "COUNT_ONLY",
    )
    valid_from = _parse_date(
        request.form.get("valid_from"),
        "начало действия",
    )
    valid_to = _parse_date(
        request.form.get("valid_to"),
        "окончание действия",
    )
    validate_group_period(plan_line, valid_from, valid_to)

    source_class_ids = {
        int(value)
        for value in request.form.getlist("snapshot_class_ids")
        if value.isdigit()
    }
    snapshot_classes = (
        PopulationSnapshotClass.query
        .filter(
            PopulationSnapshotClass.population_snapshot_id == snapshot.id,
            PopulationSnapshotClass.id.in_(source_class_ids),
        )
        .all()
        if source_class_ids else []
    )
    validate_group_sources(group_type, snapshot_classes)

    member_ids = {
        int(value)
        for value in request.form.getlist("snapshot_enrollment_ids")
        if value.isdigit()
    }
    snapshot_enrollments = (
        PopulationSnapshotEnrollment.query
        .filter(
            PopulationSnapshotEnrollment.id.in_(member_ids),
            PopulationSnapshotEnrollment.population_snapshot_class_id.in_(
                source_class_ids
            ),
        )
        .all()
        if member_ids else []
    )
    if (
        composition_mode == "PERSONAL"
        and group_type == "CLASS"
    ):
        snapshot_enrollments = (
            PopulationSnapshotEnrollment.query
            .filter(
                PopulationSnapshotEnrollment.population_snapshot_class_id.in_(
                    source_class_ids
                )
            )
            .all()
        )
    validate_group_members(
        group_type,
        composition_mode,
        snapshot_classes,
        snapshot_enrollments,
        actual_size,
    )
    validate_member_conflicts(
        tariff_version_id=plan_line.education_plan.tariff_version_id,
        plan_line_id=plan_line.id,
        member_entries=snapshot_enrollments,
        valid_from=valid_from,
        valid_to=valid_to,
        exclude_group_id=exclude_group_id,
    )

    building_id = request.form.get("building_id", type=int)
    if building_id and db.session.get(Building, building_id) is None:
        raise GroupValidationError("Выберите существующее здание.")
    department_id = request.form.get("department_id", type=int)
    if department_id and db.session.get(Department, department_id) is None:
        raise GroupValidationError("Выберите существующую кафедру.")

    return {
        "group_type": group_type,
        "code": code,
        "name": name,
        "composition_mode": composition_mode,
        "planned_size": planned_size,
        "actual_size": actual_size,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "building_id": building_id,
        "department_id": department_id,
        "snapshot_classes": snapshot_classes,
        "snapshot_enrollments": snapshot_enrollments,
    }


def _render_group_form(group=None, selected_plan_line=None):
    plan_lines = _available_plan_lines()
    if selected_plan_line is None and plan_lines:
        selected_id = request.args.get("plan_line_id", type=int)
        selected_plan_line = next(
            (item for item in plan_lines if item.id == selected_id),
            plan_lines[0],
        )
    if group and group.source_classes:
        snapshot = (
            group.source_classes[0]
            .population_snapshot_class
            .population_snapshot
        )
    else:
        snapshot = (
            _snapshot_for_line(selected_plan_line)
            if selected_plan_line else None
        )
    snapshot_classes, snapshot_enrollments = _snapshot_data(snapshot)
    allowed_group_types = (
        tuple(
            group_type
            for group_type in TEACHING_GROUP_TYPES
            if group_type in GROUP_TYPES_BY_PLAN_KIND[
                selected_plan_line.education_plan.plan_kind
            ]
        )
        if selected_plan_line else TEACHING_GROUP_TYPES
    )
    return render_template(
        "workload/group_form.html",
        group=group,
        plan_lines=plan_lines,
        selected_plan_line=selected_plan_line,
        snapshot=snapshot,
        snapshot_classes=snapshot_classes,
        snapshot_enrollments=snapshot_enrollments,
        group_types=allowed_group_types,
        group_type_labels=TEACHING_GROUP_TYPE_LABELS,
        composition_modes=GROUP_COMPOSITION_MODES,
        composition_mode_labels=GROUP_COMPOSITION_MODE_LABELS,
        buildings=Building.query.order_by(Building.name.asc()).all(),
        departments=Department.query.order_by(Department.name.asc()).all(),
        selected_class_ids={
            item.population_snapshot_class_id
            for item in group.source_classes
        } if group else set(),
        selected_member_ids={
            item.snapshot_enrollment_id
            for item in group.members
        } if group else set(),
    )


def register_group_routes(workload_bp):
    @workload_bp.get("/groups/")
    @login_required
    def groups():
        _require_groups_read()
        organization_id = _current_organization_id()
        query = (
            TeachingGroup.query
            .join(TariffVersion)
            .join(TariffCycle)
        )
        if organization_id is None:
            query = query.filter(TariffCycle.organization_id.is_(None))
        else:
            query = query.filter(
                TariffCycle.organization_id == organization_id
            )
        scope = resolve_workload_scope(current_user)
        if not scope.unrestricted:
            query = query.filter(
                TeachingGroup.building_id.in_(scope.building_ids)
            )

        group_type = (
            request.args.get("group_type") or ""
        ).strip().upper()
        status = (request.args.get("status") or "").strip().upper()
        activity_id = request.args.get("activity_id", type=int)
        if group_type in TEACHING_GROUP_TYPES:
            query = query.filter(TeachingGroup.group_type == group_type)
        if status in TEACHING_GROUP_STATUSES:
            query = query.filter(TeachingGroup.status == status)
        if activity_id:
            query = query.filter(
                TeachingGroup.education_activity_id == activity_id
            )
        items = query.order_by(
            TeachingGroup.status.asc(),
            TeachingGroup.name.asc(),
        ).all()
        selected_group_id = request.args.get("selected_group_id", type=int)
        selected_group = next(
            (item for item in items if item.id == selected_group_id),
            items[0] if items else None,
        )
        group_type_counts = {
            item: sum(1 for group in items if group.group_type == item)
            for item in TEACHING_GROUP_TYPES
        }
        group_status_counts = {
            item: sum(1 for group in items if group.status == item)
            for item in TEACHING_GROUP_STATUSES
        }

        draft_versions = (
            TariffVersion.query
            .join(TariffCycle)
            .filter(TariffVersion.status == "DRAFT")
        )
        if organization_id is None:
            draft_versions = draft_versions.filter(
                TariffCycle.organization_id.is_(None)
            )
        else:
            draft_versions = draft_versions.filter(
                TariffCycle.organization_id == organization_id
            )
        versions = draft_versions.all()
        snapshots = {
            version.id: current_population_snapshot(version.id)
            for version in versions
        }
        can_update = (
            is_feature_enabled(WORKLOAD_WRITE)
            and can_use_workload_permission(
                "workload.groups.update",
                current_user,
            )
        )
        return render_template(
            "workload/groups.html",
            groups=items,
            group_types=TEACHING_GROUP_TYPES,
            group_type_labels=TEACHING_GROUP_TYPE_LABELS,
            group_statuses=TEACHING_GROUP_STATUSES,
            group_status_labels=TEACHING_GROUP_STATUS_LABELS,
            composition_mode_labels=GROUP_COMPOSITION_MODE_LABELS,
            selected_group_type=group_type,
            selected_status=status,
            selected_activity_id=activity_id,
            activities=EducationActivity.query.order_by(
                EducationActivity.name.asc()
            ).all(),
            versions=versions,
            snapshots=snapshots,
            selected_group=selected_group,
            selected_version=(
                selected_group.tariff_version
                if selected_group else (versions[0] if versions else None)
            ),
            group_type_counts=group_type_counts,
            group_status_counts=group_status_counts,
            can_update=can_update,
        )

    @workload_bp.post("/groups/snapshot/refresh")
    @login_required
    def group_snapshot_refresh():
        _require_groups_update()
        version_id = request.form.get("tariff_version_id", type=int)
        version = db.session.get(TariffVersion, version_id)
        if version is None:
            flash("Выберите рабочую версию.", "danger")
            return redirect(url_for("workload.groups"))
        organization_id = _current_organization_id()
        if version.tariff_cycle.organization_id != organization_id:
            abort(403)
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
                f"Снимок контингента № {snapshot.revision_no} сформирован.",
                "success",
            )
        return redirect(url_for("workload.groups"))

    @workload_bp.route("/groups/new", methods=["GET", "POST"])
    @login_required
    def group_create():
        _require_groups_update()
        plan_lines = _available_plan_lines()
        selected_id = (
            request.form.get("source_plan_line_id", type=int)
            if request.method == "POST"
            else request.args.get("plan_line_id", type=int)
        )
        selected_plan_line = next(
            (item for item in plan_lines if item.id == selected_id),
            None,
        )
        if (
            request.method == "GET"
            and selected_plan_line is None
            and plan_lines
        ):
            selected_plan_line = plan_lines[0]
        if request.method == "POST":
            try:
                if selected_plan_line is None:
                    raise GroupValidationError(
                        "Выберите строку учебного плана."
                    )
                snapshot = _snapshot_for_line(selected_plan_line)
                payload = _group_form_payload(
                    selected_plan_line,
                    snapshot,
                )
                group = TeachingGroup(
                    tariff_version_id=(
                        selected_plan_line.education_plan.tariff_version_id
                    ),
                    education_activity_id=(
                        selected_plan_line.education_activity_id
                    ),
                    source_plan_line_id=selected_plan_line.id,
                    group_type=payload["group_type"],
                    code=payload["code"],
                    name=payload["name"],
                    composition_mode=payload["composition_mode"],
                    building_id=payload["building_id"],
                    department_id=payload["department_id"],
                    planned_size=payload["planned_size"],
                    actual_size=0,
                    valid_from=payload["valid_from"],
                    valid_to=payload["valid_to"],
                    status="DRAFT",
                    created_by_user_id=current_user.id,
                    updated_by_user_id=current_user.id,
                )
                db.session.add(group)
                db.session.flush()
                replace_group_composition(
                    group,
                    snapshot_classes=payload["snapshot_classes"],
                    snapshot_enrollments=payload["snapshot_enrollments"],
                    actual_size=payload["actual_size"],
                    user_id=current_user.id,
                )
                add_group_history(
                    group,
                    "CREATED",
                    current_user.id,
                    {
                        "source_plan_line_id": selected_plan_line.id,
                        "actual_size": group.actual_size,
                    },
                )
                db.session.commit()
            except GroupValidationError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
            except IntegrityError:
                db.session.rollback()
                flash(
                    "Группа с таким кодом уже существует в этой версии.",
                    "danger",
                )
            else:
                flash("Группа создана.", "success")
                return redirect(
                    url_for("workload.group_detail", group_id=group.id)
                )
        return _render_group_form(
            selected_plan_line=selected_plan_line,
        )

    @workload_bp.get("/groups/<int:group_id>")
    @login_required
    def group_detail(group_id):
        group = _get_group(group_id)
        can_manage = (
            is_feature_enabled(WORKLOAD_WRITE)
            and can_use_workload_permission(
                "workload.groups.update",
                current_user,
            )
            and group.tariff_version.status == "DRAFT"
        )
        can_update = can_manage and group.status == "DRAFT"
        coverage = group_coverage(group.source_plan_line_id)
        return render_template(
            "workload/group_detail.html",
            group=group,
            group_type_labels=TEACHING_GROUP_TYPE_LABELS,
            group_status_labels=TEACHING_GROUP_STATUS_LABELS,
            composition_mode_labels=GROUP_COMPOSITION_MODE_LABELS,
            coverage=coverage,
            can_update=can_update,
            can_manage=can_manage,
        )

    @workload_bp.route(
        "/groups/<int:group_id>/edit",
        methods=["GET", "POST"],
    )
    @login_required
    def group_edit(group_id):
        group = _get_group(group_id, for_update=True)
        try:
            require_group_editable(
                group,
                expected_revision=(
                    request.form.get("revision", type=int)
                    if request.method == "POST" else None
                ),
            )
        except GroupValidationError as exc:
            flash(str(exc), "danger")
            return redirect(
                url_for("workload.group_detail", group_id=group.id)
            )
        plan_line = group.source_plan_line
        if request.method == "POST":
            try:
                snapshot = (
                    group.source_classes[0]
                    .population_snapshot_class
                    .population_snapshot
                    if group.source_classes else _snapshot_for_line(plan_line)
                )
                payload = _group_form_payload(
                    plan_line,
                    snapshot,
                    exclude_group_id=group.id,
                )
                group.group_type = payload["group_type"]
                group.code = payload["code"]
                group.name = payload["name"]
                group.composition_mode = payload["composition_mode"]
                group.building_id = payload["building_id"]
                group.department_id = payload["department_id"]
                group.planned_size = payload["planned_size"]
                group.valid_from = payload["valid_from"]
                group.valid_to = payload["valid_to"]
                replace_group_composition(
                    group,
                    snapshot_classes=payload["snapshot_classes"],
                    snapshot_enrollments=payload["snapshot_enrollments"],
                    actual_size=payload["actual_size"],
                    user_id=current_user.id,
                )
                touch_group(
                    group,
                    user_id=current_user.id,
                    event_code="UPDATED",
                    details={"actual_size": group.actual_size},
                )
                db.session.commit()
            except GroupValidationError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
            except IntegrityError:
                db.session.rollback()
                flash(
                    "Группа с таким кодом уже существует в этой версии.",
                    "danger",
                )
            else:
                flash("Группа обновлена.", "success")
                return redirect(
                    url_for("workload.group_detail", group_id=group.id)
                )
        return _render_group_form(
            group=group,
            selected_plan_line=plan_line,
        )

    @workload_bp.post("/groups/<int:group_id>/status")
    @login_required
    def group_change_status(group_id):
        group = _get_group(group_id, for_update=True)
        try:
            change_group_status(
                group,
                request.form.get("status"),
                user_id=current_user.id,
                expected_revision=request.form.get("revision", type=int),
                close_reason=request.form.get("close_reason"),
                close_date=_parse_date(
                    request.form.get("close_date"),
                    "дата закрытия",
                ),
            )
            db.session.commit()
        except GroupValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Статус группы изменён.", "success")
        return redirect(
            url_for("workload.group_detail", group_id=group.id)
        )

    @workload_bp.post("/groups/<int:group_id>/delete")
    @login_required
    def group_delete(group_id):
        group = _get_group(group_id, for_update=True)
        try:
            require_group_editable(
                group,
                expected_revision=request.form.get("revision", type=int),
            )
            db.session.delete(group)
            db.session.commit()
        except GroupValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Черновая группа удалена.", "success")
        return redirect(url_for("workload.groups"))


__all__ = ["register_group_routes"]
