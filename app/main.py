from datetime import date, datetime, time

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func, or_

from app.core.extensions import db
from .models import AcademicYear, Child, ChildEnrollment, ChildSocial, Incident, Department, TeacherLoad, ControlWork, ControlWorkResult, ChildTransferHistory, SchoolClass, User, Document, OlympiadResult, DiagnosticImportBatch, DiagnosticResult, DiagnosticSession, DiagnosticTeacherBinding

main_bp = Blueprint("main", __name__)


# Legacy-алиасы: битые закладки пользователей ведут сюда 404-ом.
# Перенаправляем на канонические адреса без сломанного UX.
@main_bp.route("/users")
@login_required
def legacy_users_redirect():
    return redirect(url_for("users.users_list"))


@main_bp.route("/analytics/dashboard")
@login_required
def legacy_analytics_dashboard_redirect():
    return redirect(url_for("children.incidents_dashboard_legacy"))


@main_bp.route("/settings/organization")
@login_required
def legacy_settings_organization_redirect():
    return redirect(url_for("main.dashboard"))


def _dashboard_stats():
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    today = date.today()
    today_start = datetime.combine(today, time.min)
    tomorrow_start = datetime.combine(today, time.max)

    stats = {
        "current_year_name": current_year.name if current_year else None,
        "contingent": 0,
        "ovz": 0,
        "vshu": 0,
        "kdn": 0,
        "low": 0,
        "incidents": 0,
        "incidents_today": 0,
        "injuries_today": 0,
        "discipline_today": 0,
        "control_works_today": 0,
        "users_archived": 0,
        "documents_archived": 0,
    }

    if not current_year:
        return stats

    active_child_ids_base = (
        db.session.query(ChildEnrollment.child_id)
        .filter(
            ChildEnrollment.academic_year_id == current_year.id,
            ChildEnrollment.ended_at.is_(None),
        )
        .distinct()
    )
    active_child_ids_subq = active_child_ids_base.subquery()
    active_child_ids_scalar = active_child_ids_base.scalar_subquery()

    stats["contingent"] = db.session.query(func.count()).select_from(active_child_ids_subq).scalar() or 0

    stats["ovz"] = (
        db.session.query(func.count(Child.id))
        .filter(Child.id.in_(active_child_ids_scalar), Child.is_ovz.is_(True))
        .scalar()
        or 0
    )

    stats["low"] = (
        db.session.query(func.count(Child.id))
        .filter(Child.id.in_(active_child_ids_scalar), Child.is_low.is_(True))
        .scalar()
        or 0
    )

    stats["vshu"] = (
        db.session.query(func.count(Child.id))
        .outerjoin(ChildSocial, ChildSocial.child_id == Child.id)
        .filter(
            Child.id.in_(active_child_ids_scalar),
            db.or_(Child.is_vshu.is_(True), ChildSocial.vshu_since.isnot(None)),
            db.or_(ChildSocial.vshu_removed_at.is_(None), Child.is_vshu.is_(True)),
        )
        .distinct()
        .scalar()
        or 0
    )

    stats["kdn"] = (
        db.session.query(func.count(Child.id))
        .join(ChildSocial, ChildSocial.child_id == Child.id)
        .filter(Child.id.in_(active_child_ids_scalar), ChildSocial.kdn_since.isnot(None))
        .distinct()
        .scalar()
        or 0
    )

    stats["incidents"] = Incident.query.count()
    today_incidents_q = Incident.query.filter(
        Incident.occurred_at >= today_start,
        Incident.occurred_at <= tomorrow_start,
    )
    stats["incidents_today"] = today_incidents_q.count()
    stats["injuries_today"] = today_incidents_q.filter(Incident.category == "Травма/вызов скорой").count()
    stats["discipline_today"] = today_incidents_q.filter(Incident.category == "Нарушение дисциплины").count()

    control_today_q = ControlWork.query.filter(ControlWork.work_date == today)
    if current_year:
        control_today_q = control_today_q.filter(ControlWork.academic_year_id == current_year.id)
    stats["control_works_today"] = control_today_q.count()

    stats["users_archived"] = User.query.filter(User.employment_status.in_(["DISMISSED", "ARCHIVED"])).count()
    stats["documents_archived"] = Document.query.filter(db.or_(Document.is_deleted_soft.is_(True), Document.is_hidden_by_retention.is_(True), Document.is_archived.is_(True))).count()
    return stats


def _departments_dashboard_stats():
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    load_filter = [TeacherLoad.is_archived.is_(False)]
    if current_year:
        load_filter.append(
            or_(
                TeacherLoad.academic_year_id == current_year.id,
                TeacherLoad.academic_year_id.is_(None),
            )
        )
    agg = db.session.query(
        func.count(func.distinct(TeacherLoad.teacher_id)),
        func.coalesce(func.sum(TeacherLoad.hours), 0),
    ).filter(*load_filter).one()
    teachers_count, total_hours = agg
    return {
        "departments_count": Department.query.count(),
        "teachers_count": teachers_count or 0,
        "total_hours": round(float(total_hours), 1),
    }


def _control_works_dashboard_stats():
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    works_q = ControlWork.query
    results_q = ControlWorkResult.query.filter(ControlWorkResult.percent.isnot(None))
    if current_year:
        works_q = works_q.filter(ControlWork.academic_year_id == current_year.id)
        results_q = results_q.filter(ControlWorkResult.academic_year_id == current_year.id)
    works_count = works_q.count()
    agg = db.session.query(
        func.count(ControlWorkResult.id),
        func.avg(ControlWorkResult.percent),
    ).filter(ControlWorkResult.percent.isnot(None))
    if current_year:
        agg = agg.filter(ControlWorkResult.academic_year_id == current_year.id)
    results_count, avg_val = agg.one()
    return {
        "works_count": works_count,
        "results_count": results_count or 0,
        "avg_percent": round(float(avg_val), 1) if avg_val else None,
    }



def _olympiad_dashboard_stats():
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    base_filter = [OlympiadResult.is_archived.is_(False)]
    if current_year:
        base_filter.append(OlympiadResult.academic_year_id == current_year.id)

    # Total + unique children in one query
    agg = db.session.query(
        func.count(OlympiadResult.id),
        func.count(func.distinct(OlympiadResult.child_id)),
    ).filter(*base_filter).one()
    total, unique_children = agg

    # Status counts via GROUP BY
    status_rows = (
        db.session.query(
            func.lower(func.trim(func.coalesce(OlympiadResult.status, ''))),
            func.count(OlympiadResult.id),
        )
        .filter(*base_filter)
        .group_by(func.lower(func.trim(func.coalesce(OlympiadResult.status, ''))))
        .all()
    )
    winners = 0
    priz = 0
    for status_lower, cnt in status_rows:
        if status_lower in ('победитель', 'winner'):
            winners += cnt
        if status_lower and 'приз' in status_lower:
            priz += cnt

    # By stage via GROUP BY
    stage_rows = (
        db.session.query(
            func.coalesce(OlympiadResult.stage, '—'),
            func.count(OlympiadResult.id),
        )
        .filter(*base_filter)
        .group_by(func.coalesce(OlympiadResult.stage, '—'))
        .all()
    )
    by_stage = {stage: cnt for stage, cnt in stage_rows}

    return {
        'total': total or 0,
        'unique_children': unique_children or 0,
        'winners': winners,
        'prizers': priz,
        'by_stage': by_stage,
    }


def _study_year_dashboard_stats():
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    if not current_year:
        return {
            "current_year_name": None,
            "classes_count": 0,
            "active_count": 0,
            "transfers_count": 0,
            "archive_count": 0,
        }

    active_q = ChildEnrollment.query.filter(
        ChildEnrollment.academic_year_id == current_year.id,
        ChildEnrollment.ended_at.is_(None),
    )
    return {
        "current_year_name": current_year.name,
        "classes_count": SchoolClass.query.filter_by(academic_year_id=current_year.id).count(),
        "active_count": active_q.count(),
        "transfers_count": ChildTransferHistory.query.filter(ChildTransferHistory.from_academic_year_id == current_year.id).count(),
        "archive_count": ChildTransferHistory.query.filter(
            ChildTransferHistory.from_academic_year_id == current_year.id,
            ChildTransferHistory.transfer_type.in_(["ARCHIVED", "EXPELLED", "TRANSFERRED_OUT"]),
        ).count(),
    }



def _diagnostics_dashboard_stats():
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    sessions_q = DiagnosticSession.query
    if current_year:
        sessions_q = sessions_q.filter(or_(DiagnosticSession.academic_year_id == current_year.id, DiagnosticSession.academic_year_id.is_(None)))
    sessions_count = sessions_q.count()
    session_ids_sq = sessions_q.with_entities(DiagnosticSession.id).subquery()
    imports_q = DiagnosticImportBatch.query.filter(DiagnosticImportBatch.session_id.in_(db.session.query(session_ids_sq)))
    results_q = DiagnosticResult.query.filter(DiagnosticResult.session_id.in_(db.session.query(session_ids_sq)))
    below_base = results_q.filter(func.lower(func.coalesce(DiagnosticResult.level, '')) == 'низкий').count()
    departments_ready = db.session.query(func.count(Department.id)).scalar() or 0
    bound_count = (
        db.session.query(func.count(DiagnosticTeacherBinding.result_id))
        .join(DiagnosticResult, DiagnosticResult.id == DiagnosticTeacherBinding.result_id)
        .filter(DiagnosticResult.session_id.in_(db.session.query(session_ids_sq)))
        .scalar() or 0
    )
    return {
        'sessions_count': sessions_count,
        'imports_count': imports_q.count(),
        'awaiting_review': imports_q.filter(DiagnosticImportBatch.status.in_(['draft', 'requires_review'])).count(),
        'unmatched_count': max(results_q.count() - bound_count, 0),
        'below_base_count': below_base,
        'departments_ready': departments_ready,
    }

@main_bp.route("/")
@login_required
def dashboard():
    from app.services.attendance_stats_service import build_attendance_dashboard_stats
    if getattr(current_user, "role", None) == "KPP":
        return render_template(
            "attendance_kpp.html",
            stats=build_attendance_dashboard_stats(current_user),
        )
    from app.modules.hub.routes import build_home_context
    return render_template(
        "dashboard.html",
        dashboard_stats=_dashboard_stats(),
        departments_dashboard_stats=_departments_dashboard_stats(),
        control_works_dashboard_stats=_control_works_dashboard_stats(),
        study_year_dashboard_stats=_study_year_dashboard_stats(),
        olympiad_dashboard_stats=_olympiad_dashboard_stats(),
        attendance_dashboard_stats=build_attendance_dashboard_stats(current_user),
        diagnostics_dashboard_stats=_diagnostics_dashboard_stats(),
        **build_home_context(),
    )
