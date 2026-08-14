from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from flask import current_app

from app.core.extensions import db
from app.models import (
    AcademicYear,
    EducationActivity,
    OrganizationSettings,
    Subject,
    TariffCalculationRun,
    TariffLine,
    TariffVersion,
    TeacherLoad,
    WorkloadAssignment,
    WorkloadReconciliationItem,
    WorkloadReconciliationRun,
    WorkloadSourceSetting,
    WorkloadSourceTransition,
)
from app.services.tariff_calculation_service import latest_successful_run
from app.services.teaching_group_display_service import (
    teaching_group_assignment_label,
    teaching_group_class_label,
)


ZERO = Decimal("0")
HOUR_QUANTUM = Decimal("0.001")
DEFAULT_TOLERANCE = Decimal("0.001")


class WorkloadIntegrationError(ValueError):
    pass


@dataclass(frozen=True)
class WorkloadSourceState:
    configured_mode: str
    effective_mode: str
    flag_enabled: bool
    setting: WorkloadSourceSetting | None
    tariff_version: TariffVersion | None
    latest_reconciliation: WorkloadReconciliationRun | None


@dataclass
class DepartmentLoadRow:
    id: int
    teacher: object
    subject: object
    academic_year: object
    department: object
    building: object
    class_name: str | None
    grade: int | None
    group_name: str | None
    hours: float
    subject_name: str
    building_name: str | None
    is_whole_class: bool
    is_meta_group: bool
    teacher_total_hours: float
    plan_kind: str = "CURRICULUM"
    is_readonly: bool = True
    source_kind: str = "INTERNAL"
    class_label: str | None = None
    group_label: str | None = None


def active_organization_id():
    organization = (
        OrganizationSettings.query
        .filter_by(is_active=True)
        .order_by(OrganizationSettings.id.asc())
        .first()
    )
    return organization.id if organization else None


def _organization_filter(query, column, organization_id):
    if organization_id is None:
        return query.filter(column.is_(None))
    return query.filter(column == organization_id)


def get_source_setting(
    academic_year_id,
    organization_id=None,
    *,
    for_update=False,
):
    organization_id = (
        active_organization_id()
        if organization_id is None
        else organization_id
    )
    query = WorkloadSourceSetting.query.filter_by(
        academic_year_id=academic_year_id,
    )
    query = _organization_filter(
        query,
        WorkloadSourceSetting.organization_id,
        organization_id,
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def effective_version_for_year(academic_year_id, organization_id=None):
    organization_id = (
        active_organization_id()
        if organization_id is None
        else organization_id
    )
    query = (
        TariffVersion.query
        .join(TariffVersion.tariff_cycle)
        .filter(
            TariffVersion.status == "EFFECTIVE",
            TariffVersion.tariff_cycle.has(
                academic_year_id=academic_year_id,
            ),
        )
        .order_by(
            TariffVersion.effective_from.desc(),
            TariffVersion.version_no.desc(),
        )
    )
    if organization_id is None:
        query = query.filter(
            TariffVersion.tariff_cycle.has(organization_id=None)
        )
    else:
        query = query.filter(
            TariffVersion.tariff_cycle.has(
                organization_id=organization_id,
            )
        )
    return query.first()


def latest_reconciliation_for_version(tariff_version_id):
    if not tariff_version_id:
        return None
    return (
        WorkloadReconciliationRun.query
        .filter_by(tariff_version_id=tariff_version_id)
        .order_by(
            WorkloadReconciliationRun.run_no.desc(),
            WorkloadReconciliationRun.id.desc(),
        )
        .first()
    )


def source_state(academic_year_id, organization_id=None):
    setting = get_source_setting(
        academic_year_id,
        organization_id=organization_id,
    )
    configured_mode = setting.source_mode if setting else "LEGACY"
    flag_enabled = bool(
        current_app.config.get("FEATURE_WORKLOAD_NEW_SOURCE_ENABLED", False)
    )
    module_enabled = bool(
        current_app.config.get("FEATURE_WORKLOAD_MODULE_ENABLED", False)
    )
    selected_version = (
        setting.selected_tariff_version
        if setting and setting.selected_tariff_version is not None
        else None
    )
    version = (
        selected_version
        if (
            selected_version is not None
            and selected_version.status == "EFFECTIVE"
            and selected_version.tariff_cycle.academic_year_id
            == academic_year_id
        )
        else effective_version_for_year(
            academic_year_id,
            organization_id=organization_id,
        )
    )
    effective_mode = (
        "INTERNAL"
        if (
            flag_enabled
            and module_enabled
            and configured_mode == "INTERNAL"
            and version is not None
        )
        else "LEGACY"
    )
    return WorkloadSourceState(
        configured_mode=configured_mode,
        effective_mode=effective_mode,
        flag_enabled=flag_enabled,
        setting=setting,
        tariff_version=version,
        latest_reconciliation=latest_reconciliation_for_version(
            version.id if version else None
        ),
    )


def _grade_from_group(group):
    if not group or not getattr(group, "source_plan_line", None):
        return None
    scopes = getattr(group.source_plan_line, "scopes", None) or []
    grades = {
        scope.grade or (
            scope.school_class.grade
            if getattr(scope, "school_class", None)
            else None
        )
        for scope in scopes
    }
    grades.discard(None)
    return next(iter(grades)) if len(grades) == 1 else None


def _plan_kind_from_group(group):
    line = getattr(group, "source_plan_line", None) if group else None
    plan = getattr(line, "education_plan", None) if line else None
    return getattr(plan, "plan_kind", None) or "CURRICULUM"


def internal_department_load_rows(
    tariff_version,
    *,
    department_id=None,
    subject_id=None,
    teacher_id=None,
    building_id=None,
    query_text=None,
):
    if tariff_version is None or tariff_version.status != "EFFECTIVE":
        return []
    calculation_run = latest_successful_run(tariff_version.id)
    if calculation_run is None:
        return []

    query = (
        TariffLine.query
        .join(
            WorkloadAssignment,
            WorkloadAssignment.id == TariffLine.workload_assignment_id,
        )
        .filter(
            TariffLine.calculation_run_id == calculation_run.id,
            WorkloadAssignment.status == "CONFIRMED",
            WorkloadAssignment.employee_user_id.isnot(None),
            WorkloadAssignment.assignment_kind != "VACANCY",
        )
    )
    if department_id:
        query = query.filter(TariffLine.department_id == department_id)
    if teacher_id:
        query = query.filter(TariffLine.employee_user_id == teacher_id)
    if building_id:
        query = query.filter(TariffLine.building_id == building_id)
    if subject_id:
        activity = db.session.get(EducationActivity, subject_id)
        if activity is None or activity.activity_kind != "SUBJECT":
            subject = db.session.get(Subject, subject_id)
            activity = subject.education_activity if subject else None
        if activity is None:
            return []
        query = query.filter(
            TariffLine.education_activity_id == activity.id
        )

    lines = query.order_by(
        TariffLine.education_activity_id.asc(),
        TariffLine.teaching_group_id.asc(),
        TariffLine.employee_user_id.asc(),
    ).all()
    search = " ".join((query_text or "").lower().split())
    teacher_totals = defaultdict(Decimal)
    for line in lines:
        teacher_totals[line.employee_user_id] += Decimal(
            line.weekly_hours or ZERO
        )

    rows = []
    academic_year = tariff_version.tariff_cycle.academic_year
    for line in lines:
        assignment = line.workload_assignment
        group = line.teaching_group
        subject = getattr(line.education_activity, "legacy_subject", None)
        department = line.department or assignment.department
        building = line.building or assignment.building
        group_name = group.name if group else None
        class_name = group_name
        subject_name = line.education_activity.name
        teacher_name = line.employee.fio if line.employee else ""
        if search and search not in " ".join(
            (subject_name, class_name or "", teacher_name)
        ).lower():
            continue
        rows.append(DepartmentLoadRow(
            id=assignment.id,
            teacher=line.employee,
            subject=subject,
            academic_year=academic_year,
            department=department,
            building=building,
            class_name=class_name,
            grade=_grade_from_group(group),
            group_name=group_name,
            hours=float(line.weekly_hours or ZERO),
            subject_name=subject_name,
            building_name=building.name if building else None,
            is_whole_class=bool(
                group and group.group_type == "CLASS"
            ),
            is_meta_group=bool(
                group and group.group_type == "METAGROUP"
            ),
            teacher_total_hours=float(
                teacher_totals[line.employee_user_id]
            ),
            plan_kind=_plan_kind_from_group(group),
            class_label=teaching_group_class_label(group),
            group_label=teaching_group_assignment_label(group),
        ))
    return rows


def current_workload_version_for_year(
    academic_year_id,
    organization_id=None,
):
    """Return the version currently used by read-only workload consumers.

    Department and employee cards must reflect the same assignments that are
    visible in the workload matrix. During preparation this can be a draft;
    once an effective version exists it takes precedence automatically.
    """
    organization_id = (
        active_organization_id()
        if organization_id is None
        else organization_id
    )
    query = (
        TariffVersion.query
        .join(TariffVersion.tariff_cycle)
        .filter(
            TariffVersion.tariff_cycle.has(
                academic_year_id=academic_year_id,
            ),
        )
    )
    if organization_id is None:
        query = query.filter(
            TariffVersion.tariff_cycle.has(organization_id=None)
        )
    else:
        query = query.filter(
            TariffVersion.tariff_cycle.has(
                organization_id=organization_id,
            )
        )
    versions = query.order_by(
        TariffVersion.version_no.desc(),
        TariffVersion.id.desc(),
    ).all()
    priority = {
        "EFFECTIVE": 5,
        "APPROVED": 4,
        "IN_REVIEW": 3,
        "DRAFT": 2,
        "ARCHIVED": 1,
    }
    return max(
        versions,
        key=lambda item: (
            priority.get(item.status, 0),
            item.version_no,
            item.id,
        ),
        default=None,
    )


def current_department_load_rows(
    academic_year_id,
    *,
    department_id=None,
    subject_id=None,
    teacher_id=None,
    building_id=None,
    query_text=None,
    organization_id=None,
):
    """Read teacher assignments directly from the workload workspace."""
    tariff_version = current_workload_version_for_year(
        academic_year_id,
        organization_id=organization_id,
    )
    if tariff_version is None:
        return [], None

    query = (
        WorkloadAssignment.query
        .join(
            WorkloadAssignment.workload_need,
        )
        .filter(
            WorkloadAssignment.tariff_version_id == tariff_version.id,
            WorkloadAssignment.status != "CANCELLED",
            WorkloadAssignment.employee_user_id.isnot(None),
            WorkloadAssignment.assignment_kind != "VACANCY",
        )
    )
    if department_id:
        query = query.filter(db.or_(
            WorkloadAssignment.department_id == department_id,
            WorkloadAssignment.workload_need.has(
                department_id=department_id,
            ),
        ))
    if teacher_id:
        query = query.filter(
            WorkloadAssignment.employee_user_id == teacher_id,
        )
    if building_id:
        query = query.filter(db.or_(
            WorkloadAssignment.building_id == building_id,
            WorkloadAssignment.workload_need.has(
                building_id=building_id,
            ),
        ))
    if subject_id:
        activity = db.session.get(EducationActivity, subject_id)
        if activity is None or activity.activity_kind != "SUBJECT":
            subject = db.session.get(Subject, subject_id)
            activity = subject.education_activity if subject else None
        if activity is None:
            return [], tariff_version
        query = query.filter(
            WorkloadAssignment.workload_need.has(
                education_activity_id=activity.id,
            )
        )

    assignments = query.order_by(
        WorkloadAssignment.employee_user_id.asc(),
        WorkloadAssignment.workload_need_id.asc(),
        WorkloadAssignment.id.asc(),
    ).all()
    search = " ".join((query_text or "").lower().split())
    teacher_totals = defaultdict(Decimal)
    for assignment in assignments:
        teacher_totals[assignment.employee_user_id] += Decimal(
            assignment.weekly_hours or ZERO
        )

    academic_year = tariff_version.tariff_cycle.academic_year
    rows = []
    for assignment in assignments:
        need = assignment.workload_need
        group = need.teaching_group
        activity = need.education_activity
        department = assignment.department or need.department
        building = assignment.building or need.building
        group_name = group.name if group else None
        subject_name = activity.name
        teacher_name = assignment.employee.fio if assignment.employee else ""
        if search and search not in " ".join(
            (subject_name, group_name or "", teacher_name)
        ).lower():
            continue
        rows.append(DepartmentLoadRow(
            id=assignment.id,
            teacher=assignment.employee,
            subject=getattr(activity, "legacy_subject", None),
            academic_year=academic_year,
            department=department,
            building=building,
            class_name=group_name,
            grade=_grade_from_group(group),
            group_name=group_name,
            hours=float(assignment.weekly_hours or ZERO),
            subject_name=subject_name,
            building_name=building.name if building else None,
            is_whole_class=bool(group and group.group_type == "CLASS"),
            is_meta_group=bool(group and group.group_type == "METAGROUP"),
            teacher_total_hours=float(
                teacher_totals[assignment.employee_user_id]
            ),
            plan_kind=_plan_kind_from_group(group),
            class_label=teaching_group_class_label(group),
            group_label=teaching_group_assignment_label(group),
        ))
    return rows, tariff_version


def department_teacher_ids(
    academic_year_id,
    department_id,
    *,
    building_id=None,
    organization_id=None,
):
    if not academic_year_id:
        return []
    rows, _ = current_department_load_rows(
        academic_year_id,
        department_id=department_id,
        building_id=building_id,
        organization_id=organization_id,
    )
    return sorted({
        row.teacher.id for row in rows if row.teacher is not None
    })


def _decimal_hours(value):
    return Decimal(str(value or 0)).quantize(HOUR_QUANTUM)


def _aggregate_legacy(academic_year_id):
    query = TeacherLoad.query.filter(
        db.or_(
            TeacherLoad.academic_year_id == academic_year_id,
            TeacherLoad.academic_year_id.is_(None),
        )
    )
    rows = query.all()
    aggregates = {}
    unmapped = {}
    for row in rows:
        activity_id = (
            row.subject.education_activity_id
            if row.subject is not None
            else None
        )
        target = aggregates if activity_id else unmapped
        activity_key = activity_id or f"subject-{row.subject_id or row.id}"
        key = (
            row.teacher_id,
            activity_key,
            row.department_id,
            row.building_id,
        )
        item = target.setdefault(key, {
            "teacher_id": row.teacher_id,
            "activity_id": activity_id,
            "subject_id": row.subject_id,
            "department_id": row.department_id,
            "building_id": row.building_id,
            "hours": ZERO,
            "row_ids": [],
        })
        item["hours"] += _decimal_hours(row.hours)
        item["row_ids"].append(row.id)
    return rows, aggregates, unmapped


def _aggregate_internal(calculation_run):
    lines = (
        TariffLine.query
        .join(
            WorkloadAssignment,
            WorkloadAssignment.id == TariffLine.workload_assignment_id,
        )
        .filter(
            TariffLine.calculation_run_id == calculation_run.id,
            WorkloadAssignment.status == "CONFIRMED",
            WorkloadAssignment.assignment_kind != "VACANCY",
        )
        .all()
    )
    aggregates = {}
    for line in lines:
        key = (
            line.employee_user_id,
            line.education_activity_id,
            line.department_id,
            line.building_id,
        )
        item = aggregates.setdefault(key, {
            "teacher_id": line.employee_user_id,
            "activity_id": line.education_activity_id,
            "subject_id": (
                line.education_activity.legacy_subject.id
                if getattr(line.education_activity, "legacy_subject", None)
                else None
            ),
            "department_id": line.department_id,
            "building_id": line.building_id,
            "hours": ZERO,
            "line_ids": [],
        })
        item["hours"] += _decimal_hours(line.weekly_hours)
        item["line_ids"].append(line.id)
    return lines, aggregates


def _match_key(key):
    return ":".join(str(value if value is not None else 0) for value in key)


def reconcile_workload_sources(
    tariff_version,
    *,
    user_id,
    tolerance=DEFAULT_TOLERANCE,
):
    tariff_version = (
        TariffVersion.query
        .filter_by(id=tariff_version.id)
        .with_for_update()
        .one()
    )
    if tariff_version.status != "EFFECTIVE":
        raise WorkloadIntegrationError(
            "Сверять можно только введённую в действие версию."
        )
    calculation_run = latest_successful_run(tariff_version.id)
    if calculation_run is None:
        raise WorkloadIntegrationError(
            "У версии нет успешного расчёта тарификации."
        )
    academic_year = tariff_version.tariff_cycle.academic_year
    tolerance = _decimal_hours(tolerance)
    run_no = (
        db.session.query(
            db.func.max(WorkloadReconciliationRun.run_no)
        )
        .filter_by(tariff_version_id=tariff_version.id)
        .scalar()
        or 0
    ) + 1
    run = WorkloadReconciliationRun(
        organization_id=tariff_version.tariff_cycle.organization_id,
        academic_year_id=academic_year.id,
        tariff_version_id=tariff_version.id,
        calculation_run_id=calculation_run.id,
        run_no=run_no,
        status="RUNNING",
        tolerance_hours=tolerance,
        created_by_user_id=user_id,
    )
    db.session.add(run)
    db.session.flush()

    legacy_rows, legacy, unmapped = _aggregate_legacy(academic_year.id)
    internal_lines, internal = _aggregate_internal(calculation_run)
    matched_count = 0
    blocking_count = 0
    status_counts = defaultdict(int)

    for key, item in unmapped.items():
        status = "UNMAPPED_ACTIVITY"
        status_counts[status] += 1
        blocking_count += 1
        db.session.add(WorkloadReconciliationItem(
            reconciliation_run_id=run.id,
            match_key=f"unmapped:{_match_key(key)}",
            status=status,
            employee_user_id=item["teacher_id"],
            department_id=item["department_id"],
            building_id=item["building_id"],
            subject_id=item["subject_id"],
            legacy_weekly_hours=item["hours"],
            internal_weekly_hours=ZERO,
            difference_hours=-item["hours"],
            details={"legacy_row_ids": item["row_ids"]},
        ))

    for key in sorted(set(legacy) | set(internal), key=str):
        legacy_item = legacy.get(key)
        internal_item = internal.get(key)
        legacy_hours = legacy_item["hours"] if legacy_item else ZERO
        internal_hours = internal_item["hours"] if internal_item else ZERO
        difference = internal_hours - legacy_hours
        if legacy_item is None:
            status = "INTERNAL_ONLY"
        elif internal_item is None:
            status = "LEGACY_ONLY"
        elif abs(difference) <= tolerance:
            status = "MATCH"
        else:
            status = "HOURS_MISMATCH"
        status_counts[status] += 1
        if status == "MATCH":
            matched_count += 1
        else:
            blocking_count += 1
        source = internal_item or legacy_item
        db.session.add(WorkloadReconciliationItem(
            reconciliation_run_id=run.id,
            match_key=_match_key(key),
            status=status,
            employee_user_id=source["teacher_id"],
            department_id=source["department_id"],
            building_id=source["building_id"],
            subject_id=(
                legacy_item["subject_id"]
                if legacy_item
                else internal_item["subject_id"]
            ),
            education_activity_id=source["activity_id"],
            legacy_weekly_hours=legacy_hours,
            internal_weekly_hours=internal_hours,
            difference_hours=difference,
            details={
                "legacy_row_ids": (
                    legacy_item["row_ids"] if legacy_item else []
                ),
                "tariff_line_ids": (
                    internal_item["line_ids"] if internal_item else []
                ),
            },
        ))

    run.legacy_row_count = len(legacy_rows)
    run.internal_row_count = len(internal_lines)
    run.matched_count = matched_count
    run.blocking_count = blocking_count
    run.legacy_weekly_hours = sum(
        (item["hours"] for item in legacy.values()),
        ZERO,
    ) + sum((item["hours"] for item in unmapped.values()), ZERO)
    run.internal_weekly_hours = sum(
        (item["hours"] for item in internal.values()),
        ZERO,
    )
    run.summary_data = {
        "status_counts": dict(status_counts),
        "calculation_run_id": calculation_run.id,
        "algorithm_version": calculation_run.algorithm_version,
    }
    run.status = "PASSED" if blocking_count == 0 else "FAILED"
    run.finished_at = datetime.utcnow()
    db.session.flush()
    return run


def _validated_version(tariff_version, academic_year_id):
    if tariff_version is None:
        raise WorkloadIntegrationError(
            "Выберите введённую в действие версию."
        )
    if tariff_version.status != "EFFECTIVE":
        raise WorkloadIntegrationError(
            "Источником может быть только введённая в действие версия."
        )
    if tariff_version.tariff_cycle.academic_year_id != academic_year_id:
        raise WorkloadIntegrationError(
            "Версия относится к другому учебному году."
        )
    if latest_successful_run(tariff_version.id) is None:
        raise WorkloadIntegrationError(
            "У версии нет успешного расчёта тарификации."
        )
    return tariff_version


def switch_workload_source(
    academic_year,
    *,
    mode,
    tariff_version,
    user_id,
    reason,
    organization_id=None,
):
    mode = (mode or "").strip().upper()
    if mode not in {"LEGACY", "COMPARE", "INTERNAL"}:
        raise WorkloadIntegrationError("Неизвестный режим источника.")
    reason = " ".join((reason or "").split())
    if not reason:
        raise WorkloadIntegrationError(
            "Укажите основание переключения источника."
        )
    organization_id = (
        active_organization_id()
        if organization_id is None
        else organization_id
    )
    if mode != "LEGACY":
        if not current_app.config.get(
            "FEATURE_WORKLOAD_NEW_SOURCE_ENABLED",
            False,
        ):
            raise WorkloadIntegrationError(
                "Новый источник отключён feature flag."
            )
        tariff_version = _validated_version(
            tariff_version,
            academic_year.id,
        )

    reconciliation = None
    if mode == "INTERNAL":
        reconciliation = latest_reconciliation_for_version(
            tariff_version.id
        )
        if (
            reconciliation is None
            or reconciliation.status != "PASSED"
            or reconciliation.blocking_count != 0
        ):
            raise WorkloadIntegrationError(
                "Перед переключением нужна успешная сверка без расхождений."
            )
        if reconciliation.internal_row_count <= 0:
            raise WorkloadIntegrationError(
                "Нельзя переключиться на пустой внутренний источник."
            )

    setting = get_source_setting(
        academic_year.id,
        organization_id=organization_id,
        for_update=True,
    )
    if setting is None:
        setting = WorkloadSourceSetting(
            organization_id=organization_id,
            academic_year_id=academic_year.id,
            source_mode="LEGACY",
            changed_by_user_id=user_id,
        )
        db.session.add(setting)
        db.session.flush()
    from_mode = setting.source_mode
    if from_mode == mode:
        raise WorkloadIntegrationError(
            "Выбранный режим уже установлен."
        )

    setting.source_mode = mode
    if tariff_version is not None:
        setting.selected_tariff_version_id = tariff_version.id
    setting.revision += 1
    setting.change_reason = reason
    setting.changed_by_user_id = user_id
    setting.changed_at = datetime.utcnow()
    db.session.add(WorkloadSourceTransition(
        workload_source_setting_id=setting.id,
        reconciliation_run_id=(
            reconciliation.id if reconciliation else None
        ),
        tariff_version_id=(
            tariff_version.id if tariff_version else None
        ),
        from_mode=from_mode,
        to_mode=mode,
        reason=reason,
        changed_by_user_id=user_id,
    ))
    db.session.flush()
    return setting


__all__ = [
    "DepartmentLoadRow",
    "WorkloadIntegrationError",
    "WorkloadSourceState",
    "active_organization_id",
    "department_teacher_ids",
    "effective_version_for_year",
    "get_source_setting",
    "internal_department_load_rows",
    "latest_reconciliation_for_version",
    "reconcile_workload_sources",
    "source_state",
    "switch_workload_source",
]
