import hashlib
import json
from collections import Counter, defaultdict
from datetime import date

from app.core.extensions import db
from app.models import (
    Child,
    ChildEnrollment,
    EducationPlanLine,
    PopulationSnapshot,
    PopulationSnapshotClass,
    PopulationSnapshotEnrollment,
    SchoolClass,
    TeachingGroup,
    TeachingGroupClass,
    TeachingGroupHistory,
    TeachingGroupMember,
)


GROUP_TYPES_BY_PLAN_KIND = {
    "CURRICULUM": {
        "CLASS",
        "SUBGROUP",
        "METAGROUP",
        "INDIVIDUAL",
    },
    "EXTRACURRICULAR": {
        "EXTRACURRICULAR_GROUP",
        "METAGROUP",
        "INDIVIDUAL",
    },
    "ADDITIONAL_EDUCATION": {
        "ADDITIONAL_GROUP",
        "METAGROUP",
        "INDIVIDUAL",
    },
}


class GroupValidationError(ValueError):
    pass


class GroupLockedError(GroupValidationError):
    pass


class ConcurrentGroupUpdateError(GroupValidationError):
    pass


def current_population_snapshot(tariff_version_id):
    return (
        PopulationSnapshot.query
        .filter_by(
            tariff_version_id=tariff_version_id,
            status="CURRENT",
        )
        .first()
    )


def _population_checksum(digest_rows):
    return hashlib.sha256(
        "\n".join(sorted(digest_rows)).encode("utf-8")
    ).hexdigest()


def _live_population_checksum(academic_year_id):
    classes = (
        SchoolClass.query
        .filter_by(
            academic_year_id=academic_year_id,
            is_archived=False,
        )
        .order_by(SchoolClass.id.asc())
        .all()
    )
    digest_rows = [
        (
            f"CLASS:{school_class.id}:{school_class.name}:"
            f"{school_class.grade}:{school_class.building_id or ''}"
        )
        for school_class in classes
    ]
    class_ids = [school_class.id for school_class in classes]
    if class_ids:
        enrollments = (
            ChildEnrollment.query
            .filter(
                ChildEnrollment.academic_year_id == academic_year_id,
                ChildEnrollment.school_class_id.in_(class_ids),
                ChildEnrollment.status == "ACTIVE",
                ChildEnrollment.ended_at.is_(None),
            )
            .all()
        )
        digest_rows.extend(
            (
                f"{enrollment.school_class_id}:"
                f"{enrollment.child_id}:{enrollment.id}:"
                f"{enrollment.status}"
            )
            for enrollment in enrollments
        )
    return _population_checksum(digest_rows)


def population_registry_status(tariff_version, snapshot=None):
    academic_year_id = tariff_version.tariff_cycle.academic_year_id
    class_count = (
        db.session.query(db.func.count(SchoolClass.id))
        .filter(
            SchoolClass.academic_year_id == academic_year_id,
            SchoolClass.is_archived.is_(False),
        )
        .scalar()
        or 0
    )
    student_count = (
        db.session.query(db.func.count(ChildEnrollment.id))
        .join(
            SchoolClass,
            SchoolClass.id == ChildEnrollment.school_class_id,
        )
        .filter(
            ChildEnrollment.academic_year_id == academic_year_id,
            ChildEnrollment.status == "ACTIVE",
            ChildEnrollment.ended_at.is_(None),
            SchoolClass.academic_year_id == academic_year_id,
            SchoolClass.is_archived.is_(False),
        )
        .scalar()
        or 0
    )

    snapshot_class_count = 0
    snapshot_student_count = 0
    if snapshot is not None:
        snapshot_class_count, snapshot_student_count = (
            db.session.query(
                db.func.count(PopulationSnapshotClass.id),
                db.func.coalesce(
                    db.func.sum(PopulationSnapshotClass.student_count),
                    0,
                ),
            )
            .filter(
                PopulationSnapshotClass.population_snapshot_id
                == snapshot.id
            )
            .one()
        )

    live_checksum = (
        _live_population_checksum(academic_year_id)
        if snapshot is not None
        else None
    )
    structure_changed = (
        snapshot is not None
        and live_checksum != snapshot.checksum
    )

    return {
        "class_count": int(class_count),
        "student_count": int(student_count),
        "snapshot_class_count": int(snapshot_class_count),
        "snapshot_student_count": int(snapshot_student_count),
        "structure_changed": structure_changed,
        "is_stale": (
            snapshot is not None
            and (
                class_count != snapshot_class_count
                or student_count != snapshot_student_count
                or structure_changed
            )
        ),
    }


def build_population_snapshot(tariff_version, *, user_id, snapshot_date=None):
    if tariff_version.status != "DRAFT":
        raise GroupLockedError(
            "Снимок контингента можно обновлять только в черновой версии."
        )

    academic_year = tariff_version.tariff_cycle.academic_year
    classes = (
        SchoolClass.query
        .filter_by(
            academic_year_id=academic_year.id,
            is_archived=False,
        )
        .order_by(SchoolClass.grade.asc(), SchoolClass.name.asc())
        .all()
    )
    rows = []
    digest_rows = []
    for school_class in classes:
        building_name = None
        if school_class.building is not None:
            building_name = (
                school_class.building.short_name
                or school_class.building.name
            )
        digest_rows.append(
            f"CLASS:{school_class.id}:{school_class.name}:"
            f"{school_class.grade}:{school_class.building_id or ''}"
        )
        enrollments = (
            ChildEnrollment.query
            .filter(
                ChildEnrollment.academic_year_id == academic_year.id,
                ChildEnrollment.school_class_id == school_class.id,
                ChildEnrollment.status == "ACTIVE",
                ChildEnrollment.ended_at.is_(None),
            )
            .join(ChildEnrollment.child)
            .order_by(
                Child.last_name.asc(),
                Child.first_name.asc(),
                Child.middle_name.asc(),
            )
            .all()
        )
        enrollment_rows = []
        for enrollment in enrollments:
            child = enrollment.child
            started_on = (
                enrollment.enrolled_at.date()
                if enrollment.enrolled_at else None
            )
            enrollment_rows.append({
                "source_child_id": child.id,
                "source_enrollment_id": enrollment.id,
                "fio_snapshot": child.fio,
                "status_snapshot": enrollment.status,
                "started_on": started_on,
                "ended_on": (
                    enrollment.ended_at.date()
                    if enrollment.ended_at else None
                ),
            })
            digest_rows.append(
                f"{school_class.id}:{child.id}:{enrollment.id}:"
                f"{enrollment.status}"
            )
        rows.append((school_class, enrollment_rows, building_name))

    current = current_population_snapshot(tariff_version.id)
    if current is not None:
        current.status = "SUPERSEDED"
        db.session.flush()
    max_revision = (
        db.session.query(db.func.max(PopulationSnapshot.revision_no))
        .filter(PopulationSnapshot.tariff_version_id == tariff_version.id)
        .scalar()
        or 0
    )
    checksum = _population_checksum(digest_rows)
    snapshot = PopulationSnapshot(
        tariff_version_id=tariff_version.id,
        revision_no=max_revision + 1,
        snapshot_date=snapshot_date or date.today(),
        status="CURRENT",
        source_kind="REGISTRY",
        checksum=checksum,
        created_by_user_id=user_id,
    )
    db.session.add(snapshot)
    db.session.flush()

    for school_class, enrollment_rows, building_name in rows:
        snapshot_class = PopulationSnapshotClass(
            population_snapshot_id=snapshot.id,
            source_school_class_id=school_class.id,
            name_snapshot=school_class.name,
            grade_snapshot=school_class.grade,
            building_id=school_class.building_id,
            building_name_snapshot=building_name,
            student_count=len(enrollment_rows),
        )
        db.session.add(snapshot_class)
        db.session.flush()
        for enrollment_row in enrollment_rows:
            db.session.add(PopulationSnapshotEnrollment(
                population_snapshot_class_id=snapshot_class.id,
                **enrollment_row,
            ))
    db.session.flush()
    if current is not None:
        from app.services.education_plan_binding_service import (
            carry_forward_plan_bindings,
        )

        carry_forward_plan_bindings(
            current,
            snapshot,
            user_id=user_id,
        )
    return snapshot


def require_group_editable(group, *, expected_revision=None):
    if group.tariff_version.status != "DRAFT":
        raise GroupLockedError(
            "Корневая версия уже не является черновиком."
        )
    if group.tariff_version.groups_editing_status != "EDITING":
        raise GroupLockedError(
            "Изменение групп закрыто. Нажмите «Внести изменения»."
        )
    if group.status != "DRAFT":
        raise GroupLockedError(
            "Для изменения сначала верните группу в статус «Черновик»."
        )
    if group.metagroup_membership is not None:
        raise GroupLockedError(
            "Группа входит в метагруппу. Сначала удалите метагруппу."
        )
    if expected_revision is not None and group.revision != expected_revision:
        raise ConcurrentGroupUpdateError(
            "Группа была изменена другим пользователем. Обновите страницу."
        )


def normalize_group_code(value):
    return "_".join((value or "").strip().upper().split())


def validate_group_period(plan_line, valid_from, valid_to):
    if valid_from is None or valid_to is None:
        raise GroupValidationError("Укажите период действия группы.")
    if valid_to < valid_from:
        raise GroupValidationError(
            "Дата окончания группы не может быть раньше даты начала."
        )
    year = plan_line.education_plan.tariff_version.tariff_cycle.academic_year
    if year.start_date and valid_from < year.start_date:
        raise GroupValidationError(
            "Группа начинается раньше выбранного учебного года."
        )
    if year.end_date and valid_to > year.end_date:
        raise GroupValidationError(
            "Группа заканчивается позже выбранного учебного года."
        )


def validate_group_type(plan_line, group_type):
    allowed = GROUP_TYPES_BY_PLAN_KIND[
        plan_line.education_plan.plan_kind
    ]
    if group_type not in allowed:
        raise GroupValidationError(
            "Тип группы не соответствует виду исходного плана."
        )


def validate_group_sources(group_type, snapshot_classes):
    count = len(snapshot_classes)
    if group_type in {"CLASS", "SUBGROUP", "INDIVIDUAL"} and count != 1:
        raise GroupValidationError(
            "Для этого типа выберите ровно один исходный класс."
        )
    if group_type == "METAGROUP" and count < 2:
        raise GroupValidationError(
            "Метагруппа должна включать не менее двух исходных классов."
        )
    if group_type in {
        "EXTRACURRICULAR_GROUP",
        "ADDITIONAL_GROUP",
    } and count < 1:
        raise GroupValidationError(
            "Выберите хотя бы один исходный класс."
        )


def validate_group_members(
    group_type,
    composition_mode,
    snapshot_classes,
    snapshot_enrollments,
    actual_size,
):
    if composition_mode not in {"PERSONAL", "COUNT_ONLY"}:
        raise GroupValidationError("Выберите способ ведения состава.")
    class_ids = {item.id for item in snapshot_classes}
    if any(
        item.population_snapshot_class_id not in class_ids
        for item in snapshot_enrollments
    ):
        raise GroupValidationError(
            "В составе есть обучающийся не из выбранного класса."
        )
    if composition_mode == "PERSONAL":
        if not snapshot_enrollments:
            raise GroupValidationError(
                "Добавьте хотя бы одного обучающегося в состав."
            )
        if group_type == "INDIVIDUAL" and len(snapshot_enrollments) != 1:
            raise GroupValidationError(
                "Индивидуальная группа должна содержать одного обучающегося."
            )
    elif snapshot_enrollments:
        raise GroupValidationError(
            "Для режима «Только численность» поимённый состав не заполняется."
        )
    elif actual_size is None:
        raise GroupValidationError("Укажите фактическую численность.")


def validate_member_conflicts(
    *,
    tariff_version_id,
    plan_line_id,
    member_entries,
    valid_from,
    valid_to,
    exclude_group_id=None,
):
    child_ids = {item.source_child_id for item in member_entries}
    if not child_ids:
        return
    query = (
        TeachingGroupMember.query
        .join(TeachingGroup)
        .join(PopulationSnapshotEnrollment)
        .filter(
            TeachingGroup.tariff_version_id == tariff_version_id,
            TeachingGroup.source_plan_line_id == plan_line_id,
            TeachingGroup.status != "CLOSED",
            TeachingGroup.valid_from <= valid_to,
            TeachingGroup.valid_to >= valid_from,
            PopulationSnapshotEnrollment.source_child_id.in_(child_ids),
        )
    )
    if exclude_group_id is not None:
        query = query.filter(TeachingGroup.id != exclude_group_id)
    conflict = query.first()
    if conflict is not None:
        raise GroupValidationError(
            f"Обучающийся «{conflict.snapshot_enrollment.fio_snapshot}» "
            "уже включён в другую параллельную группу этой строки плана."
        )


def replace_group_composition(
    group,
    *,
    snapshot_classes,
    snapshot_enrollments,
    actual_size,
    user_id,
):
    group.source_classes.clear()
    group.members.clear()
    members_by_class = Counter(
        item.population_snapshot_class_id
        for item in snapshot_enrollments
    )
    for snapshot_class in snapshot_classes:
        if group.composition_mode == "PERSONAL":
            student_count = members_by_class[snapshot_class.id]
        else:
            student_count = None
        relation_kind = (
            "FULL"
            if student_count == snapshot_class.student_count
            and group.composition_mode == "PERSONAL"
            else "PARTIAL"
            if group.composition_mode == "PERSONAL"
            else "SOURCE"
        )
        group.source_classes.append(TeachingGroupClass(
            population_snapshot_class_id=snapshot_class.id,
            relation_kind=relation_kind,
            student_count=student_count,
        ))
    for enrollment in snapshot_enrollments:
        group.members.append(TeachingGroupMember(
            snapshot_enrollment_id=enrollment.id,
            valid_from=group.valid_from,
            valid_to=group.valid_to,
            source_kind=(
                "AUTO" if group.group_type == "CLASS" else "MANUAL"
            ),
        ))
    group.actual_size = (
        len(snapshot_enrollments)
        if group.composition_mode == "PERSONAL"
        else actual_size or 0
    )
    group.updated_by_user_id = user_id


def add_group_history(group, event_code, user_id, details=None):
    payload = (
        json.dumps(details, ensure_ascii=False, sort_keys=True)
        if details is not None else None
    )
    db.session.add(TeachingGroupHistory(
        teaching_group=group,
        event_code=event_code,
        details=payload,
        changed_by_user_id=user_id,
    ))


def touch_group(group, *, user_id, event_code, details=None):
    group.revision += 1
    group.updated_by_user_id = user_id
    add_group_history(group, event_code, user_id, details)


def validate_group_ready(group):
    if not group.source_classes:
        raise GroupValidationError("У группы нет исходных классов.")
    if group.actual_size <= 0:
        raise GroupValidationError(
            "Фактическая численность группы должна быть больше нуля."
        )
    if group.composition_mode == "PERSONAL" and not group.members:
        raise GroupValidationError("Поимённый состав группы не заполнен.")


def change_group_status(
    group,
    target_status,
    *,
    user_id,
    expected_revision,
    close_reason=None,
    close_date=None,
):
    if group.tariff_version.status != "DRAFT":
        raise GroupLockedError(
            "Корневая версия уже не является черновиком."
        )
    if expected_revision is not None and group.revision != expected_revision:
        raise ConcurrentGroupUpdateError(
            "Группа была изменена другим пользователем. Обновите страницу."
        )
    target = (target_status or "").strip().upper()
    if group.metagroup_membership is not None:
        raise GroupLockedError(
            "Статус исходной группы нельзя менять, пока она входит "
            "в метагруппу."
        )
    allowed = {
        "DRAFT": {"READY", "CLOSED"},
        "READY": {"DRAFT", "CLOSED"},
        "CLOSED": set(),
    }
    if target not in allowed[group.status]:
        raise GroupValidationError("Недопустимый переход статуса группы.")
    if target == "READY":
        validate_group_ready(group)
    if target == "CLOSED":
        reason = " ".join((close_reason or "").split())
        if not reason:
            raise GroupValidationError("Укажите основание закрытия группы.")
        if close_date is None:
            raise GroupValidationError("Укажите дату закрытия группы.")
        if close_date < group.valid_from or close_date > group.valid_to:
            raise GroupValidationError(
                "Дата закрытия должна входить в период действия группы."
            )
        group.close_reason = reason
        group.valid_to = close_date
        for member in group.members:
            if member.valid_to > close_date:
                member.valid_to = close_date
    old_status = group.status
    group.status = target
    touch_group(
        group,
        user_id=user_id,
        event_code="STATUS_CHANGED",
        details={
            "from": old_status,
            "to": target,
            "close_date": (
                close_date.isoformat()
                if target == "CLOSED" and close_date is not None
                else None
            ),
        },
    )


def group_coverage(plan_line_id):
    groups = (
        TeachingGroup.query
        .filter(
            TeachingGroup.source_plan_line_id == plan_line_id,
            TeachingGroup.group_type == "SUBGROUP",
            TeachingGroup.status != "CLOSED",
        )
        .all()
    )
    expected_by_class = {}
    assigned_by_class = defaultdict(list)
    class_names = {}
    for group in groups:
        for source_link in group.source_classes:
            snapshot_class = source_link.population_snapshot_class
            source_class_id = snapshot_class.source_school_class_id
            class_names[source_class_id] = snapshot_class.name_snapshot
            expected_by_class[source_class_id] = {
                item.source_child_id
                for item in snapshot_class.enrollments
            }
        for member in group.members:
            enrollment = member.snapshot_enrollment
            source_class_id = (
                enrollment.population_snapshot_class.source_school_class_id
            )
            assigned_by_class[source_class_id].append(
                enrollment.source_child_id
            )

    result = []
    for source_class_id, expected in expected_by_class.items():
        assigned = assigned_by_class[source_class_id]
        counts = Counter(assigned)
        duplicates = {
            child_id for child_id, count in counts.items() if count > 1
        }
        missing = expected - set(assigned)
        result.append({
            "source_class_id": source_class_id,
            "class_name": class_names[source_class_id],
            "expected_count": len(expected),
            "assigned_count": len(set(assigned)),
            "missing_count": len(missing),
            "duplicate_count": len(duplicates),
            "complete": not missing and not duplicates,
        })
    return result


def plan_line_for_group(line_id):
    line = db.session.get(EducationPlanLine, line_id)
    if line is None:
        raise GroupValidationError("Выберите строку учебного плана.")
    return line


__all__ = [
    "ConcurrentGroupUpdateError",
    "GROUP_TYPES_BY_PLAN_KIND",
    "GroupLockedError",
    "GroupValidationError",
    "add_group_history",
    "build_population_snapshot",
    "change_group_status",
    "current_population_snapshot",
    "population_registry_status",
    "group_coverage",
    "normalize_group_code",
    "plan_line_for_group",
    "replace_group_composition",
    "require_group_editable",
    "touch_group",
    "validate_group_members",
    "validate_group_period",
    "validate_group_sources",
    "validate_group_type",
    "validate_member_conflicts",
]
