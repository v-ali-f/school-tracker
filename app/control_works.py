from datetime import datetime
from io import BytesIO
from collections import defaultdict

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, jsonify
from flask_login import login_required, current_user
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from app.core.extensions import db
from .models import (
    ControlWork, ControlWorkTask, ControlWorkAssignment, ControlWorkResult,
    SchoolClass, User, ChildEnrollment, Child, AcademicYear, Subject, TeacherLoad, DepartmentLeader
)
from .permissions import has_permission

control_bp = Blueprint("control_works", __name__, url_prefix="/control-works")


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _current_year():
    return AcademicYear.query.filter_by(is_current=True).first()


def _fmt_date(value):
    return value.strftime("%d.%m.%Y") if value else "—"


def _safe_avg(values, digits=2):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), digits) if vals else None


def _score_status(percent):
    if percent is None:
        return "Нет данных"
    if percent < 50:
        return "Критично"
    if percent < 65:
        return "Риск"
    if percent < 80:
        return "Стабильно"
    return "Высокий результат"


def _bar_class(percent):
    if percent is None:
        return "bg-secondary"
    if percent < 50:
        return "bg-danger"
    if percent < 65:
        return "bg-warning"
    if percent < 80:
        return "bg-primary"
    return "bg-success"




def _department_ids_for_user(user=None):
    user = user or current_user
    if has_permission("control_works_edit", user=user) or getattr(user, "role", None) == "ADMIN":
        return None
    if getattr(user, "role", None) == "METHODIST":
        dep_ids = sorted({row.department_id for row in DepartmentLeader.query.filter_by(user_id=user.id).all() if row.department_id})
        return dep_ids or None
    return []


def _normalize_class_token(value):
    raw = (value or '').strip().upper()
    if not raw:
        return ''
    translate_map = str.maketrans({
        'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н', 'K': 'К', 'M': 'М',
        'O': 'О', 'P': 'Р', 'T': 'Т', 'X': 'Х', 'Y': 'У'
    })
    raw = raw.translate(translate_map)
    for ch in (' ', '-', '–', '—', '.', '/', '\\'):
        raw = raw.replace(ch, '')
    return raw


def _split_class_tokens(value):
    raw = (value or '')
    if not raw:
        return []
    prepared = raw
    for sep in ('\n', ';', ',', '|'):
        prepared = prepared.replace(sep, ' ')
    parts = [part for part in prepared.split() if part]
    compact = _normalize_class_token(raw)
    tokens = {_normalize_class_token(part) for part in parts if _normalize_class_token(part)}
    if compact:
        tokens.add(compact)
    return list(tokens)


def _teacher_load_candidates(subject_id=None, grade=None, class_name=None, academic_year_id=None, department_ids=None):
    query = TeacherLoad.query.filter(TeacherLoad.is_archived.is_(False))
    if academic_year_id:
        query = query.filter((TeacherLoad.academic_year_id == academic_year_id) | (TeacherLoad.academic_year_id.is_(None)))
    if subject_id:
        query = query.filter(TeacherLoad.subject_id == subject_id)
    if department_ids:
        query = query.filter(TeacherLoad.department_id.in_(department_ids))
    if grade is not None:
        query = query.filter((TeacherLoad.grade == grade) | (TeacherLoad.grade.is_(None)))

    rows = query.all()
    class_token = _normalize_class_token(class_name)
    matched = []
    for row in rows:
        if not row.teacher_id:
            continue

        row_tokens = _split_class_tokens(row.class_name)
        exact_match = False
        partial_match = False

        if class_token:
            if row_tokens:
                exact_match = class_token in row_tokens
                if not exact_match:
                    partial_match = any(class_token in token or token in class_token for token in row_tokens)
                else:
                    partial_match = True
                if not partial_match and row.grade is not None and grade is not None and row.grade != grade:
                    continue
            elif row.grade is not None and grade is not None and row.grade != grade:
                continue

        matched.append((row, exact_match, partial_match))

    unique = {}
    for row, exact_match, partial_match in matched:
        current = unique.get(row.teacher_id)
        rank = 2 if exact_match else (1 if partial_match else 0)
        if current is None or rank > current[1] or (rank == current[1] and float(row.hours or 0) > float(current[0].hours or 0)):
            unique[row.teacher_id] = (row, rank)

    ranked_rows = []
    preferred_teacher_ids = [row.teacher_id for row, rank in unique.values() if rank == 2]
    single_preferred_teacher_id = preferred_teacher_ids[0] if len(preferred_teacher_ids) == 1 else None

    for row, rank in unique.values():
        ranked_rows.append({
            'id': row.teacher_id,
            'name': row.teacher.fio if row.teacher else (row.subject_name or 'Учитель'),
            'hours': float(row.hours or 0),
            'class_name': row.class_name or '',
            'department_id': row.department_id,
            'preferred': bool(single_preferred_teacher_id and row.teacher_id == single_preferred_teacher_id),
            'match_rank': rank,
        })

    if not ranked_rows:
        return ranked_rows

    if not single_preferred_teacher_id and len(ranked_rows) == 1:
        ranked_rows[0]['preferred'] = True

    ranked_rows.sort(key=lambda x: (-x['match_rank'], -x['hours'], x['name']))
    return ranked_rows


def _teacher_options_map(classes, subject_id=None, academic_year_id=None, department_ids=None):
    data = {}
    for c in classes:
        data[c.id] = _teacher_load_candidates(
            subject_id=subject_id,
            grade=c.grade,
            class_name=c.name,
            academic_year_id=academic_year_id,
            department_ids=department_ids,
        )
    return data


def _auto_teacher_by_class(classes, teacher_options_map):
    auto_map = {}
    for c in classes:
        options = teacher_options_map.get(c.id, []) or []
        preferred = next((item for item in options if item.get('preferred')), None)
        if preferred:
            auto_map[c.id] = preferred['id']
        elif len(options) == 1:
            auto_map[c.id] = options[0]['id']
    return auto_map


def _get_archive_filters():
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    subjects = Subject.query.order_by(Subject.name.asc()).all()
    teachers = User.query.order_by(User.last_name.asc(), User.first_name.asc()).all()

    selected_year_id = request.args.get("academic_year_id", type=int)
    selected_subject_id = request.args.get("subject_id", type=int)
    selected_teacher_id = request.args.get("teacher_id", type=int)
    if not has_permission("control_works_edit"):
        selected_teacher_id = current_user.id

    return {
        "years": years,
        "subjects": subjects,
        "teachers": teachers,
        "selected_year_id": selected_year_id,
        "selected_subject_id": selected_subject_id,
        "selected_teacher_id": selected_teacher_id,
    }


def _archive_works_query(filters):
    query = ControlWork.query
    if filters["selected_year_id"]:
        query = query.filter(ControlWork.academic_year_id == filters["selected_year_id"])
    if filters["selected_subject_id"]:
        query = query.filter(ControlWork.subject_id == filters["selected_subject_id"])
    if filters["selected_teacher_id"]:
        query = query.join(ControlWorkAssignment, ControlWorkAssignment.control_work_id == ControlWork.id).filter(ControlWorkAssignment.teacher_id == filters["selected_teacher_id"])
    return query.distinct().order_by(ControlWork.work_date.desc().nullslast(), ControlWork.created_at.desc())


def _build_control_work_report(work, teacher_id=None):
    tasks = sorted((work.tasks or []), key=lambda x: x.task_number or 0)
    class_rows = []
    all_results = []
    mark_counts = {2: 0, 3: 0, 4: 0, 5: 0}
    topic_stats = {}

    for assignment in work.assignments or []:
        if teacher_id and assignment.teacher_id != teacher_id:
            continue
        if not has_permission("control_works_edit") and teacher_id is None and assignment.teacher_id != current_user.id:
            continue

        results = ControlWorkResult.query.filter_by(control_work_id=work.id, assignment_id=assignment.id, school_class_id=assignment.school_class_id).all()
        all_results.extend(results)
        marks = [r.mark for r in results if r.mark is not None]
        avg_mark = _safe_avg(marks)
        avg_percent = _safe_avg([r.percent for r in results])
        for m in marks:
            if m in mark_counts:
                mark_counts[m] += 1
        class_rows.append({
            "assignment": assignment,
            "results_count": len(results),
            "avg_mark": avg_mark,
            "avg_percent": avg_percent,
            "marks": {m: sum(1 for x in marks if x == m) for m in [2, 3, 4, 5]},
            "status": _score_status(avg_percent),
            "bar_class": _bar_class(avg_percent),
        })

    task_rows = []
    results_with_scores = [r for r in all_results if r.total_score is not None]
    max_total = sum(t.max_score or 0 for t in tasks)
    for task in tasks:
        avg_score = None
        percent = None
        if results_with_scores and max_total > 0 and (task.max_score or 0) > 0:
            est_scores = []
            for r in results_with_scores:
                est_scores.append((r.total_score or 0) * (task.max_score or 0) / max_total)
            avg_score = round(sum(est_scores) / len(est_scores), 2) if est_scores else None
            percent = round((avg_score / (task.max_score or 1)) * 100, 2) if avg_score is not None else None
        task_rows.append({
            "task": task,
            "avg_score": avg_score,
            "percent": percent,
            "status": _score_status(percent),
            "bar_class": _bar_class(percent),
        })
        topic_key = (task.topic or "—").strip()
        if topic_key not in topic_stats:
            topic_stats[topic_key] = {"sum": 0, "count": 0}
        if percent is not None:
            topic_stats[topic_key]["sum"] += percent
            topic_stats[topic_key]["count"] += 1

    topic_rows = []
    for topic, data in topic_stats.items():
        avg_percent = round(data["sum"] / data["count"], 2) if data["count"] else None
        topic_rows.append({
            "topic": topic,
            "percent": avg_percent,
            "status": _score_status(avg_percent),
            "bar_class": _bar_class(avg_percent),
        })
    topic_rows.sort(key=lambda x: (x["percent"] is None, x["percent"] or 0))

    marks = [r.mark for r in all_results if r.mark is not None]
    percents = [r.percent for r in all_results if r.percent is not None]
    class_rows.sort(key=lambda x: (x["avg_percent"] is None, -(x["avg_percent"] or 0)))

    report = {
        "classes": len(class_rows),
        "results": len(all_results),
        "avg_mark": _safe_avg(marks),
        "avg_percent": _safe_avg(percents),
        "status": _score_status(_safe_avg(percents)),
        "bar_class": _bar_class(_safe_avg(percents)),
    }
    problem_topics = [r for r in topic_rows if r["status"] in ["Критично", "Риск"]]
    return {
        "work": work,
        "class_rows": class_rows,
        "report": report,
        "task_rows": task_rows,
        "topic_rows": topic_rows,
        "mark_counts": mark_counts,
        "problem_topics": problem_topics,
    }


def _build_archive_dataset(filters):
    works = _archive_works_query(filters).all()
    teacher_groups = defaultdict(lambda: {"teacher": None, "works": [], "avg_percent": None, "results": 0})
    subject_groups = defaultdict(lambda: {"subject": None, "works": [], "avg_percent": None, "results": 0})
    year_groups = defaultdict(lambda: {"year": None, "works": [], "avg_percent": None, "results": 0, "avg_mark": None})
    work_rows = []

    for work in works:
        report_pack = _build_control_work_report(work, teacher_id=filters["selected_teacher_id"] if not has_permission("control_works_edit") else filters["selected_teacher_id"])
        report = report_pack["report"]
        teacher_names = sorted({a.teacher.fio for a in (work.assignments or []) if a.teacher and (not filters["selected_teacher_id"] or a.teacher_id == filters["selected_teacher_id"])})
        subject_name = work.subject_name
        year_name = work.academic_year.name if work.academic_year else "Без года"
        row = {
            "id": work.id,
            "work_date": work.work_date,
            "work_date_text": _fmt_date(work.work_date),
            "year_name": year_name,
            "subject_name": subject_name,
            "theme": work.theme,
            "teachers_text": ", ".join(teacher_names) if teacher_names else "—",
            "avg_percent": report["avg_percent"],
            "avg_mark": report["avg_mark"],
            "results": report["results"],
            "classes": report["classes"],
            "status": report["status"],
            "bar_class": report["bar_class"],
        }
        work_rows.append(row)

        for a in (work.assignments or []):
            if not a.teacher:
                continue
            if filters["selected_teacher_id"] and a.teacher_id != filters["selected_teacher_id"]:
                continue
            g = teacher_groups[a.teacher_id]
            g["teacher"] = a.teacher
            g["works"].append(row)

        sg = subject_groups[work.subject_id]
        sg["subject"] = work.subject_ref
        sg["works"].append(row)

        ykey = work.academic_year_id or 0
        yg = year_groups[ykey]
        yg["year"] = work.academic_year
        yg["works"].append(row)

    for group in teacher_groups.values():
        group["avg_percent"] = _safe_avg([w["avg_percent"] for w in group["works"]])
        group["results"] = sum(w["results"] or 0 for w in group["works"])
        group["bar_class"] = _bar_class(group["avg_percent"])
        group["status"] = _score_status(group["avg_percent"])

    for group in subject_groups.values():
        group["avg_percent"] = _safe_avg([w["avg_percent"] for w in group["works"]])
        group["results"] = sum(w["results"] or 0 for w in group["works"])
        group["bar_class"] = _bar_class(group["avg_percent"])
        group["status"] = _score_status(group["avg_percent"])

    for group in year_groups.values():
        group["avg_percent"] = _safe_avg([w["avg_percent"] for w in group["works"]])
        group["avg_mark"] = _safe_avg([w["avg_mark"] for w in group["works"]])
        group["results"] = sum(w["results"] or 0 for w in group["works"])
        group["bar_class"] = _bar_class(group["avg_percent"])
        group["status"] = _score_status(group["avg_percent"])

    summary = {
        "works_count": len(work_rows),
        "results_count": sum(row["results"] or 0 for row in work_rows),
        "avg_percent": _safe_avg([row["avg_percent"] for row in work_rows]),
        "avg_mark": _safe_avg([row["avg_mark"] for row in work_rows]),
        "bar_class": _bar_class(_safe_avg([row["avg_percent"] for row in work_rows])),
        "status": _score_status(_safe_avg([row["avg_percent"] for row in work_rows])),
    }

    return {
        "works": work_rows,
        "teacher_groups": sorted(teacher_groups.values(), key=lambda x: ((x["teacher"].fio if x["teacher"] else ""))),
        "subject_groups": sorted(subject_groups.values(), key=lambda x: ((x["subject"].name if x["subject"] else ""))),
        "year_groups": sorted(year_groups.values(), key=lambda x: ((x["year"].start_date if x["year"] and x["year"].start_date else datetime.min.date())), reverse=True),
        "summary": summary,
    }


def _make_archive_excel(filters, dataset):
    wb = Workbook()
    ws = wb.active
    ws.title = "Архив контрольных"
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    bold = Font(bold=True)

    ws.append(["Учебный год", "Дата", "Предмет", "Тема", "Учителя", "Классов", "Результатов", "Средний %", "Средняя отметка", "Статус"])
    for cell in ws[1]:
        cell.font = bold
        cell.fill = header_fill
    for row in dataset["works"]:
        ws.append([row["year_name"], row["work_date_text"], row["subject_name"], row["theme"], row["teachers_text"], row["classes"], row["results"], row["avg_percent"], row["avg_mark"], row["status"]])
    for col in ["A","B","C","D","E","F","G","H","I","J"]:
        ws.column_dimensions[col].width = 18
    ws.column_dimensions["D"].width = 36
    ws.column_dimensions["E"].width = 28

    ws2 = wb.create_sheet("По учителям")
    ws2.append(["Учитель", "Контрольных", "Результатов", "Средний %", "Статус"])
    for cell in ws2[1]:
        cell.font = bold
        cell.fill = header_fill
    for g in dataset["teacher_groups"]:
        ws2.append([g["teacher"].fio if g["teacher"] else "—", len(g["works"]), g["results"], g["avg_percent"], g["status"]])

    ws3 = wb.create_sheet("По предметам")
    ws3.append(["Предмет", "Контрольных", "Результатов", "Средний %", "Статус"])
    for cell in ws3[1]:
        cell.font = bold
        cell.fill = header_fill
    for g in dataset["subject_groups"]:
        ws3.append([g["subject"].name if g["subject"] else "—", len(g["works"]), g["results"], g["avg_percent"], g["status"]])

    ws4 = wb.create_sheet("По годам")
    ws4.append(["Учебный год", "Контрольных", "Результатов", "Средний %", "Средняя отметка", "Статус"])
    for cell in ws4[1]:
        cell.font = bold
        cell.fill = header_fill
    for g in dataset["year_groups"]:
        ws4.append([g["year"].name if g["year"] else "Без года", len(g["works"]), g["results"], g["avg_percent"], g["avg_mark"], g["status"]])

    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out


def _make_archive_pdf(dataset, filters):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except Exception as exc:
        raise RuntimeError("Для PDF-экспорта нужен пакет reportlab") from exc

    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    items = []
    items.append(Paragraph("Архив контрольных работ", styles["Title"]))
    items.append(Paragraph(f"Контрольных: {dataset['summary']['works_count']} · Результатов: {dataset['summary']['results_count']} · Средний %: {dataset['summary']['avg_percent'] if dataset['summary']['avg_percent'] is not None else '—'}", styles["Normal"]))
    items.append(Spacer(1, 12))

    table_data = [["Год", "Дата", "Предмет", "Тема", "Учителя", "Результ.", "Ср.%", "Ср.отметка"]]
    for row in dataset["works"][:80]:
        table_data.append([row["year_name"], row["work_date_text"], row["subject_name"], row["theme"], row["teachers_text"], row["results"], row["avg_percent"] if row["avg_percent"] is not None else "—", row["avg_mark"] if row["avg_mark"] is not None else "—"])
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    items.append(table)
    items.append(Spacer(1, 12))

    teacher_table = [["Учитель", "Контрольных", "Результатов", "Ср.%", "Статус"]]
    for g in dataset["teacher_groups"][:40]:
        teacher_table.append([g["teacher"].fio if g["teacher"] else "—", len(g["works"]), g["results"], g["avg_percent"] if g["avg_percent"] is not None else "—", g["status"]])
    t2 = Table(teacher_table, repeatRows=1)
    t2.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EEF5FB")), ("GRID", (0,0), (-1,-1), 0.5, colors.grey)]))
    items.append(Paragraph("Сводка по учителям", styles["Heading2"]))
    items.append(t2)

    doc.build(items)
    out.seek(0)
    return out


def _mark_from_percent(percent, work=None):
    if percent is None:
        return None
    g5 = getattr(work, "grade5_percent", 85) or 85
    g4 = getattr(work, "grade4_percent", 65) or 65
    g3 = getattr(work, "grade3_percent", 45) or 45
    if percent >= g5:
        return 5
    if percent >= g4:
        return 4
    if percent >= g3:
        return 3
    return 2


def _can_view_assignment(assignment):
    if has_permission("control_works_edit"):
        return True
    return assignment.teacher_id == current_user.id


def _assigned_works_query():
    if has_permission("control_works_edit"):
        return ControlWork.query.order_by(ControlWork.work_date.desc().nullslast(), ControlWork.created_at.desc())
    return (
        ControlWork.query
        .join(ControlWorkAssignment, ControlWorkAssignment.control_work_id == ControlWork.id)
        .filter(ControlWorkAssignment.teacher_id == current_user.id)
        .distinct()
        .order_by(ControlWork.work_date.desc().nullslast(), ControlWork.created_at.desc())
    )


def _form_context(selected_subject_id=None):
    year = _current_year()
    classes = (
        SchoolClass.query.filter_by(academic_year_id=year.id)
        .order_by(SchoolClass.grade.asc().nullslast(), SchoolClass.name.asc())
        .all() if year else []
    )
    teachers = User.query.order_by(User.last_name.asc(), User.first_name.asc()).all()
    subjects = Subject.query.order_by(Subject.name.asc()).all()
    parallels = sorted({c.grade for c in classes if c.grade is not None})
    department_ids = _department_ids_for_user()
    teacher_options_map = _teacher_options_map(classes, subject_id=selected_subject_id, academic_year_id=(year.id if year else None), department_ids=department_ids)
    auto_teacher_by_class = _auto_teacher_by_class(classes, teacher_options_map)
    return year, classes, teachers, subjects, parallels, teacher_options_map, auto_teacher_by_class


def _task_count_from_request_or_work(work=None):
    if request.method == "POST":
        return max(1, min(int(request.form.get("task_count") or 1), 20))
    if work and work.tasks:
        return len(work.tasks)
    return 5


def _save_work_from_form(work=None):
    subject_id = request.form.get("subject_id", type=int)
    theme = (request.form.get("theme") or "").strip()
    work_date = _parse_date(request.form.get("work_date"))
    deadline_date = _parse_date(request.form.get("deadline_date"))
    task_count = _task_count_from_request_or_work(work)
    grade5_percent = request.form.get("grade5_percent", type=int) or 85
    grade4_percent = request.form.get("grade4_percent", type=int) or 65
    grade3_percent = request.form.get("grade3_percent", type=int) or 45
    current_year = _current_year()

    if not subject_id or not theme:
        raise ValueError("Выберите предмет из реестра и укажите тему контрольной работы.")

    selected_class_ids = request.form.getlist("class_ids")
    if not selected_class_ids:
        raise ValueError("Нужно выбрать хотя бы один класс.")

    if work is None:
        work = ControlWork(created_by=current_user.id)
        db.session.add(work)

    work.subject_id = subject_id
    work.academic_year_id = current_year.id if current_year else getattr(work, "academic_year_id", None)
    if current_year and current_year.end_date:
        try:
            work.retention_until = current_year.end_date.replace(year=current_year.end_date.year + 7)
        except Exception:
            pass
    work.theme = theme
    work.work_date = work_date
    work.deadline_date = deadline_date
    work.grade5_percent = grade5_percent
    work.grade4_percent = grade4_percent
    work.grade3_percent = grade3_percent
    db.session.flush()

    ControlWorkTask.query.filter_by(control_work_id=work.id).delete()
    for i in range(1, task_count + 1):
        max_score = int(request.form.get(f"max_score_{i}") or 0)
        description = (request.form.get(f"description_{i}") or "").strip() or None
        topic = (request.form.get(f"topic_{i}") or "").strip() or None
        db.session.add(ControlWorkTask(
            control_work_id=work.id,
            task_number=i,
            max_score=max_score,
            description=description,
            topic=topic,
        ))

    ControlWorkAssignment.query.filter_by(control_work_id=work.id).delete()
    selected_classes = {c.id: c for c in SchoolClass.query.filter(SchoolClass.id.in_([int(x) for x in selected_class_ids])).all()}
    department_ids = _department_ids_for_user()
    for class_id in selected_class_ids:
        class_id_int = int(class_id)
        teacher_id = request.form.get(f"teacher_for_{class_id}", type=int)
        if not teacher_id:
            school_class = selected_classes.get(class_id_int)
            candidates = _teacher_load_candidates(
                subject_id=subject_id,
                grade=(school_class.grade if school_class else None),
                class_name=(school_class.name if school_class else None),
                academic_year_id=(current_year.id if current_year else None),
                department_ids=department_ids,
            )
            preferred = next((item for item in candidates if item.get("preferred")), None)
            if preferred:
                teacher_id = preferred["id"]
            elif len(candidates) == 1:
                teacher_id = candidates[0]["id"]
        db.session.add(ControlWorkAssignment(
            control_work_id=work.id,
            school_class_id=class_id_int,
            teacher_id=teacher_id,
            status="ASSIGNED",
        ))

    return work


@control_bp.route("/api/teachers-by-load")
@login_required
def teachers_by_load_api():
    if not has_permission("control_works_view"):
        abort(403)
    subject_id = request.args.get("subject_id", type=int)
    year = _current_year()
    department_ids = _department_ids_for_user()
    payload = {}
    class_ids = [int(x) for x in request.args.getlist("class_id") if str(x).isdigit()]
    if class_ids:
        classes = SchoolClass.query.filter(SchoolClass.id.in_(class_ids)).all()
        for school_class in classes:
            payload[str(school_class.id)] = _teacher_load_candidates(
                subject_id=subject_id,
                grade=school_class.grade,
                class_name=school_class.name,
                academic_year_id=(year.id if year else None),
                department_ids=department_ids,
            )
    else:
        parallel = request.args.get("parallel", type=int)
        query = SchoolClass.query
        if year:
            query = query.filter_by(academic_year_id=year.id)
        if parallel:
            query = query.filter_by(grade=parallel)
        for school_class in query.all():
            payload[str(school_class.id)] = _teacher_load_candidates(
                subject_id=subject_id,
                grade=school_class.grade,
                class_name=school_class.name,
                academic_year_id=(year.id if year else None),
                department_ids=department_ids,
            )
    return jsonify(payload)


def _control_summary_dataset(selected_year_id=None, selected_subject_id=None, selected_teacher_id=None, selected_grade=None, selected_class_id=None):
    current_year = _current_year()
    selected_year_id = selected_year_id or (current_year.id if current_year else None)
    department_ids = _department_ids_for_user()

    work_query = ControlWork.query
    result_query = (
        db.session.query(ControlWorkResult, ControlWork, ControlWorkAssignment, SchoolClass, Child, User)
        .join(ControlWork, ControlWork.id == ControlWorkResult.control_work_id)
        .join(ControlWorkAssignment, db.and_(
            ControlWorkAssignment.control_work_id == ControlWorkResult.control_work_id,
            ControlWorkAssignment.school_class_id == ControlWorkResult.school_class_id,
        ))
        .join(SchoolClass, SchoolClass.id == ControlWorkResult.school_class_id)
        .join(Child, Child.id == ControlWorkResult.child_id)
        .outerjoin(User, User.id == ControlWorkAssignment.teacher_id)
    )

    if selected_year_id:
        work_query = work_query.filter(ControlWork.academic_year_id == selected_year_id)
        result_query = result_query.filter(ControlWork.academic_year_id == selected_year_id)
    if selected_subject_id:
        work_query = work_query.filter(ControlWork.subject_id == selected_subject_id)
        result_query = result_query.filter(ControlWork.subject_id == selected_subject_id)
    if selected_grade:
        result_query = result_query.filter(SchoolClass.grade == selected_grade)
    if selected_class_id:
        result_query = result_query.filter(SchoolClass.id == selected_class_id)
    if selected_teacher_id:
        result_query = result_query.filter(ControlWorkAssignment.teacher_id == selected_teacher_id)
        work_query = work_query.join(ControlWorkAssignment, ControlWorkAssignment.control_work_id == ControlWork.id).filter(ControlWorkAssignment.teacher_id == selected_teacher_id)
    elif has_permission("control_works_view") and not has_permission("control_works_edit") and getattr(current_user, "role", None) != "METHODIST":
        result_query = result_query.filter(ControlWorkAssignment.teacher_id == current_user.id)
        work_query = work_query.join(ControlWorkAssignment, ControlWorkAssignment.control_work_id == ControlWork.id).filter(ControlWorkAssignment.teacher_id == current_user.id)
    elif department_ids:
        result_query = result_query.join(TeacherLoad, db.and_(
            TeacherLoad.teacher_id == ControlWorkAssignment.teacher_id,
            TeacherLoad.subject_id == ControlWork.subject_id,
            TeacherLoad.is_archived.is_(False),
        )).filter(TeacherLoad.department_id.in_(department_ids))
        work_query = work_query.join(ControlWorkAssignment, ControlWorkAssignment.control_work_id == ControlWork.id).join(TeacherLoad, db.and_(
            TeacherLoad.teacher_id == ControlWorkAssignment.teacher_id,
            TeacherLoad.subject_id == ControlWork.subject_id,
            TeacherLoad.is_archived.is_(False),
        )).filter(TeacherLoad.department_id.in_(department_ids))

    work_count = work_query.distinct().count()
    rows_raw = result_query.all()
    seen_pairs = set()
    rows = []
    for item in rows_raw:
        result, work, assignment, school_class, child, teacher = item
        key = (result.id, assignment.id)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        rows.append(item)

    percents = []
    mark_counts = {2: 0, 3: 0, 4: 0, 5: 0}
    teacher_stats = defaultdict(lambda: {"teacher_name": "—", "subject_names": set(), "results": 0, "percents": [], "marks": []})
    class_stats = defaultdict(lambda: {"class_name": "—", "results": 0, "percents": [], "marks": [], "subject_names": set()})
    child_stats = defaultdict(lambda: {"child_name": "—", "class_name": "—", "results": 0, "percents": [], "marks": [], "subject_names": set()})

    for result, work, assignment, school_class, child, teacher in rows:
        percent = float(result.percent) if result.percent is not None else None
        mark = result.mark
        if percent is not None:
            percents.append(percent)
        if mark in mark_counts:
            mark_counts[mark] += 1

        teacher_key = assignment.teacher_id or 0
        teacher_stats[teacher_key]["teacher_name"] = teacher.fio if teacher else "Не назначен"
        teacher_stats[teacher_key]["subject_names"].add(work.subject_name)
        teacher_stats[teacher_key]["results"] += 1
        if percent is not None:
            teacher_stats[teacher_key]["percents"].append(percent)
        if mark is not None:
            teacher_stats[teacher_key]["marks"].append(mark)

        class_stats[school_class.id]["class_name"] = school_class.name
        class_stats[school_class.id]["subject_names"].add(work.subject_name)
        class_stats[school_class.id]["results"] += 1
        if percent is not None:
            class_stats[school_class.id]["percents"].append(percent)
        if mark is not None:
            class_stats[school_class.id]["marks"].append(mark)

        child_stats[child.id]["child_name"] = child.fio
        child_stats[child.id]["class_name"] = school_class.name
        child_stats[child.id]["subject_names"].add(work.subject_name)
        child_stats[child.id]["results"] += 1
        if percent is not None:
            child_stats[child.id]["percents"].append(percent)
        if mark is not None:
            child_stats[child.id]["marks"].append(mark)

    def finalize(items, key_name):
        out = []
        for data in items.values():
            avg_percent = _safe_avg(data["percents"], digits=1)
            marks = data["marks"]
            quality = round(((sum(1 for m in marks if m in [4, 5]) / len(marks)) * 100), 1) if marks else None
            success = round(((sum(1 for m in marks if m in [3, 4, 5]) / len(marks)) * 100), 1) if marks else None
            out.append({
                key_name: data[key_name],
                "subjects_text": ", ".join(sorted(x for x in data["subject_names"] if x)) or "—",
                "results": data["results"],
                "avg_percent": avg_percent,
                "quality": quality,
                "success": success,
                "avg_mark": _safe_avg(marks, digits=2),
            })
        return sorted(out, key=lambda x: ((x["avg_percent"] is None), -(x["avg_percent"] or 0), x[key_name]))

    overall_quality = round(((mark_counts[4] + mark_counts[5]) / sum(mark_counts.values())) * 100, 1) if sum(mark_counts.values()) else None
    overall_success = round(((mark_counts[3] + mark_counts[4] + mark_counts[5]) / sum(mark_counts.values())) * 100, 1) if sum(mark_counts.values()) else None
    return {
        "summary": {
            "works_count": work_count,
            "results_count": len(rows),
            "avg_percent": _safe_avg(percents, digits=1),
            "quality": overall_quality,
            "success": overall_success,
            "mark_counts": mark_counts,
        },
        "teacher_rows": finalize(teacher_stats, "teacher_name")[:50],
        "class_rows": finalize(class_stats, "class_name")[:50],
        "child_rows": finalize(child_stats, "child_name")[:100],
    }


@control_bp.route("/summary")
@login_required
def control_works_summary():
    if not has_permission("control_works_view"):
        abort(403)
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    subjects = Subject.query.order_by(Subject.name.asc()).all()
    current_year = _current_year()
    selected_year_id = request.args.get("academic_year_id", type=int) or (current_year.id if current_year else None)
    selected_subject_id = request.args.get("subject_id", type=int)
    selected_teacher_id = request.args.get("teacher_id", type=int)
    selected_grade = request.args.get("grade", type=int)
    selected_class_id = request.args.get("class_id", type=int)

    teacher_query = User.query.order_by(User.last_name.asc(), User.first_name.asc())
    department_ids = _department_ids_for_user()
    if department_ids:
        teacher_ids = sorted({row.teacher_id for row in TeacherLoad.query.filter(TeacherLoad.department_id.in_(department_ids), TeacherLoad.is_archived.is_(False)).all() if row.teacher_id})
        teacher_query = teacher_query.filter(User.id.in_(teacher_ids or [0]))
    if not has_permission("control_works_edit") and getattr(current_user, "role", None) != "METHODIST":
        teacher_query = teacher_query.filter(User.id == current_user.id)
        selected_teacher_id = current_user.id
    teachers = teacher_query.all()

    classes_query = SchoolClass.query.order_by(SchoolClass.grade.asc().nullslast(), SchoolClass.name.asc())
    if selected_year_id:
        classes_query = classes_query.filter(SchoolClass.academic_year_id == selected_year_id)
    classes = classes_query.all()
    parallels = sorted({c.grade for c in classes if c.grade is not None})

    dataset = _control_summary_dataset(
        selected_year_id=selected_year_id,
        selected_subject_id=selected_subject_id,
        selected_teacher_id=selected_teacher_id,
        selected_grade=selected_grade,
        selected_class_id=selected_class_id,
    )
    return render_template("control_works/summary.html", years=years, subjects=subjects, teachers=teachers, classes=classes, parallels=parallels, selected_year_id=selected_year_id, selected_subject_id=selected_subject_id, selected_teacher_id=selected_teacher_id, selected_grade=selected_grade, selected_class_id=selected_class_id, dataset=dataset)


@control_bp.route("/")
@login_required
def list_control_works():
    if not has_permission("control_works_view"):
        abort(403)

    if not has_permission("control_works_edit"):
        return redirect(url_for("control_works.my_control_works"))

    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    selected_year_id = request.args.get("academic_year_id", type=int) or (_current_year().id if _current_year() else None)
    query = _assigned_works_query()
    if selected_year_id:
        query = query.filter(ControlWork.academic_year_id == selected_year_id)
    works = query.all()
    stats = {}
    for work in works:
        assignments = work.assignments or []
        stats[work.id] = {
            "total": len(assignments),
            "filled": sum(1 for a in assignments if a.status == "FILLED")
        }
    return render_template("control_works/list.html", works=works, stats=stats, my_only=False, years=years, selected_year_id=selected_year_id)


@control_bp.route("/my")
@login_required
def my_control_works():
    if not has_permission("control_works_view"):
        abort(403)
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    selected_year_id = request.args.get("academic_year_id", type=int) or (_current_year().id if _current_year() else None)
    works_q = (
        ControlWork.query
        .join(ControlWorkAssignment, ControlWorkAssignment.control_work_id == ControlWork.id)
        .filter(ControlWorkAssignment.teacher_id == current_user.id)
        .distinct()
        .order_by(ControlWork.work_date.desc().nullslast(), ControlWork.created_at.desc())
        
    )
    if selected_year_id:
        works_q = works_q.filter(ControlWork.academic_year_id == selected_year_id)
    works = works_q.all()
    stats = {}
    for work in works:
        assignments = [a for a in (work.assignments or []) if a.teacher_id == current_user.id]
        stats[work.id] = {"total": len(assignments), "filled": sum(1 for a in assignments if a.status == "FILLED")}
    return render_template("control_works/list.html", works=works, stats=stats, my_only=True, years=years, selected_year_id=selected_year_id)


@control_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_control_work():
    if not has_permission("control_works_edit"):
        abort(403)
    selected_subject_id = request.form.get("subject_id", type=int) or (work.subject_id if "work" in locals() and work else None)
    year, classes, teachers, subjects, parallels, teacher_options_map, auto_teacher_by_class = _form_context(selected_subject_id=selected_subject_id)
    task_count = _task_count_from_request_or_work()

    if request.method == "POST":
        try:
            work = _save_work_from_form()
            db.session.commit()
            flash("Контрольная работа создана.", "success")
            return redirect(url_for("control_works.view_control_work", work_id=work.id))
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "danger")

    return render_template("control_works/form.html", classes=classes, teachers=teachers, subjects=subjects, task_count=task_count, parallels=parallels, teacher_options_map=teacher_options_map, auto_teacher_by_class=auto_teacher_by_class, work=None)


@control_bp.route("/<int:work_id>/edit", methods=["GET", "POST"])
@login_required
def edit_control_work(work_id):
    if not has_permission("control_works_edit"):
        abort(403)
    work = ControlWork.query.get_or_404(work_id)
    selected_subject_id = request.form.get("subject_id", type=int) or (work.subject_id if "work" in locals() and work else None)
    year, classes, teachers, subjects, parallels, teacher_options_map, auto_teacher_by_class = _form_context(selected_subject_id=selected_subject_id)
    task_count = _task_count_from_request_or_work(work)

    if request.method == "POST":
        try:
            _save_work_from_form(work)
            db.session.commit()
            flash("Настройки контрольной обновлены.", "success")
            return redirect(url_for("control_works.view_control_work", work_id=work.id))
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "danger")

    selected_class_ids = {a.school_class_id for a in (work.assignments or [])}
    teacher_by_class = {a.school_class_id: a.teacher_id for a in (work.assignments or [])}
    return render_template(
        "control_works/form.html",
        classes=classes,
        teachers=teachers,
        subjects=subjects,
        task_count=task_count,
        parallels=parallels,
        work=work,
        selected_class_ids=selected_class_ids,
        teacher_by_class=teacher_by_class,
        teacher_options_map=teacher_options_map,
        auto_teacher_by_class=auto_teacher_by_class,
    )


@control_bp.route("/<int:work_id>/delete", methods=["POST"])
@login_required
def delete_control_work(work_id):
    if not has_permission("control_works_edit"):
        abort(403)
    work = ControlWork.query.get_or_404(work_id)
    db.session.delete(work)
    db.session.commit()
    flash("Контрольная работа удалена.", "success")
    return redirect(url_for("control_works.list_control_works"))


@control_bp.route("/<int:work_id>")
@login_required
def view_control_work(work_id):
    if not has_permission("control_works_view"):
        abort(403)
    work = ControlWork.query.get_or_404(work_id)
    if not has_permission("control_works_edit"):
        allowed = any(a.teacher_id == current_user.id for a in (work.assignments or []))
        if not allowed:
            abort(403)
    return render_template("control_works/detail.html", work=work)


@control_bp.route("/<int:work_id>/assignment/<int:assignment_id>", methods=["GET", "POST"])
@login_required
def assignment_results(work_id, assignment_id):
    if not has_permission("control_works_view"):
        abort(403)

    work = ControlWork.query.get_or_404(work_id)
    assignment = ControlWorkAssignment.query.get_or_404(assignment_id)
    if assignment.control_work_id != work.id:
        abort(404)
    if not _can_view_assignment(assignment):
        abort(403)

    school_class = assignment.school_class
    year = _current_year()
    enrollments = []
    if year and school_class:
        enrollments = (
            ChildEnrollment.query
            .join(Child, Child.id == ChildEnrollment.child_id)
            .filter(
                ChildEnrollment.academic_year_id == year.id,
                ChildEnrollment.school_class_id == school_class.id,
                ChildEnrollment.ended_at.is_(None),
            )
            .order_by(Child.last_name.asc(), Child.first_name.asc(), Child.middle_name.asc())
            .all()
        )
    tasks = sorted((work.tasks or []), key=lambda x: x.task_number or 0)
    max_total = sum(task.max_score or 0 for task in tasks)

    existing = {r.child_id: r for r in ControlWorkResult.query.filter_by(control_work_id=work.id, assignment_id=assignment.id, school_class_id=school_class.id).all()}
    posted_scores = {}

    if request.method == "POST":
        has_errors = False
        for en in enrollments:
            total_score = 0
            any_value = False
            for task in tasks:
                raw_value = (request.form.get(f"task_{task.id}_{en.child_id}") or "").strip()
                posted_scores[(en.child_id, task.id)] = raw_value
                if raw_value == "":
                    continue
                any_value = True
                try:
                    value = int(raw_value)
                except ValueError:
                    flash(f"{en.child.fio}: в задании {task.task_number} должно быть целое число.", "danger")
                    has_errors = True
                    continue
                max_score = task.max_score or 0
                if value < 0 or value > max_score:
                    flash(f"{en.child.fio}: в задании {task.task_number} допустимо только от 0 до {max_score}.", "danger")
                    has_errors = True
                    continue
                total_score += value

            if has_errors:
                continue

            row = existing.get(en.child_id)
            if row is None:
                row = ControlWorkResult(control_work_id=work.id, assignment_id=assignment.id, school_class_id=school_class.id, academic_year_id=(work.academic_year_id or (year.id if year else None)), child_id=en.child_id, created_by=current_user.id, grade5_percent=work.grade5_percent, grade4_percent=work.grade4_percent, grade3_percent=work.grade3_percent, retention_until=work.retention_until)
                db.session.add(row)

            row.assignment_id = assignment.id
            row.school_class_id = school_class.id
            row.academic_year_id = work.academic_year_id or (year.id if year else row.academic_year_id)
            row.grade5_percent = work.grade5_percent
            row.grade4_percent = work.grade4_percent
            row.grade3_percent = work.grade3_percent
            row.retention_until = work.retention_until

            if any_value:
                percent = round((total_score / max_total) * 100, 2) if max_total > 0 else None
                mark = _mark_from_percent(percent, work)
                row.total_score = total_score
                row.percent = percent
                row.mark = mark
            else:
                row.total_score = None
                row.percent = None
                row.mark = None

            child = en.child
            if row.mark == 2:
                child.is_low = True
                existing_subjects = [x.strip() for x in (child.low_subjects or "").split(",") if x.strip()]
                if work.subject_name not in existing_subjects:
                    existing_subjects.append(work.subject_name)
                    child.low_subjects = ", ".join(existing_subjects)
                child.low_notes = f"Контрольная: {work.subject_name} — {work.theme}"

        if has_errors:
            db.session.rollback()
            return render_template("control_works/results.html", work=work, assignment=assignment, enrollments=enrollments, existing=existing, max_total=max_total, tasks=tasks, posted_scores=posted_scores)

        assignment.status = "FILLED"
        db.session.commit()
        flash("Результаты сохранены.", "success")
        return redirect(url_for("control_works.view_control_work", work_id=work.id))

    return render_template("control_works/results.html", work=work, assignment=assignment, enrollments=enrollments, existing=existing, max_total=max_total, tasks=tasks, posted_scores=posted_scores)


@control_bp.route("/<int:work_id>/report")
@login_required
def control_work_report(work_id):
    if not has_permission("control_works_view"):
        abort(403)
    work = ControlWork.query.get_or_404(work_id)
    teacher_id = None
    if not has_permission("control_works_edit"):
        if not any(a.teacher_id == current_user.id for a in (work.assignments or [])):
            abort(403)
        teacher_id = current_user.id

    payload = _build_control_work_report(work, teacher_id=teacher_id)
    return render_template("control_works/report.html", **payload)


@control_bp.route("/archive")
@login_required
def control_works_archive():
    if not has_permission("control_works_view"):
        abort(403)
    filters = _get_archive_filters()
    dataset = _build_archive_dataset(filters)
    return render_template("control_works/archive.html", **filters, dataset=dataset)


@control_bp.route("/archive/export.xlsx")
@login_required
def control_works_archive_xlsx():
    if not has_permission("control_works_view"):
        abort(403)
    filters = _get_archive_filters()
    dataset = _build_archive_dataset(filters)
    output = _make_archive_excel(filters, dataset)
    year_part = next((y.name for y in filters["years"] if y.id == filters["selected_year_id"]), "all") if filters["selected_year_id"] else "all"
    return send_file(output, as_attachment=True, download_name=f"control_works_archive_{year_part}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@control_bp.route("/archive/export.pdf")
@login_required
def control_works_archive_pdf():
    if not has_permission("control_works_view"):
        abort(403)
    filters = _get_archive_filters()
    dataset = _build_archive_dataset(filters)
    try:
        output = _make_archive_pdf(dataset, filters)
    except RuntimeError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("control_works.control_works_archive", **request.args))
    year_part = next((y.name for y in filters["years"] if y.id == filters["selected_year_id"]), "all") if filters["selected_year_id"] else "all"
    return send_file(output, as_attachment=True, download_name=f"control_works_archive_{year_part}.pdf", mimetype="application/pdf")
