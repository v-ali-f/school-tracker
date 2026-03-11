from typing import Optional
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func

from . import db
from .models import AcademicYear, Child, ChildEnrollment, ChildSocial, Incident, IncidentChild, SchoolClass, SupportCase

management_bp = Blueprint('management', __name__)


def _current_year():
    return AcademicYear.query.filter_by(is_current=True).first()


def _active_enrollments_query(year_id: int):
    return (
        db.session.query(ChildEnrollment)
        .filter(
            ChildEnrollment.academic_year_id == year_id,
            ChildEnrollment.ended_at.is_(None),
        )
    )


def _risk_color(score: int) -> str:
    if score >= 5:
        return 'danger'
    if score >= 2:
        return 'warning'
    return 'success'


def _risk_label(score: int) -> str:
    if score >= 5:
        return 'Проблема'
    if score >= 2:
        return 'Риск'
    return 'Норма'


def build_management_data(year_id: Optional[int] = None):
    current_year = AcademicYear.query.get(year_id) if year_id else _current_year()
    years = AcademicYear.query.order_by(AcademicYear.name.desc()).all()

    empty = {
        'years': years,
        'current_year': current_year,
        'summary': {
            'students': 0,
            'classes': 0,
            'boys': 0,
            'girls': 0,
            'ovz': 0,
            'vshu': 0,
            'low_results': 0,
            'support_open': 0,
            'incidents_today': 0,
            'incidents_month': 0,
            'free_places': 0,
        },
        'parallel_stats': [],
        'risk_indicators': [],
        'report_rows': [],
    }
    if not current_year:
        return empty

    enrollments = _active_enrollments_query(current_year.id).all()
    child_ids = [e.child_id for e in enrollments]
    class_ids = [e.school_class_id for e in enrollments if e.school_class_id]
    classes = {c.id: c for c in SchoolClass.query.filter(SchoolClass.id.in_(class_ids)).all()} if class_ids else {}
    children = {c.id: c for c in Child.query.filter(Child.id.in_(child_ids)).all()} if child_ids else {}
    social_map = {s.child_id: s for s in ChildSocial.query.filter(ChildSocial.child_id.in_(child_ids)).all()} if child_ids else {}

    today = date.today()
    month_start = today.replace(day=1)
    today_start = datetime.combine(today, time.min)
    tomorrow_start = today_start + timedelta(days=1)
    month_start_dt = datetime.combine(month_start, time.min)

    incidents_today = (
        Incident.query.filter(Incident.occurred_at >= today_start, Incident.occurred_at < tomorrow_start).count()
    )
    incidents_month = (
        Incident.query.filter(Incident.occurred_at >= month_start_dt, Incident.occurred_at < tomorrow_start).count()
    )
    support_open = (
        SupportCase.query.filter(
            SupportCase.academic_year_id == current_year.id,
            SupportCase.status.in_(['OPEN', 'ACTIVE', 'WATCH']),
        ).count()
    )

    boys = girls = ovz = vshu = low_results = 0
    parallel = defaultdict(lambda: {
        'parallel': '—',
        'classes': 0,
        'students': 0,
        'boys': 0,
        'girls': 0,
        'ovz': 0,
        'vshu': 0,
        'low_results': 0,
        'free_places': 0,
        'capacity': 0,
        'incident_month': 0,
        'support_open': 0,
        'risk_score': 0,
    })

    for class_obj in classes.values():
        key = class_obj.grade or 0
        row = parallel[key]
        row['parallel'] = class_obj.grade or '—'
        row['classes'] += 1
        row['capacity'] += int(class_obj.max_students or 0)

    for enrollment in enrollments:
        child = children.get(enrollment.child_id)
        class_obj = classes.get(enrollment.school_class_id)
        if not child or not class_obj:
            continue
        key = class_obj.grade or 0
        row = parallel[key]
        row['students'] += 1
        gender = (child.gender or '').strip().lower()
        if gender.startswith('м'):
            boys += 1
            row['boys'] += 1
        elif gender.startswith('ж'):
            girls += 1
            row['girls'] += 1
        social = social_map.get(child.id)
        is_ovz = bool(child.is_ovz)
        is_vshu = bool(child.is_vshu or (social and social.vshu_since and not social.vshu_removed_at))
        is_low = bool(child.is_low)
        if is_ovz:
            ovz += 1
            row['ovz'] += 1
        if is_vshu:
            vshu += 1
            row['vshu'] += 1
        if is_low:
            low_results += 1
            row['low_results'] += 1

    support_counts = defaultdict(int)
    support_rows = (
        db.session.query(SupportCase.child_id, func.count(SupportCase.id))
        .filter(
            SupportCase.academic_year_id == current_year.id,
            SupportCase.status.in_(['OPEN', 'ACTIVE', 'WATCH']),
        )
        .group_by(SupportCase.child_id)
        .all()
    )
    for child_id, cnt in support_rows:
        support_counts[child_id] = cnt
    for enrollment in enrollments:
        class_obj = classes.get(enrollment.school_class_id)
        if class_obj:
            parallel[class_obj.grade or 0]['support_open'] += support_counts.get(enrollment.child_id, 0)

    incident_rows = (
        db.session.query(IncidentChild.child_id, func.count(IncidentChild.id))
        .join(Incident, Incident.id == IncidentChild.incident_id)
        .filter(Incident.occurred_at >= month_start_dt, Incident.occurred_at < tomorrow_start)
        .group_by(IncidentChild.child_id)
        .all()
    )
    incident_counts = defaultdict(int)
    for child_id, cnt in incident_rows:
        incident_counts[child_id] = cnt
    for enrollment in enrollments:
        class_obj = classes.get(enrollment.school_class_id)
        if class_obj:
            parallel[class_obj.grade or 0]['incident_month'] += incident_counts.get(enrollment.child_id, 0)

    risk_indicators = []
    report_rows = []
    for key in sorted(parallel.keys(), key=lambda x: (x == '—', x)):
        row = parallel[key]
        row['free_places'] = max(row['capacity'] - row['students'], 0)
        risk_score = 0
        if row['students'] and (row['vshu'] / row['students']) >= 0.08:
            risk_score += 2
        if row['students'] and (row['low_results'] / row['students']) >= 0.15:
            risk_score += 2
        if row['incident_month'] >= 3:
            risk_score += 2
        if row['capacity'] and row['students'] >= row['capacity']:
            risk_score += 1
        if row['support_open'] >= 5:
            risk_score += 1
        row['risk_score'] = risk_score
        row['risk_color'] = _risk_color(risk_score)
        row['risk_label'] = _risk_label(risk_score)
        risk_indicators.append({
            'name': f"{row['parallel']} параллель",
            'value': row['risk_label'],
            'color': row['risk_color'],
            'details': f"ВШУ: {row['vshu']}, низкие результаты: {row['low_results']}, инциденты за месяц: {row['incident_month']}"
        })
        report_rows.append(row)

    classes_count = len(classes)
    summary = {
        'students': len(child_ids),
        'classes': classes_count,
        'boys': boys,
        'girls': girls,
        'ovz': ovz,
        'vshu': vshu,
        'low_results': low_results,
        'support_open': support_open,
        'incidents_today': incidents_today,
        'incidents_month': incidents_month,
        'free_places': sum(max((int(c.max_students or 0) - sum(1 for e in enrollments if e.school_class_id == c.id)), 0) for c in classes.values()),
    }

    return {
        'years': years,
        'current_year': current_year,
        'summary': summary,
        'parallel_stats': report_rows,
        'risk_indicators': risk_indicators,
        'report_rows': report_rows,
    }


@management_bp.route('/management/dashboard')
@login_required
def dashboard():
    year_id = request.args.get('year_id', type=int)
    data = build_management_data(year_id)
    return render_template('management_dashboard.html', **data, selected_year_id=(data['current_year'].id if data['current_year'] else None))


@management_bp.route('/management/contingent-report')
@login_required
def contingent_report():
    year_id = request.args.get('year_id', type=int)
    data = build_management_data(year_id)
    return render_template('management_contingent_report.html', **data, selected_year_id=(data['current_year'].id if data['current_year'] else None))
