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
        "/incidents/new",
        "/incidents/my",
        "/incidents/registry",
        "/incidents/dashboard",
    ),
)
def test_incident_pages_use_shared_workspace_shell(
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
    assert "Добавить инцидент" in html
