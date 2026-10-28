"""Approved instruction catalog. Originals are stored by version and never overwritten."""

import hashlib
import json
import re
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.extensions import db
from app.models import SafetyInstruction, SafetyInstructionAccessEvent, SafetyInstructionVersion, SafetyJournalDraft, SafetyTripAssignment
from app.services.safety_journal_service import can_create_journal
from app.services.safety_passport_service import can_manage_instructions, is_admin, is_director, is_officer, school_today


safety_instructions_bp = Blueprint("safety_instructions", __name__, url_prefix="/safety/instructions")
MAX_FILE_BYTES = 15 * 1024 * 1024


def _can_read():
    return bool(
        can_create_journal(current_user) or is_officer(current_user) or is_director(current_user)
        or is_admin(current_user) or SafetyTripAssignment.query.filter_by(user_id=current_user.id, is_active=True).first()
    )


def _store_dir():
    base = current_app.config.get("UPLOAD_FOLDER")
    if not base:
        raise RuntimeError("Не настроено хранилище документов.")
    path = Path(base) / "safety" / "instructions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _library_dir():
    return Path(current_app.config["UPLOAD_FOLDER"]) / "safety" / "library"


def _library_items():
    manifest = _library_dir() / "manifest.json"
    if not manifest.is_file():
        return []
    try:
        items = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        current_app.logger.exception("Unable to read safety instruction library manifest")
        abort(503)
    if not isinstance(items, list):
        abort(503)
    return items


def journal_library_items():
    """List reference PDFs that can be chosen for a standalone trip journal."""
    return _library_items()


def library_items_for_section(section):
    """List reference PDFs explicitly assigned to a journal section."""
    return [item for item in _library_items() if item.get("section") == section]


def library_suggestions(subject):
    """Find reference PDFs for a school subject, including Russian case endings."""
    normalized = subject.strip().casefold().replace("ё", "е")
    aliases = {
        "информатика": ("информатик",),
        "физика": ("физик",),
        "химия": ("хим",),
        "биология": ("биолог",),
        "технология": ("технолог",),
        "физическая культура": ("физическ", "физкультур"),
    }
    terms = aliases.get(normalized) or tuple(
        word[:-2] if word.endswith(("ия", "ие")) else word[:-1] if word.endswith(("а", "я", "и", "ы")) else word
        for word in re.findall(r"[а-яa-z]+", normalized)
        if len(word) >= 5
    )
    if not terms:
        return []
    known_hashes = {row.file_sha256 for row in SafetyInstructionVersion.query.with_entities(SafetyInstructionVersion.file_sha256).all()}
    return [
        {**item, "in_catalog": item.get("id") in known_hashes}
        for item in _library_items()
        if item.get("section") != "class_teacher"
        if any(term in item.get("title", "").casefold().replace("ё", "е") for term in terms)
    ]


def journal_library_item(item_id, subject=None, section=None):
    """Resolve a reference PDF; subject matching applies to class journals."""
    if not re.fullmatch(r"[0-9a-f]{64}", item_id or ""):
        raise ValueError("Выберите инструкцию из перечня PDF.")
    candidates = library_items_for_section(section) if section else library_suggestions(subject) if subject else _library_items()
    item = next((entry for entry in candidates if entry.get("id") == item_id), None)
    if item is None:
        raise ValueError("Выбранный PDF не подходит для журнала или удалён из перечня.")
    path = _library_dir() / f"{item_id}.pdf"
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item_id:
        raise ValueError("Файл инструкции недоступен или повреждён.")
    return item


def _library_item(item_id):
    if not re.fullmatch(r"[0-9a-f]{64}", item_id):
        abort(404)
    item = next((entry for entry in _library_items() if entry.get("id") == item_id), None)
    if item is None:
        abort(404)
    path = _library_dir() / f"{item_id}.pdf"
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item_id:
        abort(409, "Файл инструкции недоступен или повреждён.")
    return item, path


@safety_instructions_bp.route("/library")
@login_required
def library():
    if not _can_read():
        abort(403)
    from app.modules.hub.routes import build_home_context
    query = (request.args.get("q") or "").strip()[:120]
    section = request.args.get("section") if request.args.get("section") == "class_teacher" else ""
    items = _library_items()
    matching = [item for item in items if (not section or item.get("section") == section)
                and (not query or query.casefold() in item["title"].casefold())]
    return render_template(
        "safety_instructions/library.html", workspace_nav=build_home_context(),
        workspace_context_title="Техника безопасности", workspace_context_subtitle="Библиотека инструкций",
        items=matching, total=len(items), query=query, section=section,
        can_manage=can_manage_instructions(current_user),
    )


@safety_instructions_bp.route("/library/<item_id>/pdf")
@login_required
def library_pdf(item_id):
    if not _can_read():
        abort(403)
    item, path = _library_item(item_id)
    response = send_file(
        path, mimetype="application/pdf", as_attachment=request.args.get("download") == "1",
        download_name=item["filename"],
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@safety_instructions_bp.route("/library/<item_id>/catalog", methods=["GET", "POST"])
@login_required
def add_library_to_catalog(item_id):
    if not can_manage_instructions(current_user):
        abort(403)
    item, path = _library_item(item_id)
    suggested_number, _, suggested_title = item["title"].partition(" ")
    subject = (request.values.get("subject") or "").strip()[:120]
    draft_id = (request.values.get("draft_id") or "").strip()
    draft = SafetyJournalDraft.query.filter_by(id=draft_id, author_id=current_user.id, status="draft").first() if draft_id else None
    if request.method == "POST":
        try:
            data = _parse_form()
            _save_new_instruction(data, item["filename"], ".pdf", "application/pdf", path.read_bytes())
            flash("Инструкция добавлена в каталог для журналов.", "success")
            if draft:
                return redirect(url_for(
                    "safety_journals.edit", draft_id=draft.id, grade=request.form.get("grade"),
                    class_id=request.form.get("class_id"), instructed_on=request.form.get("instructed_on"),
                    subject=data["category"],
                ))
            return redirect(url_for("safety_instructions.index"))
        except (ValueError, IntegrityError) as exc:
            flash(str(exc) if isinstance(exc, ValueError) else "Инструкция уже изменена. Обновите страницу.", "danger")
    from app.modules.hub.routes import build_home_context
    return render_template(
        "safety_instructions/from_library.html", workspace_nav=build_home_context(),
        workspace_context_title="Техника безопасности", workspace_context_subtitle="Добавить в каталог",
        item=item, number=suggested_number, title=suggested_title or item["title"],
        form=request.form if request.method == "POST" else {}, subject=subject,
        draft_id=draft.id if draft else "", grade=request.values.get("grade", ""),
        class_id=request.values.get("class_id", ""), instructed_on=request.values.get("instructed_on", ""),
    )


def _uploaded_original():
    file = request.files.get("original")
    if not file or not file.filename:
        raise ValueError("Приложите утверждённый PDF или DOCX.")
    name = Path(file.filename.replace("\\", "/")).name
    if len(name) > 255:
        raise ValueError("Слишком длинное имя файла.")
    content = file.stream.read(MAX_FILE_BYTES + 1)
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("Файл пуст или превышает 15 МБ.")
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf" and content.startswith(b"%PDF-"):
        mime = "application/pdf"
    elif suffix == ".docx":
        try:
            with ZipFile(BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("Некорректный DOCX-файл.")
        except BadZipFile as exc:
            raise ValueError("Некорректный DOCX-файл.") from exc
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise ValueError("Допустим только PDF или DOCX с соответствующим содержимым.")
    return name, suffix, mime, content


def _parse_form():
    fields = {}
    for name, maximum in (("number", 80), ("title", 500), ("category", 120), ("briefing_kind", 80), ("approval_basis", 500), ("summary", 500)):
        value = (request.form.get(name) or "").strip()
        if not value or len(value) > maximum:
            raise ValueError(f"Заполните поле «{name}» (до {maximum} символов).")
        fields[name] = value
    for name, maximum in (("scope", 2000), ("classroom_type", 80), ("event_kind", 80)):
        value = (request.form.get(name) or "").strip()
        if len(value) > maximum:
            raise ValueError(f"Поле «{name}» слишком длинное.")
        fields[name] = value or None
    try:
        fields["approved_on"] = date.fromisoformat(request.form.get("approved_on", ""))
        fields["effective_from"] = date.fromisoformat(request.form.get("effective_from", ""))
        fields["effective_to"] = date.fromisoformat(request.form["effective_to"]) if request.form.get("effective_to") else None
    except ValueError as exc:
        raise ValueError("Укажите корректные даты утверждения и действия.") from exc
    if fields["approved_on"] > fields["effective_from"] or (fields["effective_to"] and fields["effective_to"] < fields["effective_from"]):
        raise ValueError("Проверьте порядок дат инструкции.")
    return fields


def _save_new_instruction(data, name, suffix, mime, content):
    if SafetyInstruction.query.filter_by(number=data["number"]).first():
        raise ValueError("Инструкция с таким номером уже есть. Добавьте новую версию.")
    stored = f"{uuid4().hex}{suffix}"
    try:
        (_store_dir() / stored).write_bytes(content)
        instruction = SafetyInstruction(
            number=data["number"], title=data["title"], category=data["category"],
            briefing_kind=data["briefing_kind"], scope=data["scope"],
            classroom_type=data["classroom_type"], event_kind=data["event_kind"],
            created_by_id=current_user.id,
        )
        db.session.add(instruction)
        db.session.flush()
        version = SafetyInstructionVersion(
            instruction_id=instruction.id, version_number=1, title_snapshot=data["title"],
            approved_on=data["approved_on"], effective_from=data["effective_from"],
            effective_to=data["effective_to"], status="active", approval_basis=data["approval_basis"],
            summary=data["summary"], original_filename=name, stored_filename=stored,
            file_sha256=hashlib.sha256(content).hexdigest(), file_mime_type=mime,
            created_by_id=current_user.id,
        )
        db.session.add(version)
        db.session.flush()
        db.session.add(SafetyInstructionAccessEvent(version_id=version.id, actor_id=current_user.id, action="created"))
        db.session.commit()
    except Exception:
        db.session.rollback()
        (_store_dir() / stored).unlink(missing_ok=True)
        raise


@safety_instructions_bp.route("/")
@login_required
def index():
    if not _can_read():
        abort(403)
    from app.modules.hub.routes import build_home_context
    query = (request.args.get("q") or "").strip()[:120]
    instructions = SafetyInstruction.query.options(selectinload(SafetyInstruction.versions)).order_by(SafetyInstruction.number).all()
    if query:
        term = query.casefold()
        instructions = [item for item in instructions if term in item.number.casefold() or term in item.title.casefold() or term in item.category.casefold()]
    return render_template(
        "safety_instructions/index.html", workspace_nav=build_home_context(),
        workspace_context_title="Техника безопасности", workspace_context_subtitle="Инструкции",
        instructions=instructions, query=query, can_manage=can_manage_instructions(current_user), today=school_today(),
    )


@safety_instructions_bp.route("/<int:instruction_id>")
@login_required
def detail(instruction_id):
    if not _can_read():
        abort(403)
    instruction = db.session.get(SafetyInstruction, instruction_id) or abort(404)
    from app.modules.hub.routes import build_home_context
    return render_template(
        "safety_instructions/detail.html", workspace_nav=build_home_context(),
        workspace_context_title="Техника безопасности", workspace_context_subtitle="Инструкция",
        instruction=instruction, can_manage=can_manage_instructions(current_user), today=school_today(),
    )


@safety_instructions_bp.route("/new", methods=["POST"])
@login_required
def create():
    if not can_manage_instructions(current_user):
        abort(403)
    try:
        data = _parse_form()
        name, suffix, mime, content = _uploaded_original()
        _save_new_instruction(data, name, suffix, mime, content)
        flash("Инструкция добавлена.", "success")
    except (ValueError, IntegrityError) as exc:
        flash(str(exc) if isinstance(exc, ValueError) else "Инструкция уже изменена. Обновите страницу.", "danger")
    return redirect(url_for("safety_instructions.index"))


@safety_instructions_bp.route("/<int:instruction_id>/versions", methods=["POST"])
@login_required
def add_version(instruction_id):
    if not can_manage_instructions(current_user):
        abort(403)
    instruction = db.session.get(SafetyInstruction, instruction_id) or abort(404)
    stored = None
    try:
        data = _parse_form()
        if data["number"] != instruction.number:
            raise ValueError("Номер инструкции при смене версии не меняется.")
        old = max(instruction.versions, key=lambda item: item.version_number)
        if data["effective_from"] <= old.effective_from:
            raise ValueError("Новая версия должна вступить в силу позже предыдущей.")
        name, suffix, mime, content = _uploaded_original()
        stored = f"{uuid4().hex}{suffix}"
        (_store_dir() / stored).write_bytes(content)
        if old.status == "active":
            old.effective_to = min(old.effective_to or date.max, data["effective_from"] - timedelta(days=1))
        instruction.title = data["title"]
        instruction.category = data["category"]
        instruction.briefing_kind = data["briefing_kind"]
        instruction.scope = data["scope"]
        instruction.classroom_type = data["classroom_type"]
        instruction.event_kind = data["event_kind"]
        version = SafetyInstructionVersion(
            instruction_id=instruction.id, version_number=old.version_number + 1,
            title_snapshot=data["title"], approved_on=data["approved_on"],
            effective_from=data["effective_from"], effective_to=data["effective_to"],
            status="active", approval_basis=data["approval_basis"], summary=data["summary"],
            original_filename=name, stored_filename=stored,
            file_sha256=hashlib.sha256(content).hexdigest(), file_mime_type=mime,
            replaced_version_id=old.id, created_by_id=current_user.id,
        )
        db.session.add(version)
        db.session.flush()
        db.session.add(SafetyInstructionAccessEvent(version_id=version.id, actor_id=current_user.id, action="new_version"))
        db.session.commit()
        flash("Новая версия инструкции сохранена; прежняя доступна в истории.", "success")
    except (ValueError, IntegrityError) as exc:
        db.session.rollback()
        if stored:
            (_store_dir() / stored).unlink(missing_ok=True)
        flash(str(exc) if isinstance(exc, ValueError) else "Версия уже изменена. Обновите страницу.", "danger")
    return redirect(url_for("safety_instructions.detail", instruction_id=instruction_id))


@safety_instructions_bp.route("/versions/<int:version_id>/archive", methods=["POST"])
@login_required
def archive(version_id):
    if not can_manage_instructions(current_user):
        abort(403)
    version = db.session.get(SafetyInstructionVersion, version_id) or abort(404)
    version.status = "archived"
    db.session.add(SafetyInstructionAccessEvent(version_id=version.id, actor_id=current_user.id, action="archived"))
    db.session.commit()
    flash("Версия перенесена в архив. Исторические журналы сохранятся.", "success")
    return redirect(url_for("safety_instructions.detail", instruction_id=version.instruction_id))


@safety_instructions_bp.route("/versions/<int:version_id>/original")
@login_required
def download_original(version_id):
    if not _can_read():
        abort(403)
    version = db.session.get(SafetyInstructionVersion, version_id) or abort(404)
    path = _store_dir() / version.stored_filename
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != version.file_sha256:
        abort(409, "Оригинал инструкции недоступен или повреждён.")
    inline = request.args.get("inline") == "1" and version.file_mime_type == "application/pdf"
    db.session.add(SafetyInstructionAccessEvent(version_id=version.id, actor_id=current_user.id, action="preview" if inline else "download"))
    db.session.commit()
    response = send_file(path, mimetype=version.file_mime_type, as_attachment=not inline, download_name=version.original_filename)
    response.headers["Cache-Control"] = "private, no-store"
    return response
