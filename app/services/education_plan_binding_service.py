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

    bindings = (
        EducationPlanBinding.query
        .join(EducationPlan)
        .filter(
            EducationPlanBinding.population_snapshot_class_id
            == snapshot_class.id,
            EducationPlan.tariff_version_id == plan.tariff_version_id,
            EducationPlan.plan_kind == plan.plan_kind,
        )
        .all()
    )
    bindings_by_plan_id = {
        item.education_plan_id: item for item in bindings
    }
    allocations = {
        item.education_plan_id: effective_binding_member_ids(
            item,
            all_enrollment_ids,
        )
        for item in bindings
    }

    # An individual student has exactly one principal curriculum in a version.
    for plan_id in list(allocations):
        if plan_id != plan.id:
            allocations[plan_id] -= selected_enrollment_ids
    allocations[plan.id] = selected_enrollment_ids

    for plan_id, member_ids in allocations.items():
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

    return bindings_by_plan_id.get(plan.id)


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
        if not new_member_ids:
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
    "carry_forward_plan_bindings",
    "class_plan_allocations",
    "effective_binding_member_ids",
    "plan_matches_snapshot_class",
    "replace_plan_binding_members",
]
