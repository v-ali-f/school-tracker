from __future__ import annotations

import json
import uuid
from collections import defaultdict
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.core.cache import view_response_cache, make_key
from app.core.extensions import db
from .models import (
    AcademicYear,
    Child,
    Department,
    DepartmentLeader,
    OlympiadImportSession,
    OlympiadResult,
    OlympiadSubjectMapping,
    OlympiadUnmatchedRow,
    Subject,
    TeacherLoad,
    User,
)
from .permissions import CLASS_TEACHER, METHODIST, TEACHER, has_permission
from .services.olympiad_import_service import execute_import, extract_unique_subjects, filter_school_rows, preview_import, read_excel, read_zip, ensure_olympiad_result_schema
from .services.olympiad_matcher import find_department_for_row, find_teacher_for_row
from .services.olympiad_normalization import STATUS_LABELS, STAGE_LABELS, normalize_olympiad_stage, normalize_olympiad_status, stage_badge, stage_label, status_label
from .services.olympiad_stats_service import all_analytics, class_stats, dashboard_stats, department_stats, subject_stats, teacher_stats, yearly_comparison

olympiads_bp = Blueprint("olympiads", __name__, url_prefix="/olympiads")
STAGES = ["школьный", "муниципальный", "региональный", "заключительный"]


def _mapping_linked_subject_ids_from_form():
    values = []
    for raw in request.form.getlist("linked_subject_ids"):
        if str(raw).isdigit():
            values.append(int(raw))
    primary = request.form.get("subject_id", type=int)
    if primary and primary not in values:
        values.insert(0, primary)
    return ",".join(str(x) for x in values) if values else None


def _mapping_grade_label(row):
    g_from = getattr(row, "grade_from", None)
    g_to = getattr(row, "grade_to", None)
    if g_from and g_to:
        return f"{g_from}–{g_to}" if g_from != g_to else str(g_from)
    if g_from:
        return f"с {g_from}"
    if g_to:
        return f"по {g_to}"
    return "Все"


def _mapping_linked_subject_names(row):
    ids = []
    for raw in str(getattr(row, "linked_subject_ids", None) or "").replace(";", ",").split(","):
        raw = str(raw).strip()
        if raw.isdigit():
            ids.append(int(raw))
    names = []
    seen = set()
    for subject_id in ids:
        subject = Subject.query.get(subject_id)
        if subject and subject.name and subject.name not in seen:
            names.append(subject.name)
            seen.add(subject.name)
    if row.subject and row.subject.name not in seen:
        names.insert(0, row.subject.name)
    return names




def _ensure_olympiad_school_columns():
    """Runtime-схема для полей фильтрации школы в импорте олимпиад."""
    try:
        db.session.execute(db.text("ALTER TABLE organization_settings ADD COLUMN IF NOT EXISTS olympiad_school_login VARCHAR(80)"))
        db.session.execute(db.text("ALTER TABLE organization_settings ADD COLUMN IF NOT EXISTS olympiad_ekis_code VARCHAR(80)"))
        db.session.execute(db.text("ALTER TABLE organization_settings ADD COLUMN IF NOT EXISTS olympiad_school_name VARCHAR(255)"))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _olympiad_school_filter_values():
    _ensure_olympiad_school_columns()
    try:
        row = db.session.execute(db.text("""
            SELECT short_name, full_name,
                   olympiad_school_login, olympiad_ekis_code, olympiad_school_name
            FROM organization_settings
            ORDER BY COALESCE(is_active, FALSE) DESC, id DESC
            LIMIT 1
        """)).mappings().first()
    except Exception:
        db.session.rollback()
        try:
            row = db.session.execute(db.text("""
                SELECT short_name, full_name,
                       olympiad_school_login, olympiad_ekis_code, olympiad_school_name
                FROM organization_settings
                ORDER BY id DESC
                LIMIT 1
            """)).mappings().first()
        except Exception:
            db.session.rollback()
            row = None
    if not row:
        return {"school_login_value": None, "school_ekis_value": None, "school_name_value": None}
    school_name = row.get("olympiad_school_name") or row.get("short_name") or row.get("full_name")
    return {
        "school_login_value": row.get("olympiad_school_login"),
        "school_ekis_value": row.get("olympiad_ekis_code"),
        "school_name_value": school_name,
    }

def _deny_unless(code: str):
    if not has_permission(code):
        abort(403)


def _department_ids_for_user(user=None):
    user = user or current_user
    if getattr(user, "role", None) == "ADMIN" or has_permission("olympiad_settings_manage"):
        return None
    if getattr(user, "role", None) == METHODIST:
        dep_ids = sorted({row.department_id for row in DepartmentLeader.query.filter_by(user_id=user.id).all() if row.department_id})
        return dep_ids or []
    if getattr(user, "role", None) in {TEACHER, CLASS_TEACHER}:
        dep_ids = sorted({row.department_id for row in TeacherLoad.query.filter_by(teacher_id=user.id, is_archived=False).all() if row.department_id})
        return dep_ids or []
    return []


def _allowed_departments():
    dep_ids = _department_ids_for_user()
    q = Department.query.order_by(Department.name.asc())
    if dep_ids is None:
        return q.all()
    if not dep_ids:
        return []
    return q.filter(Department.id.in_(dep_ids)).all()


def _subject_teachers(subject_id=None, academic_year_id=None, department_id=None):
    if not subject_id:
        return []
    q = db.session.query(User).join(TeacherLoad, TeacherLoad.teacher_id == User.id).filter(
        TeacherLoad.is_archived.is_(False),
        TeacherLoad.subject_id == subject_id,
    )
    if academic_year_id:
        q = q.filter((TeacherLoad.academic_year_id == academic_year_id) | (TeacherLoad.academic_year_id.is_(None)))
    if department_id:
        q = q.filter((TeacherLoad.department_id == department_id) | (TeacherLoad.department_id.is_(None)))
    return q.distinct().order_by(User.last_name.asc(), User.first_name.asc()).all()


def _teacher_options_for_result(result: OlympiadResult):
    return _subject_teachers(result.subject_id, result.academic_year_id, result.department_id)

def _apply_manual_binding(rows, teacher_id):
    teacher = User.query.get(teacher_id) if teacher_id else None
    for row in rows:
        row.teacher_id = teacher_id
        row.teacher_binding_status = "manual" if teacher_id else "unassigned"
        row.teacher_binding_source = "manual_bulk" if teacher_id else "unassigned"
        row.teacher_binding_reason = "Учитель назначен массово" if teacher_id else "Учитель снят массово"
        if teacher_id and row.subject_id and row.academic_year_id:
            load_q = TeacherLoad.query.filter_by(teacher_id=teacher_id, academic_year_id=row.academic_year_id, is_archived=False)
            if row.subject_id:
                load_q = load_q.filter((TeacherLoad.subject_id == row.subject_id) | (db.func.lower(db.func.coalesce(TeacherLoad.subject_name, '')) == db.func.lower(row.subject.name if row.subject else row.subject_name or '')))
            best = load_q.order_by(TeacherLoad.hours.desc(), TeacherLoad.id.desc()).first()
            if best and best.department_id:
                row.department_id = best.department_id
        elif teacher and not row.department_id:
            dep_ids = sorted({x.department_id for x in TeacherLoad.query.filter_by(teacher_id=teacher_id, is_archived=False).all() if x.department_id})
            if len(dep_ids) == 1:
                row.department_id = dep_ids[0]


def _apply_auto_binding(row, overwrite_manual=False):
    if row.teacher_binding_source in {"manual", "manual_bulk", "manual_single"} and not overwrite_manual:
        return False
    payload = {
        "subject": row.subject_name or (row.subject.name if row.subject else ""),
        "class_study": row.class_study_text or (row.school_class.name if row.school_class else ""),
        "class_participation": row.class_participation_text or "",
    }
    load, teacher_error = find_teacher_for_row(
        payload,
        child=row.child,
        subject=row.subject,
        academic_year_id=row.academic_year_id,
        department=row.department,
        teacher_binding_mode="auto",
    ) if row.child and row.subject else (None, "Не удалось определить учителя")
    department = row.department
    if load and not department:
        department, _ = find_department_for_row(payload, teacher_load=load, subject=row.subject, subject_department=row.department, selected_department_id=row.department_id)
    row.teacher_id = load.teacher_id if load else None
    row.teacher_binding_status = "auto" if load else "unassigned"
    row.teacher_binding_source = "auto_load" if load else "unassigned"
    row.teacher_binding_reason = teacher_error or ("Учитель найден автоматически" if load else "Учитель не найден")
    if load and load.department_id:
        row.department_id = load.department_id
    elif department and getattr(department, "id", None):
        row.department_id = department.id
    return True


def _binding_groups_query(academic_year_id=None, stage=None, subject_id=None, department_id=None, parallel=None, class_name=None, status=None, teacher_id=None):
    q = OlympiadResult.query.filter(OlympiadResult.is_archived.is_(False))
    if academic_year_id:
        q = q.filter(OlympiadResult.academic_year_id == academic_year_id)
    if stage:
        q = q.filter(OlympiadResult.stage == stage)
    if subject_id:
        q = q.filter(OlympiadResult.subject_id == subject_id)
    if department_id:
        q = q.filter(OlympiadResult.department_id == department_id)
    if status:
        q = q.filter(OlympiadResult.teacher_binding_status == status)
    if teacher_id:
        q = q.filter(OlympiadResult.teacher_id == teacher_id)
    rows = q.order_by(OlympiadResult.subject_name.asc(), OlympiadResult.class_study_text.asc(), OlympiadResult.id.asc()).all()
    groups = {}
    for row in rows:
        cls = row.school_class.name if row.school_class else (row.class_study_text or "—")
        grade = row.school_class.grade if row.school_class else None
        if parallel and grade != parallel:
            continue
        if class_name and cls != class_name:
            continue
        key = (row.academic_year_id, row.stage or "", row.subject_id or 0, row.subject_name or "", cls)
        groups.setdefault(key, []).append(row)
    return groups


@olympiads_bp.route("/")
@login_required
def registry():
    _deny_unless("olympiad_view")
    ensure_olympiad_result_schema()
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    academic_year_id = request.args.get("academic_year_id", type=int) or (current_year.id if current_year else None)
    stage = (request.args.get("stage") or "").strip()
    subject_id = request.args.get("subject_id", type=int)
    teacher_id = request.args.get("teacher_id", type=int)
    department_id = request.args.get("department_id", type=int)
    status = request.args.get("status", "").strip()
    status_group = request.args.get("status_group", "").strip()
    child_q = request.args.get("child", "").strip()

    allowed_dep_ids = _department_ids_for_user()
    if allowed_dep_ids is not None:
        if department_id and department_id not in allowed_dep_ids:
            abort(403)
        if not department_id and len(allowed_dep_ids) == 1:
            department_id = allowed_dep_ids[0]

    # Response-кеш для /olympiads/ — типовой запрос admin/METHODIST 980 мс из-за
    # joinedload по 500 OlympiadResult и шаблона с inline-формами teacher-picker.
    # Кеш разделён по роли (teacher_scoped vs общий) и по department_ids.
    is_teacher_scoped = current_user.role in {TEACHER, CLASS_TEACHER}
    cache_role_key = f"u{current_user.id}" if is_teacher_scoped else "_"
    cache_dep_key = ",".join(map(str, sorted(allowed_dep_ids))) if allowed_dep_ids is not None else "*"
    cache_key = make_key(
        "olympiads_registry",
        cache_role_key,
        cache_dep_key,
        academic_year_id or 0,
        stage,
        subject_id or 0,
        teacher_id or 0,
        department_id or 0,
        stage_group or "",
        status_group or "",
        year_from_id or 0,
        year_to_id or 0,
        status,
        status_group,
        child_q,
    )
    cached_html = view_response_cache.get(cache_key)
    if cached_html is not None:
        from flask import Response
        return Response(cached_html, mimetype="text/html; charset=utf-8")

    rows_q = OlympiadResult.query.options(
        joinedload(OlympiadResult.child),
        joinedload(OlympiadResult.teacher),
        joinedload(OlympiadResult.subject),
        joinedload(OlympiadResult.school_class),
        joinedload(OlympiadResult.department),
    ).filter(OlympiadResult.is_archived.is_(False))
    if academic_year_id:
        rows_q = rows_q.filter(OlympiadResult.academic_year_id == academic_year_id)
    if stage:
        rows_q = rows_q.filter(OlympiadResult.stage == stage)
    if subject_id:
        rows_q = rows_q.filter(OlympiadResult.subject_id == subject_id)
    if teacher_id:
        rows_q = rows_q.filter(OlympiadResult.teacher_id == teacher_id)
    if department_id:
        rows_q = rows_q.filter(OlympiadResult.department_id == department_id)
    elif allowed_dep_ids is not None:
        if allowed_dep_ids:
            rows_q = rows_q.filter(OlympiadResult.department_id.in_(allowed_dep_ids))
        else:
            rows_q = rows_q.filter(db.text("1=0"))
    if status_group:
        rows_q = rows_q.filter(OlympiadResult.status_group == status_group)
    elif status:
        rows_q = rows_q.filter(OlympiadResult.status.ilike(f"%{status}%"))
    if child_q:
        rows_q = rows_q.join(Child, OlympiadResult.child_id == Child.id).filter(
            db.or_(
                Child.last_name.ilike(f"%{child_q}%"),
                Child.first_name.ilike(f"%{child_q}%"),
                Child.middle_name.ilike(f"%{child_q}%"),
            )
        )
    if current_user.role in {TEACHER, CLASS_TEACHER}:
        rows_q = rows_q.filter(OlympiadResult.teacher_id == current_user.id)

    rows = rows_q.order_by(OlympiadResult.created_at.desc()).limit(500).all()
    # Batch teacher options: group rows by (subject_id, year_id, dept_id) to avoid N queries
    _teacher_cache = {}
    teacher_options_by_result = {}
    for row in rows:
        cache_key = (row.subject_id, row.academic_year_id, row.department_id)
        if cache_key not in _teacher_cache:
            _teacher_cache[cache_key] = _teacher_options_for_result(row)
        teacher_options_by_result[row.id] = _teacher_cache[cache_key]
    html = render_template(
        "olympiad_registry.html",
        rows=rows,
        teacher_options_by_result=teacher_options_by_result,
        years=AcademicYear.query.order_by(AcademicYear.name.desc()).all(),
        subjects=Subject.query.order_by(Subject.name.asc()).all(),
        teachers=User.query.order_by(User.last_name.asc(), User.first_name.asc()).all(),
        departments=_allowed_departments(),
        stages=STAGES,
        academic_year_id=academic_year_id,
        stage=stage,
        subject_id=subject_id,
        teacher_id=teacher_id,
        department_id=department_id,
        status=status,
        status_group=status_group,
        status_labels=STATUS_LABELS,
        stage_labels=STAGE_LABELS,
        stage_badge=stage_badge,
        stage_label=stage_label,
        status_label=status_label,
        child_q=child_q,
    )
    view_response_cache.set(cache_key, html, timeout=120)
    return html


@olympiads_bp.route("/<int:result_id>/assign-teacher", methods=["POST"])
@login_required
def assign_teacher(result_id: int):
    _deny_unless("olympiad_edit")
    result = OlympiadResult.query.get_or_404(result_id)
    teacher_id = request.form.get("teacher_id", type=int)
    if teacher_id:
        result.teacher_id = teacher_id
        result.teacher_binding_status = "manual"
        result.teacher_binding_source = "manual_single"
        result.teacher_binding_reason = "Учитель назначен вручную"
        load = TeacherLoad.query.filter_by(
            teacher_id=teacher_id,
            subject_id=result.subject_id,
            academic_year_id=result.academic_year_id,
            is_archived=False,
        )
        if result.department_id:
            load = load.filter((TeacherLoad.department_id == result.department_id) | (TeacherLoad.department_id.is_(None)))
        best = load.order_by(TeacherLoad.hours.desc(), TeacherLoad.id.desc()).first()
        if best and best.department_id:
            result.department_id = best.department_id
    else:
        result.teacher_id = None
        result.teacher_binding_status = "unassigned"
        result.teacher_binding_source = "unassigned"
        result.teacher_binding_reason = "Учитель снят вручную"
    db.session.commit()
    flash("Учитель по результату обновлён.", "success")
    return redirect(url_for("olympiads.registry", academic_year_id=result.academic_year_id, subject_id=result.subject_id))


@olympiads_bp.route("/bulk-assign-teacher", methods=["POST"])
@login_required
def bulk_assign_teacher():
    _deny_unless("olympiad_edit")
    teacher_id = request.form.get("teacher_id", type=int)
    result_ids = [int(x) for x in request.form.getlist("result_ids") if str(x).isdigit()]
    if not result_ids:
        flash("Не выбраны записи для массового изменения.", "warning")
        return redirect(url_for("olympiads.registry"))
    rows = OlympiadResult.query.filter(OlympiadResult.id.in_(result_ids)).all()
    for row in rows:
        row.teacher_id = teacher_id
        row.teacher_binding_status = "manual" if teacher_id else "unassigned"
        row.teacher_binding_source = "manual_bulk" if teacher_id else "unassigned"
        row.teacher_binding_reason = "Учитель назначен массово" if teacher_id else "Учитель снят массово"
        if teacher_id and row.subject_id and row.academic_year_id:
            load = TeacherLoad.query.filter_by(
                teacher_id=teacher_id,
                subject_id=row.subject_id,
                academic_year_id=row.academic_year_id,
                is_archived=False,
            ).order_by(TeacherLoad.hours.desc(), TeacherLoad.id.desc()).first()
            if load and load.department_id:
                row.department_id = load.department_id
    db.session.commit()
    flash(f"Обновлено записей: {len(rows)}.", "success")
    return redirect(url_for("olympiads.registry"))


@olympiads_bp.route('/teachers/by-subject')
@login_required
def teachers_by_subject():
    _deny_unless('olympiad_import')
    subject_id = request.args.get('subject_id', type=int)
    academic_year_id = request.args.get('academic_year_id', type=int)
    department_id = request.args.get('department_id', type=int)
    rows = [{"id": t.id, "fio": t.fio} for t in _subject_teachers(subject_id, academic_year_id, department_id)]
    return jsonify(rows)


@olympiads_bp.route("/import", methods=["GET", "POST"])
@login_required
def import_view():
    _deny_unless("olympiad_import")
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("Файл не выбран", "danger")
            return redirect(url_for("olympiads.import_view"))

        filename = (file.filename or "").lower()
        mode = request.form.get("mode") or ("zip" if filename.endswith(".zip") else "excel")
        academic_year_id = request.form.get("academic_year_id", type=int)
        stage = request.form.get("stage") or "школьный"
        subject_id = request.form.get("subject_id", type=int)
        department_id = request.form.get("department_id", type=int)
        teacher_binding_mode = (request.form.get('teacher_binding_mode') or 'auto').strip().lower()
        selected_teacher_id = request.form.get('teacher_id', type=int)
        selected_teacher_ids = [int(x) for x in request.form.getlist('teacher_ids') if str(x).isdigit()]
        filter_mode = (request.form.get("filter_mode") or "both").strip().lower()
        use_login = filter_mode in {"both", "login"}
        use_ekis = filter_mode in {"both", "ekis"}

        rows = read_zip(file) if mode == "zip" else read_excel(file)
        school_filter_values = _olympiad_school_filter_values()
        school_rows = filter_school_rows(
            rows,
            use_login=use_login,
            use_ekis=use_ekis,
            use_name=True,
            **school_filter_values,
        )
        unique_subjects = extract_unique_subjects(school_rows)
        preview_rows = preview_import(
            school_rows,
            academic_year_id=academic_year_id,
            stage=stage,
            subject_id=subject_id,
            teacher_binding_mode=teacher_binding_mode,
            selected_teacher_id=selected_teacher_id,
            selected_teacher_ids=selected_teacher_ids,
            selected_department_id=department_id,
        )

        preview_dir = Path(current_app.instance_path) / "olympiad_previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_id = str(uuid.uuid4())
        preview_file = preview_dir / f"{preview_id}.json"
        preview_file.write_text(json.dumps({"rows": school_rows}, ensure_ascii=False), encoding="utf-8")

        payload = {
            "academic_year_id": academic_year_id,
            "stage": stage,
            "subject_id": subject_id,
            "department_id": department_id,
            "mode": mode,
            "file_name": file.filename,
            "teacher_binding_mode": teacher_binding_mode,
            "selected_teacher_id": selected_teacher_id,
            "selected_teacher_ids": selected_teacher_ids,
            "preview_id": preview_id,
        }
        session["olympiad_import_preview"] = payload

        subject = Subject.query.get(subject_id) if subject_id else None
        teacher = User.query.get(selected_teacher_id) if selected_teacher_id else None
        department = Department.query.get(department_id) if department_id else None
        return render_template(
            "olympiad_import_preview.html",
            preview_rows=preview_rows,
            total_rows=len(rows),
            school_rows=len(school_rows),
            matched_rows=sum(1 for x in preview_rows if x.get("child") and x.get("subject")),
            unmatched_rows=sum(1 for x in preview_rows if not x.get("child") or not x.get("subject")),
            duplicate_rows=sum(1 for x in preview_rows if x.get("duplicate_status")),
            stage=stage,
            years=AcademicYear.query.order_by(AcademicYear.name.desc()).all(),
            academic_year_id=academic_year_id,
            subject=subject,
            teacher=teacher,
            department=department,
            unique_subjects=unique_subjects,
            payload=payload,
            teacher_binding_mode=teacher_binding_mode,
        )

    subject_id = request.args.get('subject_id', type=int)
    academic_year_id = request.args.get('academic_year_id', type=int) or (current_year.id if current_year else None)
    department_id = request.args.get('department_id', type=int)
    return render_template(
        "olympiad_import.html",
        years=AcademicYear.query.order_by(AcademicYear.name.desc()).all(),
        subjects=Subject.query.order_by(Subject.name.asc()).all(),
        departments=_allowed_departments(),
        stages=STAGES,
        current_year=current_year,
        selected_subject_id=subject_id,
        selected_department_id=department_id,
        selected_academic_year_id=academic_year_id,
        teachers_for_subject=_subject_teachers(subject_id, academic_year_id, department_id),
        olympiad_school_filter_values=_olympiad_school_filter_values(),
    )


@olympiads_bp.route("/import/commit", methods=["POST"])
@login_required
def import_commit():
    _deny_unless("olympiad_import")
    payload = session.get("olympiad_import_preview")
    if not payload:
        flash("Нет данных для импорта. Сначала загрузите файл.", "warning")
        return redirect(url_for("olympiads.import_view"))

    preview_id = payload.get("preview_id")
    rows = []
    if preview_id:
        preview_file = Path(current_app.instance_path) / "olympiad_previews" / f"{preview_id}.json"
        if preview_file.exists():
            stored = json.loads(preview_file.read_text(encoding="utf-8"))
            rows = stored.get("rows") or []

    if not rows:
        flash("Нет данных для импорта. Сначала загрузите файл.", "warning")
        return redirect(url_for("olympiads.import_view"))

    subject = Subject.query.get(payload.get("subject_id")) if payload.get("subject_id") else None
    import_session = execute_import(
        rows,
        academic_year_id=payload.get("academic_year_id"),
        stage=payload.get("stage"),
        subject_id=payload.get("subject_id"),
        subject_name=subject.name if subject else None,
        imported_by=current_user.id,
        teacher_binding_mode=payload.get('teacher_binding_mode') or 'auto',
        selected_teacher_id=payload.get('selected_teacher_id'),
        selected_teacher_ids=payload.get('selected_teacher_ids') or [],
        selected_department_id=payload.get('department_id'),
    )

    if preview_id:
        preview_file = Path(current_app.instance_path) / "olympiad_previews" / f"{preview_id}.json"
        if preview_file.exists():
            preview_file.unlink()

    session.pop("olympiad_import_preview", None)
    flash(
        f"Импорт завершён: создано {import_session.created_rows}, дубликатов {import_session.duplicate_rows}, несопоставлено {import_session.unmatched_rows}.",
        "success",
    )
    if import_session.comment:
        flash(import_session.comment, "warning" if import_session.unmatched_rows else "info")
    return redirect(url_for("olympiads.imports"))


@olympiads_bp.route("/imports")
@login_required
def imports():
    _deny_unless("olympiad_import")
    rows = OlympiadImportSession.query.order_by(OlympiadImportSession.created_at.desc()).all()
    return render_template("olympiad_imports.html", rows=rows)


@olympiads_bp.route("/imports/<int:session_id>/rollback", methods=["POST"])
@login_required
def rollback_import(session_id: int):
    _deny_unless("olympiad_import")
    import_session = OlympiadImportSession.query.get_or_404(session_id)
    OlympiadResult.query.filter_by(import_session_id=import_session.id).delete(synchronize_session=False)
    OlympiadUnmatchedRow.query.filter_by(import_session_id=import_session.id).delete(synchronize_session=False)
    db.session.delete(import_session)
    db.session.commit()
    flash("Импорт отменён. Все результаты этой загрузки удалены.", "success")
    return redirect(url_for("olympiads.imports"))


@olympiads_bp.route("/department")
@login_required
def department_registry():
    _deny_unless("olympiad_department_summary_view")
    ensure_olympiad_result_schema()
    department_id = request.args.get("department_id", type=int)
    academic_year_id = request.args.get("academic_year_id", type=int)
    subject_id = request.args.get("subject_id", type=int)
    stage = (request.args.get("stage") or "").strip()

    q = OlympiadResult.query.filter(OlympiadResult.is_archived.is_(False))
    if department_id:
        q = q.filter(OlympiadResult.department_id == department_id)
    if academic_year_id:
        q = q.filter(OlympiadResult.academic_year_id == academic_year_id)
    if subject_id:
        q = q.filter(OlympiadResult.subject_id == subject_id)
    if stage:
        q = q.filter(OlympiadResult.stage == stage)
    rows = q.order_by(OlympiadResult.created_at.desc()).limit(500).all()

    teachers = []
    if department_id:
        tq = db.session.query(User).join(TeacherLoad, TeacherLoad.teacher_id == User.id).filter(
            TeacherLoad.is_archived.is_(False),
            TeacherLoad.department_id == department_id,
        )
        if academic_year_id:
            tq = tq.filter((TeacherLoad.academic_year_id == academic_year_id) | (TeacherLoad.academic_year_id.is_(None)))
        teachers = tq.distinct().order_by(User.last_name.asc(), User.first_name.asc()).all()

    return render_template(
        "olympiad_department.html",
        rows=rows,
        teachers=teachers,
        departments=_allowed_departments(),
        years=AcademicYear.query.order_by(AcademicYear.name.desc()).all(),
        subjects=Subject.query.order_by(Subject.name.asc()).all(),
        stages=STAGES,
        department_id=department_id,
        academic_year_id=academic_year_id,
        subject_id=subject_id,
        stage=stage,
        stage_badge=stage_badge,
        stage_label=stage_label,
        status_label=status_label,
    )


@olympiads_bp.route("/department/<int:result_id>/assign-teacher", methods=["POST"])
@login_required
def department_assign_teacher(result_id: int):
    _deny_unless("olympiad_department_summary_view")
    result = OlympiadResult.query.get_or_404(result_id)
    teacher_id = request.form.get("teacher_id", type=int)
    if teacher_id:
        result.teacher_id = teacher_id
        result.teacher_binding_status = "manual"
        result.teacher_binding_source = "manual_single"
        result.teacher_binding_reason = "Учитель назначен вручную"
    if not result.department_id:
        result.department_id = request.form.get("department_id", type=int) or result.department_id
    db.session.commit()
    flash("Учитель назначен.", "success")
    return redirect(url_for("olympiads.department_registry", department_id=result.department_id, academic_year_id=result.academic_year_id))


@olympiads_bp.route("/unmatched")
@login_required
def unmatched():
    _deny_unless("olympiad_edit")
    q = OlympiadUnmatchedRow.query.order_by(OlympiadUnmatchedRow.created_at.desc())
    resolution_status = (request.args.get("resolution_status") or "OPEN").strip().upper()
    if resolution_status in {"OPEN", "RESOLVED"}:
        q = q.filter(OlympiadUnmatchedRow.resolution_status == resolution_status)
    rows = q.limit(500).all()
    return render_template(
        "olympiad_unmatched.html",
        rows=rows,
        children=Child.query.order_by(Child.last_name.asc(), Child.first_name.asc()).all(),
        departments=_allowed_departments(),
        resolution_status=resolution_status,
    )


@olympiads_bp.route("/unmatched/<int:row_id>/resolve", methods=["POST"])
@login_required
def unmatched_resolve(row_id: int):
    _deny_unless("olympiad_edit")
    row = OlympiadUnmatchedRow.query.get_or_404(row_id)
    child_id = request.form.get("child_id", type=int)
    teacher_id = request.form.get("teacher_id", type=int)
    department_id = request.form.get("department_id", type=int)
    mark_left = bool(request.form.get("maybe_left_school"))
    comment = (request.form.get("comment") or "").strip() or None
    row.resolved_child_id = child_id
    row.resolved_teacher_id = teacher_id
    row.resolved_department_id = department_id
    row.maybe_left_school = mark_left
    row.comment = comment
    row.resolution_status = "RESOLVED" if (child_id or mark_left or comment) else row.resolution_status
    db.session.commit()
    flash("Строка обновлена.", "success")
    return redirect(url_for("olympiads.unmatched"))


@olympiads_bp.route("/teacher-binding", methods=["GET", "POST"])
@login_required
def teacher_binding():
    _deny_unless("olympiad_edit")
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    academic_year_id = request.values.get("academic_year_id", type=int) or (current_year.id if current_year else None)
    stage = (request.values.get("stage") or "").strip()
    subject_id = request.values.get("subject_id", type=int)
    department_id = request.values.get("department_id", type=int)
    parallel = request.values.get("parallel", type=int)
    class_name = (request.values.get("class_name") or "").strip()
    status = (request.values.get("status") or "").strip()
    teacher_id = request.values.get("teacher_id", type=int)

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        if action in {"assign", "remove", "auto_apply"}:
            result_ids = [int(x) for x in (request.form.get("result_ids") or "").split(",") if x.strip().isdigit()]
            rows = OlympiadResult.query.filter(OlympiadResult.id.in_(result_ids)).all() if result_ids else []
            if action == "assign":
                teacher_id_form = request.form.get("assign_teacher_id", type=int)
                _apply_manual_binding(rows, teacher_id_form)
                db.session.commit()
                flash(f"Массово обновлено записей: {len(rows)}.", "success")
            elif action == "remove":
                _apply_manual_binding(rows, None)
                db.session.commit()
                flash(f"Снят учитель у записей: {len(rows)}.", "success")
            elif action == "auto_apply":
                updated = 0
                for row in rows:
                    if _apply_auto_binding(row):
                        updated += 1
                db.session.commit()
                flash(f"Автопривязка выполнена для записей: {updated}.", "success")
        return redirect(url_for("olympiads.teacher_binding", academic_year_id=academic_year_id or "", stage=stage, subject_id=subject_id or "", department_id=department_id or "", parallel=parallel or "", class_name=class_name, status=status, teacher_id=teacher_id or ""))

    groups_map = _binding_groups_query(academic_year_id=academic_year_id, stage=stage, subject_id=subject_id, department_id=department_id, parallel=parallel, class_name=class_name, status=status, teacher_id=teacher_id)
    groups = []
    class_options = set()
    for key, rows in groups_map.items():
        sample = rows[0]
        cls = sample.school_class.name if sample.school_class else (sample.class_study_text or "—")
        class_options.add(cls)
        teacher_ids = {r.teacher_id for r in rows if r.teacher_id}
        teacher = User.query.get(next(iter(teacher_ids))) if len(teacher_ids) == 1 else None
        source_set = {r.teacher_binding_source or "unassigned" for r in rows}
        status_set = {r.teacher_binding_status or "unassigned" for r in rows}
        reason_set = {r.teacher_binding_reason or "" for r in rows}
        grade = sample.school_class.grade if sample.school_class else None
        options = []
        if sample.subject_id:
            options = _subject_teachers(sample.subject_id, sample.academic_year_id, sample.department_id)
        if not options:
            options = User.query.order_by(User.last_name.asc(), User.first_name.asc()).all()
        groups.append({
            "year": sample.academic_year.name if sample.academic_year else "—",
            "stage": sample.stage or "—",
            "subject": sample.subject.name if sample.subject else (sample.subject_name or "—"),
            "class_name": cls,
            "parallel": grade,
            "count": len(rows),
            "teacher": teacher,
            "department": sample.department,
            "source": next(iter(source_set)) if len(source_set) == 1 else "mixed",
            "status": next(iter(status_set)) if len(status_set) == 1 else "mixed",
            "reason": next(iter(reason_set)) if len(reason_set) == 1 else "Смешанные причины / статусы",
            "result_ids": ",".join(str(r.id) for r in rows),
            "teacher_options": options,
        })
    groups.sort(key=lambda x: (x["year"], x["stage"], x["subject"], x["class_name"]))
    return render_template(
        "olympiad_teacher_binding.html",
        groups=groups,
        years=AcademicYear.query.order_by(AcademicYear.name.desc()).all(),
        subjects=Subject.query.order_by(Subject.name.asc()).all(),
        departments=_allowed_departments(),
        teachers=User.query.order_by(User.last_name.asc(), User.first_name.asc()).all(),
        stages=STAGES,
        academic_year_id=academic_year_id,
        stage=stage,
        subject_id=subject_id,
        department_id=department_id,
        parallel=parallel,
        class_name=class_name,
        status=status,
        teacher_id=teacher_id,
        class_options=sorted(class_options),
    )


@olympiads_bp.route("/analytics")
@login_required
def analytics():
    _deny_unless("olympiad_dashboard_view")
    ensure_olympiad_result_schema()
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    academic_year_id = request.args.get("academic_year_id", type=int) or (current_year.id if current_year else None)
    year_from_id = request.args.get("year_from_id", type=int)
    year_to_id = request.args.get("year_to_id", type=int)
    if year_from_id or year_to_id:
        academic_year_id = None
    teacher_id = request.args.get("teacher_id", type=int)
    department_id = request.args.get("department_id", type=int)
    stage_group = request.args.get("stage_group", "").strip()
    status_group = request.args.get("status_group", "").strip()

    # Response-кеш для /olympiads/analytics — 1.7 с из-за 6 агрегаций в all_analytics.
    # Ключ по фильтрам + department_ids роли (для teacher-view разные данные).
    allowed_dep_ids = _department_ids_for_user()
    cache_dep_key = ",".join(map(str, sorted(allowed_dep_ids))) if allowed_dep_ids is not None else "*"
    cache_key = make_key(
        "olympiads_analytics",
        cache_dep_key,
        academic_year_id or 0,
        teacher_id or 0,
        department_id or 0,
        stage_group or "",
        status_group or "",
        year_from_id or 0,
        year_to_id or 0,
    )
    cached_html = view_response_cache.get(cache_key)
    if cached_html is not None:
        from flask import Response
        return Response(cached_html, mimetype="text/html; charset=utf-8")

    summary, by_teacher, by_department, by_subject, by_class, comparison, movement, yearly_stage_rows = all_analytics(
        academic_year_id, teacher_id, department_id, stage_group, status_group, year_from_id, year_to_id
    )

    html = render_template(
        "olympiad_analytics.html",
        stats=summary or {},
        summary=summary or {},
        by_teacher=by_teacher or [],
        by_department=by_department or {},
        by_subject=by_subject or [],
        by_class=by_class or [],
        by_status=(summary.get("by_status") if summary else []) or [],
        comparison=comparison or [],
        yearly_rows=comparison or [],
        status_rows=(summary or {}).get("by_status", []),
        movement=movement or {},
        yearly_stage_rows=yearly_stage_rows or [],
        stage_labels=STAGE_LABELS,
        status_labels=STATUS_LABELS,
        years=AcademicYear.query.order_by(AcademicYear.name.desc()).all(),
        teachers=User.query.order_by(User.last_name.asc(), User.first_name.asc()).all(),
        departments=_allowed_departments(),
        academic_year_id=academic_year_id,
        teacher_id=teacher_id,
        department_id=department_id,
        stage_group=stage_group,
        status_group=status_group,
        year_from_id=year_from_id,
        year_to_id=year_to_id,
    )
    view_response_cache.set(cache_key, html, timeout=120)
    return html


@olympiads_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    _deny_unless("olympiad_settings_manage")
    if request.method == "POST":
        mapping_id = request.form.get("mapping_id", type=int)
        olympiad_name = (request.form.get("olympiad_name") or "").strip() or None
        olympiad_subject_name = (request.form.get("olympiad_subject_name") or "").strip()
        subject_id = request.form.get("subject_id", type=int)
        department_id = request.form.get("department_id", type=int)
        grade_from = request.form.get("grade_from", type=int)
        grade_to = request.form.get("grade_to", type=int)
        priority = request.form.get("priority", type=int) or 100
        linked_subject_ids = _mapping_linked_subject_ids_from_form()
        comment = (request.form.get("comment") or "").strip() or None
        is_active = bool(request.form.get("is_active"))

        if olympiad_subject_name and subject_id:
            if grade_from and grade_to and grade_from > grade_to:
                flash("Диапазон параллелей заполнен некорректно.", "danger")
                return redirect(url_for("olympiads.settings"))

            duplicate_q = OlympiadSubjectMapping.query.filter(
                OlympiadSubjectMapping.olympiad_subject_name == olympiad_subject_name,
                OlympiadSubjectMapping.olympiad_name == olympiad_name,
                OlympiadSubjectMapping.subject_id == subject_id,
                OlympiadSubjectMapping.department_id == department_id,
                OlympiadSubjectMapping.grade_from == grade_from,
                OlympiadSubjectMapping.grade_to == grade_to,
                OlympiadSubjectMapping.is_active.is_(True),
            )
            if mapping_id:
                duplicate_q = duplicate_q.filter(OlympiadSubjectMapping.id != mapping_id)
            duplicate = duplicate_q.first()
            if duplicate:
                flash("Такое активное сопоставление уже существует для этой параллели.", "warning")
                return redirect(url_for("olympiads.settings"))

            row = OlympiadSubjectMapping.query.get(mapping_id) if mapping_id else None
            if not row:
                row = OlympiadSubjectMapping()
                db.session.add(row)

            row.olympiad_name = olympiad_name
            row.olympiad_subject_name = olympiad_subject_name
            row.subject_id = subject_id
            row.linked_subject_ids = linked_subject_ids
            row.department_id = department_id
            row.grade_from = grade_from
            row.grade_to = grade_to
            row.priority = priority
            row.comment = comment
            row.is_active = is_active or request.form.get("mapping_id") is None
            try:
                db.session.commit()
                flash("Сопоставление предмета сохранено.", "success")
            except IntegrityError:
                db.session.rollback()
                flash(
                    "Не удалось сохранить запись. В базе осталась старая уникальная блокировка по названию олимпиадного предмета. "
                    "Перезапустите приложение с этой версией — при старте ограничение будет снято автоматически.",
                    "danger",
                )
        return redirect(url_for("olympiads.settings"))
    mappings = OlympiadSubjectMapping.query.order_by(
        OlympiadSubjectMapping.olympiad_subject_name.asc(),
        OlympiadSubjectMapping.priority.asc(),
        OlympiadSubjectMapping.grade_from.asc().nullsfirst(),
    ).all()
    return render_template(
        "olympiad_settings.html",
        mappings=mappings,
        subjects=Subject.query.order_by(Subject.name.asc()).all(),
        departments=Department.query.order_by(Department.name.asc()).all(),
        stages=STAGES,
        mapping_grade_label=_mapping_grade_label,
        mapping_linked_subject_names=_mapping_linked_subject_names,
    )


@olympiads_bp.route("/my")
@login_required
def my_results():
    _deny_unless("olympiad_view")
    q = OlympiadResult.query.filter(OlympiadResult.is_archived.is_(False))
    if current_user.role in {TEACHER, CLASS_TEACHER}:
        q = q.filter(OlympiadResult.teacher_id == current_user.id)
    rows = q.order_by(OlympiadResult.created_at.desc()).limit(300).all()
    return render_template("olympiad_my.html", rows=rows, stage_badge=stage_badge, stage_label=stage_label, status_label=status_label)
