from datetime import date

import pytest

from app.core.extensions import db
from app.models import AcademicYear, SchoolPlanDirection, SchoolPlanEvent
from scripts.import_vsoko_2026_2027 import import_plan, load_plan


def test_vsoko_import_is_editable_and_keeps_user_changes(app, client, make_user, login):
    login(make_user(role="ADMIN"))
    plan = load_plan()
    assert len(plan["items"]) == 37

    with app.app_context():
        db.session.add(AcademicYear(name="2026/2027", is_current=True))
        db.session.commit()
        assert import_plan(plan) == 37
        direction = SchoolPlanDirection.query.filter_by(code="vsoko").one()
        direction_id = direction.id
        events = SchoolPlanEvent.query.filter_by(direction_id=direction_id).all()
        assert len(events) == 37
        assert sum(event.period_type == "day" for event in events) == 2
        first = next(event for event in events if "Пункт исходного плана: №1" in event.description)
        assert first.start_date == date(2026, 8, 1)
        assert first.end_date == date(2026, 8, 31)
        assert "Ожидаемый результат:" in first.description
        assert first.responsible_text == plan["items"][0]["responsible"]
        first_id = first.id

    index = client.get(f"/school-plan/?period=2026-08&direction_id={direction_id}")
    assert index.status_code == 200
    html = index.get_data(as_text=True)
    assert "ВСОКО" in html
    assert "Готовность зданий" in html
    assert f"period=2026-09&amp;direction_id={direction_id}" in html

    edit = client.get(f"/school-plan/{first_id}/edit")
    assert edit.status_code == 200
    assert "Готовность зданий" in edit.get_data(as_text=True)

    response = client.post(f"/school-plan/{first_id}/edit", data={
        "title": "Обновлённый пункт ВСОКО",
        "date_mode": "period",
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
        "direction_id": str(direction_id),
        "responsible_other": "Заместители директора",
        "audience_scope": "school",
        "description": "Дополненное содержание проверки",
        "return_period": "2026-08",
    })
    assert response.status_code == 302

    added = client.post("/school-plan/new", data={
        "title": "Дополнительное мероприятие ВСОКО",
        "date_mode": "single",
        "start_date": "2026-09-15",
        "direction_id": str(direction_id),
        "audience_scope": "school",
        "return_period": "2026-09",
    })
    assert added.status_code == 302

    with app.app_context():
        assert SchoolPlanEvent.query.filter_by(direction_id=direction_id).count() == 38
        assert db.session.get(SchoolPlanEvent, first_id).title == "Обновлённый пункт ВСОКО"
        with pytest.raises(ValueError, match="Повторная загрузка остановлена"):
            import_plan(plan)
        assert db.session.get(SchoolPlanEvent, first_id).description == "Дополненное содержание проверки"
