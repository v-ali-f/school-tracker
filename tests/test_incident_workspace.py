from datetime import date, datetime
import re

import pytest

from app.core.extensions import db
from app.models import AcademicYear, Incident, Role, UserRole


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
    assert "incidents_workspace.css" in html
    if path == "/incidents/my":
        assert "incidents_my.css" in html
    assert 'class="incident-section-tabs"' in html
    assert "Добавить инцидент" in html


def test_incident_card_and_timeline_use_shared_workspace(app, client, make_user, login):
    admin_id = make_user("ADMIN")
    with app.app_context():
        incident = Incident(
            occurred_at=datetime(2026, 9, 23, 10, 30),
            category="Конфликт",
            description="Проверочная запись",
            author_id=admin_id,
        )
        db.session.add(incident)
        db.session.commit()
        incident_id = incident.id

    login(admin_id)
    for path in (f"/incidents/{incident_id}/edit", f"/incidents/{incident_id}/timeline"):
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'class="sp-workspace ws-workspace"' in html
        assert "incidents_workspace.css" in html
        assert 'class="incident-section-tabs"' in html


def test_incident_assignment_pages_share_legacy_and_normalized_candidates(
    app,
    client,
    make_user,
    login,
    current_year,
):
    admin_id = make_user("ADMIN")
    legacy_teacher_id = make_user("TEACHER")
    normalized_teacher_id = make_user("VIEWER")

    with app.app_context():
        teacher_role = Role(code="CLASS_TEACHER", name="Классный руководитель")
        db.session.add(teacher_role)
        db.session.flush()
        db.session.add(
            UserRole(user_id=normalized_teacher_id, role_id=teacher_role.id)
        )
        incident = Incident(
            occurred_at=datetime(2026, 9, 23, 10, 30),
            category="Конфликт",
            description="Проверка общего списка исполнителей",
            author_id=admin_id,
        )
        db.session.add(incident)
        db.session.commit()
        incident_id = incident.id

    login(admin_id)
    for path in (f"/incidents/{incident_id}/edit", "/incidents/my"):
        response = client.get(path)
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert re.search(
            rf'name="assignee_ids"[^>]*value="{legacy_teacher_id}"', html
        )
        assert re.search(
            rf'name="assignee_ids"[^>]*value="{normalized_teacher_id}"', html
        )
        assert "incident_assignee_picker.js" in html
        assert "data-assignee-menu" in html
