from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from ..core.extensions import db
from ..models import AcademicYear, OlympiadResult


def _base_query(academic_year_id=None):
    q = OlympiadResult.query.filter(OlympiadResult.is_archived.is_(False))
    if academic_year_id:
        q = q.filter(OlympiadResult.academic_year_id == academic_year_id)
    return q


def _load_rows_eager(academic_year_id=None):
    """Load all results once with eager-loaded relationships."""
    return (
        _base_query(academic_year_id)
        .options(
            joinedload(OlympiadResult.teacher),
            joinedload(OlympiadResult.subject),
            joinedload(OlympiadResult.school_class),
        )
        .all()
    )


def _compute_dashboard(rows):
    """Compute dashboard_stats from pre-loaded rows."""
    winners = 0
    prizers = 0
    by_stage = defaultdict(int)
    by_status = defaultdict(int)
    child_ids = set()
    for r in rows:
        status_lower = (r.status or "").strip().lower()
        if status_lower == "победитель":
            winners += 1
        elif "приз" in status_lower:
            prizers += 1
        by_stage[r.stage or "—"] += 1
        by_status[(r.status or "участник").strip() or "участник"] += 1
        if r.child_id:
            child_ids.add(r.child_id)
    return {
        "total_results": len(rows),
        "total": len(rows),
        "unique_children": len(child_ids),
        "winners": winners,
        "prizers": prizers,
        "participants": len(rows) - winners - prizers,
        "by_stage": [[k, v] for k, v in sorted(by_stage.items())],
        "by_status": [[k, v] for k, v in sorted(by_status.items())],
    }


def dashboard_stats(academic_year_id=None):
    rows = _load_rows_eager(academic_year_id)
    return _compute_dashboard(rows)


def all_analytics(academic_year_id=None, teacher_id=None, department_id=None):
    """Compute ALL analytics in a single pass over one set of rows."""
    rows = _load_rows_eager(academic_year_id)

    # --- dashboard ---
    summary = _compute_dashboard(rows)

    # --- teacher_stats ---
    teacher_rows = rows
    if teacher_id:
        teacher_rows = [r for r in rows if r.teacher_id == teacher_id]
    by_teacher_count = defaultdict(int)
    for r in teacher_rows:
        key = r.teacher.fio if r.teacher else "Не определён"
        by_teacher_count[key] += 1
    by_teacher = [[k, v] for k, v in sorted(by_teacher_count.items(), key=lambda x: x[1], reverse=True)[:15]]

    # --- department_stats ---
    dept_rows = rows
    if department_id:
        dept_rows = [r for r in rows if r.department_id == department_id]
    dept_by_subject = defaultdict(int)
    dept_by_teacher = defaultdict(lambda: {"name": "", "subjects": set(), "total": 0, "winners": 0, "prizers": 0})
    dept_winners = dept_prizers = 0
    dept_child_ids = set()
    for r in dept_rows:
        subj = r.subject_name or (r.subject.name if r.subject else "—")
        dept_by_subject[subj] += 1
        tname = r.teacher.fio if r.teacher else "Не определён"
        item = dept_by_teacher[tname]
        item["name"] = tname
        item["subjects"].add(subj)
        item["total"] += 1
        status = (r.status or "").strip().lower()
        if status == "победитель":
            item["winners"] += 1
            dept_winners += 1
        if "приз" in status:
            item["prizers"] += 1
            dept_prizers += 1
        if r.child_id:
            dept_child_ids.add(r.child_id)
    dept_teacher_rows = sorted(
        [{"name": it["name"], "subject": ", ".join(sorted(it["subjects"])), "total": it["total"], "winners": it["winners"], "prizers": it["prizers"]}
         for it in dept_by_teacher.values()],
        key=lambda x: (-x["total"], x["name"]),
    )
    dept_subject_rows = [{"name": k, "count": v} for k, v in sorted(dept_by_subject.items(), key=lambda x: (-x[1], x[0]))]
    by_department = {
        "total_results": len(dept_rows),
        "unique_children": len(dept_child_ids),
        "winners": dept_winners,
        "prizers": dept_prizers,
        "by_subject": dept_subject_rows,
        "by_teacher": dept_teacher_rows,
    }

    # --- subject_stats ---
    subj_count = defaultdict(int)
    for r in rows:
        subj_count[r.subject_name or (r.subject.name if r.subject else "—")] += 1
    by_subject = [[k, v] for k, v in sorted(subj_count.items(), key=lambda x: x[1], reverse=True)[:15]]

    # --- class_stats ---
    cls_count = defaultdict(int)
    for r in rows:
        key = r.school_class.name if r.school_class else (r.class_study_text or r.class_participation_text or "—")
        cls_count[key] += 1
    by_class = sorted(cls_count.items(), key=lambda x: x[0])

    # --- yearly_comparison via GROUP BY ---
    comparison = _yearly_comparison_sql()

    return summary, by_teacher, by_department, by_subject, by_class, comparison


def _yearly_comparison_sql():
    """Use SQL GROUP BY instead of loading all rows per year."""
    years = AcademicYear.query.order_by(AcademicYear.start_date.asc().nullslast(), AcademicYear.name.asc()).all()
    if not years:
        return []

    year_ids = [y.id for y in years]
    year_names = {y.id: y.name for y in years}

    # Single query: group by academic_year_id, get counts
    base = (
        db.session.query(
            OlympiadResult.academic_year_id,
            func.count(OlympiadResult.id).label("total"),
            func.count(func.distinct(OlympiadResult.child_id)).label("unique_children"),
            OlympiadResult.status,
        )
        .filter(
            OlympiadResult.is_archived.is_(False),
            OlympiadResult.academic_year_id.in_(year_ids),
        )
        .group_by(OlympiadResult.academic_year_id, OlympiadResult.status)
        .all()
    )

    # Aggregate per year
    year_data = {yid: {"total": 0, "unique_children": 0, "winners": 0, "prizers": 0} for yid in year_ids}
    # unique_children needs a separate approach since we group by status too
    # Let's do a simpler two-query approach
    totals = (
        db.session.query(
            OlympiadResult.academic_year_id,
            func.count(OlympiadResult.id).label("total"),
            func.count(func.distinct(OlympiadResult.child_id)).label("unique_children"),
        )
        .filter(
            OlympiadResult.is_archived.is_(False),
            OlympiadResult.academic_year_id.in_(year_ids),
        )
        .group_by(OlympiadResult.academic_year_id)
        .all()
    )
    for row in totals:
        if row.academic_year_id in year_data:
            year_data[row.academic_year_id]["total"] = row.total
            year_data[row.academic_year_id]["unique_children"] = row.unique_children

    # Winners/prizers — load status strings per year (lighter than loading all rows)
    status_counts = (
        db.session.query(
            OlympiadResult.academic_year_id,
            func.lower(func.trim(func.coalesce(OlympiadResult.status, ''))),
            func.count(OlympiadResult.id),
        )
        .filter(
            OlympiadResult.is_archived.is_(False),
            OlympiadResult.academic_year_id.in_(year_ids),
        )
        .group_by(
            OlympiadResult.academic_year_id,
            func.lower(func.trim(func.coalesce(OlympiadResult.status, ''))),
        )
        .all()
    )
    for yid, status_lower, cnt in status_counts:
        if yid not in year_data:
            continue
        if status_lower == "победитель":
            year_data[yid]["winners"] += cnt
        if status_lower and "приз" in status_lower:
            year_data[yid]["prizers"] += cnt

    result = []
    for y in years:
        d = year_data.get(y.id, {"total": 0, "unique_children": 0, "winners": 0, "prizers": 0})
        result.append({
            "year_name": y.name,
            "total_results": d["total"],
            "unique_children": d["unique_children"],
            "winners": d["winners"],
            "prizers": d["prizers"],
            "participants": d["total"] - d["winners"] - d["prizers"],
        })
    return result


# Keep old signatures for backward compatibility (used by other code)
def teacher_stats(academic_year_id=None, teacher_id=None):
    rows = _load_rows_eager(academic_year_id)
    if teacher_id:
        rows = [r for r in rows if r.teacher_id == teacher_id]
    by_teacher = defaultdict(int)
    for r in rows:
        key = r.teacher.fio if r.teacher else "Не определён"
        by_teacher[key] += 1
    return [[k, v] for k, v in sorted(by_teacher.items(), key=lambda x: x[1], reverse=True)[:15]]


def department_stats(academic_year_id=None, department_id=None):
    q = _base_query(academic_year_id)
    if department_id:
        q = q.filter(OlympiadResult.department_id == department_id)
    rows = q.options(joinedload(OlympiadResult.teacher), joinedload(OlympiadResult.subject)).all()
    by_subject = defaultdict(int)
    by_teacher = defaultdict(lambda: {"name": "", "subjects": set(), "total": 0, "winners": 0, "prizers": 0})
    winners = prizers = 0
    for r in rows:
        subj = r.subject_name or (r.subject.name if r.subject else "—")
        by_subject[subj] += 1
        tname = r.teacher.fio if r.teacher else "Не определён"
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
    rows = _load_rows_eager(academic_year_id)
    by_subject = defaultdict(int)
    for r in rows:
        by_subject[r.subject_name or (r.subject.name if r.subject else "—")] += 1
    return [[k, v] for k, v in sorted(by_subject.items(), key=lambda x: x[1], reverse=True)[:15]]


def class_stats(academic_year_id=None):
    rows = _load_rows_eager(academic_year_id)
    by_class = defaultdict(int)
    for r in rows:
        key = r.school_class.name if r.school_class else (r.class_study_text or r.class_participation_text or "—")
        by_class[key] += 1
    return sorted(by_class.items(), key=lambda x: x[0])


def yearly_comparison():
    return _yearly_comparison_sql()
