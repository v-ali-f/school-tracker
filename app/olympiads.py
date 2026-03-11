from __future__ import annotations

import json
import uuid
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from . import db
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
from .services.olympiad_import_service import execute_import, extract_unique_subjects, filter_school_rows, preview_import, read_excel, read_zip
from .services.olympiad_stats_service import class_stats, dashboard_stats, department_stats, subject_stats, teacher_stats, yearly_comparison

olympiads_bp = Blueprint("olympiads", __name__, url_prefix="/olympiads")
STAGES = ["школьный", "муниципальный", "региональный", "заключительный"]


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


@olympiads_bp.route("/")
@login_required
def registry():
    _deny_unless("olympiad_view")
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    academic_year_id = request.args.get("academic_year_id", type=int) or (current_year.id if current_year else None)
    stage = (request.args.get("stage") or "").strip()
    subject_id = request.args.get("subject_id", type=int)
    teacher_id = request.args.get("teacher_id", type=int)
    department_id = request.args.get("department_id", type=int)
    status = request.args.get("status", "").strip()
    child_q = request.args.get("child", "").strip()

    allowed_dep_ids = _department_ids_for_user()
    if allowed_dep_ids is not None:
        if department_id and department_id not in allowed_dep_ids:
            abort(403)
        if not department_id and len(allowed_dep_ids) == 1:
            department_id = allowed_dep_ids[0]

    rows_q = OlympiadResult.query.filter(OlympiadResult.is_archived.is_(False))
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
    if status:
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
    teacher_options_by_result = {row.id: _teacher_options_for_result(row) for row in rows}
    return render_template(
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
        child_q=child_q,
    )


@olympiads_bp.route("/<int:result_id>/assign-teacher", methods=["POST"])
@login_required
def assign_teacher(result_id: int):
    _deny_unless("olympiad_edit")
    result = OlympiadResult.query.get_or_404(result_id)
    teacher_id = request.form.get("teacher_id", type=int)
    if teacher_id:
        result.teacher_id = teacher_id
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
        school_rows = filter_school_rows(rows, use_login=use_login, use_ekis=use_ekis, use_name=True)
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
    )


@olympiads_bp.route("/department/<int:result_id>/assign-teacher", methods=["POST"])
@login_required
def department_assign_teacher(result_id: int):
    _deny_unless("olympiad_department_summary_view")
    result = OlympiadResult.query.get_or_404(result_id)
    teacher_id = request.form.get("teacher_id", type=int)
    if teacher_id:
        result.teacher_id = teacher_id
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


@olympiads_bp.route("/analytics")
@login_required
def analytics():
    _deny_unless("olympiad_dashboard_view")
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    academic_year_id = request.args.get("academic_year_id", type=int) or (current_year.id if current_year else None)
    teacher_id = request.args.get("teacher_id", type=int)
    department_id = request.args.get("department_id", type=int)

    summary = dashboard_stats(academic_year_id)
    by_teacher = teacher_stats(academic_year_id, teacher_id)
    by_department = department_stats(academic_year_id, department_id)
    by_subject = subject_stats(academic_year_id)
    by_class = class_stats(academic_year_id)
    comparison = yearly_comparison()

    return render_template(
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
        years=AcademicYear.query.order_by(AcademicYear.name.desc()).all(),
        teachers=User.query.order_by(User.last_name.asc(), User.first_name.asc()).all(),
        departments=_allowed_departments(),
        academic_year_id=academic_year_id,
        teacher_id=teacher_id,
        department_id=department_id,
    )


@olympiads_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    _deny_unless("olympiad_settings_manage")
    if request.method == "POST":
        mapping_id = request.form.get("mapping_id", type=int)
        olympiad_subject_name = (request.form.get("olympiad_subject_name") or "").strip()
        subject_id = request.form.get("subject_id", type=int)
        department_id = request.form.get("department_id", type=int)
        comment = (request.form.get("comment") or "").strip() or None
        is_active = bool(request.form.get("is_active"))
        if olympiad_subject_name and subject_id:
            row = OlympiadSubjectMapping.query.get(mapping_id) if mapping_id else OlympiadSubjectMapping.query.filter(
                db.func.lower(OlympiadSubjectMapping.olympiad_subject_name) == olympiad_subject_name.lower()
            ).first()
            if not row:
                row = OlympiadSubjectMapping(
                    olympiad_subject_name=olympiad_subject_name,
                    subject_id=subject_id,
                    department_id=department_id,
                    comment=comment,
                    is_active=is_active or request.form.get("mapping_id") is None,
                )
                db.session.add(row)
            else:
                row.olympiad_subject_name = olympiad_subject_name
                row.subject_id = subject_id
                row.department_id = department_id
                row.comment = comment
                row.is_active = is_active
            db.session.commit()
            flash("Сопоставление предмета сохранено.", "success")
        return redirect(url_for("olympiads.settings"))
    return render_template(
        "olympiad_settings.html",
        mappings=OlympiadSubjectMapping.query.order_by(OlympiadSubjectMapping.olympiad_subject_name.asc()).all(),
        subjects=Subject.query.order_by(Subject.name.asc()).all(),
        departments=Department.query.order_by(Department.name.asc()).all(),
        stages=STAGES,
    )


@olympiads_bp.route("/my")
@login_required
def my_results():
    _deny_unless("olympiad_view")
    q = OlympiadResult.query.filter(OlympiadResult.is_archived.is_(False))
    if current_user.role in {TEACHER, CLASS_TEACHER}:
        q = q.filter(OlympiadResult.teacher_id == current_user.id)
    rows = q.order_by(OlympiadResult.created_at.desc()).limit(300).all()
    return render_template("olympiad_my.html", rows=rows)
