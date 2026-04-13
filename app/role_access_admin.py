from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.core.extensions import db
from app.models.role_access import (
    ACCESS_LEVELS,
    DashboardBlockCatalog,
    RoleDashboardBlock,
    RoleModuleAccess,
    RoleQuickLinkAccess,
)
from app.models import User
from app.permissions import is_admin as _permissions_is_admin


role_access_admin_bp = Blueprint("role_access_admin", __name__, url_prefix="/admin/role-access")


DEFAULT_MODULES = [
    ("dashboard", "Главная"),
    ("children", "Обучающиеся"),
    ("attendance", "Посещаемость и пропуски"),
    ("incidents", "Инциденты"),
    ("control_works", "Контрольные работы"),
    ("diagnostics", "Диагностики"),
    ("olympiads", "Олимпиады"),
    ("departments", "Кафедры"),
    ("service_staff", "СППС"),
    ("iom", "ИОМ"),
    ("orders", "Приказы"),
    ("documents", "Документы"),
    ("analytics", "Аналитика"),
    ("admin", "Администрирование"),
]

DEFAULT_QUICK_LINKS = [
    ("quick_search", "Быстрый поиск"),
    ("class_list", "Список класса"),
    ("attendance_pass_new", "Добавить электронный пропуск"),
    ("incident_new", "Добавить инцидент"),
    ("control_works", "Контрольные работы"),
    ("diagnostics", "Диагностики"),
    ("olympiads", "Олимпиады"),
    ("service_staff", "Сопровождение"),
    ("iom", "ИОМ"),
]

# Описания модулей — показываются в admin-панели под названием
MODULE_DESCRIPTIONS = {
    "dashboard": "Главная страница: быстрый поиск, статистика, быстрые действия",
    "children": "Реестр учеников, карточки, социальные паспорта, инциденты",
    "attendance": "Журнал посещаемости, оформление и просмотр пропусков",
    "incidents": "Реестр инцидентов: создание, просмотр, дашборд событий",
    "control_works": "Контрольные работы и результаты выполнения",
    "diagnostics": "Диагностики МЦКО, результаты тестирований по классам",
    "olympiads": "Олимпиады: участие, результаты, стадии",
    "departments": "Кафедры и предметные группы педагогов",
    "service_staff": "Сопровождение СППС: психолог, соцпедагог, ИОМ, задачи",
    "iom": "Индивидуальные образовательные маршруты учеников",
    "orders": "Реестр приказов и распоряжений по школе",
    "documents": "Загруженные файлы и документы учеников",
    "analytics": "Аналитические отчёты и сводные данные",
    "admin": "Администрирование: пользователи, роли, настройки системы",
}

# Описания быстрых кнопок
QUICK_LINK_DESCRIPTIONS = {
    "quick_search": "Строка поиска ученика на главной странице",
    "class_list": "Кнопка быстрого перехода к списку своего класса",
    "attendance_pass_new": "Кнопка оформления нового электронного пропуска",
    "incident_new": "Кнопка создания нового инцидента",
    "control_works": "Кнопка быстрого перехода в раздел контрольных работ",
    "diagnostics": "Кнопка быстрого перехода к диагностикам МЦКО",
    "olympiads": "Кнопка быстрого перехода к олимпиадам",
    "service_staff": "Кнопка перехода в раздел СППС / сопровождения",
    "iom": "Кнопка перехода к индивидуальным образовательным маршрутам",
}

# Ограничения видимости модулей по умолчанию (когда нет явной записи в БД).
# None = модуль виден всем; set = только этим ролям.
MODULE_DEFAULT_ROLES = {
    "dashboard":    None,  # все
    "children":     None,  # все (карточки ограничены на уровне маршрутов)
    "attendance":   {"ADMIN", "CLASS_TEACHER"},
    "incidents":    {"ADMIN", "TEACHER", "CLASS_TEACHER", "PSYCHOLOGIST", "SOCIAL_PEDAGOG"},
    "control_works":{"ADMIN", "TEACHER", "CLASS_TEACHER", "METHODIST"},
    "diagnostics":  None,  # все
    "olympiads":    {"ADMIN", "TEACHER", "CLASS_TEACHER", "METHODIST"},
    "departments":  None,  # все
    "service_staff":{"ADMIN", "METHODIST", "PSYCHOLOGIST", "SOCIAL_PEDAGOG"},
    "iom":          {"ADMIN", "CLASS_TEACHER", "PSYCHOLOGIST", "SOCIAL_PEDAGOG", "METHODIST"},
    "orders":       {"ADMIN", "METHODIST"},
    "documents":    {"ADMIN", "CLASS_TEACHER", "PSYCHOLOGIST", "SOCIAL_PEDAGOG"},
    "analytics":    {"ADMIN", "METHODIST"},
    "admin":        {"ADMIN"},
}


def _default_module_visible(module_code: str, role_code: str) -> bool:
    """Видимость модуля по умолчанию для роли (когда нет записи в БД)."""
    constraint = MODULE_DEFAULT_ROLES.get(module_code)
    return constraint is None or role_code in constraint


# Русские названия ролей для отображения
ROLE_LABELS = {
    "ADMIN": "Администратор",
    "CLASS_TEACHER": "Классный руководитель",
    "TEACHER": "Учитель",
    "PSYCHOLOGIST": "Психолог",
    "SOCIAL_PEDAGOG": "Социальный педагог",
    "METHODIST": "Методист",
    "KPP": "КПП (пост охраны)",
    "VIEWER": "Наблюдатель",
    "DEPUTY_DIRECTOR": "Заместитель директора",
}


def _is_admin():
    return _permissions_is_admin()


def _role_choices():
    try:
        roles = (
            db.session.query(User.role)
            .filter(User.role.isnot(None))
            .distinct()
            .order_by(User.role.asc())
            .all()
        )
        values = [r[0] for r in roles if r and r[0]]
    except Exception:
        values = []
    base_roles = ["ADMIN", "METHODIST", "TEACHER", "CLASS_TEACHER", "KPP"]
    for item in base_roles:
        if item not in values:
            values.append(item)
    return sorted(set(values))


def _ensure_defaults():
    created = False
    for block_code, title, category, default_order in [
        ("home_search", "Быстрый поиск", "dashboard", 10),
        ("home_summary", "Быстрая сводка", "dashboard", 20),
        ("home_quick_links", "Быстрый доступ", "dashboard", 30),
        ("home_sections", "Тематические разделы", "dashboard", 40),
    ]:
        exists = DashboardBlockCatalog.query.filter_by(block_code=block_code).first()
        if not exists:
            db.session.add(DashboardBlockCatalog(
                block_code=block_code,
                title=title,
                category=category,
                default_order=default_order,
                is_active=True,
            ))
            created = True
    if created:
        db.session.commit()





def _build_preview_data(selected_role, dashboard_catalog):
    module_rows = {
        row.module_code: row for row in RoleModuleAccess.query.filter_by(role_code=selected_role, is_active=True).all()
    } if selected_role else {}
    quick_rows = {
        row.quick_link_code: row for row in RoleQuickLinkAccess.query.filter_by(role_code=selected_role, is_active=True).all()
    } if selected_role else {}
    block_rows = {
        row.block_code: row for row in RoleDashboardBlock.query.filter_by(role_code=selected_role, is_active=True).all()
    } if selected_role else {}

    visible_blocks = []
    hidden_blocks = []
    for block in dashboard_catalog:
        row = block_rows.get(block.block_code)
        is_visible = True if not row else bool(row.is_visible and row.is_enabled and row.access_level != "hidden")
        payload = {
            "code": block.block_code,
            "title": block.title,
            "order": (row.display_order if row else block.default_order),
        }
        if is_visible:
            visible_blocks.append(payload)
        else:
            hidden_blocks.append(payload)

    visible_blocks.sort(key=lambda x: (x["order"], x["title"]))
    hidden_blocks.sort(key=lambda x: (x["order"], x["title"]))

    visible_quick_links = []
    hidden_quick_links = []
    for quick_link_code, title in DEFAULT_QUICK_LINKS:
        row = quick_rows.get(quick_link_code)
        is_visible = True if not row else bool(row.is_visible and row.is_enabled and row.access_level != "hidden")
        payload = {
            "code": quick_link_code,
            "title": title,
            "order": (row.display_order if row else 100),
        }
        if is_visible:
            visible_quick_links.append(payload)
        else:
            hidden_quick_links.append(payload)

    visible_quick_links.sort(key=lambda x: (x["order"], x["title"]))
    hidden_quick_links.sort(key=lambda x: (x["order"], x["title"]))

    visible_modules = []
    hidden_modules = []
    for module_code, title in DEFAULT_MODULES:
        row = module_rows.get(module_code)
        is_visible = True if not row else bool(row.is_visible and row.is_enabled and row.access_level != "hidden")
        payload = {
            "code": module_code,
            "title": title,
            "order": (row.display_order if row else 100),
            "access_level": (row.access_level if row else "view"),
        }
        if is_visible:
            visible_modules.append(payload)
        else:
            hidden_modules.append(payload)

    visible_modules.sort(key=lambda x: (x["order"], x["title"]))
    hidden_modules.sort(key=lambda x: (x["order"], x["title"]))

    return {
        "visible_blocks": visible_blocks,
        "hidden_blocks": hidden_blocks,
        "visible_quick_links": visible_quick_links,
        "hidden_quick_links": hidden_quick_links,
        "visible_modules": visible_modules,
        "hidden_modules": hidden_modules,
    }

def _upsert(model, role_code, code_field, code_value, visible, enabled, access_level, display_order):
    row = model.query.filter_by(role_code=role_code, **{code_field: code_value}).first()
    if not row:
        row = model(role_code=role_code, **{code_field: code_value})
        db.session.add(row)
    row.is_visible = bool(visible)
    row.is_enabled = bool(enabled)
    row.access_level = access_level if access_level in ACCESS_LEVELS else "view"
    row.display_order = int(display_order or 100)
    row.is_active = True
    return row


@role_access_admin_bp.route("/", methods=["GET", "POST"])
@login_required
def settings():
    if not _is_admin():
        flash("Доступ запрещен.", "danger")
        return redirect(url_for("main.dashboard"))

    _ensure_defaults()

    selected_role = (request.values.get("role") or "").strip()
    roles = _role_choices()
    if not selected_role and roles:
        selected_role = roles[0]

    dashboard_catalog = (
        DashboardBlockCatalog.query
        .filter_by(is_active=True)
        .order_by(DashboardBlockCatalog.default_order.asc(), DashboardBlockCatalog.id.asc())
        .all()
    )

    if request.method == "POST" and selected_role:
        for module_code, _title in DEFAULT_MODULES:
            _upsert(
                RoleModuleAccess,
                selected_role,
                "module_code",
                module_code,
                request.form.get(f"module_visible__{module_code}") == "1",
                request.form.get(f"module_enabled__{module_code}") == "1",
                request.form.get(f"module_access_level__{module_code}") or "view",
                request.form.get(f"module_order__{module_code}") or 100,
            )

        for quick_link_code, _title in DEFAULT_QUICK_LINKS:
            _upsert(
                RoleQuickLinkAccess,
                selected_role,
                "quick_link_code",
                quick_link_code,
                request.form.get(f"quick_visible__{quick_link_code}") == "1",
                request.form.get(f"quick_enabled__{quick_link_code}") == "1",
                request.form.get(f"quick_access_level__{quick_link_code}") or "view",
                request.form.get(f"quick_order__{quick_link_code}") or 100,
            )

        for block in dashboard_catalog:
            _upsert(
                RoleDashboardBlock,
                selected_role,
                "block_code",
                block.block_code,
                request.form.get(f"block_visible__{block.block_code}") == "1",
                request.form.get(f"block_enabled__{block.block_code}") == "1",
                request.form.get(f"block_access_level__{block.block_code}") or "view",
                request.form.get(f"block_order__{block.block_code}") or block.default_order,
            )

        db.session.commit()
        flash("Настройки доступа по роли сохранены.", "success")
        return redirect(url_for("role_access_admin.settings", role=selected_role))

    module_rows = {
        row.module_code: row for row in RoleModuleAccess.query.filter_by(role_code=selected_role, is_active=True).all()
    } if selected_role else {}
    quick_rows = {
        row.quick_link_code: row for row in RoleQuickLinkAccess.query.filter_by(role_code=selected_role, is_active=True).all()
    } if selected_role else {}
    block_rows = {
        row.block_code: row for row in RoleDashboardBlock.query.filter_by(role_code=selected_role, is_active=True).all()
    } if selected_role else {}

    # Предварительно вычисляем дефолты видимости для текущей роли
    module_defaults = {
        code: _default_module_visible(code, selected_role)
        for code, _title in DEFAULT_MODULES
    } if selected_role else {}

    return render_template(
        "role_access_settings.html",
        roles=roles,
        selected_role=selected_role,
        access_levels=ACCESS_LEVELS,
        default_modules=DEFAULT_MODULES,
        default_quick_links=DEFAULT_QUICK_LINKS,
        dashboard_catalog=dashboard_catalog,
        module_rows=module_rows,
        quick_rows=quick_rows,
        block_rows=block_rows,
        module_descriptions=MODULE_DESCRIPTIONS,
        quick_link_descriptions=QUICK_LINK_DESCRIPTIONS,
        role_labels=ROLE_LABELS,
        module_defaults=module_defaults,
    )
