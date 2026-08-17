from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app.core.extensions import db
from app.models import (
    AcademicYear,
    Department,
    DiagnosticImportBatch,
    DiagnosticKesResult,
    DiagnosticResult,
    DiagnosticSession,
    DiagnosticTaskResult,
    DiagnosticTeacherBinding,
    SchoolClass,
    TeacherLoad,
    User,
)
from app.models_legacy import DepartmentLeader
from app.permissions import has_role
from app.services.education_activity_service import (
    assign_subject_activity,
    get_subject_activity,
    list_subject_activities,
)
from app.modules.diagnostics.services.import_service import apply_preview, build_preview, build_report, load_preview, save_preview
from app.modules.diagnostics.repositories import (
    get_kes_rows_for_session,
    get_task_rows_for_results,
)
from app.modules.diagnostics.services.analytics_service import LEVEL_COLORS, LEVEL_ORDER, aggregate_results as modular_aggregate_results, build_tasks_table


diagnostics_bp = Blueprint("diagnostics", __name__, url_prefix="/diagnostics")

GROUP_SUBJECT_MARKERS = ["англий", "иностран", "немец", "француз", "испан"]


@diagnostics_bp.before_request
def _restrict_diagnostics_module():
    """School-wide MCKO data is available only to admins and methodists."""
    if not getattr(current_user, "is_authenticated", False):
        return None
    if not (has_role("ADMIN") or has_role("METHODIST")):
        abort(403)


# ------------------------------------------------------------
# BASIC HELPERS
# ------------------------------------------------------------
def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _norm(value: str | None) -> str:
    return " ".join(str(value or "").replace("ё", "е").replace("Ё", "Е").split()).strip().lower()


def _norm_class(value: str | None) -> str:
    return _norm(value).replace(" ", "")


def _extract_parallel_from_class_name(value: str | None) -> int | None:
    raw = (value or "").strip()
    digits = ""
    for ch in raw:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    try:
        return int(digits) if digits else None
    except Exception:
        return None


def _task_skill_label(task: DiagnosticTaskResult) -> str:
    for value in [getattr(task, "skill", None), getattr(task, "block_name", None), getattr(task, "kes_code", None)]:
        text = (value or "").strip()
        if text:
            return text
    return "—"




def _task_skill_candidates(task: DiagnosticTaskResult) -> list[str]:
    values = []
    for value in [getattr(task, "skill", None), getattr(task, "block_name", None), getattr(task, "kes_code", None)]:
        text = (value or "").strip()
        if text and text not in values:
            values.append(text)
    return values


def _choose_task_skill_label(task_rows: list[DiagnosticTaskResult]) -> str:
    if not task_rows:
        return "—"
    candidates: list[str] = []
    for task in task_rows:
        for value in _task_skill_candidates(task):
            if value and value not in candidates:
                candidates.append(value)
    if not candidates:
        return "—"

    def norm(value: str) -> str:
        return " ".join(value.lower().replace("ё", "е").split())

    best = candidates[0]
    for candidate in candidates[1:]:
        best_norm = norm(best)
        cand_norm = norm(candidate)
        if best_norm == cand_norm:
            if len(candidate) > len(best):
                best = candidate
            continue
        if best_norm and cand_norm.startswith(best_norm):
            best = candidate
            continue
        if cand_norm and best_norm.startswith(cand_norm):
            continue
        if len(candidate) > len(best):
            best = candidate
    return best
def _task_topic_label(task: DiagnosticTaskResult) -> str:
    for value in [getattr(task, "topic", None), getattr(task, "block_name", None)]:
        text = (value or "").strip()
        if text:
            return text

    skill = (getattr(task, "skill", None) or "").strip()
    if skill:
        for separator in [";", ":", ". " ]:
            if separator in skill:
                skill = skill.split(separator, 1)[0].strip()
                break
        if len(skill) > 120:
            skill = skill[:117].rstrip() + "..."
        if skill:
            return skill

    return "Без темы"


def _display_teacher(user: User | None) -> str:
    if not user:
        return "—"
    return (user.fio or user.username or "—").strip()


def _choose_kes_name(values: list[str]) -> str:
    cleaned = []
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        return "—"

    def norm(value: str) -> str:
        return " ".join(value.lower().replace("ё", "е").split())

    best = cleaned[0]
    for candidate in cleaned[1:]:
        best_norm = norm(best)
        cand_norm = norm(candidate)
        if best_norm == cand_norm:
            if len(candidate) > len(best):
                best = candidate
            continue
        if best_norm and cand_norm.startswith(best_norm):
            best = candidate
            continue
        if cand_norm and best_norm.startswith(cand_norm):
            continue
        if len(candidate) > len(best):
            best = candidate
    return best


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


VALID_MARK_VALUES = {"2", "3", "4", "5"}
PERCENT_MODE_BINS = [
    ("0–20%", 0, 20),
    ("21–40%", 21, 40),
    ("41–60%", 41, 60),
    ("61–80%", 61, 80),
    ("81–100%", 81, 100),
]


def _mark_display_label(result: DiagnosticResult) -> str | None:
    raw = str(getattr(result, "mark", "") or "").strip()
    return raw if raw in VALID_MARK_VALUES else None


def _detect_result_mode(rows: list[DiagnosticResult]) -> str:
    has_level = any((_result_display_label(row, row.session) or "") not in {"", "—"} for row in rows)
    has_mark = any(_mark_display_label(row) for row in rows)
    has_percent = any(_safe_float(getattr(row, "percent", None)) is not None for row in rows)
    if has_level and has_mark:
        return "mixed"
    if has_level:
        return "level"
    if has_mark:
        return "mark"
    if has_percent:
        return "percent"
    return "score"


def _aggregate_marks(rows: list[DiagnosticResult]) -> dict:
    counts = {key: 0 for key in ["5", "4", "3", "2"]}
    values = []
    for row in rows:
        mark = _mark_display_label(row)
        if mark:
            counts[mark] = counts.get(mark, 0) + 1
            values.append(int(mark))
    low_count = counts.get("2", 0)
    return {
        "counts": counts,
        "avg_mark": round(sum(values) / len(values), 2) if values else None,
        "low_count": low_count,
        "low_percent": round(low_count * 100 / len(rows), 1) if rows else 0,
    }


def _aggregate_percent_bands(rows: list[DiagnosticResult]) -> dict:
    buckets = {label: 0 for label, _, _ in PERCENT_MODE_BINS}
    low_count = 0
    scores = []
    percents = []
    for row in rows:
        percent = _safe_float(getattr(row, "percent", None))
        score = _safe_float(getattr(row, "total_score", None))
        if score is not None:
            scores.append(score)
        if percent is None:
            continue
        percents.append(percent)
        if percent <= 30:
            low_count += 1
        for label, left, right in PERCENT_MODE_BINS:
            if left <= percent <= right:
                buckets[label] += 1
                break
    return {
        "bands": buckets,
        "avg_percent": round(sum(percents) / len(percents), 1) if percents else None,
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "low_count": low_count,
        "low_percent": round(low_count * 100 / len(rows), 1) if rows else 0,
    }


def _result_display_label(result: DiagnosticResult, session: DiagnosticSession | None = None) -> str | None:
    raw = (getattr(result, "level", None) or getattr(result, "mark", None) or "").strip()
    if raw and raw not in {"-", "—"}:
        return raw
    current_session = session or getattr(result, "session", None)
    if current_session and current_session.diagnostic_type == "FG":
        score = getattr(result, "total_score", None)
        try:
            if score is not None and float(score) <= 7:
                return "Ниже базового"
        except Exception:
            pass
    return None


def _normalized_level_label(result: DiagnosticResult, session: DiagnosticSession | None = None) -> str:
    label = (_result_display_label(result, session) or "").strip().lower()
    if label in {"высокий", "высокий уровень"}:
        return "Высокий"
    if label in {"повышенный", "повышенный уровень"}:
        return "Повышенный"
    if label in {"базовый", "базовый уровень"}:
        return "Базовый"
    if label in {"низкий", "ниже базового", "нижебазового"}:
        return "Ниже базового"
    return "Без уровня"


# ------------------------------------------------------------
# ACCESS HELPERS
# ------------------------------------------------------------
def _current_role_code() -> str:
    return str(getattr(current_user, "role", "") or "").upper()


def _is_admin() -> bool:
    return has_role("ADMIN") or _current_role_code() == "ADMIN"


def _is_methodist() -> bool:
    return has_role("METHODIST") or _current_role_code() == "METHODIST"


def _is_class_teacher() -> bool:
    return has_role("CLASS_TEACHER") or _current_role_code() == "CLASS_TEACHER"


def _is_teacher() -> bool:
    return has_role("TEACHER") or _current_role_code() == "TEACHER"


def _is_social_pedagog() -> bool:
    return has_role("SOCIAL_PEDAGOG") or _current_role_code() == "SOCIAL_PEDAGOG"


def _leader_department_ids() -> list[int]:
    if not getattr(current_user, "id", None):
        return []
    return [
        row.department_id
        for row in DepartmentLeader.query.filter_by(user_id=current_user.id).all()
        if getattr(row, "department_id", None)
    ]


def _visible_department_ids() -> list[int]:
    leader_ids = _leader_department_ids()
    if leader_ids:
        return sorted(set(leader_ids))
    if _is_teacher():
        return sorted(
            {
                row.department_id
                for row in TeacherLoad.query.filter_by(teacher_id=current_user.id, is_archived=False).all()
                if row.department_id
            }
        )
    return []


def _teacher_visible_class_names() -> set[str]:
    values = set()
    if _is_class_teacher():
        for school_class in SchoolClass.query.filter_by(teacher_user_id=current_user.id, is_archived=False).all():
            if school_class.name:
                values.add(_norm_class(school_class.name))
    if _is_teacher():
        for load in TeacherLoad.query.filter_by(teacher_id=current_user.id, is_archived=False).all():
            if load.class_name:
                values.add(_norm_class(load.class_name))
    return values


def _can_manage_diagnostics() -> bool:
    return _is_admin() or _is_social_pedagog()


def _can_import_diagnostics() -> bool:
    return _is_admin() or _is_social_pedagog()


def _can_edit_binding() -> bool:
    return _is_admin() or _is_methodist() or _is_social_pedagog() or bool(_leader_department_ids())


def _ensure_can_manage():
    if not _can_manage_diagnostics():
        abort(403)


def _ensure_can_import():
    if not _can_import_diagnostics():
        abort(403)


def _apply_results_visibility(results: list[DiagnosticResult]) -> list[DiagnosticResult]:
    if _is_admin() or _is_social_pedagog():
        return results

    leader_department_ids = set(_leader_department_ids())
    visible_classes = _teacher_visible_class_names()
    filtered = []
    for row in results:
        binding = getattr(row, "teacher_binding", None)
        class_name = _norm_class(row.class_name_raw or (row.school_class.name if row.school_class else ""))

        if _is_methodist() and not leader_department_ids:
            filtered.append(row)
            continue

        if leader_department_ids:
            teacher_id = binding.teacher_id if binding else None
            if not teacher_id:
                continue
            teacher_deps = {
                load.department_id
                for load in TeacherLoad.query.filter_by(teacher_id=teacher_id, is_archived=False).all()
                if load.department_id
            }
            if teacher_deps.intersection(leader_department_ids):
                filtered.append(row)
            continue

        if _is_class_teacher() and class_name and class_name in visible_classes:
            filtered.append(row)
            continue

        if _is_teacher() and binding and binding.teacher_id == current_user.id:
            filtered.append(row)
            continue

    return filtered


def _visible_sessions_with_stats() -> list[DiagnosticSession]:
    sessions = DiagnosticSession.query.order_by(DiagnosticSession.created_at.desc()).all()
    if _is_admin() or _is_social_pedagog() or (_is_methodist() and not _leader_department_ids()):
        return sessions

    visible_ids = set()
    for row in _apply_results_visibility(DiagnosticResult.query.filter_by(is_final=True).all()):
        visible_ids.add(row.session_id)
    return [session for session in sessions if session.id in visible_ids]


def _result_department_name(result: DiagnosticResult) -> str:
    binding = getattr(result, "teacher_binding", None)
    if not binding or not binding.teacher_id:
        return "—"
    load = (
        TeacherLoad.query.filter_by(teacher_id=binding.teacher_id, is_archived=False)
        .filter(TeacherLoad.department_id.isnot(None))
        .order_by(TeacherLoad.id.asc())
        .first()
    )
    if load and load.department:
        return load.department.name
    return "—"


# ------------------------------------------------------------
# LOAD MATCHING / BINDING HELPERS
# ------------------------------------------------------------
def _is_group_subject(subject_name: str, matches: list[TeacherLoad]) -> bool:
    normalized = _norm(subject_name)
    if any(marker in normalized for marker in GROUP_SUBJECT_MARKERS):
        return True
    for load in matches:
        if (load.group_name or "").strip():
            return True
        if getattr(load, "is_whole_class", None) is False:
            return True
        if getattr(load, "is_meta_group", None):
            return True
    return False


def _match_teacher_loads(current_year: AcademicYear | None, result: DiagnosticResult, all_loads: list[TeacherLoad]):
    session = result.session
    subject_activity_id = (
        session.education_activity_id
        if session
        else None
    )
    subject_name = (
        (
            session.education_activity.name
            if session and session.education_activity
            else session.subject
        )
        or ""
    ).strip() if session else ""
    class_name = (result.class_name_raw or (result.school_class.name if result.school_class else "") or "").strip()
    result_year_id = session.academic_year_id if session and session.academic_year_id else (current_year.id if current_year else None)

    matches = []
    for load in all_loads:
        if load.is_archived:
            continue
        if result_year_id and load.academic_year_id and load.academic_year_id != result_year_id:
            continue

        same_subject = True
        if subject_activity_id:
            same_subject = load.education_activity_id == subject_activity_id
        elif subject_name and load.subject_name:
            same_subject = _norm(load.subject_name) == _norm(subject_name)
        elif subject_name and getattr(load, "subject", None) and getattr(load.subject, "name", None):
            same_subject = _norm(load.subject.name) == _norm(subject_name)

        same_class = True
        if class_name and load.class_name:
            same_class = _norm_class(load.class_name) == _norm_class(class_name)
        elif class_name and load.grade:
            same_class = _norm_class(class_name).startswith(str(load.grade))

        if same_subject and same_class:
            matches.append(load)

    unique_teachers = []
    seen = set()
    for load in matches:
        teacher = getattr(load, "teacher", None)
        if teacher and teacher.id not in seen:
            unique_teachers.append(teacher)
            seen.add(teacher.id)

    group_subject = _is_group_subject(subject_name, matches)
    auto_teacher = unique_teachers[0] if len(unique_teachers) == 1 and not group_subject else None
    disputed = (len(unique_teachers) > 1) or (group_subject and len(unique_teachers) >= 1)

    return {
        "subject_name": subject_name or "—",
        "class_name": class_name or "—",
        "matches": matches,
        "teachers": unique_teachers,
        "group_subject": group_subject,
        "auto_teacher": auto_teacher,
        "disputed": disputed,
    }


def _auto_bind_session_results(session: DiagnosticSession, overwrite_auto: bool = False) -> int:
    current_year = AcademicYear.query.filter_by(is_current=True).first()
    target_year = session.academic_year if getattr(session, "academic_year", None) else current_year

    load_q = TeacherLoad.query.filter(TeacherLoad.is_archived.is_(False))
    if session.academic_year_id:
        load_q = load_q.filter(or_(TeacherLoad.academic_year_id == session.academic_year_id, TeacherLoad.academic_year_id.is_(None)))
    all_loads = load_q.all()

    changed = 0
    results = DiagnosticResult.query.filter_by(session_id=session.id, is_final=True).all()
    for result in results:
        binding = result.teacher_binding
        if binding and binding.source == "manual":
            continue

        match_info = _match_teacher_loads(target_year, result, all_loads)
        auto_teacher = match_info.get("auto_teacher")
        if not auto_teacher:
            if overwrite_auto and binding and binding.source in {"auto", "auto_load"}:
                db.session.delete(binding)
                changed += 1
            continue

        if not binding:
            binding = DiagnosticTeacherBinding(result_id=result.id)
            db.session.add(binding)

        if binding.teacher_id != auto_teacher.id or binding.source != "auto_load" or (binding.comment or "") != "Автоматическая привязка из педагогической нагрузки":
            binding.teacher_id = auto_teacher.id
            binding.source = "auto_load"
            binding.comment = "Автоматическая привязка из педагогической нагрузки"
            changed += 1
    return changed


def _aggregate_results(rows: list[DiagnosticResult]) -> dict:
    return modular_aggregate_results(
        rows,
        level_getter=lambda row: _normalized_level_label(row, row.session),
        percent_getter=lambda row: _safe_float(getattr(row, "percent", None)),
        score_getter=lambda row: _safe_float(getattr(row, "total_score", None)),
        binding_getter=lambda row: bool(getattr(row, "teacher_binding", None) and row.teacher_binding.teacher_id),
    )


def _task_success_percent(task_rows: list[DiagnosticTaskResult]) -> float | None:
    from app.modules.diagnostics.services.analytics_service import task_success_percent
    return task_success_percent(task_rows)


# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------
@diagnostics_bp.route("/")
@login_required
def index():
    academic_year_id = request.args.get("academic_year_id", type=int)
    diagnostic_type = (request.args.get("diagnostic_type") or "").strip()
    subject_id = request.args.get("subject_id", type=int)
    parallel_filter = request.args.get("parallel", type=int)
    status_filter = (request.args.get("status") or "").strip()

    years = AcademicYear.query.order_by(AcademicYear.name.desc()).all()
    subjects = list_subject_activities()
    all_rows = _visible_sessions_with_stats()

    # s85: фильтруем сначала, потом подгружаем статистику только по нужным сессиям.
    pre_filtered = []
    for row in all_rows:
        if academic_year_id and row.academic_year_id != academic_year_id:
            continue
        if diagnostic_type and row.diagnostic_type != diagnostic_type:
            continue
        if subject_id and row.education_activity_id != subject_id:
            continue
        if parallel_filter and row.parallel != parallel_filter:
            continue
        if status_filter and row.status != status_filter:
            continue
        pre_filtered.append(row)

    # s85: батч-запросы вместо N+1 — все агрегации одним SQL на отфильтрованные сессии.
    session_ids = [r.id for r in pre_filtered]
    visible_results_by_session = {}
    imports_count_by_session = {}
    sessions_with_any_result = set()
    if session_ids:
        all_visible = _apply_results_visibility(
            DiagnosticResult.query
            .filter(DiagnosticResult.session_id.in_(session_ids), DiagnosticResult.is_final == True)
            .all()
        )
        for item in all_visible:
            visible_results_by_session.setdefault(item.session_id, []).append(item)
        for sid, cnt in (
            db.session.query(DiagnosticImportBatch.session_id, func.count(DiagnosticImportBatch.id))
            .filter(DiagnosticImportBatch.session_id.in_(session_ids))
            .group_by(DiagnosticImportBatch.session_id)
            .all()
        ):
            imports_count_by_session[sid] = cnt
        sessions_with_any_result = {
            sid for (sid,) in (
                db.session.query(DiagnosticResult.session_id)
                .filter(DiagnosticResult.session_id.in_(session_ids))
                .distinct()
                .all()
            )
        }

    rows = []
    can_manage = _can_manage_diagnostics()
    for row in pre_filtered:
        visible_results = visible_results_by_session.get(row.id, [])
        bound_count = sum(1 for item in visible_results if item.teacher_binding and item.teacher_binding.teacher_id)
        imports_count = imports_count_by_session.get(row.id, 0)
        row.can_delete = can_manage and imports_count == 0 and row.id not in sessions_with_any_result
        row.imports_count = imports_count
        row.results_count = len(visible_results)
        row.bound_count = bound_count
        row.has_binding = bound_count > 0
        rows.append(row)

    return render_template(
        "diagnostics/diagnostics_list.html",
        rows=rows,
        years=years,
        subjects=subjects,
        current_year_id=academic_year_id,
        diagnostic_type=diagnostic_type,
        selected_subject_id=subject_id,
        parallel_filter=parallel_filter,
        status_filter=status_filter,
        can_manage=_can_manage_diagnostics(),
    )


@diagnostics_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    _ensure_can_manage()
    years = AcademicYear.query.order_by(AcademicYear.name.desc()).all()
    subjects = list_subject_activities()
    if request.method == "POST":
        activity = get_subject_activity(
            request.form.get("education_activity_id", type=int)
        )
        if activity is None:
            flash("Выберите предмет из единого каталога.", "danger")
            return render_template(
                "diagnostics/diagnostics_form.html",
                years=years,
                subjects=subjects,
                session_obj=None,
            )
        session = DiagnosticSession(
            title=(request.form.get("title") or "").strip() or "Новая диагностика",
            diagnostic_type=(request.form.get("diagnostic_type") or "MCKO").strip(),
            parallel=request.form.get("parallel", type=int),
            date_main=_parse_date(request.form.get("date_main")),
            date_reserve=_parse_date(request.form.get("date_reserve")),
            academic_year_id=request.form.get("academic_year_id", type=int),
            status="draft",
            created_by=current_user.id,
        )
        assign_subject_activity(session, activity)
        db.session.add(session)
        db.session.commit()
        flash("Карточка диагностики создана.", "success")
        return redirect(url_for("diagnostics.detail", session_id=session.id))
    return render_template("diagnostics/diagnostics_form.html", years=years, subjects=subjects, session_obj=None)


@diagnostics_bp.route("/<int:session_id>/edit", methods=["GET", "POST"])
@login_required
def edit(session_id: int):
    _ensure_can_manage()
    session = DiagnosticSession.query.get_or_404(session_id)
    years = AcademicYear.query.order_by(AcademicYear.name.desc()).all()
    subjects = list_subject_activities()
    if request.method == "POST":
        activity = get_subject_activity(
            request.form.get("education_activity_id", type=int)
        )
        if activity is None:
            flash("Выберите предмет из единого каталога.", "danger")
            return render_template(
                "diagnostics/diagnostics_form.html",
                years=years,
                subjects=subjects,
                session_obj=session,
            )
        session.title = (request.form.get("title") or "").strip() or session.title
        session.diagnostic_type = (request.form.get("diagnostic_type") or session.diagnostic_type or "MCKO").strip()
        assign_subject_activity(session, activity)
        session.parallel = request.form.get("parallel", type=int)
        session.date_main = _parse_date(request.form.get("date_main"))
        session.date_reserve = _parse_date(request.form.get("date_reserve"))
        session.academic_year_id = request.form.get("academic_year_id", type=int)
        db.session.commit()
        auto_bound = 0
        if session.subject:
            auto_bound = _auto_bind_session_results(session, overwrite_auto=True)
            if auto_bound:
                db.session.commit()
        flash(f"Диагностика обновлена. Автопривязка учителей: {auto_bound}.", "success")
        return redirect(url_for("diagnostics.detail", session_id=session.id))
    return render_template("diagnostics/diagnostics_form.html", years=years, subjects=subjects, session_obj=session)


@diagnostics_bp.route("/<int:session_id>/delete", methods=["POST"])
@login_required
def delete_session(session_id: int):
    _ensure_can_manage()
    session = DiagnosticSession.query.get_or_404(session_id)
    has_imports = DiagnosticImportBatch.query.filter_by(session_id=session.id).first() is not None
    has_results = DiagnosticResult.query.filter_by(session_id=session.id).first() is not None
    if has_imports or has_results:
        flash("Нельзя удалить диагностику, по которой уже есть импорт или результаты.", "danger")
        return redirect(url_for("diagnostics.index"))
    db.session.delete(session)
    db.session.commit()
    flash("Диагностика удалена.", "success")
    return redirect(url_for("diagnostics.index"))


@diagnostics_bp.route("/<int:session_id>")
@login_required
def detail(session_id: int):
    session = DiagnosticSession.query.get_or_404(session_id)
    year_filter = request.args.get("academic_year_id", type=int)
    class_filter = (request.args.get("class_name") or "").strip()
    student_query = (request.args.get("student") or "").strip()
    only_unbound = request.args.get("only_unbound") in {"1", "true", "on", "yes"}

    raw_rows = DiagnosticResult.query.filter_by(session_id=session.id, is_final=True).order_by(DiagnosticResult.class_name_raw.asc(), DiagnosticResult.full_name_raw.asc()).all()
    visible_rows = _apply_results_visibility(raw_rows)

    if year_filter and session.academic_year_id != year_filter:
        visible_rows = []
    if class_filter:
        class_norm = _norm_class(class_filter)
        visible_rows = [row for row in visible_rows if _norm_class(row.class_name_raw or (row.school_class.name if row.school_class else "")) == class_norm]
    if student_query:
        q = _norm(student_query)
        visible_rows = [
            row for row in visible_rows
            if q in _norm(row.full_name_raw or (row.child.fio if row.child else "")) or q in _norm(row.participant_code)
        ]
    if only_unbound:
        visible_rows = [row for row in visible_rows if not row.teacher_binding or not row.teacher_binding.teacher_id]

    stats = _aggregate_results(visible_rows)
    result_mode = _detect_result_mode(visible_rows)
    mark_summary = _aggregate_marks(visible_rows)
    percent_summary = _aggregate_percent_bands(visible_rows)
    class_options = sorted({(row.class_name_raw or (row.school_class.name if row.school_class else "") or "—").strip() for row in _apply_results_visibility(raw_rows) if (row.class_name_raw or (row.school_class.name if row.school_class else ""))})
    years = AcademicYear.query.order_by(AcademicYear.name.desc()).all()

    return render_template(
        "diagnostics/diagnostics_card.html",
        session=session,
        rows=visible_rows,
        stats=stats,
        result_mode=result_mode,
        mark_summary=mark_summary,
        percent_summary=percent_summary,
        years=years,
        class_options=class_options,
        class_filter=class_filter,
        student_query=student_query,
        only_unbound=only_unbound,
        result_display_label=_result_display_label,
        mark_display_label=_mark_display_label,
        can_manage=_can_manage_diagnostics(),
        can_import=_can_import_diagnostics(),
        current_year_id=year_filter,
    )


@diagnostics_bp.route("/<int:session_id>/import", methods=["GET", "POST"])
@login_required
def import_view(session_id: int):
    _ensure_can_import()
    session = DiagnosticSession.query.get_or_404(session_id)
    if request.method == "POST":
        result_zip = request.files.get("result_zip")
        codes_zip = request.files.get("codes_zip")
        reserve = request.form.get("source_kind") == "reserve"
        if not result_zip or not result_zip.filename:
            flash("Загрузите архив результатов.", "danger")
            return redirect(url_for("diagnostics.import_view", session_id=session.id))
        try:
            preview = build_preview(result_zip, codes_zip=codes_zip if codes_zip and codes_zip.filename else None, reserve=reserve, session_id=session.id)
            preview_id = save_preview(preview)
            return redirect(url_for("diagnostics.preview", session_id=session.id, preview_id=preview_id, filename=result_zip.filename))
        except Exception as exc:
            flash(f"Ошибка разбора архива: {exc}", "danger")
            return redirect(url_for("diagnostics.import_view", session_id=session.id))
    return render_template("diagnostics/diagnostics_import.html", session=session)


@diagnostics_bp.route("/<int:session_id>/preview/<preview_id>", methods=["GET", "POST"])
@login_required
def preview(session_id: int, preview_id: str):
    _ensure_can_import()
    session = DiagnosticSession.query.get_or_404(session_id)
    preview = load_preview(preview_id)
    if request.method == "POST":
        actions = {k.split("action_", 1)[1]: v for k, v in request.form.items() if k.startswith("action_")}
        filename = request.args.get("filename") or request.form.get("filename") or "diagnostics.zip"
        apply_preview(session, preview, actions, filename=filename, created_by=current_user.id)
        auto_bound = _auto_bind_session_results(session)
        if auto_bound:
            db.session.commit()
        flash(f"Импорт завершён. Автопривязка учителей: {auto_bound}.", "success")
        return redirect(url_for("diagnostics.detail", session_id=session.id))
    return render_template(
        "diagnostics/diagnostics_preview.html",
        session=session,
        preview=preview,
        preview_id=preview_id,
        filename=request.args.get("filename") or "diagnostics.zip",
        result_display_label=_result_display_label,
    )


@diagnostics_bp.route("/<int:session_id>/report")
@login_required
def report(session_id: int):
    DiagnosticSession.query.get_or_404(session_id)
    return redirect(url_for("diagnostics.analytics", session_id=session_id))


@diagnostics_bp.route("/imports")
@login_required
def imports_registry():
    _ensure_can_import()
    rows = DiagnosticImportBatch.query.order_by(DiagnosticImportBatch.created_at.desc()).all()
    for row in rows:
        row.results_count = DiagnosticResult.query.filter_by(import_batch_id=row.id).count()
    return render_template("diagnostics/diagnostics_imports_registry.html", rows=rows, can_manage=_can_manage_diagnostics())


@diagnostics_bp.route("/imports/<int:batch_id>/delete", methods=["GET", "POST"])
@login_required
def delete_import(batch_id: int):
    _ensure_can_import()
    batch = DiagnosticImportBatch.query.get_or_404(batch_id)
    if request.method == "POST":
        result_ids = [row.id for row in DiagnosticResult.query.filter_by(import_batch_id=batch.id).all()]
        if result_ids:
            DiagnosticTeacherBinding.query.filter(DiagnosticTeacherBinding.result_id.in_(result_ids)).delete(synchronize_session=False)
            DiagnosticTaskResult.query.filter(DiagnosticTaskResult.result_id.in_(result_ids)).delete(synchronize_session=False)
            DiagnosticResult.query.filter(DiagnosticResult.replaced_result_id.in_(result_ids)).update({DiagnosticResult.replaced_result_id: None}, synchronize_session=False)
            DiagnosticResult.query.filter(DiagnosticResult.id.in_(result_ids)).delete(synchronize_session=False)
        db.session.delete(batch)
        db.session.commit()
        flash("Импорт удалён.", "success")
        return redirect(url_for("diagnostics.imports_registry"))
    rows_count = DiagnosticResult.query.filter_by(import_batch_id=batch.id).count()
    return render_template("diagnostics/diagnostics_import_delete.html", batch=batch, rows_count=rows_count)


@diagnostics_bp.route("/analytics")
@login_required
def analytics():
    session_id = request.args.get("session_id", type=int)
    parallel_filter = request.args.get("parallel", type=int)
    class_filter = (request.args.get("class_name") or "").strip()
    subject_id = request.args.get("subject_id", type=int)
    teacher_id = request.args.get("teacher_id", type=int)

    all_sessions = _visible_sessions_with_stats()
    if not session_id and all_sessions:
        session_id = all_sessions[0].id

    # s85: фильтр по session_id уходит в SQL вместо Python; полная история не грузится.
    rows_q = DiagnosticResult.query.filter_by(is_final=True)
    if session_id:
        rows_q = rows_q.filter(DiagnosticResult.session_id == session_id)
    rows = rows_q.order_by(DiagnosticResult.class_name_raw.asc(), DiagnosticResult.full_name_raw.asc()).all()
    rows = _apply_results_visibility(rows)

    selected_session = next((s for s in all_sessions if s.id == session_id), None)
    session_rows = rows  # фильтр по session_id уже применён в SQL

    available_parallels = []
    parallel_seen = set()
    for row in session_rows:
        parallel = _extract_parallel_from_class_name(row.class_name_raw or (row.school_class.name if row.school_class else "")) or (selected_session.parallel if selected_session else None)
        if parallel is not None and parallel not in parallel_seen:
            available_parallels.append(parallel)
            parallel_seen.add(parallel)
    if selected_session and selected_session.parallel and selected_session.parallel not in parallel_seen:
        available_parallels.append(selected_session.parallel)
    available_parallels = sorted(available_parallels)

    if parallel_filter is None and len(available_parallels) == 1:
        parallel_filter = available_parallels[0]

    class_options = []
    class_seen = set()
    teacher_seen = set()
    teacher_options = []
    for row in session_rows:
        class_name = (row.class_name_raw or (row.school_class.name if row.school_class else "") or "").strip()
        if class_name:
            row_parallel = _extract_parallel_from_class_name(class_name) or (selected_session.parallel if selected_session else None)
            if not parallel_filter or row_parallel == parallel_filter:
                key = _norm_class(class_name)
                if key not in class_seen:
                    class_options.append(class_name)
                    class_seen.add(key)
        if row.teacher_binding and row.teacher_binding.teacher and row.teacher_binding.teacher.id not in teacher_seen:
            teacher_options.append(row.teacher_binding.teacher)
            teacher_seen.add(row.teacher_binding.teacher.id)
    class_options.sort(key=lambda x: (_extract_parallel_from_class_name(x) or 0, x))
    teacher_options.sort(key=lambda x: ((x.last_name or ""), (x.first_name or ""), (x.username or "")))

    filtered = []
    for row in session_rows:
        session = row.session
        class_name = (row.class_name_raw or (row.school_class.name if row.school_class else "") or "").strip()
        row_parallel = _extract_parallel_from_class_name(class_name) or (selected_session.parallel if selected_session else None)
        binding = getattr(row, "teacher_binding", None)
        if parallel_filter and row_parallel != parallel_filter:
            continue
        if class_filter and _norm_class(class_name) != _norm_class(class_filter):
            continue
        if subject_id and session.education_activity_id != subject_id:
            continue
        if teacher_id and (not binding or binding.teacher_id != teacher_id):
            continue
        filtered.append(row)

    filtered.sort(key=lambda r: (
        _extract_parallel_from_class_name(r.class_name_raw or (r.school_class.name if r.school_class else "") or "") or 0,
        (r.class_name_raw or (r.school_class.name if r.school_class else "") or ""),
        0 if _normalized_level_label(r, r.session) == "Ниже базового" else 1,
        (r.full_name_raw or (r.child.fio if r.child else "") or ""),
    ))

    summary = _aggregate_results(filtered)
    summary["diagnostics"] = 1 if selected_session else 0
    result_mode = _detect_result_mode(filtered)
    mark_summary = _aggregate_marks(filtered)
    percent_summary = _aggregate_percent_bands(filtered)

    classes_table = []
    teachers_table = []
    kes_table = []
    below_basic_table = []

    class_groups = defaultdict(list)
    teacher_groups = defaultdict(list)
    department_groups = defaultdict(list)

    for row in filtered:
        class_name = (row.class_name_raw or (row.school_class.name if row.school_class else "") or "Без класса").strip()
        class_groups[class_name].append(row)
        if row.teacher_binding and row.teacher_binding.teacher:
            teacher_groups[row.teacher_binding.teacher_id].append(row)
            department_name = _result_department_name(row)
            department_groups[department_name].append(row)

    visible_result_ids = {row.id for row in filtered}
    task_rows = get_task_rows_for_results(visible_result_ids) if visible_result_ids else []
    tasks_table = build_tasks_table(task_rows)

    low_result_label = "Ниже базового"
    summary_metric_label = "Средний балл"
    summary_metric_value = summary.get("avg_score") if summary.get("avg_score") is not None else (summary.get("avg_percent") if summary.get("avg_percent") is not None else "—")
    distribution_title = "Распределение результатов"
    distribution_labels = []
    distribution_values = []

    if result_mode == "mark":
        low_result_label = "Отметка 2"
        summary_metric_label = "Средняя отметка"
        summary_metric_value = mark_summary.get("avg_mark") if mark_summary.get("avg_mark") is not None else "—"
        distribution_title = "Распределение отметок"
        distribution_labels = ["5", "4", "3", "2"]
        distribution_values = [mark_summary["counts"].get(label, 0) for label in distribution_labels]
    elif result_mode in {"percent", "score"}:
        low_result_label = "Низкий результат"
        summary_metric_label = "Средний результат"
        summary_metric_value = percent_summary.get("avg_score") if percent_summary.get("avg_score") is not None else (percent_summary.get("avg_percent") if percent_summary.get("avg_percent") is not None else "—")
        distribution_title = "Распределение по % выполнения"
        distribution_labels = [label for label, _, _ in PERCENT_MODE_BINS]
        distribution_values = [percent_summary["bands"].get(label, 0) for label in distribution_labels]
    else:
        distribution_labels = list(LEVEL_ORDER)
        distribution_values = [summary["levels"].get(label, 0) for label in distribution_labels]

    def build_group_stats(group: list[DiagnosticResult]) -> dict:
        agg = _aggregate_results(group)
        mark_agg = _aggregate_marks(group)
        percent_agg = _aggregate_percent_bands(group)
        if result_mode == "mark":
            low_count = mark_agg["low_count"]
            low_percent = mark_agg["low_percent"]
        elif result_mode in {"percent", "score"}:
            low_count = percent_agg["low_count"]
            low_percent = percent_agg["low_percent"]
        else:
            low_count = agg["levels"].get("Ниже базового", 0)
            low_percent = round(low_count * 100 / agg["count"], 1) if agg["count"] else 0
        return {
            **agg,
            "mark_summary": mark_agg,
            "percent_summary": percent_agg,
            "low_count": low_count,
            "low_percent": low_percent,
        }

    for class_name, group in class_groups.items():
        agg = build_group_stats(group)
        below_basic_table.append({
            "class_name": class_name,
            "parallel": _extract_parallel_from_class_name(class_name),
            "below_basic_count": agg["low_count"],
            "below_basic_percent": agg["low_percent"],
            **agg,
        })
        classes_table.append({"class_name": class_name, **agg})
    classes_table.sort(key=lambda x: ((x["avg_percent"] or 0), -(x["low_count"])), reverse=True)
    below_basic_table.sort(key=lambda x: (x["below_basic_count"], x["below_basic_percent"], -(x["avg_percent"] or 0)), reverse=True)

    for teacher_key, group in teacher_groups.items():
        agg = build_group_stats(group)
        teacher = group[0].teacher_binding.teacher
        class_names = sorted({(r.class_name_raw or (r.school_class.name if r.school_class else "") or "—").strip() for r in group})
        teachers_table.append({
            "teacher": teacher,
            "classes": ", ".join(class_names),
            "below_basic_percent": agg["low_percent"],
            **agg,
        })
    teachers_table.sort(key=lambda x: ((x["avg_percent"] or 0), -(x["low_count"])), reverse=True)

    departments_table = []
    student_rows = list(filtered)
    for department_name, group in department_groups.items():
        agg = build_group_stats(group)
        departments_table.append({
            "department_name": department_name or "—",
            "below_basic_percent": agg["low_percent"],
            **agg,
        })
    departments_table.sort(key=lambda x: ((x["avg_percent"] or 0), -(x["low_count"])), reverse=True)

    visible_class_names = {_norm_class((row.class_name_raw or (row.school_class.name if row.school_class else "") or "").strip()) for row in filtered}
    kes_rows = get_kes_rows_for_session(selected_session.id) if selected_session else []
    kes_buckets = {}
    for row in kes_rows:
        class_name = (row.class_name_raw or "").strip()
        row_parallel = _extract_parallel_from_class_name(class_name) or (selected_session.parallel if selected_session else None)
        if parallel_filter and row_parallel != parallel_filter:
            continue
        if class_filter and _norm_class(class_name) != _norm_class(class_filter):
            continue
        if visible_class_names and class_name and _norm_class(class_name) not in visible_class_names and class_filter:
            continue

        kes_code = (row.kes_code or "—").strip() or "—"
        key = kes_code
        bucket = kes_buckets.setdefault(
            key,
            {
                "kes_names": [],
                "class_percents": [],
                "city_percents": [],
                "classes": set(),
            },
        )
        kes_name = (row.kes_name or "").strip()
        if kes_name:
            bucket["kes_names"].append(kes_name)
        if row.class_percent is not None:
            bucket["class_percents"].append(row.class_percent)
        if row.city_percent is not None:
            bucket["city_percents"].append(row.city_percent)
        if class_name:
            bucket["classes"].add(_norm_class(class_name))

    for kes_code, bucket in kes_buckets.items():
        class_avg = round(sum(bucket["class_percents"]) / len(bucket["class_percents"]), 2) if bucket["class_percents"] else None
        city_avg = round(sum(bucket["city_percents"]) / len(bucket["city_percents"]), 2) if bucket["city_percents"] else None
        gap = round(class_avg - city_avg, 2) if class_avg is not None and city_avg is not None else None
        kes_table.append({
            "kes_code": kes_code,
            "kes_name": _choose_kes_name(bucket["kes_names"]),
            "class_percent": class_avg,
            "city_percent": city_avg,
            "gap": gap,
            "classes_count": len(bucket["classes"]),
        })
    kes_table.sort(key=lambda x: (999 if x["class_percent"] is None else x["class_percent"], x["kes_code"]))

    class_chart = [{"label": item["class_name"], "avg_percent": item["avg_percent"] or 0} for item in classes_table[:20]]
    below_basic_chart = [{"label": item["class_name"], "below_basic_count": item["below_basic_count"]} for item in below_basic_table[:20]]
    kes_chart = [
        {
            "label": f"{item['kes_code']}",
            "class_percent": item["class_percent"] or 0,
            "city_percent": item["city_percent"] or 0,
        }
        for item in kes_table[:12]
        if item.get("class_percent") is not None or item.get("city_percent") is not None
    ]

    subject_options = list_subject_activities()

    return render_template(
        "diagnostics/diagnostics_analytics.html",
        all_sessions=all_sessions,
        selected_session=selected_session,
        selected_session_id=session_id,
        parallel_filter=parallel_filter,
        class_filter=class_filter,
        selected_subject_id=subject_id,
        teacher_filter=teacher_id,
        parallel_options=available_parallels,
        class_options=class_options,
        teacher_options=teacher_options,
        subject_options=subject_options,
        summary=summary,
        result_mode=result_mode,
        mark_summary=mark_summary,
        percent_summary=percent_summary,
        summary_metric_label=summary_metric_label,
        summary_metric_value=summary_metric_value,
        low_result_label=low_result_label,
        distribution_title=distribution_title,
        distribution_labels=distribution_labels,
        distribution_values=distribution_values,
        level_order=LEVEL_ORDER,
        level_colors=LEVEL_COLORS,
        classes_table=classes_table,
        teachers_table=teachers_table,
        departments_table=departments_table,
        tasks_table=tasks_table,
        student_rows=student_rows,
        show_class_comparison=not bool(class_filter),
        kes_table=kes_table,
        kes_chart=kes_chart,
        below_basic_table=below_basic_table,
        class_chart=class_chart,
        below_basic_chart=below_basic_chart,
        rows=filtered,
        result_display_label=_result_display_label,
        mark_display_label=_mark_display_label,
        display_teacher=_display_teacher,
    )


@diagnostics_bp.route("/departments")
@login_required
def departments_summary():
    departments = Department.query.order_by(Department.name.asc()).all()
    blocks = []
    visible_rows = _apply_results_visibility(DiagnosticResult.query.filter_by(is_final=True).all())

    def build_group_stats(group: list[DiagnosticResult], result_mode: str) -> dict:
        agg = _aggregate_results(group)
        mark_agg = _aggregate_marks(group)
        percent_agg = _aggregate_percent_bands(group)
        if result_mode == "mark":
            low_count = mark_agg["low_count"]
            low_percent = mark_agg["low_percent"]
        elif result_mode in {"percent", "score"}:
            low_count = percent_agg["low_count"]
            low_percent = percent_agg["low_percent"]
        else:
            low_count = agg["levels"].get("Ниже базового", 0)
            low_percent = round(low_count * 100 / agg["count"], 1) if agg["count"] else 0
        return {
            **agg,
            "mark_summary": mark_agg,
            "percent_summary": percent_agg,
            "low_count": low_count,
            "low_percent": low_percent,
        }

    for department in departments:
        dep_rows = [row for row in visible_rows if _result_department_name(row) == department.name]
        session_ids = sorted({row.session_id for row in dep_rows})
        sessions = DiagnosticSession.query.filter(DiagnosticSession.id.in_(session_ids)).all() if session_ids else []
        sessions_by_id = {session.id: session for session in sessions}
        result_mode = _detect_result_mode(dep_rows)
        stats = build_group_stats(dep_rows, result_mode) if dep_rows else {
            "count": 0,
            "avg_score": None,
            "avg_percent": None,
            "levels": {},
            "with_binding": 0,
            "mark_summary": _aggregate_marks([]),
            "percent_summary": _aggregate_percent_bands([]),
            "low_count": 0,
            "low_percent": 0,
        }

        subjects = sorted({(sessions_by_id.get(row.session_id).subject or "—").strip() if sessions_by_id.get(row.session_id) else "—" for row in dep_rows})
        teachers_map = {}
        for row in dep_rows:
            binding = getattr(row, 'teacher_binding', None)
            if binding and binding.teacher:
                teachers_map[binding.teacher.id] = binding.teacher
        subject_groups = defaultdict(list)
        teacher_groups = defaultdict(list)
        work_groups = defaultdict(list)
        for row in dep_rows:
            session = sessions_by_id.get(row.session_id)
            subject_name = ((session.subject if session else None) or "—").strip() or "—"
            subject_groups[subject_name].append(row)
            binding = getattr(row, 'teacher_binding', None)
            teacher_key = binding.teacher_id if binding and binding.teacher_id else 0
            teacher_groups[teacher_key].append(row)
            work_groups[row.session_id].append(row)

        subject_rows = []
        for subject_name, group in subject_groups.items():
            agg = build_group_stats(group, result_mode)
            subject_rows.append({
                "subject_name": subject_name,
                **agg,
            })
        subject_rows.sort(key=lambda item: (item["subject_name"] != "—", item["subject_name"]))

        teacher_rows = []
        for teacher_id, group in teacher_groups.items():
            teacher = teachers_map.get(teacher_id)
            agg = build_group_stats(group, result_mode)
            class_names = sorted({(r.class_name_raw or (r.school_class.name if r.school_class else "") or "—").strip() for r in group})
            teacher_rows.append({
                "teacher": teacher,
                "teacher_name": _display_teacher(teacher) if teacher else "Не привязан",
                "classes": ", ".join(class_names),
                **agg,
            })
        teacher_rows.sort(key=lambda item: item["teacher_name"])

        work_rows = []
        for session_id, group in work_groups.items():
            session = sessions_by_id.get(session_id)
            agg = build_group_stats(group, result_mode)
            work_rows.append({
                "session": session,
                "title": (session.title if session else f"Диагностика #{session_id}"),
                "diagnostic_type": (session.diagnostic_type if session else "—"),
                "subject_name": ((session.subject if session else None) or "—").strip() or "—",
                **agg,
            })
        work_rows.sort(key=lambda item: (item["subject_name"], item["title"]))

        blocks.append({
            "department": department,
            "teachers_count": len(teachers_map),
            "sessions_count": len(session_ids),
            "sessions": sorted(sessions, key=lambda s: (s.subject or "", s.title or ""))[:5],
            "bound_results": len(dep_rows),
            "result_mode": result_mode,
            "stats": stats,
            "subject_rows": subject_rows,
            "teacher_rows": teacher_rows,
            "work_rows": work_rows,
            "show_subjects": len(subject_rows) > 1,
            "show_teachers": len([row for row in teacher_rows if row["teacher_name"] != "Не привязан"]) > 1,
            "show_works": len(work_rows) > 1,
        })
    if _leader_department_ids():
        blocks = [item for item in blocks if item["department"].id in set(_leader_department_ids())]
    return render_template("diagnostics/diagnostics_departments_summary.html", blocks=blocks)


@diagnostics_bp.route("/binding", methods=["GET", "POST"])
@login_required
def teacher_binding():
    if not (_can_edit_binding() or _is_admin() or _is_methodist() or _is_class_teacher() or _is_teacher()):
        abort(403)

    current_year = AcademicYear.query.filter_by(is_current=True).first()
    selected_year_id = request.values.get("academic_year_id", type=int) or (current_year.id if current_year else None)
    session_id = request.values.get("session_id", type=int)
    subject_id = request.values.get("subject_id", type=int)
    parallel_filter = request.values.get("parallel", type=int)
    class_filter = (request.values.get("class_name") or "").strip()
    teacher_filter = request.values.get("teacher_id", type=int)
    status_filter = (request.values.get("status") or "").strip()
    only_unassigned = request.values.get("only_unassigned") in {"1", "true", "on", "yes"}
    selected_class_focus = (request.values.get("focus_class") or "").strip()

    sessions = _visible_sessions_with_stats()
    years = AcademicYear.query.order_by(AcademicYear.name.desc()).all()
    teachers = User.query.order_by(User.last_name.asc(), User.first_name.asc(), User.username.asc()).all()

    results_q = DiagnosticResult.query.join(DiagnosticSession, DiagnosticSession.id == DiagnosticResult.session_id).filter(DiagnosticResult.is_final.is_(True)).order_by(DiagnosticResult.created_at.desc())
    if selected_year_id:
        results_q = results_q.filter(or_(DiagnosticSession.academic_year_id == selected_year_id, DiagnosticSession.academic_year_id.is_(None)))
    if session_id:
        results_q = results_q.filter(DiagnosticResult.session_id == session_id)
    if subject_id:
        results_q = results_q.filter(
            DiagnosticSession.education_activity_id == subject_id,
        )
    if parallel_filter:
        results_q = results_q.filter(DiagnosticSession.parallel == parallel_filter)

    raw_results = _apply_results_visibility(results_q.limit(800).all())
    if class_filter:
        class_norm = _norm_class(class_filter)
        raw_results = [row for row in raw_results if _norm_class(row.class_name_raw or (row.school_class.name if row.school_class else "")) == class_norm]

    load_q = TeacherLoad.query.filter(TeacherLoad.is_archived.is_(False))
    if selected_year_id:
        load_q = load_q.filter(or_(TeacherLoad.academic_year_id == selected_year_id, TeacherLoad.academic_year_id.is_(None)))
    all_loads = load_q.all()
    current_year_obj = AcademicYear.query.get(selected_year_id) if selected_year_id else current_year

    binding_rows = []
    class_binding_map = {}
    for row in raw_results:
        match_info = _match_teacher_loads(current_year_obj, row, all_loads)
        binding = row.teacher_binding
        current_teacher = binding.teacher if binding and binding.teacher else None
        source = (binding.source if binding else "") or ""
        if binding and current_teacher:
            if source == "manual":
                status = "manual"
            elif source == "auto_class":
                status = "auto"
            else:
                status = "auto"
        else:
            status = "disputed" if match_info["disputed"] else "unassigned"
        if only_unassigned and status != "unassigned":
            continue
        if status_filter and status != status_filter:
            continue
        if teacher_filter and (not current_teacher or current_teacher.id != teacher_filter):
            continue
        row_item = {
            "result": row,
            "session": row.session,
            "subject_name": match_info["subject_name"],
            "class_name": match_info["class_name"],
            "candidate_teachers": match_info["teachers"],
            "candidate_teacher_names": [_display_teacher(t) for t in match_info["teachers"]],
            "current_teacher": current_teacher,
            "current_teacher_name": _display_teacher(current_teacher) if current_teacher else "—",
            "status": status,
            "status_label": {
                "auto": "Автоматически назначено",
                "manual": "Назначено вручную",
                "unassigned": "Не назначено",
                "disputed": "Требует уточнения",
            }.get(status, "—"),
            "source_label": {
                "auto_load": "auto_load",
                "auto_class": "auto_class",
                "manual": "manual",
                "auto": "auto_load",
            }.get(source, source or "—"),
            "comment": (binding.comment if binding else None) or ("Групповой предмет / несколько педагогов" if match_info["disputed"] else ("Один учитель найден в нагрузке" if match_info["auto_teacher"] else "Учитель не найден в нагрузке")),
            "auto_teacher": match_info["auto_teacher"],
        }
        binding_rows.append(row_item)

        key = (row.session_id, match_info["class_name"], match_info["subject_name"])
        bucket = class_binding_map.setdefault(key, {"rows": [], "teachers": {}, "session": row.session, "class_name": match_info["class_name"], "subject_name": match_info["subject_name"]})
        bucket["rows"].append(row_item)
        for teacher in match_info["teachers"]:
            bucket["teachers"][teacher.id] = teacher

    if request.method == "POST":
        action = request.form.get("action") or "save"
        changed = 0

        if action == "auto_apply":
            for row in binding_rows:
                result = row["result"]
                if result.teacher_binding:
                    continue
                if row["auto_teacher"]:
                    db.session.add(DiagnosticTeacherBinding(result_id=result.id, teacher_id=row["auto_teacher"].id, source="auto_load", comment="Автоматическая привязка из педагогической нагрузки"))
                    changed += 1
            db.session.commit()
            flash(f"Автоматическая привязка выполнена: {changed} строк.", "success")
        elif action == "apply_class_binding":
            if not _can_edit_binding():
                abort(403)
            target_session_id = request.form.get("target_session_id", type=int)
            target_class_name = (request.form.get("target_class_name") or "").strip()
            teacher_id = request.form.get("target_teacher_id", type=int)
            for row in binding_rows:
                if row["result"].session_id != target_session_id or row["class_name"] != target_class_name:
                    continue
                binding = DiagnosticTeacherBinding.query.filter_by(result_id=row["result"].id).first()
                if not binding:
                    binding = DiagnosticTeacherBinding(result_id=row["result"].id)
                    db.session.add(binding)
                binding.teacher_id = teacher_id
                binding.source = "auto_class"
                binding.comment = f"Быстрая привязка по классу: {target_class_name}"
                changed += 1
            db.session.commit()
            flash(f"Быстрая привязка по классу выполнена: {changed} строк.", "success")
        elif action == "bulk_assign":
            if not _can_edit_binding():
                abort(403)
            teacher_id = request.form.get("bulk_teacher_id", type=int)
            selected_ids = [int(v) for v in request.form.getlist("selected_result_ids") if str(v).isdigit()]
            if not selected_ids:
                flash("Не выбраны строки для массового назначения.", "warning")
            elif not teacher_id:
                flash("Не выбран учитель для массового назначения.", "warning")
            else:
                teacher = User.query.get(teacher_id)
                for result_id in selected_ids:
                    binding = DiagnosticTeacherBinding.query.filter_by(result_id=result_id).first()
                    if not binding:
                        binding = DiagnosticTeacherBinding(result_id=result_id)
                        db.session.add(binding)
                    binding.teacher_id = teacher_id
                    binding.source = "manual"
                    binding.comment = f"Массовое назначение: {_display_teacher(teacher)}"
                    changed += 1
                db.session.commit()
                flash(f"Учитель назначен для {changed} строк.", "success")
        else:
            if not _can_edit_binding():
                abort(403)
            for row in binding_rows:
                result_id = row["result"].id
                teacher_id = request.form.get(f"teacher_id_{result_id}", type=int)
                comment = (request.form.get(f"comment_{result_id}") or "").strip() or None
                binding = DiagnosticTeacherBinding.query.filter_by(result_id=result_id).first()
                if teacher_id:
                    if not binding:
                        binding = DiagnosticTeacherBinding(result_id=result_id)
                        db.session.add(binding)
                    binding.teacher_id = teacher_id
                    binding.source = "manual"
                    binding.comment = comment or "Ручная корректировка привязки"
                    changed += 1
                elif binding:
                    db.session.delete(binding)
                    changed += 1
            db.session.commit()
            flash(f"Изменения сохранены: {changed} строк.", "success")

        return redirect(url_for("diagnostics.teacher_binding", academic_year_id=selected_year_id or "", session_id=session_id or "", subject_id=subject_id or "", parallel=parallel_filter or "", class_name=class_filter, teacher_id=teacher_filter or "", status=status_filter, only_unassigned=1 if only_unassigned else "", focus_class=selected_class_focus))

    status_counts = defaultdict(int)
    for row in binding_rows:
        status_counts[row["status"]] += 1

    quick_class_rows = []
    for (_, class_name, subject_name), bucket in sorted(class_binding_map.items(), key=lambda x: (x[0][1], x[0][2])):
        teachers_found = list(bucket["teachers"].values())
        current_teacher = None
        if bucket["rows"]:
            first_binding = bucket["rows"][0]["current_teacher"]
            if first_binding:
                current_teacher = first_binding
        quick_class_rows.append({
            "session": bucket["session"],
            "class_name": class_name,
            "subject_name": subject_name,
            "teachers_found": teachers_found,
            "teachers_found_names": [_display_teacher(t) for t in teachers_found],
            "suggested_teacher": teachers_found[0] if len(teachers_found) == 1 and not _is_group_subject(subject_name, []) else None,
            "current_teacher": current_teacher,
            "results_count": len(bucket["rows"]),
            "requires_attention": len(teachers_found) != 1 or any(row["status"] == "disputed" for row in bucket["rows"]),
        })

    if selected_class_focus:
        binding_rows = [row for row in binding_rows if row["class_name"] == selected_class_focus]

    return render_template(
        "diagnostics/diagnostics_teacher_binding.html",
        years=years,
        sessions=sessions,
        subjects=list_subject_activities(),
        teachers=teachers,
        binding_rows=binding_rows,
        quick_class_rows=quick_class_rows,
        current_year_id=selected_year_id,
        current_session_id=session_id,
        selected_subject_id=subject_id,
        parallel_filter=parallel_filter,
        class_filter=class_filter,
        teacher_filter=teacher_filter,
        status_filter=status_filter,
        only_unassigned=only_unassigned,
        status_counts=status_counts,
        focus_class=selected_class_focus,
        can_edit_binding=_can_edit_binding(),
    )
