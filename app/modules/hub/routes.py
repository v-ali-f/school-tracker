from flask import Blueprint, abort, current_app, render_template, request, url_for
from flask_login import current_user, login_required

from app.permissions import has_permission, has_any_role, has_role

hub_bp = Blueprint("hub", __name__, url_prefix="/hub")


ICON_MAP = {
    "Инциденты": ("bi-shield-exclamation", "accent-dark"),
    "Травмы": ("bi-heart-pulse", "accent-orange"),
    "Вызов скорой": ("bi-activity", "accent-orange"),
    "Нарушения дисциплины": ("bi-exclamation-octagon", "accent-dark"),
    "Травмы и вызов скорой": ("bi-heart-pulse", "accent-orange"),
    "Драки и конфликты": ("bi-people", "accent-orange"),
    "Буллинг": ("bi-shield-exclamation", "accent-orange"),
    "Добавить инцидент": ("bi-shield-plus", "accent-orange"),
    "Дашборд инцидентов": ("bi-graph-up-arrow", "accent-dark"),
    "Сводный контингент": ("bi-people", "accent-green"),
    "Создать пропуск": ("bi-person-vcard", "accent-green"),
    "Кафедры": ("bi-diagram-3", "accent-dark"),
    "Диагностики МЦКО": ("bi-clipboard-data", "accent-orange"),
    "Пропуска и аналитика посещаемости": ("bi-calendar-check", "accent-green"),
    "Олимпиады": ("bi-trophy", "accent-orange"),
    "Реестр приказов": ("bi-file-earmark-text", "accent-dark"),
    "Классное руководство": ("bi-person-badge", "accent-green"),
    "Социально-психологическая служба": ("bi-people-fill", "accent-blue"),
    "Учебные годы": ("bi-calendar3", "accent-dark"),
    "Классы учебного года": ("bi-grid-3x3-gap", "accent-dark"),
    "Реестр предметов": ("bi-book", "accent-orange"),
    "Реестр олимпиадных предметов": ("bi-award", "accent-orange"),
    "Несопоставленные результаты олимпиад": ("bi-link-45deg", "accent-orange"),
    "Пользователи": ("bi-people", "accent-dark"),
    "Документы": ("bi-folder2-open", "accent-dark"),
    "Время начала занятий": ("bi-clock", "accent-green"),
    "Обновить архив по срокам хранения": ("bi-arrow-repeat", "accent-dark"),
    "Реестр зданий": ("bi-building", "accent-dark"),
    "План работы школы": ("bi-calendar-week", "accent-blue"),
    "База знаний": ("bi-book-half", "accent-blue"),
}

ACCENT_TO_ZONE = {
    "primary": "blue",
    "success": "green",
    "secondary": "orange",
    "dark": "rose",
    "accent-green": "green",
    "accent-orange": "orange",
    "accent-dark": "rose",
    "accent-blue": "blue",
}

THEME_ZONE_MAP = {
    "incidents": "orange",
    "departments": "blue",
    "diagnostics": "rose",
    "attendance": "green",
    "olympiads": "rose",
    "orders": "slate",
    "classroom": "green",
    "admin": "slate",
}

TITLE_ZONE_MAP = {
    "Инциденты": "orange",
    "Травмы": "orange",
    "Вызов скорой": "orange",
    "Нарушения дисциплины": "orange",
    "Травмы и вызов скорой": "orange",
    "Драки и конфликты": "orange",
    "Буллинг": "orange",
    "Добавить инцидент": "orange",
    "Дашборд инцидентов": "orange",
    "Сводный контингент": "green",
    "Создать пропуск": "green",
    "Кафедры": "blue",
    "Диагностики МЦКО": "rose",
    "Пропуска и аналитика посещаемости": "green",
    "Олимпиады": "rose",
    "Реестр приказов": "slate",
    "Классное руководство": "green",
    "Учебные годы": "slate",
    "Классы учебного года": "green",
    "Реестр предметов": "green",
    "Реестр олимпиадных предметов": "rose",
    "Несопоставленные результаты олимпиад": "rose",
    "Пользователи": "slate",
    "Документы": "slate",
    "Время начала занятий": "green",
    "Обновить архив по срокам хранения": "slate",
    "Реестр зданий": "slate",
    "План работы школы": "blue",
    "База знаний": "blue",
}


def _infer_zone(row, default="blue"):
    title = (row.get("title") or "").strip()
    if row.get("zone"):
        return row["zone"]
    if title in TITLE_ZONE_MAP:
        return TITLE_ZONE_MAP[title]
    accent_class = row.get("accent_class")
    if accent_class in ACCENT_TO_ZONE:
        return ACCENT_TO_ZONE[accent_class]
    accent = row.get("accent")
    if accent in ACCENT_TO_ZONE:
        return ACCENT_TO_ZONE[accent]
    return default


def _decorate_item(row):
    icon, accent = ICON_MAP.get(row.get("title"), (None, None))
    if icon and not row.get("icon"):
        row["icon"] = icon
    if accent and not row.get("accent_class"):
        row["accent_class"] = accent
    row.setdefault("zone", _infer_zone(row, default="slate"))
    return row


def _endpoint_exists(endpoint: str) -> bool:
    return endpoint in current_app.view_functions


def _safe_url(endpoint: str, **values):
    if endpoint and _endpoint_exists(endpoint):
        try:
            return url_for(endpoint, **values)
        except Exception:
            return None
    return None


def _allowed(item: dict) -> bool:
    visible_if = item.get("visible_if")
    if callable(visible_if):
        try:
            if not visible_if():
                return False
        except Exception:
            return False

    roles_any = item.get("roles_any") or []
    if roles_any and not has_any_role(*roles_any):
        return False

    permission_any = item.get("permission_any") or []
    if permission_any and not any(has_permission(code) for code in permission_any):
        return False

    endpoint = item.get("endpoint")
    if endpoint and not _endpoint_exists(endpoint):
        return False

    return True


def _materialize(items):
    prepared = []
    for item in items:
        if not _allowed(item):
            continue
        row = dict(item)
        endpoint = row.get("endpoint")
        if endpoint:
            row["url"] = _safe_url(endpoint, **row.get("endpoint_kwargs", {}))
        row.setdefault("url", row.get("external_url"))
        prepared.append(_decorate_item(row))
    return prepared


_SUMMARY_STATS_CACHE = {"ts": 0.0, "data": None}
_SUMMARY_TTL_SECONDS = 60


def _get_summary_stats():
    """Возвращает статистику инцидентов за сегодня с кешом TTL 60 сек.
    Цифры одинаковы для всех пользователей, поэтому кеш глобальный.
    """
    import time as _time_mod
    now = _time_mod.time()
    cache = _SUMMARY_STATS_CACHE
    if cache["data"] is not None and (now - cache["ts"]) < _SUMMARY_TTL_SECONDS:
        return cache["data"]

    stats = {
        "incidents": 0,
        "injuries": 0,
        "ambulance": 0,
        "discipline": 0,
    }
    try:
        from app.main import _dashboard_stats
        dashboard = _dashboard_stats()
        stats["incidents"] = dashboard.get("incidents_today", 0)
        stats["injuries"] = dashboard.get("injuries_today", 0)
        stats["discipline"] = dashboard.get("discipline_today", 0)

        from app.models import Incident
        from datetime import date, datetime, time
        today = date.today()
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        stats["ambulance"] = Incident.query.filter(
            Incident.occurred_at >= today_start,
            Incident.occurred_at <= today_end,
            Incident.category.ilike("%скор%"),
        ).count()
    except Exception:
        pass

    cache["ts"] = now
    cache["data"] = stats
    return stats


def _summary_cards():
    stats = _get_summary_stats()
    return _materialize([
        {
            "title": "Инциденты",
            "value": stats["incidents"],
            "description": "События за сегодня",
            "endpoint": "children.incidents_dashboard",
            "permission_any": ["incident_dashboard_view"],
        },
        {
            "title": "Травмы",
            "value": stats["injuries"],
            "description": "Текущий день",
            "endpoint": "children.incidents_dashboard",
            "permission_any": ["incident_dashboard_view"],
        },
        {
            "title": "Вызов скорой",
            "value": stats["ambulance"],
            "description": "Текущий день",
            "endpoint": "children.incidents_dashboard",
            "permission_any": ["incident_dashboard_view"],
        },
        {
            "title": "Нарушения дисциплины",
            "value": stats["discipline"],
            "description": "Текущий день",
            "endpoint": "children.incidents_dashboard",
            "permission_any": ["incident_dashboard_view"],
        },
    ])


def _main_page_config():
    return {
        "quick_search": {
            "title": "Быстрый поиск",
            "placeholder": "Поиск ученика по ФИО, части ФИО или классу",
            "endpoint": "children.list_children",
            "param": "q",
            "description": "Поиск ученика по всей школе с переходом к результатам.",
        },
        "quick_actions": _materialize([
            {
                "title": "Добавить инцидент",
                "description": "Быстро зарегистрировать новое событие.",
                "endpoint": "children.incident_new",
                "permission_any": ["incident_add"],
                "accent": "primary",
            },
            {
                "title": "Дашборд инцидентов",
                "description": "Открыть аналитику по инцидентам.",
                "endpoint": "children.incidents_dashboard",
                "permission_any": ["incident_dashboard_view"],
                "accent": "dark",
            },
            {
                "title": "Сводный контингент",
                "description": "Общая сводка по обучающимся.",
                "endpoint": "children.contingent",
                "permission_any": ["contingent_view"],
                "accent": "success",
            },
            {
                "title": "Создать пропуск",
                "description": "Оформить пропуск для ученика.",
                "endpoint": "attendance.new_pass",
                "roles_any": ["CLASS_TEACHER", "TEACHER"],
                "accent": "secondary",
            },
            {
                "title": "Мои заявки",
                "description": "Поданные инциденты, статусы и история.",
                "endpoint": "children.incidents_my",
                "permission_any": ["incident_add"],
                "accent": "secondary",
            },
            {
                "title": "Мои задачи",
                "description": "Поручения, сроки и просроченные задачи.",
                "endpoint": "tasks.my_tasks",
                "accent": "primary",
            },
        ]),
        "secondary_sections": _materialize([
            {
                "title": "Инциденты",
                "description": "Реестр, категории (травмы, драки, буллинг, дисциплина) и дашборд событий.",
                "endpoint": "hub.incidents",
                "permission_any": ["incident_registry_view", "incident_dashboard_view"],
            },
            {
                "title": "Кафедры",
                "description": "Предметные кафедры, сводки и нагрузка педагогов.",
                "endpoint": "hub.departments",
            },
            {
                "title": "Диагностики МЦКО",
                "description": "Сессии, импорт результатов, аналитика и привязка к учителям.",
                "endpoint": "hub.diagnostics",
            },
            {
                "title": "Пропуска и аналитика посещаемости",
                "description": "Реестр пропусков, аналитика, импорт и начало занятий.",
                "endpoint": "hub.attendance",
                "roles_any": ["ADMIN", "CLASS_TEACHER", "SOCIAL_PEDAGOG"],
            },
            {
                "title": "Олимпиады",
                "description": "Перечень олимпиад, импорт результатов и аналитика.",
                "endpoint": "hub.olympiads",
                "permission_any": ["olympiad_view", "olympiad_import", "olympiad_dashboard_view"],
            },
            {
                "title": "Реестр приказов",
                "description": "Журнал приказов, шаблоны, поиск и архив.",
                "endpoint": "hub.orders",
                "roles_any": ["ADMIN", "METHODIST", "SOCIAL_PEDAGOG"],
            },
            {
                "title": "Классное руководство",
                "description": "Социальный паспорт класса, пропуски и инциденты класса.",
                "endpoint": "hub.classroom",
                "roles_any": ["ADMIN", "CLASS_TEACHER", "METHODIST", "SOCIAL_PEDAGOG"],
            },
            {
                "title": "Социально-психологическая служба",
                "description": "Специалисты службы, структура, здания и ответственные по модулю.",
                "endpoint": "service_staff.index",
                "visible_if": lambda: has_role("ADMIN") or has_role("METHODIST") or has_role("PSYCHOLOGIST") or has_role("SOCIAL_PEDAGOG"),
            },
            {
                "title": "Задачи и поручения",
                "description": "Постановка задач, сроки, комментарии и контроль исполнения.",
                "endpoint": "tasks.my_tasks",
            },
            {
                "title": "План работы школы",
                "description": "Школьный план мероприятий по дням, периодам, зданиям и классам.",
                "endpoint": "school_plan.index",
                "roles_any": ["ADMIN", "METHODIST", "DEPUTY_DIRECTOR", "SOCIAL_PEDAGOG"],
            },
            {
                "title": "База знаний",
                "description": "Инструкции и материалы по работе в системе для каждой роли.",
                "endpoint": "knowledge.knowledge_list",
            },
        ]),
        "admin_sections": _materialize([
            {"title": "Учебные годы", "endpoint": "children.academic_years_registry", "roles_any": ["ADMIN"]},
            {"title": "Классы учебного года", "endpoint": "children.classes_registry", "roles_any": ["ADMIN"]},
            {"title": "Реестр предметов", "endpoint": "children.subjects_registry", "roles_any": ["ADMIN"]},
            {"title": "Реестр олимпиадных предметов", "endpoint": "olympiads.settings", "roles_any": ["ADMIN"]},
            {"title": "Несопоставленные результаты олимпиад", "endpoint": "olympiads.unmatched", "roles_any": ["ADMIN"]},
            {"title": "Пользователи", "endpoint": "users.users_list", "roles_any": ["ADMIN"]},
            {"title": "Документы", "endpoint": "documents.documents_archive", "roles_any": ["ADMIN"]},
            {"title": "Время начала занятий", "endpoint": "attendance.schedule_rules", "roles_any": ["ADMIN"]},
            {"title": "Обновить архив по срокам хранения", "endpoint": "documents.run_retention", "roles_any": ["ADMIN"]},
            {"title": "Реестр зданий", "endpoint": "children.buildings_registry", "roles_any": ["ADMIN"]},
            {"title": "Настройки организации", "endpoint": "organization_settings.edit", "roles_any": ["ADMIN"]},
            {"title": "Настройка почты", "endpoint": "organization_settings.mail_settings", "roles_any": ["ADMIN"]},
        ]),
    }


def _theme_configs():
    return {
        "incidents": {
            "title": "Инциденты",
            "subtitle": "Все разделы, связанные с инцидентами, травмами и дисциплиной.",
            "permission_any": ["incident_add", "incident_registry_view", "incident_dashboard_view"],
            "quick_actions": _materialize([
                {"title": "Добавить инцидент", "endpoint": "children.incident_new", "permission_any": ["incident_add"]},
                {"title": "Дашборд инцидентов", "endpoint": "children.incidents_dashboard", "permission_any": ["incident_dashboard_view"]},
            ]),
            "sections": _materialize([
                {"title": "Добавить инцидент", "description": "Создать новую запись об инциденте.", "endpoint": "children.incident_new", "permission_any": ["incident_add"]},
                {"title": "Дашборд инцидентов", "description": "Оперативная аналитика по событиям.", "endpoint": "children.incidents_dashboard", "permission_any": ["incident_dashboard_view"]},
                {"title": "Реестр инцидентов", "description": "Полный журнал всех инцидентов.", "endpoint": "children.incidents_registry", "permission_any": ["incident_registry_view"]},
                {"title": "Травмы и вызов скорой", "description": "Только случаи травмирования и скорой помощи.", "endpoint": "children.incidents_registry", "endpoint_kwargs": {"category": "Травма/вызов скорой"}, "permission_any": ["incident_registry_view"]},
                {"title": "Нарушения дисциплины", "description": "Только дисциплинарные инциденты.", "endpoint": "children.incidents_registry", "endpoint_kwargs": {"category": "Нарушение дисциплины"}, "permission_any": ["incident_registry_view"]},
                {"title": "Драки и конфликты", "description": "Только конфликтные ситуации.", "endpoint": "children.incidents_registry", "endpoint_kwargs": {"category": "Драка/конфликт"}, "permission_any": ["incident_registry_view"]},
                {"title": "Буллинг", "description": "Случаи буллинга.", "endpoint": "children.incidents_registry", "endpoint_kwargs": {"category": "Буллинг"}, "permission_any": ["incident_registry_view"]},
            ]),
        },
        "departments": {
            "title": "Кафедры",
            "subtitle": "Предметные кафедры, педнагрузка и аналитика по объединениям.",
            "sections": _materialize([
                {"title": "Настройка предметных кафедр", "description": "Структура кафедр и состав участников.", "endpoint": "departments.settings"},
                {"title": "Свод по кафедрам", "description": "Итоги и показатели по кафедрам.", "endpoint": "departments.summary"},
                {"title": "Нагрузка учителей", "description": "Распределение часов и учебной нагрузки.", "endpoint": "departments.loads"},
                {"title": "Аналитика по кафедрам", "description": "Общий экран кафедральной аналитики.", "endpoint": "departments.index"},
            ]),
        },
        "diagnostics": {
            "title": "Диагностики МЦКО",
            "subtitle": "Сессии диагностики, импорт PDF-отчетов, аналитика и привязка к учителям.",
            "sections": _materialize([
                {"title": "Список диагностик", "description": "Сессии, карточки и итоги диагностик.", "endpoint": "diagnostics.index"},
                {"title": "Импорт результатов", "description": "Загрузка новых пакетов результатов.", "endpoint": "diagnostics.imports_registry"},
                {"title": "Аналитика диагностик", "description": "Темы, уровни и результаты.", "endpoint": "diagnostics.analytics"},
                {"title": "Привязка к учителям", "description": "Связь результатов с педагогами.", "endpoint": "diagnostics.teacher_binding"},
                {"title": "Кафедральная аналитика", "description": "Результаты по кафедрам.", "endpoint": "diagnostics.departments_summary"},
            ]),
        },
        "attendance": {
            "title": "Пропуска и аналитика посещаемости",
            "subtitle": "Реестр пропусков, аналитика посещаемости, импорт и время начала занятий.",
            "roles_any": ["ADMIN", "CLASS_TEACHER", "SOCIAL_PEDAGOG"],
            "sections": _materialize([
                {"title": "Реестр пропусков", "description": "Список оформленных пропусков.", "endpoint": "attendance.passes_registry"},
                {"title": "Создать пропуск", "description": "Оформить новый пропуск.", "endpoint": "attendance.new_pass"},
                {"title": "Аналитика посещаемости", "description": "Посещаемость, опоздания, KPI и рейтинг классов.", "endpoint": "attendance.analytics"},
                {"title": "Импорт", "description": "Загрузка отчетов по посещаемости.", "endpoint": "attendance.import_view", "roles_any": ["ADMIN"]},
                {"title": "Начало занятий", "description": "Настройка времени начала занятий по параллелям.", "endpoint": "attendance.schedule_rules", "roles_any": ["ADMIN"]},
            ]),
        },
        "olympiads": {
            "title": "Олимпиады",
            "subtitle": "Олимпиадное движение, импорт результатов, сводки и аналитика.",
            "permission_any": ["olympiad_view", "olympiad_import", "olympiad_dashboard_view"],
            "sections": _materialize([
                {"title": "Результаты олимпиад", "description": "Реестр участников, победителей и призёров.", "endpoint": "olympiads.registry", "permission_any": ["olympiad_view"]},
                {"title": "Импорт результатов", "description": "Загрузка новых файлов и просмотр импортов.", "endpoint": "olympiads.import_view", "permission_any": ["olympiad_import"]},
                {"title": "Аналитика", "description": "Срезы по предметам, учителям и этапам.", "endpoint": "olympiads.analytics", "permission_any": ["olympiad_view", "olympiad_dashboard_view"]},
                {"title": "Привязка к учителям", "description": "Назначение учителя на класс и предмет.", "endpoint": "olympiads.teacher_binding", "permission_any": ["olympiad_edit"]},
                {"title": "Связь с кафедрами", "description": "Привязка результатов к кафедрам.", "endpoint": "olympiads.department_registry", "permission_any": ["olympiad_department_summary_view"]},
            ]),
        },
        "orders": {
            "title": "Реестр приказов",
            "subtitle": "Журнал приказов, создание, шаблоны и архивное хранение.",
            "roles_any": ["ADMIN", "METHODIST", "SOCIAL_PEDAGOG"],
            "sections": _materialize([
                {"title": "Журнал приказов", "description": "Список всех приказов с поиском и фильтрацией.", "endpoint": "orders.registry"},
                {"title": "Создание приказа", "description": "Оформление нового приказа.", "endpoint": "orders.create"},
                {"title": "Шаблоны и ответственные", "description": "Настройка ответственных и типовых данных.", "endpoint": "orders.responsibles"},
            ]),
        },
        "classroom": {
            "title": "Классное руководство",
            "subtitle": "Социальный паспорт, результаты, пропуски и инциденты класса.",
            "roles_any": ["ADMIN", "CLASS_TEACHER", "METHODIST", "SOCIAL_PEDAGOG"],
            "sections": _materialize([
                {"title": "Социальный паспорт класса", "description": "Реестр и статусы по классам.", "endpoint": "children.social_passport_registry", "permission_any": ["social_passport_registry_view"]},
                {"title": "Сопровождение класса", "description": "Показатели, сопровождение и наблюдение.", "endpoint": "children.social_passport_dashboard", "permission_any": ["social_passport_dashboard_view"]},
                {"title": "Результаты класса", "description": "Учебные результаты и контрольные работы.", "endpoint": "academic.dashboard", "permission_any": ["control_works_view"]},
                {"title": "Пропуски класса", "description": "Посещаемость и пропуска по классу.", "endpoint": "attendance.analytics", "roles_any": ["ADMIN", "CLASS_TEACHER", "SOCIAL_PEDAGOG"]},
                {"title": "Инциденты класса", "description": "События и случаи по обучающимся класса.", "endpoint": "children.incidents_registry", "roles_any": ["ADMIN", "METHODIST", "PSYCHOLOGIST", "SOCIAL_PEDAGOG"]},
            ]),
        },
        "admin": {
            "title": "Для администратора",
            "subtitle": "Служебные настройки и технические разделы управления системой.",
            "roles_any": ["ADMIN"],
            "sections": _main_page_config()["admin_sections"],
        },
    }


def _theme_or_403(theme_key: str):
    config = _theme_configs().get(theme_key)
    if not config:
        abort(404)
    if not _allowed(config):
        abort(403)
    prepared = dict(config)
    prepared.setdefault("zone", THEME_ZONE_MAP.get(theme_key, "blue"))
    return prepared


@hub_bp.route("/incidents")
@login_required
def incidents():
    return render_template("hub/theme_page.html", theme=_theme_or_403("incidents"))


@hub_bp.route("/departments")
@login_required
def departments():
    return render_template("hub/theme_page.html", theme=_theme_or_403("departments"))


@hub_bp.route("/diagnostics")
@login_required
def diagnostics():
    return render_template("hub/theme_page.html", theme=_theme_or_403("diagnostics"))


@hub_bp.route("/attendance")
@login_required
def attendance():
    return render_template("hub/theme_page.html", theme=_theme_or_403("attendance"))


@hub_bp.route("/olympiads")
@login_required
def olympiads():
    return render_template("hub/theme_page.html", theme=_theme_or_403("olympiads"))


@hub_bp.route("/orders")
@login_required
def orders():
    return render_template("hub/theme_page.html", theme=_theme_or_403("orders"))


@hub_bp.route("/classroom")
@login_required
def classroom():
    return render_template("hub/theme_page.html", theme=_theme_or_403("classroom"))


@hub_bp.route("/admin")
@login_required
def admin():
    return render_template("hub/theme_page.html", theme=_theme_or_403("admin"))


def _class_teacher_context():
    """Возвращает объект SchoolClass, которым руководит текущий пользователь, или None."""
    if not has_role("CLASS_TEACHER"):
        return None
    try:
        from app.models import AcademicYear, SchoolClass
        current_year = AcademicYear.query.filter_by(is_current=True).first()
        if not current_year:
            return None
        return SchoolClass.query.filter_by(
            teacher_user_id=current_user.id,
            academic_year_id=current_year.id,
            is_active=True,
        ).first()
    except Exception:
        return None


def _read_block_codes(role_code: str):
    """
    Читает настройки видимости блоков дашборда для роли из RoleDashboardBlock.
    Возвращает frozenset видимых block_code, либо None если настроек нет (→ показывать всё).
    """
    try:
        from app.models.role_access import RoleDashboardBlock
        rows = RoleDashboardBlock.query.filter_by(role_code=role_code, is_active=True).all()
        if not rows:
            return None
        return frozenset(
            r.block_code for r in rows
            if r.is_visible and r.is_enabled and r.access_level != "hidden"
        )
    except Exception:
        return None


# Список кодов, в которых показывается полоса быстрой сводки
_SUMMARY_ROLES = {"ADMIN", "METHODIST", "SOCIAL_PEDAGOG", "PSYCHOLOGIST", "DEPUTY_DIRECTOR"}

# Читаемые названия ролей для баннера превью
_ROLE_LABELS = {
    "ADMIN": "Администратор",
    "CLASS_TEACHER": "Классный руководитель",
    "TEACHER": "Учитель",
    "PSYCHOLOGIST": "Психолог",
    "SOCIAL_PEDAGOG": "Социальный педагог",
    "METHODIST": "Методист",
    "KPP": "КПП",
    "VIEWER": "Наблюдатель",
    "DEPUTY_DIRECTOR": "Заместитель директора",
}


def build_home_context():
    from flask import request as _request
    from app.permissions import is_admin as _is_admin, _user_role_codes

    # ── Preview-режим (только для ADMIN) ──
    preview_role = None
    if _is_admin():
        pr = (_request.args.get("preview_role") or "").strip().upper()
        if pr:
            preview_role = pr

    # ── Роль для чтения настроек видимости блоков ──
    if preview_role:
        lookup_role = preview_role
    else:
        codes = _user_role_codes()
        lookup_role = next(iter(codes), None) or getattr(current_user, "role", None)

    role_block_codes = _read_block_codes(lookup_role) if lookup_role else None

    # ── Реальные флаги текущего пользователя (не подменяем на preview) ──
    is_ct = has_role("CLASS_TEACHER")
    show_summary = has_any_role(*_SUMMARY_ROLES)

    # В preview-режиме эмулируем флаги выбранной роли
    if preview_role:
        is_ct = (preview_role == "CLASS_TEACHER")
        show_summary = preview_role in _SUMMARY_ROLES

    class_teacher_class = _class_teacher_context() if is_ct and not preview_role else None

    # Генерируем page config с учётом preview-роли:
    # временно подменяем роль в g, чтобы _allowed() фильтровал по preview-роли
    if preview_role:
        from flask import g
        g._hub_preview_role_codes = {preview_role}
    page = _main_page_config()
    if preview_role:
        g._hub_preview_role_codes = None

    return {
        "page": page,
        "quick_summary": _summary_cards() if show_summary else [],
        "show_quick_summary": show_summary,
        "show_admin_block": has_role("ADMIN") and not preview_role,
        "class_teacher_class": class_teacher_class,
        "is_class_teacher": is_ct,
        "role_block_codes": role_block_codes,
        "preview_role": preview_role,
        "preview_role_label": _ROLE_LABELS.get(preview_role, preview_role) if preview_role else None,
    }
