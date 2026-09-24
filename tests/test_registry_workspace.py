from datetime import date

import pytest

from app.core.extensions import db
from app.models import AcademicYear, Child, ChildEnrollment, SchoolClass


@pytest.fixture()
def current_year(app):
    with app.app_context():
        year = AcademicYear(
            name="2026/2027",
            is_current=True,
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
        )
        db.session.add(year)
        db.session.commit()
        return year.id


@pytest.mark.parametrize(
    "path",
    (
        "/hub/registries",
        "/children",
        "/contingent",
        "/registry/vshu",
        "/registry/ovz",
        "/registry/az",
        "/registry/enrolled",
        "/registry/expelled",
        "/registry/kdn",
        "/classes",
        "/comments/registry",
    ),
)
def test_registry_pages_use_shared_workspace_shell(
    client,
    make_user,
    login,
    current_year,
    path,
):
    login(make_user("ADMIN"))

    response = client.get(path, follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert 'id="workspaceSidebar"' in html
    assert "workspace_ui.css" in html
    if path == "/hub/registries":
        assert "hub_workspace.css" in html
    else:
        assert "registries_workspace.css" in html
    assert (
        "Основные реестры" in html
        or "Контингент школы" in html
    )


@pytest.mark.parametrize(
    "path",
    (
        "/children/new",
        "/children/import",
        "/children/import-parents",
        "/classrooms",
        "/transfers/",
        "/transfers/class",
        "/transfers/parallel",
        "/transfers/individual",
        "/transfers/archive",
    ),
)
def test_student_workflows_use_compact_workspace_navigation(
    client,
    make_user,
    login,
    current_year,
    path,
):
    login(make_user("ADMIN"))

    response = client.get(path, follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert "children_workspace.css" in html
    assert "Ученики" in html
    assert "Классы" in html
    assert "Контингент" in html
    assert "Переводы и выбытие" in html
    assert "Кабинеты" in html


def test_child_and_class_cards_keep_student_workspace_context(
    app,
    client,
    make_user,
    login,
    current_year,
):
    with app.app_context():
        school_class = SchoolClass(
            academic_year_id=current_year,
            name="5А",
            grade=5,
            letter="А",
        )
        child = Child(last_name="Иванов", first_name="Иван")
        db.session.add_all([school_class, child])
        db.session.flush()
        db.session.add(
            ChildEnrollment(
                child_id=child.id,
                academic_year_id=current_year,
                school_class_id=school_class.id,
                status="ACTIVE",
            )
        )
        db.session.commit()
        child_id = child.id
        class_id = school_class.id

    login(make_user("ADMIN"))

    for path in (f"/children/{child_id}", f"/classes/{class_id}"):
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'class="sp-workspace ws-workspace"' in html
        assert "children_workspace.css" in html
        assert "Иванов Иван" in html


@pytest.mark.parametrize(
    "path",
    (
        "/service-staff/",
        "/service-staff/specialists",
        "/service-staff/specialists/new",
        "/service-staff/structure",
        "/service-staff/buildings",
        "/service-staff/responsibles",
        "/service-staff/assignments",
        "/service-staff/assignments/new",
        "/service-staff/children-summary",
        "/service-staff/buildings-children",
        "/service-staff/cyclegrams",
        "/service-staff/cyclegrams/new",
        "/service-staff/presentations",
        "/service-staff/presentations/new",
        "/service-staff/norms",
        "/service-staff/norms/new",
        "/service-staff/analytics",
        "/service-staff/analytics/specialists",
        "/service-staff/analytics/buildings",
        "/service-staff/analytics/data-quality",
    ),
)
def test_service_staff_pages_use_shared_workspace_shell(
    client,
    make_user,
    login,
    current_year,
    path,
):
    login(make_user("ADMIN"))

    response = client.get(path, follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert "service_staff_workspace.css" in html
    assert "Служба сопровождения" in html
    assert "Специалисты" in html
    assert "Сопровождение" in html
    assert "Аналитика" in html
