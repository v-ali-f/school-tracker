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
    assignment_snapshot,
    refresh_need_status,
)


class AssignmentRelinkResult(int):
    """Transferred count with reconciliation details for the UI."""

    def __new__(cls, transferred=0, cancelled=0):
        result = int.__new__(cls, transferred)
        result.transferred = transferred
        result.cancelled = cancelled
        return result


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


def _semantic_need_key(need):
    """Identify the same workload cell after a class changes its plan.

    ``source_plan_line_id`` is intentionally omitted here: replacing the
    bound education plan creates another line id even when the class, subject,
    period and hours stay unchanged.  This key is only used as a guarded
    fallback when the exact key has no target, and the caller still requires
    exactly one matching current need.
    """
    group = need.teaching_group
    return (
        need.education_activity_id,
        _class_key(group),
        need.need_kind,
        need.date_from,
        need.date_to,
        need.weekly_hours,
        need.annual_hours,
        group.group_type if group is not None else None,
    )


def _semantic_assignment_key(assignment):
    holder_key = (
        ("vacancy", assignment.position_code)
        if assignment.assignment_kind == "VACANCY"
        else ("teacher", assignment.employee_user_id)
    )
    return (*_semantic_need_key(assignment.workload_need), holder_key)


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
    """Reconcile active assignments with the current workload structure.

    An assignment is transferred only when one current target is found.  If
    its plan cell was removed or split into several groups, the old assignment
    is cancelled with an audit record so the new cell can be distributed
    deliberately without affecting unrelated workload.
    """
    if target_snapshot is None or target_snapshot.tariff_version_id != version.id:
        return AssignmentRelinkResult()

    # In normal operation every active assignment already points at the current
    # population snapshot.  Check that inexpensive condition in SQL before
    # loading the complete assignment/group graph.  The workspace calls this
    # guard on every view and filter change, while the full graph is only needed
    # after an actual population snapshot rollover.
    stale_assignment = (
        db.session.query(WorkloadAssignment.id)
        .join(
            WorkloadNeed,
            WorkloadNeed.id == WorkloadAssignment.workload_need_id,
        )
        .join(
            TeachingGroup,
            TeachingGroup.id == WorkloadNeed.teaching_group_id,
        )
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
            WorkloadAssignment.status != "CANCELLED",
            PopulationSnapshotClass.population_snapshot_id
            != target_snapshot.id,
        )
        .first()
    )
    if stale_assignment is None:
        return AssignmentRelinkResult()

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
    current_semantic_keys = {
        _semantic_assignment_key(assignment)
        for assignment in current_assignments
    }
    stale_by_semantic_key = defaultdict(list)
    for assignment in stale_candidates:
        stale_by_semantic_key[
            _semantic_assignment_key(assignment)
        ].append(assignment)
    if not stale_by_semantic_key:
        return AssignmentRelinkResult()

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
    targets_by_semantic_key = defaultdict(list)
    for need in target_needs:
        targets_by_key[_need_key(need)].append(need)
        targets_by_semantic_key[_semantic_need_key(need)].append(need)

    mappings = []
    cancelled = []
    for semantic_key, matching_assignments in stale_by_semantic_key.items():
        matching_assignments.sort(
            key=lambda assignment: (
                _snapshot_revision(assignment),
                assignment.created_at,
                assignment.id,
            ),
            reverse=True,
        )
        assignment = matching_assignments[0]
        # Older active copies are historical leftovers from previous registry
        # revisions.  Keep their audit trail, but do not let them participate
        # in the current workload or make every workspace load expensive.
        cancelled.extend(matching_assignments[1:])
        if semantic_key in current_semantic_keys:
            cancelled.append(assignment)
            continue
        candidates = targets_by_key.get(_need_key(assignment.workload_need), ())
        if not candidates:
            candidates = targets_by_semantic_key.get(
                _semantic_need_key(assignment.workload_need),
                (),
            )
        if len(candidates) != 1:
            # A missing target means the plan line was removed.  Multiple
            # targets mean that the cell was split into groups.  In either
            # case retaining the old assignment would put hours into an
            # incorrect cell; preserve it in history as cancelled and leave
            # the new cell(s) open for deliberate redistribution.
            cancelled.append(assignment)
            continue
        target_need = candidates[0]
        mappings.append((assignment, target_need))

    old_needs = {
        assignment.workload_need
        for assignment, _ in mappings
    } | {
        assignment.workload_need
        for assignment in cancelled
    }
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

    for assignment in cancelled:
        before = assignment_snapshot(assignment)
        assignment.status = "CANCELLED"
        assignment.revision += 1
        assignment.updated_by_user_id = user_id
        db.session.add(WorkloadAssignmentChange(
            workload_assignment=assignment,
            change_kind="CANCEL",
            changed_by_user_id=user_id,
            before_data=before,
            after_data=assignment_snapshot(assignment),
            reason=(
                "Автоматическое снятие нагрузки: строка учебного плана "
                "удалена, заменена или разделена на другое число групп."
            ),
        ))

    db.session.flush()
    for need in old_needs | new_needs:
        refresh_need_status(need)
    return AssignmentRelinkResult(
        transferred=len(mappings),
        cancelled=len(cancelled),
    )


__all__ = [
    "AssignmentRelinkResult",
    "relink_assignments_to_population_snapshot",
]
