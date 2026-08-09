from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.core.extensions import db
from app.models import (
    AcademicYear,
    Department,
    DepartmentLeader,
    TeacherAttestation,
    TeacherMckoResult,
    User,
)
from app.permissions import has_any_role
from app.services.education_activity_service import assign_subject_activity, list_subject_activities
from app.services.teacher_mcko_registry_service import (
    mcko_registry_summary,
    remaining_period_label,
    teacher_mcko_registry_rows,
)
from app.services.teacher_mcko_service import MCKO_LEVEL_LABELS, mcko_expires_at, normalize_mcko_level
from app.services.teacher_attestation_registry_service import (
    attestation_registry_summary,
    attestation_remaining_period_label,
    teacher_attestation_registry_rows,
)
from app.services.teacher_attestation_service import (
    ATTESTATION_CATEGORY_LABELS,
    position_compliance_due_at,
)
from app.services.teacher_professional_audit_service import (
    CHANGE_ARCHIVED,
    CHANGE_CREATED,
    CHANGE_UPDATED,
    record_professional_change,
)


professional_registry_bp = Blueprint(
    "professional_registry",
    __name__,
    url_prefix="/professional-registers",
)

VIEW_ROLES = ("ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR", "METHODIST", "DEPARTMENT_HEAD")


def _role_codes():
    return {str(code).upper() for code in getattr(current_user, "role_codes", [])}


def _can_view():
    return has_any_role(*VIEW_ROLES)


def _can_manage():
    return bool(_role_codes().intersection({"ADMIN", "DEPUTY_DIRECTOR"}))


def _managed_department_ids():
    if not has_any_role("DEPARTMENT_HEAD") or has_any_role("ADMIN", "DIRECTOR", "DEPUTY_DIRECTOR", "METHODIST"):
        return None
    return {
        row.department_id
        for row in DepartmentLeader.query.filter_by(user_id=current_user.id).all()
    }


def _require_view():
    if not _can_view():
        abort(403)


def _require_manage():
    if not _can_manage():
        abort(403)


def _parse_date(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _teacher_options():
    rows = teacher_mcko_registry_rows()
    by_id = {row.teacher.id: row.teacher for row in rows}
    return sorted(by_id.values(), key=lambda item: (item.fio or item.username).casefold())


def _attestation_teacher_options():
    rows = teacher_attestation_registry_rows()
    return [row.teacher for row in rows]


def _form_context(record=None):
    return {
        "record": record,
        "teachers": _teacher_options(),
        "activities": list_subject_activities(),
        "levels": MCKO_LEVEL_LABELS,
    }


def _apply_form(record):
    teacher = User.query.filter_by(
        id=request.form.get("teacher_id", type=int),
        is_active_user=True,
        employment_status="ACTIVE",
    ).first()
    activity = next(
        (
            item
            for item in list_subject_activities()
            if item.id == request.form.get("education_activity_id", type=int)
        ),
        None,
    )
    passed_at = _parse_date(request.form.get("passed_at"))
    level = normalize_mcko_level(request.form.get("level"))
    if teacher is None:
        raise ValueError("Выберите педагога.")
    if activity is None:
        raise ValueError("Выберите предмет диагностики.")
    if passed_at is None:
        raise ValueError("Укажите корректную дату сертификата.")
    if level is None:
        raise ValueError("Выберите уровень результата.")

    record.teacher_id = teacher.id
    assign_subject_activity(record, activity)
    record.passed_at = passed_at
    record.expires_at = mcko_expires_at(passed_at)
    record.level = level
    record.certificate_number = (request.form.get("certificate_number") or "").strip() or None
    record.result_text = (request.form.get("result_text") or "").strip() or None
    record.updated_by_user_id = current_user.id
    return record


def _attestation_form_context(record=None):
    selected_teacher_id = (
        record.teacher_id
        if record and record.teacher_id
        else request.values.get("teacher_id", type=int)
    )
    selected_teacher = (
        db.session.get(User, selected_teacher_id)
        if selected_teacher_id
        else None
    )
    return {
        "record": record,
        "teachers": _attestation_teacher_options(),
        "categories": ATTESTATION_CATEGORY_LABELS,
        "selected_teacher": selected_teacher,
    }


def _apply_attestation_form(record):
    teacher = User.query.filter_by(
        id=request.form.get("teacher_id", type=int),
        is_active_user=True,
        employment_status="ACTIVE",
    ).first()
    category = (request.form.get("category") or "").strip().upper()
    decision_date = _parse_date(request.form.get("decision_date"))
    if teacher is None:
        raise ValueError("Выберите педагога.")
    if category not in ATTESTATION_CATEGORY_LABELS:
        raise ValueError("Выберите вид аттестации.")
    if decision_date is None:
        raise ValueError("Укажите корректную дату решения.")

    employment_start_raw = (request.form.get("employment_start_date") or "").strip()
    employment_start_date = _parse_date(employment_start_raw) if employment_start_raw else None
    if employment_start_raw and employment_start_date is None:
        raise ValueError("Укажите корректную дату приёма на работу.")
    if employment_start_date and employment_start_date > decision_date:
        raise ValueError("Дата приёма не может быть позже даты решения.")

    is_indefinite = (
        category in {"FIRST", "HIGHEST"}
        and (request.form.get("term_type") or "").strip().upper() == "INDEFINITE"
    )
    valid_until = _parse_date(request.form.get("valid_until"))
    if category == "POSITION_COMPLIANCE":
        is_indefinite = False
        valid_until = position_compliance_due_at(
            None,
            last_decision_date=decision_date,
        )
    elif is_indefinite:
        valid_until = None
    elif valid_until is None:
        raise ValueError("Для срочной категории укажите дату окончания.")
    if valid_until and valid_until < decision_date:
        raise ValueError("Срок действия не может завершаться раньше даты решения.")

    if employment_start_date is not None:
        teacher.employment_start_date = employment_start_date
    record.teacher_id = teacher.id
    record.category = category
    record.position_title = (request.form.get("position_title") or "").strip() or None
    record.decision_date = decision_date
    record.valid_until = valid_until
    record.is_indefinite = is_indefinite
    record.order_number = (request.form.get("order_number") or "").strip() or None
    record.notes = (request.form.get("notes") or "").strip() or None
    record.updated_by_user_id = current_user.id
    return record


@professional_registry_bp.get("/mcko")
@login_required
def mcko_registry():
    _require_view()
    allowed_department_ids = _managed_department_ids()
    selected_department = request.args.get("department_id", type=int)
    selected_activity = request.args.get("activity_id", type=int)
    status = (request.args.get("status") or "").strip().upper()
    expiry = (request.args.get("expiry") or "").strip().upper()
    rows = teacher_mcko_registry_rows(
        search=request.args.get("q"),
        department_id=selected_department,
        activity_id=selected_activity,
        status=status or None,
        expiry=expiry or None,
        allowed_department_ids=allowed_department_ids,
    )
    department_query = Department.query
    if allowed_department_ids is not None:
        department_query = department_query.filter(
            Department.id.in_(allowed_department_ids or {-1})
        )
    return render_template(
        "professional_registry/mcko_registry.html",
        rows=rows,
        summary=mcko_registry_summary(rows),
        departments=department_query.order_by(Department.name.asc()).all(),
        activities=list_subject_activities(),
        can_manage=_can_manage(),
        remaining_period_label=remaining_period_label,
    )


@professional_registry_bp.route("/mcko/new", methods=["GET", "POST"])
@login_required
def mcko_new():
    _require_manage()
    if request.method == "POST":
        current_year = AcademicYear.query.filter_by(is_current=True).first()
        retention_until = None
        if current_year and current_year.end_date:
            try:
                retention_until = current_year.end_date.replace(year=current_year.end_date.year + 7)
            except ValueError:
                retention_until = current_year.end_date.replace(year=current_year.end_date.year + 7, day=28)
        record = TeacherMckoResult(
            entry_source="ADMINISTRATION",
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
            academic_year_id=current_year.id if current_year else None,
            retention_until=retention_until,
        )
        try:
            _apply_form(record)
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("professional_registry/mcko_form.html", **_form_context(record)), 400
        db.session.add(record)
        db.session.flush()
        record_professional_change(record, change_kind=CHANGE_CREATED, actor_id=current_user.id)
        db.session.commit()
        flash("Результат МЦКО добавлен.", "success")
        return redirect(url_for("professional_registry.mcko_registry"))
    return render_template("professional_registry/mcko_form.html", **_form_context())


@professional_registry_bp.route("/mcko/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
def mcko_edit(record_id):
    _require_manage()
    record = TeacherMckoResult.query.filter_by(id=record_id, is_archived=False).first_or_404()
    if request.method == "POST":
        try:
            _apply_form(record)
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("professional_registry/mcko_form.html", **_form_context(record)), 400
        record_professional_change(record, change_kind=CHANGE_UPDATED, actor_id=current_user.id)
        db.session.commit()
        flash("Результат МЦКО обновлён.", "success")
        return redirect(url_for("professional_registry.mcko_registry"))
    return render_template("professional_registry/mcko_form.html", **_form_context(record))


@professional_registry_bp.post("/mcko/<int:record_id>/archive")
@login_required
def mcko_archive(record_id):
    _require_manage()
    record = TeacherMckoResult.query.filter_by(id=record_id, is_archived=False).first_or_404()
    record.is_archived = True
    record.updated_by_user_id = current_user.id
    record_professional_change(record, change_kind=CHANGE_ARCHIVED, actor_id=current_user.id)
    db.session.commit()
    flash("Запись МЦКО перенесена в архив.", "success")
    return redirect(url_for("professional_registry.mcko_registry"))


@professional_registry_bp.get("/attestations")
@login_required
def attestation_registry():
    _require_view()
    allowed_department_ids = _managed_department_ids()
    selected_department = request.args.get("department_id", type=int)
    category = (request.args.get("category") or "").strip().upper()
    status = (request.args.get("status") or "").strip().upper()
    expiry = (request.args.get("expiry") or "").strip().upper()
    rows = teacher_attestation_registry_rows(
        search=request.args.get("q"),
        department_id=selected_department,
        category=category or None,
        status=status or None,
        expiry=expiry or None,
        allowed_department_ids=allowed_department_ids,
    )
    department_query = Department.query
    if allowed_department_ids is not None:
        department_query = department_query.filter(
            Department.id.in_(allowed_department_ids or {-1})
        )
    return render_template(
        "professional_registry/attestation_registry.html",
        rows=rows,
        summary=attestation_registry_summary(rows),
        departments=department_query.order_by(Department.name.asc()).all(),
        categories=ATTESTATION_CATEGORY_LABELS,
        can_manage=_can_manage(),
        remaining_period_label=attestation_remaining_period_label,
    )


@professional_registry_bp.route("/attestations/new", methods=["GET", "POST"])
@login_required
def attestation_new():
    _require_manage()
    if request.method == "POST":
        record = TeacherAttestation(
            entry_source="ADMINISTRATION",
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
        )
        try:
            _apply_attestation_form(record)
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template(
                "professional_registry/attestation_form.html",
                **_attestation_form_context(record),
            ), 400
        db.session.add(record)
        db.session.flush()
        record_professional_change(
            record,
            change_kind=CHANGE_CREATED,
            actor_id=current_user.id,
        )
        db.session.commit()
        flash("Сведения об аттестации добавлены.", "success")
        return redirect(url_for("professional_registry.attestation_registry"))
    return render_template(
        "professional_registry/attestation_form.html",
        **_attestation_form_context(),
    )


@professional_registry_bp.route(
    "/attestations/<int:record_id>/edit",
    methods=["GET", "POST"],
)
@login_required
def attestation_edit(record_id):
    _require_manage()
    record = TeacherAttestation.query.filter_by(
        id=record_id,
        is_archived=False,
    ).first_or_404()
    if request.method == "POST":
        try:
            _apply_attestation_form(record)
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template(
                "professional_registry/attestation_form.html",
                **_attestation_form_context(record),
            ), 400
        record_professional_change(
            record,
            change_kind=CHANGE_UPDATED,
            actor_id=current_user.id,
        )
        db.session.commit()
        flash("Сведения об аттестации обновлены.", "success")
        return redirect(url_for("professional_registry.attestation_registry"))
    return render_template(
        "professional_registry/attestation_form.html",
        **_attestation_form_context(record),
    )


@professional_registry_bp.post("/attestations/<int:record_id>/archive")
@login_required
def attestation_archive(record_id):
    _require_manage()
    record = TeacherAttestation.query.filter_by(
        id=record_id,
        is_archived=False,
    ).first_or_404()
    record.is_archived = True
    record.updated_by_user_id = current_user.id
    record_professional_change(
        record,
        change_kind=CHANGE_ARCHIVED,
        actor_id=current_user.id,
    )
    db.session.commit()
    flash("Запись об аттестации перенесена в архив.", "success")
    return redirect(url_for("professional_registry.attestation_registry"))
