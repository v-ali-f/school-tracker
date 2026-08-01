from math import ceil

from app.core.extensions import db
from app.models import (
    EducationPlan,
    EducationPlanLine,
    PopulationSnapshotClass,
    TeachingGroup,
    TeachingGroupClass,
    TeachingGroupMember,
    WorkloadNeed,
)
from app.services.class_plan_matrix_service import build_class_plan_matrix
from app.services.teaching_group_service import (
    GroupValidationError,
    add_group_history,
    touch_group,
)


AUTO_GROUP_CODE_PREFIX = "AUTO_L"


def build_teaching_group_matrix(snapshot, plans, education_level, version_id):
    matrix = build_class_plan_matrix(snapshot, plans, education_level)
    line_ids = {
        cell["line"].id
        for section in matrix["sections"]
        for row in section["rows"]
        for cell in row["cells"].values()
    }
    class_ids = {
        column["snapshot_class"].id
        for column in matrix["columns"]
        if not column["is_unassigned"]
    }
    groups_by_cell = {}
    if line_ids and class_ids:
        groups = (
            TeachingGroup.query
            .filter(
                TeachingGroup.tariff_version_id == version_id,
                TeachingGroup.source_plan_line_id.in_(line_ids),
                TeachingGroup.status != "CLOSED",
                TeachingGroup.group_type != "METAGROUP",
            )
            .all()
        )
        for group in groups:
            for source in group.source_classes:
                class_id = source.population_snapshot_class_id
                if class_id not in class_ids:
                    continue
                groups_by_cell.setdefault(
                    (group.source_plan_line_id, class_id),
                    [],
                ).append(group)

    divided_count = 0
    incomplete_count = 0
    for section in matrix["sections"]:
        for row in section["rows"]:
            for column in matrix["columns"]:
                cell = row["cells"].get(column["key"])
                if cell is None:
                    continue
                groups = groups_by_cell.get(
                    (
                        cell["line"].id,
                        column["snapshot_class"].id,
                    ),
                    [],
                )
                group_count = len(groups) or 1
                needs_composition = (
                    group_count > 1
                    and any(group.status != "READY" for group in groups)
                )
                cell.update({
                    "group_count": group_count,
                    "group_ids": tuple(group.id for group in groups),
                    "groups": tuple(
                        sorted(groups, key=lambda group: (group.code, group.id))
                    ),
                    "is_configured": bool(groups),
                    "needs_composition": needs_composition,
                })
                if group_count > 1:
                    divided_count += 1
                if needs_composition:
                    incomplete_count += 1

    matrix["divided_count"] = divided_count
    matrix["incomplete_count"] = incomplete_count
    matrix["column_count"] = sum(
        1 for column in matrix["columns"] if not column["is_unassigned"]
    )
    return matrix


def _group_type(plan_kind, count, is_full_class):
    if plan_kind == "EXTRACURRICULAR":
        return "EXTRACURRICULAR_GROUP"
    if plan_kind == "ADDITIONAL_EDUCATION":
        return "ADDITIONAL_GROUP"
    if count == 1 and is_full_class:
        return "CLASS"
    return "SUBGROUP"


def _unique_group_code(version_id, line_id, class_id, index):
    base = f"{AUTO_GROUP_CODE_PREFIX}{line_id}_C{class_id}_{index}"
    candidate = base
    suffix = 1
    while (
        TeachingGroup.query
        .filter_by(tariff_version_id=version_id, code=candidate)
        .first()
    ):
        suffix += 1
        candidate = f"{base}_R{suffix}"
    return candidate


def _locate_matrix_cell(snapshot, plans, line, snapshot_class, plan):
    matrix = build_class_plan_matrix(
        snapshot,
        plans,
        plan.education_level,
    )
    column = next(
        (
            item for item in matrix["columns"]
            if (
                item["snapshot_class"].id == snapshot_class.id
                and item["plan"] is not None
                and item["plan"].id == plan.id
            )
        ),
        None,
    )
    if column is None:
        raise GroupValidationError(
            "Учебный план не назначен выбранному классу или группе учеников."
        )
    cell = next(
        (
            row["cells"].get(column["key"])
            for section in matrix["sections"]
            for row in section["rows"]
            if (
                row["cells"].get(column["key"]) is not None
                and row["cells"][column["key"]]["line"].id == line.id
            )
        ),
        None,
    )
    if cell is None:
        raise GroupValidationError(
            "Предмет отсутствует в назначенном учебном плане класса."
        )
    return column


def _editable_existing_groups(version_id, line_id, class_id):
    groups = (
        TeachingGroup.query
        .join(TeachingGroupClass)
        .filter(
            TeachingGroup.tariff_version_id == version_id,
            TeachingGroup.source_plan_line_id == line_id,
            TeachingGroup.status != "CLOSED",
            TeachingGroup.group_type != "METAGROUP",
            TeachingGroupClass.population_snapshot_class_id == class_id,
        )
        .all()
    )
    if any(
        not group.code.startswith(AUTO_GROUP_CODE_PREFIX)
        for group in groups
    ):
        raise GroupValidationError(
            "В ячейке есть группа, созданная вручную. Измените её в карточке группы."
        )
    group_ids = [group.id for group in groups]
    if group_ids and (
        WorkloadNeed.query
        .filter(WorkloadNeed.teaching_group_id.in_(group_ids))
        .first()
    ):
        raise GroupValidationError(
            "По этим группам уже сформирована нагрузка. Сначала отмените её."
        )
    if group_ids and (
        TeachingGroup.query
        .filter(TeachingGroup.source_group_id.in_(group_ids))
        .first()
    ):
        raise GroupValidationError(
            "Группы уже используются в метагруппе и не могут быть пересозданы."
        )
    if any(
        member.source_kind != "AUTO"
        for group in groups
        for member in group.members
    ):
        raise GroupValidationError(
            "Поимённый состав уже заполнен. Измените количество после очистки состава."
        )
    return groups


def replace_teaching_group_count(
    *,
    version,
    snapshot,
    plans,
    plan_line_id,
    snapshot_class_id,
    plan_id,
    group_count,
    user_id,
):
    if version.status != "DRAFT":
        raise GroupValidationError(
            "Количество групп можно менять только в рабочей версии."
        )
    if group_count < 1 or group_count > 9:
        raise GroupValidationError("Количество групп должно быть от 1 до 9.")

    line = db.session.get(EducationPlanLine, plan_line_id)
    snapshot_class = db.session.get(
        PopulationSnapshotClass,
        snapshot_class_id,
    )
    plan = db.session.get(EducationPlan, plan_id)
    if line is None or snapshot_class is None or plan is None:
        raise GroupValidationError("Строка учебного плана не найдена.")
    if (
        line.education_plan.tariff_version_id != version.id
        or plan.tariff_version_id != version.id
        or snapshot_class.population_snapshot_id != snapshot.id
    ):
        raise GroupValidationError(
            "Строка, класс и учебный план относятся к разным версиям."
        )
    root_plan_id = (
        line.education_plan.root_plan_id
        or line.education_plan.id
    )
    if root_plan_id != plan.id:
        raise GroupValidationError(
            "Строка не относится к выбранному комплекту учебного плана."
        )

    column = _locate_matrix_cell(
        snapshot,
        plans,
        line,
        snapshot_class,
        plan,
    )
    member_ids = set(column["member_ids"])
    if not member_ids:
        raise GroupValidationError(
            "В выбранной части класса нет учеников, привязанных к учебному плану."
        )

    existing_groups = _editable_existing_groups(
        version.id,
        line.id,
        snapshot_class.id,
    )
    for group in existing_groups:
        db.session.delete(group)
    db.session.flush()

    academic_year = version.tariff_cycle.academic_year
    valid_from = academic_year.start_date
    valid_to = academic_year.end_date
    is_full_class = member_ids == {
        enrollment.id for enrollment in snapshot_class.enrollments
    }
    groups = []
    for index in range(1, group_count + 1):
        is_single = group_count == 1
        group = TeachingGroup(
            tariff_version_id=version.id,
            education_activity_id=line.education_activity_id,
            group_type=_group_type(
                line.education_plan.plan_kind,
                group_count,
                is_full_class,
            ),
            code=_unique_group_code(
                version.id,
                line.id,
                snapshot_class.id,
                index,
            ),
            name=(
                f"{snapshot_class.name_snapshot} · "
                f"{line.education_activity.name}"
                + ("" if is_single else f" · группа {index}")
            ),
            composition_mode="PERSONAL",
            building_id=snapshot_class.building_id,
            planned_size=(
                len(member_ids)
                if is_single
                else ceil(len(member_ids) / group_count)
            ),
            actual_size=len(member_ids) if is_single else 0,
            valid_from=valid_from,
            valid_to=valid_to,
            source_plan_line_id=line.id,
            status="READY" if is_single else "DRAFT",
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        db.session.add(group)
        db.session.flush()
        db.session.add(TeachingGroupClass(
            teaching_group_id=group.id,
            population_snapshot_class_id=snapshot_class.id,
            relation_kind=(
                "FULL"
                if is_single and is_full_class
                else "PARTIAL" if is_single else "SOURCE"
            ),
            student_count=len(member_ids) if is_single else 0,
        ))
        if is_single:
            for member_id in sorted(member_ids):
                db.session.add(TeachingGroupMember(
                    teaching_group_id=group.id,
                    snapshot_enrollment_id=member_id,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    source_kind="AUTO",
                ))
        add_group_history(
            group,
            "MATRIX_CREATED",
            user_id,
            {
                "group_count": group_count,
                "snapshot_class_id": snapshot_class.id,
                "plan_id": plan.id,
            },
        )
        groups.append(group)

    return groups


def build_group_composition_workspace(matrix):
    items = []
    for section in matrix["sections"]:
        for row in section["rows"]:
            for column in matrix["columns"]:
                cell = row["cells"].get(column["key"])
                if (
                    cell is None
                    or column["is_unassigned"]
                    or cell["group_count"] <= 1
                    or not cell["groups"]
                ):
                    continue
                groups = list(cell["groups"])
                eligible_ids = set(column["member_ids"])
                enrollments = sorted(
                    (
                        enrollment
                        for enrollment in column[
                            "snapshot_class"
                        ].enrollments
                        if enrollment.id in eligible_ids
                    ),
                    key=lambda item: item.fio_snapshot.casefold(),
                )
                assignment_by_member_id = {}
                for group in groups:
                    for member in group.members:
                        if member.snapshot_enrollment_id in eligible_ids:
                            assignment_by_member_id[
                                member.snapshot_enrollment_id
                            ] = group.id
                assigned_count = len(assignment_by_member_id)
                group_sizes = {
                    group.id: sum(
                        1
                        for group_id in assignment_by_member_id.values()
                        if group_id == group.id
                    )
                    for group in groups
                }
                complete = (
                    assigned_count == len(enrollments)
                    and bool(enrollments)
                    and all(group_sizes[group.id] > 0 for group in groups)
                )
                items.append({
                    "key": (
                        f"line-{cell['line'].id}-"
                        f"class-{column['snapshot_class'].id}"
                    ),
                    "section_label": section["label"],
                    "activity": row["activity"],
                    "plan_line": cell["line"],
                    "snapshot_class": column["snapshot_class"],
                    "plan": column["plan"],
                    "groups": groups,
                    "enrollments": enrollments,
                    "assignment_by_member_id": assignment_by_member_id,
                    "group_sizes": group_sizes,
                    "assigned_count": assigned_count,
                    "student_count": len(enrollments),
                    "complete": complete,
                })
    items.sort(key=lambda item: (
        item["snapshot_class"].grade_snapshot or 0,
        item["snapshot_class"].name_snapshot.casefold(),
        item["plan"].name.casefold(),
        item["activity"].name.casefold(),
    ))
    return {
        "items": items,
        "complete_count": sum(1 for item in items if item["complete"]),
        "incomplete_count": sum(
            1 for item in items if not item["complete"]
        ),
        "assigned_count": sum(
            item["assigned_count"] for item in items
        ),
        "student_count": sum(
            item["student_count"] for item in items
        ),
    }


def replace_group_composition_assignments(
    item,
    assignments,
    *,
    user_id,
):
    groups = list(item["groups"])
    if not groups:
        raise GroupValidationError("Учебные группы не найдены.")
    if any(
        not group.code.startswith(AUTO_GROUP_CODE_PREFIX)
        for group in groups
    ):
        raise GroupValidationError(
            "Состав можно менять только у групп, созданных из матрицы."
        )
    group_ids = {group.id for group in groups}
    if (
        WorkloadNeed.query
        .filter(WorkloadNeed.teaching_group_id.in_(group_ids))
        .first()
    ):
        raise GroupValidationError(
            "По группам уже сформирована нагрузка. Сначала отмените её."
        )

    eligible_ids = {
        enrollment.id for enrollment in item["enrollments"]
    }
    normalized_assignments = {
        int(member_id): int(group_id)
        for member_id, group_id in dict(assignments).items()
        if group_id is not None
    }
    if set(normalized_assignments) - eligible_ids:
        raise GroupValidationError(
            "В составе есть ученик из другого класса или учебного плана."
        )
    if set(normalized_assignments.values()) - group_ids:
        raise GroupValidationError(
            "Выбрана группа из другого предмета или класса."
        )

    for group in groups:
        for member in list(group.members):
            db.session.delete(member)
    db.session.flush()

    members_by_group = {group.id: [] for group in groups}
    for member_id, group_id in normalized_assignments.items():
        members_by_group[group_id].append(member_id)
    complete = (
        len(normalized_assignments) == len(eligible_ids)
        and bool(eligible_ids)
        and all(members_by_group[group.id] for group in groups)
    )
    for group in groups:
        member_ids = sorted(members_by_group[group.id])
        for member_id in member_ids:
            db.session.add(TeachingGroupMember(
                teaching_group_id=group.id,
                snapshot_enrollment_id=member_id,
                valid_from=group.valid_from,
                valid_to=group.valid_to,
                source_kind="MANUAL",
            ))
        group.actual_size = len(member_ids)
        group.status = "READY" if complete else "DRAFT"
        for source_class in group.source_classes:
            if (
                source_class.population_snapshot_class_id
                == item["snapshot_class"].id
            ):
                source_class.student_count = len(member_ids)
        touch_group(
            group,
            user_id=user_id,
            event_code="COMPOSITION_UPDATED",
            details={
                "actual_size": len(member_ids),
                "complete": complete,
            },
        )
    return {
        "complete": complete,
        "assigned_count": len(normalized_assignments),
        "student_count": len(eligible_ids),
        "group_sizes": {
            group.id: len(members_by_group[group.id])
            for group in groups
        },
    }


def materialize_default_teaching_groups(
    *,
    version,
    snapshot,
    plans,
    user_id,
):
    if version.status != "DRAFT" or snapshot is None:
        return 0
    existing_keys = {
        (
            group.source_plan_line_id,
            source.population_snapshot_class_id,
        )
        for group in (
            TeachingGroup.query
            .filter(
                TeachingGroup.tariff_version_id == version.id,
                TeachingGroup.status != "CLOSED",
                TeachingGroup.group_type != "METAGROUP",
            )
            .all()
        )
        for source in group.source_classes
    }
    academic_year = version.tariff_cycle.academic_year
    created = 0
    for education_level in ("NOO", "OOO", "SOO"):
        matrix = build_class_plan_matrix(
            snapshot,
            plans,
            education_level,
        )
        columns_by_key = {
            column["key"]: column
            for column in matrix["columns"]
            if not column["is_unassigned"]
        }
        for section in matrix["sections"]:
            for row in section["rows"]:
                for column_key, cell in row["cells"].items():
                    column = columns_by_key.get(column_key)
                    if column is None:
                        continue
                    line = cell["line"]
                    snapshot_class = column["snapshot_class"]
                    key = (line.id, snapshot_class.id)
                    if key in existing_keys:
                        continue
                    member_ids = set(column["member_ids"])
                    if not member_ids:
                        continue
                    is_full_class = member_ids == {
                        item.id for item in snapshot_class.enrollments
                    }
                    group = TeachingGroup(
                        tariff_version_id=version.id,
                        education_activity_id=line.education_activity_id,
                        group_type=_group_type(
                            line.education_plan.plan_kind,
                            1,
                            is_full_class,
                        ),
                        code=_unique_group_code(
                            version.id,
                            line.id,
                            snapshot_class.id,
                            1,
                        ),
                        name=(
                            f"{snapshot_class.name_snapshot} · "
                            f"{line.education_activity.name}"
                        ),
                        composition_mode="PERSONAL",
                        building_id=snapshot_class.building_id,
                        planned_size=len(member_ids),
                        actual_size=len(member_ids),
                        valid_from=academic_year.start_date,
                        valid_to=academic_year.end_date,
                        source_plan_line_id=line.id,
                        status="READY",
                        created_by_user_id=user_id,
                        updated_by_user_id=user_id,
                    )
                    db.session.add(group)
                    db.session.flush()
                    db.session.add(TeachingGroupClass(
                        teaching_group_id=group.id,
                        population_snapshot_class_id=snapshot_class.id,
                        relation_kind="FULL" if is_full_class else "PARTIAL",
                        student_count=len(member_ids),
                    ))
                    for member_id in sorted(member_ids):
                        db.session.add(TeachingGroupMember(
                            teaching_group_id=group.id,
                            snapshot_enrollment_id=member_id,
                            valid_from=academic_year.start_date,
                            valid_to=academic_year.end_date,
                            source_kind="AUTO",
                        ))
                    add_group_history(
                        group,
                        "MATRIX_DEFAULT_CREATED",
                        user_id,
                        {
                            "group_count": 1,
                            "snapshot_class_id": snapshot_class.id,
                            "plan_id": column["plan"].id,
                        },
                    )
                    existing_keys.add(key)
                    created += 1
    return created


__all__ = [
    "AUTO_GROUP_CODE_PREFIX",
    "build_group_composition_workspace",
    "build_teaching_group_matrix",
    "materialize_default_teaching_groups",
    "replace_group_composition_assignments",
    "replace_teaching_group_count",
]
