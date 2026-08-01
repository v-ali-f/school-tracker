import re
from collections import defaultdict
from decimal import Decimal


ZERO = Decimal("0")

PLAN_KIND_LABELS = {
    "CURRICULUM": "Учебный план",
    "EXTRACURRICULAR": "Внеурочная деятельность",
    "ADDITIONAL_EDUCATION": "Дополнительное образование",
}

PLAN_KIND_ORDER = {
    "CURRICULUM": 0,
    "EXTRACURRICULAR": 1,
    "ADDITIONAL_EDUCATION": 2,
}


def _class_sort_key(name):
    text = " ".join((name or "").split())
    match = re.match(r"^(\d+)\s*(.*)$", text)
    if match:
        return int(match.group(1)), match.group(2).casefold()
    return 99, text.casefold()


def _need_plan_context(need):
    group = need.teaching_group
    line = group.source_plan_line if group else None
    plan = line.education_plan if line else None
    root_plan = plan.root_plan if plan and plan.root_plan else plan
    return {
        "plan_kind": plan.plan_kind if plan else "CURRICULUM",
        "plan": plan,
        "root_plan": root_plan,
    }


def _group_label(group):
    if group is None:
        return "Без учебной группы"
    if group.group_type == "CLASS":
        return "Весь класс"
    if group.group_type == "SUBGROUP":
        match = re.search(r"группа\s*(\d+)", group.name or "", re.I)
        return f"Группа {match.group(1)}" if match else group.name
    return group.name


def _column_for_need(need, plan_context):
    group = need.teaching_group
    source_classes = sorted(
        (
            link.population_snapshot_class
            for link in (group.source_classes if group else [])
            if link.population_snapshot_class is not None
        ),
        key=lambda item: _class_sort_key(item.name_snapshot),
    )
    if group and (group.group_type == "METAGROUP" or len(source_classes) > 1):
        class_names = tuple(item.name_snapshot for item in source_classes)
        grade = min(
            (
                item.grade_snapshot
                for item in source_classes
                if item.grade_snapshot is not None
            ),
            default=99,
        )
        return {
            "key": f"metagroup-{group.id}",
            "label": group.name,
            "detail": " + ".join(class_names),
            "plan_name": (
                plan_context["root_plan"].name
                if plan_context["root_plan"] is not None
                else ""
            ),
            "is_metagroup": True,
            "is_orphan": False,
            "grade": grade,
            "class_name": group.name,
            "sort_key": (
                grade,
                "яя",
                1,
                (group.name or "").casefold(),
            ),
        }
    if len(source_classes) == 1:
        snapshot_class = source_classes[0]
        root_plan = plan_context["root_plan"]
        plan_id = root_plan.id if root_plan is not None else 0
        return {
            "key": f"class-{snapshot_class.id}-plan-{plan_id}",
            "label": snapshot_class.name_snapshot,
            "detail": "",
            "plan_name": root_plan.name if root_plan is not None else "",
            "is_metagroup": False,
            "is_orphan": False,
            "grade": snapshot_class.grade_snapshot or 99,
            "class_name": snapshot_class.name_snapshot,
            "sort_key": (
                snapshot_class.grade_snapshot or 99,
                _class_sort_key(snapshot_class.name_snapshot)[1],
                0,
                (root_plan.name if root_plan is not None else "").casefold(),
            ),
        }
    group_name = group.name if group is not None else "Без класса"
    group_id = group.id if group is not None else need.id
    return {
        "key": f"group-{group_id}",
        "label": group_name,
        "detail": "Учебная группа",
        "plan_name": (
            plan_context["root_plan"].name
            if plan_context["root_plan"] is not None
            else ""
        ),
        "is_metagroup": False,
        "is_orphan": True,
        "grade": 99,
        "class_name": group_name,
        "sort_key": (99, "яя", 2, group_name.casefold()),
    }


def _new_row(teacher, activity, plan_kind):
    return {
        "teacher": teacher,
        "activity": activity,
        "plan_kind": plan_kind,
        "plan_kind_label": PLAN_KIND_LABELS.get(plan_kind, plan_kind),
        "total": ZERO,
        "cells": defaultdict(list),
    }


def _new_block(teacher=None, *, unassigned=False):
    return {
        "teacher": teacher,
        "unassigned": unassigned,
        "label": "Не распределено" if unassigned else teacher.fio,
        "total": ZERO,
        "rows_by_key": {},
        "rows": [],
    }


def _row_for(block, need, plan_context):
    key = (
        need.education_activity_id,
        plan_context["plan_kind"],
    )
    row = block["rows_by_key"].get(key)
    if row is None:
        row = _new_row(
            block["teacher"],
            need.education_activity,
            plan_context["plan_kind"],
        )
        block["rows_by_key"][key] = row
    return row


def _segment(need, hours, *, unassigned):
    group = need.teaching_group
    return {
        "need": need,
        "hours": Decimal(hours or ZERO),
        "planned": Decimal(need.weekly_hours or ZERO),
        "remaining": Decimal(need.remaining_weekly_hours or ZERO),
        "label": _group_label(group),
        "group_type": group.group_type if group else None,
        "unassigned": unassigned,
        "partial": (
            not unassigned
            and Decimal(need.remaining_weekly_hours or ZERO) > ZERO
        ),
    }


def build_workload_assignment_matrix(needs, assignments):
    needs = list(needs)
    assignments = list(assignments)
    contexts = {
        need.id: _need_plan_context(need)
        for need in needs
    }
    columns_by_key = {}
    need_column_keys = {}
    for need in needs:
        column = _column_for_need(need, contexts[need.id])
        need_column_keys[need.id] = column["key"]
        columns_by_key.setdefault(column["key"], column)

    class_plan_counts = defaultdict(set)
    for column in columns_by_key.values():
        if not column["is_orphan"] and not column["is_metagroup"]:
            class_plan_counts[column["class_name"]].add(column["plan_name"])
    for column in columns_by_key.values():
        column["show_plan_name"] = (
            not column["is_orphan"]
            and not column["is_metagroup"]
            and len(class_plan_counts[column["class_name"]]) > 1
        )
        column["planned"] = ZERO
        column["allocated"] = ZERO
        column["remaining"] = ZERO

    assignments_by_need = defaultdict(list)
    for assignment in assignments:
        if (
            assignment.status == "CANCELLED"
            or assignment.assignment_kind == "VACANCY"
            or assignment.employee_user_id is None
        ):
            continue
        assignments_by_need[assignment.workload_need_id].append(assignment)

    blocks_by_teacher = {}
    unassigned_block = _new_block(unassigned=True)
    for need in needs:
        context = contexts[need.id]
        column_key = need_column_keys[need.id]
        column = columns_by_key[column_key]
        column["planned"] += Decimal(need.weekly_hours or ZERO)
        column["allocated"] += Decimal(need.allocated_weekly_hours or ZERO)
        column["remaining"] += Decimal(need.remaining_weekly_hours or ZERO)

        for assignment in assignments_by_need.get(need.id, []):
            teacher = assignment.employee
            block = blocks_by_teacher.setdefault(
                teacher.id,
                _new_block(teacher),
            )
            row = _row_for(block, need, context)
            hours = Decimal(assignment.weekly_hours or ZERO)
            row["total"] += hours
            block["total"] += hours
            row["cells"][column_key].append(
                _segment(need, hours, unassigned=False)
            )

        remaining = Decimal(need.remaining_weekly_hours or ZERO)
        if remaining > ZERO:
            row = _row_for(unassigned_block, need, context)
            row["total"] += remaining
            unassigned_block["total"] += remaining
            row["cells"][column_key].append(
                _segment(need, remaining, unassigned=True)
            )

    columns = sorted(
        columns_by_key.values(),
        key=lambda item: item["sort_key"],
    )
    blocks = list(blocks_by_teacher.values())
    blocks.sort(key=lambda item: item["label"].casefold())
    if unassigned_block["rows_by_key"]:
        blocks.insert(0, unassigned_block)

    for block in blocks:
        block["rows"] = sorted(
            block["rows_by_key"].values(),
            key=lambda row: (
                PLAN_KIND_ORDER.get(row["plan_kind"], 99),
                row["activity"].name.casefold(),
            ),
        )
        for row in block["rows"]:
            row["cells"] = dict(row["cells"])

    total_weekly = sum(
        (Decimal(need.weekly_hours or ZERO) for need in needs),
        ZERO,
    )
    total_allocated = sum(
        (Decimal(need.allocated_weekly_hours or ZERO) for need in needs),
        ZERO,
    )
    return {
        "columns": columns,
        "blocks": blocks,
        "need_count": len(needs),
        "teacher_count": len(blocks_by_teacher),
        "total_weekly": total_weekly,
        "total_allocated": total_allocated,
        "total_remaining": total_weekly - total_allocated,
    }


__all__ = ["build_workload_assignment_matrix"]
