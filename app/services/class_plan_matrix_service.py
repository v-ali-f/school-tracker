from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import joinedload, selectinload

from app.core.extensions import db
from app.models import (
    EducationPlan,
    EducationPlanBinding,
    EducationPlanLine,
    PLAN_COMPONENT_KINDS,
    PLAN_COMPONENT_LABELS,
    PopulationSnapshotClass,
)
from app.services.education_plan_binding_service import (
    EDUCATION_LEVEL_GRADES,
    class_level_plan_ids,
    class_plan_allocations,
    class_plan_option_ids,
    effective_binding_member_ids,
    plan_matches_snapshot_class,
)
from app.services.education_plan_service import (
    PLAN_BUNDLE_KINDS,
    PLAN_BUNDLE_LABELS,
    plan_bundle_parts,
)
from app.utils.building_matrix_tones import building_matrix_tone


EDUCATION_LEVEL_LABELS = {
    "NOO": "НОО · 1–4 классы",
    "OOO": "ООО · 5–9 классы",
    "SOO": "СОО · 10–11 классы",
}
UNASSIGNED_BUILDING_FILTER_ID = -1


def effective_line_weekly_hours(line, grade):
    if grade in {1, 11} and line.periods:
        first_period = min(line.periods, key=lambda item: item.date_from)
        return Decimal(first_period.weekly_hours or 0)
    if line.weekly_hours is None:
        return None
    return Decimal(line.weekly_hours)


def class_period_label(education_level, grade):
    if education_level == "NOO" and grade == 1:
        return "сент.–окт."
    if education_level == "SOO" and grade == 11:
        return "I период"
    return "ч/нед."


def snapshot_building_options(snapshot, allowed_building_ids=None):
    by_id = {}
    for item in (snapshot.classes if snapshot else []):
        if (
            allowed_building_ids is not None
            and item.building_id not in allowed_building_ids
        ):
            continue
        if item.building_id is None:
            option = by_id.setdefault(
                UNASSIGNED_BUILDING_FILTER_ID,
                {
                    "id": UNASSIGNED_BUILDING_FILTER_ID,
                    "name": "Здание не указано",
                    "class_count": 0,
                    "matrix_tone": 0,
                },
            )
            option["class_count"] += 1
            continue
        option = by_id.setdefault(item.building_id, {
            "id": item.building_id,
            "name": (
                item.building_name_snapshot
                or (
                    item.building.short_name
                    if item.building and item.building.short_name
                    else item.building.name
                    if item.building else None
                )
                or f"Здание {item.building_id}"
            ),
            "class_count": 0,
            "matrix_tone": building_matrix_tone(item.building),
        })
        option["class_count"] += 1
    return sorted(
        by_id.values(),
        key=lambda item: item["name"].casefold(),
    )


def _line_matches_snapshot_class(line, snapshot_class):
    for scope in line.scopes:
        if (
            scope.scope_kind == "GRADE"
            and scope.grade == snapshot_class.grade_snapshot
        ):
            return True
        if (
            scope.scope_kind == "CLASS"
            and scope.school_class_id
            == snapshot_class.source_school_class_id
        ):
            return True
    return False


def _plan_profile_label(plan):
    label = (plan.profile_name or plan.name or "").strip()
    if not plan.profile_name:
        upper_label = label.upper()
        for prefix in ("СОО ", "ООО ", "НОО "):
            if upper_label.startswith(prefix):
                label = label[len(prefix):].strip()
                break
    return label or plan.name


def _assigned_columns(snapshot_class, plans, bindings=None):
    compatible_plans = [
        plan
        for plan in plans
        if plan_matches_snapshot_class(plan, snapshot_class)
    ]
    if bindings is None:
        allocations, _ = class_plan_allocations(
            snapshot_class,
            compatible_plans,
        )
        whole_class_plan_ids = class_level_plan_ids(
            snapshot_class,
            compatible_plans,
        )
        option_plan_ids = class_plan_option_ids(
            snapshot_class,
            compatible_plans,
        )
    else:
        enrollment_ids = {
            item.id for item in snapshot_class.enrollments
        }
        compatible_plan_ids = {item.id for item in compatible_plans}
        compatible_bindings = [
            binding for binding in bindings
            if binding.education_plan_id in compatible_plan_ids
        ]
        allocations = {
            binding.education_plan_id: effective_binding_member_ids(
                binding,
                enrollment_ids,
            )
            for binding in compatible_bindings
        }
        whole_class_plan_ids = {
            binding.education_plan_id
            for binding in compatible_bindings
            if binding.binding_mode == "CLASS"
        }
        option_plan_ids = {
            binding.education_plan_id
            for binding in compatible_bindings
        }
    visible_plan_ids = whole_class_plan_ids | option_plan_ids
    split_profile_columns = (
        snapshot_class.grade_snapshot in {10, 11}
        and len(option_plan_ids) > 1
    )
    enrollment_ids = {item.id for item in snapshot_class.enrollments}
    assigned_ids = set()
    columns = []
    plans_by_id = {item.id: item for item in compatible_plans}
    for plan_id, member_ids in allocations.items():
        member_ids = set(member_ids) & enrollment_ids
        if not member_ids and plan_id not in visible_plan_ids:
            continue
        assigned_ids.update(member_ids)
        plan = plans_by_id.get(plan_id)
        if plan is None:
            continue
        profile_label = _plan_profile_label(plan)
        columns.append({
            "key": f"class-{snapshot_class.id}-plan-{plan.id}",
            "snapshot_class": snapshot_class,
            "plan": plan,
            "profile_label": profile_label,
            "class_display_name": (
                f"{snapshot_class.name_snapshot} {profile_label}"
                if split_profile_columns
                else snapshot_class.name_snapshot
            ),
            "is_profile_column": split_profile_columns,
            "student_count": len(member_ids),
            "member_ids": frozenset(member_ids),
            "is_unassigned": False,
        })
    columns.sort(key=lambda item: item["plan"].name.casefold())

    unassigned_count = len(enrollment_ids - assigned_ids)
    if unassigned_count or (
        not enrollment_ids and not visible_plan_ids
    ):
        columns.append({
            "key": f"class-{snapshot_class.id}-unassigned",
            "snapshot_class": snapshot_class,
            "plan": None,
            "profile_label": "",
            "class_display_name": snapshot_class.name_snapshot,
            "is_profile_column": False,
            "student_count": unassigned_count,
            "member_ids": frozenset(),
            "is_unassigned": True,
        })
    return columns


def _preload_matrix_plans(plans):
    plan_ids = [plan.id for plan in plans if plan.id is not None]
    if not plan_ids:
        return list(plans)

    root_line = selectinload(EducationPlan.lines)
    companion_line = (
        selectinload(EducationPlan.companion_plans)
        .selectinload(EducationPlan.lines)
    )
    loaded = (
        db.session.query(EducationPlan)
        .options(
            selectinload(EducationPlan.companion_plans),
            root_line.selectinload(EducationPlanLine.scopes),
            selectinload(EducationPlan.lines).selectinload(
                EducationPlanLine.periods
            ),
            selectinload(EducationPlan.lines).joinedload(
                EducationPlanLine.education_activity
            ),
            companion_line.selectinload(EducationPlanLine.scopes),
            selectinload(EducationPlan.companion_plans)
            .selectinload(EducationPlan.lines)
            .selectinload(EducationPlanLine.periods),
            selectinload(EducationPlan.companion_plans)
            .selectinload(EducationPlan.lines)
            .joinedload(EducationPlanLine.education_activity),
        )
        .filter(EducationPlan.id.in_(plan_ids))
        .all()
    )
    loaded_by_id = {plan.id: plan for plan in loaded}
    return [loaded_by_id.get(plan.id, plan) for plan in plans]


def build_class_plan_matrix(
    snapshot,
    plans,
    education_level,
    grade=None,
    building_id=None,
    allowed_building_ids=None,
):
    grades = EDUCATION_LEVEL_GRADES.get(education_level, set())
    selected_grade = grade if grade in grades else None
    snapshot_classes = sorted(
        (
            item
            for item in (
                PopulationSnapshotClass.query
                .options(
                    joinedload(PopulationSnapshotClass.building),
                    selectinload(PopulationSnapshotClass.enrollments),
                )
                .filter_by(population_snapshot_id=snapshot.id)
                .all()
                if snapshot else []
            )
            if (
                item.grade_snapshot in grades
                and (
                    allowed_building_ids is None
                    or item.building_id in allowed_building_ids
                )
                and (
                    building_id is None
                    or (
                        building_id == UNASSIGNED_BUILDING_FILTER_ID
                        and item.building_id is None
                    )
                    or item.building_id == building_id
                )
                and (
                    selected_grade is None
                    or item.grade_snapshot == selected_grade
                )
            )
        ),
        key=lambda item: (
            item.grade_snapshot or 0,
            item.name_snapshot.casefold(),
        ),
    )
    plans = _preload_matrix_plans(plans)
    root_plans = [
        item
        for item in plans
        if (
            item.plan_kind == "CURRICULUM"
            and item.root_plan_id is None
            and item.education_level == education_level
        )
    ]

    bindings_by_class = defaultdict(list)
    snapshot_class_ids = [item.id for item in snapshot_classes]
    root_plan_ids = [item.id for item in root_plans]
    if snapshot_class_ids and root_plan_ids:
        bindings = (
            EducationPlanBinding.query
            .options(selectinload(EducationPlanBinding.members))
            .filter(
                EducationPlanBinding.population_snapshot_class_id.in_(
                    snapshot_class_ids
                ),
                EducationPlanBinding.education_plan_id.in_(root_plan_ids),
            )
            .all()
        )
        for binding in bindings:
            bindings_by_class[
                binding.population_snapshot_class_id
            ].append(binding)

    class_groups = []
    columns = []
    for snapshot_class in snapshot_classes:
        class_columns = _assigned_columns(
            snapshot_class,
            root_plans,
            bindings=bindings_by_class[snapshot_class.id],
        )
        for column in class_columns:
            column["period_label"] = class_period_label(
                education_level,
                snapshot_class.grade_snapshot,
            )
        class_groups.append({
            "snapshot_class": snapshot_class,
            "columns": class_columns,
            "split_profile_columns": any(
                column["is_profile_column"]
                for column in class_columns
            ),
        })
        columns.extend(class_columns)

    row_map = {}
    section_column_totals = defaultdict(lambda: defaultdict(Decimal))
    plan_kind_column_totals = defaultdict(lambda: defaultdict(Decimal))
    column_totals = defaultdict(Decimal)
    plan_kind_order = {
        value: index for index, value in enumerate(PLAN_BUNDLE_KINDS)
    }
    component_order = {
        value: index for index, value in enumerate(PLAN_COMPONENT_KINDS)
    }

    for column in columns:
        plan = column["plan"]
        if plan is None:
            continue
        snapshot_class = column["snapshot_class"]
        parts = plan_bundle_parts(plan)
        for plan_kind in PLAN_BUNDLE_KINDS:
            part = parts.get(plan_kind)
            if part is None:
                continue
            for line in part.lines:
                if not _line_matches_snapshot_class(line, snapshot_class):
                    continue
                row_key = (
                    plan_kind,
                    line.component_kind,
                    line.education_activity_id,
                    line.profile_code or "",
                )
                row = row_map.setdefault(row_key, {
                    "plan_kind": plan_kind,
                    "component_kind": line.component_kind,
                    "activity": line.education_activity,
                    "profile_code": line.profile_code,
                    "sort_order": line.sort_order,
                    "plan_kind_order": plan_kind_order.get(plan_kind, 99),
                    "cells": {},
                })
                row["sort_order"] = min(row["sort_order"], line.sort_order)
                row["plan_kind_order"] = min(
                    row["plan_kind_order"],
                    plan_kind_order.get(plan_kind, 99),
                )
                hours = effective_line_weekly_hours(
                    line,
                    snapshot_class.grade_snapshot,
                )
                row["cells"][column["key"]] = {
                    "line": line,
                    "hours": hours,
                }
                if hours is not None:
                    section_column_totals[(
                        plan_kind,
                        line.component_kind,
                    )][
                        column["key"]
                    ] += hours
                    plan_kind_column_totals[plan_kind][
                        column["key"]
                    ] += hours
                    column_totals[column["key"]] += hours

    rows = sorted(
        row_map.values(),
        key=lambda row: (
            row["plan_kind_order"],
            component_order.get(row["component_kind"], 99),
            row["sort_order"],
            row["activity"].name.casefold(),
        ),
    )
    section_map = {}
    for row in rows:
        section_key = (row["plan_kind"], row["component_kind"])
        section_label = (
            PLAN_COMPONENT_LABELS.get(
                row["component_kind"],
                row["component_kind"],
            )
            if row["plan_kind"] == "CURRICULUM"
            else PLAN_BUNDLE_LABELS.get(
                row["plan_kind"],
                row["component_kind"],
            )
        )
        section = section_map.setdefault(section_key, {
            "plan_kind": row["plan_kind"],
            "component_kind": row["component_kind"],
            "label": section_label,
            "rows": [],
            "column_totals": section_column_totals[section_key],
        })
        section["rows"].append(row)

    sections = sorted(
        section_map.values(),
        key=lambda section: (
            min(row["plan_kind_order"] for row in section["rows"]),
            component_order.get(section["component_kind"], 99),
        ),
    )
    for index, section in enumerate(sections):
        section["is_plan_kind_end"] = (
            index == len(sections) - 1
            or sections[index + 1]["plan_kind"]
            != section["plan_kind"]
        )
    return {
        "education_level": education_level,
        "selected_grade": selected_grade,
        "selected_building_id": building_id,
        "level_label": EDUCATION_LEVEL_LABELS[education_level],
        "class_groups": class_groups,
        "columns": columns,
        "sections": sections,
        "plan_kind_column_totals": plan_kind_column_totals,
        "column_totals": column_totals,
        "class_count": len(snapshot_classes),
    }


__all__ = [
    "EDUCATION_LEVEL_GRADES",
    "EDUCATION_LEVEL_LABELS",
    "UNASSIGNED_BUILDING_FILTER_ID",
    "build_class_plan_matrix",
    "class_period_label",
    "effective_line_weekly_hours",
    "snapshot_building_options",
]
