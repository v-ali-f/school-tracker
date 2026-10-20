from app.core.extensions import db
from app.models import (
    Department,
    DepartmentLeader,
    DepartmentSubject,
    DepartmentTeacherMembership,
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


def test_department_pages_use_shared_workspace_shell(
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    login(admin_id)

    for path in (
        "/departments/settings",
        "/departments/loads",
        "/departments/summary",
        f"/departments/teachers/{teacher_id}",
    ):
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'class="sp-workspace ws-workspace"' in html
        assert "workspace_ui.css" in html
        assert "departments_workspace.css" in html
        assert 'class="departments-section-tabs"' in html
        if path == "/departments/summary":
            assert 'class="department-directions"' in html
            assert 'id="summary-details"' not in html


def test_summary_opens_only_selected_direction_for_department_head(
    app,
    client,
    make_user,
    login,
):
    head_id = make_user("DEPARTMENT_HEAD")
    methodist_head_id = make_user("METHODIST")
    with app.app_context():
        own = Department(name="Кафедра руководителя", code="head-own")
        other = Department(name="Другая кафедра", code="head-other")
        db.session.add_all([own, other])
        db.session.flush()
        db.session.add(DepartmentLeader(department_id=own.id, user_id=head_id))
        db.session.add(DepartmentLeader(department_id=own.id, user_id=methodist_head_id))
        db.session.commit()
        own_id, other_id = own.id, other.id
    login(head_id)

    sections = {
        "load": 'id="section-load"',
        "control": 'id="section-control"',
        "diagnostics": 'id="section-diagnostics"',
        "olympiads": 'id="section-olympiads"',
        "mcko": 'id="section-mcko"',
        "training": 'id="section-training"',
        "attestation": 'id="section-attestation"',
    }
    for section, marker in sections.items():
        response = client.get(f"/departments/summary?department_id={own_id}&section={section}")
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'id="summary-details"' in html
        assert marker in html
        for other_section, other_marker in sections.items():
            if other_section != section:
                assert other_marker not in html
    fragment = client.get(
        f"/departments/summary?department_id={own_id}&section=training",
        headers={"X-Department-Summary": "details"},
    )
    fragment_html = fragment.get_data(as_text=True)
    assert fragment.status_code == 200
    assert 'id="summary-details"' in fragment_html
    assert 'id="section-training"' in fragment_html
    assert 'class="department-directions"' not in fragment_html
    assert 'id="section-mcko"' not in fragment_html
    assert client.get(f"/departments/summary?department_id={other_id}&section=mcko").status_code == 403
    assert client.get(
        f"/departments/summary?department_id={other_id}&section=training",
        headers={"X-Department-Summary": "details"},
    ).status_code == 403

    login(methodist_head_id)
    own_page = client.get("/departments/summary?section=mcko")
    assert own_page.status_code == 200
    assert 'id="section-mcko"' in own_page.get_data(as_text=True)
    assert client.get(f"/departments/summary?department_id={other_id}&section=mcko").status_code == 403


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
        department_id = department.id
    login(admin_id)

    response = client.get("/departments/settings")
    assert response.status_code == 200
    assert 'id="department-picker"' in response.get_data(as_text=True)
    assert 'id="department-detail"' not in response.get_data(as_text=True)
    assert "Школьный проект" not in response.get_data(as_text=True)

    response = client.get(f"/departments/settings?department_id={department_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="subject_ids"' not in html
    assert 'id="department-detail"' in html
    assert html.count("Школьный проект") == 2
    assert "Учебный курс" in html
    assert "Внеурочный курс" in html
    assert "Учитель Мария" in html
    assert "Наблюдатель Иван" not in html
    assert 'id="leader-choice"' in html
    assert 'id="department-members"' in html


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

    page = client.get(f"/departments/settings?department_id={department_id}")

    assert page.status_code == 200
    assert "Убрать".encode() in page.data

    deleted = client.post(
        f"/departments/settings/leader/{leader_id}/delete",
    )

    assert deleted.status_code == 302
    with app.app_context():
        assert db.session.get(DepartmentLeader, leader_id) is None


def test_settings_directory_skips_department_detail_queries(
    app, client, make_user, login, monkeypatch,
):
    import app.departments as department_routes

    admin_id = make_user("ADMIN")
    with app.app_context():
        db.session.add(Department(name="Кафедра для выбора", code="choose-only"))
        db.session.commit()
    login(admin_id)

    def unexpected(*args, **kwargs):
        raise AssertionError("Detailed department data should load after selection")

    monkeypatch.setattr(department_routes, "department_teacher_ids", unexpected)
    monkeypatch.setattr(department_routes, "_department_leader_candidates", unexpected)
    response = client.get("/departments/settings")
    assert response.status_code == 200
    assert 'id="department-picker"' in response.get_data(as_text=True)


def test_settings_can_manage_member_and_activity_for_selected_department(
    app, client, make_user, login,
):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        department = Department(name="Кафедра выбора", code="choice")
        db.session.add(department)
        db.session.flush()
        activity = EducationActivity(
            code="SETTINGS_ACTIVITY", name="Новый предмет",
            activity_kind="SUBJECT", is_global=True,
            is_tariffable=True, is_active=True,
        )
        db.session.add(activity)
        db.session.commit()
        department_id, activity_id = department.id, activity.id
    login(admin_id)

    added_member = client.post(
        f"/departments/settings/{department_id}/teacher/add",
        data={"teacher_id": str(teacher_id)},
    )
    assert added_member.status_code == 302
    assert f"department_id={department_id}" in added_member.headers["Location"]
    added_activity = client.post(
        f"/departments/settings/{department_id}/activity/add",
        data={"activity_id": str(activity_id)},
    )
    assert added_activity.status_code == 302
    with app.app_context():
        membership = DepartmentTeacherMembership.query.filter_by(
            department_id=department_id, teacher_id=teacher_id,
        ).one()
        assert membership.mode == "INCLUDE"
        link = EducationActivityDepartment.query.filter_by(
            department_id=department_id, education_activity_id=activity_id,
        ).one()
        assert link.is_active is True
        assert DepartmentSubject.query.filter_by(
            department_id=department_id, education_activity_id=activity_id,
        ).count() == 1
        link_id = link.id

    page = client.get(f"/departments/settings?department_id={department_id}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Новый предмет" in html
    assert "Вручную" in html

    excluded = client.post(
        f"/departments/settings/{department_id}/teacher/{teacher_id}/exclude",
    )
    removed = client.post(
        f"/departments/settings/{department_id}/activity/{link_id}/remove",
    )
    assert excluded.status_code == removed.status_code == 302
    with app.app_context():
        assert DepartmentTeacherMembership.query.filter_by(
            department_id=department_id, teacher_id=teacher_id,
        ).one().mode == "EXCLUDE"
        assert db.session.get(EducationActivityDepartment, link_id).is_active is False
        assert DepartmentSubject.query.filter_by(
            department_id=department_id, education_activity_id=activity_id,
        ).count() == 0
