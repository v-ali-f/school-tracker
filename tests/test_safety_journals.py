"""Stage 2 acceptance paths: access, roster edits, frozen PDF, and age rules."""

from datetime import date, datetime, timedelta
from io import BytesIO
import re
from html import unescape
from types import SimpleNamespace

import pdfplumber

from app.core.extensions import db
from app.models import (
    AcademicYear, Child, ChildEnrollment, OrganizationSettings, SafetyInstruction,
    SafetyInstructionAccessEvent, SafetyInstructionVersion, SafetyJournalDraft,
    SafetyJournalDraftEvent, SafetyJournalPage, SafetyJournalPageEvent,
    SafetyOfficerAssignment, SchoolClass, User,
)
from app.services.safety_passport_service import school_today
from app.services.safety_journal_pdf import build_journal_pdf


def _setup(app, make_user, tmp_path):
    director_id = make_user("DIRECTOR")
    officer_id = make_user("TEACHER")
    teacher_id = make_user("TEACHER")
    other_id = make_user("TEACHER")
    viewer_id = make_user("VIEWER")
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    with app.app_context():
        today = school_today()
        year = AcademicYear(name=f"{today.year - 1}/{today.year + 1}", start_date=today - timedelta(days=300), end_date=today + timedelta(days=300), is_current=True)
        db.session.add(year)
        db.session.flush()
        first_class = SchoolClass(academic_year_id=year.id, name="5А", grade=5)
        second_class = SchoolClass(academic_year_id=year.id, name="5Б", grade=5)
        db.session.add_all([first_class, second_class])
        db.session.flush()
        children = [
            Child(last_name="Александров", first_name="Илья", birth_date=date(today.year - 14, today.month, today.day)),
            Child(last_name="Борисова", first_name="Анна", birth_date=date(today.year - 14, today.month, today.day) + timedelta(days=1)),
            Child(last_name="Васильев", first_name="Пётр", birth_date=date(today.year - 14, today.month, today.day)),
        ]
        db.session.add_all(children)
        db.session.flush()
        enrolled_at = datetime.combine(today - timedelta(days=100), datetime.min.time())
        db.session.add_all([
            ChildEnrollment(child_id=children[0].id, academic_year_id=year.id, school_class_id=first_class.id, enrolled_at=enrolled_at),
            ChildEnrollment(child_id=children[1].id, academic_year_id=year.id, school_class_id=first_class.id, enrolled_at=enrolled_at),
            ChildEnrollment(child_id=children[2].id, academic_year_id=year.id, school_class_id=second_class.id, enrolled_at=enrolled_at),
            OrganizationSettings(full_name="ГБОУ Школа Тест", is_active=True),
            SafetyOfficerAssignment(user_id=officer_id, assigned_by_id=director_id, valid_from=today - timedelta(days=1), can_manage_instructions=True),
        ])
        db.session.commit()
        return {
            "director": director_id, "officer": officer_id, "teacher": teacher_id,
            "other": other_id, "viewer": viewer_id, "class": first_class.id,
            "children": [child.id for child in children], "today": today,
        }


def _instruction_form(today, **extra):
    values = {
        "number": "ИОТ-1", "title": "Безопасность на уроке", "category": "Общие",
        "briefing_kind": "первичный", "approval_basis": "Приказ № 1",
        "summary": "Правила поведения в кабинете", "approved_on": (today - timedelta(days=5)).isoformat(),
        "effective_from": (today - timedelta(days=5)).isoformat(),
        "original": (BytesIO(b"%PDF-1.4 test original"), "Инструкция.pdf"),
    }
    values.update(extra)
    return values


def test_catalog_rights_versions_and_immutable_original(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    login(ids["teacher"])
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"]), content_type="multipart/form-data").status_code == 403
    login(ids["officer"])
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"]), content_type="multipart/form-data").status_code == 302
    with app.app_context():
        version = SafetyInstructionVersion.query.one()
        old_id, old_hash, old_file = version.id, version.file_sha256, version.stored_filename
    assert client.get(f"/safety/instructions/versions/{old_id}/original").data.startswith(b"%PDF")
    assert client.post("/safety/instructions/1/versions", data=_instruction_form(
        ids["today"], title="Новая редакция", effective_from=(ids["today"] + timedelta(days=1)).isoformat(),
    ), content_type="multipart/form-data").status_code == 302
    with app.app_context():
        instruction = SafetyInstruction.query.one()
        assert [v.status for v in instruction.versions] == ["active", "active"]
        assert instruction.versions[0].effective_to == ids["today"]
        assert instruction.versions[0].file_sha256 == old_hash
        assert instruction.versions[0].stored_filename == old_file
        assert instruction.versions[0].title_snapshot == "Безопасность на уроке"
        assert instruction.versions[1].title_snapshot == "Новая редакция"
        assert [event.action for event in SafetyInstructionAccessEvent.query.order_by(SafetyInstructionAccessEvent.id)] == ["created", "download", "new_version"]
    login(ids["viewer"])
    assert client.get(f"/safety/instructions/versions/{old_id}/original").status_code == 403


def test_journal_roster_snapshot_pdf_and_print_confirmation(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    login(ids["officer"])
    client.post("/safety/instructions/new", data=_instruction_form(ids["today"]), content_type="multipart/form-data")
    with app.app_context():
        version_id = SafetyInstructionVersion.query.one().id
    login(ids["teacher"])
    response = client.post("/safety/journals/new")
    draft_url = response.headers["Location"]
    assert client.get(draft_url).status_code == 200
    settings = client.post(f"{draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "grade": "5",
        "instruction_version_id": str(version_id), "class_ids": [str(ids["class"])],
    })
    assert settings.status_code == 302
    with app.app_context():
        draft = SafetyJournalDraft.query.one()
        assert len(draft.selected_child_ids) == 2
    first, second, third = ids["children"]
    assert client.post(f"{draft_url}/participants", data={"action": "remove", "child_id": first}).status_code == 302
    assert client.post(f"{draft_url}/participants", data={"action": "restore", "child_id": first}).status_code == 302
    assert client.post(f"{draft_url}/participants", data={"action": "add", "child_id": third}).status_code == 302
    assert client.post(f"{draft_url}/participants", data={"action": "add", "child_id": third}).status_code == 302
    with app.app_context():
        draft = SafetyJournalDraft.query.one()
        assert len(draft.selected_child_ids) == 3
        assert [event.action for event in draft.events] == ["created", "settings_saved", "remove", "restore", "add"]
    preview = client.get(f"{draft_url}/preview")
    assert preview.status_code == 200
    digest = re.search(r'name="preview_digest" value="([^"]+)"', preview.get_data(as_text=True)).group(1)
    assert client.post(f"{draft_url}/generate", data={"preview_digest": "stale"}).status_code == 302
    with app.app_context():
        assert SafetyJournalPage.query.count() == 0
    generated = client.post(f"{draft_url}/generate", data={"preview_digest": digest})
    assert generated.status_code == 302
    page_url = generated.headers["Location"]
    detail = client.get(page_url)
    assert detail.status_code == 200
    pdf_link = unescape(re.search(r'href="([^"]+/pdf\?token=[^"]+)"', detail.get_data(as_text=True)).group(1))
    pdf = client.get(pdf_link)
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    with pdfplumber.open(BytesIO(pdf.data)) as document:
        text = "\n".join(page.extract_text() or "" for page in document.pages)
        assert "ознакомлен" in text
        assert (ids["today"] - timedelta(days=14 * 365)).strftime("%d.%m.%Y") not in text
        assert date(ids["today"].year - 14, ids["today"].month, ids["today"].day).strftime("%d.%m.%Y") not in text
        assert "ГБОУ Школа Тест" in text
    assert client.get(page_url + "/pdf").status_code == 403
    with app.app_context():
        page = SafetyJournalPage.query.one()
        assert page.number.startswith("ОТ-") and len(page.participants) == 3
        rules = {item.child_id: item.signature_rule for item in page.participants}
        assert rules[first] == "handwritten" and rules[second] == "acquainted"
        assert page.status == "generated" and page.printed_at is None
        original_pdf_hash = page.revisions[0].pdf_sha256
        db.session.get(Child, first).last_name = "Переименован"
        db.session.commit()
        assert page.participants[0].full_name_snapshot != "Переименован Илья"
    assert client.post(page_url + "/printed").status_code == 302
    with app.app_context():
        page = SafetyJournalPage.query.one()
        assert page.status == "printed" and page.printed_at is not None
        assert page.revisions[0].pdf_sha256 == original_pdf_hash
        assert SafetyJournalPageEvent.query.filter_by(action="downloaded").count() == 1
    assert client.post(page_url + "/based-on").status_code == 302
    with app.app_context():
        assert SafetyJournalDraft.query.count() == 2
        copy = SafetyJournalDraft.query.filter_by(status="draft").one()
        assert len(copy.selected_child_ids) == 3
        assert copy.events[0].action == "based_on"
    login(ids["other"])
    assert client.get(page_url).status_code == 403
    assert client.get(pdf_link).status_code == 403
    login(ids["officer"])
    assert client.get(page_url).status_code == 200


def test_pdf_repeats_nine_column_header_on_each_sheet(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    login(ids["officer"])
    client.post("/safety/instructions/new", data=_instruction_form(ids["today"]), content_type="multipart/form-data")
    with app.app_context():
        version = SafetyInstructionVersion.query.one()
        page = SafetyJournalPage(
            number="ОТ-2026-000999", source_draft_id="synthetic-pdf-preview", author_id=ids["teacher"], instruction_version_id=version.id,
            instructed_on=ids["today"], group_label="5А", organization_name_snapshot="ГБОУ Школа Тест",
            instructor_name_snapshot="Иванов Иван Иванович", instruction_number_snapshot="ИОТ-1",
            instruction_title_snapshot="Безопасность на уроке", instruction_summary_snapshot="Правила поведения в кабинете",
            instruction_file_sha256_snapshot=version.file_sha256, instruction_version_number_snapshot=1,
        )
        people = [SimpleNamespace(sequence=n, full_name_snapshot=f"Ученик {n}", class_name_snapshot="5А", signature_rule="handwritten") for n in range(1, 81)]
        content = build_journal_pdf(page, people)
    with pdfplumber.open(BytesIO(content)) as document:
        assert len(document.pages) > 1
        for sheet in document.pages:
            text = sheet.extract_text() or ""
            assert "Дата рождения" in text
            assert "Подпись" in text
            assert "Иванов Иван Иванович" in text
