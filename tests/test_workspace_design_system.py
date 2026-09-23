from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_design_system_preview_is_available_to_admin(client, make_user, login):
    login(make_user("ADMIN"))

    response = client.get("/design-system/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Единая дизайн-система" in html
    assert "workspace_ui.css" in html
    assert "ws-metric-grid" in html
    assert "ws-status is-success" in html
    assert "ws-empty" in html


def test_design_system_preview_is_hidden_from_regular_users(client, make_user, login):
    login(make_user("TEACHER"))

    assert client.get("/design-system/").status_code == 403


def test_shared_workspace_styles_do_not_import_feature_module():
    entrypoint = (PROJECT_ROOT / "app/static/css/workspace_ui.css").read_text()
    school_plan = (PROJECT_ROOT / "app/static/css/school_plan_workspace.css").read_text()

    assert "workspace_tokens.css" in entrypoint
    assert "workspace_shell.css" in entrypoint
    assert "workspace_components.css" in entrypoint
    assert "school_plan_workspace.css" not in entrypoint
    assert "sp-sidebar" not in school_plan
    assert "school-plan-modern-shell" not in school_plan


def test_workspace_component_macros_are_present():
    macros = (PROJECT_ROOT / "app/templates/components/workspace_ui.html").read_text()

    for macro_name in ("page_header", "status_badge", "metric", "empty_state", "filter_panel", "card"):
        assert f"macro {macro_name}" in macros
