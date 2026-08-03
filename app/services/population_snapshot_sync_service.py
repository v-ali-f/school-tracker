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


__all__ = ["register_population_snapshot_sync"]
