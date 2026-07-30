from datetime import date
from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.core.feature_flags import WORKLOAD_WRITE, is_feature_enabled
from app.models import (
    ACTIVITY_KIND_LABELS,
    ALLOWANCE_BASE_KINDS,
    COEFFICIENT_CONDITION_KINDS,
    PLAN_KIND_LABELS,
    ROUNDING_RULES,
    CalculationParameterSet,
    EducationActivity,
    OrganizationSettings,
    TariffAllowanceRule,
    TariffAllowanceType,
    TariffCalculationRun,
    TariffCoefficientType,
    TariffCoefficientValue,
    TariffCycle,
    TariffLine,
    TariffRateNorm,
    TariffVersion,
    User,
)
from app.services.tariff_calculation_service import (
    TariffCalculationError,
    calculate_tariff_version,
    decimal_parameter,
    ensure_standard_tariff_types,
    normalize_rule_code,
    tariff_run_totals,
    validate_parameter_set,
    validate_rate_norm,
)

from .access import can_use_workload_permission, require_workload_write
from .scopes import resolve_workload_scope


ZERO = Decimal("0")
RUN_STATUS_LABELS = {
    "QUEUED": "В очереди",
    "RUNNING": "Выполняется",
    "SUCCEEDED": "Выполнен",
    "FAILED": "С ошибками",
    "CANCELLED": "Отменён",
}
PARAMETER_STATUS_LABELS = {
    "DRAFT": "Черновик",
    "LOCKED": "Заблокирован",
}


def _current_organization_id():
    organization = (
        OrganizationSettings.query
        .filter_by(is_active=True)
        .order_by(OrganizationSettings.id.asc())
        .first()
    )
    return organization.id if organization else None


def _require_tariff_read():
    if not can_use_workload_permission("workload.read", current_user):
        abort(403)


def _require_finance_read():
    if not can_use_workload_permission(
        "workload.finance.read",
        current_user,
    ):
        abort(403)


def _require_calculate():
    require_workload_write()
    if not can_use_workload_permission("workload.calculate", current_user):
        abort(403)


def _versions_query():
    organization_id = _current_organization_id()
    query = TariffVersion.query.join(TariffCycle)
    if organization_id is None:
        query = query.filter(TariffCycle.organization_id.is_(None))
    else:
        query = query.filter(TariffCycle.organization_id == organization_id)
    return query.order_by(TariffVersion.id.desc())


def _get_version(version_id, *, draft_only=False):
    query = _versions_query().filter(TariffVersion.id == version_id)
    if draft_only:
        query = query.filter(TariffVersion.status == "DRAFT")
    return query.first_or_404()


def _get_parameter_set(parameter_set_id, *, editable=False):
    item = (
        CalculationParameterSet.query
        .filter(CalculationParameterSet.id == parameter_set_id)
        .first_or_404()
    )
    version = _get_version(item.tariff_version_id, draft_only=editable)
    if item.tariff_version_id != version.id:
        abort(404)
    if editable and item.status != "DRAFT":
        abort(409)
    return item


def _get_run(run_id):
    run = TariffCalculationRun.query.get_or_404(run_id)
    _get_version(run.tariff_version_id)
    return run


def _line_is_in_scope(line):
    scope = resolve_workload_scope(current_user)
    if scope.unrestricted:
        return True
    department_ok = (
        not scope.department_ids
        or line.department_id in scope.department_ids
    )
    building_ok = (
        not scope.building_ids
        or line.building_id in scope.building_ids
    )
    return department_ok and building_ok


def _parse_date(value, label):
    text = str(value or "").strip()
    if not text:
        raise TariffCalculationError(f"Укажите дату: {label}.")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise TariffCalculationError(
            f"Укажите корректную дату: {label}."
        ) from exc


def _active_employees():
    return (
        User.query
        .filter(
            User.is_active_user.is_(True),
            User.employment_status == "ACTIVE",
            User.archived_at.is_(None),
        )
        .order_by(
            User.last_name.asc(),
            User.first_name.asc(),
            User.middle_name.asc(),
        )
        .all()
    )


def _parameter_form_defaults(version):
    year = version.tariff_cycle.academic_year
    return {
        "valid_from": year.start_date,
        "valid_to": year.end_date,
        "rounding_rule": "HALF_UP",
        "currency_code": "RUB",
        "periods_per_year": Decimal("12"),
    }


def register_tariff_routes(workload_bp):
    @workload_bp.get("/tariffication/")
    @login_required
    def tariffication():
        _require_tariff_read()
        versions = _versions_query().all()
        selected_version_id = request.args.get("version_id", type=int)
        version = None
        if selected_version_id:
            version = _get_version(selected_version_id)
        elif versions:
            version = versions[0]
            selected_version_id = version.id
        runs = []
        selected_run = None
        lines = []
        parameter_sets = []
        if version is not None:
            parameter_sets = (
                CalculationParameterSet.query
                .filter_by(tariff_version_id=version.id)
                .order_by(CalculationParameterSet.id.desc())
                .all()
            )
            runs = (
                TariffCalculationRun.query
                .filter_by(tariff_version_id=version.id)
                .order_by(TariffCalculationRun.run_no.desc())
                .all()
            )
            run_id = request.args.get("run_id", type=int)
            if run_id:
                selected_run = next(
                    (item for item in runs if item.id == run_id),
                    None,
                )
                if selected_run is None:
                    abort(404)
            else:
                selected_run = next(
                    (item for item in runs if item.status == "SUCCEEDED"),
                    runs[0] if runs else None,
                )
            if selected_run is not None:
                lines = [
                    line for line in selected_run.lines
                    if _line_is_in_scope(line)
                ]
        can_view_finance = can_use_workload_permission(
            "workload.finance.read",
            current_user,
        )
        return render_template(
            "workload/tariffication.html",
            versions=versions,
            selected_version_id=selected_version_id,
            version=version,
            runs=runs,
            selected_run=selected_run,
            lines=lines,
            parameter_sets=parameter_sets,
            totals=tariff_run_totals(selected_run),
            run_status_labels=RUN_STATUS_LABELS,
            can_view_finance=can_view_finance,
            can_calculate=(
                version is not None
                and version.status == "DRAFT"
                and is_feature_enabled(WORKLOAD_WRITE)
                and can_use_workload_permission(
                    "workload.calculate",
                    current_user,
                )
            ),
        )

    @workload_bp.post("/tariffication/calculate")
    @login_required
    def tariffication_calculate():
        _require_calculate()
        version = _get_version(
            request.form.get("version_id", type=int),
            draft_only=True,
        )
        parameter_set = _get_parameter_set(
            request.form.get("parameter_set_id", type=int),
        )
        try:
            run, reused = calculate_tariff_version(
                version,
                parameter_set,
                user_id=current_user.id,
            )
            db.session.commit()
        except (TariffCalculationError, IntegrityError) as exc:
            db.session.rollback()
            message = (
                str(exc)
                if isinstance(exc, TariffCalculationError)
                else "Не удалось выполнить расчёт."
            )
            flash(message, "danger")
            return redirect(url_for(
                "workload.tariffication",
                version_id=version.id,
            ))
        if reused:
            flash(
                "Исходные данные не изменились. Открыт ранее выполненный "
                "расчёт.",
                "info",
            )
        elif run.status == "SUCCEEDED":
            flash(
                f"Расчёт № {run.run_no} выполнен успешно.",
                "success",
            )
        else:
            flash(
                f"Расчёт № {run.run_no} завершён с ошибками. "
                "Откройте протокол.",
                "danger",
            )
        return redirect(url_for(
            "workload.tariffication",
            version_id=version.id,
            run_id=run.id,
        ))

    @workload_bp.get("/tariffication/runs/<int:run_id>")
    @login_required
    def tariff_run_detail(run_id):
        _require_tariff_read()
        run = _get_run(run_id)
        lines = [line for line in run.lines if _line_is_in_scope(line)]
        return render_template(
            "workload/tariff_run_detail.html",
            run=run,
            selected_version=run.tariff_version,
            lines=lines,
            totals=tariff_run_totals(run),
            run_status_labels=RUN_STATUS_LABELS,
            can_view_finance=can_use_workload_permission(
                "workload.finance.read",
                current_user,
            ),
        )

    @workload_bp.get("/tariffication/lines/<int:line_id>")
    @login_required
    def tariff_line_detail(line_id):
        _require_tariff_read()
        line = TariffLine.query.get_or_404(line_id)
        _get_run(line.calculation_run_id)
        if not _line_is_in_scope(line):
            abort(403)
        return render_template(
            "workload/tariff_line_detail.html",
            line=line,
            selected_version=line.calculation_run.tariff_version,
            can_view_finance=can_use_workload_permission(
                "workload.finance.read",
                current_user,
            ),
        )

    @workload_bp.get("/tariffication/settings/")
    @login_required
    def tariff_settings():
        _require_finance_read()
        versions = _versions_query().all()
        selected_version_id = request.args.get("version_id", type=int)
        version = None
        if selected_version_id:
            version = _get_version(selected_version_id)
        elif versions:
            version = versions[0]
            selected_version_id = version.id
        parameter_sets = (
            CalculationParameterSet.query
            .filter_by(tariff_version_id=version.id)
            .order_by(CalculationParameterSet.id.desc())
            .all()
            if version else []
        )
        return render_template(
            "workload/tariff_settings.html",
            versions=versions,
            version=version,
            selected_version_id=selected_version_id,
            parameter_sets=parameter_sets,
            parameter_status_labels=PARAMETER_STATUS_LABELS,
            can_manage=(
                version is not None
                and version.status == "DRAFT"
                and is_feature_enabled(WORKLOAD_WRITE)
                and can_use_workload_permission(
                    "workload.calculate",
                    current_user,
                )
            ),
        )

    @workload_bp.route(
        "/tariffication/settings/new",
        methods=["GET", "POST"],
    )
    @login_required
    def tariff_parameter_set_new():
        _require_calculate()
        version = _get_version(
            request.values.get("version_id", type=int),
            draft_only=True,
        )
        defaults = _parameter_form_defaults(version)
        if request.method == "POST":
            try:
                item = CalculationParameterSet(
                    organization_id=version.tariff_cycle.organization_id,
                    tariff_version=version,
                    code=normalize_rule_code(request.form.get("code")),
                    name=" ".join(
                        (request.form.get("name") or "").split()
                    ),
                    valid_from=_parse_date(
                        request.form.get("valid_from"),
                        "начало действия",
                    ),
                    valid_to=_parse_date(
                        request.form.get("valid_to"),
                        "окончание действия",
                    ),
                    student_hour_rate=decimal_parameter(
                        request.form.get("student_hour_rate"),
                        "стоимость ученико-часа",
                    ),
                    periods_per_year=decimal_parameter(
                        request.form.get("periods_per_year"),
                        "количество расчётных периодов",
                        allow_zero=False,
                    ),
                    rounding_rule=(
                        request.form.get("rounding_rule") or ""
                    ).strip().upper(),
                    currency_code=(
                        request.form.get("currency_code") or "RUB"
                    ).strip().upper(),
                    status="DRAFT",
                    created_by_user_id=current_user.id,
                    updated_by_user_id=current_user.id,
                )
                if not item.code or not item.name:
                    raise TariffCalculationError(
                        "Укажите код и название набора."
                    )
                validate_parameter_set(item)
                db.session.add(item)
                ensure_standard_tariff_types(item.organization_id)
                db.session.commit()
            except (
                TariffCalculationError,
                IntegrityError,
            ) as exc:
                db.session.rollback()
                message = (
                    str(exc)
                    if isinstance(exc, TariffCalculationError)
                    else "Набор с таким кодом уже существует."
                )
                flash(message, "danger")
            else:
                flash("Набор параметров создан.", "success")
                return redirect(url_for(
                    "workload.tariff_parameter_set_detail",
                    parameter_set_id=item.id,
                ))
        return render_template(
            "workload/tariff_parameter_set_form.html",
            version=version,
            defaults=defaults,
            rounding_rules=ROUNDING_RULES,
        )

    @workload_bp.get(
        "/tariffication/settings/<int:parameter_set_id>"
    )
    @login_required
    def tariff_parameter_set_detail(parameter_set_id):
        _require_finance_read()
        item = _get_parameter_set(parameter_set_id)
        coefficient_types = (
            TariffCoefficientType.query
            .filter_by(
                organization_id=item.organization_id,
                is_active=True,
            )
            .order_by(TariffCoefficientType.name.asc())
            .all()
        )
        allowance_types = (
            TariffAllowanceType.query
            .filter_by(
                organization_id=item.organization_id,
                is_active=True,
            )
            .order_by(TariffAllowanceType.name.asc())
            .all()
        )
        return render_template(
            "workload/tariff_parameter_set_detail.html",
            parameter_set=item,
            selected_version=item.tariff_version,
            coefficient_types=coefficient_types,
            allowance_types=allowance_types,
            employees=_active_employees(),
            activities=(
                EducationActivity.query
                .filter_by(is_active=True)
                .order_by(EducationActivity.name.asc())
                .all()
            ),
            activity_kind_labels=ACTIVITY_KIND_LABELS,
            plan_kind_labels=PLAN_KIND_LABELS,
            coefficient_condition_kinds=COEFFICIENT_CONDITION_KINDS,
            allowance_base_kinds=ALLOWANCE_BASE_KINDS,
            can_manage=(
                item.status == "DRAFT"
                and item.tariff_version.status == "DRAFT"
                and is_feature_enabled(WORKLOAD_WRITE)
                and can_use_workload_permission(
                    "workload.calculate",
                    current_user,
                )
            ),
        )

    @workload_bp.post(
        "/tariffication/settings/<int:parameter_set_id>/rate-norms"
    )
    @login_required
    def tariff_rate_norm_add(parameter_set_id):
        _require_calculate()
        parameter_set = _get_parameter_set(
            parameter_set_id,
            editable=True,
        )
        try:
            rate_norm = TariffRateNorm(
                parameter_set_id=parameter_set.id,
                position_code=normalize_rule_code(
                    request.form.get("position_code")
                ),
                position_name=" ".join(
                    (request.form.get("position_name") or "").split()
                ),
                activity_kind=(
                    request.form.get("activity_kind") or ""
                ).strip().upper() or None,
                weekly_norm_hours=decimal_parameter(
                    request.form.get("weekly_norm_hours"),
                    "норму часов на ставку",
                    allow_zero=False,
                ),
                valid_from=_parse_date(
                    request.form.get("valid_from"),
                    "начало действия нормы",
                ),
                valid_to=_parse_date(
                    request.form.get("valid_to"),
                    "окончание действия нормы",
                ),
                source_text=" ".join(
                    (request.form.get("source_text") or "").split()
                ) or None,
                created_by_user_id=current_user.id,
            )
            if not rate_norm.position_code or not rate_norm.position_name:
                raise TariffCalculationError(
                    "Укажите код и название должности."
                )
            validate_rate_norm(rate_norm)
            db.session.add(rate_norm)
            parameter_set.revision += 1
            parameter_set.updated_by_user_id = current_user.id
            db.session.commit()
        except (TariffCalculationError, IntegrityError) as exc:
            db.session.rollback()
            flash(
                str(exc)
                if isinstance(exc, TariffCalculationError)
                else "Не удалось добавить норму.",
                "danger",
            )
        else:
            flash("Норма ставки добавлена.", "success")
        return redirect(url_for(
            "workload.tariff_parameter_set_detail",
            parameter_set_id=parameter_set.id,
        ))

    @workload_bp.post(
        "/tariffication/settings/<int:parameter_set_id>/coefficients"
    )
    @login_required
    def tariff_coefficient_add(parameter_set_id):
        _require_calculate()
        parameter_set = _get_parameter_set(
            parameter_set_id,
            editable=True,
        )
        coefficient_type = TariffCoefficientType.query.get_or_404(
            request.form.get("coefficient_type_id", type=int)
        )
        if coefficient_type.organization_id != parameter_set.organization_id:
            abort(404)
        condition_kind = (
            request.form.get("condition_kind") or "ALWAYS"
        ).strip().upper()
        condition_data = {}
        if condition_kind == "ACTIVITY":
            activity_id = request.form.get("activity_id", type=int)
            if not activity_id:
                flash("Выберите дисциплину.", "danger")
                return redirect(url_for(
                    "workload.tariff_parameter_set_detail",
                    parameter_set_id=parameter_set.id,
                ))
            condition_data["activity_ids"] = [activity_id]
        elif condition_kind == "PLAN_KIND":
            plan_kind = (
                request.form.get("plan_kind") or ""
            ).strip().upper()
            if not plan_kind:
                flash("Выберите вид плана.", "danger")
                return redirect(url_for(
                    "workload.tariff_parameter_set_detail",
                    parameter_set_id=parameter_set.id,
                ))
            condition_data["plan_kinds"] = [plan_kind]
        if coefficient_type.calculation_kind == "GROUP_SIZE_RATIO":
            condition_data["only_above_one"] = True
        try:
            rule = TariffCoefficientValue(
                parameter_set_id=parameter_set.id,
                coefficient_type_id=coefficient_type.id,
                value=decimal_parameter(
                    request.form.get("value"),
                    "значение коэффициента",
                ),
                condition_kind=condition_kind,
                condition_data=condition_data or None,
                priority=request.form.get("priority", type=int) or 100,
                minimum_value=decimal_parameter(
                    request.form.get("minimum_value"),
                    "минимальное значение",
                    required=False,
                ),
                maximum_value=decimal_parameter(
                    request.form.get("maximum_value"),
                    "максимальное значение",
                    required=False,
                ),
                valid_from=_parse_date(
                    request.form.get("valid_from"),
                    "начало действия коэффициента",
                ),
                valid_to=_parse_date(
                    request.form.get("valid_to"),
                    "окончание действия коэффициента",
                ),
                source_text=" ".join(
                    (request.form.get("source_text") or "").split()
                ) or None,
                created_by_user_id=current_user.id,
            )
            if rule.valid_to < rule.valid_from:
                raise TariffCalculationError(
                    "Дата окончания коэффициента раньше начала."
                )
            if (
                rule.minimum_value is not None
                and rule.maximum_value is not None
                and rule.maximum_value < rule.minimum_value
            ):
                raise TariffCalculationError(
                    "Максимум коэффициента меньше минимума."
                )
            db.session.add(rule)
            parameter_set.revision += 1
            parameter_set.updated_by_user_id = current_user.id
            db.session.commit()
        except (TariffCalculationError, IntegrityError) as exc:
            db.session.rollback()
            flash(
                str(exc)
                if isinstance(exc, TariffCalculationError)
                else "Не удалось добавить коэффициент.",
                "danger",
            )
        else:
            flash("Коэффициент добавлен.", "success")
        return redirect(url_for(
            "workload.tariff_parameter_set_detail",
            parameter_set_id=parameter_set.id,
        ))

    @workload_bp.post(
        "/tariffication/settings/<int:parameter_set_id>/allowances"
    )
    @login_required
    def tariff_allowance_add(parameter_set_id):
        _require_calculate()
        parameter_set = _get_parameter_set(
            parameter_set_id,
            editable=True,
        )
        allowance_type = TariffAllowanceType.query.get_or_404(
            request.form.get("allowance_type_id", type=int)
        )
        if allowance_type.organization_id != parameter_set.organization_id:
            abort(404)
        condition_data = {}
        employee_user_id = request.form.get(
            "employee_user_id",
            type=int,
        )
        if employee_user_id:
            condition_data["employee_user_ids"] = [employee_user_id]
        assignment_id = request.form.get("assignment_id", type=int)
        if assignment_id:
            condition_data["assignment_ids"] = [assignment_id]
        try:
            fixed_amount = decimal_parameter(
                request.form.get("fixed_amount"),
                "фиксированную сумму",
                required=False,
                scale=Decimal("0.01"),
            )
            percent_value = decimal_parameter(
                request.form.get("percent_value"),
                "процент",
                required=False,
            )
            if allowance_type.amount_kind == "FIXED":
                if fixed_amount is None:
                    raise TariffCalculationError(
                        "Укажите фиксированную сумму."
                    )
                percent_value = None
            else:
                if percent_value is None:
                    raise TariffCalculationError("Укажите процент.")
                fixed_amount = None
            rule = TariffAllowanceRule(
                parameter_set_id=parameter_set.id,
                allowance_type_id=allowance_type.id,
                fixed_amount=fixed_amount,
                percent_value=percent_value,
                base_kind=(
                    request.form.get("base_kind") or "BASE"
                ).strip().upper(),
                condition_data=condition_data or None,
                priority=request.form.get("priority", type=int) or 100,
                valid_from=_parse_date(
                    request.form.get("valid_from"),
                    "начало действия доплаты",
                ),
                valid_to=_parse_date(
                    request.form.get("valid_to"),
                    "окончание действия доплаты",
                ),
                source_text=" ".join(
                    (request.form.get("source_text") or "").split()
                ) or None,
                created_by_user_id=current_user.id,
            )
            if rule.base_kind not in ALLOWANCE_BASE_KINDS:
                raise TariffCalculationError(
                    "Выберите допустимую базу доплаты."
                )
            if rule.valid_to < rule.valid_from:
                raise TariffCalculationError(
                    "Дата окончания доплаты раньше начала."
                )
            db.session.add(rule)
            parameter_set.revision += 1
            parameter_set.updated_by_user_id = current_user.id
            db.session.commit()
        except (TariffCalculationError, IntegrityError) as exc:
            db.session.rollback()
            flash(
                str(exc)
                if isinstance(exc, TariffCalculationError)
                else "Не удалось добавить доплату.",
                "danger",
            )
        else:
            flash("Правило доплаты добавлено.", "success")
        return redirect(url_for(
            "workload.tariff_parameter_set_detail",
            parameter_set_id=parameter_set.id,
        ))
