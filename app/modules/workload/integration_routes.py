from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.core.extensions import db
from app.models import (
    AcademicYear,
    TariffVersion,
    WorkloadReconciliationRun,
    WORKLOAD_SOURCE_MODE_LABELS,
)
from app.services.workload_integration_service import (
    WorkloadIntegrationError,
    active_organization_id,
    reconcile_workload_sources,
    source_state,
    switch_workload_source,
)

from .access import can_use_workload_permission, require_workload_write


RECONCILIATION_STATUS_LABELS = {
    "RUNNING": "Выполняется",
    "PASSED": "Расхождений нет",
    "FAILED": "Есть расхождения",
    "TECHNICAL_ERROR": "Техническая ошибка",
}

RECONCILIATION_ITEM_STATUS_LABELS = {
    "MATCH": "Совпадает",
    "HOURS_MISMATCH": "Разные часы",
    "LEGACY_ONLY": "Только Excel",
    "INTERNAL_ONLY": "Только новый модуль",
    "UNMAPPED_ACTIVITY": "Предмет не сопоставлен",
}


def _require_integration_manage():
    require_workload_write()
    _require_integration_read()


def _require_integration_read():
    if not can_use_workload_permission(
        "workload.settings.manage",
        current_user,
    ):
        abort(403)


def _effective_versions_query(academic_year_id):
    organization_id = active_organization_id()
    query = (
        TariffVersion.query
        .join(TariffVersion.tariff_cycle)
        .filter(
            TariffVersion.status == "EFFECTIVE",
            TariffVersion.tariff_cycle.has(
                academic_year_id=academic_year_id,
            ),
        )
    )
    if organization_id is None:
        query = query.filter(
            TariffVersion.tariff_cycle.has(organization_id=None)
        )
    else:
        query = query.filter(
            TariffVersion.tariff_cycle.has(
                organization_id=organization_id,
            )
        )
    return query.order_by(
        TariffVersion.effective_from.desc(),
        TariffVersion.version_no.desc(),
    )


def register_integration_routes(workload_bp):
    @workload_bp.get("/integration/")
    @login_required
    def integration():
        _require_integration_read()
        years = AcademicYear.query.order_by(
            AcademicYear.start_date.desc().nullslast(),
            AcademicYear.name.desc(),
        ).all()
        current_year = AcademicYear.query.filter_by(is_current=True).first()
        academic_year_id = request.args.get(
            "academic_year_id",
            type=int,
        ) or (current_year.id if current_year else None)
        academic_year = (
            db.session.get(AcademicYear, academic_year_id)
            if academic_year_id
            else None
        )
        versions = (
            _effective_versions_query(academic_year.id).all()
            if academic_year
            else []
        )
        state = (
            source_state(academic_year.id)
            if academic_year
            else None
        )
        runs = []
        selected_run = None
        if academic_year:
            runs = (
                WorkloadReconciliationRun.query
                .filter_by(academic_year_id=academic_year.id)
                .order_by(
                    WorkloadReconciliationRun.created_at.desc(),
                    WorkloadReconciliationRun.id.desc(),
                )
                .all()
            )
            run_id = request.args.get("run_id", type=int)
            selected_run = (
                next((run for run in runs if run.id == run_id), None)
                if run_id
                else (runs[0] if runs else None)
            )
        return render_template(
            "workload/integration.html",
            years=years,
            academic_year=academic_year,
            selected_version=state.tariff_version if state else None,
            versions=versions,
            state=state,
            runs=runs,
            selected_run=selected_run,
            mode_labels=WORKLOAD_SOURCE_MODE_LABELS,
            run_status_labels=RECONCILIATION_STATUS_LABELS,
            item_status_labels=RECONCILIATION_ITEM_STATUS_LABELS,
        )

    @workload_bp.post("/integration/reconcile")
    @login_required
    def integration_reconcile():
        _require_integration_manage()
        version = db.session.get(
            TariffVersion,
            request.form.get("tariff_version_id", type=int),
        )
        if version is None:
            abort(404)
        try:
            run = reconcile_workload_sources(
                version,
                user_id=current_user.id,
            )
            db.session.commit()
        except WorkloadIntegrationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return redirect(url_for(
                "workload.integration",
                academic_year_id=version.tariff_cycle.academic_year_id,
            ))
        flash(
            "Сверка выполнена: расхождений нет."
            if run.status == "PASSED"
            else (
                "Сверка выполнена. Найдены блокирующие расхождения: "
                f"{run.blocking_count}."
            ),
            "success" if run.status == "PASSED" else "warning",
        )
        return redirect(url_for(
            "workload.integration",
            academic_year_id=version.tariff_cycle.academic_year_id,
            run_id=run.id,
        ))

    @workload_bp.post("/integration/source")
    @login_required
    def integration_source():
        _require_integration_manage()
        academic_year = db.session.get(
            AcademicYear,
            request.form.get("academic_year_id", type=int),
        )
        if academic_year is None:
            abort(404)
        version_id = request.form.get("tariff_version_id", type=int)
        version = (
            db.session.get(TariffVersion, version_id)
            if version_id
            else None
        )
        try:
            setting = switch_workload_source(
                academic_year,
                mode=request.form.get("source_mode"),
                tariff_version=version,
                user_id=current_user.id,
                reason=request.form.get("reason"),
            )
            db.session.commit()
        except WorkloadIntegrationError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash(
                "Источник нагрузки переключён: "
                f"{WORKLOAD_SOURCE_MODE_LABELS[setting.source_mode]}.",
                "success",
            )
        return redirect(url_for(
            "workload.integration",
            academic_year_id=academic_year.id,
        ))


__all__ = ["register_integration_routes"]
