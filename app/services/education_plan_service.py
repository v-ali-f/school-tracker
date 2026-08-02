from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.core.extensions import db
from app.models import (
    EducationPlan,
    EducationPlanLine,
    EducationPlanLinePeriod,
    EducationPlanLineScope,
    PLAN_COMPONENT_KINDS,
    SchoolClass,
    TariffCycle,
    TariffVersion,
    TariffVersionStatusHistory,
)


PLAN_COMPONENTS_BY_KIND = {
    "CURRICULUM": {
        "MANDATORY",
        "PARTICIPANT_FORMED",
        "ELECTIVE",
        "OTHER",
    },
    "EXTRACURRICULAR": {"EXTRACURRICULAR", "OTHER"},
    "ADDITIONAL_EDUCATION": {"ADDITIONAL", "OTHER"},
}

ACTIVITY_KINDS_BY_PLAN = {
    "CURRICULUM": {"SUBJECT", "COURSE", "MODULE"},
    "EXTRACURRICULAR": {"EXTRACURRICULAR_COURSE", "COURSE", "MODULE"},
    "ADDITIONAL_EDUCATION": {
        "ADDITIONAL_PROGRAM",
        "CLUB_OR_SECTION",
        "COURSE",
    },
}

PLAN_BUNDLE_KINDS = (
    "CURRICULUM",
    "EXTRACURRICULAR",
    "ADDITIONAL_EDUCATION",
)

PLAN_BUNDLE_LABELS = {
    "CURRICULUM": "Учебный план",
    "EXTRACURRICULAR": "Внеурочная деятельность",
    "ADDITIONAL_EDUCATION": "Дополнительное образование",
}


class PlanValidationError(ValueError):
    pass


class PlanLockedError(PlanValidationError):
    pass


class ConcurrentPlanUpdateError(PlanValidationError):
    pass


def plan_scope_code(education_level=None, building_id=None):
    level = (education_level or "ALL").strip().upper()
    return f"{level}:B{building_id or 0}"


def line_scope_key(
    scope_kind,
    *,
    school_class_id=None,
    grade=None,
    profile_code=None,
    building_id=None,
):
    kind = (scope_kind or "").strip().upper()
    building = building_id or 0
    if kind == "CLASS" and school_class_id:
        return f"CLASS:{school_class_id}"
    if kind == "GRADE" and grade:
        return f"GRADE:{grade}:B{building}"
    if kind == "PROFILE" and (profile_code or "").strip():
        profile = " ".join(profile_code.strip().upper().split())
        return f"PROFILE:{profile}:B{building}"
    raise PlanValidationError("Заполните целевую область строки плана.")


def parse_decimal(value, field_label, *, required=False):
    text = str(value or "").strip().replace(",", ".")
    if not text:
        if required:
            raise PlanValidationError(f"Укажите {field_label}.")
        return None
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise PlanValidationError(
            f"Поле «{field_label}» должно быть числом."
        ) from exc
    if number < 0:
        raise PlanValidationError(
            f"Поле «{field_label}» не может быть отрицательным."
        )
    return number.quantize(Decimal("0.001"))


def calculate_annual_hours(weekly_hours, weeks_count, annual_hours=None):
    if weeks_count is not None and weekly_hours is None:
        raise PlanValidationError(
            "Количество недель можно указать только вместе с часами в неделю."
        )
    if weeks_count is not None and weeks_count <= 0:
        raise PlanValidationError(
            "Количество учебных недель должно быть больше нуля."
        )
    if weekly_hours is not None and weeks_count is not None:
        return (weekly_hours * weeks_count).quantize(Decimal("0.001"))
    return annual_hours


def _cycle_query(academic_year_id, organization_id):
    query = TariffCycle.query.filter_by(academic_year_id=academic_year_id)
    if organization_id is None:
        return query.filter(TariffCycle.organization_id.is_(None))
    return query.filter(TariffCycle.organization_id == organization_id)


def ensure_draft_tariff_version(
    academic_year,
    *,
    organization_id=None,
    user_id=None,
):
    cycle = _cycle_query(academic_year.id, organization_id).first()
    if cycle is None:
        cycle = TariffCycle(
            organization_id=organization_id,
            academic_year_id=academic_year.id,
            code=f"AY_{academic_year.name.replace('/', '_')}",
            name=f"Нагрузка и тарификация {academic_year.name}",
            status="OPEN",
            opened_at=datetime.utcnow(),
            created_by_user_id=user_id,
        )
        db.session.add(cycle)
        db.session.flush()

    version = (
        TariffVersion.query
        .filter_by(tariff_cycle_id=cycle.id, status="DRAFT")
        .order_by(TariffVersion.version_no.desc())
        .first()
    )
    if version is None:
        max_no = (
            db.session.query(db.func.max(TariffVersion.version_no))
            .filter(TariffVersion.tariff_cycle_id == cycle.id)
            .scalar()
            or 0
        )
        version = TariffVersion(
            tariff_cycle_id=cycle.id,
            version_no=max_no + 1,
            version_type="BASE" if max_no == 0 else "CORRECTION",
            status="DRAFT",
            effective_from=academic_year.start_date,
            effective_to=academic_year.end_date,
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        db.session.add(version)
        db.session.flush()
        db.session.add(TariffVersionStatusHistory(
            tariff_version_id=version.id,
            from_status=None,
            to_status="DRAFT",
            changed_by_user_id=user_id,
            comment="Создание рабочей версии для планирования.",
        ))
    return cycle, version


def create_plan_bundle(root_plan, *, user_id):
    if root_plan.plan_kind != "CURRICULUM" or root_plan.root_plan_id is not None:
        raise PlanValidationError(
            "Комплект можно создать только для основного учебного плана."
        )
    if root_plan.id is None:
        db.session.flush()

    parts = {"CURRICULUM": root_plan}
    for plan_kind in PLAN_BUNDLE_KINDS[1:]:
        companion = EducationPlan(
            tariff_version_id=root_plan.tariff_version_id,
            root_plan_id=root_plan.id,
            plan_kind=plan_kind,
            name=(
                f"{root_plan.name} · {PLAN_BUNDLE_LABELS[plan_kind]}"
            )[:255],
            profile_name=root_plan.profile_name,
            education_level=root_plan.education_level,
            building_id=root_plan.building_id,
            scope_code=root_plan.scope_code,
            status=root_plan.status,
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        db.session.add(companion)
        parts[plan_kind] = companion
    return parts


def plan_bundle_root(plan):
    return plan.root_plan or plan


def plan_bundle_parts(plan):
    root = plan_bundle_root(plan)
    parts = {"CURRICULUM": root}
    parts.update({
        companion.plan_kind: companion
        for companion in root.companion_plans
    })
    return parts


def clone_plan_bundle(
    source_plan,
    target_plan,
    *,
    user_id,
    class_scope_fallback=False,
):
    source_root = plan_bundle_root(source_plan)
    target_root = plan_bundle_root(target_plan)
    if source_root.plan_kind != "CURRICULUM":
        raise PlanValidationError(
            "Копировать можно только комплект учебного плана."
        )
    if target_root.plan_kind != "CURRICULUM":
        raise PlanValidationError(
            "Целевой комплект учебного плана создан некорректно."
        )
    if source_root.education_level != target_root.education_level:
        raise PlanValidationError(
            "Исходный и новый планы должны относиться к одному уровню."
        )

    source_parts = plan_bundle_parts(source_root)
    target_parts = plan_bundle_parts(target_root)
    source_year = source_root.tariff_version.tariff_cycle.academic_year
    target_year = target_root.tariff_version.tariff_cycle.academic_year

    for plan_kind in PLAN_BUNDLE_KINDS:
        source_part = source_parts.get(plan_kind)
        target_part = target_parts.get(plan_kind)
        if source_part is None or target_part is None:
            continue
        for old_line in source_part.lines:
            new_line = EducationPlanLine(
                education_plan_id=target_part.id,
                education_activity_id=old_line.education_activity_id,
                component_kind=old_line.component_kind,
                weekly_hours=old_line.weekly_hours,
                weeks_count=old_line.weeks_count,
                annual_hours=old_line.annual_hours,
                requires_division=old_line.requires_division,
                profile_code=old_line.profile_code,
                source_line_id=old_line.id,
                sort_order=old_line.sort_order,
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
            )
            db.session.add(new_line)
            db.session.flush()

            for old_scope in old_line.scopes:
                school_class_id = None
                building_id = old_scope.building_id
                scope_kind = old_scope.scope_kind
                grade = old_scope.grade
                if old_scope.scope_kind == "CLASS":
                    source_class = old_scope.school_class
                    target_class = (
                        SchoolClass.query
                        .filter_by(
                            academic_year_id=target_year.id,
                            name=source_class.name,
                            grade=source_class.grade,
                            building_id=source_class.building_id,
                            is_archived=False,
                        )
                        .first()
                    )
                    if target_class is None:
                        if not class_scope_fallback or source_class.grade is None:
                            raise PlanValidationError(
                                "Не найден класс "
                                f"«{source_class.name}» в учебном году "
                                f"{target_year.name}."
                            )
                        scope_kind = "GRADE"
                        grade = source_class.grade
                        building_id = source_class.building_id
                    else:
                        school_class_id = target_class.id
                        building_id = target_class.building_id
                new_line.scopes.append(EducationPlanLineScope(
                    scope_kind=scope_kind,
                    school_class_id=school_class_id,
                    grade=grade,
                    profile_code=old_scope.profile_code,
                    building_id=building_id,
                    scope_key=line_scope_key(
                        scope_kind,
                        school_class_id=school_class_id,
                        grade=grade,
                        profile_code=old_scope.profile_code,
                        building_id=building_id,
                    ),
                ))

            for old_period in old_line.periods:
                from_offset = (
                    old_period.date_from - source_year.start_date
                )
                to_offset = old_period.date_to - source_year.start_date
                new_line.periods.append(EducationPlanLinePeriod(
                    date_from=target_year.start_date + from_offset,
                    date_to=min(
                        target_year.start_date + to_offset,
                        target_year.end_date,
                    ),
                    weeks_count=old_period.weeks_count,
                    weekly_hours=old_period.weekly_hours,
                    annual_hours=old_period.annual_hours,
                ))
    return target_root


def require_plan_editable(plan, *, expected_revision=None):
    if plan.tariff_version.status != "DRAFT":
        raise PlanLockedError(
            "Корневая версия уже не является черновиком."
        )
    if plan.status != "DRAFT":
        raise PlanLockedError(
            "Для изменения сначала верните план в статус «Черновик»."
        )
    if expected_revision is not None and plan.revision != expected_revision:
        raise ConcurrentPlanUpdateError(
            "План был изменён другим пользователем. Обновите страницу."
        )


def validate_line_values(
    plan,
    activity,
    component_kind,
    weekly_hours,
    annual_hours,
    weeks_count=None,
):
    component = (component_kind or "").strip().upper()
    if component not in PLAN_COMPONENT_KINDS:
        raise PlanValidationError("Выберите допустимую часть плана.")
    if component not in PLAN_COMPONENTS_BY_KIND[plan.plan_kind]:
        raise PlanValidationError(
            "Выбранная часть не относится к этому виду плана."
        )
    if activity.activity_kind not in ACTIVITY_KINDS_BY_PLAN[plan.plan_kind]:
        raise PlanValidationError(
            "Вид дисциплины не соответствует выбранному виду плана."
        )
    if not activity.is_active:
        raise PlanValidationError("Нельзя использовать архивную дисциплину.")
    if weekly_hours is None and annual_hours is None:
        raise PlanValidationError(
            "Укажите недельные или годовые часы."
        )
    if weeks_count is not None and weekly_hours is None:
        raise PlanValidationError(
            "Количество недель требует значения часов в неделю."
        )


def validate_period_range(plan, date_from, date_to, *, exclude_period_id=None):
    if date_from is None or date_to is None:
        raise PlanValidationError("Укажите начало и окончание периода.")
    if date_to < date_from:
        raise PlanValidationError(
            "Дата окончания периода не может быть раньше даты начала."
        )

    academic_year = plan.tariff_version.tariff_cycle.academic_year
    if academic_year.start_date and date_from < academic_year.start_date:
        raise PlanValidationError("Период начинается раньше учебного года.")
    if academic_year.end_date and date_to > academic_year.end_date:
        raise PlanValidationError("Период заканчивается позже учебного года.")


def validate_no_period_overlap(
    line,
    date_from,
    date_to,
    *,
    exclude_period_id=None,
):
    query = EducationPlanLinePeriod.query.filter(
        EducationPlanLinePeriod.education_plan_line_id == line.id,
        EducationPlanLinePeriod.date_from <= date_to,
        EducationPlanLinePeriod.date_to >= date_from,
    )
    if exclude_period_id is not None:
        query = query.filter(EducationPlanLinePeriod.id != exclude_period_id)
    if query.first() is not None:
        raise PlanValidationError(
            "Период пересекается с другим периодом этой строки."
        )


def validate_plan_ready(plan):
    if not plan.lines:
        raise PlanValidationError("Добавьте хотя бы одну строку плана.")
    for line in plan.lines:
        validate_line_values(
            plan,
            line.education_activity,
            line.component_kind,
            line.weekly_hours,
            line.annual_hours,
            line.weeks_count,
        )
        if not line.scopes:
            raise PlanValidationError(
                f"У строки «{line.education_activity.name}» нет целевой области."
            )
        periods = sorted(line.periods, key=lambda item: item.date_from)
        for previous, current in zip(periods, periods[1:]):
            if previous.date_to >= current.date_from:
                raise PlanValidationError(
                    f"У строки «{line.education_activity.name}» "
                    "пересекаются периоды."
                )


def change_plan_status(plan, target_status, *, user_id, expected_revision):
    if plan.tariff_version.status != "DRAFT":
        raise PlanLockedError(
            "Корневая версия уже не является черновиком."
        )
    if expected_revision is not None and plan.revision != expected_revision:
        raise ConcurrentPlanUpdateError(
            "План был изменён другим пользователем. Обновите страницу."
        )
    target = (target_status or "").strip().upper()
    if target not in {"DRAFT", "READY"}:
        raise PlanValidationError(
            "На этапе планирования доступны статусы «Черновик» и "
            "«Готов к проверке»."
        )
    if target == plan.status:
        return plan
    if target == "READY":
        if plan.status != "DRAFT":
            raise PlanValidationError(
                "Передать на проверку можно только черновик."
            )
        validate_plan_ready(plan)
    elif plan.status != "READY":
        raise PlanValidationError(
            "Вернуть в черновик можно только план на проверке."
        )
    plan.status = target
    plan.revision += 1
    plan.updated_by_user_id = user_id
    return plan


def touch_plan(plan, *, user_id):
    plan.revision += 1
    plan.updated_by_user_id = user_id
    return plan


def plans_visible_in_buildings(query, building_ids):
    values = tuple(building_ids or ())
    if not values:
        return query.filter(db.false())
    return query.filter(EducationPlan.building_id.in_(values))


__all__ = [
    "PLAN_COMPONENTS_BY_KIND",
    "ACTIVITY_KINDS_BY_PLAN",
    "PLAN_BUNDLE_KINDS",
    "PLAN_BUNDLE_LABELS",
    "PlanValidationError",
    "PlanLockedError",
    "ConcurrentPlanUpdateError",
    "plan_scope_code",
    "line_scope_key",
    "parse_decimal",
    "ensure_draft_tariff_version",
    "create_plan_bundle",
    "clone_plan_bundle",
    "plan_bundle_root",
    "plan_bundle_parts",
    "require_plan_editable",
    "validate_line_values",
    "validate_period_range",
    "validate_no_period_overlap",
    "validate_plan_ready",
    "change_plan_status",
    "touch_plan",
    "plans_visible_in_buildings",
]
