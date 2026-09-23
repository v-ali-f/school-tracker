from app.core.extensions import db
from app.models import ControlWork, Subject


def _assert_workspace(response):
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert 'id="workspaceSidebar"' in html
    assert "workspace_ui.css" in html
    assert "control_works_workspace.css" in html
    assert "Планирование, заполнение и анализ результатов" in html


def test_control_work_list_and_form_use_workspace(client, make_user, login):
    login(make_user("ADMIN"))

    _assert_workspace(client.get("/control-works/", follow_redirects=True))
    _assert_workspace(client.get("/control-works/new", follow_redirects=True))
    _assert_workspace(client.get("/control-works/journal", follow_redirects=True))


def test_control_work_detail_uses_workspace(app, client, make_user, login):
    user_id = make_user("ADMIN")
    with app.app_context():
        subject = Subject(name="Математика")
        db.session.add(subject)
        db.session.flush()
        work = ControlWork(
            subject_id=subject.id,
            theme="Проверочная работа",
            created_by=user_id,
        )
        db.session.add(work)
        db.session.commit()
        work_id = work.id

    login(user_id)
    _assert_workspace(client.get(f"/control-works/{work_id}"))
