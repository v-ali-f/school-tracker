import re
from datetime import datetime
from app.core.extensions import db
from app import create_app
from app.models import AcademicYear, SchoolClass, ChildEnrollment, Child

def parse_class_name(raw: str):
    """
    Примеры: '5А', '5 А', '10Б', '1В'
    Возвращает (grade:int, letter:str) или None
    """
    if not raw:
        return None
    s = raw.strip().upper().replace(" ", "")
    s = s.replace("A", "А").replace("B", "В")  # на всякий случай латиница
    m = re.match(r"^(\d{1,2})([А-ЯЁ])$", s)
    if not m:
        return None
    return int(m.group(1)), m.group(2)

def ensure_current_year(name="2025/2026"):
    y = AcademicYear.query.filter_by(name=name).first()
    if not y:
        y = AcademicYear(name=name, is_current=True)
        db.session.add(y)
        db.session.flush()
    else:
        # делаем его текущим, остальные выключаем
        AcademicYear.query.update({AcademicYear.is_current: False})
        y.is_current = True
    return y

def migrate_children_to_enrollments(year_name="2025/2026", default_max=25):
    y = ensure_current_year(year_name)

    # создаём классы по уникальным именам из Child.class_name
    children = Child.query.all()

    class_map = {}  # "5А" -> SchoolClass
    for ch in children:
        p = parse_class_name(ch.class_name or "")
        if not p:
            continue
        grade, letter = p
        class_name = f"{grade}{letter}"

        sc = SchoolClass.query.filter_by(academic_year_id=y.id, building_id=None, name=class_name).first()
        if not sc:
            sc = SchoolClass(
                academic_year_id=y.id,
                building_id=None,
                name=class_name,
                max_students=default_max
            )
            db.session.add(sc)
            db.session.flush()
        class_map[class_name] = sc

    db.session.flush()

    # создаём активные зачисления тем, у кого их ещё нет
    for ch in children:
        # если уже есть активное — пропускаем
        active = None
        for e in (ch.enrollments or []):
            if e.ended_at is None and e.academic_year_id == y.id:
                active = e
                break
        if active:
            continue

        p = parse_class_name(ch.class_name or "")
        if not p:
            continue

        grade, letter = p
        class_name = f"{grade}{letter}"
        sc = class_map.get(class_name)
        if not sc:
            continue

        db.session.add(ChildEnrollment(
            child_id=ch.id,
            academic_year_id=y.id,
            school_class_id=sc.id,
            status="ACTIVE",
            created_at=datetime.utcnow()
        ))

    db.session.commit()
    print("MIGRATION OK")

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        migrate_children_to_enrollments("2025/2026")