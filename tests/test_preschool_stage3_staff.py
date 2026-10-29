from app.core.extensions import db
from app.models_legacy import AcademicYear, Building, User
from app.modules.preschool.models import (
    PreschoolBuildingStaff,
    PreschoolChild,
    PreschoolGroup,
    PreschoolGroupAssignment,
    PreschoolResponsibility,
    PreschoolStaffChange,
)


def _base(app):
    with app.app_context():
        year = AcademicYear(name="2026/2027", is_current=True)
        first = Building(name="Детский сад № 1", is_preschool=True)
        second = Building(name="Детский сад № 2", is_preschool=True)
        db.session.add_all([year, first, second])
        db.session.flush()
        group = PreschoolGroup(name="Ромашки", academic_year_id=year.id, building_id=first.id)
        other_group = PreschoolGroup(name="Звёзды", academic_year_id=year.id, building_id=second.id)
        db.session.add_all([group, other_group])
        db.session.flush()
        child = PreschoolChild(group_id=group.id, first_name="Иван", last_name="Иванов")
        other_child = PreschoolChild(group_id=other_group.id, first_name="Пётр", last_name="Петров")
        db.session.add_all([child, other_child])
        db.session.commit()
        return first.id, second.id, group.id, other_group.id, child.id, other_child.id


def _building_post(client, building_id, user_id, position, action="assign", **extra):
    return client.post(f"/preschool/staff/buildings/{building_id}", data={
        "user_id": user_id, "position": position, "action": action, **extra,
    })


def _group_post(client, group_id, user_id, position, action="assign", **extra):
    return client.post(f"/preschool/groups/{group_id}/staff", data={
        "user_id": user_id, "position": position, "action": action, **extra,
    })


def test_multiple_seniors_and_building_scope(app, client, make_user, login):
    first, second, group, other_group, _, _ = _base(app)
    admin = make_user("ADMIN")
    senior_a = make_user("SENIOR_EDUCATOR")
    senior_b = make_user("SENIOR_EDUCATOR")
    educator = make_user("EDUCATOR")
    psychologist = make_user("PSYCHOLOGIST")
    login(admin)
    assert _building_post(client, first, senior_a, "SENIOR_EDUCATOR").status_code == 302
    assert _building_post(client, first, senior_b, "SENIOR_EDUCATOR").status_code == 302
    assert _building_post(client, second, senior_b, "SENIOR_EDUCATOR").status_code == 302
    assert _building_post(client, first, psychologist, "PSYCHOLOGIST").status_code == 302
    assert _building_post(client, first, senior_a, "SENIOR_EDUCATOR").status_code == 409
    login(senior_a)
    page = client.get("/preschool/staff")
    assert page.status_code == 200
    assert "Детский сад № 1" in page.get_data(as_text=True)
    assert "Детский сад № 2" not in page.get_data(as_text=True)
    assert client.get(f"/preschool/groups/{group}/staff").status_code == 200
    assert client.get(f"/preschool/groups/{other_group}/staff").status_code == 403
    assert _building_post(client, first, educator, "EDUCATOR").status_code == 302
    assert _building_post(client, second, educator, "EDUCATOR").status_code == 403
    assert _building_post(client, first, psychologist, "EDUCATOR").status_code == 302
    with app.app_context():
        assert PreschoolBuildingStaff.query.filter_by(position="SENIOR_EDUCATOR", building_id=first).count() == 2


def test_multiple_group_staff_access_and_revocation(app, client, make_user, login):
    first, second, group, _, child, other_child = _base(app)
    admin = make_user("ADMIN")
    educators = [make_user("EDUCATOR"), make_user("EDUCATOR")]
    assistant = make_user("ASSISTANT_EDUCATOR")
    login(admin)
    for user_id in educators:
        assert _building_post(client, first, user_id, "EDUCATOR").status_code == 302
        assert _group_post(client, group, user_id, "EDUCATOR").status_code == 302
    assert _building_post(client, first, assistant, "ASSISTANT_EDUCATOR").status_code == 302
    assert _group_post(client, group, assistant, "ASSISTANT_EDUCATOR").status_code == 302
    assert _group_post(client, group, assistant, "ASSISTANT_EDUCATOR").status_code == 409
    with app.app_context():
        assert PreschoolGroupAssignment.query.filter_by(group_id=group, is_active=True).count() == 3
    for user_id in [*educators, assistant]:
        login(user_id)
        assert client.get(f"/preschool/children/{child}").status_code == 200
        assert client.get(f"/preschool/children/{other_child}").status_code == 403
        assert client.get("/preschool/children").status_code == 403
        assert client.post(f"/preschool/groups/{group}/staff", data={}).status_code == 403
    login(admin)
    assert _building_post(client, first, educators[0], "EDUCATOR", action="revoke").status_code == 302
    login(educators[0])
    assert client.get(f"/preschool/children/{child}").status_code == 403
    login(educators[1])
    assert client.get(f"/preschool/children/{child}").status_code == 200
    with app.app_context():
        assert PreschoolStaffChange.query.filter_by(scope="group", action="revoke", user_id=educators[0]).count() == 1


def test_group_assignment_adds_building_staff_without_dates(app, client, make_user, login):
    first, second, group, _, _, _ = _base(app)
    admin = make_user("ADMIN")
    educator = make_user("VIEWER")
    assistant = make_user("VIEWER")
    login(admin)
    assert _group_post(client, group, educator, "EDUCATOR", start_date="2026-10-01", end_date="2026-09-01").status_code == 302
    assert _group_post(client, group, assistant, "ASSISTANT_EDUCATOR").status_code == 302
    with app.app_context():
        membership = PreschoolBuildingStaff.query.filter_by(building_id=first, user_id=educator, position="EDUCATOR").one()
        assignment = PreschoolGroupAssignment.query.filter_by(group_id=group, user_id=educator, position="EDUCATOR").one()
        assert membership.start_date is None and membership.end_date is None
        assert assignment.start_date is None and assignment.end_date is None
        assert db.session.get(User, educator).has_role("EDUCATOR")
        assert PreschoolBuildingStaff.query.filter_by(building_id=second, user_id=educator).count() == 0


def test_unlinked_group_can_be_set_up_from_contingent_summary(app, client, make_user, login):
    first, second, group, _, _, _ = _base(app)
    admin = make_user("ADMIN")
    manager = make_user("VIEWER")
    educator = make_user("VIEWER")
    with app.app_context():
        db.session.get(PreschoolGroup, group).building_id = None
        db.session.get(User, educator).phone = "+7 999 123 45 67"
        db.session.add(PreschoolResponsibility(kind="CONTINGENT_MANAGER", user_id=manager, assigned_by_user_id=admin))
        db.session.commit()
    login(manager)
    summary = client.get("/preschool/children")
    assert summary.status_code == 200
    assert "Изменить" in summary.get_data(as_text=True)
    assert "Корпус и сотрудники" not in summary.get_data(as_text=True)
    assert client.post(f"/preschool/groups/{group}/staff", data={
        "action": "inline_save", "building_id": first, "user_id": educator, "position": "EDUCATOR",
    }).status_code == 302
    summary = client.get("/preschool/children").get_data(as_text=True)
    assert "+7 999 123 45 67" in summary
    assert "Воспитатель:" in summary
    assert _building_post(client, second, educator, "EDUCATOR").status_code == 403


def test_senior_and_director_can_assign_staff_in_summary_with_building_scope(app, client, make_user, login):
    first, second, group, other_group, _, _ = _base(app)
    admin = make_user("ADMIN")
    senior = make_user("VIEWER")
    director = make_user("DIRECTOR")
    educator = make_user("VIEWER")
    login(admin)
    assert _building_post(client, first, senior, "SENIOR_EDUCATOR").status_code == 302
    login(senior)
    assert client.post(f"/preschool/groups/{group}/staff", data={
        "action": "inline_save", "building_id": first, "user_id": educator, "position": "EDUCATOR",
    }).status_code == 302
    assert client.post(f"/preschool/groups/{other_group}/staff", data={
        "action": "inline_save", "building_id": second, "user_id": educator, "position": "EDUCATOR",
    }).status_code == 403
    login(director)
    assert client.post(f"/preschool/groups/{other_group}/staff", data={
        "action": "inline_save", "building_id": second, "user_id": educator, "position": "ASSISTANT_EDUCATOR",
    }).status_code == 302
    with app.app_context():
        assert PreschoolGroupAssignment.query.filter_by(group_id=group, user_id=educator, position="EDUCATOR", is_active=True).count() == 1
        assert PreschoolGroupAssignment.query.filter_by(group_id=other_group, user_id=educator, position="ASSISTANT_EDUCATOR", is_active=True).count() == 1


def test_legacy_teacher_migrates_once_and_stays_revoked(app, client, make_user, login):
    first, _, group_id, _, child, _ = _base(app)
    admin = make_user("ADMIN")
    educator = make_user("EDUCATOR")
    with app.app_context():
        group = db.session.get(PreschoolGroup, group_id)
        group.teacher_user_id = educator
        db.session.commit()
    login(educator)
    assert client.get(f"/preschool/children/{child}").status_code == 200
    with app.app_context():
        assert PreschoolGroupAssignment.query.filter_by(group_id=group_id, user_id=educator).count() == 1
        assert PreschoolBuildingStaff.query.filter_by(building_id=first, user_id=educator).count() == 1
    login(admin)
    assert _group_post(client, group_id, educator, "EDUCATOR", action="revoke").status_code == 302
    with app.app_context():
        app.config.pop("_PRESCHOOL_LEGACY_STAFF_MIGRATED", None)
    login(educator)
    assert client.get(f"/preschool/children/{child}").status_code == 403
    with app.app_context():
        rows = PreschoolGroupAssignment.query.filter_by(group_id=group_id, user_id=educator).all()
        assert len(rows) == 1 and rows[0].is_active is False


def test_deputy_sees_staff_without_editing(app, client, make_user, login):
    first, _, group, _, _, _ = _base(app)
    deputy = make_user("DEPUTY_DIRECTOR")
    educator = make_user("EDUCATOR")
    login(deputy)
    assert client.get("/preschool/staff").status_code == 200
    assert client.get(f"/preschool/groups/{group}/staff").status_code == 200
    assert _building_post(client, first, educator, "EDUCATOR").status_code == 403
    assert _group_post(client, group, educator, "EDUCATOR").status_code == 403


def test_only_preschool_buildings_appear_and_admin_can_change_type(app, client, make_user, login):
    first, _, _, _, _, _ = _base(app)
    admin = make_user("ADMIN")
    employee = make_user("VIEWER")
    with app.app_context():
        school = Building(name="Школьный корпус")
        db.session.add(school)
        db.session.commit()
        school_id = school.id
    login(admin)
    page = client.get("/preschool/staff").get_data(as_text=True)
    assert "Детский сад № 1" in page
    assert "Школьный корпус" not in page
    assert 'name="start_date"' not in page and 'name="end_date"' not in page
    assert _building_post(client, school_id, employee, "EDUCATOR").status_code == 403
    assert client.post(f"/buildings/{school_id}/update", data={
        "name": "Школьный корпус", "is_preschool": "1", "matrix_tone": "0",
    }).status_code == 302
    assert "Школьный корпус" not in client.get("/preschool/staff").get_data(as_text=True)
    with app.app_context():
        group = PreschoolGroup.query.filter_by(building_id=first).first()
        group.building_id = school_id
        db.session.commit()
    assert "Школьный корпус" in client.get("/preschool/staff").get_data(as_text=True)
    assert client.post(f"/buildings/{school_id}/update", data={
        "name": "Школьный корпус", "matrix_tone": "0",
    }).status_code == 302
    assert "Школьный корпус" not in client.get("/preschool/staff").get_data(as_text=True)


def test_building_assignment_grants_and_releases_employee_role(app, client, make_user, login):
    first, _, _, _, _, _ = _base(app)
    admin = make_user("ADMIN")
    employee = make_user("VIEWER")
    login(admin)
    assert _building_post(client, first, employee, "EDUCATOR").status_code == 302
    with app.app_context():
        assert db.session.get(User, employee).has_role("EDUCATOR")
    assert _building_post(client, first, employee, "EDUCATOR", action="revoke").status_code == 302
    with app.app_context():
        assert not db.session.get(User, employee).has_role("EDUCATOR")


def test_employee_search_suggests_after_first_letter(app, client, make_user, login):
    _base(app)
    admin = make_user("ADMIN")
    employee = make_user("VIEWER")
    login(admin)
    response = client.get("/preschool/staff/search?q=Т")
    assert response.status_code == 200
    assert employee in {person["id"] for person in response.json}
