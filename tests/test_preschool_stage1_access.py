from app.core.extensions import db
from app.models_legacy import AcademicYear
from app.modules.preschool.access import CHIEF_EDUCATOR, CONTINGENT_MANAGER
from app.modules.preschool.models import (
    PreschoolChild,
    PreschoolGroup,
    PreschoolResponsibility,
    PreschoolResponsibilityChange,
)


def _create_groups(app, educator_id):
    with app.app_context():
        own = PreschoolGroup(name="Солнечная группа", teacher_user_id=educator_id)
        other = PreschoolGroup(name="Лесная группа")
        db.session.add_all([own, other])
        db.session.flush()
        own_child = PreschoolChild(group_id=own.id, last_name="Иванов", first_name="Иван")
        other_child = PreschoolChild(group_id=other.id, last_name="Петров", first_name="Пётр")
        db.session.add_all([own_child, other_child])
        db.session.commit()
        return own_child.id, other_child.id


def test_preschool_denies_unauthorized_direct_urls(client, make_user, login):
    assert client.get("/preschool/").status_code in (302, 401)
    login(make_user("VIEWER"))
    for path in ("/preschool/", "/preschool/children", "/preschool/children/import", "/preschool/access"):
        assert client.get(path).status_code == 403


def test_educator_sees_only_assigned_group_and_cannot_change_contingent(app, client, make_user, login):
    educator_id = make_user("EDUCATOR")
    own_child_id, other_child_id = _create_groups(app, educator_id)
    login(educator_id)

    home = client.get("/preschool/")
    assert home.status_code == 200
    assert b"sp-workspace ws-workspace" in home.data
    assert "Детодни" not in home.get_data(as_text=True)

    own_group = client.get("/preschool/my-group")
    assert own_group.status_code == 200
    assert "Солнечная группа" in own_group.get_data(as_text=True)
    assert "Лесная группа" not in own_group.get_data(as_text=True)
    assert "Иванов Иван" in own_group.get_data(as_text=True)
    assert "Петров Пётр" not in own_group.get_data(as_text=True)

    own_card = client.get(f"/preschool/children/{own_child_id}")
    assert own_card.status_code == 200
    assert "Изменить" not in own_card.get_data(as_text=True)
    assert f"/preschool/children/{own_child_id}/movement" not in own_card.get_data(as_text=True)
    assert client.get(f"/preschool/children/{other_child_id}").status_code == 403
    for path in (
        "/preschool/children",
        "/preschool/children/registry",
        "/preschool/children/import",
        "/preschool/movements",
        f"/preschool/children/{own_child_id}/edit",
    ):
        assert client.get(path).status_code == 403
    assert client.post(f"/preschool/children/{own_child_id}/movement", data={}).status_code == 403
    assert client.get("/preschool/access").status_code == 403
    assert client.post("/preschool/access", data={"kind": CONTINGENT_MANAGER}).status_code == 403


def test_admin_assignment_grants_and_revokes_full_access_with_audit(app, client, make_user, login):
    admin_id = make_user("ADMIN")
    educator_id = make_user("EDUCATOR")
    login(admin_id)
    assert client.get("/preschool/access").status_code == 200

    response = client.post("/preschool/access", data={"kind": CONTINGENT_MANAGER, "user_id": educator_id})
    assert response.status_code == 302
    with app.app_context():
        assignment = PreschoolResponsibility.query.filter_by(kind=CONTINGENT_MANAGER).one()
        assert assignment.user_id == educator_id
        change = PreschoolResponsibilityChange.query.filter_by(kind=CONTINGENT_MANAGER).one()
        assert change.changed_by_user_id == admin_id
        assert change.new_user_id == educator_id

    login(educator_id)
    assert client.get("/preschool/children").status_code in (200, 302)
    assert client.get("/preschool/access").status_code == 403

    login(admin_id)
    assert client.post("/preschool/access", data={"kind": CONTINGENT_MANAGER, "user_id": ""}).status_code == 302
    login(educator_id)
    assert client.get("/preschool/children").status_code == 403
    with app.app_context():
        assert PreschoolResponsibilityChange.query.filter_by(kind=CONTINGENT_MANAGER).count() == 2


def test_chief_must_be_senior_and_senior_has_preschool_access(app, client, make_user, login):
    director_id = make_user("DIRECTOR")
    senior_id = make_user("SENIOR_EDUCATOR")
    educator_id = make_user("EDUCATOR")
    login(director_id)
    assert client.get("/preschool/access").status_code == 200

    assert client.post("/preschool/access", data={"kind": CHIEF_EDUCATOR, "user_id": educator_id}).status_code == 302
    with app.app_context():
        assert PreschoolResponsibility.query.filter_by(kind=CHIEF_EDUCATOR).count() == 0
    assert client.post("/preschool/access", data={"kind": CHIEF_EDUCATOR, "user_id": senior_id}).status_code == 302

    login(senior_id)
    assert client.get("/preschool/").status_code == 200
    assert client.get("/preschool/access").status_code == 403
    assert client.get("/preschool/children/registry").status_code in (200, 302)


def test_assistant_can_open_preschool_but_has_no_full_contingent_access(client, make_user, login):
    login(make_user("ASSISTANT_EDUCATOR"))
    assert client.get("/preschool/").status_code == 200
    assert client.get("/preschool/my-group").status_code == 200
    assert client.get("/preschool/children").status_code == 403


def test_deputy_sees_all_children_read_only(app, client, make_user, login):
    deputy_id = make_user("DEPUTY_DIRECTOR")
    with app.app_context():
        year = AcademicYear(name="2026/2027", is_current=True)
        db.session.add(year)
        db.session.flush()
        group = PreschoolGroup(name="Радуга", academic_year_id=year.id)
        db.session.add(group)
        db.session.flush()
        child = PreschoolChild(group_id=group.id, last_name="Сидоров", first_name="Сидор")
        db.session.add(child)
        db.session.commit()
        child_id = child.id

    login(deputy_id)
    registry = client.get("/preschool/children/registry")
    assert registry.status_code == 200
    assert b"sp-workspace ws-workspace" in registry.data
    assert "Сидоров" in registry.get_data(as_text=True)
    assert "Импорт детей" not in registry.get_data(as_text=True)
    assert client.get(f"/preschool/children/{child_id}").status_code == 200
    assert client.get(f"/preschool/children/{child_id}/edit").status_code == 403
    assert client.post("/preschool/children/registry", data={}).status_code == 403
    assert client.post(f"/preschool/children/{child_id}/movement", data={}).status_code == 403


def test_preschool_roles_have_plan_and_incident_views(app, client, make_user, login):
    with app.app_context():
        db.session.add(AcademicYear(name="2026/2027", is_current=True))
        db.session.commit()
    for role in ("EDUCATOR", "ASSISTANT_EDUCATOR"):
        login(make_user(role))
        assert client.get("/school-plan/").status_code == 200
        assert client.get("/incidents/my").status_code == 200
        assert client.get("/school-plan/new").status_code == 403
        assert client.get("/incidents/dashboard").status_code == 403

    login(make_user("SENIOR_EDUCATOR"))
    assert client.get("/school-plan/").status_code == 200
    assert client.get("/school-plan/new").status_code == 200
    assert client.get("/incidents/dashboard").status_code == 302
    assert client.get("/incidents/dashboard-legacy").status_code == 200


def test_senior_incident_dashboard_opens_before_first_academic_year(client, make_user, login):
    login(make_user("SENIOR_EDUCATOR"))
    assert client.get("/incidents/dashboard-legacy").status_code == 200
