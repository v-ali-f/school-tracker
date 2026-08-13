from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.core.extensions import db
from app.models import (
    EducationActivityDepartment,
    EducationPlanLine,
    TariffVersion,
    TeachingGroup,
    TeachingMetagroupSource,
    User,
    WorkloadAssignment,
    WorkloadAssignmentChange,
    WorkloadNeed,
    WorkloadNeedSource,
)


ZERO = Decimal("0")
HOURS_QUANTUM = Decimal("0.001")


class WorkloadDistributionError(ValueError):
    pass


class WorkloadLockedError(WorkloadDistributionError):
    pass


class ConcurrentWorkloadUpdateError(WorkloadDistributionError):
    pass


def decimal_hours(value, label, *, required=True):
    text = str(value or "").strip().replace(",", ".")
    if not text:
        if required:
            raise WorkloadDistributionError(f"Укажите {label}.")
        return None
    try:
        number = Decimal(text).quantize(
            HOURS_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    except InvalidOperation as exc:
        raise WorkloadDistributionError(
            f"Поле «{label}» должно содержать число."
        ) from exc
    if number < ZERO:
        raise WorkloadDistributionError(
            f"Поле «{label}» не может быть отрицательным."
        )
    return number


def resolve_need_department(group):
    if group.department_id:
        return group.department_id
    link = (
        EducationActivityDepartment.query
        .filter_by(
            education_activity_id=group.education_activity_id,
            is_active=True,
            is_primary=True,
        )
        .order_by(EducationActivityDepartment.id.asc())
        .first()
    )
    return link.department_id if link else None


def resolve_line_hours(plan_line, date_from, date_to):
    containing_periods = [
        period
        for period in plan_line.periods
        if period.date_from <= date_from and period.date_to >= date_to
    ]
    period = containing_periods[0] if len(containing_periods) == 1 else None
    weekly = (
        period.weekly_hours
        if period is not None and period.weekly_hours is not None
        else plan_line.weekly_hours
    )
    annual = (
        period.annual_hours
        if period is not None and period.annual_hours is not None
        else plan_line.annual_hours
    )
    weeks = (
        period.weeks_count
        if period is not None and period.weeks_count is not None
        else plan_line.weeks_count
    )
    weekly = Decimal(weekly or ZERO).quantize(HOURS_QUANTUM)
    if annual is None and weekly > ZERO and weeks is not None:
        annual = weekly * Decimal(weeks)
    annual = Decimal(annual or ZERO).quantize(HOURS_QUANTUM)
    return weekly, annual


def refresh_need_status(need):
    if need.status == "CANCELLED":
        return need.status
    weekly = Decimal(need.weekly_hours or ZERO)
    annual = Decimal(need.annual_hours or ZERO)
    allocated_weekly = need.allocated_weekly_hours
    allocated_annual = need.allocated_annual_hours
    weekly_over = weekly > ZERO and allocated_weekly > weekly
    annual_over = annual > ZERO and allocated_annual > annual
    if weekly_over or annual_over:
        need.status = "OVERALLOCATED"
    elif (
        (weekly <= ZERO or allocated_weekly == weekly)
        and (annual <= ZERO or allocated_annual == annual)
    ):
        need.status = "COVERED"
    elif allocated_weekly > ZERO or allocated_annual > ZERO:
        need.status = "PARTIAL"
    else:
        need.status = "OPEN"
    return need.status


def _synchronize_full_assignment(
    need,
    *,
    old_weekly,
    old_annual,
    new_weekly,
    new_annual,
    user_id,
):
    active = [
        item
        for item in need.assignments
        if item.status != "CANCELLED"
        and item.assignment_kind != "VACANCY"
    ]
    if len(active) != 1:
        return False
    assignment = active[0]
    if (
        Decimal(assignment.weekly_hours or ZERO) != old_weekly
        or Decimal(assignment.annual_hours or ZERO) != old_annual
    ):
        return False
    if old_weekly == new_weekly and old_annual == new_annual:
        return False
    before = assignment_snapshot(assignment)
    assignment.weekly_hours = new_weekly
    assignment.annual_hours = new_annual
    assignment.revision += 1
    assignment.updated_by_user_id = user_id
    add_assignment_change(
        assignment,
        "UPDATE",
        user_id=user_id,
        before_data=before,
        reason="Автоматически синхронизировано с учебным планом",
    )
    return True


def generate_plan_needs(
    tariff_version,
    *,
    user_id,
    source_plan_line_ids=None,
):
    if tariff_version.status != "DRAFT":
        raise WorkloadLockedError(
            "Потребность можно пересчитывать только в черновой версии."
        )
    from app.services.teaching_group_matrix_service import (
        materialize_default_teaching_groups,
    )
    from app.services.teaching_group_service import (
        current_population_snapshot,
    )

    source_plan_line_ids = (
        {int(item) for item in source_plan_line_ids}
        if source_plan_line_ids else None
    )
    plans = [
        plan for plan in tariff_version.plans
        if plan.plan_kind == "CURRICULUM" and plan.root_plan_id is None
    ]
    materialize_default_teaching_groups(
        version=tariff_version,
        snapshot=current_population_snapshot(tariff_version.id),
        plans=plans,
        user_id=user_id,
        source_plan_line_ids=source_plan_line_ids,
    )
    db.session.flush()
    organization_id = tariff_version.tariff_cycle.organization_id
    groups = (
        TeachingGroup.query
        .filter(
            TeachingGroup.tariff_version_id == tariff_version.id,
            TeachingGroup.status != "CLOSED",
        )
        .order_by(TeachingGroup.id.asc())
        .all()
    )
    merged_source_ids = {
        item.source_group_id
        for item in (
            TeachingMetagroupSource.query
            .join(
                TeachingGroup,
                TeachingGroup.id
                == TeachingMetagroupSource.metagroup_id,
            )
            .filter(
                TeachingGroup.tariff_version_id == tariff_version.id,
                TeachingGroup.status != "CLOSED",
            )
            .all()
        )
    }
    groups = [
        group for group in groups
        if group.id not in merged_source_ids
    ]
    desired_keys = set()
    created = 0
    updated = 0
    skipped_empty = 0
    processed_groups = []
    for group in groups:
        source_lines = (
            list(dict.fromkeys(
                link.source_group.source_plan_line
                for link in group.metagroup_sources
            ))
            if group.group_type == "METAGROUP"
            else [group.source_plan_line]
        )
        if (
            source_plan_line_ids is not None
            and not source_plan_line_ids.intersection(
                source_line.id for source_line in source_lines
            )
        ):
            continue
        processed_groups.append(group)
        line = source_lines[0]
        weekly, annual = resolve_line_hours(
            line,
            group.valid_from,
            group.valid_to,
        )
        if weekly <= ZERO and annual <= ZERO:
            skipped_empty += 1
            continue
        key = (
            group.id,
            group.valid_from,
            group.valid_to,
            "PLAN",
        )
        desired_keys.add(key)
        need = WorkloadNeed.query.filter_by(
            tariff_version_id=tariff_version.id,
            teaching_group_id=group.id,
            date_from=group.valid_from,
            date_to=group.valid_to,
            need_kind="PLAN",
        ).first()
        if need is None:
            need = WorkloadNeed(
                organization_id=organization_id,
                tariff_version_id=tariff_version.id,
                teaching_group_id=group.id,
                education_activity_id=group.education_activity_id,
                department_id=resolve_need_department(group),
                building_id=group.building_id,
                date_from=group.valid_from,
                date_to=group.valid_to,
                weekly_hours=weekly,
                annual_hours=annual,
                need_kind="PLAN",
                status="OPEN",
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
            )
            db.session.add(need)
            db.session.flush()
            for source_line in source_lines:
                db.session.add(WorkloadNeedSource(
                    workload_need_id=need.id,
                    education_plan_line_id=source_line.id,
                    source_weekly_hours=weekly,
                    source_annual_hours=annual,
                    source_kind=(
                        "MERGE"
                        if group.group_type == "METAGROUP"
                        else "DIVISION"
                        if line.requires_division
                        or group.group_type == "SUBGROUP"
                        else "DIRECT"
                    ),
                ))
            created += 1
        else:
            old_weekly = Decimal(need.weekly_hours or ZERO)
            old_annual = Decimal(need.annual_hours or ZERO)
            _synchronize_full_assignment(
                need,
                old_weekly=old_weekly,
                old_annual=old_annual,
                new_weekly=weekly,
                new_annual=annual,
                user_id=user_id,
            )
            if (
                need.allocated_weekly_hours > weekly
                or (
                    annual > ZERO
                    and need.allocated_annual_hours > annual
                )
            ):
                raise WorkloadDistributionError(
                    f"После пересчёта назначение по группе «{group.name}» "
                    "превысит плановые часы."
                )
            need.education_activity_id = group.education_activity_id
            need.department_id = resolve_need_department(group)
            need.building_id = group.building_id
            need.weekly_hours = weekly
            need.annual_hours = annual
            need.status = "OPEN"
            need.revision += 1
            need.updated_by_user_id = user_id
            desired_sources = {
                (
                    source_line.id,
                    "MERGE"
                    if group.group_type == "METAGROUP"
                    else "DIVISION"
                    if line.requires_division
                    or group.group_type == "SUBGROUP"
                    else "DIRECT",
                )
                for source_line in source_lines
            }
            existing_sources = {
                (source.education_plan_line_id, source.source_kind): source
                for source in need.sources
            }
            for key, source in existing_sources.items():
                if key not in desired_sources:
                    db.session.delete(source)
            for line_id, source_kind in desired_sources:
                source = existing_sources.get((line_id, source_kind))
                if source is None:
                    db.session.add(WorkloadNeedSource(
                        workload_need_id=need.id,
                        education_plan_line_id=line_id,
                        source_weekly_hours=weekly,
                        source_annual_hours=annual,
                        source_kind=source_kind,
                    ))
                else:
                    source.source_weekly_hours = weekly
                    source.source_annual_hours = annual
            refresh_need_status(need)
            if old_weekly != weekly or old_annual != annual:
                updated += 1

    cancelled = 0
    existing_needs_query = WorkloadNeed.query.filter_by(
        tariff_version_id=tariff_version.id,
        need_kind="PLAN",
    )
    if source_plan_line_ids is not None:
        existing_needs_query = (
            existing_needs_query
            .join(WorkloadNeedSource)
            .filter(
                WorkloadNeedSource.education_plan_line_id.in_(
                    source_plan_line_ids
                )
            )
            .distinct()
        )
    existing_needs = existing_needs_query.all()
    for need in existing_needs:
        key = (
            need.teaching_group_id,
            need.date_from,
            need.date_to,
            need.need_kind,
        )
        if key in desired_keys or need.status == "CANCELLED":
            continue
        if any(
            item.status != "CANCELLED"
            for item in need.assignments
        ):
            raise WorkloadDistributionError(
                "Нельзя отменить потребность с действующими назначениями: "
                f"{need.education_activity.name}, "
                f"{need.teaching_group.name if need.teaching_group else 'без группы'}."
            )
        need.status = "CANCELLED"
        need.revision += 1
        need.updated_by_user_id = user_id
        cancelled += 1
    return {
        "created": created,
        "updated": updated,
        "cancelled": cancelled,
        "ready_groups": len(processed_groups),
        "skipped_empty": skipped_empty,
    }


def delete_plan_lines_with_dependencies(lines):
    lines = list(lines)
    if not lines:
        return {"groups": 0, "needs": 0, "assignments": 0}
    version_ids = {
        line.education_plan.tariff_version_id for line in lines
    }
    if len(version_ids) != 1:
        raise WorkloadDistributionError(
            "Удаляемые строки относятся к разным версиям тарификации."
        )
    version_id = next(iter(version_ids))
    line_ids = {line.id for line in lines}
    # Lines copied into another plan/version keep a historical source link.
    # They are independent rows and must not make deletion of the original
    # line look like an active workload conflict.
    (
        EducationPlanLine.query
        .filter(EducationPlanLine.source_line_id.in_(line_ids))
        .update(
            {EducationPlanLine.source_line_id: None},
            synchronize_session=False,
        )
    )
    groups = (
        TeachingGroup.query
        .filter(
            TeachingGroup.tariff_version_id == version_id,
            TeachingGroup.source_plan_line_id.in_(line_ids),
        )
        .all()
    )
    groups_by_id = {group.id: group for group in groups}

    changed = True
    while changed and groups_by_id:
        changed = False
        group_ids = set(groups_by_id)
        linked_groups = (
            TeachingGroup.query
            .filter(TeachingGroup.source_group_id.in_(group_ids))
            .all()
        )
        linked_metagroups = [
            link.metagroup
            for link in (
                TeachingMetagroupSource.query
                .filter(
                    TeachingMetagroupSource.source_group_id.in_(group_ids)
                )
                .all()
            )
        ]
        for group in linked_groups + linked_metagroups:
            if group.tariff_version_id != version_id:
                raise WorkloadDistributionError(
                    "Строка используется в следующей версии. "
                    "Сначала удалите связанную версию нагрузки."
                )
            if group.id not in groups_by_id:
                groups_by_id[group.id] = group
                changed = True

    group_ids = set(groups_by_id)
    need_ids = {
        item.workload_need_id
        for item in (
            WorkloadNeedSource.query
            .filter(WorkloadNeedSource.education_plan_line_id.in_(line_ids))
            .all()
        )
    }
    if group_ids:
        need_ids.update(
            need.id
            for need in (
                WorkloadNeed.query
                .filter(WorkloadNeed.teaching_group_id.in_(group_ids))
                .all()
            )
        )
    needs = (
        WorkloadNeed.query
        .filter(WorkloadNeed.id.in_(need_ids))
        .all()
        if need_ids else []
    )
    assignment_count = sum(len(need.assignments) for need in needs)
    for need in needs:
        db.session.delete(need)
    db.session.flush()

    ordered_groups = sorted(
        groups_by_id.values(),
        key=lambda group: (
            group.group_type != "METAGROUP",
            group.source_group_id is None,
            group.id,
        ),
    )
    for group in ordered_groups:
        db.session.delete(group)
    db.session.flush()
    for line in lines:
        db.session.delete(line)
    return {
        "groups": len(ordered_groups),
        "needs": len(needs),
        "assignments": assignment_count,
    }


def assignment_snapshot(assignment):
    return {
        "employee_user_id": assignment.employee_user_id,
        "position_code": assignment.position_code,
        "position_title": assignment.position_title,
        "department_id": assignment.department_id,
        "building_id": assignment.building_id,
        "assignment_kind": assignment.assignment_kind,
        "date_from": assignment.date_from.isoformat(),
        "date_to": assignment.date_to.isoformat(),
        "weekly_hours": str(assignment.weekly_hours),
        "annual_hours": str(assignment.annual_hours),
        "status": assignment.status,
        "revision": assignment.revision,
    }


def add_assignment_change(
    assignment,
    change_kind,
    *,
    user_id,
    before_data=None,
    reason=None,
):
    db.session.add(WorkloadAssignmentChange(
        workload_assignment=assignment,
        change_kind=change_kind,
        changed_by_user_id=user_id,
        before_data=before_data,
        after_data=assignment_snapshot(assignment),
        reason=" ".join((reason or "").split()) or None,
    ))


def require_assignment_editable(assignment, *, expected_revision=None):
    if assignment.tariff_version.status != "DRAFT":
        raise WorkloadLockedError(
            "Назначение относится к версии, недоступной для изменения."
        )
    if assignment.status == "CANCELLED":
        raise WorkloadLockedError("Отменённое назначение нельзя изменить.")
    if (
        expected_revision is not None
        and assignment.revision != expected_revision
    ):
        raise ConcurrentWorkloadUpdateError(
            "Назначение изменено другим пользователем. Обновите страницу."
        )


def validate_assignment(
    need,
    assignment,
    *,
    exclude_assignment_id=None,
):
    if need.tariff_version.status != "DRAFT":
        raise WorkloadLockedError(
            "Назначения можно менять только в черновой версии."
        )
    if need.status == "CANCELLED":
        raise WorkloadLockedError("Потребность отменена.")
    if assignment.assignment_kind not in {
        "MAIN",
        "SECONDARY",
        "INTERNAL_PART_TIME",
        "EXTERNAL_PART_TIME",
        "SUBSTITUTE",
        "VACANCY",
    }:
        raise WorkloadDistributionError("Выберите допустимый вид назначения.")
    if assignment.assignment_kind == "VACANCY":
        if assignment.employee_user_id is not None:
            raise WorkloadDistributionError(
                "Для вакансии сотрудник не указывается."
            )
    else:
        if assignment.employee_user_id is None:
            raise WorkloadDistributionError("Выберите преподавателя.")
        employee = db.session.get(User, assignment.employee_user_id)
        if employee is None or not employee.is_active_user:
            raise WorkloadDistributionError(
                "Выбранный сотрудник не найден или отключён."
            )
        if employee.employment_status != "ACTIVE":
            raise WorkloadDistributionError(
                "Нельзя назначить нагрузку неработающему сотруднику."
            )
        if (
            employee.dismissal_date is not None
            and employee.dismissal_date < assignment.date_to
        ):
            raise WorkloadDistributionError(
                "Период назначения выходит за дату увольнения сотрудника."
            )
    if assignment.date_from is None or assignment.date_to is None:
        raise WorkloadDistributionError("Укажите период назначения.")
    if assignment.date_to < assignment.date_from:
        raise WorkloadDistributionError(
            "Дата окончания назначения не может быть раньше начала."
        )
    if (
        assignment.date_from < need.date_from
        or assignment.date_to > need.date_to
    ):
        raise WorkloadDistributionError(
            "Период назначения должен входить в период потребности."
        )
    weekly = Decimal(assignment.weekly_hours or ZERO)
    annual = Decimal(assignment.annual_hours or ZERO)
    if weekly <= ZERO and annual <= ZERO:
        raise WorkloadDistributionError(
            "Назначенный объём часов должен быть больше нуля."
        )
    active_query = WorkloadAssignment.query.filter(
        WorkloadAssignment.workload_need_id == need.id,
        WorkloadAssignment.status != "CANCELLED",
    )
    if exclude_assignment_id is not None:
        active_query = active_query.filter(
            WorkloadAssignment.id != exclude_assignment_id
        )
    active = active_query.all()
    if assignment.assignment_kind == "VACANCY":
        vacancy_weekly = sum(
            (
                Decimal(item.weekly_hours or ZERO)
                for item in active
                if item.assignment_kind == "VACANCY"
            ),
            ZERO,
        )
        vacancy_annual = sum(
            (
                Decimal(item.annual_hours or ZERO)
                for item in active
                if item.assignment_kind == "VACANCY"
            ),
            ZERO,
        )
        if (
            vacancy_weekly + weekly > need.remaining_weekly_hours
            or vacancy_annual + annual > need.remaining_annual_hours
        ):
            raise WorkloadDistributionError(
                "Объём вакансии превышает нераспределённый остаток."
            )
        return
    allocated_weekly = sum(
        (
            Decimal(item.weekly_hours or ZERO)
            for item in active
            if item.assignment_kind != "VACANCY"
        ),
        ZERO,
    )
    allocated_annual = sum(
        (
            Decimal(item.annual_hours or ZERO)
            for item in active
            if item.assignment_kind != "VACANCY"
        ),
        ZERO,
    )
    if allocated_weekly + weekly > Decimal(need.weekly_hours or ZERO):
        raise WorkloadDistributionError(
            "Недельные назначения превышают потребность."
        )
    if (
        allocated_annual + annual
        > Decimal(need.annual_hours or ZERO)
    ):
        raise WorkloadDistributionError(
            "Годовые назначения превышают потребность."
        )
    duplicate = (
        WorkloadAssignment.query
        .filter(
            WorkloadAssignment.workload_need_id == need.id,
            WorkloadAssignment.employee_user_id == assignment.employee_user_id,
            WorkloadAssignment.status != "CANCELLED",
            WorkloadAssignment.date_from <= assignment.date_to,
            WorkloadAssignment.date_to >= assignment.date_from,
        )
    )
    if exclude_assignment_id is not None:
        duplicate = duplicate.filter(
            WorkloadAssignment.id != exclude_assignment_id
        )
    if duplicate.first() is not None:
        raise WorkloadDistributionError(
            "У этого преподавателя уже есть пересекающееся назначение "
            "по данной потребности."
        )


def calculate_assignment_annual_hours(need, weekly_hours, annual_hours):
    if annual_hours is not None:
        return annual_hours
    need_weekly = Decimal(need.weekly_hours or ZERO)
    need_annual = Decimal(need.annual_hours or ZERO)
    if need_weekly > ZERO and need_annual > ZERO:
        return (
            weekly_hours * need_annual / need_weekly
        ).quantize(HOURS_QUANTUM, rounding=ROUND_HALF_UP)
    return ZERO


def cancel_assignment(
    assignment,
    *,
    user_id,
    expected_revision,
    reason,
):
    require_assignment_editable(
        assignment,
        expected_revision=expected_revision,
    )
    normalized_reason = " ".join((reason or "").split())
    if not normalized_reason:
        raise WorkloadDistributionError(
            "Укажите основание отмены назначения."
        )
    before = assignment_snapshot(assignment)
    assignment.status = "CANCELLED"
    assignment.revision += 1
    assignment.updated_by_user_id = user_id
    add_assignment_change(
        assignment,
        "CANCEL",
        user_id=user_id,
        before_data=before,
        reason=normalized_reason,
    )
    refresh_need_status(assignment.workload_need)


def teacher_totals(assignments):
    totals = {
        "CURRICULUM": ZERO,
        "EXTRACURRICULAR": ZERO,
        "ADDITIONAL_EDUCATION": ZERO,
        "TOTAL": ZERO,
    }
    for assignment in assignments:
        if (
            assignment.status == "CANCELLED"
            or assignment.assignment_kind == "VACANCY"
        ):
            continue
        kind = (
            assignment.workload_need.teaching_group
            .source_plan_line.education_plan.plan_kind
        )
        hours = Decimal(assignment.weekly_hours or ZERO)
        totals[kind] = totals.get(kind, ZERO) + hours
        totals["TOTAL"] += hours
    return totals


__all__ = [
    "ConcurrentWorkloadUpdateError",
    "HOURS_QUANTUM",
    "WorkloadDistributionError",
    "WorkloadLockedError",
    "add_assignment_change",
    "assignment_snapshot",
    "calculate_assignment_annual_hours",
    "cancel_assignment",
    "decimal_hours",
    "generate_plan_needs",
    "refresh_need_status",
    "require_assignment_editable",
    "resolve_need_department",
    "teacher_totals",
    "validate_assignment",
]
