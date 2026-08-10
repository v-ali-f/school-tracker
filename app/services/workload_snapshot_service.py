"""Keep workload assignments attached when the population snapshot changes."""

from collections import defaultdict

from sqlalchemy.orm import joinedload, selectinload

from app.core.extensions import db
from app.models import (
    PopulationSnapshotClass,
    TeachingGroup,
    TeachingGroupClass,
    WorkloadAssignment,
    WorkloadAssignmentChange,
    WorkloadNeed,
)
from app.services.workload_distribution_service import (
    WorkloadDistributionError,
    assignment_snapshot,
    refresh_need_status,
)


def _class_key(group):
    if group is None:
        return ()
    return tuple(sorted({
        link.population_snapshot_class.source_school_class_id
        for link in group.source_classes
    }))


def _need_key(need):
    group = need.teaching_group
    return (
        group.source_plan_line_id if group is not None else None,
        _class_key(group),
        need.need_kind,
        need.date_from,
        need.date_to,
    )


def relink_assignments_to_population_snapshot(
    version,
    target_snapshot,
    *,
    user_id,
):
    """Move active assignments from superseded snapshots to matching needs.

    No partial move is allowed: if one target is missing or ambiguous, the
    caller receives an error and can roll back the transaction.
    """
    if target_snapshot is None or target_snapshot.tariff_version_id != version.id:
        return 0

    assignments = (
        WorkloadAssignment.query
        .options(
            joinedload(WorkloadAssignment.workload_need)
            .joinedload(WorkloadNeed.teaching_group)
            .selectinload(TeachingGroup.source_classes)
            .joinedload(TeachingGroupClass.population_snapshot_class)
        )
        .join(WorkloadNeed, WorkloadNeed.id == WorkloadAssignment.workload_need_id)
        .filter(
            WorkloadNeed.tariff_version_id == version.id,
            WorkloadAssignment.status != "CANCELLED",
        )
        .all()
    )
    stale_assignments = [
        assignment
        for assignment in assignments
        if assignment.workload_need.teaching_group is not None
        and _class_key(assignment.workload_need.teaching_group)
        and any(
            link.population_snapshot_class.population_snapshot_id
            != target_snapshot.id
            for link in assignment.workload_need.teaching_group.source_classes
        )
    ]
    if not stale_assignments:
        return 0

    target_needs = (
        WorkloadNeed.query
        .options(
            joinedload(WorkloadNeed.teaching_group)
            .selectinload(TeachingGroup.source_classes)
            .joinedload(TeachingGroupClass.population_snapshot_class)
        )
        .join(TeachingGroup, TeachingGroup.id == WorkloadNeed.teaching_group_id)
        .join(
            TeachingGroupClass,
            TeachingGroupClass.teaching_group_id == TeachingGroup.id,
        )
        .join(
            PopulationSnapshotClass,
            PopulationSnapshotClass.id
            == TeachingGroupClass.population_snapshot_class_id,
        )
        .filter(
            WorkloadNeed.tariff_version_id == version.id,
            WorkloadNeed.status != "CANCELLED",
            TeachingGroup.status != "CLOSED",
            PopulationSnapshotClass.population_snapshot_id == target_snapshot.id,
        )
        .distinct()
        .all()
    )
    targets_by_key = defaultdict(list)
    for need in target_needs:
        targets_by_key[_need_key(need)].append(need)

    mappings = []
    errors = []
    for assignment in stale_assignments:
        candidates = targets_by_key.get(_need_key(assignment.workload_need), ())
        if len(candidates) != 1:
            errors.append(
                f"назначение №{assignment.id}: найдено целей {len(candidates)}"
            )
            continue
        target_need = candidates[0]
        duplicate = next(
            (
                item for item in assignments
                if item.id != assignment.id
                and item.workload_need_id == target_need.id
                and item.employee_user_id == assignment.employee_user_id
                and item.assignment_kind == assignment.assignment_kind
                and item.position_code == assignment.position_code
                and item.status != "CANCELLED"
            ),
            None,
        )
        if duplicate is not None:
            errors.append(
                f"назначение №{assignment.id}: текущая цель уже распределена"
            )
            continue
        mappings.append((assignment, target_need))

    if errors:
        details = "; ".join(errors[:5])
        raise WorkloadDistributionError(
            "Нагрузка сохранена в предыдущем снимке, но не может быть "
            f"перенесена автоматически: {details}."
        )

    old_needs = {assignment.workload_need for assignment, _ in mappings}
    new_needs = {target_need for _, target_need in mappings}
    for assignment, target_need in mappings:
        before = assignment_snapshot(assignment)
        before["workload_need_id"] = assignment.workload_need_id
        assignment.workload_need = target_need
        assignment.building_id = target_need.building_id
        assignment.revision += 1
        assignment.updated_by_user_id = user_id
        after = assignment_snapshot(assignment)
        after["workload_need_id"] = target_need.id
        db.session.add(WorkloadAssignmentChange(
            workload_assignment=assignment,
            change_kind="TRANSFER",
            changed_by_user_id=user_id,
            before_data=before,
            after_data=after,
            reason=(
                "Автоматическая перепривязка нагрузки к обновлённому "
                "снимку контингента."
            ),
        ))

    db.session.flush()
    for need in old_needs | new_needs:
        refresh_need_status(need)
    return len(mappings)


__all__ = ["relink_assignments_to_population_snapshot"]
