from datetime import date, datetime, time

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func, or_

from . import db
from .models import AcademicYear, Child, ChildEnrollment, ChildSocial, Incident, Department, TeacherLoad, ControlWork, ControlWorkResult, ChildTransferHistory, SchoolClass, User, Document, OlympiadResult

main_bp = Blueprint("main", __name__)


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

    active_child_ids_q = (
        db.session.query(ChildEnrollment.child_id)
        .filter(
            ChildEnrollment.academic_year_id == current_year.id,
            ChildEnrollment.ended_at.is_(None),
        )
        .distinct()
        .subquery()
    )

    stats["contingent"] = db.session.query(func.count()).select_from(active_child_ids_q).scalar() or 0

    stats["ovz"] = (
        db.session.query(func.count(Child.id))
        .filter(Child.id.in_(active_child_ids_q), Child.is_ovz.is_(True))
        .scalar()
        or 0
    )

    stats["low"] = (
        db.session.query(func.count(Child.id))
        .filter(Child.id.in_(active_child_ids_q), Child.is_low.is_(True))
        .scalar()
        or 0
    )

    stats["vshu"] = (
        db.session.query(func.count(Child.id))
        .outerjoin(ChildSocial, ChildSocial.child_id == Child.id)
        .filter(
            Child.id.in_(active_child_ids_q),
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
        .filter(Child.id.in_(active_child_ids_q), ChildSocial.kdn_since.isnot(None))
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
    load_q = TeacherLoad.query.filter(TeacherLoad.is_archived.is_(False))
    if current_year:
        load_q = load_q.filter(
            or_(
                TeacherLoad.academic_year_id == current_year.id,
                TeacherLoad.academic_year_id.is_(None),
            )
        )
    loads = load_q.all()
    departments_count = Department.query.count()
    teacher_ids = {x.teacher_id for x in loads if x.teacher_id}
    total_hours = sum(float(x.hours or 0) for x in loads)
    return {
        "departments_count": departments_count,
        "teachers_count": len(teacher_ids),
        "total_hours": round(total_hours, 1),
    }


def _control_works_dashboard_stats():
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    works_q = ControlWork.query
    results_q = ControlWorkResult.query.filter(ControlWorkResult.percent.isnot(None))
    if current_year:
        works_q = works_q.filter(ControlWork.academic_year_id == current_year.id)
        results_q = results_q.filter(ControlWorkResult.academic_year_id == current_year.id)
    works_count = works_q.count()
    results = [float(x.percent) for x in results_q.all()]
    avg_percent = round(sum(results) / len(results), 1) if results else None
    return {
        "works_count": works_count,
        "results_count": len(results),
        "avg_percent": avg_percent,
    }



def _olympiad_dashboard_stats():
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    q = OlympiadResult.query.filter(OlympiadResult.is_archived.is_(False))
    if current_year:
        q = q.filter(OlympiadResult.academic_year_id == current_year.id)
    rows = q.all()
    winners = sum(1 for r in rows if (r.status or '').strip().lower() in {'победитель', 'winner'})
    priz = sum(1 for r in rows if 'приз' in (r.status or '').strip().lower())
    by_stage = {}
    for r in rows:
        key = r.stage or '—'
        by_stage[key] = by_stage.get(key, 0) + 1
    return {
        'total': len(rows),
        'unique_children': len({r.child_id for r in rows if r.child_id}),
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

@main_bp.route("/")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        dashboard_stats=_dashboard_stats(),
        departments_dashboard_stats=_departments_dashboard_stats(),
        control_works_dashboard_stats=_control_works_dashboard_stats(),
        study_year_dashboard_stats=_study_year_dashboard_stats(),
        olympiad_dashboard_stats=_olympiad_dashboard_stats(),
    )
