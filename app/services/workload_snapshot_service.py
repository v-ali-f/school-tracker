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


def _assignment_key(assignment):
    holder_key = (
        ("vacancy", assignment.position_code)
        if assignment.assignment_kind == "VACANCY"
        else ("teacher", assignment.employee_user_id)
    )
    return (*_need_key(assignment.workload_need), holder_key)


def _snapshot_revision(assignment):
    revisions = [
        link.population_snapshot_class.population_snapshot.revision_no
        for link in assignment.workload_need.teaching_group.source_classes
    ]
    return max(revisions, default=0)


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
            .joinedload(PopulationSnapshotClass.population_snapshot)
        )
        .join(WorkloadNeed, WorkloadNeed.id == WorkloadAssignment.workload_need_id)
        .filter(
            WorkloadNeed.tariff_version_id == version.id,
            WorkloadAssignment.status != "CANCELLED",
        )
        .all()
    )
    current_assignments = [
        assignment
        for assignment in assignments
        if assignment.workload_need.teaching_group is not None
        and _class_key(assignment.workload_need.teaching_group)
        and all(
            link.population_snapshot_class.population_snapshot_id
            == target_snapshot.id
            for link in assignment.workload_need.teaching_group.source_classes
        )
    ]
    stale_candidates = [
        assignment
        for assignment in assignments
        if assignment not in current_assignments
        and assignment.workload_need.teaching_group is not None
        and _class_key(assignment.workload_need.teaching_group)
    ]
    current_keys = {
        _assignment_key(assignment)
        for assignment in current_assignments
    }
    newest_stale_by_key = {}
    for assignment in stale_candidates:
        key = _assignment_key(assignment)
        current = newest_stale_by_key.get(key)
        if current is None or (
            _snapshot_revision(assignment),
            assignment.created_at,
            assignment.id,
        ) > (
            _snapshot_revision(current),
            current.created_at,
            current.id,
        ):
            newest_stale_by_key[key] = assignment
    stale_assignments = [
        assignment
        for key, assignment in newest_stale_by_key.items()
        if key not in current_keys
    ]
    if not stale_assignments:
        return 0

    target_needs = (
        WorkloadNeed.query
        .options(
            joinedload(WorkloadNeed.teaching_group)
            .selectinload(TeachingGroup.source_classes)
            .joinedload(TeachingGroupClass.population_snapshot_class)
            .joinedload(PopulationSnapshotClass.population_snapshot)
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
