"""Undo duplicate historical assignments from a snapshot relink operation."""

from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal

from app import create_app
from app.core.extensions import db
from app.models import (
    WorkloadAssignment,
    WorkloadAssignmentChange,
    WorkloadNeed,
)
from app.services.workload_distribution_service import (
    assignment_snapshot,
    refresh_need_status,
)


RELINK_REASON = (
    "Автоматическая перепривязка нагрузки к обновлённому снимку контингента."
)
NORMALIZE_REASON = (
    "Возврат исторического дубля после перепривязки нагрузки к новому снимку."
)


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-id", type=int, required=True)
    parser.add_argument("--target-snapshot-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def _need_class_key(need):
    group = need.teaching_group
    return tuple(sorted({
        link.population_snapshot_class.source_school_class_id
        for link in group.source_classes
    }))


def _need_snapshot_revision(need):
    return max((
        link.population_snapshot_class.population_snapshot.revision_no
        for link in need.teaching_group.source_classes
    ), default=0)


def _logical_key(assignment, old_need):
    holder = (
        ("vacancy", assignment.position_code)
        if assignment.assignment_kind == "VACANCY"
        else ("teacher", assignment.employee_user_id)
    )
    return (
        old_need.teaching_group.source_plan_line_id,
        _need_class_key(old_need),
        old_need.need_kind,
        old_need.date_from,
        old_need.date_to,
        holder,
    )


def run(version_id, target_snapshot_id, apply_changes=False):
    changes = (
        WorkloadAssignmentChange.query
        .join(WorkloadAssignment)
        .filter(
            WorkloadAssignment.tariff_version_id == version_id,
            WorkloadAssignment.status != "CANCELLED",
            WorkloadAssignmentChange.change_kind == "TRANSFER",
            WorkloadAssignmentChange.reason == RELINK_REASON,
        )
        .order_by(WorkloadAssignmentChange.id.asc())
        .all()
    )
    records = []
    for change in changes:
        old_need_id = (change.before_data or {}).get("workload_need_id")
        old_need = db.session.get(WorkloadNeed, old_need_id)
        assignment = change.workload_assignment
        if old_need is None or assignment.workload_need_id == old_need_id:
            continue
        target_snapshot_ids = {
            link.population_snapshot_class.population_snapshot_id
            for link in assignment.workload_need.teaching_group.source_classes
        }
        if target_snapshot_ids != {target_snapshot_id}:
            continue
        records.append((assignment, old_need))

    by_key = defaultdict(list)
    for assignment, old_need in records:
        by_key[_logical_key(assignment, old_need)].append((assignment, old_need))

    keep_ids = set()
    for items in by_key.values():
        newest = max(items, key=lambda item: (
            _need_snapshot_revision(item[1]),
            item[0].created_at,
            item[0].id,
        ))
        keep_ids.add(newest[0].id)
    reverts = [
        (assignment, old_need)
        for assignment, old_need in records
        if assignment.id not in keep_ids
    ]
    revert_hours = sum(
        (Decimal(item.weekly_hours or 0) for item, _ in reverts),
        Decimal("0"),
    )
    print(
        f"reviewed={len(records)} logical_assignments={len(keep_ids)} "
        f"historical_duplicates={len(reverts)} duplicate_hours={revert_hours}"
    )
    if not apply_changes:
        db.session.rollback()
        print("dry_run=true")
        return

    actor_user_id = changes[-1].changed_by_user_id if changes else None
    if actor_user_id is None:
        raise RuntimeError("Audit author was not found.")
    current_needs = set()
    old_needs = set()
    for assignment, old_need in reverts:
        current_need = assignment.workload_need
        before = assignment_snapshot(assignment)
        before["workload_need_id"] = current_need.id
        assignment.workload_need = old_need
        assignment.building_id = old_need.building_id
        assignment.revision += 1
        assignment.updated_by_user_id = actor_user_id
        after = assignment_snapshot(assignment)
        after["workload_need_id"] = old_need.id
        db.session.add(WorkloadAssignmentChange(
            workload_assignment=assignment,
            change_kind="TRANSFER",
            changed_by_user_id=actor_user_id,
            before_data=before,
            after_data=after,
            reason=NORMALIZE_REASON,
        ))
        current_needs.add(current_need)
        old_needs.add(old_need)
    db.session.flush()
    for need in current_needs | old_needs:
        refresh_need_status(need)
    db.session.commit()
    print(f"applied={len(reverts)}")


if __name__ == "__main__":
    args = _arguments()
    app = create_app()
    with app.app_context():
        run(args.version_id, args.target_snapshot_id, args.apply)
