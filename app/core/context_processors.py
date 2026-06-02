from flask import current_app, url_for
from flask_login import current_user
from urllib.parse import urlencode

from app.services.org_settings_service import get_active_organization_settings

def register_context_processors(app, has_permission, build_menu_flags):
    @app.context_processor
    def inject_permissions():
        def can(permission_code: str):
            return has_permission(permission_code)
        return {"can": can, **build_menu_flags()}

    @app.context_processor
    def inject_helpers():
        def endpoint_exists(endpoint_name: str) -> bool:
            return endpoint_name in current_app.view_functions
        try:
            from app.children import _category_label as _cat_lbl
            cat_label = _cat_lbl
        except Exception:
            cat_label = lambda v: (v or "—")
        return dict(endpoint_exists=endpoint_exists, incident_category_label=cat_label)

    @app.context_processor
    def inject_datalens():
        try:
            from app.datalens import dashboard_full_url
            from app.kubok import get_rating
            return dict(
                kubok_rating=get_rating,
                datalens_dashboard_url=dashboard_full_url(),
            )
        except Exception:
            return dict(
                kubok_rating=lambda _name=None: None,
                datalens_dashboard_url="",
            )

    @app.context_processor
    def inject_organization_settings():
        settings = get_active_organization_settings()
        default_system_name = "Система сопровождения обучающихся"
        org_name = getattr(settings, 'display_name', None) or getattr(settings, 'short_name', None) or getattr(settings, 'full_name', None) or "Образовательная организация"
        org_full_name = getattr(settings, 'full_name', None) or org_name

        def media_url(relative_path, fallback_static=None):
            if relative_path:
                filename = str(relative_path).split('organization/', 1)[-1]
                return url_for('organization_settings.uploaded_media', filename=filename)
            if fallback_static:
                return url_for('static', filename=fallback_static)
            return None

        return dict(
            org_settings=settings,
            org_name=org_name,
            org_short_name=getattr(settings, 'short_name', None) or org_name,
            org_full_name=org_full_name,
            org_logo_url=media_url(getattr(settings, 'logo_path', None), 'images/logo547.png'),
            org_emblem_url=media_url(getattr(settings, 'emblem_path', None)),
            app_system_name=default_system_name,
            app_display_title=f"{default_system_name} — {org_name}",
        )

    @app.context_processor
    def inject_task_notifications():
        empty = dict(
            task_unread_notifications=0,
            task_latest_notifications=[],
            incident_unread_notifications=0,
            incident_latest_notifications=[],
            bell_unread_total=0,
        )
        if not getattr(current_user, 'is_authenticated', False):
            return empty
        task_unread, task_latest = 0, []
        inc_unread, inc_latest = 0, []
        try:
            from app.models import TaskNotification
            task_unread = TaskNotification.query.filter_by(user_id=current_user.id, is_read=False).count()
            task_latest = TaskNotification.query.filter_by(user_id=current_user.id).order_by(TaskNotification.created_at.desc()).limit(10).all()
        except Exception:
            pass
        try:
            from app.models_legacy import IncidentNotification
            inc_unread = IncidentNotification.query.filter_by(user_id=current_user.id, is_read=False).count()
            inc_latest = IncidentNotification.query.filter_by(user_id=current_user.id).order_by(IncidentNotification.created_at.desc()).limit(10).all()
        except Exception:
            pass
        return dict(
            task_unread_notifications=task_unread,
            task_latest_notifications=task_latest,
            incident_unread_notifications=inc_unread,
            incident_latest_notifications=inc_latest,
            bell_unread_total=task_unread + inc_unread,
        )

    @app.context_processor
    def inject_auto_breadcrumbs():
        """Автоматические хлебные крошки по endpoint текущего запроса."""
        from flask import request
        try:
            endpoint = request.endpoint or ''
        except RuntimeError:
            return dict(auto_breadcrumbs=[])

        HOME = ('Главная', 'main.dashboard')

        # endpoint → [(Название, endpoint_or_None), ...]
        MAP = {
            # Инциденты
            'children.incidents_my':       [HOME, ('Мои заявки', None)],
            'children.incident_new':       [HOME, ('Мои заявки', 'children.incidents_my'), ('Новый инцидент', None)],
            'children.incident_edit':      [HOME, ('Мои заявки', 'children.incidents_my'), ('Редактировать', None)],
            'children.incidents_registry': [HOME, ('Реестр инцидентов', None)],
            'children.incidents_dashboard':[HOME, ('Дашборд инцидентов', None)],
            # Дети
            'children.list_children':      [HOME, ('Список учеников', None)],
            'children.child_card':         [HOME, ('Список учеников', 'children.list_children'), ('Карточка ученика', None)],
            'children.new_child':          [HOME, ('Список учеников', 'children.list_children'), ('Новый ученик', None)],
            'children.children_import':    [HOME, ('Список учеников', 'children.list_children'), ('Импорт детей', None)],
            'children.parents_import':     [HOME, ('Список учеников', 'children.list_children'), ('Импорт родителей', None)],
            # Классы и контингент
            'children.classes_registry':   [HOME, ('Классы', None)],
            'children.class_detail':       [HOME, ('Классы', 'children.classes_registry'), ('Класс', None)],
            'children.contingent':         [HOME, ('Контингент', None)],
            'children.list_contingent':    [HOME, ('Контингент', None)],
            'children.movements_registry': [HOME, ('Движение контингента', None)],
            'children.comments_registry':  [HOME, ('Комментарии', None)],
            'children.social_passport_dashboard': [HOME, ('Социальные паспорта', None)],
            'children.social_passport_registry':  [HOME, ('Социальные паспорта', None)],
            # Пропуска
            'children.attendance_passes':  [HOME, ('Пропуска', None)],
            'children.attendance_pass_new':[HOME, ('Пропуска', 'children.attendance_passes'), ('Новый пропуск', None)],
            'children.attendance_kpp':     [HOME, ('КПП', None)],
            'children.attendance_analytics':[HOME, ('Аналитика пропусков', None)],
            # Задачи
            'tasks.my_tasks':              [HOME, ('Задачи', None)],
            'tasks.index':                 [HOME, ('Задачи', None)],
            'tasks.new_task':              [HOME, ('Задачи', 'tasks.my_tasks'), ('Новая задача', None)],
            'tasks.created_by_me':         [HOME, ('Задачи', 'tasks.my_tasks'), ('Мои поручения', None)],
            'tasks.overdue_tasks':         [HOME, ('Задачи', 'tasks.my_tasks'), ('Просроченные', None)],
            'tasks.archive_tasks':         [HOME, ('Задачи', 'tasks.my_tasks'), ('Архив', None)],
            'tasks.notifications':         [HOME, ('Задачи', 'tasks.my_tasks'), ('Уведомления', None)],
            'tasks.task_notification_settings': [HOME, ('Задачи', 'tasks.my_tasks'), ('Настройки', None)],
            'tasks.templates_list':        [HOME, ('Задачи', 'tasks.my_tasks'), ('Шаблоны', None)],
            # Пользователи и роли
            'children.users_list':         [HOME, ('Пользователи', None)],
            'users.users_list':            [HOME, ('Пользователи', None)],
            'users.users_activity':        [HOME, ('Активность пользователей', None)],
            'users.users_paths':           [HOME, ('Журнал переходов', None)],
            # Профиль
            'auth.profile_settings':              [HOME, ('Профиль', None), ('Настройки', None)],
            'auth.profile_notifications':         [HOME, ('Профиль', None), ('Уведомления', None)],
            'auth.profile_settings_notifications':[HOME, ('Профиль', None), ('Уведомления', None)],
            # Хаб (темы)
            'hub.incidents':               [HOME, ('Инциденты', None)],
            'hub.classroom':               [HOME, ('Сопровождение учеников', None)],
            'hub.contingent':              [HOME, ('Контингент', None)],
            'hub.registries':              [HOME, ('Основные реестры', None)],
            'hub.management':              [HOME, ('Управленческий контур', None)],
            'hub.academic':                [HOME, ('Академические показатели', None)],
            'hub.control_works':           [HOME, ('Контрольные работы', None)],
            'hub.olympiads':               [HOME, ('Олимпиады', None)],
            'hub.attendance':              [HOME, ('Пропуска', None)],
            'hub.diagnostics':             [HOME, ('Диагностика МЦКО', None)],
            'hub.departments':             [HOME, ('Кафедры', None)],
            'hub.orders':                  [HOME, ('Реестр приказов', None)],
            'hub.admin':                   [HOME, ('Администрирование', None)],
            'children.user_edit':          [HOME, ('Пользователи', 'children.users_list'), ('Редактировать', None)],
            'children.user_new':           [HOME, ('Пользователи', 'children.users_list'), ('Новый', None)],
            'children.roles_admin':        [HOME, ('Управление ролями', None)],
            # Администрирование
            'role_access_admin.settings':  [HOME, ('Настройка ролей', None)],
            'children.system_logs':        [HOME, ('Системные логи', None)],
            'organization_settings.settings_form': [HOME, ('Настройки организации', None)],
            # Олимпиады (blueprint: olympiads)
            'olympiads.registry':          [HOME, ('Олимпиады', None)],
            'olympiads.import_view':       [HOME, ('Олимпиады', 'olympiads.registry'), ('Импорт', None)],
            'olympiads.imports':           [HOME, ('Олимпиады', 'olympiads.registry'), ('История импортов', None)],
            'olympiads.department_registry': [HOME, ('Олимпиады', 'olympiads.registry'), ('По кафедрам', None)],
            # Кафедры
            'departments.index':           [HOME, ('Кафедры', None)],
            'departments.settings':        [HOME, ('Кафедры', 'departments.index'), ('Настройка', None)],
            'departments.loads':           [HOME, ('Кафедры', 'departments.index'), ('Нагрузка', None)],
            'departments.summary':         [HOME, ('Кафедры', 'departments.index'), ('Сводка', None)],
            # Диагностика
            'diagnostics.list':            [HOME, ('Диагностика МЦКО', None)],
            'diagnostics.create':          [HOME, ('Диагностика МЦКО', 'diagnostics.list'), ('Новая', None)],
            'diagnostics.detail':          [HOME, ('Диагностика МЦКО', 'diagnostics.list'), ('Карточка', None)],
            'diagnostics.edit':            [HOME, ('Диагностика МЦКО', 'diagnostics.list'), ('Редактировать', None)],
            'diagnostics.import_results':  [HOME, ('Диагностика МЦКО', 'diagnostics.list'), ('Импорт', None)],
            'diagnostics.preview':         [HOME, ('Диагностика МЦКО', 'diagnostics.list'), ('Предпросмотр', None)],
            'diagnostics.report':          [HOME, ('Диагностика МЦКО', 'diagnostics.list'), ('Отчёт', None)],
            'diagnostics.imports':         [HOME, ('Диагностика МЦКО', 'diagnostics.list'), ('История импортов', None)],
            'diagnostics.analytics':       [HOME, ('Диагностика МЦКО', 'diagnostics.list'), ('Аналитика', None)],
            'diagnostics.departments_summary': [HOME, ('Диагностика МЦКО', 'diagnostics.list'), ('По кафедрам', None)],
            'diagnostics.teacher_binding': [HOME, ('Диагностика МЦКО', 'diagnostics.list'), ('Привязка учителей', None)],
            # Соц-псих сопровождение
            'service_staff.index':         [HOME, ('Соц-псих служба', None)],
            'service_staff.registry':      [HOME, ('Соц-псих служба', 'service_staff.index'), ('Реестр', None)],
            'service_staff.assignments_registry': [HOME, ('Соц-псих служба', 'service_staff.index'), ('Поручения', None)],
            'service_staff.new_assignment': [HOME, ('Соц-псих служба', 'service_staff.index'), ('Поручения', 'service_staff.assignments_registry'), ('Новое', None)],
            'service_staff.edit_assignment': [HOME, ('Соц-псих служба', 'service_staff.index'), ('Поручения', 'service_staff.assignments_registry'), ('Редактировать', None)],
            'service_staff.card':          [HOME, ('Соц-псих служба', 'service_staff.index'), ('Карточка специалиста', None)],
            'service_staff.cyclegrams_registry': [HOME, ('Соц-псих служба', 'service_staff.index'), ('Циклограммы', None)],
            'service_staff.cyclegram_card': [HOME, ('Соц-псих служба', 'service_staff.index'), ('Циклограммы', 'service_staff.cyclegrams_registry'), ('Карточка', None)],
            'service_staff.analytics_dashboard': [HOME, ('Соц-псих служба', 'service_staff.index'), ('Аналитика', None)],
            'service_staff.structure':     [HOME, ('Соц-псих служба', 'service_staff.index'), ('Структура', None)],
            'service_staff.buildings':     [HOME, ('Соц-псих служба', 'service_staff.index'), ('Здания', None)],
            'service_staff.norms_registry': [HOME, ('Соц-псих служба', 'service_staff.index'), ('Нормы', None)],
            'service_staff.presentations_registry': [HOME, ('Соц-псих служба', 'service_staff.index'), ('Представления', None)],
            # Контрольные работы
            'control_works.list':          [HOME, ('Контрольные работы', None)],
            'control_works.detail':        [HOME, ('Контрольные работы', 'control_works.list'), ('Работа', None)],
            'control_works.form':          [HOME, ('Контрольные работы', 'control_works.list'), ('Форма', None)],
            'control_works.results':       [HOME, ('Контрольные работы', 'control_works.list'), ('Результаты', None)],
            'control_works.registry':      [HOME, ('Контрольные работы', 'control_works.list'), ('Реестр', None)],
            'control_works.report':        [HOME, ('Контрольные работы', 'control_works.list'), ('Отчёт', None)],
            'control_works.class_report':  [HOME, ('Контрольные работы', 'control_works.list'), ('Отчёт по классу', None)],
            'control_works.journal':       [HOME, ('Контрольные работы', 'control_works.list'), ('Журнал', None)],
            'control_works.summary':       [HOME, ('Контрольные работы', 'control_works.list'), ('Сводка', None)],
            'control_works.archive':       [HOME, ('Контрольные работы', 'control_works.list'), ('Архив', None)],
            # Приказы
            'orders.registry':             [HOME, ('Приказы', None)],
            'orders.create':               [HOME, ('Приказы', 'orders.registry'), ('Новый приказ', None)],
            'orders.edit':                 [HOME, ('Приказы', 'orders.registry'), ('Редактировать', None)],
            'orders.responsibles':         [HOME, ('Приказы', 'orders.registry'), ('Ответственные', None)],
            # Переводы
            'transfers.index':             [HOME, ('Переводы', None)],
            'transfers.archive':           [HOME, ('Переводы', 'transfers.index'), ('Архив', None)],
            # Академическая успеваемость
            'academic.dashboard':          [HOME, ('Успеваемость', None)],
            'academic.dynamics':           [HOME, ('Успеваемость', 'academic.dashboard'), ('Динамика', None)],
            'academic.low_results':        [HOME, ('Успеваемость', 'academic.dashboard'), ('Неуспевающие', None)],
            # Аналитика
            'analytics.dashboard':         [HOME, ('Аналитика', None)],
            # Управление
            'management.dashboard':        [HOME, ('Управление', None)],
            'management.contingent_report':[HOME, ('Управление', 'management.dashboard'), ('Контингент', None)],
            # ИОМ
            'iom.registry':                [HOME, ('ИОМ', None)],
            'iom.create_card':             [HOME, ('ИОМ', 'iom.registry'), ('Новая карточка', None)],
            'iom.card_view':               [HOME, ('ИОМ', 'iom.registry'), ('Карточка', None)],
            'iom.edit_card':               [HOME, ('ИОМ', 'iom.registry'), ('Редактировать', None)],
            # План работы школы
            'school_plan.index':           [HOME, ('План работы школы', None)],
            'school_plan.week_view':       [HOME, ('План работы школы', 'school_plan.index'), ('Неделя', None)],
            'school_plan.month_view':      [HOME, ('План работы школы', 'school_plan.index'), ('Месяц', None)],
            'school_plan.create':          [HOME, ('План работы школы', 'school_plan.index'), ('Новое мероприятие', None)],
            'school_plan.view':            [HOME, ('План работы школы', 'school_plan.index'), ('Мероприятие', None)],
            'school_plan.edit':            [HOME, ('План работы школы', 'school_plan.index'), ('Редактировать', None)],
        }

        # Fallback: если endpoint не в MAP — показываем [Главная] > [Раздел] по имени blueprint
        BLUEPRINT_SECTIONS = {
            'departments':         ('Кафедры',              'departments.index'),
            'orders':              ('Приказы',              'orders.registry'),
            'olympiads':           ('Олимпиады',            'olympiads.registry'),
            'diagnostics':         ('Диагностика МЦКО',     'diagnostics.list'),
            'service_staff':       ('Соц-псих служба',      'service_staff.index'),
            'control_works':       ('Контрольные работы',   'control_works.list'),
            'transfers':           ('Переводы',             'transfers.index'),
            'academic':            ('Успеваемость',         'academic.dashboard'),
            'analytics':           ('Аналитика',            'analytics.dashboard'),
            'management':          ('Управление',           'management.dashboard'),
            'tasks':               ('Задачи',               'tasks.my_tasks'),
            'iom':                 ('ИОМ',                  'iom.registry'),
            'school_plan':         ('План работы школы',    'school_plan.index'),
            'role_access_admin':   ('Настройка ролей',      'role_access_admin.settings'),
            'organization_settings': ('Настройки организации', 'organization_settings.settings_form'),
        }

        crumbs_def = MAP.get(endpoint)
        if not crumbs_def:
            blueprint = endpoint.split('.')[0] if '.' in endpoint else ''
            section = BLUEPRINT_SECTIONS.get(blueprint)
            if section:
                section_label, section_ep = section
                # Если мы на родительской странице самого раздела
                if endpoint == section_ep:
                    crumbs_def = [HOME, (section_label, None)]
                else:
                    crumbs_def = [HOME, (section_label, section_ep)]
            else:
                return dict(auto_breadcrumbs=[])

        result = []
        for label, ep in crumbs_def:
            link = None
            if ep is not None:
                try:
                    link = url_for(ep)
                except Exception:
                    link = None
            result.append({'label': label, 'url': link})

        return dict(auto_breadcrumbs=result)

    @app.template_filter("replace_query")
    def replace_query(args, **updates):
        data = dict(args.items()) if hasattr(args, "items") else dict(args)
        for key, value in updates.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        return urlencode(data)

    @app.template_filter("format_minutes_hm")
    def format_minutes_hm(value):
        try:
            total = int(value or 0)
        except (TypeError, ValueError):
            return '0 ч 00 мин'
        hours = total // 60
        minutes = total % 60
        if hours:
            return f'{hours} ч {minutes:02d} мин'
        return f'{minutes} мин'



def build_dashboard_role_context(user):
    try:
        from app.services.role_access_service import (
            get_visible_dashboard_blocks_for_role,
            get_visible_quick_links_for_role,
        )
    except Exception:
        return {
            "role_dashboard_blocks": [],
            "role_quick_links": [],
            "role_block_codes": set(),
            "role_quick_link_codes": set(),
        }

    role_code = getattr(user, "role", None) if user else None
    blocks = get_visible_dashboard_blocks_for_role(role_code)
    quick_links = get_visible_quick_links_for_role(role_code)

    block_codes = {getattr(item, "block_code", None) for item in blocks if getattr(item, "block_code", None)}
    quick_codes = {getattr(item, "quick_link_code", None) for item in quick_links if getattr(item, "quick_link_code", None)}

    return {
        "role_dashboard_blocks": blocks,
        "role_quick_links": quick_links,
        "role_block_codes": block_codes,
        "role_quick_link_codes": quick_codes,
    }
