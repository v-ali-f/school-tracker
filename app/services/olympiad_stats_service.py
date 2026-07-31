from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from ..core.extensions import db
from ..models import AcademicYear, OlympiadResult
from .olympiad_normalization import (
    STAGE_LABELS,
    STATUS_LABELS,
    normalize_olympiad_stage,
    normalize_olympiad_status,
    stage_label,
    status_label,
)
from .olympiad_import_service import ensure_olympiad_result_schema

STAGE_ORDER = ["school", "municipal", "regional", "final", "unknown"]
STATUS_ORDER = ["winner", "prize", "participant", "out_of_competition", "annulled", "unknown"]


def _row_stage_group(row):
    return getattr(row, "stage_group", None) or normalize_olympiad_stage(getattr(row, "stage", None))


def _row_status_group(row):
    return getattr(row, "status_group", None) or normalize_olympiad_status(getattr(row, "status_original", None) or getattr(row, "status", None), getattr(row, "reason", None))


def _base_query(academic_year_id=None, stage_group=None, status_group=None, department_id=None, teacher_id=None, year_ids=None):
    ensure_olympiad_result_schema()
    q = OlympiadResult.query.filter(OlympiadResult.is_archived.is_(False))
    if academic_year_id:
        q = q.filter(OlympiadResult.academic_year_id == academic_year_id)
    if year_ids:
        q = q.filter(OlympiadResult.academic_year_id.in_(year_ids))
    if stage_group:
        q = q.filter(
            db.or_(
                OlympiadResult.stage_group == stage_group,
                db.and_(OlympiadResult.stage_group.is_(None), OlympiadResult.stage.ilike(f"%{STAGE_LABELS.get(stage_group, stage_group).split()[0]}%")),
            )
        )
    if status_group:
        q = q.filter(OlympiadResult.status_group == status_group)
    if department_id:
        q = q.filter(OlympiadResult.department_id == department_id)
    if teacher_id:
        q = q.filter(OlympiadResult.teacher_id == teacher_id)
    return q


def _load_rows_eager(academic_year_id=None, stage_group=None, status_group=None, teacher_id=None, department_id=None, year_ids=None):
    return (
        _base_query(academic_year_id, stage_group, status_group, department_id, teacher_id, year_ids)
        .options(
            joinedload(OlympiadResult.teacher),
            joinedload(OlympiadResult.subject),
            joinedload(OlympiadResult.school_class),
            joinedload(OlympiadResult.department),
            joinedload(OlympiadResult.academic_year),
        )
        .all()
    )


def _empty_stage_row(code):
    return {
        "stage_group": code,
        "stage_label": stage_label(code),
        "stage_badge": {"school": "ШЭ", "municipal": "МЭ", "regional": "РЭ", "final": "ЗЭ", "unknown": "?"}.get(code, "?"),
        "total": 0,
        "counted": 0,
        "unique_children": 0,
        "winners": 0,
        "prizers": 0,
        "participants": 0,
        "annulled": 0,
        "out_of_competition": 0,
        "unknown": 0,
    }


def _compute_dashboard(rows):
    winners = prizers = annulled = out_of_competition = unknown = participant = counted = 0
    by_stage = {code: _empty_stage_row(code) for code in STAGE_ORDER}
    by_status = {code: 0 for code in STATUS_ORDER}
    child_ids = set()
    stage_child_ids = defaultdict(set)

    for r in rows:
        sg = _row_stage_group(r)
        stg = _row_status_group(r)
        by_status[stg] = by_status.get(stg, 0) + 1
        if sg not in by_stage:
            by_stage[sg] = _empty_stage_row(sg)
        row = by_stage[sg]
        row["total"] += 1
        if r.child_id:
            child_ids.add(r.child_id)
            stage_child_ids[sg].add(r.child_id)
        if stg == "winner":
            winners += 1
            row["winners"] += 1
            counted += 1
            row["counted"] += 1
        elif stg == "prize":
            prizers += 1
            row["prizers"] += 1
            counted += 1
            row["counted"] += 1
        elif stg == "annulled":
            annulled += 1
            row["annulled"] += 1
        elif stg == "out_of_competition":
            out_of_competition += 1
            row["out_of_competition"] += 1
        elif stg == "participant":
            participant += 1
            row["participants"] += 1
            counted += 1
            row["counted"] += 1
        else:
            unknown += 1
            row["unknown"] += 1
            counted += 1
            row["counted"] += 1

    for sg, ids in stage_child_ids.items():
        if sg in by_stage:
            by_stage[sg]["unique_children"] = len(ids)

    stages_table = [by_stage[code] for code in STAGE_ORDER if code in by_stage]
    return {
        "total_results": len(rows),
        "total": len(rows),
        "counted_results": counted,
        "unique_children": len(child_ids),
        "winners": winners,
        "prizers": prizers,
        "participants": participant,
        "annulled": annulled,
        "out_of_competition": out_of_competition,
        "unknown": unknown,
        "by_stage": [[r["stage_label"], r["total"]] for r in stages_table],
        "by_status": [[STATUS_LABELS.get(k, k), by_status.get(k, 0)] for k in STATUS_ORDER if by_status.get(k, 0)],
        "stage_summary": stages_table,
    }


def dashboard_stats(academic_year_id=None):
    return _compute_dashboard(_load_rows_eager(academic_year_id))


def _year_ids_from_range(year_from_id=None, year_to_id=None):
    years = AcademicYear.query.order_by(AcademicYear.start_date.asc().nullslast(), AcademicYear.name.asc()).all()
    if not year_from_id and not year_to_id:
        return None
    ids = [y.id for y in years]
    try:
        start = ids.index(year_from_id) if year_from_id in ids else 0
        end = ids.index(year_to_id) if year_to_id in ids else len(ids) - 1
    except Exception:
        return None
    if start > end:
        start, end = end, start
    return ids[start:end + 1]


def all_analytics(academic_year_id=None, teacher_id=None, department_id=None, stage_group=None, status_group=None, year_from_id=None, year_to_id=None):
    year_ids = None if academic_year_id else _year_ids_from_range(year_from_id, year_to_id)
    rows = _load_rows_eager(academic_year_id, stage_group, status_group, teacher_id, department_id, year_ids)
    summary = _compute_dashboard(rows)

    by_teacher_count = defaultdict(int)
    for r in rows:
        key = r.teacher.fio if r.teacher else "Не определён"
        by_teacher_count[key] += 1
    by_teacher = [[k, v] for k, v in sorted(by_teacher_count.items(), key=lambda x: x[1], reverse=True)[:15]]

    dept_by_subject = defaultdict(int)
    dept_by_teacher = defaultdict(lambda: {"name": "", "subjects": set(), "total": 0, "winners": 0, "prizers": 0, "annulled": 0})
    dept_child_ids = set()
    for r in rows:
        subj = r.resolved_subject_name
        dept_by_subject[subj] += 1
        tname = r.teacher.fio if r.teacher else "Не определён"
        item = dept_by_teacher[tname]
        item["name"] = tname
        item["subjects"].add(subj)
        item["total"] += 1
        stg = _row_status_group(r)
        if stg == "winner":
            item["winners"] += 1
        elif stg == "prize":
            item["prizers"] += 1
        elif stg == "annulled":
            item["annulled"] += 1
        if r.child_id:
            dept_child_ids.add(r.child_id)
    dept_teacher_rows = sorted(
        [{"name": it["name"], "subject": ", ".join(sorted(it["subjects"])), "total": it["total"], "winners": it["winners"], "prizers": it["prizers"], "annulled": it["annulled"]}
         for it in dept_by_teacher.values()],
        key=lambda x: (-x["total"], x["name"]),
    )
    dept_subject_rows = [{"name": k, "count": v} for k, v in sorted(dept_by_subject.items(), key=lambda x: (-x[1], x[0]))]
    by_department = {**summary, "by_subject": dept_subject_rows, "by_teacher": dept_teacher_rows}

    subj_count = defaultdict(int)
    for r in rows:
        subj_count[r.resolved_subject_name] += 1
    by_subject = [[k, v] for k, v in sorted(subj_count.items(), key=lambda x: x[1], reverse=True)[:15]]

    cls_count = defaultdict(int)
    for r in rows:
        key = r.school_class.name if r.school_class else (r.class_study_text or r.class_participation_text or "—")
        cls_count[key] += 1
    by_class = sorted(cls_count.items(), key=lambda x: x[0])

    comparison = _yearly_comparison(rows)
    movement = _stage_movement(rows)
    yearly_stage_rows = _yearly_stage_rows(rows)
    return summary, by_teacher, by_department, by_subject, by_class, comparison, movement, yearly_stage_rows


def _yearly_comparison(rows=None):
    if rows is None:
        rows = _load_rows_eager()
    grouped = defaultdict(list)
    for r in rows:
        name = r.academic_year.name if r.academic_year else "Без года"
        grouped[name].append(r)
    result = []
    prev = None
    for year_name in sorted(grouped.keys()):
        d = _compute_dashboard(grouped[year_name])
        item = {
            "year_name": year_name,
            "total_results": d["total_results"],
            "counted_results": d["counted_results"],
            "unique_children": d["unique_children"],
            "winners": d["winners"],
            "prizers": d["prizers"],
            "participants": d["participants"],
            "annulled": d["annulled"],
            "delta_unique_children": None if prev is None else d["unique_children"] - prev["unique_children"],
            "delta_winners": None if prev is None else d["winners"] - prev["winners"],
            "delta_prizers": None if prev is None else d["prizers"] - prev["prizers"],
        }
        result.append(item)
        prev = d
    return result


def _stage_movement(rows):
    child_stages = defaultdict(set)
    for r in rows:
        if r.child_id:
            child_stages[r.child_id].add(_row_stage_group(r))
    return {
        "school": sum(1 for stages in child_stages.values() if "school" in stages),
        "municipal": sum(1 for stages in child_stages.values() if "municipal" in stages),
        "regional": sum(1 for stages in child_stages.values() if "regional" in stages),
        "final": sum(1 for stages in child_stages.values() if "final" in stages),
        "school_municipal": sum(1 for stages in child_stages.values() if {"school", "municipal"}.issubset(stages)),
        "municipal_regional": sum(1 for stages in child_stages.values() if {"municipal", "regional"}.issubset(stages)),
        "regional_final": sum(1 for stages in child_stages.values() if {"regional", "final"}.issubset(stages)),
    }


def _yearly_stage_rows(rows):
    bucket = defaultdict(list)
    for r in rows:
        year = r.academic_year.name if r.academic_year else "Без года"
        bucket[(year, _row_stage_group(r))].append(r)
    out = []
    for (year, sg), items in sorted(bucket.items()):
        d = _compute_dashboard(items)
        out.append({"year_name": year, "stage_group": sg, "stage_label": stage_label(sg), **d})
    return out


def teacher_stats(academic_year_id=None, teacher_id=None):
    rows = _load_rows_eager(academic_year_id, teacher_id=teacher_id)
    by_teacher = defaultdict(int)
    for r in rows:
        by_teacher[r.teacher.fio if r.teacher else "Не определён"] += 1
    return [[k, v] for k, v in sorted(by_teacher.items(), key=lambda x: x[1], reverse=True)[:15]]


def department_stats(academic_year_id=None, department_id=None):
    rows = _load_rows_eager(academic_year_id, department_id=department_id)
    summary, _, dept, _, _, _, _, _ = all_analytics(academic_year_id=academic_year_id, department_id=department_id)
    return dept


def subject_stats(academic_year_id=None):
    rows = _load_rows_eager(academic_year_id)
    by_subject = defaultdict(int)
    for r in rows:
        by_subject[r.resolved_subject_name] += 1
    return [[k, v] for k, v in sorted(by_subject.items(), key=lambda x: x[1], reverse=True)[:15]]


def class_stats(academic_year_id=None):
    rows = _load_rows_eager(academic_year_id)
    by_class = defaultdict(int)
    for r in rows:
        key = r.school_class.name if r.school_class else (r.class_study_text or r.class_participation_text or "—")
        by_class[key] += 1
    return sorted(by_class.items(), key=lambda x: x[0])


def yearly_comparison():
    return _yearly_comparison()
