"""Stage 2 acceptance paths: access, roster edits, frozen PDF, and age rules."""

from datetime import date, datetime, timedelta
from io import BytesIO
import hashlib
import json
import re
from html import unescape
from types import SimpleNamespace

import pdfplumber

from app.core.extensions import db
from app.models import (
    AcademicYear, Child, ChildEnrollment, EducationActivity, EducationPlan,
    EducationPlanLine, OrganizationSettings, PopulationSnapshot,
    PopulationSnapshotClass, SafetyInstruction,
    SafetyInstructionAccessEvent, SafetyInstructionVersion, SafetyJournalDraft,
    SafetyJournalDraftEvent, SafetyJournalPage, SafetyJournalPageEvent,
    SafetyOfficerAssignment, SchoolClass, TariffCycle, TariffVersion, TeacherLoad,
    TeachingGroup, TeachingGroupClass, User, WorkloadAssignment, WorkloadNeed,
)
from app.services.safety_journal_service import journal_classes_for_user, journal_subjects_for_class
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
            TeacherLoad(teacher_id=teacher_id, academic_year_id=year.id, class_name="5А", grade=5, subject_name="Общие", hours=2),
            TeacherLoad(teacher_id=teacher_id, academic_year_id=year.id, class_name="5А", grade=5, subject_name="Физика", hours=2),
            TeacherLoad(teacher_id=other_id, academic_year_id=year.id, class_name="5Б", grade=5, subject_name="Общие", hours=2),
        ])
        db.session.commit()
        return {
            "director": director_id, "officer": officer_id, "teacher": teacher_id,
            "other": other_id, "viewer": viewer_id, "class": first_class.id, "other_class": second_class.id,
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


def test_teacher_can_view_print_and_download_reference_pdf(app, client, make_user, login, tmp_path):
    teacher_id = make_user("TEACHER")
    viewer_id = make_user("VIEWER")
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    folder = tmp_path / "safety" / "library"
    folder.mkdir(parents=True)
    content = b"%PDF-1.4 example reference"
    digest = hashlib.sha256(content).hexdigest()
    (folder / f"{digest}.pdf").write_bytes(content)
    (folder / "manifest.json").write_text(json.dumps([
        {"id": digest, "title": "ИОП-01 Вводный инструктаж", "filename": "ИОП-01.pdf"}
    ], ensure_ascii=False), encoding="utf-8")

    login(teacher_id)
    assert "ИОП-01" in client.get("/safety/instructions/library").get_data(as_text=True)
    library_html = client.get("/safety/instructions/library").get_data(as_text=True)
    assert "registry-matrix" in library_html and 'id="safety-pdf-preview-modal"' in library_html
    assert 'data-bs-target="#safety-pdf-preview-modal"' in library_html
    assert "ИОП-01" in client.get("/safety/instructions/library?q=ИОП-01").get_data(as_text=True)
    assert "По запросу ничего не найдено" in client.get("/safety/instructions/library?q=несуществующая").get_data(as_text=True)
    inline = client.get(f"/safety/instructions/library/{digest}/pdf")
    assert inline.status_code == 200 and inline.data == content
    assert inline.headers["Content-Disposition"].startswith("inline")
    assert inline.headers["Content-Disposition"].startswith("inline;")
    downloaded = client.get(f"/safety/instructions/library/{digest}/pdf?download=1")
    assert downloaded.status_code == 200
    assert downloaded.headers["Content-Disposition"].startswith("attachment;")
    assert client.get("/safety/instructions/library/not-an-id/pdf").status_code == 404
    (folder / f"{digest}.pdf").write_bytes(b"changed")
    assert client.get(f"/safety/instructions/library/{digest}/pdf").status_code == 409
    login(viewer_id)
    assert client.get("/safety/instructions/library").status_code == 403


def test_officer_can_confirm_library_pdf_for_ordinary_journal(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    folder = tmp_path / "safety" / "library"
    folder.mkdir(parents=True)
    content = b"%PDF-1.4 approved original"
    digest = hashlib.sha256(content).hexdigest()
    (folder / f"{digest}.pdf").write_bytes(content)
    (folder / "manifest.json").write_text(json.dumps([
        {"id": digest, "title": "ИОП-19-23-Об Инструкция в кабинете физики", "filename": "ИОП-19-23-Об.pdf"}
    ], ensure_ascii=False), encoding="utf-8")
    login(ids["teacher"])
    before = client.get("/safety/journals/").get_data(as_text=True)
    assert "Сформировать журнал для класса" in before
    assert "Перед печатью нужно подтвердить действующую инструкцию" in before
    assert client.get(f"/safety/instructions/library/{digest}/catalog").status_code == 403

    login(ids["officer"])
    assert client.get(f"/safety/instructions/library/{digest}/catalog").status_code == 200
    approved_on = (ids["today"] - timedelta(days=10)).isoformat()
    response = client.post(f"/safety/instructions/library/{digest}/catalog", data={
        "number": "ИОП-19-23-Об", "title": "Инструкция в кабинете физики",
        "category": "Физика", "briefing_kind": "первичный",
        "approval_basis": "Утверждение на первом листе", "summary": "Правила работы в кабинете физики",
        "approved_on": approved_on, "effective_from": approved_on,
    })
    assert response.status_code == 302
    with app.app_context():
        version = SafetyInstructionVersion.query.one()
        assert version.file_sha256 == digest and version.original_filename == "ИОП-19-23-Об.pdf"

    login(ids["teacher"])
    after = client.get("/safety/journals/").get_data(as_text=True)
    assert "Сформировать журнал для класса" in after
    assert "Перед печатью нужно подтвердить действующую инструкцию" not in after
    assert client.post("/safety/journals/new").status_code == 302


def test_admin_can_select_subject_class_students_and_generate_pdf(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    admin_id = make_user("ADMIN")
    login(admin_id)
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"], category="Физика"), content_type="multipart/form-data").status_code == 302
    with app.app_context():
        version_id = SafetyInstructionVersion.query.one().id
    assert "Сформировать журнал для класса" in client.get("/safety/journals/").get_data(as_text=True)
    response = client.post("/safety/journals/new")
    assert response.status_code == 302
    draft_url = response.headers["Location"]
    classes = client.get(f"{draft_url}?grade=5").get_data(as_text=True)
    assert "5А" in classes
    chooser = client.get(f"{draft_url}?grade=5&class_id={ids['class']}&subject=Физика").get_data(as_text=True)
    assert "Физика" in chooser and "ИОТ-1" in chooser
    assert client.post(f"{draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "grade": "5", "subject": "Физика",
        "instruction_version_id": str(version_id), "class_ids": [str(ids["class"])],
    }).status_code == 302
    first, second, _ = ids["children"]
    roster = client.get(draft_url).get_data(as_text=True)
    assert f'value="{first}"' in roster and f'value="{second}"' in roster
    assert client.post(f"{draft_url}/participants/select", data={"child_ids": [str(first)]}).status_code == 302
    with app.app_context():
        draft = SafetyJournalDraft.query.one()
        assert draft.selected_child_ids == [first]
    preview = client.get(f"{draft_url}/preview")
    assert preview.status_code == 200
    digest = re.search(r'name="preview_digest" value="([^"]+)"', preview.get_data(as_text=True)).group(1)
    generated = client.post(f"{draft_url}/generate", data={"preview_digest": digest})
    assert generated.status_code == 302
    with app.app_context():
        page = SafetyJournalPage.query.one()
        assert page.author_id == admin_id and page.instruction_number_snapshot == "ИОТ-1"
        assert [person.child_id for person in page.participants] == [first]


def test_teacher_classes_and_subjects_follow_personal_load(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    login(ids["officer"])
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"], category="Физика"), content_type="multipart/form-data").status_code == 302
    with app.app_context():
        version_id = SafetyInstructionVersion.query.one().id
    login(ids["teacher"])
    draft_url = client.post("/safety/journals/new").headers["Location"]
    classes = client.get(f"{draft_url}?grade=5").get_data(as_text=True)
    assert "5А" in classes and "5Б" not in classes
    subjects = client.get(f"{draft_url}?grade=5&class_id={ids['class']}").get_data(as_text=True)
    assert "Физика" in subjects
    client.post(f"{draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "grade": "5", "subject": "Физика",
        "instruction_version_id": str(version_id), "class_ids": [str(ids["other_class"])],
    })
    with app.app_context():
        assert SafetyJournalDraft.query.one().class_ids == []
    client.post(f"{draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "grade": "5", "subject": "Математика",
        "instruction_version_id": str(version_id), "class_ids": [str(ids["class"])],
    })
    with app.app_context():
        assert SafetyJournalDraft.query.one().class_ids == []


def test_current_workload_matrix_drives_teacher_classes_and_admin_plan_subjects(app, make_user, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    admin_id = make_user("ADMIN")
    other_teacher_id = make_user("TEACHER")
    with app.app_context():
        year = AcademicYear.query.one()
        organization = OrganizationSettings.query.one()
        classroom = db.session.get(SchoolClass, ids["class"])
        teacher = db.session.get(User, ids["teacher"])
        admin = db.session.get(User, admin_id)
        other_teacher = db.session.get(User, other_teacher_id)
        activity = EducationActivity(organization_id=organization.id, code="PHYSICS", name="Физика", activity_kind="SUBJECT")
        cycle = TariffCycle(organization_id=organization.id, academic_year_id=year.id, code="TEST", name="Тестовая нагрузка")
        version = TariffVersion(tariff_cycle=cycle, version_no=1, status="DRAFT")
        plan = EducationPlan(tariff_version=version, plan_kind="CURRICULUM", name="План 5 класса", scope_code="ALL")
        line = EducationPlanLine(education_plan=plan, education_activity=activity, component_kind="MANDATORY", weekly_hours=2)
        snapshot = PopulationSnapshot(tariff_version=version, revision_no=1, snapshot_date=ids["today"], checksum="test")
        snapshot_class = PopulationSnapshotClass(population_snapshot=snapshot, source_school_class=classroom, name_snapshot="5А", grade_snapshot=5, student_count=2)
        group = TeachingGroup(tariff_version=version, education_activity=activity, group_type="CLASS", code="5A-PHYSICS", name="Физика 5А", valid_from=ids["today"] - timedelta(days=1), valid_to=ids["today"] + timedelta(days=1), source_plan_line=line, status="READY")
        link = TeachingGroupClass(teaching_group=group, population_snapshot_class=snapshot_class)
        need = WorkloadNeed(tariff_version=version, teaching_group=group, education_activity=activity, date_from=group.valid_from, date_to=group.valid_to, weekly_hours=2, annual_hours=70)
        assignment = WorkloadAssignment(tariff_version=version, workload_need=need, employee_user_id=teacher.id, assignment_kind="MAIN", date_from=group.valid_from, date_to=group.valid_to, weekly_hours=2, annual_hours=70, status="DRAFT")
        db.session.add_all([activity, cycle, version, plan, line, snapshot, snapshot_class, group, link, need, assignment])
        db.session.commit()
        teacher_classes = journal_classes_for_user(ids["today"], teacher)
        assert [item.id for item in teacher_classes] == [classroom.id]
        assert journal_subjects_for_class(ids["today"], teacher, classroom) == ["Физика"]
        assert journal_subjects_for_class(ids["today"], admin, classroom) == ["Физика"]
        assert journal_classes_for_user(ids["today"], other_teacher) == []


def test_library_pdf_is_suggested_and_can_return_to_journal_after_confirmation(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    admin_id = make_user("ADMIN")
    with app.app_context():
        year = AcademicYear.query.one()
        db.session.add(TeacherLoad(teacher_id=ids["teacher"], academic_year_id=year.id, class_name="5А", grade=5, subject_name="Информатика", hours=2))
        db.session.commit()
    folder = tmp_path / "safety" / "library"
    folder.mkdir(parents=True)
    titles = [
        "ИОП-04-23-Об Вводный инструктаж в кабинете информатики",
        "ИОП-31-23-Об Инструкция по ОТ в кабинете информатики",
        "ИОП-32-23-Об Инструкция по ОТ при выполнении практических работ в кабинете информатики",
        "ИОП-07-23-Об Инструкция по ОТ в кабинете химии",
    ]
    items = []
    for number, title in enumerate(titles):
        content = f"%PDF-1.4 example {number}".encode()
        digest = hashlib.sha256(content).hexdigest()
        (folder / f"{digest}.pdf").write_bytes(content)
        items.append({"id": digest, "title": title, "filename": f"{number}.pdf"})
    (folder / "manifest.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    login(admin_id)
    draft_url = client.post("/safety/journals/new").headers["Location"]
    form_url = f"{draft_url}?grade=5&class_id={ids['class']}&subject=Информатика"
    chooser = client.get(form_url).get_data(as_text=True)
    assert "ИОП-04-23-Об" in chooser and "ИОП-31-23-Об" in chooser and "ИОП-32-23-Об" in chooser
    assert "ИОП-07-23-Об" not in chooser
    assert "Подтвердить для журнала" in chooser
    assert client.get(f"/safety/instructions/library/{items[1]['id']}/catalog?subject=Информатика&draft_id={draft_url.rsplit('/', 1)[-1]}&grade=5&class_id={ids['class']}&instructed_on={ids['today'].isoformat()}").get_data(as_text=True).count('value="Информатика"') >= 1
    response = client.post(f"/safety/instructions/library/{items[1]['id']}/catalog", data={
        "csrf_token": "", "draft_id": draft_url.rsplit("/", 1)[-1], "grade": "5",
        "class_id": str(ids["class"]), "instructed_on": ids["today"].isoformat(),
        "number": "ИОП-31-23-Об", "title": "Инструкция по ОТ в кабинете информатики",
        "category": "Информатика", "briefing_kind": "первичный",
        "approval_basis": "Приказ № 1", "summary": "Правила работы в кабинете",
        "approved_on": (ids["today"] - timedelta(days=5)).isoformat(),
        "effective_from": (ids["today"] - timedelta(days=5)).isoformat(),
    })
    assert response.status_code == 302 and response.headers["Location"].startswith(draft_url)
    chooser = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "ИОП-31-23-Об" in chooser and "Показать список класса" in chooser


def test_catalog_rights_versions_and_immutable_original(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    login(ids["teacher"])
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"]), content_type="multipart/form-data").status_code == 403
    login(ids["officer"])
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"]), content_type="multipart/form-data").status_code == 302
    registry = client.get("/safety/instructions/?q=ИОТ-1").get_data(as_text=True)
    assert "registry-matrix" in registry and "ИОТ-1" in registry
    detail = client.get("/safety/instructions/1").get_data(as_text=True)
    assert "Добавить новую версию" in detail and "registry-matrix" in detail
    assert 'id="safety-pdf-preview-modal"' in detail
    with app.app_context():
        version = SafetyInstructionVersion.query.one()
        old_id, old_hash, old_file = version.id, version.file_sha256, version.stored_filename
    assert client.get(f"/safety/instructions/versions/{old_id}/original").data.startswith(b"%PDF")
    inline = client.get(f"/safety/instructions/versions/{old_id}/original?inline=1")
    assert inline.status_code == 200 and inline.headers["Content-Disposition"].startswith("inline")
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
        assert [event.action for event in SafetyInstructionAccessEvent.query.order_by(SafetyInstructionAccessEvent.id)] == ["created", "download", "preview", "new_version"]
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
        assert "ознакомлен" not in text
        assert "дата инструктажа " not in text.lower()
        assert ids["today"].strftime("%d.%m.%Y") not in text
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
