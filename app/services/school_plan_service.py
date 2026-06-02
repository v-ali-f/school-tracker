from app.core.extensions import db
from app.models import SchoolPlanCategory, SchoolPlanDirection


DEFAULT_DIRECTIONS = [
    ('study', 'Учебная часть', '#2563eb', '#ffffff', 10),
    ('upbringing', 'Воспитательная работа', '#16a34a', '#ffffff', 20),
    ('control', 'Контрольные работы', '#f59e0b', '#111827', 30),
    ('mcko', 'МЦКО', '#9f1239', '#ffffff', 40),
    ('diagnostics', 'Диагностики', '#7c3aed', '#ffffff', 50),
    ('exams', 'Экзамены', '#dc2626', '#ffffff', 60),
    ('olympiads', 'Олимпиады', '#0f766e', '#ffffff', 70),
    ('methodical', 'Методическая работа', '#475569', '#ffffff', 80),
    ('parents', 'Работа с родителями', '#0ea5e9', '#ffffff', 90),
    ('admin', 'Административные мероприятия', '#334155', '#ffffff', 100),
]

DEFAULT_CATEGORIES = [
    ('control_work', 'Контрольная работа', '#f59e0b', '#111827', 10),
    ('diagnostic', 'Диагностика', '#7c3aed', '#ffffff', 20),
    ('ped_council', 'Педсовет', '#1d4ed8', '#ffffff', 30),
    ('meeting', 'Совещание', '#eab308', '#111827', 40),
    ('class_hour', 'Классный час', '#16a34a', '#ffffff', 50),
    ('monitoring', 'Мониторинг', '#0f766e', '#ffffff', 60),
    ('olympiad', 'Олимпиада', '#0f766e', '#ffffff', 70),
    ('exam', 'Экзамен', '#dc2626', '#ffffff', 80),
    ('event', 'Мероприятие', '#2563eb', '#ffffff', 90),
]


def ensure_school_plan_seed_data():
    changed = False
    for code, name, color, text_color, sort_order in DEFAULT_DIRECTIONS:
        row = SchoolPlanDirection.query.filter((SchoolPlanDirection.code == code) | (SchoolPlanDirection.name == name)).first()
        if not row:
            row = SchoolPlanDirection(code=code, name=name)
            db.session.add(row)
            changed = True
        row.color = row.color or color
        row.text_color = row.text_color or text_color
        row.sort_order = row.sort_order or sort_order
        row.is_active = True

    for code, name, color, text_color, sort_order in DEFAULT_CATEGORIES:
        row = SchoolPlanCategory.query.filter((SchoolPlanCategory.code == code) | (SchoolPlanCategory.name == name)).first()
        if not row:
            row = SchoolPlanCategory(code=code, name=name)
            db.session.add(row)
            changed = True
        row.color = row.color or color
        row.text_color = row.text_color or text_color
        row.sort_order = row.sort_order or sort_order
        row.is_active = True

    if changed:
        db.session.commit()
