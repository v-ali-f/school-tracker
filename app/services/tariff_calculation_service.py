import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, ROUND_HALF_UP

from sqlalchemy import func

from app.core.extensions import db
from app.models import (
    CalculationParameterSet,
    TariffAllowanceRule,
    TariffAllowanceType,
    TariffCalculationRun,
    TariffCoefficientType,
    TariffCoefficientValue,
    TariffLine,
    TariffLineComponent,
    TariffRateNorm,
    WorkloadAssignment,
)


ZERO = Decimal("0")
MONEY_QUANTUM = Decimal("0.01")
CALCULATION_QUANTUM = Decimal("0.000001")
FTE_QUANTUM = Decimal("0.000001")
ALGORITHM_VERSION = "ALT-TARIFF-1.0"


class TariffCalculationError(ValueError):
    pass


def normalize_rule_code(value):
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper())
    return normalized.strip("_")


def decimal_parameter(
    value,
    label,
    *,
    required=True,
    scale=CALCULATION_QUANTUM,
    allow_zero=True,
):
    text = str(value or "").strip().replace(",", ".")
    if not text:
        if required:
            raise TariffCalculationError(f"Укажите {label}.")
        return None
    try:
        number = Decimal(text).quantize(scale, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise TariffCalculationError(
            f"Поле «{label}» должно содержать число."
        ) from exc
    if number < ZERO or (not allow_zero and number == ZERO):
        qualifier = "больше нуля" if not allow_zero else "неотрицательным"
        raise TariffCalculationError(
            f"Поле «{label}» должно быть {qualifier}."
        )
    return number


def money_round(value, rounding_rule):
    method = {
        "HALF_UP": ROUND_HALF_UP,
        "HALF_EVEN": ROUND_HALF_EVEN,
    }.get(rounding_rule)
    if method is None:
        raise TariffCalculationError("Неизвестное правило округления.")
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=method)


def ensure_standard_tariff_types(organization_id=None):
    coefficient_specs = (
        (
            "DIVISION",
            "Доплата за деление и наполняемость",
            "GROUP_SIZE_RATIO",
            "GROUP",
        ),
        (
            "COMPLEXITY",
            "Коэффициент сложности",
            "MULTIPLIER",
            "ACTIVITY",
        ),
    )
    coefficient_types = {}
    for code, name, calculation_kind, scope in coefficient_specs:
        item = TariffCoefficientType.query.filter_by(
            organization_id=organization_id,
            code=code,
        ).first()
        if item is None:
            item = TariffCoefficientType(
                organization_id=organization_id,
                code=code,
                name=name,
                calculation_kind=calculation_kind,
                applicable_scope=scope,
                is_configurable=True,
                is_active=True,
            )
            db.session.add(item)
            db.session.flush()
        coefficient_types[code] = item

    allowance_specs = (
        (
            "CLASSROOM_CITY",
            "Городское вознаграждение за классное руководство",
            "FIXED",
            "EMPLOYEE",
        ),
        (
            "CLASSROOM_FEDERAL",
            "Федеральное вознаграждение за классное руководство",
            "FIXED",
            "EMPLOYEE",
        ),
        (
            "OTHER_FIXED",
            "Иная фиксированная доплата",
            "FIXED",
            "EMPLOYEE",
        ),
        (
            "OTHER_PERCENT",
            "Иная процентная доплата",
            "PERCENT",
            "TARIFF_LINE",
        ),
    )
    allowance_types = {}
    for code, name, amount_kind, scope in allowance_specs:
        item = TariffAllowanceType.query.filter_by(
            organization_id=organization_id,
            code=code,
        ).first()
        if item is None:
            item = TariffAllowanceType(
                organization_id=organization_id,
                code=code,
                name=name,
                amount_kind=amount_kind,
                scope_kind=scope,
                is_manual_allowed=True,
                is_active=True,
            )
            db.session.add(item)
            db.session.flush()
        allowance_types[code] = item
    return coefficient_types, allowance_types


def validate_parameter_set(parameter_set):
    if parameter_set.tariff_version.status != "DRAFT":
        raise TariffCalculationError(
            "Настройки можно изменять только в черновой версии."
        )
    if parameter_set.status != "DRAFT":
        raise TariffCalculationError("Набор параметров заблокирован.")
    if parameter_set.valid_to < parameter_set.valid_from:
        raise TariffCalculationError(
            "Дата окончания набора параметров раньше даты начала."
        )
    if Decimal(parameter_set.student_hour_rate or ZERO) < ZERO:
        raise TariffCalculationError(
            "Стоимость ученико-часа не может быть отрицательной."
        )
    if Decimal(parameter_set.periods_per_year or ZERO) <= ZERO:
        raise TariffCalculationError(
            "Количество расчётных периодов должно быть больше нуля."
        )
    if parameter_set.rounding_rule not in {"HALF_UP", "HALF_EVEN"}:
        raise TariffCalculationError("Выберите допустимое округление.")


def validate_rate_norm(rate_norm):
    if Decimal(rate_norm.weekly_norm_hours or ZERO) <= ZERO:
        raise TariffCalculationError(
            "Норма часов на ставку должна быть больше нуля."
        )
    if rate_norm.valid_to < rate_norm.valid_from:
        raise TariffCalculationError(
            "Дата окончания нормы раньше даты начала."
        )
    query = TariffRateNorm.query.filter(
        TariffRateNorm.parameter_set_id == rate_norm.parameter_set_id,
        TariffRateNorm.position_code == rate_norm.position_code,
        TariffRateNorm.valid_from <= rate_norm.valid_to,
        TariffRateNorm.valid_to >= rate_norm.valid_from,
    )
    if rate_norm.id is not None:
        query = query.filter(TariffRateNorm.id != rate_norm.id)
    if rate_norm.activity_kind is None:
        query = query.filter(TariffRateNorm.activity_kind.is_(None))
    else:
        query = query.filter(
            TariffRateNorm.activity_kind == rate_norm.activity_kind
        )
    if query.first() is not None:
        raise TariffCalculationError(
            "Для этой должности и вида деятельности уже действует "
            "пересекающаяся норма."
        )


def _period_contains(item, date_from, date_to):
    return item.valid_from <= date_from and item.valid_to >= date_to


def resolve_rate_norm(parameter_set, assignment):
    activity_kind = assignment.workload_need.education_activity.activity_kind
    candidates = [
        item
        for item in parameter_set.rate_norms
        if item.position_code == assignment.position_code
        and _period_contains(item, assignment.date_from, assignment.date_to)
        and item.activity_kind in {activity_kind, None}
    ]
    candidates.sort(
        key=lambda item: (
            item.activity_kind is None,
            item.valid_from,
            item.id,
        )
    )
    exact = [
        item for item in candidates
        if item.activity_kind == activity_kind
    ]
    selected = exact or [
        item for item in candidates
        if item.activity_kind is None
    ]
    if len(selected) != 1:
        raise TariffCalculationError(
            "Не найдена однозначная норма ставки для должности "
            f"«{assignment.position_title or assignment.position_code}» "
            f"и вида деятельности {activity_kind}."
        )
    return selected[0]


def _plan_kind(assignment):
    group = assignment.workload_need.teaching_group
    if group is None or group.source_plan_line is None:
        return None
    return group.source_plan_line.education_plan.plan_kind


def _condition_matches(condition_kind, condition_data, assignment):
    condition_data = condition_data or {}
    if condition_kind == "ALWAYS":
        return True
    if condition_kind == "ACTIVITY":
        activity_ids = {
            int(value) for value in condition_data.get("activity_ids", [])
        }
        return assignment.workload_need.education_activity_id in activity_ids
    if condition_kind == "PLAN_KIND":
        return _plan_kind(assignment) in set(
            condition_data.get("plan_kinds", [])
        )
    return False


def _clamp(value, minimum, maximum):
    if minimum is not None:
        value = max(value, Decimal(minimum))
    if maximum is not None:
        value = min(value, Decimal(maximum))
    return value


def resolve_coefficient_components(
    parameter_set,
    assignment,
    *,
    base_raw,
    population,
):
    resolved = []
    values = sorted(
        parameter_set.coefficient_values,
        key=lambda item: (item.priority, item.id),
    )
    for rule in values:
        coefficient_type = rule.coefficient_type
        if not coefficient_type.is_active:
            continue
        if not _period_contains(
            rule,
            assignment.date_from,
            assignment.date_to,
        ):
            continue
        if not _condition_matches(
            rule.condition_kind,
            rule.condition_data,
            assignment,
        ):
            continue
        kind = coefficient_type.calculation_kind
        configured = Decimal(rule.value)
        effective = configured
        if kind == "GROUP_SIZE_RATIO":
            if population <= ZERO:
                raise TariffCalculationError(
                    "Нельзя рассчитать коэффициент деления при нулевой "
                    "численности группы."
                )
            effective = configured / population
            effective = _clamp(
                effective,
                rule.minimum_value,
                rule.maximum_value,
            )
            if (rule.condition_data or {}).get("only_above_one", True):
                effective = max(Decimal("1"), effective)
            amount_raw = base_raw * (effective - Decimal("1"))
            expression = (
                f"{base_raw} × ({effective} − 1), "
                f"норматив {configured} / численность {population}"
            )
        elif kind == "MULTIPLIER":
            amount_raw = base_raw * (effective - Decimal("1"))
            expression = f"{base_raw} × ({effective} − 1)"
        elif kind == "PERCENT":
            amount_raw = base_raw * effective / Decimal("100")
            expression = f"{base_raw} × {effective}%"
        else:
            raise TariffCalculationError(
                f"Неизвестный вид коэффициента {kind}."
            )
        resolved.append({
            "rule": rule,
            "code": coefficient_type.code,
            "name": coefficient_type.name,
            "numeric_value": effective.quantize(CALCULATION_QUANTUM),
            "amount_raw": amount_raw.quantize(CALCULATION_QUANTUM),
            "expression": expression,
        })
    return resolved


def _allowance_condition_matches(rule, assignment):
    data = rule.condition_data or {}
    employee_ids = {
        int(value) for value in data.get("employee_user_ids", [])
    }
    if employee_ids and assignment.employee_user_id not in employee_ids:
        return False
    assignment_ids = {
        int(value) for value in data.get("assignment_ids", [])
    }
    if assignment_ids and assignment.id not in assignment_ids:
        return False
    activity_ids = {
        int(value) for value in data.get("activity_ids", [])
    }
    if (
        activity_ids
        and assignment.workload_need.education_activity_id not in activity_ids
    ):
        return False
    plan_kinds = set(data.get("plan_kinds", []))
    if plan_kinds and _plan_kind(assignment) not in plan_kinds:
        return False
    return True


def resolve_allowance_components(
    parameter_set,
    assignment,
    *,
    base_raw,
    subtotal_raw,
    first_assignment_by_employee,
):
    resolved = []
    rules = sorted(
        parameter_set.allowance_rules,
        key=lambda item: (item.priority, item.id),
    )
    for rule in rules:
        allowance_type = rule.allowance_type
        if not allowance_type.is_active:
            continue
        if not _period_contains(
            rule,
            assignment.date_from,
            assignment.date_to,
        ):
            continue
        if not _allowance_condition_matches(rule, assignment):
            continue
        if (
            allowance_type.scope_kind == "EMPLOYEE"
            and first_assignment_by_employee.get(
                assignment.employee_user_id
            ) != assignment.id
        ):
            continue
        if allowance_type.amount_kind == "FIXED":
            amount_raw = Decimal(rule.fixed_amount or ZERO)
            numeric_value = amount_raw
            expression = f"фиксированная сумма {amount_raw}"
        elif allowance_type.amount_kind == "PERCENT":
            numeric_value = Decimal(rule.percent_value or ZERO)
            basis = base_raw if rule.base_kind == "BASE" else subtotal_raw
            amount_raw = basis * numeric_value / Decimal("100")
            expression = f"{basis} × {numeric_value}%"
        else:
            raise TariffCalculationError(
                f"Неизвестный вид доплаты {allowance_type.amount_kind}."
            )
        resolved.append({
            "rule": rule,
            "code": allowance_type.code,
            "name": allowance_type.name,
            "numeric_value": numeric_value.quantize(CALCULATION_QUANTUM),
            "amount_raw": amount_raw.quantize(CALCULATION_QUANTUM),
            "expression": expression,
        })
    return resolved


def _canonical_hash(payload):
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def calculation_input_payload(parameter_set, assignments):
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "parameter_set": {
            "id": parameter_set.id,
            "revision": parameter_set.revision,
            "student_hour_rate": str(parameter_set.student_hour_rate),
            "periods_per_year": str(parameter_set.periods_per_year),
            "rounding_rule": parameter_set.rounding_rule,
            "rate_norms": [
                {
                    "id": item.id,
                    "position_code": item.position_code,
                    "activity_kind": item.activity_kind,
                    "weekly_norm_hours": str(item.weekly_norm_hours),
                    "valid_from": item.valid_from.isoformat(),
                    "valid_to": item.valid_to.isoformat(),
                }
                for item in sorted(
                    parameter_set.rate_norms,
                    key=lambda row: row.id,
                )
            ],
            "coefficients": [
                {
                    "id": item.id,
                    "type": item.coefficient_type.code,
                    "value": str(item.value),
                    "condition_kind": item.condition_kind,
                    "condition_data": item.condition_data,
                    "priority": item.priority,
                    "valid_from": item.valid_from.isoformat(),
                    "valid_to": item.valid_to.isoformat(),
                }
                for item in sorted(
                    parameter_set.coefficient_values,
                    key=lambda row: row.id,
                )
            ],
            "allowances": [
                {
                    "id": item.id,
                    "type": item.allowance_type.code,
                    "fixed_amount": str(item.fixed_amount),
                    "percent_value": str(item.percent_value),
                    "base_kind": item.base_kind,
                    "condition_data": item.condition_data,
                    "priority": item.priority,
                    "valid_from": item.valid_from.isoformat(),
                    "valid_to": item.valid_to.isoformat(),
                }
                for item in sorted(
                    parameter_set.allowance_rules,
                    key=lambda row: row.id,
                )
            ],
        },
        "assignments": [
            {
                "id": item.id,
                "revision": item.revision,
                "employee_user_id": item.employee_user_id,
                "position_code": item.position_code,
                "position_title": item.position_title,
                "activity_id": item.workload_need.education_activity_id,
                "group_id": item.workload_need.teaching_group_id,
                "weekly_hours": str(item.weekly_hours),
                "annual_hours": str(item.annual_hours),
                "date_from": item.date_from.isoformat(),
                "date_to": item.date_to.isoformat(),
                "population": (
                    item.workload_need.teaching_group.actual_size
                    if item.workload_need.teaching_group
                    else None
                ),
            }
            for item in assignments
        ],
    }


def current_tariff_input_hash(tariff_version, parameter_set):
    assignments = (
        WorkloadAssignment.query
        .filter(
            WorkloadAssignment.tariff_version_id == tariff_version.id,
            WorkloadAssignment.status != "CANCELLED",
            WorkloadAssignment.assignment_kind != "VACANCY",
        )
        .order_by(WorkloadAssignment.id.asc())
        .all()
    )
    return _canonical_hash(
        calculation_input_payload(parameter_set, assignments)
    )


def _new_component(
    line,
    sequence_no,
    *,
    kind,
    code,
    name,
    numeric_value=None,
    amount_raw=None,
    amount_value=None,
    expression=None,
    source_type=None,
    source_id=None,
    user_id=None,
):
    return TariffLineComponent(
        tariff_line=line,
        component_kind=kind,
        component_code=code,
        component_name=name,
        sequence_no=sequence_no,
        numeric_value=numeric_value,
        amount_raw=amount_raw,
        amount_value=amount_value,
        calculation_expression=expression,
        source_entity_type=source_type,
        source_entity_id=source_id,
        created_by_user_id=user_id,
    )


def _calculate_line(
    run,
    parameter_set,
    assignment,
    *,
    first_assignment_by_employee,
    user_id,
):
    rate_norm = resolve_rate_norm(parameter_set, assignment)
    weekly = Decimal(assignment.weekly_hours or ZERO)
    annual = Decimal(assignment.annual_hours or ZERO)
    norm = Decimal(rate_norm.weekly_norm_hours)
    fte = (weekly / norm).quantize(FTE_QUANTUM, rounding=ROUND_HALF_UP)
    group = assignment.workload_need.teaching_group
    population = Decimal(
        (
            group.actual_size
            if group is not None and group.actual_size is not None
            else group.planned_size
            if group is not None and group.planned_size is not None
            else 0
        )
    ).quantize(Decimal("0.001"))
    if population <= ZERO:
        raise TariffCalculationError(
            "У группы отсутствует положительная расчётная численность."
        )
    student_hour_rate = Decimal(parameter_set.student_hour_rate)
    periods = Decimal(parameter_set.periods_per_year)
    base_raw = (
        student_hour_rate * population * annual / periods
    ).quantize(CALCULATION_QUANTUM, rounding=ROUND_HALF_UP)
    base_amount = money_round(base_raw, parameter_set.rounding_rule)
    coefficients = resolve_coefficient_components(
        parameter_set,
        assignment,
        base_raw=base_raw,
        population=population,
    )
    coefficient_total = sum(
        (item["amount_raw"] for item in coefficients),
        ZERO,
    )
    subtotal_raw = base_raw + coefficient_total
    allowances = resolve_allowance_components(
        parameter_set,
        assignment,
        base_raw=base_raw,
        subtotal_raw=subtotal_raw,
        first_assignment_by_employee=first_assignment_by_employee,
    )
    allowance_total = sum(
        (item["amount_raw"] for item in allowances),
        ZERO,
    )
    total_raw = (
        subtotal_raw + allowance_total
    ).quantize(CALCULATION_QUANTUM, rounding=ROUND_HALF_UP)
    total_amount = money_round(total_raw, parameter_set.rounding_rule)
    formula = {
        "algorithm_version": ALGORITHM_VERSION,
        "assignment_id": assignment.id,
        "parameter_set_id": parameter_set.id,
        "rate_norm_id": rate_norm.id,
        "inputs": {
            "weekly_hours": str(weekly),
            "annual_hours": str(annual),
            "rate_norm_hours": str(norm),
            "fte_value": str(fte),
            "population": str(population),
            "student_hour_rate": str(student_hour_rate),
            "periods_per_year": str(periods),
        },
        "base_expression": (
            f"{student_hour_rate} × {population} × {annual} / {periods}"
        ),
        "coefficient_rule_ids": [
            item["rule"].id for item in coefficients
        ],
        "allowance_rule_ids": [
            item["rule"].id for item in allowances
        ],
        "rounding_rule": parameter_set.rounding_rule,
        "base_raw": str(base_raw),
        "total_raw": str(total_raw),
        "total_amount": str(total_amount),
    }
    line_hash = _canonical_hash(formula)
    line = TariffLine(
        calculation_run=run,
        workload_assignment_id=assignment.id,
        employee_user_id=assignment.employee_user_id,
        position_code=assignment.position_code,
        position_title=assignment.position_title or assignment.position_code,
        education_activity_id=(
            assignment.workload_need.education_activity_id
        ),
        teaching_group_id=assignment.workload_need.teaching_group_id,
        department_id=assignment.department_id,
        building_id=assignment.building_id,
        date_from=assignment.date_from,
        date_to=assignment.date_to,
        weekly_hours=weekly,
        annual_hours=annual,
        rate_norm_hours=norm,
        fte_value=fte,
        population_value=population,
        student_hour_rate=student_hour_rate,
        base_amount_raw=base_raw,
        base_amount=base_amount,
        total_amount_raw=total_raw,
        total_amount=total_amount,
        formula_snapshot=formula,
        line_hash=line_hash,
    )
    db.session.add(line)
    db.session.flush()
    sequence = 1
    inputs = (
        ("WEEKLY_HOURS", "Часов в неделю", weekly),
        ("ANNUAL_HOURS", "Часов за период", annual),
        ("RATE_NORM_HOURS", "Норма часов на ставку", norm),
        ("FTE_VALUE", "Доля ставки", fte),
        ("POPULATION", "Расчётная численность", population),
        ("STUDENT_HOUR_RATE", "Стоимость ученико-часа", student_hour_rate),
    )
    for code, name, value in inputs:
        db.session.add(_new_component(
            line,
            sequence,
            kind="INPUT",
            code=code,
            name=name,
            numeric_value=value,
            source_type="CALCULATION_INPUT",
            user_id=user_id,
        ))
        sequence += 1
    db.session.add(_new_component(
        line,
        sequence,
        kind="INPUT",
        code="BASE_AMOUNT",
        name="Основная оплата",
        numeric_value=base_raw,
        amount_raw=base_raw,
        amount_value=base_amount,
        expression=formula["base_expression"],
        source_type="CALCULATION_PARAMETER_SET",
        source_id=parameter_set.id,
        user_id=user_id,
    ))
    sequence += 1
    for item in coefficients:
        db.session.add(_new_component(
            line,
            sequence,
            kind="COEFFICIENT",
            code=item["code"],
            name=item["name"],
            numeric_value=item["numeric_value"],
            amount_raw=item["amount_raw"],
            amount_value=money_round(
                item["amount_raw"],
                parameter_set.rounding_rule,
            ),
            expression=item["expression"],
            source_type="TARIFF_COEFFICIENT_VALUE",
            source_id=item["rule"].id,
            user_id=user_id,
        ))
        sequence += 1
    for item in allowances:
        db.session.add(_new_component(
            line,
            sequence,
            kind="ALLOWANCE",
            code=item["code"],
            name=item["name"],
            numeric_value=item["numeric_value"],
            amount_raw=item["amount_raw"],
            amount_value=money_round(
                item["amount_raw"],
                parameter_set.rounding_rule,
            ),
            expression=item["expression"],
            source_type="TARIFF_ALLOWANCE_RULE",
            source_id=item["rule"].id,
            user_id=user_id,
        ))
        sequence += 1
    db.session.add(_new_component(
        line,
        sequence,
        kind="TOTAL",
        code="TOTAL",
        name="Итого по строке",
        numeric_value=total_raw,
        amount_raw=total_raw,
        amount_value=total_amount,
        expression=(
            f"{base_raw} + {coefficient_total} + {allowance_total}"
        ),
        source_type="TARIFF_LINE",
        user_id=user_id,
    ))
    return line


def calculate_tariff_version(tariff_version, parameter_set, *, user_id):
    if tariff_version.status != "DRAFT":
        raise TariffCalculationError(
            "Предварительный расчёт доступен только для черновой версии."
        )
    if parameter_set.tariff_version_id != tariff_version.id:
        raise TariffCalculationError(
            "Набор параметров относится к другой версии."
        )
    validate_parameter_set(parameter_set)
    assignments = (
        WorkloadAssignment.query
        .filter(
            WorkloadAssignment.tariff_version_id == tariff_version.id,
            WorkloadAssignment.status != "CANCELLED",
            WorkloadAssignment.assignment_kind != "VACANCY",
        )
        .order_by(WorkloadAssignment.id.asc())
        .all()
    )
    if not assignments:
        raise TariffCalculationError(
            "Для версии нет назначений педагогов, доступных для расчёта."
        )
    payload = calculation_input_payload(parameter_set, assignments)
    input_hash = _canonical_hash(payload)
    existing = (
        TariffCalculationRun.query
        .filter_by(
            tariff_version_id=tariff_version.id,
            parameter_set_id=parameter_set.id,
            input_hash=input_hash,
            status="SUCCEEDED",
        )
        .order_by(TariffCalculationRun.run_no.desc())
        .first()
    )
    if existing is not None:
        return existing, True
    max_run = (
        db.session.query(func.max(TariffCalculationRun.run_no))
        .filter(
            TariffCalculationRun.tariff_version_id == tariff_version.id
        )
        .scalar()
        or 0
    )
    input_revision = sum(item.revision for item in assignments)
    run = TariffCalculationRun(
        tariff_version_id=tariff_version.id,
        parameter_set_id=parameter_set.id,
        run_no=max_run + 1,
        status="RUNNING",
        started_at=datetime.utcnow(),
        input_revision=input_revision,
        algorithm_version=ALGORITHM_VERSION,
        input_hash=input_hash,
        created_by_user_id=user_id,
    )
    db.session.add(run)
    db.session.flush()
    first_assignment_by_employee = {}
    for assignment in assignments:
        first_assignment_by_employee.setdefault(
            assignment.employee_user_id,
            assignment.id,
        )
    errors = []
    calculated = 0
    for assignment in assignments:
        try:
            _calculate_line(
                run,
                parameter_set,
                assignment,
                first_assignment_by_employee=first_assignment_by_employee,
                user_id=user_id,
            )
            calculated += 1
        except TariffCalculationError as exc:
            errors.append({
                "assignment_id": assignment.id,
                "employee_user_id": assignment.employee_user_id,
                "message": str(exc),
            })
    run.finished_at = datetime.utcnow()
    run.summary_data = {
        "assignment_count": len(assignments),
        "calculated_count": calculated,
        "error_count": len(errors),
        "errors": errors,
        "input_hash": input_hash,
    }
    if errors:
        run.status = "FAILED"
        run.error_text = "\n".join(
            f"Назначение {item['assignment_id']}: {item['message']}"
            for item in errors
        )
    else:
        run.status = "SUCCEEDED"
        run.error_text = None
    db.session.flush()
    return run, False


def latest_successful_run(tariff_version_id):
    return (
        TariffCalculationRun.query
        .filter_by(
            tariff_version_id=tariff_version_id,
            status="SUCCEEDED",
        )
        .order_by(
            TariffCalculationRun.run_no.desc(),
            TariffCalculationRun.id.desc(),
        )
        .first()
    )


def tariff_run_totals(run):
    result = {
        "weekly_hours": ZERO,
        "fte": ZERO,
        "base_amount": ZERO,
        "total_amount": ZERO,
        "employees": set(),
    }
    if run is None:
        result["employee_count"] = 0
        return result
    for line in run.lines:
        result["weekly_hours"] += Decimal(line.weekly_hours or ZERO)
        result["fte"] += Decimal(line.fte_value or ZERO)
        result["base_amount"] += Decimal(line.base_amount or ZERO)
        result["total_amount"] += Decimal(line.total_amount or ZERO)
        result["employees"].add(line.employee_user_id)
    result["employee_count"] = len(result["employees"])
    return result


__all__ = [
    "ALGORITHM_VERSION",
    "CALCULATION_QUANTUM",
    "FTE_QUANTUM",
    "MONEY_QUANTUM",
    "TariffCalculationError",
    "calculate_tariff_version",
    "calculation_input_payload",
    "current_tariff_input_hash",
    "decimal_parameter",
    "ensure_standard_tariff_types",
    "latest_successful_run",
    "money_round",
    "normalize_rule_code",
    "resolve_allowance_components",
    "resolve_coefficient_components",
    "resolve_rate_norm",
    "tariff_run_totals",
    "validate_parameter_set",
    "validate_rate_norm",
]
