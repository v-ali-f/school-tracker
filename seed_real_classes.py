"""Добавляет в локальную SQLite несколько реальных классов из школы №547
(формат 7-ПМ, 4-ВН и т.п.) и тестовых учеников, чтобы можно было кликнуть
в карточку и увидеть Кубок школы с реальным именем класса.

Безопасен: только INSERT, существующие классы/дети не трогает.
Запуск: python seed_real_classes.py
"""
import os, sys, io
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + os.path.abspath('instance/app.db'))

from app import create_app
from app.core.extensions import db


REAL_CLASSES = [
    ("7-ПМ", 7),
    ("7-НИ", 7),
    ("4-ВН", 4),
    ("11-ВМ", 11),
    ("10-ГА", 10),
    ("6-АГ", 6),
]

STUDENTS = [
    # (last, first, mid, class_name)
    ("Петров",    "Артём",    "Сергеевич",   "7-ПМ"),
    ("Иванов",    "Максим",   "Алексеевич",  "7-ПМ"),
    ("Сидорова",  "Анна",     "Дмитриевна",  "7-НИ"),
    ("Кузнецов",  "Егор",     "Павлович",    "4-ВН"),
    ("Орлова",    "Полина",   "Ивановна",    "11-ВМ"),
    ("Смирнов",   "Никита",   "Андреевич",   "10-ГА"),
    ("Фёдорова",  "Василиса", "Олеговна",    "6-АГ"),
]


def main():
    app = create_app()
    with app.app_context():
        from app.models import SchoolClass, Child, AcademicYear, ChildEnrollment

        year = AcademicYear.query.filter_by(is_current=True).first()
        if not year:
            print("Не найден текущий учебный год — прерываю")
            return

        created_classes = 0
        class_by_name = {}
        for name, grade in REAL_CLASSES:
            sc = SchoolClass.query.filter_by(academic_year_id=year.id, name=name).first()
            if not sc:
                sc = SchoolClass(
                    academic_year_id=year.id,
                    name=name,
                    grade=grade,
                    max_students=25,
                )
                db.session.add(sc)
                db.session.flush()
                created_classes += 1
                print(f"  + класс {name} (id={sc.id})")
            else:
                print(f"  = класс {name} уже есть (id={sc.id})")
            class_by_name[name] = sc

        created_children = 0
        for last, first, mid, cls_name in STUDENTS:
            sc = class_by_name.get(cls_name)
            if not sc:
                continue
            exists = Child.query.filter_by(
                last_name=last, first_name=first, middle_name=mid
            ).first()
            if exists:
                print(f"  = ученик {last} {first} уже есть (id={exists.id})")
                continue
            ch = Child(
                last_name=last,
                first_name=first,
                middle_name=mid,
                birth_date=date(2012, 1, 1),
                gender="M" if first[-1] not in ("а", "я") else "F",
            )
            db.session.add(ch)
            db.session.flush()
            enr = ChildEnrollment(
                child_id=ch.id,
                school_class_id=sc.id,
                academic_year_id=year.id,
                status="ACTIVE",
            )
            db.session.add(enr)
            created_children += 1
            print(f"  + {last} {first} → {cls_name} (child_id={ch.id})")

        db.session.commit()
        print(f"\nИтого: +{created_classes} классов, +{created_children} учеников")


if __name__ == "__main__":
    main()
