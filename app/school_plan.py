import os
from datetime import date, datetime, timedelta
from io import BytesIO
import calendar as pycalendar

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, send_file
from flask_login import current_user, login_required
from sqlalchemy import and_, or_

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from app.core.extensions import db
from app.models import (
    AcademicYear,
    Building,
    SchoolClass,
    SchoolPlanCategory,
    SchoolPlanDirection,
    SchoolPlanEvent,
    User,
)

school_plan_bp = Blueprint('school_plan', __name__, url_prefix='/school-plan')


STATUS_TITLES = {
    'planned': 'Запланировано',
    'in_progress': 'В работе',
    'done': 'Выполнено',
    'postponed': 'Перенесено',
    'cancelled': 'Отменено',
}

PRIORITY_TITLES = {
    'normal': 'Обычный',
    'important': 'Важный',
    'critical': 'Очень важный',
}

VISIBILITY_TITLES = {
    'school': 'Вся школа',
    'building': 'Здание',
    'class': 'Класс',
}

WEEKDAY_TITLES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
MONTH_TITLES = [
    '', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
]


PDF_FONT_NAME = None
PDF_FONT_BOLD_NAME = None


def _find_pdf_font_paths():
    regular_candidates = [
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/Library/Fonts/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/dejavu/DejaVuSans.ttf',
        'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/DejaVuSans.ttf',
    ]
    bold_candidates = [
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/Library/Fonts/Arial Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
        'C:/Windows/Fonts/arialbd.ttf',
        'C:/Windows/Fonts/DejaVuSans-Bold.ttf',
    ]

    regular_path = next((path for path in regular_candidates if os.path.exists(path)), None)
    bold_path = next((path for path in bold_candidates if os.path.exists(path)), None)
    return regular_path, bold_path



def _ensure_pdf_fonts():
    global PDF_FONT_NAME, PDF_FONT_BOLD_NAME
    if PDF_FONT_NAME and PDF_FONT_BOLD_NAME:
        return PDF_FONT_NAME, PDF_FONT_BOLD_NAME

    regular_path, bold_path = _find_pdf_font_paths()
    if regular_path:
        if 'SchoolPlanPdfFont' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('SchoolPlanPdfFont', regular_path))
        PDF_FONT_NAME = 'SchoolPlanPdfFont'
    else:
        PDF_FONT_NAME = 'Helvetica'

    if bold_path:
        if 'SchoolPlanPdfFontBold' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('SchoolPlanPdfFontBold', bold_path))
        PDF_FONT_BOLD_NAME = 'SchoolPlanPdfFontBold'
    else:
        PDF_FONT_BOLD_NAME = PDF_FONT_NAME

    return PDF_FONT_NAME, PDF_FONT_BOLD_NAME


def _is_manager():
    return getattr(current_user, 'role', None) in {'ADMIN', 'METHODIST', 'DEPUTY_DIRECTOR'}


def _user_scope():
    if _is_manager():
        return {'all_access': True, 'building_ids': set(), 'class_ids': set()}

    building_ids = {row.building_id for row in getattr(current_user, 'building_links', []) if getattr(row, 'building_id', None)}
    class_rows = SchoolClass.query.filter_by(teacher_user_id=current_user.id, is_archived=False).all()
    class_ids = {row.id for row in class_rows}
    for row in class_rows:
        if row.building_id:
            building_ids.add(row.building_id)

    return {'all_access': False, 'building_ids': building_ids, 'class_ids': class_ids}


def _visible_events_query(include_archived=False):
    query = SchoolPlanEvent.query
    if not include_archived:
        query = query.filter(SchoolPlanEvent.is_archived.is_(False))

    scope = _user_scope()
    if scope['all_access']:
        return query

    conditions = [SchoolPlanEvent.visibility_level == 'school']
    if scope['building_ids']:
        conditions.append(and_(SchoolPlanEvent.visibility_level == 'building', SchoolPlanEvent.building_id.in_(scope['building_ids'])))
    if scope['class_ids']:
        conditions.append(and_(SchoolPlanEvent.visibility_level == 'class', SchoolPlanEvent.class_id.in_(scope['class_ids'])))

    return query.filter(or_(*conditions))


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except Exception:
        return None


def _apply_filters(query):
    year_id = _args_int('year_id')
    building_id = _args_int('building_id')
    class_id = _args_int('class_id')
    direction_id = _args_int('direction_id')
    category_id = _args_int('category_id')
    visibility_level = (request.args.get('visibility_level') or '').strip()
    status = (request.args.get('status') or '').strip()
    priority = (request.args.get('priority') or '').strip()
    q = (request.args.get('q') or '').strip()

    if year_id:
        query = query.filter(SchoolPlanEvent.academic_year_id == year_id)
    if building_id:
        query = query.filter(SchoolPlanEvent.building_id == building_id)
    if class_id:
        query = query.filter(SchoolPlanEvent.class_id == class_id)
    if direction_id:
        query = query.filter(SchoolPlanEvent.direction_id == direction_id)
    if category_id:
        query = query.filter(SchoolPlanEvent.category_id == category_id)
    if visibility_level:
        query = query.filter(SchoolPlanEvent.visibility_level == visibility_level)
    if status:
        query = query.filter(SchoolPlanEvent.status == status)
    if priority:
        query = query.filter(SchoolPlanEvent.priority == priority)
    if q:
        ilike = f'%{q}%'
        query = query.filter(or_(
            SchoolPlanEvent.title.ilike(ilike),
            SchoolPlanEvent.description.ilike(ilike),
            SchoolPlanEvent.responsible_text.ilike(ilike),
            SchoolPlanEvent.participants.ilike(ilike),
        ))
    return query


def _event_query(include_archived=False):
    return _apply_filters(_visible_events_query(include_archived=include_archived))


def _period_overlap(query, start_date, end_date):
    return query.filter(
        SchoolPlanEvent.start_date <= end_date,
        or_(SchoolPlanEvent.end_date.is_(None), SchoolPlanEvent.end_date >= start_date),
    )


def _month_shift(year, month, delta):
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


def _build_calendar_weeks(events, year, month):
    cal = pycalendar.Calendar(firstweekday=0)
    event_map = {}
    for event in events:
        cur = max(event.start_date, date(year, month, 1))
        last_day = pycalendar.monthrange(year, month)[1]
        end = min(event.end_date or event.start_date, date(year, month, last_day))
        while cur <= end:
            event_map.setdefault(cur, []).append(event)
            cur += timedelta(days=1)

    weeks = []
    for week in cal.monthdatescalendar(year, month):
        days = []
        for day in week:
            days.append({
                'date': day,
                'in_month': day.month == month,
                'events': sorted(event_map.get(day, []), key=lambda x: (x.start_date, x.title.lower())),
                'is_today': day == date.today(),
            })
        weeks.append(days)
    return weeks



def _args_int(name):
    value = (request.args.get(name) or '').strip()
    try:
        return int(value) if value else None
    except Exception:
        return None


def _request_args_dict():
    return request.args.to_dict(flat=True)


def _export_filename(prefix, ext):
    stamp = datetime.now().strftime('%Y%m%d_%H%M')
    return f'{prefix}_{stamp}.{ext}'


def _events_for_export(include_archived=False):
    return _event_query(include_archived=include_archived).order_by(SchoolPlanEvent.start_date.asc(), SchoolPlanEvent.created_at.desc()).all()


def _build_excel(events):
    wb = Workbook()
    ws = wb.active
    ws.title = 'План работы школы'
    headers = ['Дата начала', 'Дата окончания', 'Название', 'Направление', 'Категория', 'Ответственный', 'Видимость', 'Здание', 'Класс', 'Статус', 'Важность', 'Место', 'Участники']
    ws.append(headers)
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    for event in events:
        ws.append([
            event.start_date.strftime('%d.%m.%Y') if event.start_date else '',
            (event.end_date or event.start_date).strftime('%d.%m.%Y') if (event.end_date or event.start_date) else '',
            event.title or '',
            event.direction.name if event.direction else '',
            event.category.name if event.category else '',
            event.display_responsible or '',
            VISIBILITY_TITLES.get(event.visibility_level, event.visibility_level or ''),
            (event.building.short_name or event.building.name) if event.building else '',
            event.school_class.name if event.school_class else '',
            STATUS_TITLES.get(event.status, event.status or ''),
            PRIORITY_TITLES.get(event.priority, event.priority or ''),
            event.location or '',
            event.participants or '',
        ])
    widths = [14, 14, 40, 22, 22, 24, 16, 18, 14, 18, 14, 20, 24]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64+i)].width = width
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


def _build_pdf(events, title='План работы школы'):
    font_name, bold_font_name = _ensure_pdf_fonts()

    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    styles['Title'].fontName = bold_font_name
    story = [Paragraph(title, styles['Title']), Spacer(1, 10)]
    data = [['Период', 'Мероприятие', 'Направление', 'Ответственный', 'Видимость', 'Статус']]
    for event in events:
        data.append([
            event.display_period,
            event.title or '',
            event.direction.name if event.direction else '',
            event.display_responsible or '',
            VISIBILITY_TITLES.get(event.visibility_level, event.visibility_level or ''),
            STATUS_TITLES.get(event.status, event.status or ''),
        ])
    table = Table(data, repeatRows=1, colWidths=[90, 220, 110, 120, 80, 90])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('FONTNAME', (0, 0), (-1, 0), bold_font_name),
        ('FONTNAME', (0, 1), (-1, -1), font_name),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('LEADING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    doc.build(story)
    stream.seek(0)
    return stream


def _academic_week_groups(events):
    groups = {}
    for event in events:
        week_no = event.start_date.isocalendar().week
        groups.setdefault(week_no, []).append(event)
    ordered = []
    for week_no in sorted(groups):
        ordered.append((week_no, sorted(groups[week_no], key=lambda x: (x.start_date, x.title.lower()))))
    return ordered


@school_plan_bp.route('/')
@login_required
def index():
    include_archived = _is_manager() and request.args.get('show_archived') == '1'
    events = _event_query(include_archived=include_archived).order_by(SchoolPlanEvent.start_date.asc(), SchoolPlanEvent.created_at.desc()).all()
    return render_template('school_plan/index.html', events=events, can_manage=_is_manager(), active_view='list', **_form_context())


@school_plan_bp.route('/week')
@login_required
def week_view():
    ref = _parse_date(request.args.get('date')) or date.today()
    week_start = ref - timedelta(days=ref.weekday())
    week_end = week_start + timedelta(days=6)
    include_archived = _is_manager() and request.args.get('show_archived') == '1'
    events = _period_overlap(_event_query(include_archived=include_archived), week_start, week_end).order_by(SchoolPlanEvent.start_date.asc(), SchoolPlanEvent.created_at.desc()).all()
    days = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        day_events = [e for e in events if e.start_date <= day <= (e.end_date or e.start_date)]
        days.append({'date': day, 'title': WEEKDAY_TITLES[i], 'events': day_events})
    return render_template('school_plan/week.html', days=days, week_start=week_start, week_end=week_end,
                           prev_date=week_start - timedelta(days=7), next_date=week_start + timedelta(days=7),
                           can_manage=_is_manager(), active_view='week', **_form_context())


@school_plan_bp.route('/month')
@login_required
def month_view():
    today = date.today()
    year = _args_int('year') or today.year
    month = _args_int('month') or today.month
    year, month = _month_shift(year, month, 0)
    month_start = date(year, month, 1)
    month_end = date(year, month, pycalendar.monthrange(year, month)[1])
    include_archived = _is_manager() and request.args.get('show_archived') == '1'
    events = _period_overlap(_event_query(include_archived=include_archived), month_start, month_end).order_by(SchoolPlanEvent.start_date.asc(), SchoolPlanEvent.created_at.desc()).all()
    weeks = _build_calendar_weeks(events, year, month)
    prev_y, prev_m = _month_shift(year, month, -1)
    next_y, next_m = _month_shift(year, month, 1)
    return render_template('school_plan/month.html', weeks=weeks, month=month, year=year,
                           month_title=MONTH_TITLES[month], prev_year=prev_y, prev_month=prev_m,
                           next_year=next_y, next_month=next_m, can_manage=_is_manager(), active_view='month', **_form_context())


@school_plan_bp.route('/day')
@login_required
def day_view():
    selected_date = _parse_date(request.args.get('date')) or date.today()
    include_archived = _is_manager() and request.args.get('show_archived') == '1'
    events = _period_overlap(_event_query(include_archived=include_archived), selected_date, selected_date).order_by(SchoolPlanEvent.start_date.asc(), SchoolPlanEvent.created_at.desc()).all()
    return render_template('school_plan/day.html', selected_date=selected_date, events=events,
                           prev_date=selected_date - timedelta(days=1), next_date=selected_date + timedelta(days=1),
                           can_manage=_is_manager(), active_view='day', **_form_context())


@school_plan_bp.route('/weeks')
@login_required
def weeks_view():
    include_archived = _is_manager() and request.args.get('show_archived') == '1'
    events = _event_query(include_archived=include_archived).order_by(SchoolPlanEvent.start_date.asc(), SchoolPlanEvent.created_at.desc()).all()
    groups = _academic_week_groups(events)
    return render_template('school_plan/weeks.html', week_groups=groups, can_manage=_is_manager(), active_view='weeks', **_form_context())


@school_plan_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    if not _is_manager():
        abort(403)
    event = SchoolPlanEvent()
    if request.method == 'POST':
        _apply_event_form(event)
        db.session.add(event)
        db.session.commit()
        flash('Мероприятие плана создано.', 'success')
        return redirect(url_for('school_plan.index'))
    return render_template('school_plan/form.html', event=event, can_manage=True, active_view='list', **_form_context())


@school_plan_bp.route('/<int:event_id>')
@login_required
def view(event_id):
    event = _visible_events_query(include_archived=True).filter(SchoolPlanEvent.id == event_id).first_or_404()
    return render_template('school_plan/view.html', event=event, can_manage=_is_manager(), active_view='list',
                           status_titles=STATUS_TITLES, priority_titles=PRIORITY_TITLES, visibility_titles=VISIBILITY_TITLES)


@school_plan_bp.route('/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(event_id):
    if not _is_manager():
        abort(403)
    event = SchoolPlanEvent.query.get_or_404(event_id)
    if request.method == 'POST':
        _apply_event_form(event)
        db.session.commit()
        flash('Мероприятие плана обновлено.', 'success')
        return redirect(url_for('school_plan.view', event_id=event.id))
    return render_template('school_plan/form.html', event=event, can_manage=True, active_view='list', **_form_context())


@school_plan_bp.route('/<int:event_id>/archive', methods=['POST'])
@login_required
def archive(event_id):
    if not _is_manager():
        abort(403)
    event = SchoolPlanEvent.query.get_or_404(event_id)
    event.is_archived = True
    event.updated_by_user_id = current_user.id
    db.session.commit()
    flash('Мероприятие перенесено в архив.', 'success')
    return redirect(url_for('school_plan.index'))


@school_plan_bp.route('/<int:event_id>/restore', methods=['POST'])
@login_required
def restore(event_id):
    if not _is_manager():
        abort(403)
    event = SchoolPlanEvent.query.get_or_404(event_id)
    event.is_archived = False
    event.updated_by_user_id = current_user.id
    db.session.commit()
    flash('Мероприятие восстановлено из архива.', 'success')
    return redirect(url_for('school_plan.index', show_archived=1))


@school_plan_bp.route('/<int:event_id>/delete', methods=['POST'])
@login_required
def delete(event_id):
    if not _is_manager():
        abort(403)
    event = SchoolPlanEvent.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    flash('Мероприятие плана удалено.', 'success')
    return redirect(url_for('school_plan.index'))



@school_plan_bp.route('/export/xlsx')
@login_required
def export_xlsx():
    include_archived = _is_manager() and request.args.get('show_archived') == '1'
    stream = _build_excel(_events_for_export(include_archived=include_archived))
    return send_file(stream,
                     as_attachment=True,
                     download_name=_export_filename('school_plan', 'xlsx'),
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@school_plan_bp.route('/export/pdf')
@login_required
def export_pdf():
    include_archived = _is_manager() and request.args.get('show_archived') == '1'
    stream = _build_pdf(_events_for_export(include_archived=include_archived))
    return send_file(stream,
                     as_attachment=True,
                     download_name=_export_filename('school_plan', 'pdf'),
                     mimetype='application/pdf')


@school_plan_bp.route('/print')
@login_required
def print_view_export():
    include_archived = _is_manager() and request.args.get('show_archived') == '1'
    events = _events_for_export(include_archived=include_archived)
    return render_template('school_plan/print.html', events=events,
                           status_titles=STATUS_TITLES, priority_titles=PRIORITY_TITLES,
                           visibility_titles=VISIBILITY_TITLES)


@school_plan_bp.route('/legend')
@login_required
def legend():
    return render_template('school_plan/legend.html', active_view='legend', **_form_context())


def _form_context():
    return {
        'years': AcademicYear.query.order_by(AcademicYear.is_current.desc(), AcademicYear.name.desc()).all(),
        'buildings': Building.query.order_by(Building.name.asc()).all(),
        'classes': SchoolClass.query.order_by(SchoolClass.name.asc()).all(),
        'directions': SchoolPlanDirection.query.filter_by(is_active=True).order_by(SchoolPlanDirection.sort_order.asc(), SchoolPlanDirection.name.asc()).all(),
        'categories': SchoolPlanCategory.query.filter_by(is_active=True).order_by(SchoolPlanCategory.sort_order.asc(), SchoolPlanCategory.name.asc()).all(),
        'users': User.query.filter(User.is_active_user.is_(True)).order_by(User.last_name.asc(), User.first_name.asc()).all(),
        'visibility_choices': [('school', 'Вся школа'), ('building', 'Здание'), ('class', 'Класс')],
        'period_choices': [('day', 'Один день'), ('week', 'Неделя'), ('month', 'Месяц'), ('range', 'Период')],
        'status_choices': [('planned', 'Запланировано'), ('in_progress', 'В работе'), ('done', 'Выполнено'), ('postponed', 'Перенесено'), ('cancelled', 'Отменено')],
        'priority_choices': [('normal', 'Обычный'), ('important', 'Важный'), ('critical', 'Очень важный')],
        'status_titles': STATUS_TITLES,
        'priority_titles': PRIORITY_TITLES,
        'visibility_titles': VISIBILITY_TITLES,
        'current_args': _request_args_dict(),
    }


def _apply_event_form(event):
    title = (request.form.get('title') or '').strip()
    if not title:
        raise abort(400, 'Не указано название мероприятия.')
    event.title = title
    event.short_title = (request.form.get('short_title') or '').strip() or None
    event.description = (request.form.get('description') or '').strip() or None
    event.start_date = _parse_date(request.form.get('start_date'))
    event.end_date = _parse_date(request.form.get('end_date')) or event.start_date
    if not event.start_date:
        raise abort(400, 'Не указана дата начала.')
    event.period_type = (request.form.get('period_type') or 'day').strip()
    event.academic_year_id = request.form.get('academic_year_id', type=int) or None
    event.direction_id = request.form.get('direction_id', type=int) or None
    event.category_id = request.form.get('category_id', type=int) or None
    event.responsible_user_id = request.form.get('responsible_user_id', type=int) or None
    event.responsible_text = (request.form.get('responsible_text') or '').strip() or None
    event.location = (request.form.get('location') or '').strip() or None
    event.participants = (request.form.get('participants') or '').strip() or None
    event.priority = (request.form.get('priority') or 'normal').strip()
    event.status = (request.form.get('status') or 'planned').strip()
    event.visibility_level = (request.form.get('visibility_level') or 'school').strip()
    event.building_id = request.form.get('building_id', type=int) or None
    event.class_id = request.form.get('class_id', type=int) or None
    event.color = (request.form.get('color') or '').strip() or None
    event.text_color = (request.form.get('text_color') or '').strip() or None
    if event.visibility_level == 'school':
        event.building_id = None
        event.class_id = None
    elif event.visibility_level == 'building':
        event.class_id = None
    elif event.visibility_level == 'class' and event.class_id:
        school_class = SchoolClass.query.get(event.class_id)
        if school_class and school_class.building_id:
            event.building_id = school_class.building_id
    if not event.id:
        event.created_by_user_id = current_user.id
    event.updated_by_user_id = current_user.id
