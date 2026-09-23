from datetime import date, time

from app.core.extensions import db
from app.models import SchoolPlanDirection, SchoolPlanEvent


def test_all_school_plan_views_use_shared_workspace(client, make_user, login):
    login(make_user(role="ADMIN"))

    for path in (
        "/school-plan/",
        "/school-plan/week",
        "/school-plan/month",
        "/school-plan/day",
        "/school-plan/weeks",
        "/school-plan/new",
        "/school-plan/editors",
        "/school-plan/legend",
    ):
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'class="sp-workspace ws-workspace"' in html
        assert "workspace_ui.css" in html
        assert "school_plan_workspace.css" in html
        assert "План работы школы" in html


def _event_form_data(direction_id, title, start_time=""):
    data = {
        "title": title,
        "date_mode": "single",
        "start_date": date.today().isoformat(),
        "start_time": start_time,
        "direction_id": str(direction_id),
        "responsible_groups": "role:TEACHER",
        "audience_scope": "school",
        "return_period": date.today().strftime("%Y-%m"),
    }
    return data


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

    form_response = client.get("/school-plan/new")
    assert form_response.status_code == 200
    form_html = form_response.get_data(as_text=True)
    assert "Школьный спортивный клуб" in form_html
    assert 'class="sp-workspace ws-workspace"' in form_html
    assert 'class="card soft-card sp-plan-form-card"' in form_html
    assert "Добавить инцидент" in form_html

    editors_response = client.get("/school-plan/editors")
    assert editors_response.status_code == 200
    editors_html = editors_response.get_data(as_text=True)
    assert 'class="sp-workspace ws-workspace"' in editors_html
    assert 'class="school-plan-editors-page"' in editors_html
    assert "Разделы и сервисы" in editors_html

    with app.app_context():
        event = SchoolPlanEvent.query.one()
        event_id = event.id
        assert [link.form_value for link in event.group_links] == ["role:TEACHER"]

    index_response = client.get(
        f"/school-plan/?period={date.today().strftime('%Y-%m')}"
    )
    assert index_response.status_code == 200
    index_html = index_response.get_data(as_text=True)
    assert 'aria-label="Изменить мероприятие"' in index_html
    assert 'aria-label="Отменить мероприятие"' in index_html
    assert ">Изменить</a>" not in index_html
    assert ">Отменить</button>" not in index_html

    edit_response = client.post(
        f"/school-plan/{event_id}/edit",
        data=_event_form_data(direction_id, "Обновлённое название"),
    )
    assert edit_response.status_code == 302

    with app.app_context():
        event = db.session.get(SchoolPlanEvent, event_id)
        assert event.title == "Обновлённое название"
        assert event.start_time is None
        assert [link.form_value for link in event.group_links] == ["role:TEACHER"]


def test_event_start_time_is_saved_updated_and_shown(
    app, client, make_user, login
):
    admin_id = make_user(role="ADMIN")
    login(admin_id)

    with app.app_context():
        direction = SchoolPlanDirection(
            name="Мероприятия по времени",
            code="test-start-time",
            is_active=True,
        )
        db.session.add(direction)
        db.session.commit()
        direction_id = direction.id

    response = client.post(
        "/school-plan/new",
        data=_event_form_data(direction_id, "Совещание", "09:30"),
    )
    assert response.status_code == 302

    with app.app_context():
        event = SchoolPlanEvent.query.one()
        event_id = event.id
        assert event.start_time == time(9, 30)
        assert event.display_time == "09:30"
        assert event.display_schedule.endswith("· 09:30")

    index_response = client.get(
        f"/school-plan/?period={date.today().strftime('%Y-%m')}"
    )
    assert index_response.status_code == 200
    assert "09:30" in index_response.get_data(as_text=True)

    view_response = client.get(f"/school-plan/{event_id}")
    assert view_response.status_code == 200
    view_html = view_response.get_data(as_text=True)
    assert 'class="sp-workspace ws-workspace"' in view_html
    assert 'class="sp-event-detail"' in view_html
    assert "Добавить инцидент" in view_html
    assert "Разделы и сервисы" in view_html
    assert 'class="sp-detail-value">09:30</div>' in view_html
    assert 'class="fw-semibold">09:30</div>' not in view_html

    edit_response = client.post(
        f"/school-plan/{event_id}/edit",
        data=_event_form_data(direction_id, "Совещание", "10:15"),
    )
    assert edit_response.status_code == 302

    with app.app_context():
        event = db.session.get(SchoolPlanEvent, event_id)
        assert event.start_time == time(10, 15)
