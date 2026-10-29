from app.core.extensions import db
from app.models_legacy import AcademicYear, Building
from app.modules.preschool.models import (
    PreschoolBuildingStaff,
    PreschoolChild,
    PreschoolGroup,
    PreschoolGroupAssignment,
    PreschoolStaffChange,
)


def _base(app):
    with app.app_context():
        year = AcademicYear(name="2026/2027", is_current=True)
        first = Building(name="Детский сад № 1")
        second = Building(name="Детский сад № 2")
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
    assert _building_post(client, first, psychologist, "EDUCATOR").status_code == 400
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


def test_group_assignment_requires_matching_building_role_and_period(app, client, make_user, login):
    first, second, group, _, _, _ = _base(app)
    admin = make_user("ADMIN")
    educator = make_user("EDUCATOR")
    assistant = make_user("ASSISTANT_EDUCATOR")
    login(admin)
    assert _group_post(client, group, educator, "EDUCATOR").status_code == 400
    assert _building_post(client, second, educator, "EDUCATOR").status_code == 302
    assert _group_post(client, group, educator, "EDUCATOR").status_code == 400
    assert _building_post(client, first, educator, "EDUCATOR", start_date="2026-01-01", end_date="2027-12-31").status_code == 302
    assert _group_post(client, group, educator, "EDUCATOR", start_date="2025-12-31", end_date="2027-01-01").status_code == 400
    assert _group_post(client, group, educator, "EDUCATOR", start_date="2026-10-01", end_date="2026-09-01").status_code == 400
    assert _group_post(client, group, educator, "EDUCATOR", start_date="2026-10-01", end_date="2027-01-01").status_code == 302
    assert _group_post(client, group, assistant, "EDUCATOR").status_code == 400


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
