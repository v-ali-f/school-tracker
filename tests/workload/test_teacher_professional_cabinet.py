from datetime import date

from app.core.extensions import db
from app.models import (
    AcademicYear,
    EducationActivity,
    TeacherAttestation,
    TeacherCourse,
    TeacherMckoResult,
)
from app.services.teacher_mcko_service import mcko_results_for_teachers


def _subject():
    subject = EducationActivity(
        code="mathematics",
        name="Математика",
        short_name="Математика",
        activity_kind="SUBJECT",
        is_global=True,
        is_active=True,
    )
    db.session.add(subject)
    db.session.commit()
    return subject


def test_mcko_requires_explicit_teacher(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        subject_id = _subject().id

    login(admin_id)
    response = client.post(
        "/departments/teacher/mcko/add",
        data={
            "subject_id": subject_id,
            "passed_at": "2026-05-26",
            "level": "HIGH",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Сначала выберите преподавателя." in response.get_data(as_text=True)
    with app.app_context():
        assert TeacherMckoResult.query.count() == 0


def test_teacher_manages_own_professional_records_only(
    app,
    client,
    make_user,
    login,
):
    teacher_id = make_user("TEACHER")
    other_teacher_id = make_user("TEACHER")
    with app.app_context():
        subject_id = _subject().id

    login(teacher_id)
    mcko = client.post(
        "/departments/teacher/mcko/add",
        data={
            "teacher_id": teacher_id,
            "subject_id": subject_id,
            "passed_at": "2026-05-26",
            "level": "HIGH",
        },
    )
    course = client.post(
        "/departments/teacher/course/add",
        data={
            "teacher_id": teacher_id,
            "title": "Современные методики обучения",
            "provider": "ГАОУ ДПО",
            "hours": "36",
            "end_date": "2026-06-01",
        },
    )
    attestation = client.post(
        "/departments/teacher/attestation/add",
        data={
            "teacher_id": teacher_id,
            "category": "HIGHEST",
            "decision_date": "2026-04-15",
            "valid_until": "2031-04-15",
        },
    )
    forbidden = client.post(
        "/departments/teacher/course/add",
        data={
            "teacher_id": other_teacher_id,
            "title": "Чужой курс",
        },
    )

    assert mcko.status_code == 302
    assert course.status_code == 302
    assert attestation.status_code == 302
    assert forbidden.status_code == 403
    with app.app_context():
        assert TeacherMckoResult.query.filter_by(teacher_id=teacher_id).count() == 1
        assert TeacherCourse.query.filter_by(teacher_id=teacher_id).count() == 1
        record = TeacherAttestation.query.filter_by(teacher_id=teacher_id).one()
        assert record.category == "HIGHEST"
        assert record.valid_until == date(2031, 4, 15)
        assert TeacherCourse.query.filter_by(teacher_id=other_teacher_id).count() == 0

    cabinet = client.get(f"/departments/teachers/{teacher_id}")
    html = cabinet.get_data(as_text=True)
    assert cabinet.status_code == 200
    assert "Кабинет преподавателя" in html
    assert "Современные методики обучения" in html
    assert "Высшая квалификационная категория" in html
    assert "Высокий" in html


def test_department_index_exposes_teacher_cabinet_links(
    app,
    client,
    make_user,
    login,
):
    teacher_id = make_user("TEACHER")
    login(teacher_id)
    teacher_page = client.get("/departments/")
    teacher_html = teacher_page.get_data(as_text=True)

    assert teacher_page.status_code == 200
    assert "Мой кабинет" in teacher_html
    assert 'href="/departments/teacher/cabinet"' in teacher_html

    admin_id = make_user("ADMIN")
    login(admin_id)
    admin_page = client.get("/departments/")
    admin_html = admin_page.get_data(as_text=True)

    assert admin_page.status_code == 200
    assert "Кабинеты преподавателей" in admin_html
    assert 'href="/departments/summary#department-teachers"' in admin_html


def test_mcko_history_can_be_filtered_by_academic_year(
    app,
    make_user,
):
    teacher_id = make_user("TEACHER")
    with app.app_context():
        first_year = AcademicYear(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 8, 31),
        )
        second_year = AcademicYear(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
        )
        subject = _subject()
        db.session.add_all([first_year, second_year])
        db.session.flush()
        db.session.add_all([
            TeacherMckoResult(
                teacher_id=teacher_id,
                education_activity_id=subject.id,
                academic_year_id=first_year.id,
                passed_at=date(2026, 5, 20),
                level="BASIC",
            ),
            TeacherMckoResult(
                teacher_id=teacher_id,
                education_activity_id=subject.id,
                academic_year_id=second_year.id,
                passed_at=date(2027, 5, 20),
                level="HIGH",
            ),
        ])
        db.session.commit()

        first_rows = mcko_results_for_teachers(
            [teacher_id],
            academic_year_id=first_year.id,
        )
        second_rows = mcko_results_for_teachers(
            [teacher_id],
            academic_year_id=second_year.id,
        )

        assert [row.level_code for row in first_rows] == ["BASIC"]
        assert [row.level_code for row in second_rows] == ["HIGH"]
