from __future__ import annotations

from collections import defaultdict

LEVEL_ORDER = ["Высокий", "Повышенный", "Базовый", "Ниже базового", "Без уровня"]
LEVEL_COLORS = {
    "Ниже базового": {"fill": "rgba(220, 53, 69, 0.75)", "stroke": "rgb(220, 53, 69)"},
    "Базовый": {"fill": "rgba(255, 193, 7, 0.75)", "stroke": "rgb(255, 193, 7)"},
    "Повышенный": {"fill": "rgba(25, 135, 84, 0.75)", "stroke": "rgb(25, 135, 84)"},
    "Высокий": {"fill": "rgba(13, 110, 253, 0.75)", "stroke": "rgb(13, 110, 253)"},
    "Без уровня": {"fill": "rgba(108, 117, 125, 0.75)", "stroke": "rgb(108, 117, 125)"},
}


def aggregate_results(rows, level_getter, percent_getter, score_getter, binding_getter):
    percents = []
    scores = []
    levels = {key: 0 for key in LEVEL_ORDER}
    bound = 0
    for row in rows:
        level = level_getter(row)
        levels[level] = levels.get(level, 0) + 1
        percent = percent_getter(row)
        score = score_getter(row)
        if percent is not None:
            percents.append(percent)
        if score is not None:
            scores.append(score)
        if binding_getter(row):
            bound += 1
    return {
        "count": len(rows),
        "avg_percent": round(sum(percents) / len(percents), 1) if percents else None,
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "bound_count": bound,
        "unbound_count": len(rows) - bound,
        "binding_percent": round(bound * 100 / len(rows), 1) if rows else 0,
        "levels": levels,
    }


def choose_longest_label(values):
    values = [str(v).strip() for v in values if str(v or '').strip()]
    if not values:
        return "—"
    unique = []
    seen = set()
    for value in values:
        key = " ".join(value.lower().replace("ё", "е").split())
        if key not in seen:
            seen.add(key)
            unique.append(value)
    unique.sort(key=lambda x: (len(x), x), reverse=True)
    return unique[0]


def task_success_percent(task_rows):
    unique_by_result = {}
    for row in task_rows:
        unique_by_result.setdefault(getattr(row, "result_id", None), row)
    unique_rows = list(unique_by_result.values())
    if not unique_rows:
        return None
    success = 0
    for row in unique_rows:
        raw = (getattr(row, "raw_value", None) or "").strip().upper()
        if raw and raw not in {"0", "N", "N-", "0+", "0-"}:
            success += 1
    return round(success * 100 / len(unique_rows), 1)


def build_tasks_table(task_rows):
    grouped = defaultdict(list)
    for row in task_rows:
        task_key = str(getattr(row, "task_number", None) or "—")
        grouped[task_key].append(row)
    items = []
    for task_number, rows in grouped.items():
        label_values = []
        for row in rows:
            for value in [getattr(row, "skill", None), getattr(row, "block_name", None), getattr(row, "kes_code", None)]:
                if value:
                    label_values.append(value)
        unique_result_ids = {getattr(row, "result_id", None) for row in rows if getattr(row, "result_id", None) is not None}
        items.append({
            "task_number": task_number,
            "skill": choose_longest_label(label_values),
            "success_percent": task_success_percent(rows),
            "count": len(unique_result_ids) if unique_result_ids else len(rows),
        })
    def sort_key(item):
        raw = str(item["task_number"])
        try:
            return (0, int(raw))
        except Exception:
            return (1, raw)
    items.sort(key=lambda x: (sort_key(x), x["success_percent"] if x["success_percent"] is not None else 999))
    return items
