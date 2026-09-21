from datetime import date

from app.core.extensions import db
from app.models import SchoolPlanDirection, SchoolPlanEvent


def _event_form_data(direction_id, title):
    return {
        "title": title,
        "date_mode": "single",
        "start_date": date.today().isoformat(),
        "direction_id": str(direction_id),
        "responsible_groups": "role:TEACHER",
        "audience_scope": "school",
        "return_period": date.today().strftime("%Y-%m"),
    }


def test_editor_can_save_event_twice_with_same_responsible_group(
    app, client, make_user, login
):
    admin_id = make_user(role="ADMIN")
    login(admin_id)

    with app.app_context():
        direction = SchoolPlanDirection(
            name="Тестовое направление",
            code="test-editing",
            is_active=True,
        )
        db.session.add(direction)
        db.session.commit()
        direction_id = direction.id

    create_response = client.post(
        "/school-plan/new",
        data=_event_form_data(direction_id, "Первоначальное название"),
    )
    assert create_response.status_code == 302

    with app.app_context():
        event = SchoolPlanEvent.query.one()
        event_id = event.id
        assert [link.form_value for link in event.group_links] == ["role:TEACHER"]

    edit_response = client.post(
        f"/school-plan/{event_id}/edit",
        data=_event_form_data(direction_id, "Обновлённое название"),
    )
    assert edit_response.status_code == 302

    with app.app_context():
        event = db.session.get(SchoolPlanEvent, event_id)
        assert event.title == "Обновлённое название"
        assert [link.form_value for link in event.group_links] == ["role:TEACHER"]
