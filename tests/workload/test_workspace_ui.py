def test_workload_pages_use_shared_workspace_shell(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    login(make_user("ADMIN"))

    response = client.get("/workload/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/workload/plans/")
    response = client.get(response.headers["Location"])
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-workload-workspace' in html
    assert 'data-active-mode="hours"' in html
    assert "Учебное планирование и нагрузка" in html
    assert "Учебные планы" in html
    assert "Привязка УП" in html
    assert "Свод по классам" in html
    assert "Структура" not in html
    assert "Контекст" not in html
    assert "data-workload-panel-toggle" not in html
    assert "Группы" in html
    assert "Метагруппы" in html
    assert "Нагрузка" in html
    assert "Контроль" not in html
    assert "Печать и экспорт" not in html
    assert "workload_workspace.css" in html
    assert "workload_workspace.js" not in html


def test_metagroup_filter_selects_metagroup_workspace_mode(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    login(make_user("ADMIN"))

    response = client.get("/workload/groups/?group_type=METAGROUP")

    assert response.status_code == 200
    assert 'data-active-mode="metagroups"' in response.get_data(
        as_text=True
    )
