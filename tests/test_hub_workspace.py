import pytest


THEME_HUBS = (
    ("/hub/management", "Управленческий контур"),
    ("/hub/academic", "Академический контур"),
    ("/hub/contingent", "Контингент"),
    ("/hub/incidents", "Инциденты"),
    ("/hub/departments", "Кафедры"),
    ("/hub/diagnostics", "Диагностики"),
    ("/hub/attendance", "Посещаемость"),
    ("/hub/registries", "Основные реестры"),
    ("/hub/control-works", "Контрольные работы"),
    ("/hub/olympiads", "Олимпиады"),
    ("/hub/orders", "Реестр приказов"),
    ("/hub/classroom", "Классное руководство"),
    ("/hub/admin", "Для администратора"),
)


@pytest.mark.parametrize(("path", "title"), THEME_HUBS)
def test_all_theme_hubs_use_shared_workspace(
    client,
    make_user,
    login,
    path,
    title,
):
    login(make_user("ADMIN"))

    response = client.get(path)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert title in html
    assert 'class="sp-workspace ws-workspace"' in html
    assert 'id="workspaceSidebar"' in html
    assert "workspace_ui.css" in html
    assert "hub_workspace.css" in html
    assert "hub-workspace-page" in html
    assert "hub-workspace-card" in html
    assert "theme-hub-classic" not in html


def test_theme_hub_keeps_role_access_rules(client, make_user, login):
    login(make_user("TEACHER"))

    assert client.get("/hub/departments").status_code == 403
    assert client.get("/hub/admin").status_code == 403
