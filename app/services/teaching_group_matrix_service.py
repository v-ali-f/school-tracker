from datetime import datetime
from decimal import Decimal
from math import ceil

from sqlalchemy.orm import selectinload

from app.core.extensions import db
from app.models import (
    EducationPlan,
    EducationPlanLine,
    PopulationSnapshotClass,
    TeachingGroup,
    TeachingGroupClass,
    TeachingGroupCompositionApproval,
    TeachingGroupMember,
    TeachingMetagroupSource,
    WorkloadAssignment,
    WorkloadNeed,
)
from app.services.class_plan_matrix_service import (
    build_class_plan_matrix,
    preload_class_plan_matrix_data,
)
from app.services.teaching_group_service import (
    GroupValidationError,
    add_group_history,
    touch_group,
)


AUTO_GROUP_CODE_PREFIX = "AUTO_L"


def _cell_has_instructional_hours(cell):
    line = cell["line"]
    return any(
        Decimal(value or 0) > 0
        for value in (
            cell.get("hours"),
            line.weekly_hours,
            line.annual_hours,
            *(
                period.weekly_hours
                for period in line.periods
            ),
            *(
                period.annual_hours
                for period in line.periods
            ),
        )
    )


def _keep_active_matrix_cells(matrix):
    active_sections = []
    for section in matrix["sections"]:
        active_rows = []
        for row in section["rows"]:
            row["cells"] = {
                key: cell
                for key, cell in row["cells"].items()
                if _cell_has_instructional_hours(cell)
            }
            if row["cells"]:
                active_rows.append(row)
        section["rows"] = active_rows
        if active_rows:
            active_sections.append(section)
    matrix["sections"] = active_sections
    return matrix


def build_teaching_group_matrix(
    snapshot,
    plans,
    education_level,
    version_id,
    grade=None,
    building_id=None,
    allowed_building_ids=None,
    matrix_data=None,
):
    matrix = build_class_plan_matrix(
        snapshot,
        plans,
        education_level,
        grade=grade,
        building_id=building_id,
        allowed_building_ids=allowed_building_ids,
        matrix_data=matrix_data,
    )
    _keep_active_matrix_cells(matrix)
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
    approvals_by_cell = {}
    if line_ids and class_ids:
        groups = (
            TeachingGroup.query
            .options(
                selectinload(TeachingGroup.source_classes).joinedload(
                    TeachingGroupClass.population_snapshot_class
                ),
                selectinload(TeachingGroup.metagroup_membership).joinedload(
                    TeachingMetagroupSource.metagroup
                ),
            )
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
        approvals = (
            TeachingGroupCompositionApproval.query
            .filter(
                TeachingGroupCompositionApproval.tariff_version_id
                == version_id,
                TeachingGroupCompositionApproval.education_plan_line_id.in_(
                    line_ids
                ),
                TeachingGroupCompositionApproval
                .population_snapshot_class_id.in_(class_ids),
            )
            .all()
        )
        approvals_by_cell = {
            (
                approval.education_plan_line_id,
                approval.population_snapshot_class_id,
            ): approval
            for approval in approvals
        }

    divided_count = 0
    incomplete_count = 0
    approved_count = 0
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
                approval = approvals_by_cell.get((
                    cell["line"].id,
                    column["snapshot_class"].id,
                ))
                composition_approved = bool(
                    approval
                    and group_count > 1
                    and not needs_composition
                )
                cell.update({
                    "group_count": group_count,
                    "group_ids": tuple(group.id for group in groups),
                    "groups": tuple(
                        sorted(groups, key=lambda group: (group.code, group.id))
                    ),
                    "is_configured": bool(groups),
                    "needs_composition": needs_composition,
                    "composition_approval": approval,
                    "composition_approved": composition_approved,
                })
                if group_count > 1:
                    divided_count += 1
                if needs_composition:
                    incomplete_count += 1
                if composition_approved:
                    approved_count += 1

    matrix["divided_count"] = divided_count
    matrix["incomplete_count"] = incomplete_count
    matrix["approved_count"] = approved_count
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
                and _cell_has_instructional_hours(
                    row["cells"][column["key"]]
                )
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
        TeachingGroup.query
        .filter(TeachingGroup.source_group_id.in_(group_ids))
        .first()
    ):
        raise GroupValidationError(
            "Группы уже перенесены в следующую версию и не могут быть пересозданы."
        )
    if group_ids and (
        TeachingMetagroupSource.query
        .filter(
            TeachingMetagroupSource.source_group_id.in_(group_ids)
        )
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
    needs = (
        WorkloadNeed.query
        .filter(WorkloadNeed.teaching_group_id.in_(group_ids))
        .all()
        if group_ids else []
    )
    need_ids = [need.id for need in needs]
    has_active_assignments = bool(
        need_ids
        and WorkloadAssignment.query.filter(
            WorkloadAssignment.workload_need_id.in_(need_ids),
            WorkloadAssignment.status != "CANCELLED",
        ).first()
    )
    if has_active_assignments:
        raise GroupValidationError(
            "Количество групп не изменено: по этому предмету и классу уже "
            "назначена нагрузка. Сначала снимите или перенесите только эти часы."
        )
    for need in needs:
        db.session.delete(need)
    if needs:
        db.session.flush()
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
    if version.groups_editing_status != "EDITING":
        raise GroupValidationError(
            "Изменение групп закрыто. Нажмите «Внести изменения»."
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

    existing_groups = _editable_existing_groups(
        version.id,
        line.id,
        snapshot_class.id,
    )
    _clear_group_composition_approval(
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
                f"{column['class_display_name']} · "
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


def _group_teacher_names(group_ids):
    names_by_group = {
        group_id: set()
        for group_id in group_ids
    }
    if not group_ids:
        return {}
    assignments = (
        WorkloadAssignment.query
        .join(WorkloadNeed)
        .filter(
            WorkloadNeed.teaching_group_id.in_(group_ids),
            WorkloadAssignment.status != "CANCELLED",
            WorkloadAssignment.employee_user_id.isnot(None),
        )
        .all()
    )
    for assignment in assignments:
        if assignment.employee is None:
            continue
        names_by_group.setdefault(
            assignment.workload_need.teaching_group_id,
            set(),
        ).add(assignment.employee.fio)
    return {
        group_id: tuple(sorted(names, key=str.casefold))
        for group_id, names in names_by_group.items()
    }


def build_group_composition_workspace(matrix):
    group_ids = {
        group.id
        for section in matrix["sections"]
        for row in section["rows"]
        for cell in row["cells"].values()
        for group in cell.get("groups", ())
    }
    teacher_names_by_group = _group_teacher_names(group_ids)
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
                item_teacher_names = tuple(sorted({
                    teacher_name
                    for group in groups
                    for teacher_name in teacher_names_by_group.get(
                        group.id,
                        (),
                    )
                }, key=str.casefold))
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
                    "teacher_names_by_group": {
                        group.id: teacher_names_by_group.get(group.id, ())
                        for group in groups
                    },
                    "teacher_names": item_teacher_names,
                    "enrollments": enrollments,
                    "assignment_by_member_id": assignment_by_member_id,
                    "group_sizes": group_sizes,
                    "assigned_count": assigned_count,
                    "student_count": len(enrollments),
                    "complete": complete,
                    "composition_approval": cell.get(
                        "composition_approval"
                    ),
                    "composition_approved": bool(
                        cell.get("composition_approved")
                    ),
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


def _clear_group_composition_approval(
    version_id,
    plan_line_id,
    snapshot_class_id,
):
    return (
        TeachingGroupCompositionApproval.query
        .filter_by(
            tariff_version_id=version_id,
            education_plan_line_id=plan_line_id,
            population_snapshot_class_id=snapshot_class_id,
        )
        .delete(synchronize_session=False)
    )


def _sync_metagroups_for_sources(groups, *, user_id):
    source_ids = {group.id for group in groups}
    if not source_ids:
        return
    metagroup_ids = {
        link.metagroup_id
        for link in (
            TeachingMetagroupSource.query
            .filter(
                TeachingMetagroupSource.source_group_id.in_(source_ids)
            )
            .all()
        )
    }
    for metagroup_id in metagroup_ids:
        metagroup = db.session.get(TeachingGroup, metagroup_id)
        if metagroup is None or metagroup.status == "CLOSED":
            continue
        sources = [
            link.source_group
            for link in metagroup.metagroup_sources
            if link.source_group.status != "CLOSED"
        ]
        member_ids = [
            member.snapshot_enrollment_id
            for source in sources
            for member in source.members
        ]
        if len(member_ids) != len(set(member_ids)):
            raise GroupValidationError(
                "Один ученик не может входить в метагруппу дважды."
            )

        for member in list(metagroup.members):
            db.session.delete(member)
        db.session.flush()
        for member_id in sorted(member_ids):
            db.session.add(TeachingGroupMember(
                teaching_group_id=metagroup.id,
                snapshot_enrollment_id=member_id,
                valid_from=metagroup.valid_from,
                valid_to=metagroup.valid_to,
                source_kind="AUTO",
            ))

        members_by_class = {}
        for source in sources:
            for member in source.members:
                class_id = (
                    member.snapshot_enrollment
                    .population_snapshot_class_id
                )
                members_by_class[class_id] = (
                    members_by_class.get(class_id, 0) + 1
                )
        for source_class in metagroup.source_classes:
            source_class.student_count = members_by_class.get(
                source_class.population_snapshot_class_id,
                0,
            )

        metagroup.actual_size = len(member_ids)
        metagroup.planned_size = sum(
            source.planned_size
            if source.planned_size is not None
            else source.actual_size
            for source in sources
        )
        metagroup.status = (
            "READY"
            if (
                sources
                and all(
                    source.status == "READY" and bool(source.members)
                    for source in sources
                )
            )
            else "DRAFT"
        )
        touch_group(
            metagroup,
            user_id=user_id,
            event_code="METAGROUP_COMPOSITION_SYNCED",
            details={
                "source_group_ids": [source.id for source in sources],
                "actual_size": len(member_ids),
                "ready": metagroup.status == "READY",
            },
        )


def approve_group_composition(item, *, user_id):
    if not item["complete"]:
        raise GroupValidationError(
            "Сначала распределите всех учеников по группам."
        )
    groups = list(item["groups"])
    if len(groups) <= 1:
        raise GroupValidationError(
            "Согласование требуется только для предметов с делением."
        )
    version_id = groups[0].tariff_version_id
    plan_line_id = item["plan_line"].id
    snapshot_class_id = item["snapshot_class"].id
    approval = (
        TeachingGroupCompositionApproval.query
        .filter_by(
            tariff_version_id=version_id,
            education_plan_line_id=plan_line_id,
            population_snapshot_class_id=snapshot_class_id,
        )
        .first()
    )
    if approval is None:
        approval = TeachingGroupCompositionApproval(
            tariff_version_id=version_id,
            education_plan_line_id=plan_line_id,
            population_snapshot_class_id=snapshot_class_id,
        )
        db.session.add(approval)
    approval.approved_by_user_id = user_id
    approval.approved_at = datetime.utcnow()
    for group in groups:
        add_group_history(
            group,
            "COMPOSITION_APPROVED",
            user_id,
            {
                "snapshot_class_id": snapshot_class_id,
                "plan_line_id": plan_line_id,
            },
        )
    return approval


def replace_group_composition_assignments(
    item,
    assignments,
    *,
    user_id,
    allow_with_workload=False,
):
    groups = list(item["groups"])
    if not groups:
        raise GroupValidationError("Учебные группы не найдены.")
    if groups[0].tariff_version.groups_editing_status != "EDITING":
        raise GroupValidationError(
            "Изменение групп закрыто. Нажмите «Внести изменения»."
        )
    if any(
        not group.code.startswith(AUTO_GROUP_CODE_PREFIX)
        for group in groups
    ):
        raise GroupValidationError(
            "Состав можно менять только у групп, созданных из матрицы."
        )
    group_ids = {group.id for group in groups}
    if (
        not allow_with_workload
        and WorkloadNeed.query
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

    _clear_group_composition_approval(
        groups[0].tariff_version_id,
        item["plan_line"].id,
        item["snapshot_class"].id,
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
    db.session.flush()
    for group in groups:
        db.session.expire(group, ["members"])
    _sync_metagroups_for_sources(groups, user_id=user_id)
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
    matrices=None,
):
    if version.status != "DRAFT" or snapshot is None:
        return 0
    existing_groups_by_key = {}
    for group in (
        TeachingGroup.query
        .options(
            selectinload(TeachingGroup.source_classes),
            selectinload(TeachingGroup.members),
        )
        .filter(
            TeachingGroup.tariff_version_id == version.id,
            TeachingGroup.status != "CLOSED",
            TeachingGroup.group_type != "METAGROUP",
        )
        .all()
    ):
        for source in group.source_classes:
            existing_groups_by_key.setdefault(
                (
                    group.source_plan_line_id,
                    source.population_snapshot_class_id,
                ),
                [],
            ).append(group)
    academic_year = version.tariff_cycle.academic_year
    created = 0
    matrix_data = None
    if matrices is None:
        matrix_data = preload_class_plan_matrix_data(
            snapshot,
            plans,
            compact_enrollments=True,
        )
        matrices = [
            build_class_plan_matrix(
                snapshot,
                plans,
                education_level,
                matrix_data=matrix_data,
            )
            for education_level in ("NOO", "OOO", "SOO")
        ]
    for matrix in matrices:
        columns_by_key = {
            column["key"]: column
            for column in matrix["columns"]
            if not column["is_unassigned"]
        }
        for section in matrix["sections"]:
            for row in section["rows"]:
                for column_key, cell in row["cells"].items():
                    column = columns_by_key.get(column_key)
                    if (
                        column is None
                        or not _cell_has_instructional_hours(cell)
                    ):
                        continue
                    line = cell["line"]
                    snapshot_class = column["snapshot_class"]
                    key = (line.id, snapshot_class.id)
                    member_ids = set(column["member_ids"])
                    existing_groups = existing_groups_by_key.get(key, [])
                    if existing_groups:
                        if (
                            len(existing_groups) == 1
                            and existing_groups[0].code.startswith(
                                AUTO_GROUP_CODE_PREFIX
                            )
                            and all(
                                member.source_kind == "AUTO"
                                for member in existing_groups[0].members
                            )
                        ):
                            group = existing_groups[0]
                            current_member_ids = {
                                member.snapshot_enrollment_id
                                for member in group.members
                            }
                            if current_member_ids != member_ids:
                                for member in list(group.members):
                                    db.session.delete(member)
                                for member_id in sorted(member_ids):
                                    db.session.add(TeachingGroupMember(
                                        teaching_group_id=group.id,
                                        snapshot_enrollment_id=member_id,
                                        valid_from=group.valid_from,
                                        valid_to=group.valid_to,
                                        source_kind="AUTO",
                                    ))
                                is_full_class = member_ids == {
                                    item.id
                                    for item in snapshot_class.enrollments
                                }
                                group.group_type = _group_type(
                                    line.education_plan.plan_kind,
                                    1,
                                    is_full_class,
                                )
                                group.name = (
                                    f"{column['class_display_name']} · "
                                    f"{line.education_activity.name}"
                                )
                                group.planned_size = len(member_ids)
                                group.actual_size = len(member_ids)
                                group.status = "READY"
                                for source in group.source_classes:
                                    if (
                                        source.population_snapshot_class_id
                                        == snapshot_class.id
                                    ):
                                        source.relation_kind = (
                                            "FULL"
                                            if is_full_class
                                            else "PARTIAL"
                                        )
                                        source.student_count = len(member_ids)
                                touch_group(
                                    group,
                                    user_id=user_id,
                                    event_code="MATRIX_DEFAULT_SYNCED",
                                    details={
                                        "student_count": len(member_ids),
                                        "plan_id": column["plan"].id,
                                    },
                                )
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
                            f"{column['class_display_name']} · "
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
                    existing_groups_by_key[key] = [group]
                    created += 1
    return created


__all__ = [
    "AUTO_GROUP_CODE_PREFIX",
    "build_group_composition_workspace",
    "approve_group_composition",
    "build_teaching_group_matrix",
    "materialize_default_teaching_groups",
    "replace_group_composition_assignments",
    "replace_teaching_group_count",
]
