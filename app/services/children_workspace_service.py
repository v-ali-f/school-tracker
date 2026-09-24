"""Role-aware workspace navigation for children, incidents and admin pages."""

from flask import request, url_for

from app.permissions import has_role


REGISTRY_WORKSPACE_ENDPOINTS = {
    "children.list_children",
    "children.contingent",
    "children.classes_registry",
    "children.comments_registry",
    "children.registry_vshu",
    "children.registry_ovz",
    "children.registry_az",
    "children.registry_enrolled",
    "children.registry_expelled",
    "children.registry_kdn",
    "children.new_child",
    "children.child_card",
    "children.children_import",
    "children.parents_import",
    "children.class_detail",
    "children.classrooms_registry",
}

INCIDENT_WORKSPACE_ENDPOINTS = {
    "children.incident_new",
    "children.incident_edit",
    "children.incident_timeline",
    "children.incidents_my",
    "children.incidents_registry",
    "children.incidents_dashboard",
}

ADMIN_WORKSPACE_ENDPOINTS = {
    "children.academic_years_registry",
    "children.buildings_registry",
    "children.roles_admin",
    "children.subjects_import",
}


def workspace_navigation():
    from app.modules.hub.routes import build_home_context

    return build_home_context()


def children_workspace_context():
    """Build the shared shell context for routes on the children blueprint."""
    endpoint = request.endpoint or ""
    if endpoint in ADMIN_WORKSPACE_ENDPOINTS:
        from app.services.workspace_navigation_service import admin_workspace_context

        return admin_workspace_context()

    if endpoint in INCIDENT_WORKSPACE_ENDPOINTS:
        return {
            "workspace_nav": workspace_navigation(),
            "workspace_context_title": "Инциденты",
            "workspace_context_subtitle": (
                "Регистрация, сопровождение и аналитика событий"
            ),
        }

    if endpoint not in REGISTRY_WORKSPACE_ENDPOINTS:
        return {}

    is_contingent = endpoint == "children.contingent"
    children_tabs = [
        {
            "title": "Ученики",
            "icon": "bi-people",
            "url": url_for("children.list_children"),
            "active": endpoint in {
                "children.list_children",
                "children.new_child",
                "children.child_card",
                "children.children_import",
                "children.parents_import",
            },
        }
    ]
    if has_role("ADMIN"):
        children_tabs.extend(
            [
                {
                    "title": "Классы",
                    "icon": "bi-mortarboard",
                    "url": url_for("children.classes_registry"),
                    "active": endpoint in {
                        "children.classes_registry",
                        "children.class_detail",
                    },
                },
                {
                    "title": "Переводы и выбытие",
                    "icon": "bi-arrow-left-right",
                    "url": url_for("transfers.index"),
                    "active": False,
                },
                {
                    "title": "Кабинеты",
                    "icon": "bi-door-open",
                    "url": url_for("children.classrooms_registry"),
                    "active": endpoint == "children.classrooms_registry",
                },
            ]
        )
    if has_role("ADMIN") or has_role("METHODIST"):
        children_tabs.insert(
            2 if has_role("ADMIN") else 1,
            {
                "title": "Контингент",
                "icon": "bi-bar-chart",
                "url": url_for("children.contingent"),
                "active": is_contingent,
            },
        )
    return {
        "workspace_nav": workspace_navigation(),
        "children_workspace_tabs": children_tabs,
        "workspace_context_title": (
            "Контингент школы" if is_contingent else "Основные реестры"
        ),
        "workspace_context_subtitle": (
            "Сводные данные по классам и зданиям"
            if is_contingent
            else "Ученики, зачисление и движение контингента"
        ),
    }
