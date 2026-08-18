from sqlalchemy import event
from sqlalchemy.orm import Session


_PENDING_ENROLLMENTS_KEY = "altair_pending_snapshot_enrollments"
_listeners_registered = False


def _is_active_class_enrollment(enrollment):
    return bool(
        enrollment.school_class_id
        and enrollment.status == "ACTIVE"
        and enrollment.ended_at is None
    )


def _remember_new_enrollments(session, _flush_context, _instances):
    from app.models import ChildEnrollment

    pending = [
        enrollment
        for enrollment in session.new
        if (
            isinstance(enrollment, ChildEnrollment)
            and _is_active_class_enrollment(enrollment)
        )
    ]
    if pending:
        session.info.setdefault(_PENDING_ENROLLMENTS_KEY, []).extend(pending)


def _sync_new_enrollment(session, enrollment):
    from app.models import (
        Child,
        PopulationSnapshot,
        PopulationSnapshotClass,
        PopulationSnapshotEnrollment,
        TariffCycle,
        TariffVersion,
        TeachingGroupCompositionApproval,
    )

    if not _is_active_class_enrollment(enrollment):
        return 0

    child = session.get(Child, enrollment.child_id)
    if child is None:
        return 0

    snapshots = (
        session.query(PopulationSnapshot)
        .join(TariffVersion)
        .join(TariffCycle)
        .filter(
            TariffCycle.academic_year_id == enrollment.academic_year_id,
            TariffVersion.status == "DRAFT",
            PopulationSnapshot.status == "CURRENT",
        )
        .all()
    )
    added = 0
    for snapshot in snapshots:
        already_in_snapshot = (
            session.query(PopulationSnapshotEnrollment.id)
            .join(PopulationSnapshotClass)
            .filter(
                PopulationSnapshotClass.population_snapshot_id == snapshot.id,
                PopulationSnapshotEnrollment.source_child_id == child.id,
            )
            .first()
        )
        if already_in_snapshot is not None:
            continue

        snapshot_class = (
            session.query(PopulationSnapshotClass)
            .filter_by(
                population_snapshot_id=snapshot.id,
                source_school_class_id=enrollment.school_class_id,
            )
            .first()
        )
        if snapshot_class is None:
            continue

        started_on = (
            enrollment.enrolled_at.date()
            if enrollment.enrolled_at else None
        )
        session.add(PopulationSnapshotEnrollment(
            population_snapshot_class_id=snapshot_class.id,
            source_child_id=child.id,
            source_enrollment_id=enrollment.id,
            fio_snapshot=child.fio,
            status_snapshot=enrollment.status,
            started_on=started_on,
            ended_on=None,
        ))
        snapshot_class.student_count = int(
            snapshot_class.student_count or 0
        ) + 1
        (
            session.query(TeachingGroupCompositionApproval)
            .filter_by(
                tariff_version_id=snapshot.tariff_version_id,
                population_snapshot_class_id=snapshot_class.id,
            )
            .delete(synchronize_session=False)
        )
        added += 1
    return added


def _sync_remembered_enrollments(session, _flush_context):
    pending = session.info.pop(_PENDING_ENROLLMENTS_KEY, ())
    for enrollment in pending:
        _sync_new_enrollment(session, enrollment)


def _single_building_id(values):
    building_ids = set(values)
    return next(iter(building_ids)) if len(building_ids) == 1 else None


def _sync_group_building(session, group, building_id):
    """Move a group and its inherited workload rows to the class building."""
    from app.models import WorkloadAssignment, WorkloadNeed

    old_group_building_id = group.building_id
    if old_group_building_id == building_id:
        return False
    group.building_id = building_id
    group.revision = int(group.revision or 0) + 1
    needs = session.query(WorkloadNeed).filter_by(
        teaching_group_id=group.id
    ).all()
    for need in needs:
        old_need_building_id = need.building_id
        need.building_id = building_id
        need.revision = int(need.revision or 0) + 1
        assignments = session.query(WorkloadAssignment).filter_by(
            workload_need_id=need.id
        ).all()
        for assignment in assignments:
            if assignment.building_id == old_need_building_id:
                assignment.building_id = building_id
                assignment.revision = int(assignment.revision or 0) + 1
    return True


def sync_teaching_group_buildings(session, group_ids):
    """Recalculate group/workload buildings from their current class links."""
    from app.models import (
        PopulationSnapshotClass,
        TeachingGroup,
        TeachingGroupClass,
        TeachingMetagroupSource,
    )

    frontier = set(group_ids)
    changed_group_ids = set()
    processed_group_ids = set()
    while frontier:
        current_ids = frontier - processed_group_ids
        if not current_ids:
            break
        groups = session.query(TeachingGroup).filter(
            TeachingGroup.id.in_(current_ids),
            TeachingGroup.status != "CLOSED",
        ).all()
        for group in groups:
            source_building_ids = [
                row[0]
                for row in (
                    session.query(PopulationSnapshotClass.building_id)
                    .join(TeachingGroupClass)
                    .filter(
                        TeachingGroupClass.teaching_group_id == group.id
                    )
                    .all()
                )
            ]
            if _sync_group_building(
                session,
                group,
                _single_building_id(source_building_ids),
            ):
                changed_group_ids.add(group.id)
        processed_group_ids.update(current_ids)

        parent_ids = {
            row[0]
            for row in (
                session.query(TeachingMetagroupSource.metagroup_id)
                .filter(
                    TeachingMetagroupSource.source_group_id.in_(current_ids)
                )
                .all()
            )
        }
        for metagroup in session.query(TeachingGroup).filter(
            TeachingGroup.id.in_(parent_ids),
            TeachingGroup.status != "CLOSED",
        ).all():
            source_building_ids = [
                row[0]
                for row in (
                    session.query(TeachingGroup.building_id)
                    .join(
                        TeachingMetagroupSource,
                        TeachingMetagroupSource.source_group_id
                        == TeachingGroup.id,
                    )
                    .filter(
                        TeachingMetagroupSource.metagroup_id == metagroup.id
                    )
                    .all()
                )
            ]
            if _sync_group_building(
                session,
                metagroup,
                _single_building_id(source_building_ids),
            ):
                changed_group_ids.add(metagroup.id)
        frontier = parent_ids
    return changed_group_ids


def sync_school_class_structure(session, school_class):
    """Keep active draft workload snapshots aligned with the class registry.

    The population snapshot is intentionally materialized, so changing a
    class building in the core registry otherwise leaves workload filters on
    the old value until a manual snapshot refresh.
    """
    from app.models import (
        Building,
        PopulationSnapshot,
        PopulationSnapshotClass,
        TariffCycle,
        TariffVersion,
        TeachingGroup,
        TeachingGroupClass,
    )
    from app.services.teaching_group_service import (
        _live_population_checksum,
    )

    building = (
        session.get(Building, school_class.building_id)
        if school_class.building_id is not None else None
    )
    building_name = (
        building.short_name or building.name if building is not None else None
    )
    snapshot_classes = (
        session.query(PopulationSnapshotClass)
        .join(PopulationSnapshot)
        .join(TariffVersion)
        .join(TariffCycle)
        .filter(
            PopulationSnapshotClass.source_school_class_id
            == school_class.id,
            PopulationSnapshot.status == "CURRENT",
            TariffVersion.status == "DRAFT",
            TariffCycle.academic_year_id == school_class.academic_year_id,
        )
        .all()
    )
    if not snapshot_classes:
        return {"snapshots": 0, "groups": 0}

    snapshot_ids = set()
    snapshot_class_ids = set()
    for snapshot_class in snapshot_classes:
        snapshot_class.name_snapshot = school_class.name
        snapshot_class.grade_snapshot = school_class.grade
        snapshot_class.building_id = school_class.building_id
        snapshot_class.building_name_snapshot = building_name
        snapshot_ids.add(snapshot_class.population_snapshot_id)
        snapshot_class_ids.add(snapshot_class.id)
    session.flush()

    direct_groups = (
        session.query(TeachingGroup)
        .join(TeachingGroupClass)
        .filter(
            TeachingGroupClass.population_snapshot_class_id.in_(
                snapshot_class_ids
            ),
            TeachingGroup.status != "CLOSED",
        )
        .all()
    )
    changed_group_ids = sync_teaching_group_buildings(
        session,
        {group.id for group in direct_groups},
    )

    checksum = _live_population_checksum(school_class.academic_year_id)
    session.query(PopulationSnapshot).filter(
        PopulationSnapshot.id.in_(snapshot_ids)
    ).update({"checksum": checksum}, synchronize_session=False)
    return {
        "snapshots": len(snapshot_ids),
        "groups": len(changed_group_ids),
    }


def register_population_snapshot_sync():
    """Keep draft class snapshots current when a genuinely new pupil is added."""
    global _listeners_registered
    if _listeners_registered:
        return
    event.listen(Session, "before_flush", _remember_new_enrollments)
    event.listen(
        Session,
        "after_flush_postexec",
        _sync_remembered_enrollments,
    )
    _listeners_registered = True


__all__ = [
    "register_population_snapshot_sync",
    "sync_school_class_structure",
    "sync_teaching_group_buildings",
]
