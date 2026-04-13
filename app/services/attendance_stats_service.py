from __future__ import annotations

from collections import defaultdict
from datetime import date
from types import SimpleNamespace

from app.core.extensions import db
from app.core.cache import cache, make_key
from app.models import ChildEnrollment, SchoolClass

RU_MONTHS = {
    '01': 'январь', '02': 'февраль', '03': 'март', '04': 'апрель', '05': 'май', '06': 'июнь',
    '07': 'июль', '08': 'август', '09': 'сентябрь', '10': 'октябрь', '11': 'ноябрь', '12': 'декабрь'
}


def get_default_month() -> str:
    return date.today().strftime('%Y-%m')


def get_month_choices():
    today = date.today()
    years = list(range(today.year - 2, today.year + 2))
    months = [(f'{i:02d}', RU_MONTHS[f'{i:02d}']) for i in range(1, 13)]
    return years, months


def _class_filter_ids_for_user(user) -> list[int] | None:
    role = getattr(user, 'role', None)
    if role != 'CLASS_TEACHER':
        return None
    rows = SchoolClass.query.filter(SchoolClass.teacher_user_id == getattr(user, 'id', None)).all()
    return [x.id for x in rows]


def _month_bounds(month: str):
    year, mon = map(int, month.split('-'))
    start_date = date(year, mon, 1)
    end_date = date(year + (1 if mon == 12 else 0), 1 if mon == 12 else mon + 1, 1)
    return start_date, end_date


def _paginate(items, page=1, per_page=20):
    total = len(items)
    if per_page == 'all':
        per_page_num = total or 1
        page = 1
    else:
        per_page_num = max(1, int(per_page or 20))
        page = max(1, int(page or 1))
    pages = max(1, (total + per_page_num - 1) // per_page_num)
    if page > pages:
        page = pages
    start = (page - 1) * per_page_num
    end = start + per_page_num
    return SimpleNamespace(items=items[start:end], page=page, per_page=per_page, total=total, pages=pages, has_prev=page > 1, has_next=page < pages)


def _to_minutes(value):
    if not value:
        return None
    return value.hour * 60 + value.minute


def _avg_time_str(values):
    if not values:
        return '—'
    minutes = [v.hour * 60 + v.minute for v in values]
    avg = round(sum(minutes) / len(minutes))
    return f"{avg//60:02d}:{avg%60:02d}"


def _build_rank_chart(rows, value_key, label_key, top_n=8):
    ranked = sorted(rows, key=lambda x: (-x.get(value_key, 0), x.get(label_key, '')))[:top_n]
    max_value = max([item.get(value_key, 0) for item in ranked] or [0])
    chart = []
    for item in ranked:
        value = item.get(value_key, 0)
        width = round((value / max_value) * 100, 1) if max_value else 0
        chart.append({
            'label': item.get(label_key, '—'),
            'value': value,
            'width': width,
            'subtitle': item.get('subtitle') or '',
        })
    return chart


def build_attendance_dashboard_stats(user=None) -> dict:
    from app.attendance import AttendanceImportSession, AttendanceLate, AttendancePass
    today = date.today()
    class_ids = _class_filter_ids_for_user(user)
    late_q = AttendanceLate.query.filter(AttendanceLate.late_date == today)
    pass_q = AttendancePass.query.filter(AttendancePass.status == 'created')
    if class_ids is not None:
        if class_ids:
            late_q = late_q.filter(AttendanceLate.class_id.in_(class_ids))
            pass_q = pass_q.filter(AttendancePass.class_id.in_(class_ids))
        else:
            late_q = late_q.filter(db.text('1=0'))
            pass_q = pass_q.filter(db.text('1=0'))
    return {'today_lates': late_q.count(), 'active_passes': pass_q.count(), 'imports_count': AttendanceImportSession.query.count()}


def _get_month_school_days(month: str):
    from app.attendance import AttendanceSchoolDay

    rows = AttendanceSchoolDay.query.filter_by(month_key=month, is_school_day=True).order_by(AttendanceSchoolDay.day_date.asc()).all()
    if rows:
        return [x.day_date for x in rows]
    start_date, end_date = _month_bounds(month)
    result = []
    cursor = start_date
    while cursor < end_date:
        if cursor.weekday() < 5:
            result.append(cursor)
        cursor = date.fromordinal(cursor.toordinal() + 1)
    return result


def _current_year_id():
    from app.models import AcademicYear
    current = AcademicYear.query.filter_by(is_current=True).first()
    return current.id if current else None


def build_month_analytics(month: str, user=None, grade=None, class_id=None, building_id=None, mode='school', class_page=1, student_page=1, sessions_page=1, per_page=20) -> dict:
    from app.attendance import AttendanceImportSession, AttendanceRawEntry, resolve_start_time_for_class

    cache_key = make_key('attendance-analytics', month, getattr(user, 'id', None), getattr(user, 'role', None), grade, class_id, building_id, mode, class_page, student_page, sessions_page, per_page)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    class_ids = _class_filter_ids_for_user(user)
    start_date, end_date = _month_bounds(month)
    school_days = _get_month_school_days(month)
    school_days_set = set(school_days)
    school_days_count = len(school_days)

    base_q = AttendanceRawEntry.query.filter(AttendanceRawEntry.entry_date >= start_date, AttendanceRawEntry.entry_date < end_date)

    if class_ids is not None:
        if class_ids:
            base_q = base_q.filter(AttendanceRawEntry.matched_class_id.in_(class_ids))
        else:
            base_q = base_q.filter(db.text('1=0'))

    need_class_join = bool(grade or building_id)
    if need_class_join:
        base_q = base_q.join(SchoolClass, AttendanceRawEntry.matched_class_id == SchoolClass.id)
    if class_id:
        base_q = base_q.filter(AttendanceRawEntry.matched_class_id == class_id)
    elif grade:
        base_q = base_q.filter(SchoolClass.grade == grade)
    if building_id:
        base_q = base_q.filter(SchoolClass.building_id == building_id)

    entries = [row for row in base_q.order_by(AttendanceRawEntry.entry_date.desc(), AttendanceRawEntry.full_name.asc()).all() if row.entry_date in school_days_set]
    recognized_entries = [row for row in entries if row.entry_date]

    # contingent by class
    current_year_id = _current_year_id()
    class_q = SchoolClass.query.filter(SchoolClass.is_archived.is_(False))
    if current_year_id:
        class_q = class_q.filter(SchoolClass.academic_year_id == current_year_id)
    if class_ids is not None:
        if class_ids:
            class_q = class_q.filter(SchoolClass.id.in_(class_ids))
        else:
            class_q = class_q.filter(db.text('1=0'))
    if class_id:
        class_q = class_q.filter(SchoolClass.id == class_id)
    elif grade:
        class_q = class_q.filter(SchoolClass.grade == grade)
    if building_id:
        class_q = class_q.filter(SchoolClass.building_id == building_id)
    classes = class_q.order_by(SchoolClass.grade.asc().nulls_last(), SchoolClass.name.asc()).all()
    class_ids_scope = [c.id for c in classes]

    enroll_q = ChildEnrollment.query.filter(ChildEnrollment.ended_at.is_(None))
    if current_year_id:
        enroll_q = enroll_q.filter(ChildEnrollment.academic_year_id == current_year_id)
    if class_ids_scope:
        enroll_q = enroll_q.filter(ChildEnrollment.school_class_id.in_(class_ids_scope))
    else:
        enroll_q = enroll_q.filter(db.text('1=0'))
    enrollments = enroll_q.all()
    contingent_by_class_id = defaultdict(set)
    for enr in enrollments:
        contingent_by_class_id[enr.school_class_id].add(enr.child_id)

    contingent_by_class_name = {}
    building_name_by_class_id = {}
    building_classes = defaultdict(list)
    total_contingent_students = 0
    for sc in classes:
        cnt = len(contingent_by_class_id.get(sc.id, set()))
        contingent_by_class_name[sc.name] = cnt
        total_contingent_students += cnt
        building_name = sc.building.name if getattr(sc, 'building', None) else 'Без здания'
        building_name_by_class_id[sc.id] = building_name
        building_classes[building_name].append(sc)

    no_entry_count = sum(1 for row in recognized_entries if row.no_entry_fix)
    no_exit_count = sum(1 for row in recognized_entries if row.no_exit_fix)
    unique_students = len({(row.child_id or row.full_name) for row in recognized_entries})
    unique_classes = len({(row.matched_class_id or row.source_class_name or 'Без класса') for row in recognized_entries})

    classes_map = defaultdict(lambda: {'class_id': None, 'building_name': 'Без здания', 'students': set(), 'days': set(), 'present': 0, 'lates': 0, 'late_minutes_sum': 0, 'no_entry': 0, 'no_exit': 0, 'first_ins': [], 'problems': 0})
    students_map = defaultdict(lambda: {'name': '', 'class_name': '—', 'building_name': 'Без здания', 'lates': set(), 'days': set(), 'days_with_entry': set(), 'present_days': set(), 'no_entry': 0, 'no_exit': 0, 'first_ins': [], 'max_late': 0, 'late_minutes_sum': 0, 'problems': 0})
    daily_map = defaultdict(lambda: {'students': set(), 'present_students': set(), 'lates': 0, 'late_minutes_sum': 0, 'no_entry': 0, 'no_exit': 0})
    building_map = defaultdict(lambda: {'classes': set(), 'students': set(), 'present': 0, 'lates': 0, 'late_minutes_sum': 0, 'no_entry': 0, 'no_exit': 0, 'first_ins': [], 'problems': 0})
    threshold_cache = {}

    for row in recognized_entries:
        school_class = getattr(row, 'school_class', None)
        class_name = school_class.name if school_class else (row.source_class_name or 'Без класса')
        class_id_value = getattr(school_class, 'id', None)
        child_name = row.child.fio if getattr(row, 'child', None) else (row.full_name or 'Не определён')
        building_name = building_name_by_class_id.get(class_id_value, getattr(getattr(school_class, 'building', None), 'name', None) or 'Без здания')

        cache_key = class_id_value
        if cache_key not in threshold_cache:
            threshold_cache[cache_key] = resolve_start_time_for_class(school_class)
        threshold = threshold_cache.get(cache_key)
        first_in_minutes = _to_minutes(row.first_in)
        threshold_minutes = _to_minutes(threshold)
        late_minutes = 0
        is_late_dynamic = bool(first_in_minutes is not None and threshold_minutes is not None and first_in_minutes > threshold_minutes)
        if is_late_dynamic:
            late_minutes = first_in_minutes - threshold_minutes

        class_item = classes_map[class_name]
        class_item['class_id'] = class_id_value
        class_item['building_name'] = building_name
        class_item['students'].add(row.child_id or row.full_name)
        class_item['days'].add(row.entry_date)
        if not row.is_absent:
            class_item['present'] += 1
        if is_late_dynamic:
            class_item['lates'] += 1
            class_item['late_minutes_sum'] += late_minutes
        if row.no_entry_fix:
            class_item['no_entry'] += 1
        if row.no_exit_fix:
            class_item['no_exit'] += 1
        if row.no_entry_fix or row.no_exit_fix:
            class_item['problems'] += 1
        if row.first_in:
            class_item['first_ins'].append(row.first_in)

        student_key = row.child_id or row.full_name or f'row-{row.id}'
        student_item = students_map[student_key]
        student_item['name'] = child_name
        student_item['class_name'] = class_name
        student_item['building_name'] = building_name
        student_item['days'].add(row.entry_date)
        if not row.is_absent:
            student_item['present_days'].add(row.entry_date)
        if row.first_in:
            student_item['days_with_entry'].add(row.entry_date)
            student_item['first_ins'].append(row.first_in)
        if is_late_dynamic:
            student_item['lates'].add(row.entry_date)
            student_item['late_minutes_sum'] += late_minutes
            student_item['max_late'] = max(student_item['max_late'], late_minutes)
        if row.no_entry_fix:
            student_item['no_entry'] += 1
        if row.no_exit_fix:
            student_item['no_exit'] += 1
        if row.no_entry_fix or row.no_exit_fix:
            student_item['problems'] += 1

        d = daily_map[row.entry_date]
        d['students'].add(student_key)
        if not row.is_absent:
            d['present_students'].add(student_key)
        if is_late_dynamic:
            d['lates'] += 1
            d['late_minutes_sum'] += late_minutes
        if row.no_entry_fix:
            d['no_entry'] += 1
        if row.no_exit_fix:
            d['no_exit'] += 1

        b = building_map[building_name]
        b['classes'].add(class_name)
        b['students'].add(student_key)
        if not row.is_absent:
            b['present'] += 1
        if is_late_dynamic:
            b['lates'] += 1
            b['late_minutes_sum'] += late_minutes
        if row.no_entry_fix:
            b['no_entry'] += 1
        if row.no_exit_fix:
            b['no_exit'] += 1
        if row.no_entry_fix or row.no_exit_fix:
            b['problems'] += 1
        if row.first_in:
            b['first_ins'].append(row.first_in)

    total_possible_visits = total_contingent_students * school_days_count
    total_present_visits = sum(item['present'] for item in classes_map.values())
    attendance_percent = round((total_present_visits / total_possible_visits) * 100, 1) if total_possible_visits else 0.0

    class_rows = []
    for sc in classes:
        item = classes_map.get(sc.name, {'present': 0, 'lates': 0, 'late_minutes_sum': 0, 'no_entry': 0, 'no_exit': 0, 'first_ins': [], 'problems': 0, 'days': set(), 'students': set()})
        contingent = len(contingent_by_class_id.get(sc.id, set()))
        total_possible = contingent * school_days_count
        percent = round((item['present'] / total_possible) * 100, 1) if total_possible else 0.0
        avg_late = round(item['late_minutes_sum'] / item['lates'], 1) if item['lates'] else 0
        class_rows.append({
            'class_name': sc.name,
            'building_name': building_name_by_class_id.get(sc.id, 'Без здания'),
            'students': contingent,
            'days': school_days_count,
            'attendance_percent': percent,
            'lates': item['lates'],
            'avg_late_minutes': avg_late,
            'no_entry': item['no_entry'],
            'no_exit': item['no_exit'],
            'avg_first_in': _avg_time_str(item['first_ins']),
            'problem_passes': item['problems'],
            'subtitle': f"ср. опоздание {avg_late} мин" if avg_late else 'без опозданий',
        })
    class_rows.sort(key=lambda x: (x['class_name']))

    student_rows = []
    anomaly_count = 0
    for _, item in students_map.items():
        lates_count = min(len(item['lates']), len(item['days_with_entry']))
        if len(item['lates']) > len(item['days_with_entry']):
            anomaly_count += 1
        avg_late = round(item['late_minutes_sum'] / lates_count, 1) if lates_count else 0
        attend_pct = round((len(item['present_days']) / school_days_count) * 100, 1) if school_days_count else 0.0
        student_rows.append({
            'name': item['name'],
            'class_name': item['class_name'],
            'building_name': item['building_name'],
            'lates': lates_count,
            'days': school_days_count,
            'days_with_entry': len(item['days_with_entry']),
            'attendance_percent': attend_pct,
            'no_entry': item['no_entry'],
            'no_exit': item['no_exit'],
            'avg_first_in': _avg_time_str(item['first_ins']),
            'avg_late_minutes': avg_late,
            'max_late': item['max_late'],
            'problem_passes': item['problems'],
        })
    student_rows.sort(key=lambda x: (-x['lates'], x['name']))

    daily_rows = []
    for day in school_days:
        item = daily_map.get(day, {'students': set(), 'present_students': set(), 'lates': 0, 'late_minutes_sum': 0, 'no_entry': 0, 'no_exit': 0})
        percent = round((len(item['present_students']) / total_contingent_students) * 100, 1) if total_contingent_students else 0.0
        avg_late = round(item['late_minutes_sum'] / item['lates'], 1) if item['lates'] else 0
        daily_rows.append({
            'date': day,
            'students': len(item['present_students']),
            'lates': item['lates'],
            'avg_late_minutes': avg_late,
            'no_entry': item['no_entry'],
            'no_exit': item['no_exit'],
            'absent': max(total_contingent_students - len(item['present_students']), 0),
            'attendance_percent': percent,
            'subtitle': f"ср. {avg_late} мин" if avg_late else 'без опозданий',
        })

    building_rows = []
    for building_name, class_list in building_classes.items():
        class_names = [sc.name for sc in class_list]
        item = building_map.get(building_name, {'present': 0, 'lates': 0, 'late_minutes_sum': 0, 'no_entry': 0, 'no_exit': 0, 'first_ins': [], 'problems': 0, 'students': set()})
        contingent = sum(len(contingent_by_class_id.get(sc.id, set())) for sc in class_list)
        total_possible = contingent * school_days_count
        percent = round((item['present'] / total_possible) * 100, 1) if total_possible else 0.0
        avg_late = round(item['late_minutes_sum'] / item['lates'], 1) if item['lates'] else 0
        building_rows.append({
            'building_name': building_name,
            'classes': len(class_names),
            'students': contingent,
            'days': school_days_count,
            'attendance_percent': percent,
            'lates': item['lates'],
            'avg_late_minutes': avg_late,
            'no_entry': item['no_entry'],
            'no_exit': item['no_exit'],
            'problem_passes': item['problems'],
            'avg_first_in': _avg_time_str(item['first_ins']),
            'subtitle': f"{len(class_names)} классов" if class_names else 'нет классов',
        })
    building_rows.sort(key=lambda x: x['building_name'])

    sessions_q = AttendanceImportSession.query.filter(AttendanceImportSession.period_month == month)
    sessions = sessions_q.order_by(AttendanceImportSession.imported_at.desc()).all()
    lates_month = sum(x['lates'] for x in student_rows)
    late_minutes_total = sum(x['late_minutes_sum'] for x in classes_map.values())

    result = {
        'month': month,
        'entries_count': len(recognized_entries),
        'lates_month': lates_month,
        'attendance_percent': attendance_percent,
        'recognized_students': unique_students,
        'recognized_classes': unique_classes,
        'no_entry_count': no_entry_count,
        'no_exit_count': no_exit_count,
        'anomaly_count': anomaly_count,
        'late_minutes_total': late_minutes_total,
        'avg_late_minutes': round(late_minutes_total / lates_month, 1) if lates_month else 0,
        'school_days_count': school_days_count,
        'contingent_total': total_contingent_students,
        'building_rows': building_rows,
        'class_rows': class_rows,
        'student_rows': student_rows,
        'daily_rows': daily_rows,
        'sessions': sessions,
        'class_pagination': _paginate(class_rows, page=class_page, per_page=per_page),
        'student_pagination': _paginate(student_rows, page=student_page, per_page=per_page),
        'sessions_pagination': _paginate(sessions, page=sessions_page, per_page=per_page),
        'chart_top_buildings': _build_rank_chart(building_rows, 'lates', 'building_name', top_n=8),
        'chart_top_classes': _build_rank_chart(class_rows, 'lates', 'class_name', top_n=8),
        'chart_top_students': _build_rank_chart(student_rows, 'lates', 'name', top_n=8),
        'chart_daily_lates': _build_rank_chart([
            {'label': x['date'].strftime('%d.%m'), 'value': x['lates'], 'subtitle': x['subtitle']}
            for x in daily_rows
        ], 'value', 'label', top_n=10),
    }
    cache.set(cache_key, result, timeout=300)
    return result
