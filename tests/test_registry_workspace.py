from datetime import date

import pytest

from app.core.extensions import db
from app.models import AcademicYear


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
    assert "Основные реестры" in html or "Контингент школы" in html
