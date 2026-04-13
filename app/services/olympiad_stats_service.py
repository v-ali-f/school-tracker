from __future__ import annotations

from collections import defaultdict

from ..models import AcademicYear, OlympiadResult


def _base_query(academic_year_id=None):
    q = OlympiadResult.query.filter(OlympiadResult.is_archived.is_(False))
    if academic_year_id:
        q = q.filter(OlympiadResult.academic_year_id == academic_year_id)
    return q


def dashboard_stats(academic_year_id=None):
    rows = _base_query(academic_year_id).all()
    winners = sum(1 for r in rows if (r.status or "").strip().lower() == "победитель")
    prizers = sum(1 for r in rows if "приз" in (r.status or "").strip().lower())
    participants = len(rows) - winners - prizers
    by_stage = defaultdict(int)
    by_status = defaultdict(int)
    for r in rows:
        by_stage[r.stage or "—"] += 1
        by_status[(r.status or "участник").strip() or "участник"] += 1
    return {
        "total_results": len(rows),
        "total": len(rows),
        "unique_children": len({r.child_id for r in rows if r.child_id}),
        "winners": winners,
        "prizers": prizers,
        "participants": participants,
        "by_stage": [[k, v] for k, v in sorted(by_stage.items())],
        "by_status": [[k, v] for k, v in sorted(by_status.items())],
    }


def teacher_stats(academic_year_id=None, teacher_id=None):
    q = _base_query(academic_year_id)
    if teacher_id:
        q = q.filter(OlympiadResult.teacher_id == teacher_id)
    rows = q.all()
    by_teacher = defaultdict(int)
    for r in rows:
        key = r.teacher.fio if getattr(r, "teacher", None) else "Не определён"
        by_teacher[key] += 1
    return [[k, v] for k, v in sorted(by_teacher.items(), key=lambda x: x[1], reverse=True)[:15]]


def department_stats(academic_year_id=None, department_id=None):
    q = _base_query(academic_year_id)
    if department_id:
        q = q.filter(OlympiadResult.department_id == department_id)
    rows = q.all()
    by_subject = defaultdict(int)
    by_teacher = defaultdict(lambda: {"name": "", "subjects": set(), "total": 0, "winners": 0, "prizers": 0})
    winners = prizers = 0
    for r in rows:
        subj = r.subject_name or (r.subject.name if getattr(r, "subject", None) else "—")
        by_subject[subj] += 1
        tname = r.teacher.fio if getattr(r, "teacher", None) else "Не определён"
        item = by_teacher[tname]
        item["name"] = tname
        item["subjects"].add(subj)
        item["total"] += 1
        status = (r.status or "").strip().lower()
        if status == "победитель":
            item["winners"] += 1
            winners += 1
        if "приз" in status:
            item["prizers"] += 1
            prizers += 1
    teacher_rows = []
    for _, item in by_teacher.items():
        teacher_rows.append({
            "name": item["name"],
            "subject": ", ".join(sorted(item["subjects"])),
            "total": item["total"],
            "winners": item["winners"],
            "prizers": item["prizers"],
        })
    teacher_rows.sort(key=lambda x: (-x["total"], x["name"]))
    subject_rows = [{"name": k, "count": v} for k, v in sorted(by_subject.items(), key=lambda x: (-x[1], x[0]))]
    return {
        "total_results": len(rows),
        "unique_children": len({r.child_id for r in rows if r.child_id}),
        "winners": winners,
        "prizers": prizers,
        "by_subject": subject_rows,
        "by_teacher": teacher_rows,
    }


def subject_stats(academic_year_id=None):
    rows = _base_query(academic_year_id).all()
    by_subject = defaultdict(int)
    for r in rows:
        by_subject[r.subject_name or (r.subject.name if getattr(r, "subject", None) else "—")] += 1
    return [[k, v] for k, v in sorted(by_subject.items(), key=lambda x: x[1], reverse=True)[:15]]


def class_stats(academic_year_id=None):
    rows = _base_query(academic_year_id).all()
    by_class = defaultdict(int)
    for r in rows:
        key = r.school_class.name if getattr(r, "school_class", None) else (r.class_study_text or r.class_participation_text or "—")
        by_class[key] += 1
    return sorted(by_class.items(), key=lambda x: x[0])


def yearly_comparison():
    years = AcademicYear.query.order_by(AcademicYear.start_date.asc().nullslast(), AcademicYear.name.asc()).all()
    rows = []
    for y in years:
        stats = dashboard_stats(y.id)
        rows.append({
            "year_name": y.name,
            "total_results": stats["total_results"],
            "unique_children": stats["unique_children"],
            "winners": stats["winners"],
            "prizers": stats["prizers"],
            "participants": stats["participants"],
        })
    return rows
