from app.core.extensions import db
from app.models import (
    Department,
    DepartmentLeader,
    EducationActivity,
    EducationActivityDepartment,
    User,
)


def _activity(code, name, activity_kind, department_id):
    activity = EducationActivity(
        code=code,
        name=name,
        activity_kind=activity_kind,
        is_global=True,
        is_tariffable=True,
        is_active=True,
    )
    db.session.add(activity)
    db.session.flush()
    db.session.add(EducationActivityDepartment(
        education_activity_id=activity.id,
        department_id=department_id,
        is_primary=True,
        is_active=True,
    ))
    return activity


def test_department_settings_only_displays_registry_activities_and_teachers(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    viewer_id = make_user("VIEWER")
    with app.app_context():
        teacher = db.session.get(User, teacher_id)
        teacher.last_name = "Учитель"
        teacher.first_name = "Мария"
        viewer = db.session.get(User, viewer_id)
        viewer.last_name = "Наблюдатель"
        viewer.first_name = "Иван"
        department = Department(
            name="Кафедра проектной деятельности",
            code="projects",
        )
        db.session.add(department)
        db.session.flush()
        _activity(
            "PROJECT_COURSE",
            "Школьный проект",
            "COURSE",
            department.id,
        )
        _activity(
            "PROJECT_AFTER_SCHOOL",
            "Школьный проект",
            "EXTRACURRICULAR_COURSE",
            department.id,
        )
        db.session.commit()
    login(admin_id)

    response = client.get("/departments/settings")

    assert response.status_code == 200
    html = response.data.decode()
    assert 'name="subject_ids"' not in html
    assert "Изменить в реестре" in html
    assert html.count("Школьный проект") == 2
    assert "Учебный курс" in html
    assert "Внеурочный курс" in html
    assert "Учитель Мария" in html
    assert "Наблюдатель Иван" not in html
    assert "data-leader-picker" in html
    assert "Исключить" not in html


def test_department_update_does_not_change_registry_links(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        department = Department(name="Кафедра курсов", code="courses")
        db.session.add(department)
        db.session.flush()
        activity = _activity(
            "MEDIA_COURSE",
            "Медиаграмотность",
            "COURSE",
            department.id,
        )
        db.session.commit()
        department_id = department.id
        activity_id = activity.id
    login(admin_id)

    response = client.post(
        f"/departments/settings/{department_id}/update",
        data={
            "name": "Кафедра учебных курсов",
            "description": "Новое описание",
            "subject_ids": [],
        },
    )

    assert response.status_code == 302
    with app.app_context():
        department = db.session.get(Department, department_id)
        link = EducationActivityDepartment.query.filter_by(
            education_activity_id=activity_id,
            department_id=department_id,
        ).one()
        assert department.name == "Кафедра учебных курсов"
        assert department.description == "Новое описание"
        assert link.is_active is True


def test_only_teacher_candidates_can_be_department_leaders(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("CLASS_TEACHER")
    viewer_id = make_user("VIEWER")
    with app.app_context():
        department = Department(name="Кафедра наставников", code="mentors")
        db.session.add(department)
        db.session.commit()
        department_id = department.id
    login(admin_id)

    rejected = client.post(
        f"/departments/settings/{department_id}/leader/add",
        data={"user_id": str(viewer_id)},
    )

    assert rejected.status_code == 302
    with app.app_context():
        assert DepartmentLeader.query.filter_by(
            department_id=department_id,
        ).count() == 0

    accepted = client.post(
        f"/departments/settings/{department_id}/leader/add",
        data={"user_id": str(teacher_id)},
    )

    assert accepted.status_code == 302
    with app.app_context():
        leader = DepartmentLeader.query.filter_by(
            department_id=department_id,
            user_id=teacher_id,
        ).one()
        leader_id = leader.id

    page = client.get("/departments/settings")

    assert page.status_code == 200
    assert "Исключить".encode() in page.data

    deleted = client.post(
        f"/departments/settings/leader/{leader_id}/delete",
    )

    assert deleted.status_code == 302
    with app.app_context():
        assert db.session.get(DepartmentLeader, leader_id) is None
