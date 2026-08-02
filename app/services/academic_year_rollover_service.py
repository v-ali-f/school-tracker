from dataclasses import dataclass

from app.core.extensions import db
from app.models import (
    EducationPlan,
    TariffCycle,
)
from app.services.education_plan_service import (
    clone_plan_bundle,
    create_plan_bundle,
    ensure_draft_tariff_version,
    plan_scope_code,
)


@dataclass(frozen=True)
class AcademicYearRolloverResult:
    plans_created: int


_SOURCE_VERSION_PRIORITY = {
    "EFFECTIVE": 6,
    "APPROVED": 5,
    "APPROVAL": 4,
    "VALIDATION": 3,
    "DRAFT": 2,
    "SUPERSEDED": 1,
    "ARCHIVED": 0,
}


def _source_version(cycle):
    versions = list(cycle.versions)
    if not versions:
        return None
    return max(
        versions,
        key=lambda item: (
            _SOURCE_VERSION_PRIORITY.get(item.status, -1),
            item.version_no,
            item.id,
        ),
    )


def _copy_plan_bundles(source_year, target_year, *, user_id):
    created = 0
    source_cycles = (
        TariffCycle.query
        .filter_by(academic_year_id=source_year.id)
        .order_by(TariffCycle.id.asc())
        .all()
    )
    for source_cycle in source_cycles:
        source_version = _source_version(source_cycle)
        if source_version is None:
            continue
        _, target_version = ensure_draft_tariff_version(
            target_year,
            organization_id=source_cycle.organization_id,
            user_id=user_id,
        )
        roots = (
            EducationPlan.query
            .filter_by(
                tariff_version_id=source_version.id,
                plan_kind="CURRICULUM",
                root_plan_id=None,
            )
            .order_by(EducationPlan.id.asc())
            .all()
        )
        for source_plan in roots:
            existing = (
                EducationPlan.query
                .filter_by(
                    tariff_version_id=target_version.id,
                    plan_kind="CURRICULUM",
                    root_plan_id=None,
                    name=source_plan.name,
                    education_level=source_plan.education_level,
                    building_id=source_plan.building_id,
                )
                .first()
            )
            if existing is not None:
                continue
            target_plan = EducationPlan(
                tariff_version_id=target_version.id,
                plan_kind="CURRICULUM",
                name=source_plan.name,
                education_level=source_plan.education_level,
                building_id=source_plan.building_id,
                scope_code=plan_scope_code(
                    source_plan.education_level,
                    source_plan.building_id,
                ),
                status="DRAFT",
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
            )
            db.session.add(target_plan)
            db.session.flush()
            create_plan_bundle(target_plan, user_id=user_id)
            db.session.flush()
            clone_plan_bundle(
                source_plan,
                target_plan,
                user_id=user_id,
                class_scope_fallback=True,
            )
            created += 1
    return created


def initialize_academic_year(source_year, target_year, *, user_id):
    """Create an independent planning baseline for a new academic year.

    Only education-plan bundles are copied. Classes and student enrollments
    are created by the transfer workflow. Plan bindings, teaching groups,
    workload needs and workload assignments stay empty in the target year.
    """
    plans_created = _copy_plan_bundles(
        source_year,
        target_year,
        user_id=user_id,
    )
    return AcademicYearRolloverResult(
        plans_created=plans_created,
    )
