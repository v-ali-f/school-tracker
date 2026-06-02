from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.models import AcademicYear, ControlWorkResult, OlympiadResult, TeacherLoad, User


@dataclass
class TeacherRatingRow:
    teacher: User
    control_avg: float | None
    olympiad_results: int
    winners: int
    load_hours: float
    score: float


def build_teacher_rating(limit: int = 100):
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    teacher_map = {}
    for user in User.query.order_by(User.last_name.asc(), User.first_name.asc()).all():
        if getattr(user, 'role', None) in {'ADMIN', 'MANAGEMENT', 'DEPARTMENT_HEAD', 'TEACHER', 'METHODIST', 'CLASS_TEACHER'}:
            teacher_map[user.id] = user

    control_values = defaultdict(list)
    q = ControlWorkResult.query
    if current_year:
        q = q.filter(ControlWorkResult.academic_year_id == current_year.id)
    for row in q.all():
        if row.teacher_id and row.percent is not None:
            try:
                control_values[row.teacher_id].append(float(row.percent))
            except Exception:
                pass

    olympiad_counts = defaultdict(int)
    winners = defaultdict(int)
    q = OlympiadResult.query.filter(OlympiadResult.is_archived.is_(False))
    if current_year:
        q = q.filter(OlympiadResult.academic_year_id == current_year.id)
    for row in q.all():
        if row.teacher_id:
            olympiad_counts[row.teacher_id] += 1
            status = (row.status or '').strip().lower()
            if 'побед' in status or status == 'winner':
                winners[row.teacher_id] += 1

    load_hours = defaultdict(float)
    q = TeacherLoad.query.filter(TeacherLoad.is_archived.is_(False))
    if current_year:
        q = q.filter((TeacherLoad.academic_year_id == current_year.id) | (TeacherLoad.academic_year_id.is_(None)))
    for row in q.all():
        if row.teacher_id:
            load_hours[row.teacher_id] += float(row.hours or 0)

    items = []
    for teacher_id, teacher in teacher_map.items():
        control_avg = round(sum(control_values[teacher_id]) / len(control_values[teacher_id]), 1) if control_values[teacher_id] else None
        score = (control_avg or 0) * 0.5 + olympiad_counts[teacher_id] * 1.0 + winners[teacher_id] * 3.0 + load_hours[teacher_id] * 0.05
        items.append(TeacherRatingRow(teacher=teacher, control_avg=control_avg, olympiad_results=olympiad_counts[teacher_id], winners=winners[teacher_id], load_hours=round(load_hours[teacher_id], 1), score=round(score, 2)))

    items.sort(key=lambda x: (x.score, x.teacher.fio), reverse=True)
    return {
        'current_year': current_year,
        'rows': items[:limit],
    }
