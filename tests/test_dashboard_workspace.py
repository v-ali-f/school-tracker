import re
from datetime import date, timedelta

import pytest

from app.core.extensions import db
from app.models import SchoolPlanEvent


EMPLOYEE_ROLES = (
    "ADMIN",
    "DIRECTOR",
    "DEPUTY_DIRECTOR",
    "METHODIST",
    "DEPARTMENT_HEAD",
    "CLASS_TEACHER",
    "CURATOR",
    "TEACHER",
    "VIEWER",
    "KPP",
    "OLIGOPHRENOPEDAGOG",
    "SOCIAL_PEDAGOG",
    "LOGOPEDIST",
    "PSYCHOLOGIST",
    "DEFECTOLOGIST",
    "TUTOR",
    "ASSISTANT",
    "SENIOR_EDUCATOR",
    "EDUCATOR",
    "HR_SPECIALIST",
    "ECONOMIST",
    "AUDITOR",
    "SECRETARY",
    "SECRETARY_ACADEMIC",
    "PEDAGOG_ORGANIZER",
    "SPECIALIST",
    "SUPPORT",
)


@pytest.mark.parametrize("role", EMPLOYEE_ROLES)
def test_every_employee_dashboard_has_add_incident_action(
    client,
    make_user,
    login,
    role,
):
    login(make_user(role))

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/incidents/new"'.encode() in response.data


@pytest.mark.parametrize("role", [role for role in EMPLOYEE_ROLES if role != "KPP"])
def test_add_incident_is_the_first_dashboard_quick_action(
    client,
    make_user,
    login,
    role,
):
    login(make_user(role))

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "dh-workspace" in html
    assert re.search(
        r'<div class="dh-quick-list">\s*<a[^>]+href="/incidents/new"',
        html,
    )


def test_dashboard_shows_full_period_and_ongoing_state(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    login(admin_id)
    today = date.today()

    with app.app_context():
        db.session.add(
            SchoolPlanEvent(
                title="Длительное мероприятие",
                start_date=today - timedelta(days=10),
                end_date=today + timedelta(days=5),
                period_type="range",
                created_by_user_id=admin_id,
            )
        )
        db.session.commit()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Длительное мероприятие" in html
    assert (today - timedelta(days=10)).strftime("%d.%m.%Y") in html
    assert (today + timedelta(days=5)).strftime("%d.%m.%Y") in html
    assert ">Сейчас</em>" in html
    assert "bi-calendar-range" in html
