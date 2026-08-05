import re
from collections import defaultdict
from decimal import Decimal

from app.utils.building_matrix_tones import building_matrix_tone


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
    if (
        line is None
        and group is not None
        and group.group_type == "METAGROUP"
        and group.metagroup_sources
    ):
        line = group.metagroup_sources[0].source_group.source_plan_line
    plan = line.education_plan if line else None
    root_plan = plan.root_plan if plan and plan.root_plan else plan
    return {
        "plan_kind": plan.plan_kind if plan else "CURRICULUM",
        "plan": plan,
        "root_plan": root_plan,
    }


def need_education_level(need):
    context = _need_plan_context(need)
    root_plan = context["root_plan"]
    return root_plan.education_level if root_plan is not None else None


def need_plan_kind(need):
    return _need_plan_context(need)["plan_kind"]


def need_grades(need):
    group = need.teaching_group
    return {
        item.population_snapshot_class.grade_snapshot
        for item in (group.source_classes if group else [])
        if item.population_snapshot_class is not None
        and item.population_snapshot_class.grade_snapshot is not None
    }


def need_matches_department(need, department_id):
    if not department_id:
        return True
    if need.department_id == department_id:
        return True
    return any(
        link.is_active and link.department_id == department_id
        for link in need.education_activity.department_links
    )


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
        source_building_ids = {
            item.building_id
            for item in source_classes
        }
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
            "building_id": (
                next(iter(source_building_ids))
                if len(source_building_ids) == 1
                else None
            ),
            "building_name": (
                group.building.short_name or group.building.name
                if group.building else ""
            ),
            "building_tone": building_matrix_tone(
                group.building
                if group.building
                else source_classes[0].building
                if len(source_building_ids) == 1 and source_classes
                else None
            ),
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
            "building_id": snapshot_class.building_id,
            "building_name": (
                snapshot_class.building_name_snapshot or ""
            ),
            "building_tone": building_matrix_tone(
                snapshot_class.building
            ),
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
        "building_id": (
            group.building_id if group is not None else need.building_id
        ),
        "building_name": (
            group.building.short_name or group.building.name
            if group is not None and group.building
            else need.building.short_name or need.building.name
            if need.building else ""
        ),
        "building_tone": building_matrix_tone(
            group.building
            if group is not None and group.building
            else need.building
        ),
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


def _new_block(
    teacher=None,
    *,
    vacancy_key=None,
    vacancy_label=None,
    unassigned=False,
):
    is_vacancy = vacancy_key is not None
    return {
        "teacher": teacher,
        "teacher_id": teacher.id if teacher is not None else None,
        "vacancy_key": vacancy_key,
        "is_vacancy": is_vacancy,
        "holder_key": (
            f"vacancy:{vacancy_key}"
            if is_vacancy else f"teacher:{teacher.id}"
            if teacher is not None else "unassigned"
        ),
        "unassigned": unassigned,
        "label": (
            "Не распределено"
            if unassigned else vacancy_label or "Вакансия"
            if is_vacancy else teacher.fio
        ),
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


def _editable_slot(
    need,
    block,
    source_group,
    group_index,
    group_count,
    assignments,
):
    def belongs_to_holder(item):
        if block["is_vacancy"]:
            return (
                item.assignment_kind == "VACANCY"
                and item.position_code == block["vacancy_key"]
            )
        return (
            item.assignment_kind != "VACANCY"
            and item.employee_user_id == block["teacher_id"]
        )

    own_assignment = next(
        (
            item for item in assignments
            if belongs_to_holder(item)
        ),
        None,
    )
    assigned_elsewhere = next(
        (
            item for item in assignments
            if not belongs_to_holder(item)
        ),
        None,
    )
    target_group = need.teaching_group
    if target_group is not None and target_group.group_type == "METAGROUP":
        label = f"МГ · {target_group.name}"
    elif group_count > 1:
        label = f"Группа {group_index}"
    else:
        label = ""
    return {
        "need": need,
        "source_group": source_group,
        "assignment": own_assignment,
        "assigned_elsewhere": assigned_elsewhere,
        "planned": Decimal(need.weekly_hours or ZERO),
        "value": (
            Decimal(own_assignment.weekly_hours or ZERO)
            if own_assignment is not None else None
        ),
        "label": label,
        "is_metagroup": (
            target_group is not None
            and target_group.group_type == "METAGROUP"
        ),
    }


def build_workload_assignment_matrix(
    needs,
    assignments,
    *,
    plan_matrices=(),
    extra_teachers=(),
    extra_vacancies=(),
    draft_rows=(),
    draft_vacancy_rows=(),
    teacher_metadata=None,
):
    needs = list(needs)
    assignments = list(assignments)
    contexts = {
        need.id: _need_plan_context(need)
        for need in needs
    }
    columns_by_key = {}
    plan_cells = {}
    for plan_matrix in plan_matrices:
        for class_group in plan_matrix.get("class_groups", []):
            snapshot_class = class_group["snapshot_class"]
            for source_column in class_group["columns"]:
                if source_column["is_unassigned"] or source_column["plan"] is None:
                    continue
                root_plan = source_column["plan"]
                columns_by_key[source_column["key"]] = {
                    "key": source_column["key"],
                    "label": source_column["class_display_name"],
                    "detail": "",
                    "plan_name": root_plan.name,
                    "is_metagroup": False,
                    "is_orphan": False,
                    "grade": snapshot_class.grade_snapshot or 99,
                    "class_name": source_column["class_display_name"],
                    "building_id": snapshot_class.building_id,
                    "building_name": (
                        snapshot_class.building_name_snapshot or ""
                    ),
                    "building_tone": building_matrix_tone(
                        snapshot_class.building
                    ),
                    "snapshot_class_id": snapshot_class.id,
                    "plan_id": root_plan.id,
                    "sort_key": (
                        snapshot_class.grade_snapshot or 99,
                        _class_sort_key(snapshot_class.name_snapshot)[1],
                        0,
                        root_plan.name.casefold(),
                    ),
                }
        for section in plan_matrix.get("sections", []):
            for source_row in section["rows"]:
                for column_key, cell in source_row["cells"].items():
                    if column_key not in columns_by_key:
                        continue
                    plan_cells[
                        (
                            source_row["activity"].id,
                            source_row["plan_kind"],
                            column_key,
                        )
                    ] = cell

    need_column_keys = {}
    for need in needs:
        column = _column_for_need(need, contexts[need.id])
        source_keys = []
        group = need.teaching_group
        source_groups = (
            [link.source_group for link in group.metagroup_sources]
            if group is not None and group.group_type == "METAGROUP"
            else [group]
        )
        for source_group in source_groups:
            if source_group is None:
                continue
            line = source_group.source_plan_line
            root_plan = (
                line.education_plan.root_plan
                if line and line.education_plan.root_plan is not None
                else line.education_plan if line else None
            )
            for link in source_group.source_classes:
                key = (
                    f"class-{link.population_snapshot_class_id}-"
                    f"plan-{root_plan.id if root_plan is not None else 0}"
                )
                if key in columns_by_key:
                    source_keys.append(key)
        if source_keys:
            need_column_keys[need.id] = tuple(dict.fromkeys(source_keys))
        else:
            need_column_keys[need.id] = (column["key"],)
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
        if assignment.status == "CANCELLED":
            continue
        assignments_by_need[assignment.workload_need_id].append(assignment)

    blocks_by_teacher = {}
    for need in needs:
        context = contexts[need.id]
        column_keys = need_column_keys[need.id]
        for column_key in column_keys:
            column = columns_by_key[column_key]
            column["planned"] += Decimal(need.weekly_hours or ZERO)
            column["allocated"] += Decimal(need.allocated_weekly_hours or ZERO)
            column["remaining"] += Decimal(need.remaining_weekly_hours or ZERO)

        for assignment in assignments_by_need.get(need.id, []):
            if assignment.assignment_kind == "VACANCY":
                vacancy_key = assignment.position_code
                block_key = ("vacancy", vacancy_key)
                block = blocks_by_teacher.setdefault(
                    block_key,
                    _new_block(
                        vacancy_key=vacancy_key,
                        vacancy_label=assignment.position_title,
                    ),
                )
            else:
                teacher = assignment.employee
                block_key = ("teacher", teacher.id)
                block = blocks_by_teacher.setdefault(
                    block_key,
                    _new_block(teacher),
                )
            row = _row_for(block, need, context)
            hours = Decimal(assignment.weekly_hours or ZERO)
            row["total"] += hours
            block["total"] += hours
            for column_key in column_keys:
                row["cells"][column_key].append(
                    _segment(need, hours, unassigned=False)
                )

    for teacher in extra_teachers:
        blocks_by_teacher.setdefault(
            ("teacher", teacher.id),
            _new_block(teacher),
        )
    for vacancy in extra_vacancies:
        blocks_by_teacher.setdefault(
            ("vacancy", vacancy["key"]),
            _new_block(
                vacancy_key=vacancy["key"],
                vacancy_label=vacancy["label"],
            ),
        )

    needs_by_activity = defaultdict(list)
    for need in needs:
        context = contexts[need.id]
        for column_key in need_column_keys[need.id]:
            needs_by_activity[(
                need.education_activity_id,
                context["plan_kind"],
                column_key,
            )].append(need)

    for teacher, activity, plan_kind in draft_rows:
        block = blocks_by_teacher.setdefault(
            ("teacher", teacher.id),
            _new_block(teacher),
        )
        key = (activity.id, plan_kind)
        if key not in block["rows_by_key"]:
            block["rows_by_key"][key] = _new_row(
                teacher,
                activity,
                plan_kind,
            )
    vacancies_by_key = {
        item["key"]: item
        for item in extra_vacancies
    }
    for vacancy_key, activity, plan_kind in draft_vacancy_rows:
        vacancy = vacancies_by_key.get(vacancy_key, {
            "key": vacancy_key,
            "label": "Вакансия",
        })
        block = blocks_by_teacher.setdefault(
            ("vacancy", vacancy_key),
            _new_block(
                vacancy_key=vacancy_key,
                vacancy_label=vacancy["label"],
            ),
        )
        key = (activity.id, plan_kind)
        if key not in block["rows_by_key"]:
            block["rows_by_key"][key] = _new_row(
                None,
                activity,
                plan_kind,
            )

    columns = sorted(
        columns_by_key.values(),
        key=lambda item: item["sort_key"],
    )
    for column in columns:
        column["building_tone"] = int(column.get("building_tone") or 0)
    class_groups = []
    class_groups_by_key = {}
    for column in columns:
        if column["is_metagroup"] or column["is_orphan"]:
            group_key = column["key"]
        else:
            group_key = f"class-{column['class_name']}"
        class_group = class_groups_by_key.get(group_key)
        if class_group is None:
            class_group = {
                "key": group_key,
                "label": column["class_name"],
                "is_metagroup": column["is_metagroup"],
                "is_orphan": column["is_orphan"],
                "building_id": column.get("building_id"),
                "building_name": column.get("building_name") or "",
                "building_tone": column["building_tone"],
                "columns": [],
            }
            class_groups_by_key[group_key] = class_group
            class_groups.append(class_group)
        class_group["columns"].append(column)
    for group_index, class_group in enumerate(class_groups, start=1):
        class_group["is_alt"] = group_index % 2 == 0
        for column in class_group["columns"]:
            column["is_alt"] = class_group["is_alt"]
            if column["is_metagroup"]:
                column["subheader_label"] = "Метагруппа"
            elif column["is_orphan"]:
                column["subheader_label"] = column["detail"]
            else:
                column["subheader_label"] = (
                    column["plan_name"] or "Учебный план"
                )
    blocks = list(blocks_by_teacher.values())
    blocks.sort(key=lambda item: item["label"].casefold())
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
            row["available_cells"] = {}
            row["matrix_cells"] = {}
            if not row.get("placeholder"):
                for column in columns:
                    cell_key = (
                        row["activity"].id,
                        row["plan_kind"],
                        column["key"],
                    )
                    source_cell = plan_cells.get(cell_key)
                    available_needs = needs_by_activity.get(cell_key, [])
                    if source_cell is None and not available_needs:
                        continue
                    slots = []
                    seen_need_ids = set()
                    groups = list(source_cell.get("groups", ())) if source_cell else []
                    for group_index, source_group in enumerate(groups, start=1):
                        target_group = (
                            source_group.metagroup_membership.metagroup
                            if source_group.metagroup_membership is not None
                            else source_group
                        )
                        need = next(
                            (
                                item for item in available_needs
                                if item.teaching_group_id == target_group.id
                            ),
                            None,
                        )
                        if need is None or need.id in seen_need_ids:
                            continue
                        seen_need_ids.add(need.id)
                        slots.append(_editable_slot(
                            need,
                            block,
                            source_group,
                            group_index,
                            len(groups),
                            assignments_by_need.get(need.id, []),
                        ))
                    for need in available_needs:
                        if need.id in seen_need_ids:
                            continue
                        slots.append(_editable_slot(
                            need,
                            block,
                            need.teaching_group,
                            len(slots) + 1,
                            len(available_needs),
                            assignments_by_need.get(need.id, []),
                        ))
                    row["matrix_cells"][column["key"]] = {
                        "slots": slots,
                        "planned": source_cell is not None,
                    }
        if not block["rows"] and not block["unassigned"]:
            block["rows"] = [{
                "teacher": block["teacher"],
                "activity": None,
                "plan_kind": None,
                "plan_kind_label": "",
                "total": ZERO,
                "cells": {},
                "available_cells": {},
                "matrix_cells": {},
                "placeholder": True,
            }]
        block["metadata"] = (
            (teacher_metadata or {}).get(block["teacher_id"], {})
            if not block["is_vacancy"] else {}
        )

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
        "class_groups": class_groups,
        "blocks": blocks,
        "need_count": len(needs),
        "teacher_count": len(blocks_by_teacher),
        "total_weekly": total_weekly,
        "total_allocated": total_allocated,
        "total_remaining": total_weekly - total_allocated,
    }


__all__ = [
    "build_workload_assignment_matrix",
    "need_education_level",
    "need_grades",
    "need_matches_department",
    "need_plan_kind",
]
