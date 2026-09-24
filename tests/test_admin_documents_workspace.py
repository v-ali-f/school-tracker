import pytest


@pytest.mark.parametrize(
    "path",
    (
        "/drive/",
        "/drive/collections",
        "/drive/collections/new",
        "/familiarizations/",
        "/familiarizations/my",
        "/familiarizations/new",
        "/documents/registers/",
        "/documents/registers/incoming",
        "/documents/registers/incoming/new",
        "/documents/registers/access",
        "/documents/archive",
        "/orders",
        "/orders/new",
        "/orders/responsibles",
        "/office/new/docx",
    ),
)
def test_document_workflows_use_shared_workspace_shell(
    client,
    make_user,
    login,
    path,
):
    login(make_user("ADMIN"))

    response = client.get(path, follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert "module_workspace.css" in html
    assert "operations_workspace.css" in html
    assert "Диск" in html
    assert "Сборы файлов" in html
    assert "Ознакомления" in html
    assert "Реестры документов" in html
    assert "Приказы" in html
    assert "Архив" in html


@pytest.mark.parametrize(
    "path",
    (
        "/admin/users",
        "/admin/users/activity",
        "/admin/users/paths",
        "/admin/users/new",
        "/admin/users/import",
        "/admin/users/unmatched-staff",
        "/admin/users/duplicates",
        "/admin/role-access/",
        "/admin/roles",
        "/admin/organization-settings",
        "/admin/email-settings",
        "/academic-years",
        "/buildings",
        "/subjects/import",
    ),
)
def test_admin_pages_use_shared_workspace_shell(
    client,
    make_user,
    login,
    path,
):
    login(make_user("ADMIN"))

    response = client.get(path, follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert "module_workspace.css" in html
    assert "operations_workspace.css" in html
    assert "Пользователи" in html
    assert "Назначение ролей" in html
    assert "Роли и доступ" in html
    assert "Организация" in html
    assert "Учебные годы" in html
    assert "Здания" in html


def test_teacher_sees_only_personal_document_tabs_and_not_admin_pages(
    client,
    make_user,
    login,
):
    login(make_user("TEACHER"))

    response = client.get("/familiarizations/my")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="sp-workspace ws-workspace"' in html
    assert "Мои ознакомления" in html
    assert "Реестры документов" not in html
    assert "Архив" not in html
    assert client.get("/documents/archive").status_code == 403
    assert client.get("/admin/users").status_code == 403
