from app.core.extensions import db
from app.models import (
    EducationPlan,
    EducationPlanBinding,
    EducationPlanBindingMember,
    PopulationSnapshotClass,
    PopulationSnapshotEnrollment,
)


class PlanBindingValidationError(ValueError):
    pass


EDUCATION_LEVEL_GRADES = {
    "NOO": set(range(1, 5)),
    "OOO": set(range(5, 10)),
    "SOO": {10, 11},
}


def plan_matches_snapshot_class(plan, snapshot_class):
    allowed_grades = EDUCATION_LEVEL_GRADES.get(plan.education_level)
    if allowed_grades and snapshot_class.grade_snapshot not in allowed_grades:
        return False
    if (
        plan.building_id is not None
        and snapshot_class.building_id != plan.building_id
    ):
        return False
    return True


def effective_binding_member_ids(binding, enrollment_ids=None):
    if binding.binding_mode == "CLASS":
        if enrollment_ids is not None:
            return set(enrollment_ids)
        return {
            item.id
            for item in binding.population_snapshot_class.enrollments
        }
    return {item.snapshot_enrollment_id for item in binding.members}


def _replace_binding_rows(
    binding,
    member_ids,
    all_enrollment_ids,
    *,
    user_id,
    bump_revision=True,
):
    binding.binding_mode = (
        "CLASS" if member_ids == all_enrollment_ids else "STUDENTS"
    )
    binding.updated_by_user_id = user_id
    if bump_revision:
        binding.revision += 1
    EducationPlanBindingMember.query.filter_by(
        education_plan_binding_id=binding.id
    ).delete(synchronize_session=False)
    if binding.binding_mode == "STUDENTS":
        for enrollment_id in sorted(member_ids):
            db.session.add(EducationPlanBindingMember(
                education_plan_binding_id=binding.id,
                snapshot_enrollment_id=enrollment_id,
                created_by_user_id=user_id,
            ))


def replace_plan_binding_members(
    plan,
    snapshot_class,
    selected_enrollment_ids,
    *,
    user_id,
):
    if plan.tariff_version.status != "DRAFT":
        raise PlanBindingValidationError(
            "Привязки можно изменять только в рабочей версии."
        )
    if plan.plan_kind != "CURRICULUM":
        raise PlanBindingValidationError(
            "На этом экране назначаются только основные учебные планы."
        )
    if (
        snapshot_class.population_snapshot.tariff_version_id
        != plan.tariff_version_id
    ):
        raise PlanBindingValidationError(
            "Учебный план и класс относятся к разным версиям."
        )
    if not plan_matches_snapshot_class(plan, snapshot_class):
        raise PlanBindingValidationError(
            "Учебный план не соответствует уровню или зданию класса."
        )

    all_enrollment_ids = {
        item.id for item in snapshot_class.enrollments
    }
    selected_enrollment_ids = set(selected_enrollment_ids)
    unknown_ids = selected_enrollment_ids - all_enrollment_ids
    if unknown_ids:
        raise PlanBindingValidationError(
            "В списке выбраны ученики из другого класса."
        )

    plans = [
        item
        for item in (
        EducationPlan.query
        .filter_by(
            tariff_version_id=plan.tariff_version_id,
            plan_kind="CURRICULUM",
        )
        .all()
        )
        if plan_matches_snapshot_class(item, snapshot_class)
    ]
    allocations, student_plan_ids = class_plan_allocations(
        snapshot_class,
        plans,
    )
    current_target_ids = allocations.get(plan.id, set())
    for enrollment_id in current_target_ids - selected_enrollment_ids:
        student_plan_ids.pop(enrollment_id, None)
    for enrollment_id in selected_enrollment_ids:
        student_plan_ids[enrollment_id] = plan.id

    return replace_class_plan_assignments(
        snapshot_class,
        plans,
        student_plan_ids,
        user_id=user_id,
    ).get(plan.id)


def replace_class_plan_assignments(
    snapshot_class,
    plans,
    assignment_by_enrollment_id,
    *,
    user_id,
):
    plans = list(plans)
    if not plans:
        raise PlanBindingValidationError(
            "Для класса нет подходящих учебных планов."
        )
    version_ids = {item.tariff_version_id for item in plans}
    if len(version_ids) != 1:
        raise PlanBindingValidationError(
            "Учебные планы относятся к разным версиям."
        )
    version_id = next(iter(version_ids))
    if plans[0].tariff_version.status != "DRAFT":
        raise PlanBindingValidationError(
            "Привязки можно изменять только в рабочей версии."
        )
    if (
        snapshot_class.population_snapshot.tariff_version_id
        != version_id
    ):
        raise PlanBindingValidationError(
            "Учебные планы и класс относятся к разным версиям."
        )
    if any(item.plan_kind != "CURRICULUM" for item in plans):
        raise PlanBindingValidationError(
            "К классу назначается комплект основного учебного плана."
        )
    if any(
        not plan_matches_snapshot_class(item, snapshot_class)
        for item in plans
    ):
        raise PlanBindingValidationError(
            "Один из планов не соответствует уровню или зданию класса."
        )

    all_enrollment_ids = {
        item.id for item in snapshot_class.enrollments
    }
    assignments = {
        int(enrollment_id): int(plan_id)
        for enrollment_id, plan_id
        in dict(assignment_by_enrollment_id).items()
        if plan_id is not None
    }
    unknown_enrollment_ids = set(assignments) - all_enrollment_ids
    if unknown_enrollment_ids:
        raise PlanBindingValidationError(
            "В назначениях есть ученики из другого класса."
        )
    plans_by_id = {item.id: item for item in plans}
    unknown_plan_ids = set(assignments.values()) - set(plans_by_id)
    if unknown_plan_ids:
        raise PlanBindingValidationError(
            "Выбран недоступный учебный план."
        )

    bindings = (
        EducationPlanBinding.query
        .join(EducationPlan)
        .filter(
            EducationPlanBinding.population_snapshot_class_id
            == snapshot_class.id,
            EducationPlan.tariff_version_id == version_id,
            EducationPlan.plan_kind == "CURRICULUM",
        )
        .all()
    )
    bindings_by_plan_id = {
        item.education_plan_id: item for item in bindings
    }
    allocations = {
        plan_id: {
            enrollment_id
            for enrollment_id, assigned_plan_id in assignments.items()
            if assigned_plan_id == plan_id
        }
        for plan_id in plans_by_id
    }

    for plan_id in set(bindings_by_plan_id) | set(allocations):
        member_ids = allocations.get(plan_id, set())
        binding = bindings_by_plan_id.get(plan_id)
        if not member_ids:
            if binding is not None:
                db.session.delete(binding)
            continue
        is_new = binding is None
        if is_new:
            binding = EducationPlanBinding(
                education_plan_id=plan_id,
                population_snapshot_class_id=snapshot_class.id,
                binding_mode="STUDENTS",
                revision=1,
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
            )
            db.session.add(binding)
            db.session.flush()
        _replace_binding_rows(
            binding,
            member_ids,
            all_enrollment_ids,
            user_id=user_id,
            bump_revision=not is_new,
        )
        bindings_by_plan_id[plan_id] = binding

    return bindings_by_plan_id


def assign_class_plan(
    snapshot_class,
    plans,
    plan_id,
    *,
    user_id,
):
    """Assign one plan to a whole class, including a class with no pupils."""
    plans = list(plans)
    plans_by_id = {item.id: item for item in plans}
    if plan_id is not None and plan_id not in plans_by_id:
        raise PlanBindingValidationError(
            "Выбран недоступный учебный план."
        )

    enrollment_ids = {
        item.id for item in snapshot_class.enrollments
    }
    bindings = replace_class_plan_assignments(
        snapshot_class,
        plans,
        (
            {enrollment_id: plan_id for enrollment_id in enrollment_ids}
            if plan_id is not None else {}
        ),
        user_id=user_id,
    )
    if enrollment_ids or plan_id is None:
        return bindings.get(plan_id) if plan_id is not None else None

    binding = EducationPlanBinding(
        education_plan_id=plan_id,
        population_snapshot_class_id=snapshot_class.id,
        binding_mode="CLASS",
        revision=1,
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    db.session.add(binding)
    db.session.flush()
    return binding


def class_level_plan_ids(snapshot_class, plans):
    plan_ids = [item.id for item in plans]
    if not plan_ids:
        return set()
    return {
        plan_id
        for plan_id, in (
            db.session.query(EducationPlanBinding.education_plan_id)
            .filter(
                EducationPlanBinding.population_snapshot_class_id
                == snapshot_class.id,
                EducationPlanBinding.education_plan_id.in_(plan_ids),
                EducationPlanBinding.binding_mode == "CLASS",
            )
            .all()
        )
    }


def class_plan_allocations(snapshot_class, plans):
    enrollment_ids = {
        item.id for item in snapshot_class.enrollments
    }
    bindings = (
        EducationPlanBinding.query
        .filter(
            EducationPlanBinding.population_snapshot_class_id
            == snapshot_class.id,
            EducationPlanBinding.education_plan_id.in_(
                [plan.id for plan in plans]
            ),
        )
        .all()
        if plans else []
    )
    allocations = {
        binding.education_plan_id: effective_binding_member_ids(
            binding,
            enrollment_ids,
        )
        for binding in bindings
    }
    student_plan_ids = {}
    for plan_id, member_ids in allocations.items():
        for enrollment_id in member_ids:
            student_plan_ids[enrollment_id] = plan_id
    return allocations, student_plan_ids


def carry_forward_plan_bindings(previous_snapshot, new_snapshot, *, user_id):
    if previous_snapshot is None:
        return

    new_classes = {
        item.source_school_class_id: item
        for item in new_snapshot.classes
    }
    old_classes = {
        item.id: item
        for item in previous_snapshot.classes
    }
    old_class_ids = list(old_classes)
    bindings = (
        EducationPlanBinding.query
        .filter(
            EducationPlanBinding.population_snapshot_class_id.in_(
                old_class_ids
            )
        )
        .all()
        if old_class_ids else []
    )

    for old_binding in bindings:
        old_class = old_classes[old_binding.population_snapshot_class_id]
        new_class = new_classes.get(old_class.source_school_class_id)
        if new_class is None:
            continue
        old_member_ids = effective_binding_member_ids(old_binding)
        old_child_ids = {
            enrollment.source_child_id
            for enrollment in old_class.enrollments
            if enrollment.id in old_member_ids
        }
        new_member_ids = {
            enrollment.id
            for enrollment in new_class.enrollments
            if (
                old_binding.binding_mode == "CLASS"
                or enrollment.source_child_id in old_child_ids
            )
        }
        if not new_member_ids and old_binding.binding_mode != "CLASS":
            continue
        binding = EducationPlanBinding(
            education_plan_id=old_binding.education_plan_id,
            population_snapshot_class_id=new_class.id,
            binding_mode="STUDENTS",
            revision=1,
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        db.session.add(binding)
        db.session.flush()
        _replace_binding_rows(
            binding,
            new_member_ids,
            {item.id for item in new_class.enrollments},
            user_id=user_id,
            bump_revision=False,
        )


__all__ = [
    "EDUCATION_LEVEL_GRADES",
    "PlanBindingValidationError",
    "assign_class_plan",
    "carry_forward_plan_bindings",
    "class_level_plan_ids",
    "class_plan_allocations",
    "effective_binding_member_ids",
    "plan_matches_snapshot_class",
    "replace_class_plan_assignments",
    "replace_plan_binding_members",
]
