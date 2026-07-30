from flask import Blueprint, abort, current_app, render_template, request, url_for
from flask_login import current_user, login_required

from app.permissions import has_permission, has_any_role, has_role
from app.core.feature_flags import WORKLOAD_MODULE, is_feature_enabled
from app.modules.workload.access import can_access_workload_module

hub_bp = Blueprint("hub", __name__, url_prefix="/hub")


ICON_MAP = {
    "Инциденты": ("bi-shield-exclamation", "accent-dark"),
    "Травмы": ("bi-heart-pulse", "accent-orange"),
    "Вызов скорой": ("bi-activity", "accent-orange"),
    "Нарушения дисциплины": ("bi-exclamation-octagon", "accent-dark"),
    "Добавить инцидент": ("bi-shield-plus", "accent-orange"),
    "Дашборд инцидентов": ("bi-graph-up-arrow", "accent-dark"),
    "Сводный контингент": ("bi-people", "accent-green"),
    "Создать пропуск": ("bi-person-vcard", "accent-green"),
    "Управленческий контур": ("bi-speedometer2", "accent-dark"),
    "Академический контур": ("bi-journal-check", "accent-orange"),
    "Контингент": ("bi-people-fill", "accent-green"),
    "Кафедры": ("bi-diagram-3", "accent-dark"),
    "Диагностики МЦКО": ("bi-clipboard-data", "accent-orange"),
    "Пропуска и аналитика посещаемости": ("bi-calendar-check", "accent-green"),
    "Основные реестры": ("bi-table", "accent-dark"),
    "Дошкольное отделение": ("bi-house-heart", "accent-green"),
    "Контрольные работы": ("bi-ui-checks-grid", "accent-orange"),
    "Олимпиады": ("bi-trophy", "accent-orange"),
    "Реестр приказов": ("bi-file-earmark-text", "accent-dark"),
    "Входящие документы": ("bi-inbox", "accent-blue"),
    "Исходящие документы": ("bi-send", "accent-green"),
    "Доступ к документам": ("bi-person-check", "accent-dark"),
    "Классное руководство": ("bi-person-badge", "accent-green"),
    "Социально-психологическая служба": ("bi-people-fill", "accent-blue"),
    "Учебные годы": ("bi-calendar3", "accent-dark"),
    "Классы учебного года": ("bi-grid-3x3-gap", "accent-dark"),
    "Группы ДОУ учебного года": ("bi-people", "accent-dark"),
    "Реестр предметов": ("bi-book", "accent-orange"),
    "Реестр олимпиадных предметов": ("bi-award", "accent-orange"),
    "Несопоставленные результаты олимпиад": ("bi-link-45deg", "accent-orange"),
    "Пользователи": ("bi-people", "accent-dark"),
    "Активность пользователей": ("bi-activity", "accent-dark"),
    "Документы": ("bi-folder2-open", "accent-dark"),
    "Время начала занятий": ("bi-clock", "accent-green"),
    "Обновить архив по срокам хранения": ("bi-arrow-repeat", "accent-dark"),
    "Реестр зданий": ("bi-building", "accent-dark"),
    "План работы школы": ("bi-calendar-week", "accent-blue"),
    "База знаний": ("bi-book-half", "accent-blue"),
    "Доп. образование": ("bi-mortarboard", "accent-blue"),
    "Задачи и поручения": ("bi-check2-square", "accent-blue"),
    "Обращения": ("bi-inbox", "accent-orange"),
    "Ознакомления": ("bi-file-earmark-check", "accent-green"),
    "Диск": ("bi-hdd-network", "accent-blue"),
    "Социально-психологическая служба": ("bi-heart-pulse", "accent-blue"),
    "Мои задачи": ("bi-lightning-charge", "accent-blue"),
    "Мои заявки": ("bi-inbox", "accent-orange"),
    "Настройки организации": ("bi-building-gear", "accent-dark"),
    "Настройка почты": ("bi-envelope-gear", "accent-dark"),
    "Управленческий дашборд": ("bi-speedometer2", "accent-blue"),
    "Открыть управленческий дашборд": ("bi-speedometer2", "accent-blue"),
    "Отчет по контингенту": ("bi-people", "accent-green"),
    "Сводная аналитика школы": ("bi-graph-up-arrow", "accent-blue"),
    "Аналитика олимпиад": ("bi-trophy", "accent-orange"),
    "Аналитика МЦКО": ("bi-clipboard-data", "accent-orange"),
    "Аналитика контрольных работ": ("bi-ui-checks-grid", "accent-orange"),
    "Аналитика пропусков": ("bi-calendar-check", "accent-green"),
    "Проблемные зоны": ("bi-exclamation-triangle", "accent-orange"),
    "Список контрольных работ": ("bi-list-check", "accent-orange"),
    "Список контрольных": ("bi-list-check", "accent-orange"),
    "Мои контрольные работы": ("bi-person-check", "accent-blue"),
    "Мои контрольные": ("bi-person-check", "accent-blue"),
    "Академический дашборд": ("bi-bar-chart-line", "accent-blue"),
    "Академическая аналитика": ("bi-bar-chart-line", "accent-blue"),
    "Успеваемость и динамика": ("bi-graph-up", "accent-green"),
    "Аналитика по классам": ("bi-grid-3x3-gap", "accent-green"),
    "Учебные отчеты": ("bi-file-earmark-bar-graph", "accent-blue"),
    "Ученики": ("bi-people", "accent-green"),
    "Добавить ученика": ("bi-person-plus", "accent-green"),
    "Реестр контингента": ("bi-table", "accent-green"),
    "Зачисленные": ("bi-person-check", "accent-green"),
    "Отчисленные": ("bi-person-dash", "accent-orange"),
    "Движение": ("bi-arrow-left-right", "accent-blue"),
    "Движение контингента": ("bi-arrow-left-right", "accent-blue"),
    "Реестр инцидентов": ("bi-shield-exclamation", "accent-orange"),
    "Настройка предметных кафедр": ("bi-sliders", "accent-blue"),
    "Свод по кафедрам": ("bi-diagram-3", "accent-blue"),
    "Нагрузка учителей": ("bi-person-lines-fill", "accent-blue"),
    "Нагрузка и тарификация": ("bi-calculator", "accent-blue"),
    "Аналитика по кафедрам": ("bi-bar-chart-line", "accent-blue"),
    "Список диагностик": ("bi-clipboard-check", "accent-orange"),
    "Импорт результатов": ("bi-upload", "accent-orange"),
    "Аналитика диагностик": ("bi-bar-chart-line", "accent-orange"),
    "Привязка к учителям": ("bi-link-45deg", "accent-blue"),
    "Сводки": ("bi-file-earmark-bar-graph", "accent-blue"),
    "Кафедральная аналитика": ("bi-diagram-3", "accent-blue"),
    "Реестр пропусков": ("bi-calendar-check", "accent-green"),
    "Аналитика посещаемости": ("bi-graph-up-arrow", "accent-green"),
    "Импорт": ("bi-upload", "accent-orange"),
    "Начало занятий": ("bi-clock", "accent-green"),
    "KPI посещаемости": ("bi-speedometer2", "accent-green"),
    "Реестр ОВЗ": ("bi-person-vcard", "accent-green"),
    "Реестр ВШУ": ("bi-exclamation-triangle", "accent-orange"),
    "Реестр КДН": ("bi-shield-check", "accent-orange"),
    "Реестр АЗ": ("bi-journal-x", "accent-orange"),
    "Аналитика": ("bi-bar-chart-line", "accent-blue"),
    "Отчеты": ("bi-file-earmark-bar-graph", "accent-blue"),
    "Сводные показатели": ("bi-speedometer", "accent-green"),
    "Перечень олимпиад": ("bi-trophy", "accent-orange"),
    "Реестр олимпиадников": ("bi-award", "accent-orange"),
    "Массовая привязка по классу и предмету": ("bi-link-45deg", "accent-blue"),
    "Связь с кафедрами и учителями": ("bi-diagram-3", "accent-blue"),
    "Журнал приказов": ("bi-journal-text", "accent-dark"),
    "Создание приказов": ("bi-file-earmark-plus", "accent-orange"),
    "Ответственные": ("bi-person-check", "accent-blue"),
    "Социальный паспорт класса": ("bi-person-vcard", "accent-green"),
    "Сопровождение класса": ("bi-people", "accent-green"),
    "Список класса": ("bi-list-ul", "accent-green"),
    "Результаты класса": ("bi-clipboard-data", "accent-blue"),
    "Аналитика успеваемости класса": ("bi-graph-up", "accent-blue"),
    "Ключевые показатели класса": ("bi-speedometer2", "accent-green"),
    "Пропуски класса": ("bi-calendar-check", "accent-green"),
    "Инциденты класса": ("bi-shield-exclamation", "accent-orange"),
}

ICON_RULES = (
    ("импорт", "bi-upload", "accent-orange"),
    ("аналитик", "bi-bar-chart-line", "accent-blue"),
    ("дашборд", "bi-speedometer2", "accent-blue"),
    ("отчет", "bi-file-earmark-bar-graph", "accent-blue"),
    ("отчёт", "bi-file-earmark-bar-graph", "accent-blue"),
    ("свод", "bi-file-earmark-bar-graph", "accent-blue"),
    ("показател", "bi-speedometer2", "accent-green"),
    ("реестр", "bi-table", "accent-dark"),
    ("список", "bi-list-ul", "accent-blue"),
    ("добавить", "bi-plus-circle", "accent-green"),
    ("создать", "bi-plus-circle", "accent-green"),
    ("настрой", "bi-sliders", "accent-dark"),
    ("привяз", "bi-link-45deg", "accent-blue"),
    ("связь", "bi-link-45deg", "accent-blue"),
    ("движение", "bi-arrow-left-right", "accent-blue"),
    ("контрольн", "bi-ui-checks-grid", "accent-orange"),
    ("олимпиад", "bi-trophy", "accent-orange"),
    ("пропуск", "bi-calendar-check", "accent-green"),
    ("посещаем", "bi-calendar-check", "accent-green"),
    ("инцидент", "bi-shield-exclamation", "accent-orange"),
    ("травм", "bi-heart-pulse", "accent-orange"),
    ("ученик", "bi-people", "accent-green"),
    ("класс", "bi-grid-3x3-gap", "accent-green"),
    ("приказ", "bi-file-earmark-text", "accent-dark"),
    ("документ", "bi-file-earmark-text", "accent-dark"),
    ("задач", "bi-check2-square", "accent-blue"),
)

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
    "management": "blue",
    "academic": "rose",
    "contingent": "green",
    "incidents": "orange",
    "departments": "blue",
    "diagnostics": "rose",
    "attendance": "green",
    "registries": "slate",
    "control_works": "rose",
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
    "Добавить инцидент": "orange",
    "Дашборд инцидентов": "orange",
    "Сводный контингент": "green",
    "Дошкольное отделение": "green",
    "Создать пропуск": "green",
    "Управленческий контур": "blue",
    "Академический контур": "rose",
    "Контингент": "green",
    "Кафедры": "blue",
    "Диагностики МЦКО": "rose",
    "Пропуска и аналитика посещаемости": "green",
    "Основные реестры": "slate",
    "Контрольные работы": "rose",
    "Олимпиады": "rose",
    "Реестр приказов": "slate",
    "Классное руководство": "green",
    "Учебные годы": "slate",
    "Классы учебного года": "green",
    "Группы ДОУ учебного года": "green",
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
    "Доп. образование": "blue",
    "Задачи и поручения": "blue",
    "Обращения": "orange",
    "Ознакомления": "green",
    "Диск": "blue",
    "Социально-психологическая служба": "blue",
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
    if not icon:
        title = (row.get("title") or "").lower()
        for needle, rule_icon, rule_accent in ICON_RULES:
            if needle in title:
                icon, accent = rule_icon, rule_accent
                break
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
        "primary_sections": _materialize([
            {
                "title": "Управленческий контур",
                "description": "Сводная аналитика школы, ключевые показатели и проблемные зоны.",
                "endpoint": "hub.management",
                "roles_any": ["ADMIN", "METHODIST", "SOCIAL_PEDAGOG"],
            },
            {
                "title": "Академический контур",
                "description": "Учебная аналитика, контрольные работы и результаты классов.",
                "endpoint": "hub.academic",
                "permission_any": ["control_works_view"],
            },
            {
                "title": "Контингент",
                "description": "Реестры обучающихся, движение и сводная структура контингента.",
                "endpoint": "hub.contingent",
                "permission_any": ["contingent_view"],
            },
            {
                "title": "Инциденты",
                "description": "Реестр, аналитика, травмы и нарушения дисциплины.",
                "endpoint": "hub.incidents",
                "permission_any": ["incident_add", "incident_registry_view", "incident_dashboard_view"],
            },
        ]),
        "secondary_sections": _materialize([
            {
                "title": "Нагрузка и тарификация",
                "description": "Учебное планирование, распределение нагрузки и тарификация.",
                "endpoint": "workload.index",
                "visible_if": lambda: (
                    is_feature_enabled(WORKLOAD_MODULE)
                    and can_access_workload_module(current_user)
                ),
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
                "title": "Основные реестры",
                "description": "Ученики, движение, ОВЗ, ВШУ, КДН, АЗ и другие действующие реестры.",
                "endpoint": "hub.registries",
                "permission_any": ["children_registry_view", "registry_ovz_view", "registry_vshu_view", "registry_kdn_view", "registry_az_view"],
            },
            {
                "title": "Дошкольное отделение",
                "description": "Контингент ДОУ, группы, представители и детодни.",
                "endpoint": "preschool.index",
            },
            {
                "title": "Контрольные работы",
                "description": "Список работ, результаты, отчеты и сводные показатели.",
                "endpoint": "hub.control_works",
                "permission_any": ["control_works_view"],
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
                "roles_any": ["ADMIN", "DIRECTOR", "METHODIST", "SOCIAL_PEDAGOG"],
            },
            {
                "title": "Классное руководство",
                "description": "Социальный паспорт класса, список класса и аналитика класса.",
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
            {
                "title": "Обращения",
                "description": "Реестр обращений, ответственные, сроки и контроль исполнения.",
                "endpoint": "appeals.index",
            },
            {
                "title": "Ознакомления",
                "description": "Рассылка приказов и писем, подтверждение ознакомления, банк документов.",
                "endpoint": "familiarizations.index",
            },
            {
                "title": "Диск",
                "description": "Файлы, папки, создание и редактирование документов.",
                "endpoint": "drive.index",
            },
        ]),
        "admin_sections": _materialize([
            {"title": "Учебные годы", "endpoint": "children.academic_years_registry", "roles_any": ["ADMIN"]},
            {"title": "Классы учебного года", "endpoint": "children.classes_registry", "roles_any": ["ADMIN"]},
            {"title": "Группы ДОУ учебного года", "endpoint": "preschool.groups", "roles_any": ["ADMIN"]},
            {"title": "Реестр предметов", "endpoint": "children.subjects_registry", "roles_any": ["ADMIN"]},
            {"title": "Реестр олимпиадных предметов", "endpoint": "olympiads.settings", "roles_any": ["ADMIN"]},
            {"title": "Несопоставленные результаты олимпиад", "endpoint": "olympiads.unmatched", "roles_any": ["ADMIN"]},
            {"title": "Пользователи", "endpoint": "users.users_list", "roles_any": ["ADMIN"]},
            {"title": "Активность пользователей", "endpoint": "users.users_activity", "roles_any": ["ADMIN"]},
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
        "management": {
            "title": "Управленческий контур",
            "subtitle": "Сводный управленческий хаб для администрации и методической команды.",
            "roles_any": ["ADMIN", "METHODIST", "SOCIAL_PEDAGOG"],
            "summary_cards": _materialize([
                {"title": "Управленческий дашборд", "description": "Ключевые показатели школы", "endpoint": "management.dashboard"},
                {"title": "Контингент", "description": "Управленческий отчет по параллелям", "endpoint": "management.contingent_report"},
            ]),
            "quick_actions": _materialize([
                {"title": "Открыть управленческий дашборд", "endpoint": "management.dashboard"},
                {"title": "Отчет по контингенту", "endpoint": "management.contingent_report"},
            ]),
            "sections": _materialize([
                {"title": "Сводная аналитика школы", "description": "Основные показатели и индикаторы риска.", "endpoint": "management.dashboard"},
                {"title": "Аналитика олимпиад", "description": "Срезы по предметам, этапам и результатам.", "endpoint": "olympiads.analytics", "permission_any": ["olympiad_view", "olympiad_dashboard_view"]},
                {"title": "Аналитика МЦКО", "description": "Диагностики, уровни и результаты по школе.", "endpoint": "diagnostics.analytics"},
                {"title": "Аналитика контрольных работ", "description": "Сводные данные по учебным работам.", "endpoint": "control_works.control_works_summary", "permission_any": ["control_works_view"]},
                {"title": "Аналитика пропусков", "description": "Посещаемость, опоздания и рейтинг классов.", "endpoint": "attendance.analytics", "roles_any": ["ADMIN", "CLASS_TEACHER"]},
                {"title": "Проблемные зоны", "description": "Низкие результаты и группы риска.", "endpoint": "academic.low_results", "permission_any": ["control_works_view"]},
            ]),
        },
        "academic": {
            "title": "Академический контур",
            "subtitle": "Учебный блок: успеваемость, контрольные работы и аналитика по классам.",
            "permission_any": ["control_works_view"],
            "quick_actions": _materialize([
                {"title": "Список контрольных работ", "endpoint": "control_works.list_control_works", "permission_any": ["control_works_edit"]},
                {"title": "Мои контрольные работы", "endpoint": "control_works.my_control_works", "permission_any": ["control_works_view"]},
                {"title": "Академический дашборд", "endpoint": "academic.dashboard", "permission_any": ["control_works_view"]},
            ]),
            "sections": _materialize([
                {"title": "Академическая аналитика", "description": "Общая учебная картина и качество знаний.", "endpoint": "academic.dashboard"},
                {"title": "Успеваемость и динамика", "description": "Отслеживание результатов и динамики.", "endpoint": "academic.dynamics_view"},
                {"title": "Аналитика по классам", "description": "Классовые срезы и проблемные группы.", "endpoint": "academic.low_results"},
                {"title": "Контрольные работы", "description": "Список работ, карточки и результаты.", "endpoint": "control_works.list_control_works", "permission_any": ["control_works_edit"]},
                {"title": "Учебные отчеты", "description": "Сводные отчеты по контрольным работам.", "endpoint": "control_works.control_works_summary", "permission_any": ["control_works_view"]},
            ]),
        },
        "contingent": {
            "title": "Контингент",
            "subtitle": "Реестры обучающихся, движение и состав контингента школы.",
            "permission_any": ["contingent_view"],
            "quick_actions": _materialize([
                {"title": "Сводный контингент", "endpoint": "children.contingent", "permission_any": ["contingent_view"]},
                {"title": "Дошкольное отделение", "endpoint": "preschool.index", "permission_any": ["contingent_view"]},
                {"title": "Ученики", "endpoint": "children.list_children", "permission_any": ["children_registry_view"]},
                {"title": "Добавить ученика", "endpoint": "children.new_child", "roles_any": ["ADMIN", "SECRETARY_ACADEMIC", "SOCIAL_PEDAGOG"]},
            ]),
            "sections": _materialize([
                {"title": "Сводный контингент", "description": "Основная аналитика по составу обучающихся.", "endpoint": "children.contingent"},
                {"title": "Дошкольное отделение", "description": "Контингент ДОУ, группы, представители и детодни.", "endpoint": "preschool.index"},
                {"title": "Реестр контингента", "description": "Общий список детей по школе.", "endpoint": "children.list_children", "permission_any": ["children_registry_view"]},
                {"title": "Добавить ученика", "description": "Карточка зачисления нового ученика.", "endpoint": "children.new_child", "roles_any": ["ADMIN", "SECRETARY_ACADEMIC", "SOCIAL_PEDAGOG"]},
                {"title": "Зачисленные", "description": "Отдельный реестр прибывших детей.", "endpoint": "children.registry_enrolled", "permission_any": ["registry_enrolled_view"]},
                {"title": "Отчисленные", "description": "Реестр выбывших детей.", "endpoint": "children.registry_expelled", "permission_any": ["registry_expelled_view"]},
                {"title": "Движение контингента", "description": "Переводы между классами и архивом.", "endpoint": "transfers.index", "roles_any": ["ADMIN", "SECRETARY_ACADEMIC"]},
            ]),
        },
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
                {"title": "Реестр инцидентов", "description": "Полный журнал инцидентов.", "endpoint": "children.incidents_registry", "permission_any": ["incident_registry_view"]},
                {"title": "Травмы", "description": "Контроль случаев травмирования.", "endpoint": "children.incidents_registry", "permission_any": ["incident_registry_view"]},
                {"title": "Вызов скорой", "description": "Случаи вызова скорой помощи.", "endpoint": "children.incidents_registry", "permission_any": ["incident_registry_view"]},
                {"title": "Нарушения дисциплины", "description": "Дисциплинарные инциденты и их анализ.", "endpoint": "children.incidents_registry", "permission_any": ["incident_registry_view"]},
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
                {"title": "Список диагностик", "description": "Сессии и карточки диагностик.", "endpoint": "diagnostics.index"},
                {"title": "Импорт результатов", "description": "Загрузка новых пакетов результатов.", "endpoint": "diagnostics.imports_registry"},
                {"title": "Аналитика диагностик", "description": "Темы, уровни и результаты.", "endpoint": "diagnostics.analytics"},
                {"title": "Привязка к учителям", "description": "Связь результатов с педагогами.", "endpoint": "diagnostics.teacher_binding"},
                {"title": "Сводки", "description": "Итоги по сессиям диагностики.", "endpoint": "diagnostics.index"},
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
                {"title": "Аналитика посещаемости", "description": "Посещаемость, опоздания и рейтинг классов.", "endpoint": "attendance.analytics"},
                {"title": "Импорт", "description": "Загрузка отчетов по посещаемости.", "endpoint": "attendance.import_view", "roles_any": ["ADMIN"]},
                {"title": "Начало занятий", "description": "Настройка времени начала занятий по параллелям.", "endpoint": "attendance.schedule_rules", "roles_any": ["ADMIN"]},
                {"title": "KPI посещаемости", "description": "Управленческая сводка по посещаемости.", "endpoint": "attendance.analytics"},
            ]),
        },
        "registries": {
            "title": "Основные реестры",
            "subtitle": "Все ключевые реестры системы, сгруппированные в одном тематическом разделе.",
            "sections": _materialize([
                {"title": "Ученики", "description": "Основной реестр детей по школе.", "endpoint": "children.list_children", "permission_any": ["children_registry_view"]},
                {"title": "Добавить ученика", "description": "Карточка зачисления нового ученика.", "endpoint": "children.new_child", "roles_any": ["ADMIN", "SECRETARY_ACADEMIC", "SOCIAL_PEDAGOG"]},
                {"title": "Движение", "description": "Переводы, переходы и архивирование.", "endpoint": "transfers.index", "roles_any": ["ADMIN"]},
                {"title": "Реестр ОВЗ", "description": "Дети со статусом ОВЗ.", "endpoint": "children.registry_ovz", "permission_any": ["registry_ovz_view"]},
                {"title": "Реестр ВШУ", "description": "Дети на внутришкольном учете.", "endpoint": "children.registry_vshu", "permission_any": ["registry_vshu_view"]},
                {"title": "Реестр КДН", "description": "Дети по линии КДН.", "endpoint": "children.registry_kdn", "permission_any": ["registry_kdn_view"]},
                {"title": "Реестр АЗ", "description": "Академическая задолженность и риски.", "endpoint": "children.registry_az", "permission_any": ["registry_az_view"]},
                {"title": "Реестр инцидентов", "description": "Журнал инцидентов как отдельный реестр.", "endpoint": "children.incidents_registry", "permission_any": ["incident_registry_view"]},
                {"title": "Зачисленные", "description": "Реестр зачисленных детей.", "endpoint": "children.registry_enrolled", "permission_any": ["registry_enrolled_view"]},
                {"title": "Отчисленные", "description": "Реестр отчисленных детей.", "endpoint": "children.registry_expelled", "permission_any": ["registry_expelled_view"]},
            ]),
        },
        "control_works": {
            "title": "Контрольные работы",
            "subtitle": "Учебные работы, результаты, отчеты и сводные показатели.",
            "permission_any": ["control_works_view"],
            "sections": _materialize([
                {"title": "Список контрольных", "description": "Реестр контрольных работ.", "endpoint": "control_works.list_control_works", "permission_any": ["control_works_edit"]},
                {"title": "Мои контрольные", "description": "Работы, назначенные текущему учителю.", "endpoint": "control_works.my_control_works", "permission_any": ["control_works_view"]},
                {"title": "Импорт результатов", "description": "Ввод и редактирование результатов внутри карточек работ.", "endpoint": "control_works.list_control_works", "permission_any": ["control_works_edit"]},
                {"title": "Аналитика", "description": "Общий учебный дашборд.", "endpoint": "academic.dashboard"},
                {"title": "Отчеты", "description": "Отчеты и сводные таблицы.", "endpoint": "control_works.control_works_summary"},
                {"title": "Сводные показатели", "description": "Итоги по годам, предметам и классам.", "endpoint": "control_works.control_works_summary"},
            ]),
        },
        "olympiads": {
            "title": "Олимпиады",
            "subtitle": "Олимпиадное движение, импорт результатов, сводки и аналитика.",
            "permission_any": ["olympiad_view", "olympiad_import", "olympiad_dashboard_view"],
            "sections": _materialize([
                {"title": "Перечень олимпиад", "description": "Основной реестр результатов олимпиад.", "endpoint": "olympiads.registry", "permission_any": ["olympiad_view"]},
                {"title": "Импорт результатов", "description": "Загрузка новых файлов и просмотр импортов.", "endpoint": "olympiads.import_view", "permission_any": ["olympiad_import"]},
                {"title": "Реестр олимпиадников", "description": "Участники, победители и призеры.", "endpoint": "olympiads.registry", "permission_any": ["olympiad_view"]},
                {"title": "Аналитика", "description": "Срезы по предметам, учителям и этапам.", "endpoint": "olympiads.analytics", "permission_any": ["olympiad_view", "olympiad_dashboard_view"]},
                {"title": "Массовая привязка по классу и предмету", "description": "После импорта можно назначать одного учителя сразу на класс и предмет.", "endpoint": "olympiads.teacher_binding", "permission_any": ["olympiad_edit"]},
                {"title": "Связь с кафедрами и учителями", "description": "Привязка результатов к педагогам и подразделениям.", "endpoint": "olympiads.department_registry", "permission_any": ["olympiad_department_summary_view"]},
            ]),
        },
        "orders": {
            "title": "Реестр приказов",
            "subtitle": "Журнал приказов, создание, шаблоны и архивное хранение.",
            "roles_any": ["ADMIN", "DIRECTOR", "METHODIST", "SOCIAL_PEDAGOG"],
            "sections": _materialize([
                {"title": "Журнал приказов", "description": "Список всех приказов.", "endpoint": "orders.registry"},
                {"title": "Создание приказов", "description": "Оформление нового приказа.", "endpoint": "orders.create"},
                {"title": "Ответственные", "description": "Настройка ответственных за направления приказов.", "endpoint": "orders.responsibles"},
                {"title": "Входящие документы", "description": "Регистрация входящих писем и документов.", "endpoint": "document_registers.registry", "endpoint_kwargs": {"registry_type": "incoming"}},
                {"title": "Исходящие документы", "description": "Регистрация исходящих писем и документов.", "endpoint": "document_registers.registry", "endpoint_kwargs": {"registry_type": "outgoing"}},
                {"title": "Доступ к документам", "description": "Права просмотра и ведения реестров документов.", "endpoint": "document_registers.access", "roles_any": ["ADMIN", "DIRECTOR"]},
            ]),
        },
        "classroom": {
            "title": "Классное руководство",
            "subtitle": "Социальный паспорт, список класса, результаты и события по классу.",
            "roles_any": ["ADMIN", "CLASS_TEACHER", "METHODIST", "SOCIAL_PEDAGOG"],
            "sections": _materialize([
                {"title": "Социальный паспорт класса", "description": "Реестр и статусы по классам.", "endpoint": "children.social_passport_registry", "permission_any": ["social_passport_registry_view"]},
                {"title": "Сопровождение класса", "description": "Работа с сопровождением и наблюдением класса.", "endpoint": "children.social_passport_dashboard", "permission_any": ["social_passport_dashboard_view"]},
                {"title": "Список класса", "description": "Переход к списку учеников своего класса или всей школы.", "endpoint": "children.list_children", "permission_any": ["children_registry_view"]},
                {"title": "Результаты класса", "description": "Учебные результаты и контрольные работы.", "endpoint": "academic.dashboard", "permission_any": ["control_works_view"]},
                {"title": "Аналитика успеваемости класса", "description": "Низкие результаты и динамика.", "endpoint": "academic.low_results", "permission_any": ["control_works_view"]},
                {"title": "Ключевые показатели класса", "description": "Социальные и академические индикаторы.", "endpoint": "children.social_passport_dashboard", "permission_any": ["social_passport_dashboard_view"]},
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


@hub_bp.route("/management")
@login_required
def management():
    return render_template("hub/theme_page.html", theme=_theme_or_403("management"))


@hub_bp.route("/academic")
@login_required
def academic():
    return render_template("hub/theme_page.html", theme=_theme_or_403("academic"))


@hub_bp.route("/contingent")
@login_required
def contingent():
    return render_template("hub/theme_page.html", theme=_theme_or_403("contingent"))


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


@hub_bp.route("/registries")
@login_required
def registries():
    return render_template("hub/theme_page.html", theme=_theme_or_403("registries"))


@hub_bp.route("/control-works")
@login_required
def control_works():
    return render_template("hub/theme_page.html", theme=_theme_or_403("control_works"))


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



def _read_module_codes(role_code):
    """Возвращает коды модулей, разрешённых для роли в настройке ролей."""
    if not role_code:
        return None

    try:
        from app.models.role_access import RoleModuleAccess

        rows = RoleModuleAccess.query.filter_by(
            role_code=role_code,
            is_visible=True,
            is_enabled=True,
        ).all()

        return {r.module_code for r in rows}
    except Exception:
        return None


def _filter_page_sections_by_modules(page, module_codes):
    """Фильтрует карточки тематических разделов по настройке «Модули и разделы»."""
    if not module_codes:
        return page

    endpoint_to_module = {
        "hub.departments": "departments",
        "hub.diagnostics": "diagnostics",
        "hub.attendance": "attendance",
        "hub.registries": "registries",
        "preschool.index": "preschool",
        "hub.control_works": "control_works",
        "hub.olympiads": "olympiads",
        "hub.orders": "orders",
        "hub.class_guidance": "class_guidance",
        "hub.service_staff": "service_staff",
        "tasks.my_tasks": "tasks",
        "school_plan.index": "school_plan",
        "knowledge_base.index": "knowledge_base",
        "drive.index": "drive",
        "familiarizations.index": "familiarizations",
        "familiarizations.my": "familiarizations",
        "appeals.index": "appeals",
        "workload.index": "workload",
    }

    def keep(item):
        endpoint = item.get("endpoint")
        module_key = endpoint_to_module.get(endpoint)
        if not module_key:
            return True
        if module_key == "workload":
            return (
                is_feature_enabled(WORKLOAD_MODULE)
                and can_access_workload_module(current_user)
            )
        return module_key in module_codes

    for key in ("primary_sections", "secondary_sections", "admin_sections"):
        if key in page and page[key]:
            page[key] = [item for item in page[key] if keep(item)]

    return page



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
    role_module_codes = _read_module_codes(lookup_role) if lookup_role else None

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
    page = _filter_page_sections_by_modules(page, role_module_codes)

    if preview_role:
        g._hub_preview_role_codes = None

    # Для ADMIN/DEPUTY_DIRECTOR плитка «Мои заявки» превращается
    # в «Инциденты» — открывается та же страница, но видом admin-view
    # (3 вкладки: Входящие / В работе / Завершённые)
    if preview_role:
        _is_admin_like = preview_role in ("ADMIN", "DEPUTY_DIRECTOR")
        _is_social = preview_role == "SOCIAL_PEDAGOG"
    else:
        _is_admin_like = _is_admin() or has_role("DEPUTY_DIRECTOR")
        _is_social = has_role("SOCIAL_PEDAGOG") and not _is_admin_like
    if _is_admin_like or _is_social:
        for action in page.get("quick_actions") or []:
            if action.get("endpoint") == "children.incidents_my":
                action["title"] = "Работа с инцидентами"
                if _is_social:
                    action["description"] = "Назначенные мне: входящие, в работе, завершённые."
                else:
                    action["description"] = "Входящие, в работе и завершённые."

    return {
        "page": page,
        "quick_summary": _summary_cards() if show_summary else [],
        "show_quick_summary": show_summary,
        "show_admin_block": (has_role("ADMIN") or has_role("DIRECTOR")) and not preview_role,
        "class_teacher_class": class_teacher_class,
        "is_class_teacher": is_ct,
        "role_block_codes": role_block_codes,
        "role_module_codes": role_module_codes,
        "preview_role": preview_role,
        "preview_role_label": _ROLE_LABELS.get(preview_role, preview_role) if preview_role else None,
    }
