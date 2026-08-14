import re
from collections import defaultdict
from decimal import Decimal

from app.services.teaching_group_display_service import (
    teaching_group_assignment_label,
    teaching_group_class_names,
    teaching_group_source_groups,
)
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

LIST_PLAN_KIND_LABELS = {
    "CURRICULUM": "Урочная деятельность",
    "EXTRACURRICULAR": "Внеурочная деятельность",
    "ADDITIONAL_EDUCATION": "Дополнительное образование",
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


def need_population_snapshot_ids(need):
    group = need.teaching_group
    if group is None:
        return set()
    source_groups = (
        [link.source_group for link in group.metagroup_sources]
        if group.group_type == "METAGROUP"
        else [group]
    )
    return {
        link.population_snapshot_class.population_snapshot_id
        for source_group in source_groups
        for link in source_group.source_classes
        if link.population_snapshot_class is not None
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
    return teaching_group_assignment_label(group)


def _list_source_groups(group):
    return teaching_group_source_groups(group)


def _list_class_names(group):
    return teaching_group_class_names(group)


def _list_building_names(need):
    names = set()
    if need.building is not None and need.building.name:
        return [need.building.name]
    for source_group in _list_source_groups(need.teaching_group):
        if source_group.building is not None and source_group.building.name:
            names.add(source_group.building.name)
        for link in source_group.source_classes:
            snapshot_class = link.population_snapshot_class
            if (
                snapshot_class is not None
                and snapshot_class.building_name_snapshot
            ):
                names.add(snapshot_class.building_name_snapshot)
    return sorted(names, key=str.casefold)


def build_workload_assignment_list(assignments, *, visible_holder_keys=None):
    """Build a compact teacher-by-teacher view of assigned weekly hours."""
    blocks_by_holder = {}
    overall_totals = {
        plan_kind: ZERO for plan_kind in PLAN_KIND_ORDER
    }
    allowed_keys = (
        None if visible_holder_keys is None else set(visible_holder_keys)
    )

    for assignment in assignments:
        if assignment.status == "CANCELLED":
            continue
        is_vacancy = assignment.assignment_kind == "VACANCY"
        holder_key = (
            f"vacancy:{assignment.position_code}"
            if is_vacancy
            else f"teacher:{assignment.employee_user_id}"
        )
        if allowed_keys is not None and holder_key not in allowed_keys:
            continue
        if not is_vacancy and assignment.employee is None:
            continue

        need = assignment.workload_need
        plan_kind = need_plan_kind(need)
        hours = Decimal(assignment.weekly_hours or ZERO)
        block = blocks_by_holder.setdefault(holder_key, {
            "holder_key": holder_key,
            "teacher_id": assignment.employee_user_id,
            "is_vacancy": is_vacancy,
            "label": (
                assignment.position_title or "Вакансия"
                if is_vacancy else assignment.employee.fio
            ),
            "rows": [],
            "totals": {
                item: ZERO for item in PLAN_KIND_ORDER
            },
            "total": ZERO,
        })
        class_names = _list_class_names(need.teaching_group)
        building_names = _list_building_names(need)
        block["rows"].append({
            "assignment": assignment,
            "plan_kind": plan_kind,
            "plan_kind_label": LIST_PLAN_KIND_LABELS.get(
                plan_kind,
                PLAN_KIND_LABELS.get(plan_kind, plan_kind),
            ),
            "subject_name": need.education_activity.name,
            "class_label": ", ".join(class_names) or "—",
            "hours": hours,
            "group_label": _group_label(need.teaching_group),
            "building_label": ", ".join(building_names) or "—",
        })
        block["totals"][plan_kind] = (
            block["totals"].get(plan_kind, ZERO) + hours
        )
        block["total"] += hours
        overall_totals[plan_kind] = (
            overall_totals.get(plan_kind, ZERO) + hours
        )

    blocks = sorted(
        blocks_by_holder.values(),
        key=lambda item: item["label"].casefold(),
    )
    for block in blocks:
        block["rows"].sort(key=lambda row: (
            PLAN_KIND_ORDER.get(row["plan_kind"], 99),
            _class_sort_key(row["class_label"]),
            row["subject_name"].casefold(),
            row["group_label"].casefold(),
            row["assignment"].id,
        ))
        block["sections"] = [
            {
                "plan_kind": plan_kind,
                "label": LIST_PLAN_KIND_LABELS.get(
                    plan_kind,
                    PLAN_KIND_LABELS.get(plan_kind, plan_kind),
                ),
                "rows": [
                    row for row in block["rows"]
                    if row["plan_kind"] == plan_kind
                ],
                "total": block["totals"].get(plan_kind, ZERO),
            }
            for plan_kind in sorted(
                PLAN_KIND_ORDER,
                key=lambda item: PLAN_KIND_ORDER[item],
            )
            if block["totals"].get(plan_kind, ZERO) > ZERO
        ]

    return {
        "blocks": blocks,
        "totals": overall_totals,
        "total": sum(overall_totals.values(), ZERO),
    }


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
        split_profile_column = snapshot_class.grade_snapshot in {10, 11}
        source_school_class_id = (
            getattr(snapshot_class, "source_school_class_id", None)
            or snapshot_class.id
        )
        return {
            "key": (
                f"school-class-{source_school_class_id}-plan-{plan_id}"
                if split_profile_column
                else f"school-class-{source_school_class_id}"
            ),
            "label": snapshot_class.name_snapshot,
            "detail": "",
            "plan_name": root_plan.name if root_plan is not None else "",
            "profile_label": (
                (root_plan.profile_name or root_plan.name)
                if root_plan is not None and split_profile_column
                else ""
            ),
            "is_profile_column": split_profile_column,
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
            "snapshot_class_id": snapshot_class.id,
            "source_school_class_id": source_school_class_id,
            "plan_id": plan_id,
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


def _column_from_source(snapshot_class, root_plan):
    """Build a workload column directly from an already materialized need."""
    source_school_class_id = (
        getattr(snapshot_class, "source_school_class_id", None)
        or snapshot_class.id
    )
    split_profile_column = snapshot_class.grade_snapshot in {10, 11}
    plan_id = root_plan.id if root_plan is not None else 0
    plan_name = root_plan.name if root_plan is not None else ""
    return {
        "key": (
            f"school-class-{source_school_class_id}-plan-{plan_id}"
            if split_profile_column
            else f"school-class-{source_school_class_id}"
        ),
        "label": snapshot_class.name_snapshot,
        "detail": "",
        "plan_name": plan_name,
        "profile_label": (
            (root_plan.profile_name or plan_name)
            if root_plan is not None and split_profile_column
            else ""
        ),
        "is_profile_column": split_profile_column,
        "is_metagroup": False,
        "is_orphan": False,
        "grade": snapshot_class.grade_snapshot or 99,
        "class_name": snapshot_class.name_snapshot,
        "building_id": snapshot_class.building_id,
        "building_name": snapshot_class.building_name_snapshot or "",
        "building_tone": building_matrix_tone(snapshot_class.building),
        "snapshot_class_id": snapshot_class.id,
        "source_school_class_id": source_school_class_id,
        "plan_id": plan_id,
        "plan_names": [plan_name] if plan_name else [],
        "sort_key": (
            snapshot_class.grade_snapshot or 99,
            _class_sort_key(snapshot_class.name_snapshot)[1],
            0,
            plan_name.casefold(),
        ),
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


def _segment(need, hours, *, unassigned, allocated=ZERO):
    group = need.teaching_group
    remaining = Decimal(need.weekly_hours or ZERO) - Decimal(allocated)
    return {
        "need": need,
        "hours": Decimal(hours or ZERO),
        "planned": Decimal(need.weekly_hours or ZERO),
        "remaining": remaining,
        "label": _group_label(group),
        "group_type": group.group_type if group else None,
        "unassigned": unassigned,
        "partial": (
            not unassigned
            and remaining > ZERO
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
    total_assignments=None,
    holder_totals=None,
    visible_holder_key=None,
    visible_holder_keys=None,
):
    needs = list(needs)
    assignments = list(assignments)
    visible_holder_keys = (
        set(visible_holder_keys)
        if visible_holder_keys is not None else None
    )

    def holder_is_visible(holder_key):
        if visible_holder_key and holder_key != visible_holder_key:
            return False
        return (
            visible_holder_keys is None
            or holder_key in visible_holder_keys
        )
    contexts = {
        need.id: _need_plan_context(need)
        for need in needs
    }
    columns_by_key = {}
    display_key_by_source_key = {}
    plan_cells = {}
    for plan_matrix in plan_matrices:
        for class_group in plan_matrix.get("class_groups", []):
            snapshot_class = class_group["snapshot_class"]
            for source_column in class_group["columns"]:
                if source_column["is_unassigned"] or source_column["plan"] is None:
                    continue
                root_plan = source_column["plan"]
                source_school_class_id = (
                    getattr(
                        snapshot_class,
                        "source_school_class_id",
                        None,
                    )
                    or snapshot_class.id
                )
                display_key = (
                    (
                        f"school-class-{source_school_class_id}-"
                        f"plan-{root_plan.id}"
                    )
                    if source_column.get("is_profile_column")
                    else f"school-class-{source_school_class_id}"
                )
                display_key_by_source_key[source_column["key"]] = display_key
                column = columns_by_key.setdefault(display_key, {
                    "key": display_key,
                    "label": source_column["class_display_name"],
                    "detail": "",
                    "plan_name": root_plan.name,
                    "profile_label": (
                        source_column.get("profile_label") or ""
                    ),
                    "is_profile_column": bool(
                        source_column.get("is_profile_column")
                    ),
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
                    "snapshot_class_id": snapshot_class.id,
                    "source_school_class_id": source_school_class_id,
                    "plan_id": root_plan.id,
                    "plan_names": [],
                    "sort_key": (
                        snapshot_class.grade_snapshot or 99,
                        _class_sort_key(snapshot_class.name_snapshot)[1],
                        0,
                        root_plan.name.casefold(),
                    ),
                })
                if root_plan.name not in column["plan_names"]:
                    column["plan_names"].append(root_plan.name)
                column["plan_name"] = " / ".join(column["plan_names"])
        for section in plan_matrix.get("sections", []):
            for source_row in section["rows"]:
                for column_key, cell in source_row["cells"].items():
                    display_key = display_key_by_source_key.get(column_key)
                    if display_key is None:
                        continue
                    cell_key = (
                        source_row["activity"].id,
                        source_row["plan_kind"],
                        display_key,
                    )
                    merged_cell = plan_cells.setdefault(cell_key, {
                        "groups": [],
                    })
                    known_group_ids = {
                        item.id for item in merged_cell["groups"]
                    }
                    for group in cell.get("groups", ()):
                        if group.id not in known_group_ids:
                            merged_cell["groups"].append(group)
                            known_group_ids.add(group.id)

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
                snapshot_class = link.population_snapshot_class
                if snapshot_class is None:
                    continue
                key = (
                    f"class-{link.population_snapshot_class_id}-"
                    f"plan-{root_plan.id if root_plan is not None else 0}"
                )
                display_key = display_key_by_source_key.get(key)
                if display_key is None and not plan_matrices:
                    direct_column = _column_from_source(
                        snapshot_class,
                        root_plan,
                    )
                    display_key = direct_column["key"]
                    existing_column = columns_by_key.setdefault(
                        display_key,
                        direct_column,
                    )
                    if (
                        root_plan is not None
                        and root_plan.name not in existing_column["plan_names"]
                    ):
                        existing_column["plan_names"].append(root_plan.name)
                        existing_column["plan_name"] = " / ".join(
                            existing_column["plan_names"]
                        )
                if display_key in columns_by_key:
                    source_keys.append(display_key)
                    if not plan_matrices:
                        cell_key = (
                            need.education_activity_id,
                            contexts[need.id]["plan_kind"],
                            display_key,
                        )
                        merged_cell = plan_cells.setdefault(
                            cell_key,
                            {"groups": []},
                        )
                        if all(
                            item.id != source_group.id
                            for item in merged_cell["groups"]
                        ):
                            merged_cell["groups"].append(source_group)
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
    allocated_by_need = defaultdict(Decimal)
    for assignment in assignments:
        if assignment.status == "CANCELLED":
            continue
        assignments_by_need[assignment.workload_need_id].append(assignment)
        if assignment.assignment_kind != "VACANCY":
            allocated_by_need[assignment.workload_need_id] += Decimal(
                assignment.weekly_hours or ZERO
            )

    total_assignments = (
        assignments if total_assignments is None else list(total_assignments)
    )
    global_holder_totals = defaultdict(Decimal)
    global_holder_totals.update(holder_totals or {})
    global_subject_totals = defaultdict(Decimal)
    for assignment in total_assignments:
        if assignment.status == "CANCELLED":
            continue
        holder_key = (
            ("vacancy", assignment.position_code)
            if assignment.assignment_kind == "VACANCY"
            else ("teacher", assignment.employee_user_id)
        )
        assignment_context = _need_plan_context(
            assignment.workload_need
        )
        hours = Decimal(assignment.weekly_hours or ZERO)
        if holder_totals is None:
            global_holder_totals[holder_key] += hours
        global_subject_totals[(
            holder_key,
            assignment.workload_need.education_activity_id,
            assignment_context["plan_kind"],
        )] += hours

    blocks_by_teacher = {}
    for need in needs:
        context = contexts[need.id]
        column_keys = need_column_keys[need.id]
        for column_key in column_keys:
            column = columns_by_key[column_key]
            column["planned"] += Decimal(need.weekly_hours or ZERO)
            allocated = allocated_by_need[need.id]
            column["allocated"] += allocated
            column["remaining"] += (
                Decimal(need.weekly_hours or ZERO) - allocated
            )

        for assignment in assignments_by_need.get(need.id, []):
            if assignment.assignment_kind == "VACANCY":
                vacancy_key = assignment.position_code
                block_key = ("vacancy", vacancy_key)
                holder_key = f"vacancy:{vacancy_key}"
                if not holder_is_visible(holder_key):
                    continue
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
                holder_key = f"teacher:{teacher.id}"
                if not holder_is_visible(holder_key):
                    continue
                block = blocks_by_teacher.setdefault(
                    block_key,
                    _new_block(teacher),
                )
            row = _row_for(block, need, context)
            hours = Decimal(assignment.weekly_hours or ZERO)
            for column_key in column_keys:
                row["cells"][column_key].append(
                    _segment(
                        need,
                        hours,
                        unassigned=False,
                        allocated=allocated_by_need[need.id],
                    )
                )

    for teacher in extra_teachers:
        if not holder_is_visible(f"teacher:{teacher.id}"):
            continue
        blocks_by_teacher.setdefault(
            ("teacher", teacher.id),
            _new_block(teacher),
        )
    for vacancy in extra_vacancies:
        if not holder_is_visible(f"vacancy:{vacancy['key']}"):
            continue
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
        if not holder_is_visible(f"teacher:{teacher.id}"):
            continue
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
        if not holder_is_visible(f"vacancy:{vacancy_key}"):
            continue
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
    for display_index, column in enumerate(columns):
        column["building_tone"] = int(column.get("building_tone") or 0)
        column["display_index"] = display_index
    class_groups = []
    class_groups_by_key = {}
    for column in columns:
        if column["is_metagroup"] or column["is_orphan"]:
            group_key = column["key"]
        else:
            group_key = (
                f"school-class-{column['source_school_class_id']}"
                if column.get("source_school_class_id") is not None
                else f"class-{column['class_name']}"
            )
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
                    column.get("profile_label")
                    or column.get("plan_name")
                    or ""
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
            holder_key = (
                ("vacancy", block["vacancy_key"])
                if block["is_vacancy"]
                else ("teacher", block["teacher_id"])
            )
            row["total"] = global_subject_totals[(
                holder_key,
                row["activity"].id,
                row["plan_kind"],
            )]
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
        holder_key = (
            ("vacancy", block["vacancy_key"])
            if block["is_vacancy"]
            else ("teacher", block["teacher_id"])
        )
        block["total"] = global_holder_totals[holder_key]

    total_weekly = sum(
        (Decimal(need.weekly_hours or ZERO) for need in needs),
        ZERO,
    )
    total_allocated = sum(
        (allocated_by_need[need.id] for need in needs),
        ZERO,
    )
    unassigned_items = []
    for need in needs:
        planned = Decimal(need.weekly_hours or ZERO)
        allocated = allocated_by_need[need.id]
        remaining = planned - allocated
        if remaining <= ZERO:
            continue
        context = contexts[need.id]
        column_keys = need_column_keys[need.id]
        class_names = list(dict.fromkeys(
            columns_by_key[key]["class_name"]
            for key in column_keys
            if key in columns_by_key
        ))
        sort_column = next(
            (
                columns_by_key[key]
                for key in column_keys
                if key in columns_by_key
            ),
            None,
        )
        root_plan = context["root_plan"]
        unassigned_items.append({
            "need": need,
            "class_label": " + ".join(class_names) or "Без класса",
            "activity": need.education_activity,
            "plan_kind": context["plan_kind"],
            "plan_kind_label": PLAN_KIND_LABELS.get(
                context["plan_kind"],
                context["plan_kind"],
            ),
            "plan_name": root_plan.name if root_plan is not None else "",
            "group_label": _group_label(need.teaching_group),
            "planned": planned,
            "allocated": allocated,
            "remaining": remaining,
            "sort_key": (
                sort_column["sort_key"] if sort_column else (99, "яя"),
                PLAN_KIND_ORDER.get(context["plan_kind"], 99),
                need.education_activity.name.casefold(),
                need.id,
            ),
        })
    unassigned_items.sort(key=lambda item: item["sort_key"])
    return {
        "columns": columns,
        "class_groups": class_groups,
        "blocks": blocks,
        "need_count": len(needs),
        "teacher_count": len(blocks_by_teacher),
        "total_weekly": total_weekly,
        "total_allocated": total_allocated,
        "total_remaining": total_weekly - total_allocated,
        "unassigned_items": unassigned_items,
    }


__all__ = [
    "LIST_PLAN_KIND_LABELS",
    "build_workload_assignment_list",
    "build_workload_assignment_matrix",
    "need_education_level",
    "need_grades",
    "need_matches_department",
    "need_population_snapshot_ids",
    "need_plan_kind",
]
