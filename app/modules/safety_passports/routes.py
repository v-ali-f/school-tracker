"""Classroom passport, review and school oversight screens."""

import mimetypes
from datetime import date, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.core.extensions import db
from app.models import (
    Building, SafetyOfficerAssignment, SafetyPassport, SafetyPassportDocument,
    SafetyPassportReview, SchoolClassroom, User,
)
from app.models.safety_passport import utc_now
from app.services.safety_passport_service import (
    COMPLIANCE_LABELS, REVIEW_RESULTS, ROW_SCHEMAS, STATUS_LABELS,
    can_access_registry, can_edit, can_view, current_revision, ensure_passport,
    form_data_for_display, is_admin, is_director, is_officer,
    parse_passport_form, save_revision, school_today,
)


safety_passports_bp = Blueprint("safety_passports", __name__, url_prefix="/safety/passports")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "docx"}
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024


def _local_time(value):
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(current_app.config.get("SCHOOL_TIMEZONE", "Europe/Moscow"))
    except KeyError:
        zone = timezone.utc
    return value.astimezone(zone).strftime("%d.%m.%Y %H:%M")


def _workspace_context():
    from app.modules.hub.routes import build_home_context
    return {
        "workspace_nav": build_home_context(),
        "workspace_context_title": "Охрана труда",
        "workspace_context_subtitle": "Паспорта кабинетов",
    }


def _classroom_or_404(classroom_id):
    return (
        SchoolClassroom.query
        .options(joinedload(SchoolClassroom.building), selectinload(SchoolClassroom.teachers))
        .filter_by(id=classroom_id)
        .first_or_404()
    )


def _detail_context(classroom, passport, *, form_data=None):
    revision = current_revision(passport)
    reviews = []
    if passport:
        for item in passport.revisions:
            reviews.extend(item.reviews)
    reviews.sort(key=lambda item: (item.reviewed_at, item.id), reverse=True)
    return {
        **_workspace_context(),
        "classroom": classroom,
        "passport": passport,
        "revision": revision,
        "data": form_data if form_data is not None else (revision.data if revision else {}),
        "reviews": reviews,
        "can_edit_passport": can_edit(current_user, classroom),
        "can_review_passport": is_officer(current_user),
        "status_labels": STATUS_LABELS,
        "review_results": REVIEW_RESULTS,
        "compliance_labels": COMPLIANCE_LABELS,
        "row_schemas": ROW_SCHEMAS,
        "local_time": _local_time,
    }


@safety_passports_bp.route("/")
@login_required
def index():
    if not can_access_registry(current_user):
        abort(403)
    manager = is_director(current_user) or is_admin(current_user) or is_officer(current_user)
    building_id = request.args.get("building_id", type=int)
    status = (request.args.get("status") or "").strip()
    query = SchoolClassroom.query.options(
        joinedload(SchoolClassroom.building),
        selectinload(SchoolClassroom.teachers),
        joinedload(SchoolClassroom.safety_passport),
    )
    if not manager:
        query = query.filter(
            SchoolClassroom.is_active.is_(True),
            or_(
                SchoolClassroom.teacher_user_id == current_user.id,
                SchoolClassroom.teachers.any(User.id == current_user.id),
            ),
        )
    if building_id:
        query = query.filter(SchoolClassroom.building_id == building_id)
    all_classrooms = query.join(Building).order_by(Building.name, SchoolClassroom.name).all()
    counts = {key: 0 for key in STATUS_LABELS}
    for room in all_classrooms:
        effective = "archived" if not room.is_active else (room.safety_passport.status if room.safety_passport else "not_started")
        counts[effective] += 1
    classrooms = all_classrooms
    if status in STATUS_LABELS:
        classrooms = [
            room for room in all_classrooms
            if ("archived" if not room.is_active else (room.safety_passport.status if room.safety_passport else "not_started")) == status
        ]
    return render_template(
        "safety_passports/index.html",
        **_workspace_context(),
        classrooms=classrooms,
        buildings=Building.query.order_by(Building.name).all() if manager else [],
        selected_building_id=building_id,
        selected_status=status,
        status_labels=STATUS_LABELS,
        counts=counts,
        manager=manager,
    )


@safety_passports_bp.route("/<int:classroom_id>")
@login_required
def detail(classroom_id):
    classroom = _classroom_or_404(classroom_id)
    if not can_view(current_user, classroom):
        abort(403)
    passport = SafetyPassport.query.filter_by(classroom_id=classroom.id).first()
    if passport is None and classroom.is_active and classroom.assigned_teacher_ids:
        try:
            passport = ensure_passport(classroom)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            passport = SafetyPassport.query.filter_by(classroom_id=classroom.id).first()
    return render_template("safety_passports/detail.html", **_detail_context(classroom, passport))


@safety_passports_bp.route("/<int:classroom_id>/save", methods=["POST"])
@login_required
def save(classroom_id):
    classroom = _classroom_or_404(classroom_id)
    if not can_edit(current_user, classroom):
        abort(403)
    passport = ensure_passport(classroom)
    try:
        expected_number = int(request.form.get("base_revision_number", "-1"))
        data = parse_passport_form(request.form)
        save_revision(passport, current_user, data, expected_number)
        db.session.commit()
    except (ValueError, IntegrityError) as exc:
        db.session.rollback()
        message = str(exc) if isinstance(exc, ValueError) else "Паспорт уже изменён другим сотрудником. Обновите страницу."
        flash(message, "danger")
        passport = SafetyPassport.query.filter_by(classroom_id=classroom.id).first()
        return render_template("safety_passports/detail.html", **_detail_context(classroom, passport, form_data=form_data_for_display(request.form))), 409
    flash("Паспорт сохранён.", "success")
    return redirect(url_for("safety_passports.detail", classroom_id=classroom.id))


@safety_passports_bp.route("/<int:classroom_id>/submit", methods=["POST"])
@login_required
def submit(classroom_id):
    classroom = _classroom_or_404(classroom_id)
    if not can_edit(current_user, classroom):
        abort(403)
    passport = SafetyPassport.query.filter_by(classroom_id=classroom.id).first_or_404()
    revision = current_revision(passport)
    if passport.status not in {"draft", "needs_recheck"} or revision is None or revision.reviews:
        flash("Сначала сохраните новую редакцию паспорта.", "danger")
        return redirect(url_for("safety_passports.detail", classroom_id=classroom.id))
    revision.submitted_at = utc_now()
    passport.status = "in_review"
    db.session.commit()
    flash("Паспорт отправлен на проверку.", "success")
    return redirect(url_for("safety_passports.detail", classroom_id=classroom.id))


@safety_passports_bp.route("/<int:classroom_id>/review", methods=["POST"])
@login_required
def review(classroom_id):
    if not is_officer(current_user):
        abort(403)
    classroom = _classroom_or_404(classroom_id)
    passport = SafetyPassport.query.filter_by(classroom_id=classroom.id).first_or_404()
    revision = current_revision(passport)
    if passport.status not in {"in_review", "verified", "needs_work", "noncompliant"} or revision is None or not revision.submitted_at or not classroom.is_active:
        abort(409)
    result = (request.form.get("result") or "").strip()
    comment = (request.form.get("comment") or "").strip()
    if result not in REVIEW_RESULTS or len(comment) > 5000 or ((result != "verified" or revision.reviews) and not comment):
        flash("Выберите результат и укажите замечания при возврате паспорта.", "danger")
        return redirect(url_for("safety_passports.detail", classroom_id=classroom.id))
    due_date = None
    if request.form.get("due_date"):
        try:
            due_date = date.fromisoformat(request.form["due_date"])
        except ValueError:
            flash("Укажите корректный срок исправления.", "danger")
            return redirect(url_for("safety_passports.detail", classroom_id=classroom.id))
    db.session.add(SafetyPassportReview(
        revision_id=revision.id,
        result=result,
        comment=comment or None,
        due_date=due_date,
        reviewer_id=current_user.id,
    ))
    passport.status = result
    db.session.commit()
    flash("Результат проверки сохранён.", "success")
    return redirect(url_for("safety_passports.detail", classroom_id=classroom.id))


@safety_passports_bp.route("/officers", methods=["GET", "POST"])
@login_required
def officers():
    if not is_director(current_user):
        abort(403)
    if request.method == "POST":
        user_id = request.form.get("user_id", type=int)
        user = db.session.get(User, user_id) if user_id else None
        try:
            valid_from = date.fromisoformat(request.form.get("valid_from", ""))
            valid_to = date.fromisoformat(request.form["valid_to"]) if request.form.get("valid_to") else None
        except ValueError:
            valid_from = None
            valid_to = None
        if not user or not user.is_active_user or valid_from is None or (valid_to and valid_to < valid_from):
            flash("Выберите действующего сотрудника и корректный период.", "danger")
        else:
            overlapping = SafetyOfficerAssignment.query.filter(
                SafetyOfficerAssignment.revoked_at.is_(None),
                or_(SafetyOfficerAssignment.valid_to.is_(None), SafetyOfficerAssignment.valid_to >= valid_from),
            ).all()
            concurrent = [item for item in overlapping if valid_to is None or item.valid_from <= valid_to]
            if any(item.user_id == user.id for item in concurrent):
                flash("Сотрудник уже назначен на выбранный период.", "danger")
            elif not is_director(user) and any(not is_director(item.user) for item in concurrent):
                flash("На выбранный период уже назначен ответственный за ОТ.", "danger")
            else:
                db.session.add(SafetyOfficerAssignment(
                    user_id=user.id, valid_from=valid_from, valid_to=valid_to,
                    assigned_by_id=current_user.id,
                    can_manage_instructions=request.form.get("can_manage_instructions") == "1",
                ))
                db.session.commit()
                flash("Ответственный за ОТ назначен.", "success")
        return redirect(url_for("safety_passports.officers"))
    return render_template(
        "safety_passports/officers.html",
        **_workspace_context(),
        assignments=SafetyOfficerAssignment.query.order_by(SafetyOfficerAssignment.created_at.desc()).all(),
        users=User.query.filter_by(is_active_user=True).order_by(User.last_name, User.first_name).all(),
        today=school_today(),
    )


@safety_passports_bp.route("/officers/<int:assignment_id>/revoke", methods=["POST"])
@login_required
def revoke_officer(assignment_id):
    if not is_director(current_user):
        abort(403)
    assignment = SafetyOfficerAssignment.query.get_or_404(assignment_id)
    if assignment.revoked_at is None:
        assignment.revoked_at = utc_now()
        assignment.revoked_by_id = current_user.id
        db.session.commit()
    flash("Назначение отменено; история сохранена.", "success")
    return redirect(url_for("safety_passports.officers"))


@safety_passports_bp.route("/officers/<int:assignment_id>/instructions", methods=["POST"])
@login_required
def set_instruction_right(assignment_id):
    if not is_director(current_user):
        abort(403)
    assignment = SafetyOfficerAssignment.query.get_or_404(assignment_id)
    if assignment.revoked_at is not None:
        abort(409)
    assignment.can_manage_instructions = request.form.get("can_manage_instructions") == "1"
    db.session.commit()
    flash("Право ведения инструкций обновлено.", "success")
    return redirect(url_for("safety_passports.officers"))


def _document_dir():
    return Path(current_app.config["UPLOAD_FOLDER"]) / "safety_passports"


@safety_passports_bp.route("/<int:classroom_id>/documents", methods=["POST"])
@login_required
def upload_document(classroom_id):
    classroom = _classroom_or_404(classroom_id)
    if not can_edit(current_user, classroom):
        abort(403)
    upload = request.files.get("document")
    original_name = (upload.filename or "").replace("\\", "/").split("/")[-1].replace("\x00", "").strip()[:255] if upload else ""
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if extension not in ALLOWED_EXTENSIONS:
        flash("Допустимы PDF, DOCX, JPG и PNG.", "danger")
        return redirect(url_for("safety_passports.detail", classroom_id=classroom.id))
    content = upload.stream.read(MAX_DOCUMENT_BYTES + 1)
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        flash("Файл пуст или превышает 15 МБ.", "danger")
        return redirect(url_for("safety_passports.detail", classroom_id=classroom.id))
    passport = ensure_passport(classroom)
    stored_name = f"{uuid4().hex}.{extension}"
    directory = _document_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / stored_name
    path.write_bytes(content)
    db.session.add(SafetyPassportDocument(
        passport=passport,
        original_name=original_name[:255],
        stored_name=stored_name,
        mime_type=mimetypes.guess_type(original_name)[0] or "application/octet-stream",
        description=(request.form.get("description") or "").strip()[:255] or None,
        uploaded_by_id=current_user.id,
    ))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        path.unlink(missing_ok=True)
        raise
    flash("Документ добавлен в паспорт.", "success")
    return redirect(url_for("safety_passports.detail", classroom_id=classroom.id))


@safety_passports_bp.route("/<int:classroom_id>/documents/<int:document_id>")
@login_required
def download_document(classroom_id, document_id):
    classroom = _classroom_or_404(classroom_id)
    if not can_view(current_user, classroom):
        abort(403)
    document = SafetyPassportDocument.query.filter_by(id=document_id, passport_id=classroom.safety_passport.id if classroom.safety_passport else None).first_or_404()
    return send_from_directory(_document_dir(), document.stored_name, as_attachment=True, download_name=document.original_name)


@safety_passports_bp.route("/<int:classroom_id>/print")
@login_required
def print_passport(classroom_id):
    classroom = _classroom_or_404(classroom_id)
    if not can_view(current_user, classroom):
        abort(403)
    passport = SafetyPassport.query.filter_by(classroom_id=classroom.id).first()
    return render_template("safety_passports/print.html", **_detail_context(classroom, passport), now=school_today())
