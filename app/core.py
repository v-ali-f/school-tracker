from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user

from app.core.extensions import db
from .models import AcademicYear, Child, ChildMovement, SchoolClass, SupportCase, SystemLog
from .roles import require_roles
from .services.logging_service import log_action

core_bp = Blueprint('core', __name__)


def _current_year():
    return AcademicYear.query.filter_by(is_current=True).first()


@core_bp.route('/movements')
@require_roles('ADMIN')
def movements_registry():
    year_id = request.args.get('academic_year_id', type=int)
    movement_type = (request.args.get('movement_type') or '').strip().lower()
    q = (request.args.get('q') or '').strip()

    rows = ChildMovement.query
    if year_id:
        rows = rows.filter(ChildMovement.academic_year_id == year_id)
    if movement_type:
        rows = rows.filter(ChildMovement.movement_type == movement_type)
    if q:
        like = f"%{q}%"
        rows = rows.join(Child, Child.id == ChildMovement.child_id).filter(
            db.or_(
                Child.last_name.ilike(like),
                Child.first_name.ilike(like),
                Child.middle_name.ilike(like),
                ChildMovement.reason.ilike(like),
                ChildMovement.order_number.ilike(like),
            )
        )
    rows = rows.order_by(ChildMovement.movement_date.desc(), ChildMovement.created_at.desc()).limit(300).all()
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    return render_template('movements_registry.html', rows=rows, years=years, year_id=year_id, movement_type=movement_type, q=q)


@core_bp.route('/support', methods=['GET', 'POST'])
@require_roles('ADMIN', 'CLASS_TEACHER', 'PSYCHOLOGIST', 'SOCIAL_PEDAGOG')
def support_registry():
    current_year = _current_year()
    year_id = request.values.get('academic_year_id', type=int) or (current_year.id if current_year else None)
    status = (request.values.get('status') or '').strip().upper()
    support_type = (request.values.get('support_type') or '').strip().lower()

    if request.method == 'POST':
        child_id = request.form.get('child_id', type=int)
        case = SupportCase(
            child_id=child_id,
            academic_year_id=year_id,
            support_type=(request.form.get('support_type') or 'administration').strip().lower(),
            status=(request.form.get('status') or 'OPEN').strip().upper(),
            description=(request.form.get('description') or '').strip() or None,
            created_by=getattr(current_user, 'id', None),
        )
        db.session.add(case)
        db.session.commit()
        log_action('SUPPORT_CASE_CREATED', 'support_case', case.id, getattr(current_user, 'id', None), case.description)
        flash('Случай сопровождения добавлен', 'success')
        return redirect(url_for('core.support_registry', academic_year_id=year_id))

    rows = SupportCase.query
    if year_id:
        rows = rows.filter(SupportCase.academic_year_id == year_id)
    if status:
        rows = rows.filter(SupportCase.status == status)
    if support_type:
        rows = rows.filter(SupportCase.support_type == support_type)
    rows = rows.join(Child, Child.id == SupportCase.child_id).order_by(SupportCase.created_at.desc()).limit(300).all()

    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    children = Child.query.order_by(Child.last_name.asc(), Child.first_name.asc()).limit(500).all()
    return render_template('support_registry_v44.html', rows=rows, years=years, children=children, year_id=year_id, status=status, support_type=support_type)


@core_bp.route('/support/<int:case_id>/status', methods=['POST'])
@require_roles('ADMIN', 'PSYCHOLOGIST', 'SOCIAL_PEDAGOG')
def support_status(case_id: int):
    case = SupportCase.query.get_or_404(case_id)
    case.status = (request.form.get('status') or case.status or 'OPEN').strip().upper()
    case.updated_at = datetime.utcnow()
    db.session.commit()
    log_action('SUPPORT_CASE_STATUS_CHANGED', 'support_case', case.id, getattr(current_user, 'id', None), case.status)
    flash('Статус сопровождения обновлён', 'success')
    return redirect(url_for('core.support_registry', academic_year_id=case.academic_year_id))


@core_bp.route('/system-logs')
@require_roles('ADMIN')
def system_logs_registry():
    action = (request.args.get('action') or '').strip()
    object_type = (request.args.get('object_type') or '').strip()
    rows = SystemLog.query
    if action:
        rows = rows.filter(SystemLog.action == action)
    if object_type:
        rows = rows.filter(SystemLog.object_type == object_type)
    rows = rows.order_by(SystemLog.created_at.desc()).limit(300).all()
    actions = [r[0] for r in db.session.query(SystemLog.action).distinct().order_by(SystemLog.action.asc()).all() if r[0]]
    object_types = [r[0] for r in db.session.query(SystemLog.object_type).distinct().order_by(SystemLog.object_type.asc()).all() if r[0]]
    return render_template('system_logs.html', rows=rows, action=action, object_type=object_type, actions=actions, object_types=object_types)
