from __future__ import annotations

from app.models import DiagnosticKesResult, DiagnosticResult, DiagnosticSession, DiagnosticTaskResult, Department, Subject, User


def get_visible_results_query():
    return DiagnosticResult.query.filter_by(is_final=True)


def get_all_sessions():
    return DiagnosticSession.query.order_by(DiagnosticSession.created_at.desc()).all()


def get_task_rows_for_results(result_ids: set[int] | list[int]):
    if not result_ids:
        return []
    return DiagnosticTaskResult.query.filter(DiagnosticTaskResult.result_id.in_(list(result_ids))).all()


def get_kes_rows_for_session(session_id: int | None):
    if not session_id:
        return []
    return DiagnosticKesResult.query.filter_by(session_id=session_id).all()


def get_subject_choices():
    values = []
    for item in Subject.query.order_by(Subject.name.asc()).all():
        if getattr(item, "name", None):
            values.append(item.name)
    for row in DiagnosticSession.query.filter(DiagnosticSession.subject.isnot(None)).distinct(DiagnosticSession.subject).all():
        if getattr(row, "subject", None):
            values.append(row.subject)
    unique = []
    seen = set()
    for value in values:
        key = str(value).strip().lower()
        if key and key not in seen:
            unique.append(str(value).strip())
            seen.add(key)
    return unique


def get_teacher_choices():
    return User.query.order_by(User.last_name.asc(), User.first_name.asc(), User.username.asc()).all()


def get_department_choices():
    return Department.query.order_by(Department.name.asc()).all()
