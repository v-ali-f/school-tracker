from flask import request, url_for
from flask_login import current_user

from app.permissions import _user_role_codes


def _workspace_nav():
    from app.modules.hub.routes import build_home_context

    return build_home_context()


def documents_workspace_context():
    endpoint = request.endpoint or ""
    roles = _user_role_codes(current_user)
    manager_roles = {"ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR", "SECRETARY", "SECRETARY_ACADEMIC"}
    document_admin_roles = {"ADMIN", "DIRECTOR"}
    tabs = [
        {"title": "Диск", "icon": "bi-hdd-network", "url": url_for("drive.index"), "active": endpoint == "drive.index" or endpoint.startswith("office.")},
        {"title": "Сборы файлов", "icon": "bi-collection", "url": url_for("drive.collections_list"), "active": endpoint.startswith("drive.collection")},
        {"title": "Мои ознакомления", "icon": "bi-person-check", "url": url_for("familiarizations.my"), "active": endpoint == "familiarizations.my"},
    ]
    if roles & manager_roles:
        tabs.append({"title": "Ознакомления", "icon": "bi-check2-square", "url": url_for("familiarizations.index"), "active": endpoint.startswith("familiarizations.") and endpoint != "familiarizations.my"})
    if roles & document_admin_roles or endpoint.startswith("document_registers."):
        tabs.append({"title": "Реестры документов", "icon": "bi-journal-text", "url": url_for("document_registers.index"), "active": endpoint.startswith("document_registers.")})
    if roles & document_admin_roles or endpoint.startswith("orders."):
        tabs.append({"title": "Приказы", "icon": "bi-file-earmark-text", "url": url_for("orders.registry"), "active": endpoint.startswith("orders.")})
    if "ADMIN" in roles:
        tabs.append({"title": "Архив", "icon": "bi-archive", "url": url_for("documents.documents_archive"), "active": endpoint == "documents.documents_archive"})
    return {
        "workspace_nav": _workspace_nav(),
        "workspace_context_title": "Документы и файлы",
        "workspace_context_subtitle": "Реестры, ознакомления, хранилище и сборы файлов",
        "documents_workspace_tabs": tabs,
    }


def admin_workspace_context():
    endpoint = request.endpoint or ""
    tabs = [
        {"title": "Пользователи", "icon": "bi-people", "url": url_for("users.users_list"), "active": endpoint.startswith("users.")},
        {"title": "Назначение ролей", "icon": "bi-person-badge", "url": url_for("children.roles_admin"), "active": endpoint == "children.roles_admin"},
        {"title": "Роли и доступ", "icon": "bi-shield-check", "url": url_for("role_access_admin.settings"), "active": endpoint.startswith("role_access_admin.")},
        {"title": "Организация", "icon": "bi-building-gear", "url": url_for("organization_settings.edit"), "active": endpoint.startswith("organization_settings.")},
        {"title": "Почта", "icon": "bi-envelope-gear", "url": url_for("admin_email_settings.email_settings"), "active": endpoint.startswith("admin_email_settings.")},
        {"title": "Учебные годы", "icon": "bi-calendar3", "url": url_for("children.academic_years_registry"), "active": endpoint == "children.academic_years_registry"},
        {"title": "Здания", "icon": "bi-buildings", "url": url_for("children.buildings_registry"), "active": endpoint == "children.buildings_registry"},
        {"title": "Импорт предметов", "icon": "bi-upload", "url": url_for("children.subjects_import"), "active": endpoint == "children.subjects_import"},
    ]
    return {
        "workspace_nav": _workspace_nav(),
        "workspace_context_title": "Администрирование",
        "workspace_context_subtitle": "Учётные записи, права, реквизиты и системные справочники",
        "admin_workspace_tabs": tabs,
    }
