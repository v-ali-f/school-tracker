"""Teacher drafts and immutable safety journal pages for classes and trips."""

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.extensions import db
from app.models import (
    Building, SafetyInstructionVersion, SafetyJournalDraft, SafetyJournalDraftEvent,
    SafetyJournalPage, SafetyJournalPageClass, SafetyJournalPageEvent,
    SafetyJournalPageRevision, SafetyJournalParticipant,
    SafetyJournalPaperRecord, SafetyJournalPaperScan,
    SafetyTripAssignment,
)
from app.models.safety_passport import utc_now
from app.services.safety_journal_pdf import build_journal_pdf
from app.services.safety_journal_service import (
    CLASS_TEACHER_SUBJECT, available_classes, can_create_journal, can_view_page, effective_instruction_versions,
    instruction_is_effective, journal_classes_for_user, journal_subjects_for_class,
    preview_payload, roster_for_classes, search_students,
    selected_enrollments,
)
from app.services.safety_passport_service import can_manage_instructions, is_admin, is_director, is_officer, school_today


safety_journals_bp = Blueprint("safety_journals", __name__, url_prefix="/safety/journals")
MAX_SCAN_BYTES = 20 * 1024 * 1024


def _school_zone():
    try:
        return ZoneInfo(current_app.config.get("SCHOOL_TIMEZONE", "Europe/Moscow"))
    except KeyError:
        return timezone.utc


def _local_time(value):
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_school_zone()).strftime("%d.%m.%Y %H:%M")


def _briefing_input(value):
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_school_zone()).strftime("%Y-%m-%dT%H:%M")


def _briefing_from_form():
    raw = (request.form.get("briefing_at") or "").strip()
    try:
        local_value = datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise ValueError("Укажите дату и время проведения инструктажа.") from exc
    return local_value.replace(tzinfo=_school_zone()).astimezone(timezone.utc)


def _context():
    from app.modules.hub.routes import build_home_context
    return {
        "workspace_nav": build_home_context(),
        "workspace_context_title": "Техника безопасности",
        "workspace_context_subtitle": "Журналы инструктажей",
    }


def _draft_or_404(draft_id):
    draft = db.session.get(SafetyJournalDraft, draft_id) or abort(404)
    if draft.author_id != current_user.id:
        abort(403)
    if draft.trip_assignment_id is not None and (draft.trip_assignment is None or draft.trip_assignment.user_id != current_user.id or not draft.trip_assignment.is_active):
        abort(403)
    return draft


def _page_or_404(page_id):
    page = db.session.get(SafetyJournalPage, page_id) or abort(404)
    if not can_view_page(current_user, page):
        abort(403)
    return page


def _storage():
    base = current_app.config.get("UPLOAD_FOLDER")
    if not base:
        raise RuntimeError("Не настроено хранилище журналов.")
    path = Path(base) / "safety" / "journal_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _scan_storage():
    path = _storage().parent / "paper_scans"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _paper_manager():
    return is_officer(current_user) or is_director(current_user) or is_admin(current_user)


def _paper_record(page):
    record = page.paper_record
    if record is None:
        record = SafetyJournalPaperRecord(page_id=page.id)
        db.session.add(record)
        db.session.flush()
    return record


def _scan_upload():
    uploaded = request.files.get("scan")
    if uploaded is None or not uploaded.filename:
        raise ValueError("Выберите скан в формате PDF, JPG или PNG.")
    original_name = Path(uploaded.filename.replace("\\", "/")).name
    if not original_name or len(original_name) > 255:
        raise ValueError("Некорректное имя файла.")
    content = uploaded.stream.read(MAX_SCAN_BYTES + 1)
    if not content or len(content) > MAX_SCAN_BYTES:
        raise ValueError("Скан пуст или превышает 20 МБ.")
    suffix = Path(original_name).suffix.lower()
    if suffix == ".pdf" and content.startswith(b"%PDF-") and b"%%EOF" in content[-1024:]:
        mime = "application/pdf"
    elif suffix in {".jpg", ".jpeg"} and content.startswith(b"\xff\xd8\xff") and content.rstrip().endswith(b"\xff\xd9"):
        mime = "image/jpeg"
    elif suffix == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND" in content[-20:]:
        mime = "image/png"
    else:
        raise ValueError("Файл не соответствует формату PDF, JPG или PNG.")
    return original_name, suffix, mime, content


def _token(page, revision):
    return URLSafeTimedSerializer(current_app.secret_key, salt="safety-journal-pdf-v1").dumps({
        "page": page.id, "revision": revision.id, "user": current_user.id,
    })


def _event(draft, action, child_id=None, details=None):
    db.session.add(SafetyJournalDraftEvent(
        draft_id=draft.id, actor_id=current_user.id, action=action,
        child_id=child_id, details=details,
    ))


@safety_journals_bp.route("/")
@safety_journals_bp.route("/trips", endpoint="trips_index")
@login_required
def index():
    trip_section = request.endpoint == "safety_journals.trips_index"
    manager = is_officer(current_user) or is_director(current_user) or is_admin(current_user)
    trip_assigned = SafetyTripAssignment.query.filter_by(user_id=current_user.id, is_active=True).first() is not None
    if not manager and not can_create_journal(current_user) and not trip_assigned:
        abort(403)
    query = SafetyJournalPage.query.options(
        selectinload(SafetyJournalPage.participants),
        selectinload(SafetyJournalPage.paper_record),
        selectinload(SafetyJournalPage.paper_scans),
        selectinload(SafetyJournalPage.revisions),
        selectinload(SafetyJournalPage.instruction_version),
    )
    if not manager:
        query = query.filter_by(author_id=current_user.id)
    elif request.args.get("author_id", type=int):
        query = query.filter_by(author_id=request.args.get("author_id", type=int))
    building_id = request.args.get("building_id", type=int) if manager else None
    if building_id:
        query = query.join(SafetyJournalPageClass).filter(SafetyJournalPageClass.building_id_snapshot == building_id)
    for field, comparator in (("date_from", "from"), ("date_to", "to")):
        raw = request.args.get(field)
        if raw:
            try:
                selected_date = date.fromisoformat(raw)
            except ValueError:
                selected_date = None
            if selected_date is not None:
                query = query.filter(SafetyJournalPage.instructed_on >= selected_date if comparator == "from" else SafetyJournalPage.instructed_on <= selected_date)
    status = request.args.get("status", "")
    if status in {"generated", "printed", "annulled"}:
        query = query.filter_by(status=status)
    kind = "trip" if trip_section else request.args.get("kind", "")
    if kind in {"ordinary", "class_teacher", "trip"}:
        query = query.filter_by(kind=kind)
    pages = query.order_by(SafetyJournalPage.created_at.desc(), SafetyJournalPage.id.desc()).limit(300).all()
    drafts = SafetyJournalDraft.query.filter_by(author_id=current_user.id, status="draft").order_by(SafetyJournalDraft.updated_at.desc()).all() if can_create_journal(current_user) or trip_assigned else []
    if trip_section:
        drafts = [item for item in drafts if item.journal_kind == "trip" or item.trip_order_id is not None]
    preview_tokens = {page.id: _token(page, page.revisions[-1]) for page in pages if page.revisions}
    return render_template("safety_journals/index.html", **_context(), pages=pages, preview_tokens=preview_tokens, drafts=drafts, local_time=_local_time, manager=manager, can_create=can_create_journal(current_user), can_view_trips=manager or trip_assigned, status=status, kind=kind, trip_section=trip_section, buildings=Building.query.order_by(Building.name).all() if manager else [], building_id=building_id)


@safety_journals_bp.route("/new", methods=["POST"])
@login_required
def create():
    if not can_create_journal(current_user):
        abort(403)
    journal_kind = request.form.get("journal_kind", "ordinary")
    if journal_kind not in {"ordinary", "class_teacher"}:
        abort(400)
    draft = SafetyJournalDraft(id=str(uuid4()), author_id=current_user.id, journal_kind=journal_kind,
                               instructed_on=school_today(), class_ids=[], selected_child_ids=[], removed_child_ids=[])
    db.session.add(draft)
    db.session.flush()
    _event(draft, "created")
    db.session.commit()
    return redirect(url_for("safety_journals.edit", draft_id=draft.id))


@safety_journals_bp.route("/trips/new", methods=["POST"])
@login_required
def create_trip():
    if not can_create_journal(current_user):
        abort(403)
    draft = SafetyJournalDraft(
        id=str(uuid4()), author_id=current_user.id, journal_kind="trip",
        instructed_on=school_today(), class_ids=[], selected_child_ids=[], removed_child_ids=[],
    )
    db.session.add(draft)
    db.session.flush()
    _event(draft, "created", details={"kind": "trip"})
    db.session.commit()
    return redirect(url_for("safety_journals.edit", draft_id=draft.id))


@safety_journals_bp.route("/drafts/<uuid:draft_id>")
@login_required
def edit(draft_id):
    draft = _draft_or_404(str(draft_id))
    if draft.status != "draft":
        return redirect(url_for("safety_journals.detail", page_id=draft.page_id))
    try:
        chosen_date = date.fromisoformat(request.args.get("instructed_on", "")) if request.args.get("instructed_on") else (draft.instructed_on or school_today())
    except ValueError:
        chosen_date = draft.instructed_on or school_today()
    chosen_grade = request.args.get("grade", type=int) or draft.grade
    try:
        trip = draft.trip_order_id is not None or draft.journal_kind == "trip"
        all_classes = journal_classes_for_user(chosen_date, current_user, trip=trip,
                                               homeroom=draft.journal_kind == "class_teacher")
        grades = sorted({item.grade for item in all_classes if item.grade})
        classes = [item for item in all_classes if item.grade == chosen_grade] if chosen_grade else []
        chosen_class_id = request.args.get("class_id", type=int) or (draft.class_ids[0] if draft.class_ids else None)
        chosen_class = next((item for item in classes if item.id == chosen_class_id), None)
        subjects = journal_subjects_for_class(chosen_date, current_user, chosen_class, trip=trip) if (chosen_class or trip) and draft.journal_kind != "class_teacher" else []
        active_versions = effective_instruction_versions(chosen_date)
        chosen_subject = (request.args.get("subject") or draft.subject or (draft.instruction_version.instruction.category if draft.instruction_version else "")).strip()
        chosen_subject = CLASS_TEACHER_SUBJECT if draft.journal_kind == "class_teacher" else next((item for item in subjects if item.casefold() == chosen_subject.casefold()), "")
        versions = active_versions if trip else [item for item in active_versions if item.instruction.category.strip().casefold() == chosen_subject.casefold()] if chosen_subject else []
        if chosen_subject and not trip:
            from app.modules.safety_instructions.routes import library_items_for_section, library_suggestions
            library_items = library_items_for_section("class_teacher") if draft.journal_kind == "class_teacher" else library_suggestions(chosen_subject)
        else:
            library_items = []
        roster = roster_for_classes(chosen_date, draft.class_ids) if draft.class_ids else {}
    except ValueError as exc:
        classes, versions, subjects, grades, chosen_class, chosen_subject, library_items, roster = [], [], [], [], None, "", [], {}
        flash(str(exc), "danger")
    class_roster = sorted(roster.values(), key=lambda item: (item.child.fio.casefold(), item.child_id))
    selected = [roster.get(int(child_id)) for child_id in draft.selected_child_ids if int(child_id) in roster]
    # Students from another class are resolved separately.
    if draft.selected_child_ids:
        try:
            enrollment_map = selected_enrollments(chosen_date, draft.selected_child_ids)
            selected = [enrollment_map[int(child_id)] for child_id in draft.selected_child_ids]
        except ValueError as exc:
            flash(str(exc), "warning")
    found = search_students(draft.instructed_on or chosen_date, request.args.get("q")) if draft.class_ids and request.args.get("q") else []
    removed = []
    if draft.removed_child_ids:
        try:
            removed_map = selected_enrollments(draft.instructed_on, draft.removed_child_ids)
            removed = [removed_map[int(child_id)] for child_id in draft.removed_child_ids]
        except ValueError:
            pass
    template = ("safety_journals/edit.html" if draft.trip_order_id is not None else
        "safety_journals/edit_trip.html" if draft.journal_kind == "trip" else "safety_journals/edit_ordinary.html")
    return render_template(
        template,
        **_context(), draft=draft, classes=classes,
        versions=versions, subjects=subjects, grades=grades, chosen_class=chosen_class, library_items=library_items,
        chosen_subject=chosen_subject,
        class_roster=class_roster, selected=selected, removed=removed, found=found, trip=draft.trip_order,
        selected_students=[{"id": item.child_id, "name": item.child.fio, "class_name": item.school_class.name,
                            "birth_date": item.child.birth_date.strftime("%d.%m.%Y") if item.child.birth_date else ""}
                           for item in selected],
        chosen_date=chosen_date, chosen_grade=chosen_grade, today=school_today(),
        briefing_input=_briefing_input(draft.briefing_at),
        manager_mode=is_admin(current_user) or is_director(current_user),
        can_manage_instructions=can_manage_instructions(current_user),
        admin_mode=(is_admin(current_user) or is_director(current_user)) and not current_user.has_role("TEACHER"),
    )


@safety_journals_bp.route("/choices")
@login_required
def choices():
    if not can_create_journal(current_user):
        abort(403)
    try:
        on_date = date.fromisoformat(request.args.get("on_date", "")) if request.args.get("on_date") else school_today()
        if on_date > school_today():
            raise ValueError("Дата учёта не может быть в будущем.")
        grade = request.args.get("grade", type=int)
        journal_kind = request.args.get("journal_kind", "ordinary")
        if journal_kind not in {"ordinary", "class_teacher"}:
            raise ValueError("Выберите вид журнала.")
        all_classes = journal_classes_for_user(on_date, current_user, homeroom=journal_kind == "class_teacher")
        classes = [item for item in all_classes if item.grade == grade] if grade else []
        class_id = request.args.get("class_id", type=int)
        classroom = next((item for item in classes if item.id == class_id), None)
        subjects = journal_subjects_for_class(on_date, current_user, classroom) if classroom and journal_kind == "ordinary" else []
        requested_subject = (request.args.get("subject") or "").strip()
        subject = CLASS_TEACHER_SUBJECT if journal_kind == "class_teacher" else next((item for item in subjects if item.casefold() == requested_subject.casefold()), "")
        versions = [
            item for item in effective_instruction_versions(on_date)
            if subject and item.instruction.category.strip().casefold() == subject.casefold()
        ]
        roster = roster_for_classes(on_date, [classroom.id]) if classroom else {}
        from app.modules.safety_instructions.routes import library_items_for_section, library_suggestions
        suggestions = library_items_for_section("class_teacher") if journal_kind == "class_teacher" else library_suggestions(subject) if subject else []
        instructions = [{
            "id": f"version:{item.id}", "label": f"{item.instruction.number} — {item.title_snapshot}",
            "source": "catalog",
            "preview_url": url_for("safety_instructions.download_original", version_id=item.id, inline=1) if item.file_mime_type == "application/pdf" else "",
            "download_url": url_for("safety_instructions.download_original", version_id=item.id),
        } for item in versions]
        known_hashes = {item.file_sha256 for item in versions}
        instructions.extend({
            "id": f"library:{item['id']}", "label": item["title"], "source": "library",
            "preview_url": url_for("safety_instructions.library_pdf", item_id=item["id"]),
            "download_url": url_for("safety_instructions.library_pdf", item_id=item["id"], download=1),
        } for item in suggestions if item["id"] not in known_hashes)
        response = jsonify({
            "grades": sorted({item.grade for item in all_classes if item.grade}),
            "classes": [{"id": item.id, "name": item.name} for item in classes],
            "subjects": subjects,
            "instructions": instructions,
            "roster": [{
                "id": item.child_id, "name": item.child.fio,
                "class_name": item.school_class.name,
                "birth_date": item.child.birth_date.strftime("%d.%m.%Y") if item.child.birth_date else "",
            } for item in sorted(roster.values(), key=lambda row: row.child.fio.casefold())],
        })
        response.headers["Cache-Control"] = "private, no-store"
        return response
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@safety_journals_bp.route("/trips/choices")
@login_required
def trip_choices():
    if not can_create_journal(current_user):
        abort(403)
    try:
        on_date = school_today()
        all_classes = journal_classes_for_user(on_date, current_user, trip=True)
        grade = request.args.get("grade", type=int)
        classes = [item for item in all_classes if item.grade == grade] if grade else []
        class_id = request.args.get("class_id", type=int)
        classroom = next((item for item in classes if item.id == class_id), None)
        roster = roster_for_classes(on_date, [classroom.id]) if classroom else {}
        from app.modules.safety_instructions.routes import journal_library_items
        versions = effective_instruction_versions(on_date)
        instructions = [{
            "id": f"version:{item.id}", "label": f"{item.instruction.number} — {item.title_snapshot}",
            "preview_url": url_for("safety_instructions.download_original", version_id=item.id, inline=1) if item.file_mime_type == "application/pdf" else "",
            "download_url": url_for("safety_instructions.download_original", version_id=item.id),
        } for item in versions]
        known_hashes = {item.file_sha256 for item in versions}
        instructions.extend({
            "id": f"library:{item['id']}", "label": item["title"],
            "preview_url": url_for("safety_instructions.library_pdf", item_id=item["id"]),
            "download_url": url_for("safety_instructions.library_pdf", item_id=item["id"], download=1),
        } for item in journal_library_items() if item["id"] not in known_hashes)
        response = jsonify({
            "grades": sorted({item.grade for item in all_classes if item.grade}),
            "classes": [{"id": item.id, "name": item.name} for item in classes],
            "instructions": instructions,
            "roster": [{"id": item.child_id, "name": item.child.fio, "class_name": item.school_class.name,
                        "birth_date": item.child.birth_date.strftime("%d.%m.%Y") if item.child.birth_date else ""}
                       for item in sorted(roster.values(), key=lambda row: row.child.fio.casefold())],
        })
        response.headers["Cache-Control"] = "private, no-store"
        return response
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@safety_journals_bp.route("/drafts/<uuid:draft_id>/compose", methods=["POST"])
@login_required
def compose(draft_id):
    draft = _draft_or_404(str(draft_id))
    if draft.status != "draft" or draft.trip_order_id is not None or not can_create_journal(current_user):
        abort(409)
    try:
        _populate_trip_draft(draft) if draft.journal_kind == "trip" else _populate_ordinary_draft(draft)
        _event(draft, "composed", details={"class_id": draft.class_ids[0], "version_id": draft.instruction_version_id,
                                            "library_item_id": draft.library_item_id, "count": len(draft.selected_child_ids)})
        db.session.commit()
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("safety_journals.edit", draft_id=draft.id))
    return _generate_page(draft)


def _populate_trip_draft(draft):
    briefing_at = _briefing_from_form()
    trip_kind = (request.form.get("trip_kind") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    order_number = (request.form.get("order_number") or "").strip()
    note = (request.form.get("header_note") or "").strip()
    briefing_kind = (request.form.get("briefing_kind") or "").strip().casefold()
    try:
        trip_date = date.fromisoformat(request.form.get("trip_date") or "")
    except ValueError as exc:
        raise ValueError("Укажите дату выезда.") from exc
    if not trip_kind or len(trip_kind) > 80 or not destination or len(destination) > 200:
        raise ValueError("Укажите вид и место выезда.")
    if len(order_number) > 80 or len(note) > 500:
        raise ValueError("Сократите номер приказа или дополнительную информацию.")
    if briefing_kind not in {"первичный", "повторный", "внеплановый", "целевой"}:
        raise ValueError("Выберите вид инструктажа.")
    choice = (request.form.get("instruction_choice") or "").strip()
    version_id, library_item_id = None, None
    if choice.startswith("library:"):
        library_item_id = choice.partition(":")[2]
        from app.modules.safety_instructions.routes import journal_library_item
        journal_library_item(library_item_id)
    else:
        try:
            version_id = int(choice.partition(":")[2] if choice.startswith("version:") else choice)
        except ValueError as exc:
            raise ValueError("Выберите инструкцию для выезда.") from exc
        if not instruction_is_effective(db.session.get(SafetyInstructionVersion, version_id), draft.instructed_on):
            raise ValueError("Выбранная инструкция больше не действует.")
    try:
        child_ids = [int(value) for value in request.form.getlist("child_ids")]
    except ValueError as exc:
        raise ValueError("Обновите список участников выезда.") from exc
    enrollments = selected_enrollments(draft.instructed_on, child_ids)
    classes = {item.id: item for item in journal_classes_for_user(draft.instructed_on, current_user, trip=True)}
    class_ids = sorted({item.school_class_id for item in enrollments.values()})
    if not set(class_ids).issubset(classes):
        raise ValueError("Один из выбранных классов больше не доступен.")
    draft.grade = classes[class_ids[0]].grade
    draft.class_ids = class_ids
    draft.selected_child_ids = child_ids
    draft.removed_child_ids = []
    draft.subject = trip_kind
    draft.instruction_version_id = version_id
    draft.library_item_id = library_item_id
    draft.briefing_kind = briefing_kind
    draft.briefing_at = briefing_at
    draft.header_note = note
    draft.manual_trip = {"trip_kind": trip_kind, "destination": destination,
                         "trip_date": trip_date.isoformat(), "order_number": order_number}
    db.session.flush()
    db.session.expire(draft, ["instruction_version"])


def _populate_ordinary_draft(draft):
    briefing_at = _briefing_from_form()
    on_date = draft.instructed_on or school_today()
    grade = int(request.form.get("grade", "0"))
    class_id = int(request.form.get("class_id", "0"))
    subject = CLASS_TEACHER_SUBJECT if draft.journal_kind == "class_teacher" else (request.form.get("subject") or "").strip()
    kind = (request.form.get("briefing_kind") or "").strip().casefold()
    note = (request.form.get("header_note") or "").strip()
    child_ids = [int(value) for value in request.form.getlist("child_ids")]
    choice = (request.form.get("instruction_choice") or request.form.get("instruction_version_id") or "").strip()
    if kind not in {"первичный", "повторный", "внеплановый", "целевой"}:
        raise ValueError("Выберите вид инструктажа.")
    if len(note) > 500:
        raise ValueError("Дополнительная информация должна быть не длиннее 500 символов.")
    classes = journal_classes_for_user(on_date, current_user, grade, homeroom=draft.journal_kind == "class_teacher")
    classroom = next((item for item in classes if item.id == class_id), None)
    if classroom is None:
        raise ValueError("Выберите доступный класс.")
    subjects = journal_subjects_for_class(on_date, current_user, classroom) if draft.journal_kind != "class_teacher" else []
    if draft.journal_kind != "class_teacher" and not any(item.casefold() == subject.casefold() for item in subjects):
        raise ValueError("Выберите предмет из учебного плана или вашей нагрузки.")
    version_id, library_item_id = None, None
    if choice.startswith("library:"):
        library_item_id = choice.partition(":")[2]
        from app.modules.safety_instructions.routes import journal_library_item
        journal_library_item(library_item_id, None if draft.journal_kind == "class_teacher" else subject,
                             section="class_teacher" if draft.journal_kind == "class_teacher" else None)
    else:
        version_id = int(choice.partition(":")[2] if choice.startswith("version:") else choice)
        version = db.session.get(SafetyInstructionVersion, version_id)
        if not instruction_is_effective(version, on_date) or version.instruction.category.strip().casefold() != subject.casefold():
            raise ValueError("Выберите действующую инструкцию по предмету.")
    roster = roster_for_classes(on_date, [class_id])
    if not child_ids or len(child_ids) > 120 or len(set(child_ids)) != len(child_ids) or not set(child_ids).issubset(roster):
        raise ValueError("Выберите от 1 до 120 обучающихся из списка класса.")
    draft.grade = grade
    draft.class_ids = [class_id]
    draft.subject = subject
    draft.instruction_version_id = version_id
    draft.library_item_id = library_item_id
    draft.briefing_kind = kind
    draft.briefing_at = briefing_at
    draft.header_note = note
    draft.selected_child_ids = child_ids
    draft.removed_child_ids = sorted(set(roster) - set(child_ids))
    db.session.flush()
    db.session.expire(draft, ["instruction_version"])


def _correct_page(draft, payload):
    page = db.session.get(SafetyJournalPage, draft.page_id)
    if (page is None or page.trip_order_id is not None or page.author_id != current_user.id
            or page.status not in {"generated", "printed"}):
        abort(409)
    db.session.refresh(page, with_for_update=True)
    paper = page.paper_record
    if paper and (paper.checked_at or paper.filed_at or page.paper_scans):
        abort(409)
    old = {"instruction": page.instruction_number_snapshot, "class": page.group_label,
           "kind": page.briefing_kind_snapshot, "participants": len(page.participants)}
    page.instruction_version_id = draft.instruction_version_id
    page.library_item_id = draft.library_item_id
    page.subject_snapshot = payload["subject"]
    page.instructed_on = draft.instructed_on
    page.briefing_at = draft.briefing_at
    page.group_label = payload["group_label"]
    page.organization_name_snapshot = payload["organization_name"]
    page.instructor_name_snapshot = payload["instructor_name"]
    page.instruction_number_snapshot = payload["instruction_number"]
    page.instruction_title_snapshot = payload["instruction_title"]
    page.instruction_summary_snapshot = payload["instruction_summary"]
    page.instruction_file_sha256_snapshot = payload["instruction_file_sha256"]
    page.instruction_version_number_snapshot = payload["instruction_version_number"]
    page.briefing_kind_snapshot = payload["briefing_kind"]
    page.header_note_snapshot = payload["header_note"]
    page.trip_snapshot = payload.get("trip")
    SafetyJournalParticipant.query.filter_by(page_id=page.id).delete(synchronize_session=False)
    SafetyJournalPageClass.query.filter_by(page_id=page.id).delete(synchronize_session=False)
    db.session.expire(page, ["participants", "classes"])
    class_map = {}
    for sequence, person in enumerate(payload["participants"], 1):
        db.session.add(SafetyJournalParticipant(
            page_id=page.id, sequence=sequence, child_id=person["child_id"],
            full_name_snapshot=person["full_name"], birth_date_snapshot=date.fromisoformat(person["birth_date"]),
            class_name_snapshot=person["class_name"], class_id_snapshot=person["class_id"],
            signature_rule=person["signature_rule"],
        ))
        class_map[person["class_id"]] = person
    for person in class_map.values():
        db.session.add(SafetyJournalPageClass(
            page_id=page.id, class_id=person["class_id"],
            class_name_snapshot=person["class_name"], building_id_snapshot=person["building_id"],
        ))
    db.session.flush()
    db.session.expire(page, ["participants", "classes"])
    revision_number = (db.session.query(func.max(SafetyJournalPageRevision.version_number)).filter_by(page_id=page.id).scalar() or 0) + 1
    content = build_journal_pdf(page, page.participants)
    stored = f"{uuid4().hex}.pdf"
    try:
        with (_storage() / stored).open("xb") as destination:
            destination.write(content)
        db.session.add(SafetyJournalPageRevision(
            page_id=page.id, version_number=revision_number, stored_filename=stored,
            pdf_sha256=hashlib.sha256(content).hexdigest(), reason="Исправлены сведения журнала",
            created_by_id=current_user.id,
        ))
        page.status = "generated"
        page.printed_at = None
        if paper and paper.issue_at:
            paper.issue_at = None
            paper.issue_by_id = None
            paper.issue_note = None
        db.session.add(SafetyJournalPageEvent(
            page_id=page.id, actor_id=current_user.id, action="corrected",
            details={"from": old, "to": {"instruction": payload["instruction_number"],
                     "class": payload["group_label"], "kind": payload["briefing_kind"],
                     "participants": len(payload["participants"]), "revision": revision_number}},
        ))
        draft.status = "generated"
        db.session.commit()
    except Exception:
        db.session.rollback()
        (_storage() / stored).unlink(missing_ok=True)
        raise
    flash("Журнал исправлен. Новая версия PDF готова к печати; прежняя сохранена.", "success")
    return redirect(url_for("safety_journals.detail", page_id=page.id, preview=1))


@safety_journals_bp.route("/drafts/<uuid:draft_id>/settings", methods=["POST"])
@login_required
def save_settings(draft_id):
    draft = _draft_or_404(str(draft_id))
    if draft.status != "draft":
        abort(409)
    try:
        briefing_at = _briefing_from_form()
        on_date = date.fromisoformat(request.form.get("instructed_on", ""))
        if on_date > school_today():
            raise ValueError("Дата учёта не может быть в будущем.")
        if draft.trip_order_id is not None and (draft.trip_order.cancelled_at is not None or on_date > draft.trip_order.trip_date):
            raise ValueError("Инструктаж по выезду должен пройти не позднее даты действующего выезда.")
        grade = int(request.form.get("grade", "0"))
        if grade not in range(1, 12):
            raise ValueError("Выберите параллель с 1 по 11 класс.")
        class_ids = [int(value) for value in request.form.getlist("class_ids")]
        if not class_ids or len(class_ids) != len(set(class_ids)):
            raise ValueError("Выберите один или несколько классов без повторов.")
        if draft.trip_order_id is None and len(class_ids) != 1:
            raise ValueError("Для предметного журнала выберите один класс.")
        classes = journal_classes_for_user(on_date, current_user, grade, trip=draft.trip_order_id is not None)
        if not set(class_ids).issubset({item.id for item in classes}):
            raise ValueError("Класс недоступен в вашей нагрузке или на дату учёта.")
        version = db.session.get(SafetyInstructionVersion, int(request.form.get("instruction_version_id", "0")))
        if not instruction_is_effective(version, on_date):
            raise ValueError("Инструкция не действует на дату инструктажа.")
        if draft.trip_order_id is None:
            classroom = next(item for item in classes if item.id == class_ids[0])
            subject = (request.form.get("subject") or version.instruction.category).strip()
            allowed_subjects = journal_subjects_for_class(on_date, current_user, classroom)
            if not any(item.casefold() == subject.casefold() for item in allowed_subjects) or version.instruction.category.strip().casefold() != subject.casefold():
                raise ValueError("Выберите предмет из учебного плана или нагрузки класса и инструкцию к нему.")
        roster = roster_for_classes(on_date, class_ids)
        if not roster or len(roster) > 120:
            raise ValueError("В выбранных классах должно быть от 1 до 120 обучающихся.")
        draft.instructed_on = on_date
        draft.briefing_at = briefing_at
        draft.grade = grade
        draft.instruction_version_id = version.id
        draft.class_ids = class_ids
        draft.selected_child_ids = sorted(roster)
        draft.removed_child_ids = []
        _event(draft, "settings_saved", details={"class_ids": class_ids, "version_id": version.id, "count": len(roster)})
        db.session.commit()
        flash("Параметры сохранены. Проверьте список участников.", "success")
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("safety_journals.edit", draft_id=draft.id))


@safety_journals_bp.route("/drafts/<uuid:draft_id>/participants/select", methods=["POST"])
@login_required
def select_participants(draft_id):
    draft = _draft_or_404(str(draft_id))
    if draft.status != "draft" or not draft.class_ids or not draft.instructed_on:
        abort(409)
    try:
        selected_ids = [int(value) for value in request.form.getlist("child_ids")]
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("Ученик выбран несколько раз.")
        roster = roster_for_classes(draft.instructed_on, draft.class_ids)
        if not set(selected_ids).issubset(roster):
            raise ValueError("Список класса изменился. Обновите страницу.")
        external_ids = set(draft.selected_child_ids or []) - set(roster)
        combined = sorted(set(selected_ids) | external_ids)
        if len(combined) > 120:
            raise ValueError("В одной странице допустимо не более 120 участников.")
        draft.selected_child_ids = combined
        draft.removed_child_ids = sorted(set(roster) - set(selected_ids))
        _event(draft, "participants_selected", details={"count": len(combined)})
        db.session.commit()
        flash("Состав журнала сохранён.", "success")
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("safety_journals.edit", draft_id=draft.id))


@safety_journals_bp.route("/drafts/<uuid:draft_id>/participants", methods=["POST"])
@login_required
def change_participant(draft_id):
    draft = _draft_or_404(str(draft_id))
    if draft.status != "draft" or not draft.class_ids or not draft.instructed_on:
        abort(409)
    try:
        child_id = int(request.form.get("child_id", "0"))
        action = request.form.get("action")
        if action not in {"add", "remove", "restore"}:
            raise ValueError("Неизвестное действие со списком.")
        selected = list(draft.selected_child_ids or [])
        removed = list(draft.removed_child_ids or [])
        if action == "remove":
            if child_id not in selected:
                raise ValueError("Участника уже нет в списке.")
            selected.remove(child_id)
            if child_id not in removed:
                removed.append(child_id)
        else:
            if child_id in selected:
                raise ValueError("Участник уже добавлен.")
            if len(selected) >= 120:
                raise ValueError("В одной странице допустимо не более 120 участников.")
            selected_enrollments(draft.instructed_on, [child_id])
            selected.append(child_id)
            if child_id in removed:
                removed.remove(child_id)
        draft.selected_child_ids = selected
        draft.removed_child_ids = removed
        _event(draft, action, child_id=child_id)
        db.session.commit()
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("safety_journals.edit", draft_id=draft.id))


@safety_journals_bp.route("/drafts/<uuid:draft_id>/preview")
@login_required
def preview(draft_id):
    draft = _draft_or_404(str(draft_id))
    try:
        payload, digest = preview_payload(draft, current_user)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("safety_journals.edit", draft_id=draft.id))
    return render_template("safety_journals/preview.html", **_context(), draft=draft, payload=payload, digest=digest, local_time=_local_time)


@safety_journals_bp.route("/drafts/<uuid:draft_id>/generate", methods=["POST"])
@login_required
def generate(draft_id):
    draft = _draft_or_404(str(draft_id))
    return _generate_page(draft, require_digest=request.form.get("direct") != "1")


def _generate_page(draft, *, require_digest=False):
    if draft.trip_assignment_id is None and not can_create_journal(current_user):
        abort(403)
    stored = None
    try:
        payload, digest = preview_payload(draft, current_user)
        if require_digest and digest != request.form.get("preview_digest"):
            raise ValueError("Состав или данные изменились после предварительного просмотра. Проверьте страницу снова.")
        if draft.trip_assignment_id is not None:
            assignment = (
                SafetyTripAssignment.query.filter_by(id=draft.trip_assignment_id)
                .with_for_update().populate_existing().first()
            )
            existing = assignment.current_page if assignment else None
            if existing is not None and existing.trip_order_revision == draft.trip_order_revision and existing.status != "annulled":
                raise ValueError("Страница по этой редакции приказа уже сформирована.")
        if draft.page_id is not None:
            return _correct_page(draft, payload)
        page = SafetyJournalPage(
            number=f"TMP-{uuid4().hex}", source_draft_id=draft.id, author_id=current_user.id,
            kind=draft.journal_kind if draft.journal_kind == "class_teacher" else "trip" if "trip" in payload else "ordinary",
            trip_order_id=draft.trip_order_id, trip_assignment_id=draft.trip_assignment_id,
            trip_order_revision=draft.trip_order_revision, trip_snapshot=payload.get("trip"),
            instruction_version_id=draft.instruction_version_id,
            library_item_id=draft.library_item_id,
            subject_snapshot=payload["subject"],
            instructed_on=draft.instructed_on, briefing_at=draft.briefing_at,
            group_label=payload["group_label"],
            organization_name_snapshot=payload["organization_name"],
            instructor_name_snapshot=payload["instructor_name"],
            instruction_number_snapshot=payload["instruction_number"],
            instruction_title_snapshot=payload["instruction_title"],
            instruction_summary_snapshot=payload["instruction_summary"],
            instruction_file_sha256_snapshot=payload["instruction_file_sha256"],
            instruction_version_number_snapshot=payload["instruction_version_number"],
            briefing_kind_snapshot=payload["briefing_kind"],
            header_note_snapshot=payload["header_note"],
            status="generated",
        )
        db.session.add(page)
        db.session.flush()
        prefix = "ОТ-В" if page.kind == "trip" else "ОТ-КР" if page.kind == "class_teacher" else "ОТ"
        page.number = f"{prefix}-{draft.instructed_on.year}-{page.id:06d}"
        class_map = {}
        for sequence, person in enumerate(payload["participants"], 1):
            db.session.add(SafetyJournalParticipant(
                page_id=page.id, sequence=sequence, child_id=person["child_id"],
                full_name_snapshot=person["full_name"], birth_date_snapshot=date.fromisoformat(person["birth_date"]),
                class_name_snapshot=person["class_name"], class_id_snapshot=person["class_id"],
                signature_rule=person["signature_rule"],
            ))
            class_map[person["class_id"]] = person
        for person in class_map.values():
            db.session.add(SafetyJournalPageClass(
                page_id=page.id, class_id=person["class_id"],
                class_name_snapshot=person["class_name"], building_id_snapshot=person["building_id"],
            ))
        db.session.flush()
        pdf = build_journal_pdf(page, page.participants)
        stored = f"{uuid4().hex}.pdf"
        (_storage() / stored).write_bytes(pdf)
        db.session.add(SafetyJournalPageRevision(
            page_id=page.id, version_number=1, stored_filename=stored,
            pdf_sha256=hashlib.sha256(pdf).hexdigest(), reason="Первичное формирование",
            created_by_id=current_user.id,
        ))
        db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="generated", details={"count": len(payload["participants"])}))
        if draft.trip_assignment_id is not None:
            draft.trip_assignment.current_page_id = page.id
        draft.status = "generated"
        draft.page_id = page.id
        db.session.commit()
        flash("Страница сформирована. Откройте PDF и подтвердите печать после распечатки.", "success")
        return redirect(url_for("safety_journals.detail", page_id=page.id, preview=1))
    except ValueError as exc:
        db.session.rollback()
        if stored:
            (_storage() / stored).unlink(missing_ok=True)
        flash(str(exc), "danger")
        return redirect(url_for("safety_journals.preview" if require_digest else "safety_journals.edit", draft_id=draft.id))
    except IntegrityError:
        db.session.rollback()
        if stored:
            (_storage() / stored).unlink(missing_ok=True)
        existing = SafetyJournalPage.query.filter_by(source_draft_id=str(draft.id)).first()
        if existing:
            return redirect(url_for("safety_journals.detail", page_id=existing.id))
        flash("Страница уже формируется в другой вкладке. Обновите черновик.", "danger")
        return redirect(url_for("safety_journals.edit", draft_id=draft.id))
    except Exception:
        db.session.rollback()
        if stored:
            (_storage() / stored).unlink(missing_ok=True)
        raise


@safety_journals_bp.route("/pages/<int:page_id>")
@login_required
def detail(page_id):
    page = _page_or_404(page_id)
    db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="viewed"))
    db.session.commit()
    revision = page.revisions[-1]
    can_correct = (page.trip_order_id is None and page.author_id == current_user.id and page.status in {"generated", "printed"}
                   and not (page.paper_record and (page.paper_record.checked_at or page.paper_record.filed_at or page.paper_scans)))
    return render_template("safety_journals/detail.html", **_context(), page=page, revision=revision, local_time=_local_time, download_token=_token(page, revision), revision_tokens={item.id: _token(page, item) for item in page.revisions}, can_annul=page.author_id == current_user.id or is_officer(current_user), can_create=can_create_journal(current_user), paper_manager=_paper_manager(), can_correct=can_correct)


@safety_journals_bp.route("/pages/<int:page_id>/correct", methods=["POST"])
@login_required
def start_correction(page_id):
    page = _page_or_404(page_id)
    if (page.trip_order_id is not None or page.author_id != current_user.id or page.status not in {"generated", "printed"}
            or (page.paper_record and (page.paper_record.checked_at or page.paper_record.filed_at or page.paper_scans))):
        abort(409)
    existing = SafetyJournalDraft.query.filter_by(author_id=current_user.id, page_id=page.id, status="draft").first()
    if existing:
        return redirect(url_for("safety_journals.edit", draft_id=existing.id))
    class_id = page.classes[0].class_id if page.classes else None
    classroom = next((item for item in journal_classes_for_user(page.instructed_on, current_user,
                      trip=page.kind == "trip", homeroom=page.kind == "class_teacher") if item.id == class_id), None)
    draft = SafetyJournalDraft(
        id=str(uuid4()), author_id=current_user.id, page_id=page.id,
        journal_kind=page.kind, manual_trip=page.trip_snapshot if page.kind == "trip" else None,
        instructed_on=page.instructed_on, briefing_at=page.briefing_at,
        grade=classroom.grade if classroom else None,
        instruction_version_id=page.instruction_version_id,
        library_item_id=page.library_item_id, subject=page.subject_snapshot,
        briefing_kind=page.briefing_kind_snapshot or page.instruction_version.instruction.briefing_kind,
        header_note=page.header_note_snapshot,
        class_ids=[class_id] if class_id else [],
        selected_child_ids=[item.child_id for item in page.participants if item.child_id is not None],
        removed_child_ids=[],
    )
    db.session.add(draft)
    db.session.flush()
    _event(draft, "correction_started", details={"page_id": page.id})
    db.session.commit()
    return redirect(url_for("safety_journals.edit", draft_id=draft.id))


@safety_journals_bp.route("/pages/<int:page_id>/based-on", methods=["POST"])
@login_required
def based_on(page_id):
    page = _page_or_404(page_id)
    if not can_create_journal(current_user):
        abort(403)
    today = school_today()
    class_ids = [item.class_id for item in page.classes if item.class_id is not None]
    try:
        valid_classes = {item.id: item for item in available_classes(today)}
    except ValueError:
        valid_classes = {}
    class_ids = [class_id for class_id in class_ids if class_id in valid_classes]
    if class_ids:
        grade = valid_classes[class_ids[0]].grade
        class_ids = [class_id for class_id in class_ids if valid_classes[class_id].grade == grade]
        if len(roster_for_classes(today, class_ids)) > 120:
            class_ids = []
    draft = SafetyJournalDraft(
        id=str(uuid4()), author_id=current_user.id, instructed_on=today,
        journal_kind=page.kind,
        grade=valid_classes[class_ids[0]].grade if class_ids else None,
        instruction_version_id=page.instruction_version_id if instruction_is_effective(page.instruction_version, today) else None,
        library_item_id=page.library_item_id, subject=page.subject_snapshot,
        class_ids=class_ids, selected_child_ids=[], removed_child_ids=[],
    )
    if class_ids:
        draft.selected_child_ids = sorted(roster_for_classes(today, class_ids))
    db.session.add(draft)
    db.session.flush()
    _event(draft, "based_on", details={"source_page_id": page.id})
    db.session.commit()
    flash("Создан черновик на основе страницы. Проверьте инструкцию и состав.", "success")
    return redirect(url_for("safety_journals.edit", draft_id=draft.id))


@safety_journals_bp.route("/pages/<int:page_id>/pdf")
@safety_journals_bp.route("/pages/<int:page_id>/pdf/revisions/<int:revision_id>")
@login_required
def download_pdf(page_id, revision_id=None):
    page = _page_or_404(page_id)
    revision = db.session.get(SafetyJournalPageRevision, revision_id) if revision_id is not None else page.revisions[-1]
    if revision is None or revision.page_id != page.id:
        abort(404)
    try:
        values = URLSafeTimedSerializer(current_app.secret_key, salt="safety-journal-pdf-v1").loads(request.args.get("token", ""), max_age=900)
    except (BadSignature, SignatureExpired):
        abort(403)
    if values != {"page": page.id, "revision": revision.id, "user": current_user.id}:
        abort(403)
    path = _storage() / revision.stored_filename
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != revision.pdf_sha256:
        abort(409, "Сохранённый PDF недоступен или повреждён.")
    db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="downloaded", details={"revision": revision.version_number}))
    db.session.commit()
    response = send_file(path, mimetype="application/pdf", as_attachment=request.args.get("download") == "1", download_name=f"{page.number}.pdf")
    response.headers["Cache-Control"] = "private, no-store"
    return response


@safety_journals_bp.route("/pages/<int:page_id>/pdf/reissue", methods=["POST"])
@login_required
def reissue_pdf(page_id):
    page = _page_or_404(page_id)
    if page.author_id != current_user.id and not _paper_manager():
        abort(403)
    if page.status not in {"generated", "printed"}:
        abort(409)
    paper = page.paper_record
    if paper and (paper.checked_at or paper.filed_at or page.paper_scans):
        abort(409)
    stored = None
    try:
        db.session.refresh(page, with_for_update=True)
        revision_number = (db.session.query(func.max(SafetyJournalPageRevision.version_number)).filter_by(page_id=page.id).scalar() or 0) + 1
        content = build_journal_pdf(page, page.participants)
        stored = f"{uuid4().hex}.pdf"
        with (_storage() / stored).open("xb") as destination:
            destination.write(content)
        db.session.add(SafetyJournalPageRevision(
            page_id=page.id, version_number=revision_number, stored_filename=stored,
            pdf_sha256=hashlib.sha256(content).hexdigest(), reason="Исправленный бланк: даты и подписи от руки",
            created_by_id=current_user.id,
        ))
        if page.status == "printed":
            page.status = "generated"
            page.printed_at = None
            if page.trip_assignment_id is not None and page.trip_assignment.current_page_id == page.id:
                from app.services.safety_trip_service import reopen_assignment_task
                reopen_assignment_task(page.trip_assignment)
        if paper and paper.issue_at:
            paper.issue_at = None
            paper.issue_by_id = None
            paper.issue_note = None
        db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="pdf_reissued", details={"version": revision_number}))
        db.session.commit()
    except Exception:
        db.session.rollback()
        if stored:
            (_storage() / stored).unlink(missing_ok=True)
        raise
    flash("Исправленный бланк создан. Распечатайте новую версию; прежняя сохранена в истории.", "success")
    return redirect(url_for("safety_journals.detail", page_id=page.id))


@safety_journals_bp.route("/pages/<int:page_id>/printed", methods=["POST"])
@login_required
def confirm_printed(page_id):
    page = _page_or_404(page_id)
    if page.author_id != current_user.id or page.status != "generated":
        abort(409)
    page.status = "printed"
    page.printed_at = utc_now()
    if page.trip_assignment_id is not None:
        from app.services.safety_trip_service import complete_assignment_task
        complete_assignment_task(page.trip_assignment, page)
    db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="printed_confirmed"))
    db.session.commit()
    flash("Печать подтверждена.", "success")
    return redirect(url_for("safety_journals.detail", page_id=page.id))


@safety_journals_bp.route("/pages/<int:page_id>/paper/check", methods=["POST"])
@login_required
def paper_check(page_id):
    page = _page_or_404(page_id)
    if not _paper_manager():
        abort(403)
    if page.status != "printed":
        abort(409)
    if not all(request.form.get(flag) == "on" for flag in ("dates_checked", "signatures_checked", "roster_checked")):
        flash("Подтвердите сверку дат, подписей и состава на бумажном экземпляре.", "danger")
        return redirect(url_for("safety_journals.detail", page_id=page.id))
    record = _paper_record(page)
    if record.filed_at is not None or record.checked_at is not None:
        abort(409)
    note = (request.form.get("note") or "").strip()
    if len(note) > 2000:
        flash("Примечание не должно превышать 2000 символов.", "danger")
        return redirect(url_for("safety_journals.detail", page_id=page.id))
    record.checked_at = utc_now()
    record.checked_by_id = current_user.id
    record.check_note = note or None
    record.issue_at = None
    record.issue_by_id = None
    record.issue_note = None
    db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="paper_checked", details={"note": note}))
    db.session.commit()
    flash("Бумажный экземпляр сверен.", "success")
    return redirect(url_for("safety_journals.detail", page_id=page.id))


@safety_journals_bp.route("/pages/<int:page_id>/paper/issue", methods=["POST"])
@login_required
def paper_issue(page_id):
    page = _page_or_404(page_id)
    if not _paper_manager():
        abort(403)
    if page.status != "printed":
        abort(409)
    note = (request.form.get("issue_note") or "").strip()
    if not note or len(note) > 2000:
        flash("Опишите расхождение (до 2000 символов).", "danger")
        return redirect(url_for("safety_journals.detail", page_id=page.id))
    record = _paper_record(page)
    if record.filed_at is not None:
        abort(409)
    record.checked_at = None
    record.checked_by_id = None
    record.check_note = None
    record.issue_at = utc_now()
    record.issue_by_id = current_user.id
    record.issue_note = note
    db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="paper_issue", details={"note": note}))
    db.session.commit()
    flash("Расхождение зафиксировано. Сверьте исправленный бумажный экземпляр повторно.", "warning")
    return redirect(url_for("safety_journals.detail", page_id=page.id))


@safety_journals_bp.route("/pages/<int:page_id>/paper/file", methods=["POST"])
@login_required
def paper_file(page_id):
    page = _page_or_404(page_id)
    if not _paper_manager():
        abort(403)
    record = page.paper_record
    if page.status != "printed" or record is None or record.checked_at is None or record.filed_at is not None:
        abort(409)
    binder_ref = (request.form.get("binder_ref") or "").strip()
    sheet_ref = (request.form.get("sheet_ref") or "").strip()
    if not binder_ref or len(binder_ref) > 255 or len(sheet_ref) > 80:
        flash("Укажите место хранения (до 255 символов) и номер листа (до 80 символов).", "danger")
        return redirect(url_for("safety_journals.detail", page_id=page.id))
    record.binder_ref = binder_ref
    record.sheet_ref = sheet_ref or None
    record.filed_at = utc_now()
    record.filed_by_id = current_user.id
    db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="paper_filed", details={"binder_ref": binder_ref, "sheet_ref": sheet_ref}))
    db.session.commit()
    flash("Подшивка бумажного экземпляра зафиксирована.", "success")
    return redirect(url_for("safety_journals.detail", page_id=page.id))


@safety_journals_bp.route("/pages/<int:page_id>/paper/scans", methods=["POST"])
@login_required
def paper_scan_upload(page_id):
    page = _page_or_404(page_id)
    if not _paper_manager():
        abort(403)
    record = page.paper_record
    if page.status != "printed" or record is None or record.checked_at is None:
        abort(409)
    try:
        original_name, suffix, mime, content = _scan_upload()
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("safety_journals.detail", page_id=page.id))
    db.session.refresh(page, with_for_update=True)
    version = (db.session.query(func.max(SafetyJournalPaperScan.version_number)).filter_by(page_id=page.id).scalar() or 0) + 1
    stored = f"{uuid4().hex}{suffix}"
    path = _scan_storage() / stored
    try:
        with path.open("xb") as destination:
            destination.write(content)
        db.session.add(SafetyJournalPaperScan(
            page_id=page.id, version_number=version, stored_filename=stored,
            original_filename=original_name, mime_type=mime,
            file_sha256=hashlib.sha256(content).hexdigest(), uploaded_by_id=current_user.id,
        ))
        db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="paper_scan_uploaded", details={"version": version, "sha256": hashlib.sha256(content).hexdigest()}))
        db.session.commit()
    except Exception:
        db.session.rollback()
        path.unlink(missing_ok=True)
        raise
    flash("Скан сохранён. Предыдущие версии остаются в истории.", "success")
    return redirect(url_for("safety_journals.detail", page_id=page.id))


@safety_journals_bp.route("/pages/<int:page_id>/paper/scans/<int:scan_id>")
@login_required
def paper_scan_download(page_id, scan_id):
    page = _page_or_404(page_id)
    scan = db.session.get(SafetyJournalPaperScan, scan_id)
    if scan is None or scan.page_id != page.id:
        abort(404)
    path = _scan_storage() / scan.stored_filename
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != scan.file_sha256:
        abort(409, "Сохранённый скан недоступен или повреждён.")
    db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="paper_scan_downloaded", details={"version": scan.version_number}))
    db.session.commit()
    response = send_file(path, mimetype=scan.mime_type, as_attachment=True, download_name=scan.original_filename)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@safety_journals_bp.route("/pages/<int:page_id>/annul", methods=["POST"])
@login_required
def annul(page_id):
    page = _page_or_404(page_id)
    if page.author_id != current_user.id and not is_officer(current_user):
        abort(403)
    if page.status == "annulled":
        abort(409)
    reason = (request.form.get("reason") or "").strip()
    if not reason or len(reason) > 2000:
        flash("Укажите причину аннулирования до 2000 символов.", "danger")
        return redirect(url_for("safety_journals.detail", page_id=page.id))
    page.status = "annulled"
    page.annulled_at = utc_now()
    page.annulled_by_id = current_user.id
    page.annul_reason = reason
    if page.trip_assignment_id is not None and page.trip_assignment.current_page_id == page.id:
        from app.services.safety_trip_service import reopen_assignment_task
        page.trip_assignment.current_page_id = None
        reopen_assignment_task(page.trip_assignment)
    db.session.add(SafetyJournalPageEvent(page_id=page.id, actor_id=current_user.id, action="annulled", details={"reason": reason}))
    db.session.commit()
    flash("Страница аннулирована; PDF сохранён в истории.", "success")
    return redirect(url_for("safety_journals.detail", page_id=page.id))
