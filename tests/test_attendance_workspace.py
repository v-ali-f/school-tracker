from pathlib import Path


ATTENDANCE_PAGES = (
    "/attendance/passes",
    "/attendance/passes/new",
    "/attendance/import",
    "/attendance/imports",
    "/attendance/analytics",
    "/attendance/schedule",
    "/attendance/kpp",
)


def _assert_attendance_workspace(response):
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert "workspace_ui.css" in html
    assert "attendance_workspace.css" in html
    assert "Посещаемость" in html
    assert 'class="attendance-tabs"' in html


def test_admin_attendance_pages_use_shared_workspace(client, make_user, login):
    admin_id = make_user("ADMIN")
    login(admin_id)

    for path in ATTENDANCE_PAGES:
        _assert_attendance_workspace(client.get(path))


def test_attendance_navigation_respects_existing_role_access(client, make_user, login):
    class_teacher_id = make_user("CLASS_TEACHER")
    login(class_teacher_id)

    for path in ("/attendance/passes", "/attendance/passes/new", "/attendance/analytics"):
        response = client.get(path)
        _assert_attendance_workspace(response)
        html = response.get_data(as_text=True)
        assert ">Импорт</span>" not in html
        assert ">Начало занятий</span>" not in html
        assert ">КПП</span>" not in html

    for path in ("/attendance/import", "/attendance/imports", "/attendance/schedule", "/attendance/kpp"):
        response = client.get(path)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")

    kpp_id = make_user("KPP")
    login(kpp_id)
    for path in ("/attendance/passes", "/attendance/kpp"):
        _assert_attendance_workspace(client.get(path))
    assert client.get("/attendance/analytics").status_code == 302


def test_attendance_templates_share_one_section_layout():
    templates_dir = Path(__file__).resolve().parents[1] / "app" / "templates"
    page_templates = sorted(templates_dir.glob("attendance_*.html"))
    page_templates.remove(templates_dir / "attendance_workspace.html")

    assert page_templates
    for template_path in page_templates:
        source = template_path.read_text(encoding="utf-8")
        assert source.startswith('{% extends "attendance_workspace.html" %}')
        assert "{% block attendance_content %}" in source
