from __future__ import annotations

from datetime import datetime, time
import json
import re

from app.core.extensions import db
from app.models import AcademicYear, Child, ChildEnrollment
from app.modules.imports.import_attendance import parse_attendance_file


def _parse_time(value):
    if value in (None, ""):
        return None
    if hasattr(value, "time"):
        try:
            return value.time().replace(second=0, microsecond=0)
        except Exception:
            pass
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if not m:
        return None
    return time(int(m.group(1)), int(m.group(2)))


def _parse_minutes(value):
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if ':' in text:
        try:
            hh, mm, *_ = text.split(':')
            return int(hh) * 60 + int(mm)
        except Exception:
            pass
    digits = re.findall(r"\d+", text)
    if not digits:
        return None
    nums = [int(x) for x in digits]
    if len(nums) >= 2:
        return nums[0] * 60 + nums[1]
    return nums[0]


def _current_year():
    return AcademicYear.query.filter_by(is_current=True).first()


def _find_child_by_fio(fio: str):
    parts = [p for p in str(fio or '').replace('  ', ' ').strip().split() if p]
    if len(parts) < 2:
        return None
    last_name = parts[0]
    first_name = parts[1]
    middle_name = parts[2] if len(parts) >= 3 else None
    q = Child.query.filter(Child.last_name.ilike(last_name), Child.first_name.ilike(first_name))
    if middle_name:
        q = q.filter(Child.middle_name.ilike(middle_name))
    row = q.first()
    if row:
        return row
    return Child.query.filter(Child.last_name.ilike(last_name), Child.first_name.ilike(first_name)).first()


def _find_current_class(child):
    current_year = _current_year()
    q = ChildEnrollment.query.filter(ChildEnrollment.child_id == child.id, ChildEnrollment.ended_at.is_(None))
    if current_year:
        q = q.filter(ChildEnrollment.academic_year_id == current_year.id)
    enrollment = q.order_by(ChildEnrollment.id.desc()).first()
    return enrollment.school_class if enrollment and enrollment.school_class else None


def _late_threshold_for_class(school_class):
    from app.attendance import resolve_start_time_for_class

    threshold = resolve_start_time_for_class(school_class)
    return threshold or time(9, 0)


def _min_time(a, b):
    if a and b:
        return a if a <= b else b
    return a or b


def _max_time(a, b):
    if a and b:
        return a if a >= b else b
    return a or b


def _aggregate_records(records):
    grouped = {}
    for row in records:
        fio = str(row.get('fio') or '').strip()
        entry_date = row.get('date')
        source_class_name = str(row.get('school_class') or 'Без класса').strip()
        if not fio or not entry_date:
            continue
        key = (fio.lower(), source_class_name.lower(), entry_date)
        first_in = _parse_time(row.get('first_in'))
        last_out = _parse_time(row.get('last_out'))
        presence = _parse_minutes(row.get('total_presence')) or _parse_minutes(row.get('presence_duration')) or 0
        bucket = grouped.setdefault(
            key,
            {
                'fio': fio,
                'date': entry_date,
                'school_class': source_class_name,
                'first_in': None,
                'last_out': None,
                'presence_minutes': 0,
                'presence_text': row.get('total_presence') or row.get('presence_duration'),
                'events': [],
                'raw_rows': [],
            },
        )
        bucket['first_in'] = _min_time(bucket['first_in'], first_in)
        bucket['last_out'] = _max_time(bucket['last_out'], last_out)
        bucket['presence_minutes'] = max(bucket['presence_minutes'], presence)
        if not bucket['presence_text'] and (row.get('total_presence') or row.get('presence_duration')):
            bucket['presence_text'] = row.get('total_presence') or row.get('presence_duration')
        events = row.get('events')
        if events:
            bucket['events'].append(str(events))
        bucket['raw_rows'].append(row)
    return list(grouped.values())


def delete_import_session(session_id: int):
    from app.attendance import AttendanceImportSession, AttendanceLate, AttendanceRawEntry
    try:
        AttendanceLate.query.filter_by(import_session_id=session_id).delete()
        AttendanceRawEntry.query.filter_by(import_session_id=session_id).delete()
        AttendanceImportSession.query.filter_by(id=session_id).delete()
        db.session.commit()
        return True, 'Импорт удалён.'
    except Exception as exc:
        db.session.rollback()
        return False, f'Не удалось удалить импорт: {exc}'


def import_attendance_report(path: str, filename: str, imported_by: int | None = None, period_month: str | None = None, school_days=None, building_id: int | None = None):
    from app.attendance import AttendanceImportSession, AttendanceLate, AttendanceRawEntry
    try:
        raw_records = parse_attendance_file(path)
        if not raw_records:
            return {'ok': False, 'message': 'Файл прочитан, но записи посещаемости не найдены.'}
        records = _aggregate_records(raw_records)
        if not records:
            return {'ok': False, 'message': 'После объединения строк не осталось корректных записей.'}

        now = datetime.utcnow()
        period_year = None
        period_num = None
        if period_month and '-' in period_month:
            try:
                y, m = period_month.split('-', 1)
                period_year = int(y)
                period_num = int(m)
            except Exception:
                period_year = None
                period_num = None
        session = AttendanceImportSession(filename=filename, imported_by=imported_by, period_month=period_month, period_year=period_year, period_num=period_num, building_id=building_id, imported_at=now, created_at=now, school_days_count=len(school_days or []))
        db.session.add(session)
        db.session.flush()

        rows_total = len(raw_records)
        rows_processed = 0
        rows_matched = 0
        rows_unmatched = 0
        rows_absent = 0
        rows_no_entry = 0
        rows_no_exit = 0
        late_created = 0
        months_seen = set()
        seen_classes = set()
        seen_children = set()

        for row in records:
            fio = row.get('fio')
            entry_date = row.get('date')
            source_class_name = row.get('school_class') or 'Без класса'
            if source_class_name:
                seen_classes.add(source_class_name)
            if not fio or not entry_date:
                continue
            rows_processed += 1
            months_seen.add(entry_date.strftime('%Y-%m'))
            seen_children.add((source_class_name, str(fio).strip()))

            entry_time = row.get('first_in')
            exit_time = row.get('last_out')
            presence_minutes = row.get('presence_minutes')

            no_entry_fix = entry_time is None and exit_time is not None
            no_exit_fix = entry_time is not None and exit_time is None
            is_present = bool(entry_time or exit_time or (presence_minutes is not None and presence_minutes > 0))
            is_absent = not is_present
            if is_absent:
                rows_absent += 1
            if no_entry_fix:
                rows_no_entry += 1
            if no_exit_fix:
                rows_no_exit += 1

            child = _find_child_by_fio(str(fio))
            school_class = _find_current_class(child) if child else None
            threshold = _late_threshold_for_class(school_class) if school_class else time(9, 0)
            is_late = bool(entry_time and threshold and entry_time > threshold)
            late_minutes = None
            if is_late and entry_time:
                late_minutes = (entry_time.hour * 60 + entry_time.minute) - (threshold.hour * 60 + threshold.minute)

            raw = AttendanceRawEntry(
                import_session_id=session.id,
                child_id=child.id if child else None,
                full_name=str(fio).strip(),
                source_class_name=source_class_name,
                entry_date=entry_date,
                first_in=entry_time,
                last_out=exit_time,
                presence_minutes=presence_minutes,
                presence_text=row.get('presence_text'),
                inputs_outputs=' | '.join(row.get('events') or [])[:255] or None,
                is_late=is_late,
                is_absent=is_absent,
                is_early_leave=False,
                no_entry_fix=no_entry_fix,
                no_exit_fix=no_exit_fix,
                matched_class_id=school_class.id if school_class else None,
                raw_payload=json.dumps(row.get('raw_rows') or [], ensure_ascii=False, default=str),
                created_at=now,
            )
            db.session.add(raw)

            if child:
                rows_matched += 1
            else:
                rows_unmatched += 1

            if is_late and child:
                exists = AttendanceLate.query.filter_by(child_id=child.id, late_date=entry_date).first()
                if not exists:
                    db.session.add(AttendanceLate(child_id=child.id, class_id=school_class.id if school_class else None, late_date=entry_date, late_time=entry_time, norm_time=threshold, late_minutes=late_minutes, source='IMPORT', import_session_id=session.id, created_by=imported_by, created_at=now))
                    late_created += 1

        if not session.period_month and months_seen:
            session.period_month = sorted(months_seen)[-1]
        session.rows_total = rows_total
        session.rows_processed = rows_processed
        session.rows_matched = rows_matched
        session.rows_unmatched = rows_unmatched
        session.rows_late = late_created
        session.rows_early_leave = 0
        session.rows_absent = rows_absent
        session.rows_no_entry = rows_no_entry
        session.rows_no_exit = rows_no_exit
        session.unique_classes = len(seen_classes)
        session.unique_children = len(seen_children)
        session.notes = f'Опозданий: {late_created}, без входа: {rows_no_entry}, без выхода: {rows_no_exit}, учебных дней: {len(school_days or [])}'
        db.session.commit()
        return {
            'ok': True,
            'message': f'Импорт завершён. Обработано строк: {rows_processed}, учеников: {len(seen_children)}, классов: {len(seen_classes)}, опозданий: {late_created}.',
            'period_month': session.period_month,
            'session_id': session.id,
        }
    except Exception as exc:
        db.session.rollback()
        return {'ok': False, 'message': f'Ошибка импорта: {exc}'}
