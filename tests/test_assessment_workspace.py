from pathlib import Path

from app.core.extensions import db
from app.models import DiagnosticSession


def _assert_assessment_workspace(response, context_title):
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert 'id="workspaceSidebar"' in html
    assert "workspace_ui.css" in html
    assert "assessment_workspace.css" in html
    assert context_title in html
    assert 'class="assessment-tabs"' in html


def test_olympiad_pages_use_workspace(client, make_user, login):
    login(make_user("ADMIN"))

    registry_response = client.get("/olympiads/")
    _assert_assessment_workspace(registry_response, "Олимпиады")
    assert "/olympiads/teacher-binding" in registry_response.get_data(as_text=True)

    for path in [
        "/olympiads/analytics",
        "/olympiads/import",
        "/olympiads/imports",
        "/olympiads/department",
        "/olympiads/teacher-binding",
        "/olympiads/unmatched",
        "/olympiads/settings",
        "/olympiads/my",
    ]:
        _assert_assessment_workspace(client.get(path), "Олимпиады")


def test_diagnostic_pages_use_workspace(client, make_user, login):
    user_id = make_user("ADMIN")
    login(user_id)

    for path in [
        "/diagnostics/",
        "/diagnostics/new",
        "/diagnostics/analytics",
        "/diagnostics/departments",
        "/diagnostics/binding",
        "/diagnostics/imports",
    ]:
        _assert_assessment_workspace(client.get(path), "Диагностики")


def test_diagnostic_card_edit_and_import_use_workspace(app, client, make_user, login):
    user_id = make_user("ADMIN")
    with app.app_context():
        session = DiagnosticSession(title="Проверочная диагностика", diagnostic_type="MCKO", created_by=user_id)
        db.session.add(session)
        db.session.commit()
        session_id = session.id

    login(user_id)
    for path in [
        f"/diagnostics/{session_id}",
        f"/diagnostics/{session_id}/edit",
        f"/diagnostics/{session_id}/import",
    ]:
        _assert_assessment_workspace(client.get(path), "Диагностики")


def test_all_assessment_page_templates_use_workspace_bases():
    templates_dir = Path(__file__).parents[1] / "app" / "templates"

    olympiad_templates = list(templates_dir.glob("olympiad_*.html"))
    olympiad_templates.remove(templates_dir / "olympiad_workspace.html")
    diagnostic_templates = list((templates_dir / "diagnostics").glob("diagnostics_*.html"))
    diagnostic_templates.remove(templates_dir / "diagnostics" / "diagnostics_workspace.html")

    assert len(olympiad_templates) == 10
    assert len(diagnostic_templates) == 10
    for template in olympiad_templates:
        assert '{% extends "olympiad_workspace.html" %}' in template.read_text(encoding="utf-8"), template.name
    for template in diagnostic_templates:
        assert '{% extends "diagnostics/diagnostics_workspace.html" %}' in template.read_text(encoding="utf-8"), template.name
