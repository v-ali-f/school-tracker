from collections import Counter
from decimal import Decimal

from app.core.extensions import db
from app.models import (
    EducationPlanLine,
    PopulationSnapshotClass,
    TariffVersion,
    TeachingGroup,
    TeachingGroupClass,
    TeachingGroupMember,
    TeachingMetagroupSource,
    WorkloadNeed,
)
from app.services.class_plan_matrix_service import (
    effective_line_weekly_hours,
)
from app.services.teaching_group_matrix_service import (
    replace_teaching_group_count,
)
from app.services.teaching_group_service import (
    GroupValidationError,
    add_group_history,
)


METAGROUP_CODE_PREFIX = "META_"
PLAN_KIND_ORDER = {
    "CURRICULUM": 0,
    "EXTRACURRICULAR": 1,
    "ADDITIONAL_EDUCATION": 2,
}


def _decimal_key(value):
    return str(Decimal(value or 0).normalize())


def _line_hours_signature(line, grade):
    if line.periods:
        periods = tuple(
            (
                item.date_from,
                item.date_to,
                _decimal_key(item.weeks_count),
                _decimal_key(item.weekly_hours),
                _decimal_key(item.annual_hours),
            )
            for item in sorted(
                line.periods,
                key=lambda item: (item.date_from, item.id),
            )
        )
        return ("PERIODS", periods)
    return (
        "ANNUAL",
        _decimal_key(effective_line_weekly_hours(line, grade)),
        _decimal_key(line.weeks_count),
        _decimal_key(line.annual_hours),
    )


def _candidate_from_group(group, column, row, section):
    member_ids = frozenset(
        member.snapshot_enrollment_id for member in group.members
    )
    if group.status not in {"DRAFT", "READY"}:
        return None
    return {
        "token": f"group:{group.id}",
        "group_id": group.id,
        "group": group,
        "activity": row["activity"],
        "plan_line": group.source_plan_line,
        "plan": column["plan"],
        "plan_kind": section["plan_kind"],
        "section_label": section["label"],
        "snapshot_class": column["snapshot_class"],
        "class_ids": frozenset(
            item.population_snapshot_class_id
            for item in group.source_classes
        ),
        "member_ids": member_ids,
        "student_count": len(member_ids),
        "label": group.name,
        "is_virtual": False,
        "is_ready": group.status == "READY" and bool(member_ids),
    }


def _candidate_from_cell(cell, column, row, section):
    member_ids = frozenset(column["member_ids"])
    if not member_ids:
        return None
    snapshot_class = column["snapshot_class"]
    return {
        "token": (
            f"cell:{cell['line'].id}:"
            f"{snapshot_class.id}:{column['plan'].id}"
        ),
        "group_id": None,
        "group": None,
        "activity": row["activity"],
        "plan_line": cell["line"],
        "plan": column["plan"],
        "plan_kind": section["plan_kind"],
        "section_label": section["label"],
        "snapshot_class": snapshot_class,
        "class_ids": frozenset({snapshot_class.id}),
        "member_ids": member_ids,
        "student_count": len(member_ids),
        "label": (
            f"{snapshot_class.name_snapshot} · "
            f"{row['activity'].name}"
        ),
        "is_virtual": True,
        "is_ready": True,
    }


def build_metagroup_workspace(matrix, version_id, activity_key=None):
    used_source_ids = {
        item.source_group_id
        for item in (
            TeachingMetagroupSource.query
            .join(
                TeachingGroup,
                TeachingGroup.id
                == TeachingMetagroupSource.metagroup_id,
            )
            .filter(
                TeachingGroup.tariff_version_id == version_id,
                TeachingGroup.status != "CLOSED",
            )
            .all()
        )
    }
    selected_grade = matrix.get("selected_grade")
    candidates = []
    if selected_grade is not None:
        for section in matrix["sections"]:
            for row in section["rows"]:
                for column in matrix["columns"]:
                    if column["is_unassigned"]:
                        continue
                    cell = row["cells"].get(column["key"])
                    if cell is None:
                        continue
                    if cell["groups"]:
                        for group in cell["groups"]:
                            if group.id in used_source_ids:
                                continue
                            candidate = _candidate_from_group(
                                group,
                                column,
                                row,
                                section,
                            )
                            if candidate is not None:
                                candidates.append(candidate)
                    else:
                        candidate = _candidate_from_cell(
                            cell,
                            column,
                            row,
                            section,
                        )
                        if candidate is not None:
                            candidates.append(candidate)

    clusters = {}
    for candidate in candidates:
        grade = candidate["snapshot_class"].grade_snapshot
        signature = _line_hours_signature(
            candidate["plan_line"],
            grade,
        )
        key = (
            grade,
            candidate["activity"].id,
            candidate["plan_kind"],
            signature,
        )
        cluster = clusters.setdefault(key, {
            "key": (
                f"grade-{grade}-activity-"
                f"{candidate['activity'].id}-"
                f"{candidate['plan_kind'].lower()}-"
                f"{len(clusters) + 1}"
            ),
            "grade": grade,
            "activity": candidate["activity"],
            "plan_kind": candidate["plan_kind"],
            "section_label": candidate["section_label"],
            "weekly_hours": effective_line_weekly_hours(
                candidate["plan_line"],
                grade,
            ),
            "candidates": [],
        })
        cluster["candidates"].append(candidate)

    available_clusters = []
    for cluster in clusters.values():
        cluster["candidates"].sort(key=lambda item: (
            item["snapshot_class"].name_snapshot.casefold(),
            item["label"].casefold(),
        ))
        if len({
            class_id
            for candidate in cluster["candidates"]
            for class_id in candidate["class_ids"]
        }) >= 2:
            available_clusters.append(cluster)
    available_clusters.sort(key=lambda item: (
        item["grade"] or 0,
        PLAN_KIND_ORDER.get(item["plan_kind"], 99),
        item["activity"].name.casefold(),
    ))
    activity_options_by_key = {}
    for cluster in available_clusters:
        key = f"{cluster['activity'].id}:{cluster['plan_kind']}"
        activity_options_by_key[key] = {
            "key": key,
            "activity": cluster["activity"],
            "plan_kind": cluster["plan_kind"],
            "section_label": cluster["section_label"],
        }
    activity_options = sorted(
        activity_options_by_key.values(),
        key=lambda item: (
            PLAN_KIND_ORDER.get(item["plan_kind"], 99),
            item["activity"].name.casefold(),
        ),
    )
    selected_activity_key = (
        activity_key
        if activity_key in activity_options_by_key
        else None
    )
    selected_clusters = [
        cluster
        for cluster in available_clusters
        if (
            selected_activity_key
            == f"{cluster['activity'].id}:{cluster['plan_kind']}"
        )
    ]

    metagroups = (
        TeachingGroup.query
        .filter_by(
            tariff_version_id=version_id,
            group_type="METAGROUP",
        )
        .filter(TeachingGroup.status != "CLOSED")
        .order_by(TeachingGroup.name.asc())
        .all()
    )
    allowed_grades = {
        item["snapshot_class"].grade_snapshot
        for item in matrix["columns"]
    }
    metagroups = [
        group
        for group in metagroups
        if (
            not selected_grade
            or any(
                link.population_snapshot_class.grade_snapshot
                == selected_grade
                for link in group.source_classes
            )
        )
        and (
            not allowed_grades
            or any(
                link.population_snapshot_class.grade_snapshot
                in allowed_grades
                for link in group.source_classes
            )
        )
    ]
    return {
        "clusters": selected_clusters,
        "metagroups": metagroups,
        "activity_options": activity_options,
        "selected_activity_key": selected_activity_key,
        "available_source_count": sum(
            len(item["candidates"]) for item in selected_clusters
        ),
    }


def _resolve_virtual_source(
    token,
    *,
    version,
    snapshot,
    plans,
    user_id,
):
    try:
        _, line_id, class_id, plan_id = token.split(":", 3)
        line_id = int(line_id)
        class_id = int(class_id)
        plan_id = int(plan_id)
    except (TypeError, ValueError) as exc:
        raise GroupValidationError(
            "Не удалось определить исходную группу."
        ) from exc
    existing = (
        TeachingGroup.query
        .join(TeachingGroupClass)
        .filter(
            TeachingGroup.tariff_version_id == version.id,
            TeachingGroup.source_plan_line_id == line_id,
            TeachingGroup.status != "CLOSED",
            TeachingGroup.group_type != "METAGROUP",
            TeachingGroupClass.population_snapshot_class_id == class_id,
        )
        .all()
    )
    if len(existing) == 1:
        return existing[0]
    if len(existing) > 1:
        raise GroupValidationError(
            "Ячейка уже разделена на несколько групп. Обновите страницу."
        )
    groups = replace_teaching_group_count(
        version=version,
        snapshot=snapshot,
        plans=plans,
        plan_line_id=line_id,
        snapshot_class_id=class_id,
        plan_id=plan_id,
        group_count=1,
        user_id=user_id,
    )
    return groups[0]


def _resolve_sources(
    source_tokens,
    *,
    version,
    snapshot,
    plans,
    user_id,
):
    sources = []
    seen_ids = set()
    for token in dict.fromkeys(source_tokens):
        if token.startswith("group:"):
            group_id = token.partition(":")[2]
            group = (
                db.session.get(TeachingGroup, int(group_id))
                if group_id.isdigit() else None
            )
        elif token.startswith("cell:"):
            group = _resolve_virtual_source(
                token,
                version=version,
                snapshot=snapshot,
                plans=plans,
                user_id=user_id,
            )
        else:
            group = None
        if group is None:
            raise GroupValidationError(
                "Одна из выбранных исходных групп не найдена."
            )
        if group.id not in seen_ids:
            seen_ids.add(group.id)
            sources.append(group)
    return sources


def _unique_metagroup_code(version_id, activity_id, grade):
    base = f"{METAGROUP_CODE_PREFIX}A{activity_id}_G{grade}"
    code = base
    index = 1
    while TeachingGroup.query.filter_by(
        tariff_version_id=version_id,
        code=code,
    ).first():
        index += 1
        code = f"{base}_{index}"
    return code


def create_metagroup(
    *,
    version,
    snapshot,
    plans,
    source_tokens,
    name,
    user_id,
):
    if version.status != "DRAFT":
        raise GroupValidationError(
            "Метагруппы можно менять только в рабочей версии."
        )
    sources = _resolve_sources(
        source_tokens,
        version=version,
        snapshot=snapshot,
        plans=plans,
        user_id=user_id,
    )
    if len(sources) < 2:
        raise GroupValidationError(
            "Выберите не менее двух классов или групп."
        )
    if any(
        group.tariff_version_id != version.id
        or group.group_type == "METAGROUP"
        or group.status not in {"DRAFT", "READY"}
        for group in sources
    ):
        raise GroupValidationError(
            "Объединять можно только действующие исходные группы этой версии."
        )
    if any(group.metagroup_membership is not None for group in sources):
        raise GroupValidationError(
            "Одна из групп уже включена в другую метагруппу."
        )
    source_ids = [group.id for group in sources]
    if WorkloadNeed.query.filter(
        WorkloadNeed.teaching_group_id.in_(source_ids)
    ).first():
        raise GroupValidationError(
            "По исходным группам уже сформирована нагрузка."
        )
    activity_ids = {
        group.education_activity_id for group in sources
    }
    if len(activity_ids) != 1:
        raise GroupValidationError(
            "Исходные группы должны относиться к одному предмету или курсу."
        )
    source_classes = {
        link.population_snapshot_class_id: link.population_snapshot_class
        for group in sources
        for link in group.source_classes
    }
    grades = {
        item.grade_snapshot for item in source_classes.values()
    }
    if len(grades) != 1:
        raise GroupValidationError(
            "Метагруппа создаётся только из одной параллели."
        )
    if len(source_classes) < 2:
        raise GroupValidationError(
            "Выберите группы не менее чем из двух разных классов."
        )
    grade = next(iter(grades))
    signatures = {
        _line_hours_signature(group.source_plan_line, grade)
        for group in sources
    }
    if len(signatures) != 1:
        raise GroupValidationError(
            "У исходных групп различается объём часов в учебном плане."
        )
    periods = {
        (group.valid_from, group.valid_to) for group in sources
    }
    if len(periods) != 1:
        raise GroupValidationError(
            "У исходных групп различаются периоды действия."
        )

    member_counter = Counter(
        member.snapshot_enrollment_id
        for group in sources
        for member in group.members
    )
    duplicates = {
        member_id for member_id, count in member_counter.items()
        if count > 1
    }
    if duplicates:
        raise GroupValidationError(
            "Один ученик не может входить в метагруппу дважды."
        )
    member_ids = sorted(member_counter)
    sources_ready = all(
        group.status == "READY" and bool(group.members)
        for group in sources
    )

    normalized_name = " ".join((name or "").split())
    if not normalized_name:
        activity_name = sources[0].education_activity.name
        normalized_name = (
            f"{activity_name} · метагруппа {grade}-х классов"
        )
    if len(normalized_name) > 255:
        raise GroupValidationError(
            "Название метагруппы не должно превышать 255 символов."
        )
    valid_from, valid_to = next(iter(periods))
    building_ids = {group.building_id for group in sources}
    department_ids = {group.department_id for group in sources}
    metagroup = TeachingGroup(
        tariff_version_id=version.id,
        education_activity_id=sources[0].education_activity_id,
        group_type="METAGROUP",
        code=_unique_metagroup_code(
            version.id,
            sources[0].education_activity_id,
            grade,
        ),
        name=normalized_name,
        composition_mode="PERSONAL",
        building_id=(
            next(iter(building_ids))
            if len(building_ids) == 1 else None
        ),
        department_id=(
            next(iter(department_ids))
            if len(department_ids) == 1 else None
        ),
        planned_size=sum(
            group.planned_size
            if group.planned_size is not None
            else group.actual_size
            for group in sources
        ),
        actual_size=len(member_ids),
        valid_from=valid_from,
        valid_to=valid_to,
        source_plan_line_id=sources[0].source_plan_line_id,
        status="READY" if sources_ready else "DRAFT",
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    db.session.add(metagroup)
    db.session.flush()

    members_by_class = Counter(
        member.snapshot_enrollment.population_snapshot_class_id
        for group in sources
        for member in group.members
    )
    for class_id in sorted(source_classes):
        db.session.add(TeachingGroupClass(
            teaching_group_id=metagroup.id,
            population_snapshot_class_id=class_id,
            relation_kind="SOURCE",
            student_count=members_by_class[class_id],
        ))
    for member_id in member_ids:
        db.session.add(TeachingGroupMember(
            teaching_group_id=metagroup.id,
            snapshot_enrollment_id=member_id,
            valid_from=valid_from,
            valid_to=valid_to,
            source_kind="AUTO",
        ))
    for index, group in enumerate(sources):
        db.session.add(TeachingMetagroupSource(
            metagroup_id=metagroup.id,
            source_group_id=group.id,
            sort_order=index,
        ))
    add_group_history(
        metagroup,
        "METAGROUP_CREATED",
        user_id,
        {
            "source_group_ids": source_ids,
            "grade": grade,
        },
    )
    return metagroup


def delete_metagroup(group):
    if group.group_type != "METAGROUP":
        raise GroupValidationError("Выбранная группа не является метагруппой.")
    if group.tariff_version.status != "DRAFT":
        raise GroupValidationError(
            "Метагруппу можно удалить только в рабочей версии."
        )
    if WorkloadNeed.query.filter_by(teaching_group_id=group.id).first():
        raise GroupValidationError(
            "По метагруппе уже сформирована нагрузка."
        )
    db.session.delete(group)


__all__ = [
    "METAGROUP_CODE_PREFIX",
    "build_metagroup_workspace",
    "create_metagroup",
    "delete_metagroup",
]
