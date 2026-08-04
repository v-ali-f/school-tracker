from datetime import date
from decimal import Decimal

from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.core.feature_flags import WORKLOAD_WRITE, is_feature_enabled
from app.models import (
    AcademicYear,
    Building,
    EducationActivity,
    EducationPlan,
    EducationPlanLine,
    EducationPlanLinePeriod,
    EducationPlanLineScope,
    OrganizationSettings,
    PLAN_COMPONENT_LABELS,
    PLAN_COMPONENT_KINDS,
    PLAN_KIND_LABELS,
    PLAN_SCOPE_KINDS,
    PLAN_SCOPE_LABELS,
    PLAN_STATUS_LABELS,
    SchoolClass,
    TariffCycle,
    TariffVersion,
    TeachingGroup,
    WorkloadNeedSource,
)
from app.services.education_plan_service import (
    ACTIVITY_KINDS_BY_PLAN,
    PLAN_BUNDLE_KINDS,
    PLAN_BUNDLE_LABELS,
    PLAN_COMPONENTS_BY_KIND,
    PlanValidationError,
    calculate_annual_hours,
    change_plan_status,
    clone_plan_bundle,
    create_plan_bundle,
    ensure_draft_tariff_version,
    line_scope_key,
    parse_decimal,
    plan_bundle_parts,
    plan_bundle_root,
    plan_scope_code,
    plans_visible_in_buildings,
    require_plan_editable,
    touch_plan,
    validate_line_values,
    validate_period_range,
)
from app.services.workload_distribution_service import (
    WorkloadDistributionError,
    delete_plan_lines_with_dependencies,
    generate_plan_needs,
)

from .access import (
    can_use_workload_permission,
    require_workload_write,
)
from .scopes import resolve_workload_scope


PLAN_LEVEL_GRADES = {
    "NOO": tuple(range(1, 5)),
    "OOO": tuple(range(5, 10)),
    "SOO": tuple(range(10, 12)),
}
FGOS_WEEKLY_HOUR_NORMS = {
    1: (Decimal("15"), Decimal("20")),
    2: (Decimal("23"),),
    3: (Decimal("23"),),
    4: (Decimal("23"),),
    5: (Decimal("29"),),
    6: (Decimal("30"),),
    7: (Decimal("32"),),
    8: (Decimal("33"),),
    9: (Decimal("33"),),
    10: (Decimal("34"),),
    11: (Decimal("34"), Decimal("34")),
}
DEFAULT_WEEKS_COUNT = Decimal("34")


def _is_matrix_ajax_request():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _decimal_text(value):
    if value is None:
        return ""
    return format(Decimal(value), "f").rstrip("0").rstrip(".") or "0"


def _matrix_line_response(plan, line):
    return jsonify({
        "ok": True,
        "line_id": line.id,
        "revision": plan.revision,
        "weekly_hours": _decimal_text(line.weekly_hours),
        "weeks_count": _decimal_text(line.weeks_count),
        "annual_hours": _decimal_text(line.annual_hours),
        "update_url": url_for(
            "workload.plan_line_update_hours",
            plan_id=plan.id,
            line_id=line.id,
        ),
    })


def _matrix_period_response(plan, line):
    return jsonify({
        "ok": True,
        "line_id": line.id,
        "revision": plan.revision,
        "weekly_hours": _decimal_text(line.weekly_hours),
        "weeks_count": _decimal_text(line.weeks_count),
        "annual_hours": _decimal_text(line.annual_hours),
        "periods": [
            {
                "weekly_hours": _decimal_text(period.weekly_hours),
                "weeks_count": _decimal_text(period.weeks_count),
                "annual_hours": _decimal_text(period.annual_hours),
            }
            for period in sorted(line.periods, key=lambda item: item.date_from)
        ],
        "update_url": url_for(
            "workload.plan_line_update_period_hours",
            plan_id=plan.id,
            line_id=line.id,
        ),
    })


def _current_organization_id():
    organization = (
        OrganizationSettings.query
        .filter_by(is_active=True)
        .order_by(OrganizationSettings.id.asc())
        .first()
    )
    return organization.id if organization else None


def _synchronize_plan_workload(plan, line):
    has_group = (
        TeachingGroup.query
        .filter_by(
            tariff_version_id=plan.tariff_version_id,
            source_plan_line_id=line.id,
        )
        .first()
    )
    has_need = (
        WorkloadNeedSource.query
        .filter_by(education_plan_line_id=line.id)
        .first()
    )
    if has_group is not None or has_need is not None:
        generate_plan_needs(
            plan.tariff_version,
            user_id=current_user.id,
        )


def _require_plan_read():
    if not can_use_workload_permission("workload.read", current_user):
        abort(403)


def _require_plan_update():
    require_workload_write()
    if not can_use_workload_permission("workload.plan.update", current_user):
        abort(403)


def _parse_date(value):
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise PlanValidationError("Укажите корректную дату.") from exc


def _get_plan(plan_id, *, for_update=False):
    plan = EducationPlan.query.get_or_404(plan_id)
    scope = resolve_workload_scope(current_user)
    if for_update:
        _require_plan_update()
    else:
        _require_plan_read()
    if not scope.unrestricted:
        if plan.building_id is None or plan.building_id not in scope.building_ids:
            abort(403)
    return plan


def _available_activities(plan):
    organization_id = _current_organization_id()
    query = EducationActivity.query.filter(
        EducationActivity.is_active.is_(True),
        EducationActivity.activity_kind.in_(
            ACTIVITY_KINDS_BY_PLAN[plan.plan_kind]
        ),
    )
    if organization_id is None:
        query = query.filter(EducationActivity.organization_id.is_(None))
    else:
        query = query.filter(or_(
            EducationActivity.organization_id == organization_id,
            EducationActivity.organization_id.is_(None),
        ))
    return query.order_by(EducationActivity.name.asc()).all()


def _available_classes(plan):
    query = SchoolClass.query.filter_by(
        academic_year_id=plan.tariff_version.tariff_cycle.academic_year_id,
        is_archived=False,
    )
    if plan.building_id:
        query = query.filter(SchoolClass.building_id == plan.building_id)
    return query.order_by(
        SchoolClass.grade.asc(),
        SchoolClass.name.asc(),
    ).all()


def _plan_source_options():
    query = EducationPlan.query.join(TariffVersion).join(TariffCycle).filter(
        EducationPlan.plan_kind == "CURRICULUM",
        EducationPlan.root_plan_id.is_(None),
    )
    organization_id = _current_organization_id()
    if organization_id is None:
        query = query.filter(TariffCycle.organization_id.is_(None))
    else:
        query = query.filter(
            TariffCycle.organization_id == organization_id
        )
    scope = resolve_workload_scope(current_user)
    if not scope.unrestricted:
        query = plans_visible_in_buildings(query, scope.building_ids)
    return query.order_by(
        TariffCycle.academic_year_id.desc(),
        EducationPlan.name.asc(),
    ).all()


def _line_payload(plan):
    activity_id = request.form.get("education_activity_id", type=int)
    activity = (
        db.session.get(EducationActivity, activity_id)
        if activity_id else None
    )
    if activity is None:
        raise PlanValidationError("Выберите дисциплину из единого каталога.")

    component_kind = (request.form.get("component_kind") or "").strip().upper()
    weekly_hours = parse_decimal(
        request.form.get("weekly_hours"),
        "часы в неделю",
    )
    weeks_count = parse_decimal(
        request.form.get("weeks_count"),
        "количество учебных недель",
    )
    annual_hours = parse_decimal(
        request.form.get("annual_hours"),
        "часы в год",
    )
    annual_hours = calculate_annual_hours(
        weekly_hours,
        weeks_count,
        annual_hours,
    )
    validate_line_values(
        plan,
        activity,
        component_kind,
        weekly_hours,
        annual_hours,
        weeks_count,
    )

    scope_kind = (request.form.get("scope_kind") or "").strip().upper()
    if scope_kind not in PLAN_SCOPE_KINDS:
        raise PlanValidationError("Выберите целевую область.")
    school_class_id = request.form.get("school_class_id", type=int)
    grade = request.form.get("grade", type=int)
    profile_code = " ".join(
        (request.form.get("scope_profile_code") or "").split()
    ) or None
    scope_building_id = request.form.get("scope_building_id", type=int)

    if scope_kind == "CLASS":
        school_class = (
            db.session.get(SchoolClass, school_class_id)
            if school_class_id else None
        )
        if (
            school_class is None
            or school_class.academic_year_id
            != plan.tariff_version.tariff_cycle.academic_year_id
        ):
            raise PlanValidationError(
                "Выберите класс из учебного года плана."
            )
        if plan.building_id and school_class.building_id != plan.building_id:
            raise PlanValidationError("Класс относится к другому зданию.")
        grade = None
        profile_code = None
        scope_building_id = school_class.building_id
    elif scope_kind == "GRADE":
        school_class_id = None
        profile_code = None
        if grade is None or grade < 1 or grade > 11:
            raise PlanValidationError("Параллель должна быть от 1 до 11.")
    else:
        school_class_id = None
        if not profile_code:
            raise PlanValidationError("Укажите профиль или направление.")

    if plan.building_id:
        scope_building_id = plan.building_id
    elif (
        scope_building_id
        and db.session.get(Building, scope_building_id) is None
    ):
        raise PlanValidationError("Выберите существующее здание.")

    scope_key = line_scope_key(
        scope_kind,
        school_class_id=school_class_id,
        grade=grade,
        profile_code=profile_code,
        building_id=scope_building_id,
    )

    date_from = _parse_date(request.form.get("date_from"))
    date_to = _parse_date(request.form.get("date_to"))
    period = None
    if date_from or date_to:
        validate_period_range(plan, date_from, date_to)
        period = {
            "date_from": date_from,
            "date_to": date_to,
            "weeks_count": parse_decimal(
                request.form.get("period_weeks_count"),
                "количество недель периода",
            ),
            "weekly_hours": parse_decimal(
                request.form.get("period_weekly_hours"),
                "часы периода в неделю",
            ),
            "annual_hours": parse_decimal(
                request.form.get("period_annual_hours"),
                "часы за период",
            ),
        }
        period["annual_hours"] = calculate_annual_hours(
            period["weekly_hours"],
            period["weeks_count"],
            period["annual_hours"],
        )

    return {
        "activity": activity,
        "component_kind": component_kind,
        "weekly_hours": weekly_hours,
        "weeks_count": weeks_count,
        "annual_hours": annual_hours,
        "requires_division": request.form.get("requires_division") == "1",
        "profile_code": (
            " ".join((request.form.get("profile_code") or "").split()) or None
        ),
        "sort_order": request.form.get("sort_order", type=int) or 100,
        "scope": {
            "scope_kind": scope_kind,
            "school_class_id": school_class_id,
            "grade": grade,
            "profile_code": profile_code,
            "building_id": scope_building_id,
            "scope_key": scope_key,
        },
        "period": period,
    }


def _scope_label(scope):
    if scope.scope_kind == "CLASS":
        return scope.school_class.name if scope.school_class else "Класс"
    if scope.scope_kind == "GRADE":
        label = f"{scope.grade}-е классы"
    else:
        label = scope.profile_code or "Профиль"
    if scope.building:
        label = f"{label} · {scope.building.short_name or scope.building.name}"
    return label


def _can_update_plan(plan):
    return (
        is_feature_enabled(WORKLOAD_WRITE)
        and can_use_workload_permission(
            "workload.plan.update",
            current_user,
        )
        and plan.tariff_version.status == "DRAFT"
        and plan.status == "DRAFT"
    )


def _scope_sort_key(scope):
    kind_order = {"GRADE": 0, "CLASS": 1, "PROFILE": 2}
    if scope.scope_kind == "GRADE":
        value = (scope.grade or 0, "")
    elif scope.scope_kind == "CLASS":
        school_class = scope.school_class
        value = (
            school_class.grade if school_class else 0,
            school_class.name if school_class else "",
        )
    else:
        value = (0, scope.profile_code or "")
    return (
        kind_order.get(scope.scope_kind, 99),
        value,
        scope.building_id or 0,
    )


def _instructional_year_bounds(plan):
    academic_year = plan.tariff_version.tariff_cycle.academic_year
    start = academic_year.start_date
    if start is None:
        try:
            start_year = int(academic_year.name[:4])
        except (TypeError, ValueError):
            start_year = date.today().year
        start = date(start_year, 9, 1)
    default_end = date(start.year + 1, 5, 31)
    end = academic_year.end_date or default_end
    return start, min(end, default_end)


def _grade_period_scheme(plan, grade):
    start, end = _instructional_year_bounds(plan)
    if plan.education_level == "NOO" and grade == 1:
        return {
            "kind": "NOO_GRADE_1",
            "column_span": 3,
            "show_annual": True,
            "periods": (
                {
                    "code": "SEP_OCT",
                    "label": "сент.–окт.",
                    "weeks_count": Decimal("9"),
                    "date_from": start,
                    "date_to": min(end, date(start.year, 10, 31)),
                },
                {
                    "code": "NOV_MAY",
                    "label": "нояб.–май",
                    "weeks_count": Decimal("25"),
                    "date_from": max(start, date(start.year, 11, 1)),
                    "date_to": end,
                },
            ),
        }
    if plan.education_level == "SOO" and grade == 11:
        return {
            "kind": "SOO_GRADE_11",
            "column_span": 2,
            "show_annual": False,
            "periods": (
                {
                    "code": "ATTESTATION_1",
                    "label": "I период",
                    "weeks_count": Decimal("20"),
                    "date_from": start,
                    "date_to": min(end, date(start.year + 1, 1, 31)),
                },
                {
                    "code": "ATTESTATION_2",
                    "label": "II период",
                    "weeks_count": Decimal("14"),
                    "date_from": max(start, date(start.year + 1, 2, 1)),
                    "date_to": end,
                },
            ),
        }
    return None


def _grade_scope_column(plan, grade):
    period_scheme = _grade_period_scheme(plan, grade)
    return {
        "key": line_scope_key(
            "GRADE",
            grade=grade,
            building_id=plan.building_id,
        ),
        "label": f"{grade} класс",
        "kind": "GRADE",
        "grade": grade,
        "period_scheme": period_scheme,
        "column_span": period_scheme["column_span"] if period_scheme else 2,
        "fgos_weekly_norms": FGOS_WEEKLY_HOUR_NORMS.get(grade, ()),
    }


def _add_period_weekly_totals(target, line):
    for index, period in enumerate(
        sorted(line.periods, key=lambda item: item.date_from)
    ):
        while len(target["period_weekly"]) <= index:
            target["period_weekly"].append(Decimal("0"))
        target["period_weekly"][index] += Decimal(
            period.weekly_hours or 0
        )


def _fgos_hour_control(actual, expected):
    actual = Decimal(actual or 0)
    expected = Decimal(expected)
    if actual == expected:
        state = "complete"
        result = "соответствует нормативу"
    elif actual < expected:
        state = "under"
        result = (
            f"не хватает {_decimal_text(expected - actual)} ч/нед."
        )
    else:
        state = "over"
        result = (
            f"превышение на {_decimal_text(actual - expected)} ч/нед."
        )
    return {
        "actual": actual,
        "expected": expected,
        "state": state,
        "message": (
            f"Норма ФГОС: {_decimal_text(expected)} ч/нед.; "
            f"внесено: {_decimal_text(actual)} ч/нед. — {result}."
        ),
    }


def _build_plan_matrix(plan):
    zero = Decimal("0")
    default_columns = [
        _grade_scope_column(plan, grade)
        for grade in PLAN_LEVEL_GRADES.get(plan.education_level, ())
    ]
    scope_columns_by_key = {
        column["key"]: column
        for column in default_columns
    }
    extra_scopes = {}
    row_map = {}

    for line in plan.lines:
        row_key = (
            line.component_kind,
            line.education_activity_id,
            line.profile_code or "",
        )
        row = row_map.setdefault(
            row_key,
            {
                "component_kind": line.component_kind,
                "activity": line.education_activity,
                "profile_code": line.profile_code,
                "sort_order": line.sort_order,
                "cells": {},
                "weekly_total": zero,
                "annual_total": zero,
            },
        )
        row["sort_order"] = min(row["sort_order"], line.sort_order)
        for scope in line.scopes:
            if scope.scope_key not in scope_columns_by_key:
                extra_scopes.setdefault(scope.scope_key, scope)
            row["cells"][scope.scope_key] = line
            row["weekly_total"] += Decimal(line.weekly_hours or zero)
            row["annual_total"] += Decimal(line.annual_hours or zero)

    scope_columns = list(default_columns)
    scope_columns.extend(
        {
            "key": scope.scope_key,
            "label": _scope_label(scope),
            "kind": scope.scope_kind,
            "grade": scope.grade,
            "period_scheme": None,
            "column_span": 2,
        }
        for scope in sorted(extra_scopes.values(), key=_scope_sort_key)
    )
    scope_keys = [column["key"] for column in scope_columns]

    component_order = {
        component: index
        for index, component in enumerate(PLAN_COMPONENT_KINDS)
    }
    rows = sorted(
        row_map.values(),
        key=lambda row: (
            component_order.get(row["component_kind"], 99),
            row["sort_order"],
            row["activity"].name.casefold(),
        ),
    )

    section_map = {}
    for row in rows:
        component = row["component_kind"]
        section = section_map.setdefault(
            component,
            {
                "component_kind": component,
                "label": PLAN_COMPONENT_LABELS.get(component, component),
                "rows": [],
                "scope_totals": {
                    scope_key: {
                        "weekly": zero,
                        "annual": zero,
                        "period_weekly": [],
                    }
                    for scope_key in scope_keys
                },
                "weekly_total": zero,
                "annual_total": zero,
            },
        )
        section["rows"].append(row)
        section["weekly_total"] += row["weekly_total"]
        section["annual_total"] += row["annual_total"]
        for scope_key, line in row["cells"].items():
            section["scope_totals"][scope_key]["weekly"] += Decimal(
                line.weekly_hours or zero
            )
            section["scope_totals"][scope_key]["annual"] += Decimal(
                line.annual_hours or zero
            )
            _add_period_weekly_totals(
                section["scope_totals"][scope_key],
                line,
            )

    sections = [
        section_map[component]
        for component in PLAN_COMPONENT_KINDS
        if component in section_map
    ]
    for section in sections:
        for index, row in enumerate(section["rows"]):
            row["can_move_up"] = index > 0
            row["can_move_down"] = index < len(section["rows"]) - 1
    plan_scope_totals = {
        scope_key: {
            "weekly": zero,
            "annual": zero,
            "period_weekly": [],
        }
        for scope_key in scope_keys
    }
    for section in sections:
        for scope_key in scope_keys:
            section_total = section["scope_totals"][scope_key]
            plan_total = plan_scope_totals[scope_key]
            plan_total["weekly"] += section_total["weekly"]
            plan_total["annual"] += section_total["annual"]
            for index, value in enumerate(
                section_total["period_weekly"]
            ):
                while len(plan_total["period_weekly"]) <= index:
                    plan_total["period_weekly"].append(zero)
                plan_total["period_weekly"][index] += value

    fgos_controls = {}
    if plan.plan_kind == "CURRICULUM":
        for scope in scope_columns:
            norms = scope.get("fgos_weekly_norms") or ()
            if not norms:
                continue
            scope_total = plan_scope_totals[scope["key"]]
            if scope["period_scheme"]:
                actual_values = scope_total["period_weekly"]
                period_controls = tuple(
                    _fgos_hour_control(
                        (
                            actual_values[index]
                            if index < len(actual_values)
                            else zero
                        ),
                        expected,
                    )
                    for index, expected in enumerate(norms)
                )
                fgos_controls[scope["key"]] = {
                    "periods": period_controls,
                    "weekly": None,
                }
            else:
                fgos_controls[scope["key"]] = {
                    "periods": (),
                    "weekly": _fgos_hour_control(
                        scope_total["weekly"],
                        norms[0],
                    ),
                }

    return {
        "scope_columns": scope_columns,
        "sections": sections,
        "row_count": len(rows),
        "total_column_count": (
            2 + sum(column["column_span"] for column in scope_columns)
        ),
        "scope_totals": plan_scope_totals,
        "fgos_controls": fgos_controls,
        "weekly_total": sum(
            (section["weekly_total"] for section in sections),
            zero,
        ),
        "annual_total": sum(
            (section["annual_total"] for section in sections),
            zero,
        ),
    }


def _period_hours_payload(plan, scheme, *, require_weekly=True):
    values = []
    has_value = False
    for index, period_spec in enumerate(scheme["periods"], start=1):
        weekly_hours = parse_decimal(
            request.form.get(f"period_{index}_weekly_hours"),
            f"часы в неделю: {period_spec['label']}",
        )
        weeks_value = request.form.get(f"period_{index}_weeks_count")
        weeks_count = (
            period_spec["weeks_count"]
            if weeks_value is None
            else parse_decimal(
                weeks_value,
                f"количество недель: {period_spec['label']}",
                required=True,
            )
        )
        if weeks_count <= 0:
            raise PlanValidationError(
                "Количество учебных недель должно быть больше нуля."
            )
        has_value = has_value or weekly_hours is not None
        annual_hours = (
            weekly_hours * weeks_count
            if weekly_hours is not None
            else Decimal("0")
        ).quantize(Decimal("0.001"))
        validate_period_range(
            plan,
            period_spec["date_from"],
            period_spec["date_to"],
        )
        values.append({
            **period_spec,
            "weeks_count": weeks_count,
            "weekly_hours": weekly_hours or Decimal("0"),
            "annual_hours": annual_hours,
        })
    if require_weekly and not has_value:
        raise PlanValidationError(
            "Укажите часы хотя бы для одного учебного периода."
        )
    return values


def _apply_period_hours(line, values):
    line.weekly_hours = max(
        (item["weekly_hours"] for item in values),
        default=Decimal("0"),
    )
    line.weeks_count = sum(
        (item["weeks_count"] for item in values),
        Decimal("0"),
    )
    line.annual_hours = sum(
        (item["annual_hours"] for item in values),
        Decimal("0"),
    )
    existing_periods = sorted(
        line.periods,
        key=lambda period: period.date_from,
    )
    if existing_periods and len(existing_periods) != len(values):
        line.periods.clear()
        db.session.flush()
        existing_periods = []
    for index, item in enumerate(values):
        if index < len(existing_periods):
            period = existing_periods[index]
        else:
            period = EducationPlanLinePeriod()
            line.periods.append(period)
        period.date_from = item["date_from"]
        period.date_to = item["date_to"]
        period.weeks_count = item["weeks_count"]
        period.weekly_hours = item["weekly_hours"]
        period.annual_hours = item["annual_hours"]


def _render_plan_line_form(plan, line=None):
    current_scope = line.scopes[0] if line and line.scopes else None
    current_period = line.periods[0] if line and line.periods else None
    return render_template(
        "workload/plan_line_form.html",
        plan=plan,
        line=line,
        current_scope=current_scope,
        current_period=current_period,
        activities=_available_activities(plan),
        classes=_available_classes(plan),
        buildings=Building.query.order_by(Building.name.asc()).all(),
        component_kinds=tuple(
            component
            for component in PLAN_COMPONENT_KINDS
            if component in PLAN_COMPONENTS_BY_KIND[plan.plan_kind]
        ),
        component_labels=PLAN_COMPONENT_LABELS,
        scope_kinds=PLAN_SCOPE_KINDS,
        scope_labels=PLAN_SCOPE_LABELS,
    )


def register_plan_routes(workload_bp):
    @workload_bp.get("/plans/")
    @login_required
    def plans():
        _require_plan_read()
        scope = resolve_workload_scope(current_user)
        query = EducationPlan.query.join(TariffVersion).join(TariffCycle)
        query = query.filter(
            EducationPlan.plan_kind == "CURRICULUM",
            EducationPlan.root_plan_id.is_(None),
        )
        organization_id = _current_organization_id()
        if organization_id is None:
            query = query.filter(TariffCycle.organization_id.is_(None))
        else:
            query = query.filter(
                TariffCycle.organization_id == organization_id
            )
        if not scope.unrestricted:
            query = plans_visible_in_buildings(query, scope.building_ids)

        academic_year_id = request.args.get("academic_year_id", type=int)
        if academic_year_id:
            query = query.filter(
                TariffCycle.academic_year_id == academic_year_id
            )

        items = query.order_by(
            TariffCycle.academic_year_id.desc(),
            EducationPlan.name.asc(),
        ).all()
        for item in items:
            item.curriculum_annual_hours = sum(
                (
                    Decimal(line.annual_hours or 0)
                    for line in item.lines
                ),
                Decimal("0"),
            )
        can_update = (
            is_feature_enabled(WORKLOAD_WRITE)
            and can_use_workload_permission(
                "workload.plan.update",
                current_user,
            )
        )
        return render_template(
            "workload/plans.html",
            plans=items,
            academic_years=AcademicYear.query.order_by(
                AcademicYear.name.desc()
            ).all(),
            selected_academic_year_id=academic_year_id,
            plan_status_labels=PLAN_STATUS_LABELS,
            can_update=can_update,
        )

    @workload_bp.route("/plans/new", methods=["GET", "POST"])
    @login_required
    def plan_create():
        _require_plan_update()
        source_plan_id = request.values.get("source_plan_id", type=int)
        source_plan = (
            plan_bundle_root(_get_plan(source_plan_id))
            if source_plan_id else None
        )
        if request.method == "POST":
            academic_year_id = request.form.get(
                "academic_year_id",
                type=int,
            )
            academic_year = (
                db.session.get(AcademicYear, academic_year_id)
                if academic_year_id else None
            )
            name = " ".join((request.form.get("name") or "").split())
            profile_name = (
                " ".join((request.form.get("profile_name") or "").split())
                or None
            )
            education_level = (
                (request.form.get("education_level") or "").strip().upper()
                or None
            )
            building_id = request.form.get("building_id", type=int)
            if source_plan is not None:
                education_level = source_plan.education_level
                building_id = source_plan.building_id
            building = (
                db.session.get(Building, building_id)
                if building_id else None
            )
            try:
                if academic_year is None:
                    raise PlanValidationError("Выберите учебный год.")
                if academic_year.is_closed or academic_year.is_archived:
                    raise PlanValidationError(
                        "Нельзя создать план в закрытом учебном году."
                    )
                if education_level not in PLAN_LEVEL_GRADES:
                    raise PlanValidationError(
                        "Для учебного плана выберите уровень НОО, ООО или СОО."
                    )
                if not name:
                    raise PlanValidationError("Укажите название плана.")
                if building_id and building is None:
                    raise PlanValidationError(
                        "Выберите существующее здание."
                    )

                _, version = ensure_draft_tariff_version(
                    academic_year,
                    organization_id=_current_organization_id(),
                    user_id=current_user.id,
                )
                plan = EducationPlan(
                    tariff_version_id=version.id,
                    plan_kind="CURRICULUM",
                    name=name,
                    profile_name=profile_name,
                    education_level=education_level,
                    building_id=building_id,
                    scope_code=plan_scope_code(
                        education_level,
                        building_id,
                    ),
                    status="DRAFT",
                    created_by_user_id=current_user.id,
                    updated_by_user_id=current_user.id,
                )
                db.session.add(plan)
                db.session.flush()
                create_plan_bundle(plan, user_id=current_user.id)
                if source_plan is not None:
                    db.session.flush()
                    clone_plan_bundle(
                        source_plan,
                        plan,
                        user_id=current_user.id,
                    )
                db.session.commit()
            except PlanValidationError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
            except IntegrityError:
                db.session.rollback()
                flash(
                    "План с таким названием и областью уже существует.",
                    "danger",
                )
            else:
                flash("План создан.", "success")
                return redirect(
                    url_for("workload.plan_matrix", plan_id=plan.id)
                )

        return render_template(
            "workload/plan_form.html",
            academic_years=AcademicYear.query.order_by(
                AcademicYear.name.desc()
            ).all(),
            buildings=Building.query.order_by(Building.name.asc()).all(),
            source_plans=_plan_source_options(),
            selected_source_plan=source_plan,
        )

    @workload_bp.get("/plans/<int:plan_id>")
    @login_required
    def plan_detail(plan_id):
        plan = _get_plan(plan_id)
        can_update = _can_update_plan(plan)
        return render_template(
            "workload/plan_detail.html",
            plan=plan,
            plan_kind_labels=PLAN_KIND_LABELS,
            plan_status_labels=PLAN_STATUS_LABELS,
            component_labels=PLAN_COMPONENT_LABELS,
            scope_label=_scope_label,
            can_update=can_update,
        )

    @workload_bp.post("/plans/<int:plan_id>/profile")
    @login_required
    def plan_profile_update(plan_id):
        plan = plan_bundle_root(_get_plan(plan_id, for_update=True))
        try:
            require_plan_editable(
                plan,
                expected_revision=request.form.get("revision", type=int),
            )
            name = " ".join((request.form.get("name") or "").split())
            if not name:
                raise PlanValidationError("Укажите название учебного плана.")
            profile_name = (
                " ".join((request.form.get("profile_name") or "").split())
                or None
            )
            for plan_kind, part in plan_bundle_parts(plan).items():
                part.name = (
                    name
                    if plan_kind == "CURRICULUM"
                    else f"{name} · {PLAN_BUNDLE_LABELS[plan_kind]}"[:255]
                )
                part.profile_name = profile_name
                part.updated_by_user_id = current_user.id
                part.revision += 1
            db.session.commit()
        except PlanValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            flash(
                "План с таким названием и областью уже существует.",
                "danger",
            )
        else:
            flash("Название и профиль учебного плана сохранены.", "success")
        if request.form.get("return_to") == "plans":
            return redirect(url_for(
                "workload.plans",
                academic_year_id=(
                    plan.tariff_version.tariff_cycle.academic_year_id
                ),
            ))
        return redirect(
            url_for("workload.plan_matrix", plan_id=plan.id)
        )

    @workload_bp.post("/plans/<int:plan_id>/delete")
    @login_required
    def plan_delete(plan_id):
        plan = _get_plan(plan_id, for_update=True)
        if plan.root_plan_id is not None or plan.plan_kind != "CURRICULUM":
            abort(400)
        try:
            require_plan_editable(
                plan,
                expected_revision=request.form.get("revision", type=int),
            )
            bundle = plan_bundle_parts(plan)
            line_ids = [
                line.id
                for part in bundle.values()
                for line in part.lines
            ]
            group_count = (
                TeachingGroup.query
                .filter(TeachingGroup.source_plan_line_id.in_(line_ids))
                .count()
                if line_ids else 0
            )
            need_count = (
                WorkloadNeedSource.query
                .filter(
                    WorkloadNeedSource.education_plan_line_id.in_(line_ids)
                )
                .count()
                if line_ids else 0
            )
            if group_count or need_count:
                raise PlanValidationError(
                    "План уже используется при формировании групп или "
                    "нагрузки. Сначала удалите зависимые рабочие данные."
                )

            binding_count = len(plan.class_bindings)
            if line_ids:
                (
                    EducationPlanLine.query
                    .filter(EducationPlanLine.source_line_id.in_(line_ids))
                    .update(
                        {EducationPlanLine.source_line_id: None},
                        synchronize_session=False,
                    )
                )
            plan_name = plan.name
            db.session.delete(plan)
            db.session.commit()
        except PlanValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            flash(
                "План связан с рабочими данными и пока не может быть удалён.",
                "danger",
            )
        else:
            message = f"Учебный план «{plan_name}» удалён."
            if binding_count:
                message += (
                    f" Удалено привязок к классам: {binding_count}. "
                    "Классы и ученики сохранены без учебного плана."
                )
            flash(message, "success")
        return redirect(url_for("workload.plans"))

    @workload_bp.post("/plans/<int:plan_id>/matrix/activities")
    @login_required
    def plan_matrix_add_activity(plan_id):
        plan = _get_plan(plan_id, for_update=True)
        try:
            require_plan_editable(
                plan,
                expected_revision=request.form.get("revision", type=int),
            )
            grades = PLAN_LEVEL_GRADES.get(plan.education_level, ())
            if not grades:
                raise PlanValidationError(
                    "Укажите уровень образования плана, чтобы добавить строку."
                )

            activity_id = request.form.get("education_activity_id", type=int)
            activities = {
                item.id: item
                for item in _available_activities(plan)
            }
            activity = activities.get(activity_id)
            if activity is None:
                raise PlanValidationError(
                    "Выберите предмет или курс из единого каталога."
                )

            component_kind = (
                (request.form.get("component_kind") or "").strip().upper()
            )
            if component_kind not in PLAN_COMPONENTS_BY_KIND[plan.plan_kind]:
                raise PlanValidationError(
                    "Выберите допустимую часть учебного плана."
                )

            existing = {
                (
                    line.education_activity_id,
                    line.component_kind,
                    scope.scope_key,
                )
                for line in plan.lines
                for scope in line.scopes
            }
            sort_order = max(
                (line.sort_order for line in plan.lines),
                default=0,
            ) + 10
            created_lines = []
            for grade in grades:
                scope_key = line_scope_key(
                    "GRADE",
                    grade=grade,
                    building_id=plan.building_id,
                )
                key = (activity.id, component_kind, scope_key)
                if key in existing:
                    continue
                line = EducationPlanLine(
                    education_plan_id=plan.id,
                    education_activity_id=activity.id,
                    component_kind=component_kind,
                    weekly_hours=Decimal("0"),
                    weeks_count=DEFAULT_WEEKS_COUNT,
                    annual_hours=Decimal("0"),
                    requires_division=False,
                    sort_order=sort_order,
                    created_by_user_id=current_user.id,
                    updated_by_user_id=current_user.id,
                )
                line.scopes.append(EducationPlanLineScope(
                    scope_kind="GRADE",
                    grade=grade,
                    building_id=plan.building_id,
                    scope_key=scope_key,
                ))
                db.session.add(line)
                created_lines.append(line)

            if not created_lines:
                raise PlanValidationError(
                    "Этот предмет уже добавлен во все параллели раздела."
                )
            touch_plan(plan, user_id=current_user.id)
            db.session.commit()
        except PlanValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            selected_line_id = None
        except IntegrityError:
            db.session.rollback()
            flash(
                "Не удалось добавить предмет из-за конфликта данных.",
                "danger",
            )
            selected_line_id = None
        else:
            selected_line_id = created_lines[0].id
            flash(
                f"Предмет «{activity.name}» добавлен для всех параллелей.",
                "success",
            )
        return redirect(
            url_for(
                "workload.plan_matrix",
                plan_id=plan.id,
                selected_line_id=selected_line_id,
            )
        )

    @workload_bp.post("/plans/<int:plan_id>/matrix/cells")
    @login_required
    def plan_matrix_create_cell(plan_id):
        plan = _get_plan(plan_id, for_update=True)
        selected_line_id = None
        try:
            require_plan_editable(
                plan,
                expected_revision=request.form.get("revision", type=int),
            )
            grade = request.form.get("grade", type=int)
            if grade not in PLAN_LEVEL_GRADES.get(plan.education_level, ()):
                raise PlanValidationError(
                    "Выбранный класс не относится к уровню образования плана."
                )

            activity_id = request.form.get("education_activity_id", type=int)
            activities = {
                item.id: item
                for item in _available_activities(plan)
            }
            activity = activities.get(activity_id)
            if activity is None:
                raise PlanValidationError(
                    "Выберите предмет или курс из единого каталога."
                )

            component_kind = (
                (request.form.get("component_kind") or "").strip().upper()
            )
            if component_kind not in PLAN_COMPONENTS_BY_KIND[plan.plan_kind]:
                raise PlanValidationError(
                    "Выберите допустимую часть учебного плана."
                )

            scope_key = line_scope_key(
                "GRADE",
                grade=grade,
                building_id=plan.building_id,
            )
            duplicate = (
                EducationPlanLine.query
                .join(EducationPlanLineScope)
                .filter(
                    EducationPlanLine.education_plan_id == plan.id,
                    EducationPlanLine.education_activity_id == activity.id,
                    EducationPlanLine.component_kind == component_kind,
                    EducationPlanLineScope.scope_key == scope_key,
                )
                .first()
            )
            if duplicate:
                raise PlanValidationError(
                    "Для этого предмета и класса ячейка уже существует."
                )

            weekly_hours = parse_decimal(
                request.form.get("weekly_hours"),
                "часы в неделю",
                required=True,
            )
            weeks_count = parse_decimal(
                request.form.get("weeks_count"),
                "количество учебных недель",
                required=True,
            )
            annual_hours = calculate_annual_hours(
                weekly_hours,
                weeks_count,
                parse_decimal(
                    request.form.get("annual_hours"),
                    "часы в год",
                ),
            )
            validate_line_values(
                plan,
                activity,
                component_kind,
                weekly_hours,
                annual_hours,
                weeks_count,
            )

            profile_code = " ".join(
                (request.form.get("profile_code") or "").split()
            ) or None
            line = EducationPlanLine(
                education_plan_id=plan.id,
                education_activity_id=activity.id,
                component_kind=component_kind,
                weekly_hours=weekly_hours,
                weeks_count=weeks_count,
                annual_hours=annual_hours,
                requires_division=False,
                profile_code=profile_code,
                sort_order=request.form.get("sort_order", type=int) or 100,
                created_by_user_id=current_user.id,
                updated_by_user_id=current_user.id,
            )
            line.scopes.append(EducationPlanLineScope(
                scope_kind="GRADE",
                grade=grade,
                building_id=plan.building_id,
                scope_key=scope_key,
            ))
            db.session.add(line)
            touch_plan(plan, user_id=current_user.id)
            db.session.commit()
            selected_line_id = line.id
        except PlanValidationError as exc:
            db.session.rollback()
            if _is_matrix_ajax_request():
                return jsonify({"ok": False, "error": str(exc)}), 422
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            if _is_matrix_ajax_request():
                return jsonify({
                    "ok": False,
                    "error": "Не удалось заполнить ячейку из-за конфликта данных.",
                }), 409
            flash(
                "Не удалось заполнить ячейку из-за конфликта данных.",
                "danger",
            )
        else:
            if _is_matrix_ajax_request():
                return _matrix_line_response(plan, line)
            flash(
                f"Часы для {grade} класса сохранены.",
                "success",
            )
        return redirect(
            url_for(
                "workload.plan_matrix",
                plan_id=plan.id,
                selected_line_id=selected_line_id,
            )
        )

    @workload_bp.post("/plans/<int:plan_id>/matrix/period-cells")
    @login_required
    def plan_matrix_create_period_cell(plan_id):
        plan = _get_plan(plan_id, for_update=True)
        try:
            require_plan_editable(
                plan,
                expected_revision=request.form.get("revision", type=int),
            )
            grade = request.form.get("grade", type=int)
            scheme = _grade_period_scheme(plan, grade)
            if scheme is None:
                raise PlanValidationError(
                    "Для выбранного класса периодный ввод не предусмотрен."
                )

            activity_id = request.form.get("education_activity_id", type=int)
            activities = {
                item.id: item
                for item in _available_activities(plan)
            }
            activity = activities.get(activity_id)
            if activity is None:
                raise PlanValidationError(
                    "Выберите предмет или курс из единого каталога."
                )
            component_kind = (
                (request.form.get("component_kind") or "").strip().upper()
            )
            if component_kind not in PLAN_COMPONENTS_BY_KIND[plan.plan_kind]:
                raise PlanValidationError(
                    "Выберите допустимую часть учебного плана."
                )

            scope_key = line_scope_key(
                "GRADE",
                grade=grade,
                building_id=plan.building_id,
            )
            duplicate = (
                EducationPlanLine.query
                .join(EducationPlanLineScope)
                .filter(
                    EducationPlanLine.education_plan_id == plan.id,
                    EducationPlanLine.education_activity_id == activity.id,
                    EducationPlanLine.component_kind == component_kind,
                    EducationPlanLineScope.scope_key == scope_key,
                )
                .first()
            )
            if duplicate:
                raise PlanValidationError(
                    "Для этого предмета и класса ячейка уже существует."
                )

            values = _period_hours_payload(plan, scheme)
            line = EducationPlanLine(
                education_plan_id=plan.id,
                education_activity_id=activity.id,
                component_kind=component_kind,
                weekly_hours=Decimal("0"),
                weeks_count=Decimal("34"),
                annual_hours=Decimal("0"),
                requires_division=False,
                profile_code=" ".join(
                    (request.form.get("profile_code") or "").split()
                ) or None,
                sort_order=request.form.get("sort_order", type=int) or 100,
                created_by_user_id=current_user.id,
                updated_by_user_id=current_user.id,
            )
            _apply_period_hours(line, values)
            validate_line_values(
                plan,
                activity,
                component_kind,
                line.weekly_hours,
                line.annual_hours,
                line.weeks_count,
            )
            line.scopes.append(EducationPlanLineScope(
                scope_kind="GRADE",
                grade=grade,
                building_id=plan.building_id,
                scope_key=scope_key,
            ))
            db.session.add(line)
            touch_plan(plan, user_id=current_user.id)
            db.session.commit()
        except PlanValidationError as exc:
            db.session.rollback()
            if _is_matrix_ajax_request():
                return jsonify({"ok": False, "error": str(exc)}), 422
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            if _is_matrix_ajax_request():
                return jsonify({
                    "ok": False,
                    "error": "Не удалось сохранить периоды из-за конфликта данных.",
                }), 409
            flash(
                "Не удалось сохранить периоды из-за конфликта данных.",
                "danger",
            )
        else:
            if _is_matrix_ajax_request():
                return _matrix_period_response(plan, line)
            flash("Часы учебных периодов сохранены.", "success")
        return redirect(
            url_for("workload.plan_matrix", plan_id=plan.id)
        )

    @workload_bp.post(
        "/plans/<int:plan_id>/lines/<int:line_id>/period-hours"
    )
    @login_required
    def plan_line_update_period_hours(plan_id, line_id):
        plan = _get_plan(plan_id, for_update=True)
        line = EducationPlanLine.query.filter_by(
            id=line_id,
            education_plan_id=plan.id,
        ).first_or_404()
        try:
            require_plan_editable(
                plan,
                expected_revision=request.form.get("revision", type=int),
            )
            scope = line.scopes[0] if line.scopes else None
            scheme = _grade_period_scheme(
                plan,
                scope.grade if scope and scope.scope_kind == "GRADE" else None,
            )
            if scheme is None:
                raise PlanValidationError(
                    "Для этой строки периодный ввод не предусмотрен."
                )
            values = _period_hours_payload(
                plan,
                scheme,
                require_weekly=False,
            )
            _apply_period_hours(line, values)
            validate_line_values(
                plan,
                line.education_activity,
                line.component_kind,
                line.weekly_hours,
                line.annual_hours,
                line.weeks_count,
            )
            line.updated_by_user_id = current_user.id
            touch_plan(plan, user_id=current_user.id)
            _synchronize_plan_workload(plan, line)
            db.session.commit()
        except (PlanValidationError, WorkloadDistributionError) as exc:
            db.session.rollback()
            if _is_matrix_ajax_request():
                return jsonify({"ok": False, "error": str(exc)}), 422
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            if _is_matrix_ajax_request():
                return jsonify({
                    "ok": False,
                    "error": "Не удалось обновить периоды из-за конфликта данных.",
                }), 409
            flash(
                "Не удалось обновить периоды из-за конфликта данных.",
                "danger",
            )
        else:
            if _is_matrix_ajax_request():
                return _matrix_period_response(plan, line)
            flash("Часы учебных периодов обновлены.", "success")
        return redirect(
            url_for("workload.plan_matrix", plan_id=plan.id)
        )

    @workload_bp.post("/plans/<int:plan_id>/matrix/rows/delete")
    @login_required
    def plan_matrix_delete_row(plan_id):
        plan = _get_plan(plan_id, for_update=True)
        try:
            require_plan_editable(
                plan,
                expected_revision=request.form.get("revision", type=int),
            )
            activity_id = request.form.get("education_activity_id", type=int)
            component_kind = (
                (request.form.get("component_kind") or "").strip().upper()
            )
            profile_code = " ".join(
                (request.form.get("profile_code") or "").split()
            )
            lines = (
                EducationPlanLine.query
                .filter_by(
                    education_plan_id=plan.id,
                    education_activity_id=activity_id,
                    component_kind=component_kind,
                )
                .all()
            )
            lines = [
                line
                for line in lines
                if (line.profile_code or "") == profile_code
            ]
            if not lines:
                raise PlanValidationError(
                    "Предметная строка уже удалена или не существует."
                )
            activity_name = lines[0].education_activity.name
            deleted = delete_plan_lines_with_dependencies(lines)
            touch_plan(plan, user_id=current_user.id)
            db.session.commit()
        except (PlanValidationError, WorkloadDistributionError) as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except IntegrityError:
            db.session.rollback()
            flash(
                "Строку нельзя удалить, пока она используется в нагрузке.",
                "danger",
            )
        else:
            flash(
                f"Строка «{activity_name}» удалена из плана. "
                f"Удалено групп: {deleted['groups']}, "
                f"назначений нагрузки: {deleted['assignments']}.",
                "success",
            )
        return redirect(
            url_for("workload.plan_matrix", plan_id=plan.id)
        )

    @workload_bp.post("/plans/<int:plan_id>/matrix/rows/reorder")
    @login_required
    def plan_matrix_reorder_row(plan_id):
        plan = _get_plan(plan_id, for_update=True)
        try:
            require_plan_editable(
                plan,
                expected_revision=request.form.get("revision", type=int),
            )
            activity_id = request.form.get("education_activity_id", type=int)
            component_kind = (
                (request.form.get("component_kind") or "").strip().upper()
            )
            profile_code = " ".join(
                (request.form.get("profile_code") or "").split()
            )
            direction = (request.form.get("direction") or "").strip().lower()
            if direction not in {"up", "down"}:
                raise PlanValidationError(
                    "Не удалось определить направление перемещения."
                )

            matrix = _build_plan_matrix(plan)
            section = next(
                (
                    item
                    for item in matrix["sections"]
                    if item["component_kind"] == component_kind
                ),
                None,
            )
            rows = list(section["rows"]) if section else []
            current_index = next(
                (
                    index
                    for index, row in enumerate(rows)
                    if (
                        row["activity"].id == activity_id
                        and (row["profile_code"] or "") == profile_code
                    )
                ),
                None,
            )
            if current_index is None:
                raise PlanValidationError(
                    "Предметная строка уже удалена или не существует."
                )

            target_index = (
                current_index - 1
                if direction == "up"
                else current_index + 1
            )
            if target_index < 0 or target_index >= len(rows):
                raise PlanValidationError(
                    "Строка уже находится на границе раздела."
                )

            current_row = rows.pop(current_index)
            rows.insert(target_index, current_row)
            order_by_key = {
                (
                    row["activity"].id,
                    row["profile_code"] or "",
                ): (index + 1) * 10
                for index, row in enumerate(rows)
            }
            for line in plan.lines:
                if line.component_kind != component_kind:
                    continue
                line.sort_order = order_by_key.get(
                    (
                        line.education_activity_id,
                        line.profile_code or "",
                    ),
                    line.sort_order,
                )
                line.updated_by_user_id = current_user.id

            touch_plan(plan, user_id=current_user.id)
            db.session.commit()
        except PlanValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Порядок предметов сохранён.", "success")
        return redirect(
            url_for(
                "workload.plan_matrix",
                plan_id=plan.id,
                part=plan.plan_kind,
            )
        )

    @workload_bp.post("/plans/<int:plan_id>/status")
    @login_required
    def plan_change_status(plan_id):
        plan = _get_plan(plan_id, for_update=True)
        try:
            change_plan_status(
                plan,
                request.form.get("status"),
                user_id=current_user.id,
                expected_revision=request.form.get("revision", type=int),
            )
            db.session.commit()
        except PlanValidationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash("Статус плана изменён.", "success")
        return redirect(url_for("workload.plan_detail", plan_id=plan.id))

    @workload_bp.route(
        "/plans/<int:plan_id>/lines/new",
        methods=["GET", "POST"],
    )
    @login_required
    def plan_line_create(plan_id):
        plan = _get_plan(plan_id, for_update=True)
        if request.method == "GET":
            try:
                require_plan_editable(plan)
            except PlanValidationError as exc:
                flash(str(exc), "danger")
                return redirect(
                    url_for("workload.plan_detail", plan_id=plan.id)
                )
        if request.method == "POST":
            try:
                require_plan_editable(
                    plan,
                    expected_revision=request.form.get(
                        "revision",
                        type=int,
                    ),
                )
                payload = _line_payload(plan)
                duplicate = (
                    EducationPlanLine.query
                    .join(EducationPlanLineScope)
                    .filter(
                        EducationPlanLine.education_plan_id == plan.id,
                        EducationPlanLine.education_activity_id
                        == payload["activity"].id,
                        EducationPlanLine.component_kind
                        == payload["component_kind"],
                        EducationPlanLineScope.scope_key
                        == payload["scope"]["scope_key"],
                    )
                    .first()
                )
                if duplicate:
                    raise PlanValidationError(
                        "Такая дисциплина уже добавлена для выбранной области."
                    )

                line = EducationPlanLine(
                    education_plan_id=plan.id,
                    education_activity_id=payload["activity"].id,
                    component_kind=payload["component_kind"],
                    weekly_hours=payload["weekly_hours"],
                    weeks_count=payload["weeks_count"],
                    annual_hours=payload["annual_hours"],
                    requires_division=payload["requires_division"],
                    profile_code=payload["profile_code"],
                    sort_order=payload["sort_order"],
                    created_by_user_id=current_user.id,
                    updated_by_user_id=current_user.id,
                )
                db.session.add(line)
                db.session.flush()
                db.session.add(EducationPlanLineScope(
                    education_plan_line_id=line.id,
                    **payload["scope"],
                ))
                if payload["period"]:
                    db.session.add(EducationPlanLinePeriod(
                        education_plan_line_id=line.id,
                        **payload["period"],
                    ))
                touch_plan(plan, user_id=current_user.id)
                db.session.commit()
            except PlanValidationError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
            except IntegrityError:
                db.session.rollback()
                flash(
                    "Строка плана конфликтует с существующими данными.",
                    "danger",
                )
            else:
                flash("Строка плана добавлена.", "success")
                return redirect(
                    url_for("workload.plan_detail", plan_id=plan.id)
                )

        return _render_plan_line_form(plan)

    @workload_bp.route(
        "/plans/<int:plan_id>/lines/<int:line_id>/edit",
        methods=["GET", "POST"],
    )
    @login_required
    def plan_line_edit(plan_id, line_id):
        plan = _get_plan(plan_id, for_update=True)
        line = EducationPlanLine.query.filter_by(
            id=line_id,
            education_plan_id=plan.id,
        ).first_or_404()
        if request.method == "GET":
            try:
                require_plan_editable(plan)
            except PlanValidationError as exc:
                flash(str(exc), "danger")
                return redirect(
                    url_for("workload.plan_detail", plan_id=plan.id)
                )
        else:
            try:
                require_plan_editable(
                    plan,
                    expected_revision=request.form.get(
                        "revision",
                        type=int,
                    ),
                )
                payload = _line_payload(plan)
                duplicate = (
                    EducationPlanLine.query
                    .join(EducationPlanLineScope)
                    .filter(
                        EducationPlanLine.education_plan_id == plan.id,
                        EducationPlanLine.id != line.id,
                        EducationPlanLine.education_activity_id
                        == payload["activity"].id,
                        EducationPlanLine.component_kind
                        == payload["component_kind"],
                        EducationPlanLineScope.scope_key
                        == payload["scope"]["scope_key"],
                    )
                    .first()
                )
                if duplicate:
                    raise PlanValidationError(
                        "Такая дисциплина уже добавлена для выбранной области."
                    )

                line.education_activity_id = payload["activity"].id
                line.component_kind = payload["component_kind"]
                line.weekly_hours = payload["weekly_hours"]
                line.weeks_count = payload["weeks_count"]
                line.annual_hours = payload["annual_hours"]
                line.requires_division = payload["requires_division"]
                line.profile_code = payload["profile_code"]
                line.sort_order = payload["sort_order"]
                line.updated_by_user_id = current_user.id
                line.scopes.clear()
                line.periods.clear()
                line.scopes.append(EducationPlanLineScope(
                    **payload["scope"],
                ))
                if payload["period"]:
                    line.periods.append(EducationPlanLinePeriod(
                        **payload["period"],
                    ))
                touch_plan(plan, user_id=current_user.id)
                _synchronize_plan_workload(plan, line)
                db.session.commit()
            except (PlanValidationError, WorkloadDistributionError) as exc:
                db.session.rollback()
                flash(str(exc), "danger")
            except IntegrityError:
                db.session.rollback()
                flash(
                    "Строка плана конфликтует с существующими данными.",
                    "danger",
                )
            else:
                flash("Строка плана обновлена.", "success")
                return redirect(
                    url_for("workload.plan_detail", plan_id=plan.id)
                )

        return _render_plan_line_form(plan, line)

    @workload_bp.post(
        "/plans/<int:plan_id>/lines/<int:line_id>/delete"
    )
    @login_required
    def plan_line_delete(plan_id, line_id):
        plan = _get_plan(plan_id, for_update=True)
        line = EducationPlanLine.query.filter_by(
            id=line_id,
            education_plan_id=plan.id,
        ).first_or_404()
        try:
            require_plan_editable(
                plan,
                expected_revision=request.form.get("revision", type=int),
            )
            deleted = delete_plan_lines_with_dependencies([line])
            touch_plan(plan, user_id=current_user.id)
            db.session.commit()
        except (PlanValidationError, WorkloadDistributionError) as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash(
                "Строка плана удалена. "
                f"Удалено групп: {deleted['groups']}, "
                f"назначений нагрузки: {deleted['assignments']}.",
                "success",
            )
        return redirect(url_for("workload.plan_detail", plan_id=plan.id))

    @workload_bp.post(
        "/plans/<int:plan_id>/lines/<int:line_id>/hours"
    )
    @login_required
    def plan_line_update_hours(plan_id, line_id):
        plan = _get_plan(plan_id, for_update=True)
        line = EducationPlanLine.query.filter_by(
            id=line_id,
            education_plan_id=plan.id,
        ).first_or_404()
        try:
            require_plan_editable(
                plan,
                expected_revision=request.form.get("revision", type=int),
            )
            weekly_hours = parse_decimal(
                request.form.get("weekly_hours"),
                "часы в неделю",
            )
            weeks_count = parse_decimal(
                request.form.get("weeks_count"),
                "количество учебных недель",
            )
            annual_hours = parse_decimal(
                request.form.get("annual_hours"),
                "часы в год",
            )
            annual_hours = calculate_annual_hours(
                weekly_hours,
                weeks_count,
                annual_hours,
            )
            validate_line_values(
                plan,
                line.education_activity,
                line.component_kind,
                weekly_hours,
                annual_hours,
                weeks_count,
            )
            line.weekly_hours = weekly_hours
            line.weeks_count = weeks_count
            line.annual_hours = annual_hours
            line.updated_by_user_id = current_user.id
            touch_plan(plan, user_id=current_user.id)
            _synchronize_plan_workload(plan, line)
            db.session.commit()
        except (PlanValidationError, WorkloadDistributionError) as exc:
            db.session.rollback()
            if _is_matrix_ajax_request():
                return jsonify({"ok": False, "error": str(exc)}), 422
            flash(str(exc), "danger")
        else:
            if _is_matrix_ajax_request():
                return _matrix_line_response(plan, line)
            flash("Часы строки обновлены.", "success")
        return redirect(
            url_for(
                "workload.plan_matrix",
                plan_id=plan.id,
                selected_line_id=line.id,
            )
        )

    @workload_bp.get("/plans/<int:plan_id>/matrix")
    @login_required
    def plan_matrix(plan_id):
        requested_plan = _get_plan(plan_id)
        bundle_root = plan_bundle_root(requested_plan)
        bundle_parts = plan_bundle_parts(bundle_root)
        requested_part = (
            (request.args.get("part") or requested_plan.plan_kind)
            .strip()
            .upper()
        )
        plan = bundle_parts.get(requested_part, bundle_root)
        matrix = _build_plan_matrix(plan)
        selected_line_id = request.args.get("selected_line_id", type=int)
        selected_line = next(
            (
                line
                for line in plan.lines
                if line.id == selected_line_id
            ),
            None,
        )
        if selected_line is None and plan.lines:
            selected_line = plan.lines[0]
        selected_scope_label = (
            _scope_label(selected_line.scopes[0])
            if selected_line and selected_line.scopes
            else None
        )
        return render_template(
            "workload/plan_matrix.html",
            plan=plan,
            bundle_root=bundle_root,
            bundle_parts=bundle_parts,
            bundle_kinds=PLAN_BUNDLE_KINDS,
            bundle_labels=PLAN_BUNDLE_LABELS,
            matrix=matrix,
            selected_line=selected_line,
            selected_scope_label=selected_scope_label,
            can_update=_can_update_plan(plan),
            component_labels=PLAN_COMPONENT_LABELS,
            plan_kind_labels=PLAN_KIND_LABELS,
            plan_status_labels=PLAN_STATUS_LABELS,
            activities=_available_activities(plan),
            component_kinds=tuple(
                component
                for component in PLAN_COMPONENT_KINDS
                if component in PLAN_COMPONENTS_BY_KIND[plan.plan_kind]
            ),
            default_weeks_count=DEFAULT_WEEKS_COUNT,
        )


__all__ = ["register_plan_routes"]
