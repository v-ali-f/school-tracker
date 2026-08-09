from datetime import date

from app.core.extensions import db
from app.models import (
    Department,
    DepartmentLeader,
    EducationActivity,
    TeacherLoad,
    TeacherMckoResult,
    TeacherProfessionalRecordChange,
    User,
)


def _activity():
    item = EducationActivity(
        code="registry-mathematics",
        name="Математика",
        activity_kind="SUBJECT",
        is_global=True,
        is_active=True,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_admin_registry_lists_teacher_without_diagnostic_and_hub_link(
    app, client, make_user, login
):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        department = Department(name="Кафедра математики")
        db.session.add(department)
        db.session.flush()
        db.session.add(TeacherLoad(
            teacher_id=teacher_id,
            department_id=department.id,
            subject_name="Математика",
            hours=4,
        ))
        db.session.commit()

    login(admin_id)
    hub = client.get("/hub/registries")
    registry = client.get("/professional-registers/mcko")

    assert hub.status_code == 200
    assert "Результаты МЦКО педагогов" in hub.get_data(as_text=True)
    assert registry.status_code == 200
    html = registry.get_data(as_text=True)
    assert "Кафедра математики" in html
    assert "Диагностика отсутствует" in html
    assert "Добавить результат" in html


def test_deputy_creates_edits_and_archives_mcko_with_history(
    app, client, make_user, login
):
    deputy_id = make_user("DEPUTY_DIRECTOR")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        activity_id = _activity().id

    login(deputy_id)
    created = client.post(
        "/professional-registers/mcko/new",
        data={
            "teacher_id": teacher_id,
            "education_activity_id": activity_id,
            "level": "HIGH",
            "passed_at": "2026-05-20",
            "certificate_number": "MCKO-2026-10",
        },
    )
    assert created.status_code == 302

    with app.app_context():
        record = TeacherMckoResult.query.one()
        assert record.entry_source == "ADMINISTRATION"
        assert record.created_by_user_id == deputy_id
        assert record.expires_at == date(2029, 5, 20)
        record_id = record.id

    edited = client.post(
        f"/professional-registers/mcko/{record_id}/edit",
        data={
            "teacher_id": teacher_id,
            "education_activity_id": activity_id,
            "level": "EXPERT",
            "passed_at": "2026-06-01",
            "certificate_number": "MCKO-2026-11",
        },
    )
    archived = client.post(f"/professional-registers/mcko/{record_id}/archive")
    assert edited.status_code == 302
    assert archived.status_code == 302

    with app.app_context():
        record = db.session.get(TeacherMckoResult, record_id)
        assert record.level == "EXPERT"
        assert record.expires_at == date(2029, 6, 1)
        assert record.is_archived is True
        changes = TeacherProfessionalRecordChange.query.order_by(
            TeacherProfessionalRecordChange.id
        ).all()
        assert [item.change_kind for item in changes] == ["CREATED", "UPDATED", "ARCHIVED"]
        assert all(item.changed_by_user_id == deputy_id for item in changes)


def test_registry_shows_self_reported_source_and_filters_status(
    app, client, make_user, login
):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        activity_id = _activity().id

    login(teacher_id)
    response = client.post(
        "/departments/teacher/mcko/add",
        data={
            "teacher_id": teacher_id,
            "subject_id": activity_id,
            "passed_at": "2026-05-20",
            "level": "HIGH",
        },
    )
    assert response.status_code == 302
    assert client.get("/professional-registers/mcko").status_code == 403

    login(admin_id)
    registry = client.get("/professional-registers/mcko?status=ACTIVE")
    html = registry.get_data(as_text=True)
    assert registry.status_code == 200
    assert "Внесено педагогом" in html
    assert "Тестов Пользователь" in html


def test_viewer_cannot_manage_registry(app, client, make_user, login):
    methodist_id = make_user("METHODIST")
    login(methodist_id)

    assert client.get("/professional-registers/mcko").status_code == 200
    assert client.get("/professional-registers/mcko/new").status_code == 403


def test_department_head_sees_only_own_department_teachers(
    app, client, make_user, login
):
    head_id = make_user("DEPARTMENT_HEAD")
    own_teacher_id = make_user("TEACHER")
    other_teacher_id = make_user("TEACHER")
    with app.app_context():
        db.session.get(User, own_teacher_id).last_name = "Свой"
        db.session.get(User, other_teacher_id).last_name = "Чужой"
        own_department = Department(name="Своя кафедра")
        other_department = Department(name="Другая кафедра")
        db.session.add_all([own_department, other_department])
        db.session.flush()
        db.session.add_all([
            DepartmentLeader(department_id=own_department.id, user_id=head_id),
            TeacherLoad(
                teacher_id=own_teacher_id,
                department_id=own_department.id,
                subject_name="Математика",
                hours=4,
            ),
            TeacherLoad(
                teacher_id=other_teacher_id,
                department_id=other_department.id,
                subject_name="Физика",
                hours=4,
            ),
        ])
        db.session.commit()

    login(head_id)
    response = client.get("/professional-registers/mcko")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Своя кафедра" in html
    assert "Свой Пользователь" in html
    assert "Чужой Пользователь" not in html
    assert "Другая кафедра" not in html
    assert html.count("Диагностика отсутствует") == 1
