"""Import the 2026/2027 VSOKO plan into the editable school plan once."""

import argparse
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.core.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    AcademicYear,
    SchoolPlanCategory,
    SchoolPlanDirection,
    SchoolPlanEvent,
)


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "vsoko_2026_2027.json"


def load_plan(path=DATA_PATH):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if plan.get("academic_year") != "2026/2027":
        raise ValueError("Неверный учебный год в файле ВСОКО.")
    items = plan.get("items", [])
    if len(items) != 37 or {item["source_row"] for item in items} != set(range(1, 38)):
        raise ValueError("В плане ВСОКО ожидаются 37 пронумерованных пунктов.")
    for item in items:
        start = date.fromisoformat(item["start_date"])
        end = date.fromisoformat(item["end_date"])
        if end < start or item["date_precision"] not in {"exact", "window"}:
            raise ValueError(f"Некорректный срок пункта №{item['source_row']}.")
        if item["date_precision"] == "exact" and start != end:
            raise ValueError(f"Точная дата пункта №{item['source_row']} не совпадает с окончанием.")
        for field in ("term", "subdirection", "title", "goal", "methods", "responsible", "result"):
            if not item[field].strip():
                raise ValueError(f"Не заполнено поле {field} в пункте №{item['source_row']}.")
        if len(item["responsible"]) > 255:
            raise ValueError(f"Слишком длинное поле ответственных в пункте №{item['source_row']}.")
        if len(f"{item['subdirection']}: {item['title']}") > 255:
            raise ValueError(f"Слишком длинное название пункта №{item['source_row']}.")
    return plan


def import_plan(plan):
    year = AcademicYear.query.filter_by(name=plan["academic_year"]).one_or_none()
    if year is None:
        raise ValueError("Учебный год 2026/2027 не найден в Альтаире.")

    direction = SchoolPlanDirection.query.filter_by(code="vsoko").one_or_none()
    if direction is None:
        direction = SchoolPlanDirection.query.filter_by(name="ВСОКО").one_or_none()
    if direction is not None and SchoolPlanEvent.query.filter_by(
        academic_year_id=year.id, direction_id=direction.id,
    ).first() is not None:
        raise ValueError("В школьном плане уже есть мероприятия ВСОКО за 2026/2027. Повторная загрузка остановлена, чтобы сохранить правки.")
    if direction is None:
        direction = SchoolPlanDirection(
            code="vsoko", name="ВСОКО", color="#0f766e",
            text_color="#ffffff", sort_order=15, is_active=True,
        )
        db.session.add(direction)
    elif not direction.code:
        direction.code = "vsoko"
    direction.is_active = True

    category = SchoolPlanCategory.query.filter_by(code="monitoring").one_or_none()
    if category is None:
        category = SchoolPlanCategory.query.filter_by(name="Мониторинг").one_or_none()
    if category is None:
        category = SchoolPlanCategory(
            code="monitoring", name="Мониторинг", color="#0f766e",
            text_color="#ffffff", sort_order=60, is_active=True,
        )
        db.session.add(category)

    for item in plan["items"]:
        start = date.fromisoformat(item["start_date"])
        end = date.fromisoformat(item["end_date"])
        description = "\n".join((
            f"Срок по исходному плану: {item['term']}",
            f"Направление контроля: {item['subdirection']}",
            f"Цель и содержание: {item['goal']}",
            f"Вид и методы: {item['methods']}",
            f"Ожидаемый результат: {item['result']}",
            f"Пункт исходного плана: №{item['source_row']}",
        ))
        db.session.add(SchoolPlanEvent(
            academic_year=year,
            title=f"{item['subdirection']}: {item['title']}",
            description=description,
            start_date=start,
            end_date=end if item["date_precision"] == "window" else None,
            period_type="range" if item["date_precision"] == "window" else "day",
            direction=direction,
            category=category,
            responsible_text=item["responsible"],
            priority="normal",
            status="planned",
            visibility_level="school",
        ))
    db.session.commit()
    return len(plan["items"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Записать план в базу данных")
    args = parser.parse_args()
    plan = load_plan()
    print(f"Проверено пунктов ВСОКО: {len(plan['items'])}")
    if args.apply:
        app = create_app()
        with app.app_context():
            try:
                count = import_plan(plan)
            except Exception:
                db.session.rollback()
                raise
        print(f"Загружено в школьный план: {count}")
    else:
        print("Проверка без записи; для загрузки укажите --apply")


if __name__ == "__main__":
    main()
