import pytest
from werkzeug.exceptions import NotFound

from app.core.extensions import db
from app.models import (
    Building,
    Department,
    DepartmentLeader,
    RoleModuleAccess,
    User,
    UserBuilding,
)
from app.modules.workload.access import require_workload_write
from app.modules.workload.scopes import resolve_workload_scope


def _enable_module(app):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True


def test_module_is_hidden_when_feature_flag_is_off(app, client, make_user, login):
    login(make_user("ADMIN"))

    response = client.get("/workload/")

    assert response.status_code == 404


def test_anonymous_user_is_redirected_to_login_when_enabled(app, client):
    _enable_module(app)

    response = client.get("/workload/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_user_without_workload_permission_is_forbidden(app, client, make_user, login):
    _enable_module(app)
    login(make_user("VIEWER"))

    response = client.get("/workload/")

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR", "TEACHER"])
def test_allowed_roles_can_open_scaffold(app, client, make_user, login, role):
    _enable_module(app)
    login(make_user(role))

    response = client.get("/workload/")

    assert response.status_code == 200
    assert "Нагрузка и тарификация".encode() in response.data


def test_explicit_module_deny_overrides_default_role_access(
    app, client, make_user, login
):
    _enable_module(app)
    user_id = make_user("ADMIN")
    with app.app_context():
        db.session.add(RoleModuleAccess(
            role_code="ADMIN",
            module_code="workload",
            is_visible=False,
            is_enabled=False,
            access_level="hidden",
            is_active=True,
        ))
        db.session.commit()
    login(user_id)

    response = client.get("/workload/")

    assert response.status_code == 403


def test_dashboard_hides_workload_card_when_feature_is_off(
    app, client, make_user, login
):
    login(make_user("ADMIN"))

    response = client.get("/")

    assert response.status_code == 200
    assert "Нагрузка и тарификация".encode() not in response.data


def test_dashboard_shows_workload_card_for_allowed_role_when_enabled(
    app, client, make_user, login
):
    _enable_module(app)
    login(make_user("ADMIN"))

    response = client.get("/")

    assert response.status_code == 200
    assert "Нагрузка и тарификация".encode() in response.data


def test_write_gate_stays_closed_until_its_flag_is_enabled(app):
    _enable_module(app)

    with app.test_request_context("/workload/example"):
        with pytest.raises(NotFound):
            require_workload_write()

        app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
        require_workload_write()


def test_administrator_has_unrestricted_scope(app, make_user):
    user_id = make_user("ADMIN")

    with app.app_context():
        user = db.session.get(User, user_id)
        scope = resolve_workload_scope(user)

    assert scope.unrestricted is True
    assert scope.is_empty is False


def test_department_head_scope_is_limited_to_assigned_department(
    app, make_user
):
    user_id = make_user("DEPARTMENT_HEAD")
    with app.app_context():
        building = Building(name="Тестовый корпус", short_name="ТК")
        department = Department(name="Тестовая кафедра")
        db.session.add_all([building, department])
        db.session.flush()
        db.session.add(DepartmentLeader(
            user_id=user_id,
            department_id=department.id,
            building_id=building.id,
        ))
        db.session.commit()
        user = db.session.get(User, user_id)
        scope = resolve_workload_scope(user)

        assert scope.unrestricted is False
        assert scope.department_ids == frozenset({department.id})
        assert scope.building_ids == frozenset({building.id})


def test_teacher_scope_is_self_only_and_keeps_building_boundary(app, make_user):
    user_id = make_user("TEACHER")
    with app.app_context():
        building = Building(name="Учительский корпус", short_name="УК")
        db.session.add(building)
        db.session.flush()
        db.session.add(UserBuilding(
            user_id=user_id,
            building_id=building.id,
            is_primary=True,
        ))
        db.session.commit()
        user = db.session.get(User, user_id)
        scope = resolve_workload_scope(user)

        assert scope.own_employee_only is True
        assert scope.building_ids == frozenset({building.id})
        assert scope.unrestricted is False


def test_registered_workload_business_tables_match_completed_stages():
    workload_tables = {
        table_name
        for table_name in db.metadata.tables
        if table_name.startswith(("workload_", "tariffication_", "curriculum_"))
    }

    assert workload_tables == {
        "workload_assignment",
        "workload_assignment_change",
        "workload_need",
        "workload_need_source",
        "workload_reconciliation_item",
        "workload_reconciliation_run",
        "workload_source_setting",
        "workload_source_transition",
    }
