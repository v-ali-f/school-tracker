from datetime import date

from app.core.extensions import db
from app.models import (
    EducationActivity,
    TeacherAttestation,
    TeacherCourse,
    TeacherMckoResult,
)


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
