
from datetime import date

from app.core.extensions import db
from .models import Document, TeacherLoad, TeacherMckoResult, TeacherCourse, ControlWork, ControlWorkResult


def apply_retention_policies(today=None):
    today = today or date.today()
    stats = {
        "documents_hidden": 0,
        "documents_restored": 0,
        "teacher_load_archived": 0,
        "teacher_mcko_archived": 0,
        "teacher_courses_archived": 0,
        "control_works_expired": 0,
        "control_results_expired": 0,
    }

    for doc in Document.query.all():
        should_hide = bool(doc.retention_until and doc.retention_until < today)
        if should_hide and not doc.is_hidden_by_retention:
            doc.is_hidden_by_retention = True
            doc.is_archived = True
            stats["documents_hidden"] += 1
        elif (not should_hide) and doc.is_hidden_by_retention:
            doc.is_hidden_by_retention = False
            stats["documents_restored"] += 1

    for row in TeacherLoad.query.all():
        should_archive = bool(row.retention_until and row.retention_until < today)
        if should_archive and not row.is_archived:
            row.is_archived = True
            stats["teacher_load_archived"] += 1

    for row in TeacherMckoResult.query.all():
        should_archive = bool(row.retention_until and row.retention_until < today)
        if should_archive and not row.is_archived:
            row.is_archived = True
            stats["teacher_mcko_archived"] += 1

    for row in TeacherCourse.query.all():
        should_archive = bool(row.retention_until and row.retention_until < today)
        if should_archive and not row.is_archived:
            row.is_archived = True
            stats["teacher_courses_archived"] += 1

    for row in ControlWork.query.all():
        should_archive = bool(getattr(row, 'retention_until', None) and row.retention_until < today)
        if should_archive and not getattr(row, 'is_archived', False):
            try:
                row.is_archived = True
                stats["control_works_expired"] += 1
            except Exception:
                pass

    for row in ControlWorkResult.query.all():
        should_archive = bool(getattr(row, 'retention_until', None) and row.retention_until < today)
        if should_archive and not getattr(row, 'is_archived', False):
            try:
                row.is_archived = True
                stats["control_results_expired"] += 1
            except Exception:
                pass

    db.session.commit()
    return stats
