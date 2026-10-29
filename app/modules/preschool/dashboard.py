"""Staff composition and explainable preschool indicators."""

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.core.extensions import db
from app.models_legacy import AcademicYear, Building

from .access import managed_building_ids, role_codes
from .dashboard_service import metric_rows, staff_snapshot
from .models import PreschoolDashboardSetting


POSITION_LABELS = {
    "SENIOR_EDUCATOR": "Старший воспитатель",
    "EDUCATOR": "Воспитатель",
    "ASSISTANT_EDUCATOR": "Помощник воспитателя",
    "PSYCHOLOGIST": "Педагог-психолог",
    "LOGOPEDIST": "Учитель-логопед",
    "DEFECTOLOGIST": "Учитель-дефектолог",
    "SOCIAL_PEDAGOG": "Социальный педагог",
    "TUTOR": "Тьютор",
    "SPECIALIST": "Другой специалист",
}

METRIC_LABELS = {
    "staff_total": "Всего сотрудников",
    "mcko_total": "Всего воспитателей",
    "mcko_valid": "С действующим МЦКО",
    "mcko_missing": "Без результата МЦКО",
    "mcko_expiring": "МЦКО скоро истекает",
    "mcko_expired": "МЦКО истёк",
    "attest_first": "Первая категория",
    "attest_highest": "Высшая категория",
    "attest_position": "Соответствие должности",
    "attest_missing": "Без аттестации",
    "attest_due": "Предложить аттестацию на соответствие",
    "attest_upcoming": "Скоро можно предложить аттестацию",
    "attest_no_hire_date": "Не указана дата приёма",
    "attest_expiring": "Аттестация скоро истекает",
    "attest_expired": "Аттестация истекла",
    "course_with": "С курсом за период",
    "course_without": "Без курса за период",
    "course_hours": "Суммарные часы курсов",
}


def _require_dashboard_access():
    if not role_codes() & {"ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR", "SENIOR_EDUCATOR"}:
        abort(403)


def _allowed_buildings():
    if role_codes() & {"ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR"}:
        return Building.query.order_by(Building.name).all()
    return Building.query.filter(Building.id.in_(managed_building_ids() or {-1})).order_by(Building.name).all()


def _filters():
    _require_dashboard_access()
    buildings = _allowed_buildings()
    allowed_ids = {item.id for item in buildings}
    building_id = request.args.get("building_id", type=int)
    if building_id is not None and building_id not in allowed_ids:
        abort(403)
    year_id = request.args.get("academic_year_id", type=int)
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    year = db.session.get(AcademicYear, year_id) if year_id else next((item for item in years if item.is_current), years[0] if years else None)
    if year_id and year is None:
        abort(400)
    position = (request.args.get("position") or "").strip().upper()
    if position and position not in POSITION_LABELS:
        abort(400)
    raw_as_of = (request.args.get("as_of") or "").strip()
    try:
        as_of = date.fromisoformat(raw_as_of) if raw_as_of else date.today()
    except ValueError:
        abort(400)
    setting = db.session.get(PreschoolDashboardSetting, 1)
    warning_months = setting.warning_months if setting else 6
    rows = staff_snapshot(
        as_of=as_of, year=year, allowed_building_ids=allowed_ids,
        building_id=building_id, position=position or None, warning_months=warning_months,
    )
    return {
        "rows": rows, "buildings": buildings, "years": years, "year": year,
        "building_id": building_id, "position": position, "as_of": as_of,
        "warning_months": warning_months, "position_labels": POSITION_LABELS,
        "metric_labels": METRIC_LABELS,
    }


def register_routes(bp):
    @bp.get("/staff/composition")
    def composition():
        context = _filters()
        status = (request.args.get("status") or "staff_total").strip()
        metrics = metric_rows(context["rows"])
        if status not in metrics:
            abort(400)
        rows = metrics[status]
        search = " ".join((request.args.get("q") or "").casefold().split())
        if search:
            rows = [row for row in rows if search in f"{row.user.fio} {row.user.username} {' '.join(row.building_names)} {' '.join(row.group_names)}".casefold()]
        page = max(request.args.get("page", type=int) or 1, 1)
        page_size = 30
        page_count = max((len(rows) + page_size - 1) // page_size, 1)
        if page > page_count:
            page = page_count
        context.update({
            "items": rows[(page - 1) * page_size:page * page_size],
            "total": len(rows), "page": page, "page_count": page_count,
            "status": status, "search": search,
        })
        return render_template("preschool/composition.html", **context)

    @bp.get("/dashboard")
    def dashboard():
        context = _filters()
        metrics = metric_rows(context["rows"])
        values = {key: len(items) for key, items in metrics.items()}
        values["course_hours"] = round(sum(row.course_hours for row in context["rows"]), 1)
        context.update({"values": values, "can_change_settings": bool(role_codes() & {"ADMIN", "DIRECTOR"})})
        return render_template("preschool/dashboard.html", **context)

    @bp.post("/dashboard/settings")
    def dashboard_settings():
        _require_dashboard_access()
        if not role_codes() & {"ADMIN", "DIRECTOR"}:
            abort(403)
        months = request.form.get("warning_months", type=int)
        if months is None or not 1 <= months <= 24:
            abort(400)
        row = db.session.get(PreschoolDashboardSetting, 1)
        if row is None:
            row = PreschoolDashboardSetting(id=1)
            db.session.add(row)
        row.warning_months = months
        row.updated_by_user_id = current_user.id
        db.session.commit()
        flash("Порог срока обновлён.", "success")
        return redirect(url_for("preschool.dashboard"))
