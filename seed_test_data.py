"""
Скрипт для заполнения тестовыми данными: ученики + инциденты.

Запуск (из папки "код системы"):
    python seed_test_data.py

Опции:
    --clean     удалить ранее созданные тестовые записи перед заполнением
    --incidents-only  только инциденты (ученики уже есть)
"""

import sys
import random
from datetime import datetime, timedelta

sys.path.insert(0, ".")

from app import create_app, db
from app.models_legacy import (
    Child, ChildEnrollment, SchoolClass, AcademicYear, Incident, IncidentChild, User
)

# ---------------------------------------------------------------------------
# Данные для генерации
# ---------------------------------------------------------------------------

LAST_NAMES = [
    "Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов",
    "Попов", "Лебедев", "Козлов", "Новиков", "Морозов",
    "Соколов", "Волков", "Зайцев", "Павлов", "Семёнов",
    "Голубев", "Виноградов", "Богданов", "Воробьёв", "Фёдоров",
]

LAST_NAMES_F = [n + "а" if not n.endswith("ов") else n[:-2] + "ова"
                if "ов" in n else n + "а"
                for n in LAST_NAMES]

# Простой список женских вариантов
LAST_NAMES_F = [
    "Иванова", "Петрова", "Сидорова", "Смирнова", "Кузнецова",
    "Попова", "Лебедева", "Козлова", "Новикова", "Морозова",
    "Соколова", "Волкова", "Зайцева", "Павлова", "Семёнова",
    "Голубева", "Виноградова", "Богданова", "Воробьёва", "Фёдорова",
]

FIRST_NAMES_M = [
    "Александр", "Дмитрий", "Максим", "Сергей", "Андрей",
    "Алексей", "Артём", "Илья", "Кирилл", "Михаил",
    "Никита", "Роман", "Егор", "Даниил", "Иван",
]

FIRST_NAMES_F = [
    "Анастасия", "Мария", "Анна", "Виктория", "Екатерина",
    "Наталья", "Ольга", "Татьяна", "Юлия", "Елена",
    "Дарья", "Алина", "Валерия", "Полина", "Ксения",
]

MIDDLE_NAMES_M = [
    "Александрович", "Дмитриевич", "Максимович", "Сергеевич", "Андреевич",
    "Алексеевич", "Артёмович", "Ильич", "Кириллович", "Михайлович",
]

MIDDLE_NAMES_F = [
    "Александровна", "Дмитриевна", "Максимовна", "Сергеевна", "Андреевна",
    "Алексеевна", "Артёмовна", "Ильинична", "Кирилловна", "Михайловна",
]

INCIDENT_CATEGORIES = [
    "Конфликт между учениками",
    "Опоздание / пропуск",
    "Нарушение дисциплины",
    "Травма на территории школы",
    "Буллинг",
]

INCIDENT_DESCRIPTIONS = [
    "Ситуация потребовала вмешательства классного руководителя.",
    "Зафиксировано сотрудником дежурной службы.",
    "Родители уведомлены о произошедшем.",
    "Проведена беседа с участниками инцидента.",
    "Направлено на разбор к психологу.",
    "Оформлен акт, директор уведомлён.",
]

STATUSES = ["new", "new", "in_progress", "closed"]  # чаще new

TEST_TAG = "[TEST]"  # метим notes у детей, чтобы потом можно было удалить


def random_fio():
    gender = random.choice(["M", "F"])
    if gender == "M":
        return (
            random.choice(LAST_NAMES),
            random.choice(FIRST_NAMES_M),
            random.choice(MIDDLE_NAMES_M),
            "male",
        )
    else:
        return (
            random.choice(LAST_NAMES_F),
            random.choice(FIRST_NAMES_F),
            random.choice(MIDDLE_NAMES_F),
            "female",
        )


def random_dt(days_back=90):
    delta = random.randint(0, days_back * 24 * 60)
    dt = datetime.now() - timedelta(minutes=delta)
    # округляем минуты до кратных 5
    dt = dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)
    return dt


# ---------------------------------------------------------------------------
# Основная логика
# ---------------------------------------------------------------------------

def seed(clean=False, incidents_only=False):
    app = create_app()

    with app.app_context():
        # --- Текущий учебный год ---
        year = AcademicYear.query.filter_by(is_current=True).first()
        if not year:
            print("ОШИБКА: нет текущего учебного года (is_current=True). Создайте его через /admin.")
            return

        # --- Классы ---
        classes = SchoolClass.query.filter_by(
            academic_year_id=year.id,
            is_active=True,
        ).all()
        if not classes:
            print("ОШИБКА: нет активных классов для текущего года. Добавьте классы через интерфейс.")
            return

        print(f"Учебный год: {year.name}")
        print(f"Классов доступно: {len(classes)}")

        # --- Удаление тестовых данных ---
        if clean:
            print("\nУдаляем тестовые записи...")
            test_children = Child.query.filter(Child.notes.like(f"%{TEST_TAG}%")).all()
            for ch in test_children:
                # инциденты удалятся каскадно через IncidentChild → Incident если нет других детей
                for link in ch.incident_links:
                    inc = link.incident
                    db.session.delete(link)
                    # если у инцидента больше нет детей — удаляем и его
                    if len(inc.links) <= 1:
                        db.session.delete(inc)
                for enr in ch.enrollments:
                    db.session.delete(enr)
                db.session.delete(ch)
            db.session.commit()
            print(f"Удалено тестовых детей: {len(test_children)}")

        if incidents_only:
            children = Child.query.filter(Child.notes.like(f"%{TEST_TAG}%")).all()
            if not children:
                print("Тестовых детей нет. Сначала запустите без --incidents-only.")
                return
        else:
            # --- Создаём учеников ---
            n_children = 30
            print(f"\nСоздаём {n_children} тестовых учеников...")
            children = []

            for _ in range(n_children):
                last, first, middle, gender = random_fio()
                ch = Child(
                    last_name=last,
                    first_name=first,
                    middle_name=middle,
                    gender=gender,
                    status="ACTIVE",
                    notes=TEST_TAG,
                )
                db.session.add(ch)
                db.session.flush()  # получаем ch.id

                # Записываем в случайный класс
                sc = random.choice(classes)
                enr = ChildEnrollment(
                    child_id=ch.id,
                    academic_year_id=year.id,
                    school_class_id=sc.id,
                    status="ACTIVE",
                )
                db.session.add(enr)
                children.append(ch)

            db.session.commit()
            print(f"Создано учеников: {len(children)}")

        # --- Автор инцидентов: первый ADMIN или METHODIST ---
        author = (
            User.query.filter(User.role.in_(["ADMIN", "METHODIST"])).first()
            or User.query.first()
        )
        if not author:
            print("ОШИБКА: нет пользователей в системе.")
            return

        print(f"Автор инцидентов: {author.username} ({author.role})")

        # --- Создаём инциденты ---
        n_incidents = 20
        print(f"\nСоздаём {n_incidents} тестовых инцидентов...")

        for i in range(n_incidents):
            # 1–3 ребёнка на инцидент
            n_participants = random.randint(1, 3)
            participants = random.sample(children, min(n_participants, len(children)))

            inc = Incident(
                occurred_at=random_dt(90),
                category=random.choice(INCIDENT_CATEGORIES),
                description=random.choice(INCIDENT_DESCRIPTIONS),
                status=random.choice(STATUSES),
                author_id=author.id,
            )
            db.session.add(inc)
            db.session.flush()

            for ch in participants:
                link = IncidentChild(incident_id=inc.id, child_id=ch.id)
                db.session.add(link)

        db.session.commit()
        print(f"Создано инцидентов: {n_incidents}")

        # --- Итог ---
        total_children = Child.query.filter(Child.notes.like(f"%{TEST_TAG}%")).count()
        total_incidents = Incident.query.count()
        print(f"\nГотово!")
        print(f"  Тестовых детей в БД: {total_children}")
        print(f"  Всего инцидентов в БД: {total_incidents}")
        print(f"\nЧтобы удалить тестовые данные: python seed_test_data.py --clean")


if __name__ == "__main__":
    clean = "--clean" in sys.argv
    incidents_only = "--incidents-only" in sys.argv
    seed(clean=clean, incidents_only=incidents_only)
