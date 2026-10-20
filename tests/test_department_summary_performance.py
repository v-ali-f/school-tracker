from app import departments as department_views
from app.core.extensions import db
from app.models import (
    AcademicYear,
    Child,
    ControlWork,
    ControlWorkAssignment,
    ControlWorkResult,
    Department,
    DepartmentSubject,
    EducationActivity,
    SchoolClass,
    Subject,
)
from app.models.diagnostics import (
    DiagnosticResult,
    DiagnosticSession,
    DiagnosticTeacherBinding,
)
from app.services.olympiad_stats_service import department_overview_stats
from sqlalchemy import event


def test_opening_mcko_does_not_build_other_detailed_tables(
    app, client, make_user, login, monkeypatch,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        department = Department(name="Кафедра быстрой загрузки", code="summary-fast")
        db.session.add(department)
        db.session.commit()
        department_id = department.id

    def unexpected(*args, **kwargs):
        raise AssertionError("Скрытый раздел не должен рассчитываться")

    monkeypatch.setattr(department_views, "_control_work_stats", unexpected)
    monkeypatch.setattr(department_views, "_diagnostics_department_stats", unexpected)
    monkeypatch.setattr(department_views, "olympiad_department_stats", unexpected)
    monkeypatch.setattr(department_views, "attestation_overviews_for_teachers", unexpected)
    login(admin_id)

    response = client.get(f"/departments/summary?department_id={department_id}&section=mcko")

    assert response.status_code == 200
    assert b'id="section-mcko"' in response.data


def test_diagnostic_count_and_details_use_same_department_scope(
    app, make_user,
):
    teacher_id = make_user("TEACHER")
    with app.app_context():
        department = Department(name="Кафедра физики", code="physics-summary")
        subject = Subject(name="Физика")
        db.session.add_all([department, subject])
        db.session.flush()
        db.session.add(DepartmentSubject(
            department_id=department.id,
            subject_id=subject.id,
        ))
        sessions = [
            DiagnosticSession(title="Физика", subject="Физика"),
            DiagnosticSession(title="Химия", subject="Химия"),
            DiagnosticSession(title="Биология", subject="Биология"),
        ]
        db.session.add_all(sessions)
        db.session.flush()
        results = [
            DiagnosticResult(session_id=sessions[0].id),
            DiagnosticResult(session_id=sessions[0].id),
            DiagnosticResult(session_id=sessions[1].id),
            DiagnosticResult(session_id=sessions[2].id),
        ]
        db.session.add_all(results)
        db.session.flush()
        db.session.add(DiagnosticTeacherBinding(
            result_id=results[2].id,
            teacher_id=teacher_id,
        ))
        db.session.commit()

        assert department_views._diagnostics_department_count(department, [teacher_id]) == 3
        assert department_views._diagnostics_department_stats(
            department, [teacher_id]
        )["total_results"] == 3
        assert department_views._diagnostics_department_count(
            department, [teacher_id], selected_teacher_id=teacher_id,
        ) == 1


def test_control_work_card_matches_detailed_result(app, make_user):
    teacher_id = make_user("TEACHER")
    with app.app_context():
        year = AcademicYear(name="2026/2027")
        department = Department(name="Кафедра контрольных", code="control-summary")
        activity = EducationActivity(
            code="CONTROL_PHYSICS", name="Физика", activity_kind="SUBJECT",
            is_global=True,
        )
        subject = Subject(name="Физика", education_activity=activity)
        child = Child(last_name="Ученик", first_name="Первый")
        db.session.add_all([year, department, subject, child])
        db.session.flush()
        db.session.add(DepartmentSubject(
            department_id=department.id,
            subject_id=subject.id,
            education_activity_id=activity.id,
        ))
        school_class = SchoolClass(name="7А", academic_year_id=year.id)
        work = ControlWork(
            theme="Контрольная", subject_id=subject.id,
            education_activity_id=activity.id,
        )
        db.session.add_all([school_class, work])
        db.session.flush()
        assignment = ControlWorkAssignment(
            control_work_id=work.id,
            school_class_id=school_class.id,
            teacher_id=teacher_id,
        )
        db.session.add(assignment)
        db.session.flush()
        db.session.add(ControlWorkResult(
            control_work_id=work.id,
            assignment_id=assignment.id,
            school_class_id=school_class.id,
            academic_year_id=year.id,
            child_id=child.id,
            percent=78.0,
        ))
        db.session.commit()

        card = department_views._control_work_summary(
            department, teacher_id=teacher_id, academic_year_id=year.id,
        )
        details = department_views._control_work_stats(
            department, teacher_id=teacher_id, academic_year_id=year.id,
        )
        assert card["total_results"] == details["total_results"] == 1
        assert card["avg_percent"] == details["avg_percent"] == 78.0


def test_olympiad_card_read_does_not_run_schema_updates(app):
    with app.app_context():
        statements = []

        def record_statement(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.lstrip().upper())

        event.listen(db.engine, "before_cursor_execute", record_statement)
        try:
            overview = department_overview_stats()
        finally:
            event.remove(db.engine, "before_cursor_execute", record_statement)

        assert overview["total_results"] == 0
        assert all(not statement.startswith(("ALTER ", "UPDATE ")) for statement in statements)
