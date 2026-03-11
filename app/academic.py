from collections import defaultdict
from datetime import datetime

from flask import Blueprint, render_template, request
from flask_login import login_required

from .models import AcademicYear, ControlWork, ControlWorkAssignment, ControlWorkResult, SchoolClass, Subject, User
from .permissions import has_permission

academic_bp = Blueprint("academic", __name__)


def _current_year():
    return AcademicYear.query.filter_by(is_current=True).first()


def _safe_avg(values, digits=1):
    vals = [float(v) for v in values if v is not None]
    return round(sum(vals) / len(vals), digits) if vals else None


def _performance_label(value):
    if value is None:
        return "Нет данных"
    if value < 50:
        return "Критично"
    if value < 65:
        return "Риск"
    if value < 80:
        return "Стабильно"
    return "Высокий результат"


def _filters():
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    subjects = Subject.query.order_by(Subject.name.asc()).all()
    current_year = _current_year()
    selected_year_id = request.args.get("academic_year_id", type=int) or (current_year.id if current_year else None)
    selected_subject_id = request.args.get("subject_id", type=int)
    selected_grade = request.args.get("grade", type=int)
    selected_class_id = request.args.get("class_id", type=int)
    return {
        "years": years,
        "subjects": subjects,
        "selected_year_id": selected_year_id,
        "selected_subject_id": selected_subject_id,
        "selected_grade": selected_grade,
        "selected_class_id": selected_class_id,
    }


def _base_rows(selected_year_id=None, selected_subject_id=None, selected_grade=None, selected_class_id=None):
    query = (
        ControlWorkResult.query
        .join(ControlWorkAssignment, ControlWorkAssignment.id == ControlWorkResult.assignment_id)
        .join(ControlWork, ControlWork.id == ControlWorkResult.control_work_id)
        .join(SchoolClass, SchoolClass.id == ControlWorkResult.school_class_id)
        .filter(ControlWorkResult.is_archived.is_(False))
    )
    if selected_year_id:
        query = query.filter(ControlWork.academic_year_id == selected_year_id)
    if selected_subject_id:
        query = query.filter(ControlWork.subject_id == selected_subject_id)
    if selected_grade:
        query = query.filter(SchoolClass.grade == selected_grade)
    if selected_class_id:
        query = query.filter(SchoolClass.id == selected_class_id)
    return query.order_by(ControlWork.work_date.asc().nullslast(), ControlWork.created_at.asc()).all()


def build_academic_dataset(selected_year_id=None, selected_subject_id=None, selected_grade=None, selected_class_id=None):
    rows = _base_rows(selected_year_id, selected_subject_id, selected_grade, selected_class_id)

    works = {}
    subject_stats = defaultdict(lambda: {"subject_name": "—", "percents": [], "marks": [], "results": 0, "classes": set()})
    class_stats = defaultdict(lambda: {"class_name": "—", "percents": [], "marks": [], "results": 0, "subjects": set()})
    pair_stats = defaultdict(lambda: {"class_name": "—", "subject_name": "—", "percents": [], "marks": [], "results": 0})
    child_stats = defaultdict(lambda: {"child_name": "—", "class_name": "—", "subject_names": set(), "percents": [], "marks": [], "results": 0, "low_count": 0, "last_work_date": None})
    dynamics = defaultdict(lambda: {"label": "—", "percents": [], "results": 0})

    mark_counts = {2: 0, 3: 0, 4: 0, 5: 0}
    all_percents = []

    for result in rows:
        work = result.assignment.control_work if result.assignment else None
        assignment = result.assignment
        school_class = result.school_class or (assignment.school_class if assignment else None)
        child = result.child
        if not work or not school_class or not child:
            continue

        works[work.id] = work
        percent = float(result.percent) if result.percent is not None else None
        mark = result.mark
        if percent is not None:
            all_percents.append(percent)
        if mark in mark_counts:
            mark_counts[mark] += 1

        subject_key = work.subject_id or 0
        subject_stats[subject_key]["subject_name"] = work.subject_name
        subject_stats[subject_key]["results"] += 1
        subject_stats[subject_key]["classes"].add(school_class.name)
        if percent is not None:
            subject_stats[subject_key]["percents"].append(percent)
        if mark is not None:
            subject_stats[subject_key]["marks"].append(mark)

        class_key = school_class.id
        class_stats[class_key]["class_name"] = school_class.name
        class_stats[class_key]["results"] += 1
        class_stats[class_key]["subjects"].add(work.subject_name)
        if percent is not None:
            class_stats[class_key]["percents"].append(percent)
        if mark is not None:
            class_stats[class_key]["marks"].append(mark)

        pair_key = (school_class.id, work.subject_id or 0)
        pair_stats[pair_key]["class_name"] = school_class.name
        pair_stats[pair_key]["subject_name"] = work.subject_name
        pair_stats[pair_key]["results"] += 1
        if percent is not None:
            pair_stats[pair_key]["percents"].append(percent)
        if mark is not None:
            pair_stats[pair_key]["marks"].append(mark)

        child_key = child.id
        child_stats[child_key]["child_name"] = child.fio
        child_stats[child_key]["class_name"] = school_class.name
        child_stats[child_key]["subject_names"].add(work.subject_name)
        child_stats[child_key]["results"] += 1
        if percent is not None:
            child_stats[child_key]["percents"].append(percent)
        if mark is not None:
            child_stats[child_key]["marks"].append(mark)
        if percent is not None and percent < 50 or mark == 2:
            child_stats[child_key]["low_count"] += 1
        if work.work_date and (child_stats[child_key]["last_work_date"] is None or work.work_date > child_stats[child_key]["last_work_date"]):
            child_stats[child_key]["last_work_date"] = work.work_date

        if work.work_date:
            label = f"{work.work_date.strftime('%m.%Y')} · {work.subject_name}"
        else:
            label = f"Без даты · {work.subject_name}"
        dynamics[label]["label"] = label
        dynamics[label]["results"] += 1
        if percent is not None:
            dynamics[label]["percents"].append(percent)

    def _finalize(rows_dict, text_fields=None):
        out = []
        for row in rows_dict.values():
            marks = row.get("marks", [])
            avg_percent = _safe_avg(row.get("percents", []), digits=1)
            quality = round(((sum(1 for m in marks if m in [4, 5]) / len(marks)) * 100), 1) if marks else None
            success = round(((sum(1 for m in marks if m in [3, 4, 5]) / len(marks)) * 100), 1) if marks else None
            item = dict(row)
            item["avg_percent"] = avg_percent
            item["avg_mark"] = _safe_avg(marks, digits=2)
            item["quality"] = quality
            item["success"] = success
            item["label"] = _performance_label(avg_percent)
            if text_fields:
                for src, dest in text_fields.items():
                    item[dest] = ", ".join(sorted(x for x in item.get(src, set()) if x)) or "—"
            out.append(item)
        return out

    subject_rows = sorted(_finalize(subject_stats, {"classes": "classes_text"}), key=lambda x: ((x["avg_percent"] is None), -(x["avg_percent"] or 0), x["subject_name"]))
    class_rows = sorted(_finalize(class_stats, {"subjects": "subjects_text"}), key=lambda x: ((x["avg_percent"] is None), -(x["avg_percent"] or 0), x["class_name"]))
    pair_rows = sorted(_finalize(pair_stats), key=lambda x: ((x["avg_percent"] is None), -(x["avg_percent"] or 0), x["class_name"], x["subject_name"]))
    child_rows = sorted(_finalize(child_stats, {"subject_names": "subjects_text"}), key=lambda x: (-x.get("low_count", 0), (x["avg_percent"] is None), x["avg_percent"] or 999, x["child_name"]))

    low_results_rows = []
    for item in child_rows:
        avg_percent = item.get("avg_percent")
        if item.get("low_count", 0) > 0 or (avg_percent is not None and avg_percent < 60):
            low_results_rows.append(item)

    dynamics_rows = []
    for row in dynamics.values():
        avg_percent = _safe_avg(row["percents"], digits=1)
        dynamics_rows.append({
            "label": row["label"],
            "results": row["results"],
            "avg_percent": avg_percent,
            "status": _performance_label(avg_percent),
        })
    dynamics_rows = sorted(dynamics_rows, key=lambda x: x["label"])

    results_count = sum(mark_counts.values())
    summary = {
        "works_count": len(works),
        "results_count": len(rows),
        "avg_percent": _safe_avg(all_percents, digits=1),
        "quality": round(((mark_counts[4] + mark_counts[5]) / results_count) * 100, 1) if results_count else None,
        "success": round(((mark_counts[3] + mark_counts[4] + mark_counts[5]) / results_count) * 100, 1) if results_count else None,
        "low_results_count": len(low_results_rows),
        "mark_counts": mark_counts,
    }

    return {
        "summary": summary,
        "subject_rows": subject_rows[:50],
        "class_rows": class_rows[:50],
        "pair_rows": pair_rows[:100],
        "low_results_rows": low_results_rows[:100],
        "dynamics_rows": dynamics_rows[-18:],
    }


def _class_choices(selected_year_id=None):
    query = SchoolClass.query.order_by(SchoolClass.grade.asc().nullslast(), SchoolClass.name.asc())
    if selected_year_id:
        query = query.filter(SchoolClass.academic_year_id == selected_year_id)
    classes = query.all()
    parallels = sorted({c.grade for c in classes if c.grade is not None})
    return classes, parallels


@academic_bp.route('/academic/dashboard')
@login_required
def dashboard():
    if not has_permission('control_works_view'):
        return render_template('academic_dashboard.html', dataset={"summary": {"works_count": 0, "results_count": 0, "avg_percent": None, "quality": None, "success": None, "low_results_count": 0, "mark_counts": {2:0,3:0,4:0,5:0}}, "subject_rows": [], "class_rows": [], "pair_rows": [], "low_results_rows": [], "dynamics_rows": []}, years=[], subjects=[], classes=[], parallels=[], selected_year_id=None, selected_subject_id=None, selected_grade=None, selected_class_id=None)
    filters = _filters()
    classes, parallels = _class_choices(filters["selected_year_id"])
    dataset = build_academic_dataset(filters["selected_year_id"], filters["selected_subject_id"], filters["selected_grade"], filters["selected_class_id"])
    return render_template('academic_dashboard.html', dataset=dataset, classes=classes, parallels=parallels, **filters)


@academic_bp.route('/academic/low-results')
@login_required
def low_results():
    if not has_permission('control_works_view'):
        return render_template('academic_low_results.html', dataset={"low_results_rows": []}, years=[], subjects=[], classes=[], parallels=[], selected_year_id=None, selected_subject_id=None, selected_grade=None, selected_class_id=None)
    filters = _filters()
    classes, parallels = _class_choices(filters["selected_year_id"])
    dataset = build_academic_dataset(filters["selected_year_id"], filters["selected_subject_id"], filters["selected_grade"], filters["selected_class_id"])
    return render_template('academic_low_results.html', dataset=dataset, classes=classes, parallels=parallels, **filters)


@academic_bp.route('/academic/dynamics')
@login_required
def dynamics_view():
    if not has_permission('control_works_view'):
        return render_template('academic_dynamics.html', dataset={"dynamics_rows": [], "pair_rows": []}, years=[], subjects=[], classes=[], parallels=[], selected_year_id=None, selected_subject_id=None, selected_grade=None, selected_class_id=None)
    filters = _filters()
    classes, parallels = _class_choices(filters["selected_year_id"])
    dataset = build_academic_dataset(filters["selected_year_id"], filters["selected_subject_id"], filters["selected_grade"], filters["selected_class_id"])
    return render_template('academic_dynamics.html', dataset=dataset, classes=classes, parallels=parallels, **filters)
