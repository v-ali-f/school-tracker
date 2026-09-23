import pytest

from app.core.extensions import db
from app.models import Task


@pytest.mark.parametrize("path", ("/tasks/my", "/tasks/new"))
def test_task_pages_use_shared_workspace_shell(client, make_user, login, path):
    login(make_user("ADMIN"))

    response = client.get(path, follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert 'id="workspaceSidebar"' in html
    assert "workspace_ui.css" in html
    assert "tasks_workspace.css" in html
    assert "Поручения, сроки и совместная работа" in html


def test_task_card_uses_shared_workspace_shell(app, client, make_user, login):
    user_id = make_user("ADMIN")
    with app.app_context():
        task = Task(
            title="Проверочная задача",
            creator_user_id=user_id,
            responsible_user_id=user_id,
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    login(user_id)
    response = client.get(f"/tasks/{task_id}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert "tasks_workspace.css" in html
    assert "Задача №" in html
