"""Stage 2 acceptance paths: access, roster edits, frozen PDF, and age rules."""

from datetime import date, datetime, timedelta
from io import BytesIO
import hashlib
import json
import re
from html import unescape
from types import SimpleNamespace

import pdfplumber
from reportlab.pdfgen import canvas

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
    assert "Инструкции доступны из каталога и перечня PDF" in before
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
    assert "Инструкции доступны из каталога и перечня PDF" in after
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
    form = client.get(draft_url).get_data(as_text=True)
    assert 'id="journal-compose"' in form and 'id="journal-instruction-preview"' in form
    assert 'id="journal-preview"' not in form and 'id="journal-submit"' in form
    assert 'name="briefing_at"' in form and 'type="datetime-local"' in form
    choices = client.get(f"/safety/journals/choices?grade=5&class_id={ids['class']}&subject=Физика").json
    assert any(item["name"] == "5А" for item in choices["classes"])
    assert "Физика" in choices["subjects"] and choices["instructions"][0]["label"].startswith("ИОТ-1")
    assert client.post(f"{draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "briefing_at": f'{ids["today"].isoformat()}T10:30', "grade": "5", "subject": "Физика",
        "instruction_version_id": str(version_id), "class_ids": [str(ids["class"])],
    }).status_code == 302
    first, second, _ = ids["children"]
    roster = client.get(f"/safety/journals/choices?grade=5&class_id={ids['class']}&subject=Физика").json["roster"]
    assert {item["id"] for item in roster} == {first, second}
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
        assert page.briefing_at.hour == 7 and page.briefing_at.minute == 30
        assert [person.child_id for person in page.participants] == [first]
        page.briefing_at = None  # Existing pages had no teacher-entered time.
        db.session.commit()
    old_registry = client.get("/safety/journals/").get_data(as_text=True)
    assert '<td class="registry-cell-nowrap">—</td>' in old_registry


def test_one_form_creates_and_corrects_journal_with_pdf_history(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    admin_id = make_user("ADMIN")
    login(admin_id)
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"], category="Физика"), content_type="multipart/form-data").status_code == 302
    with app.app_context():
        version_id = SafetyInstructionVersion.query.one().id
    draft_url = client.post("/safety/journals/new").headers["Location"]
    first, second, _ = ids["children"]
    missing_time = client.post(f"{draft_url}/compose", data={
        "grade": "5", "class_id": str(ids["class"]), "subject": "Физика",
        "instruction_version_id": str(version_id), "briefing_kind": "повторный",
        "child_ids": [str(first)],
    })
    assert missing_time.status_code == 302 and "drafts" in missing_time.headers["Location"]
    with app.app_context():
        assert SafetyJournalPage.query.count() == 0
    created = client.post(f"{draft_url}/compose", data={
        "grade": "5", "class_id": str(ids["class"]), "subject": "Физика",
        "instruction_version_id": str(version_id), "briefing_kind": "повторный", "briefing_at": f'{ids["today"].isoformat()}T10:30',
        "header_note": "Перед лабораторной работой", "child_ids": [str(first)],
    })
    assert created.status_code == 302 and "preview=1" in created.headers["Location"]
    with app.app_context():
        page = SafetyJournalPage.query.one()
        page_id = page.id
        old_revision = page.revisions[0]
        old_pdf = (tmp_path / "safety" / "journal_pages" / old_revision.stored_filename).read_bytes()
        assert page.briefing_kind_snapshot == "повторный" and page.header_note_snapshot == "Перед лабораторной работой"
        assert page.briefing_at.hour == 7 and page.briefing_at.minute == 30
        assert [person.child_id for person in page.participants] == [first]
        with pdfplumber.open(BytesIO(old_pdf)) as document:
            text = document.pages[0].extract_text()
            for prefix in ("Вид инструктажа:", "Проводивший инструктаж:"):
                line = next(item for item in document.pages[0].extract_text_lines() if item["text"].startswith(prefix))
                assert abs((line["x0"] + line["x1"]) / 2 - document.pages[0].width / 2) < 8
        assert "Вид инструктажа: повторный" in text
        assert "Инструкция: ИОТ-1 — Безопасность на уроке" in text
        assert "(версия 1)" not in text
        assert date(ids["today"].year - 14, ids["today"].month, ids["today"].day).strftime("%d.%m.%Y") in text
        assert "Перед лабораторной работой" in text
        assert "Проводивший инструктаж: Тестов Пользователь" in text
    detail = client.get(created.headers["Location"]).get_data(as_text=True)
    assert 'id="safety-pdf-preview-modal"' in detail and "Исправить данные журнала" in detail
    assert f'{ids["today"].strftime("%d.%m.%Y")} 10:30' in detail
    registry = client.get("/safety/journals/").get_data(as_text=True)
    assert 'id="safety-pdf-preview-modal"' in registry
    assert "Создан" in registry and "Инструктаж проведён" in registry
    assert f'{ids["today"].strftime("%d.%m.%Y")} 10:30' in registry
    assert f'aria-label="Просмотреть журнал ОТ-{ids["today"].year}-{page_id:06d}"' in registry
    assert 'aria-label="Просмотреть инструкцию ИОТ-1"' in registry
    assert f'data-pdf-url="/safety/instructions/versions/{version_id}/original?inline=1"' in registry
    journal_pdf_url = unescape(re.search(r'data-pdf-url="([^"]+/pdf\?token=[^"]+)"', registry).group(1))
    assert client.get(journal_pdf_url).data.startswith(b"%PDF")
    correction = client.post(f"/safety/journals/pages/{page_id}/correct")
    assert correction.status_code == 302
    corrected = client.post(f"{correction.headers['Location']}/compose", data={
        "grade": "5", "class_id": str(ids["class"]), "subject": "Физика",
        "instruction_version_id": str(version_id), "briefing_kind": "внеплановый", "briefing_at": f'{ids["today"].isoformat()}T11:15',
        "header_note": "Исправленная тема", "child_ids": [str(second)],
    })
    assert corrected.status_code == 302 and "preview=1" in corrected.headers["Location"]
    with app.app_context():
        page = db.session.get(SafetyJournalPage, page_id)
        assert page.briefing_kind_snapshot == "внеплановый"
        assert page.briefing_at.hour == 8 and page.briefing_at.minute == 15
        assert page.header_note_snapshot == "Исправленная тема"
        assert [person.child_id for person in page.participants] == [second]
        assert len(page.revisions) == 2
        assert (tmp_path / "safety" / "journal_pages" / page.revisions[0].stored_filename).read_bytes() == old_pdf


def test_teacher_classes_and_subjects_follow_personal_load(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    login(ids["officer"])
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"], category="Физика"), content_type="multipart/form-data").status_code == 302
    with app.app_context():
        version_id = SafetyInstructionVersion.query.one().id
    login(ids["teacher"])
    draft_url = client.post("/safety/journals/new").headers["Location"]
    choices = client.get(f"/safety/journals/choices?grade=5&class_id={ids['class']}").json
    assert [item["name"] for item in choices["classes"]] == ["5А"]
    assert "Физика" in choices["subjects"]
    client.post(f"{draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "briefing_at": f'{ids["today"].isoformat()}T10:30', "grade": "5", "subject": "Физика",
        "instruction_version_id": str(version_id), "class_ids": [str(ids["other_class"])],
    })
    with app.app_context():
        assert SafetyJournalDraft.query.one().class_ids == []
    client.post(f"{draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "briefing_at": f'{ids["today"].isoformat()}T10:30', "grade": "5", "subject": "Математика",
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


def test_library_pdf_can_be_selected_previewed_and_generated_without_catalog_confirmation(app, client, make_user, login, tmp_path):
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
        stream = BytesIO()
        document = canvas.Canvas(stream)
        document.drawString(72, 720, f"Instruction {number}")
        document.save()
        content = stream.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        (folder / f"{digest}.pdf").write_bytes(content)
        items.append({"id": digest, "title": title, "filename": f"{number}.pdf"})
    (folder / "manifest.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    login(admin_id)
    chooser = client.get(f"/safety/journals/choices?grade=5&class_id={ids['class']}&subject=Информатика").json
    labels = [item["label"] for item in chooser["instructions"]]
    assert any("ИОП-04-23-Об" in item for item in labels)
    assert any("ИОП-31-23-Об" in item for item in labels)
    assert any("ИОП-32-23-Об" in item for item in labels)
    assert not any("ИОП-07-23-Об" in item for item in labels)
    assert all(item["source"] == "library" for item in chooser["instructions"])

    login(ids["teacher"])
    draft_url = client.post("/safety/journals/new").headers["Location"]
    choice = f"library:{items[1]['id']}"
    data = {"grade": "5", "class_id": str(ids["class"]), "subject": "Информатика",
            "instruction_choice": choice, "briefing_kind": "первичный", "briefing_at": f'{ids["today"].isoformat()}T10:30',
            "child_ids": [str(ids["children"][0])], "header_note": "Практическая работа"}
    editor = client.get(draft_url).get_data(as_text=True)
    assert 'id="journal-preview"' not in editor and 'id="journal-submit"' in editor
    assert client.post(f"{draft_url}/compose/preview", data=data).status_code == 404
    invalid = client.post(f"{draft_url}/compose", data={**data, "instruction_choice": f"library:{items[3]['id']}"})
    assert invalid.status_code == 302
    with app.app_context():
        assert SafetyJournalPage.query.count() == 0
        assert SafetyInstructionVersion.query.count() == 0
    created = client.post(f"{draft_url}/compose", data=data)
    assert created.status_code == 302 and "preview=1" in created.headers["Location"]
    with app.app_context():
        page = SafetyJournalPage.query.one()
        page_id = page.id
        assert page.library_item_id == items[1]["id"] and page.instruction_version_id is None
        assert page.subject_snapshot == "Информатика" and page.instruction_number_snapshot == "ИОП-31-23-Об"
        assert page.instruction_file_sha256_snapshot == items[1]["id"]
        assert SafetyInstructionVersion.query.count() == 0
    detail = client.get(created.headers["Location"]).get_data(as_text=True)
    assert "PDF из перечня" in detail and "Практическая работа" in detail
    pdf_link = unescape(re.search(r'data-pdf-url="([^" ]+/pdf\?token=[^"]+)"', detail).group(1))
    with pdfplumber.open(BytesIO(client.get(pdf_link).data)) as document:
        pdf_text = document.pages[0].extract_text()
        assert date(ids["today"].year - 14, ids["today"].month, ids["today"].day).strftime("%d.%m.%Y") in pdf_text
        assert "Инструкция: ИОП-31-23-Об — Инструкция по ОТ в кабинете информатики" in pdf_text
        assert f"ОТ-{ids['today'].year}-{page_id:06d}" in pdf_text
        assert "ПРЕДПРОСМОТР" not in pdf_text
    registry = client.get("/safety/journals/").get_data(as_text=True)
    assert 'aria-label="Просмотреть инструкцию ИОП-31-23-Об"' in registry
    assert f'data-pdf-url="/safety/instructions/library/{items[1]["id"]}/pdf"' in registry
    correction = client.post(f"/safety/journals/pages/{page_id}/correct")
    assert correction.status_code == 302
    corrected = client.post(f"{correction.headers['Location']}/compose", data={
        **data, "instruction_choice": f"library:{items[2]['id']}", "header_note": "Уточнённая работа",
        "child_ids": [str(ids["children"][0]), str(ids["children"][1])],
    })
    assert corrected.status_code == 302
    with app.app_context():
        page = db.session.get(SafetyJournalPage, page_id)
        assert page.library_item_id == items[2]["id"] and len(page.revisions) == 2
        assert {item.child_id for item in page.participants} == set(ids["children"][:2])


def test_catalog_rights_versions_and_immutable_original(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    login(ids["teacher"])
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"]), content_type="multipart/form-data").status_code == 403
    login(ids["officer"])
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"]), content_type="multipart/form-data").status_code == 302
    registry = client.get("/safety/instructions/?q=ИОТ-1").get_data(as_text=True)
    assert "registry-matrix" in registry and "ИОТ-1" in registry
    assert 'aria-label="Просмотреть PDF ИОТ-1"' in registry
    assert 'data-bs-target="#safety-pdf-preview-modal"' in registry
    assert 'id="safety-pdf-preview-modal"' in registry
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
        "instructed_on": ids["today"].isoformat(), "briefing_at": f'{ids["today"].isoformat()}T10:30', "grade": "5",
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
    page_url = generated.headers["Location"].split("?", 1)[0]
    detail = client.get(page_url)
    assert detail.status_code == 200
    pdf_link = unescape(re.search(r'data-pdf-url="([^"]+/pdf\?token=[^"]+)"', detail.get_data(as_text=True)).group(1))
    pdf = client.get(pdf_link)
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    with pdfplumber.open(BytesIO(pdf.data)) as document:
        text = "\n".join(page.extract_text() or "" for page in document.pages)
        assert "ознакомлен" not in text
        assert "дата инструктажа " not in text.lower()
        assert ids["today"].strftime("%d.%m.%Y") not in text
        assert date(ids["today"].year - 14, ids["today"].month, ids["today"].day).strftime("%d.%m.%Y") in text
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
        page.instruction_version = version
        people = [SimpleNamespace(sequence=n, full_name_snapshot=f"Ученик {n}", birth_date_snapshot=date(2012, 1, 2), class_name_snapshot="5А", signature_rule="handwritten") for n in range(1, 81)]
        content = build_journal_pdf(page, people)
    with pdfplumber.open(BytesIO(content)) as document:
        assert len(document.pages) > 1
        for sheet in document.pages:
            text = sheet.extract_text() or ""
            footer_text = sheet.crop((0, sheet.height - 28, sheet.width, sheet.height)).extract_text() or ""
            assert footer_text.strip() == "Лист №"
            assert "Страница журнала №" not in text
            assert "Дата рождения" in text
            assert "02.01.2012" in text
            assert "Подпись" in text
            assert "Иванов Иван Иванович" in text
            printable_margin = 11 * 72 / 25.4
            assert min(char["x0"] for char in sheet.chars) >= printable_margin
            assert max(char["x1"] for char in sheet.chars) <= sheet.width - printable_margin
            assert min(line["x0"] for line in sheet.lines) >= printable_margin
            assert max(line["x1"] for line in sheet.lines) <= sheet.width - printable_margin


def test_teacher_creates_and_corrects_trip_without_order(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    login(ids["viewer"])
    assert client.post("/safety/journals/trips/new").status_code == 403
    login(ids["officer"])
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"]), content_type="multipart/form-data").status_code == 302
    with app.app_context():
        version_id = SafetyInstructionVersion.query.one().id
    login(ids["teacher"])
    registry = client.get("/safety/journals/trips")
    assert registry.status_code == 200 and "Приказ не обязателен" in registry.get_data(as_text=True)
    assert client.get("/safety/trips/").headers["Location"].endswith("/safety/journals/trips")
    response = client.post("/safety/journals/trips/new")
    assert response.status_code == 302
    draft_url = response.headers["Location"]
    editor = client.get(draft_url).get_data(as_text=True)
    assert "Номер приказа" in editor and 'name="order_number"' in editor
    assert 'id="trip-preview"' not in editor and 'id="trip-submit"' in editor
    choices = client.get(f"/safety/journals/trips/choices?grade=5&class_id={ids['class']}").get_json()
    assert {item["id"] for item in choices["classes"]} == {ids["class"], ids["other_class"]}
    assert f"version:{version_id}" in {item["id"] for item in choices["instructions"]}
    data = {
        "trip_kind": "Экскурсия", "destination": "Музей науки",
        "trip_date": (ids["today"] + timedelta(days=1)).isoformat(), "order_number": "",
        "briefing_kind": "целевой", "briefing_at": f'{ids["today"].isoformat()}T10:30', "instruction_choice": f"version:{version_id}",
        "child_ids": [str(ids["children"][0]), str(ids["children"][2])],
    }
    assert client.post(f"{draft_url}/compose/preview", data=data).status_code == 404
    generated = client.post(f"{draft_url}/compose", data=data)
    assert generated.status_code == 302
    with app.app_context():
        page = SafetyJournalPage.query.one()
        page_id = page.id
        assert page.kind == "trip" and page.trip_order_id is None and page.trip_assignment_id is None
        assert page.trip_snapshot == {"trip_kind": "Экскурсия", "destination": "Музей науки",
                                      "trip_date": data["trip_date"], "order_number": ""}
        assert {item.class_name_snapshot for item in page.participants} == {"5А", "5Б"}
    detail = client.get(generated.headers["Location"]).get_data(as_text=True)
    assert "Исправить данные журнала" in detail and "Музей науки" in detail
    assert "Карточка выезда" not in detail
    pdf_link = unescape(re.search(r'data-pdf-url="([^" ]+/pdf\?token=[^"]+)"', detail).group(1))
    with pdfplumber.open(BytesIO(client.get(pdf_link).data)) as document:
        pdf_text = document.pages[0].extract_text()
        assert "Музей науки" in pdf_text and "Приказ №" not in pdf_text
        assert date(ids["today"].year - 14, ids["today"].month, ids["today"].day).strftime("%d.%m.%Y") in pdf_text
        assert f"ОТ-В-{ids['today'].year}-{page_id:06d}" in pdf_text
        assert "ПРЕДПРОСМОТР" not in pdf_text
    trip_registry = client.get("/safety/journals/trips").get_data(as_text=True)
    assert 'aria-label="Просмотреть инструкцию ИОТ-1"' in trip_registry
    assert f'aria-label="Просмотреть журнал ОТ-В-{ids["today"].year}-{page_id:06d}"' in trip_registry
    correction = client.post(f"/safety/journals/pages/{page_id}/correct")
    assert correction.status_code == 302
    corrected = client.post(f"{correction.headers['Location']}/compose", data={
        **data, "order_number": "42", "child_ids": [str(ids["children"][0])],
    })
    assert corrected.status_code == 302
    with app.app_context():
        page = db.session.get(SafetyJournalPage, page_id)
        assert page.trip_snapshot["order_number"] == "42"
        assert len(page.revisions) == 2
        assert [item.child_id for item in page.participants] == [ids["children"][0]]


def test_trip_can_use_reference_pdf_without_subject_or_order(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    content = b"%PDF-1.4 trip reference"
    digest = hashlib.sha256(content).hexdigest()
    folder = tmp_path / "safety" / "library"
    folder.mkdir(parents=True)
    (folder / f"{digest}.pdf").write_bytes(content)
    (folder / "manifest.json").write_text(json.dumps([
        {"id": digest, "title": "ИОТ-ВЫЕЗД Правила поведения в транспорте", "filename": "transport.pdf"}
    ], ensure_ascii=False), encoding="utf-8")
    login(ids["teacher"])
    draft_url = client.post("/safety/journals/trips/new").headers["Location"]
    choices = client.get("/safety/journals/trips/choices").get_json()
    assert f"library:{digest}" in {item["id"] for item in choices["instructions"]}
    data = {
        "trip_kind": "Экскурсия", "destination": "Театр", "trip_date": ids["today"].isoformat(),
        "briefing_kind": "целевой", "briefing_at": f'{ids["today"].isoformat()}T10:30', "instruction_choice": f"library:{digest}",
        "child_ids": [str(ids["children"][0])],
    }
    assert client.post(f"{draft_url}/compose/preview", data=data).status_code == 404
    assert client.post(f"{draft_url}/compose", data=data).status_code == 302
    with app.app_context():
        page = SafetyJournalPage.query.one()
        assert page.kind == "trip" and page.library_item_id == digest
        assert page.instruction_version_id is None and page.trip_snapshot["order_number"] == ""


def test_class_teacher_journal_uses_own_instructions_without_subject(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    class_teacher_id = make_user("CLASS_TEACHER")
    with app.app_context():
        db.session.get(SchoolClass, ids["class"]).teacher_user_id = class_teacher_id
        db.session.commit()
    folder = tmp_path / "safety" / "library"
    folder.mkdir(parents=True)
    items = []
    for number, section in (("ИОТ-01-2023", "class_teacher"), ("ИОП-99", "ordinary")):
        stream = BytesIO()
        document = canvas.Canvas(stream)
        document.drawString(72, 720, number)
        document.save()
        content = stream.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        (folder / f"{digest}.pdf").write_bytes(content)
        items.append({"id": digest, "title": f"{number} Правила безопасности", "filename": f"{number}.pdf", "section": section})
    (folder / "manifest.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    with app.app_context():
        from app.modules.safety_instructions.routes import library_suggestions
        assert [item["id"] for item in library_suggestions("Правила безопасности")] == [items[1]["id"]]

    login(class_teacher_id)
    library = client.get("/safety/instructions/library?section=class_teacher").get_data(as_text=True)
    assert "ИОТ-01-2023" in library and "ИОП-99" not in library
    assert "Сформировать журнал классного руководства" in client.get("/safety/journals/").get_data(as_text=True)
    draft_url = client.post("/safety/journals/new", data={"journal_kind": "class_teacher"}).headers["Location"]
    editor = client.get(draft_url).get_data(as_text=True)
    assert 'data-journal-kind="class_teacher"' in editor and 'name="subject"' not in editor
    choices = client.get(f"/safety/journals/choices?journal_kind=class_teacher&grade=5&class_id={ids['class']}").json
    assert [item["id"] for item in choices["classes"]] == [ids["class"]]
    assert choices["subjects"] == []
    assert [item["id"] for item in choices["instructions"]] == [f"library:{items[0]['id']}"]
    data = {"grade": "5", "class_id": str(ids["class"]), "instruction_choice": f"library:{items[1]['id']}",
            "briefing_kind": "целевой", "briefing_at": f'{ids["today"].isoformat()}T10:30',
            "child_ids": [str(ids["children"][0])]}
    assert client.post(f"{draft_url}/compose", data=data).status_code == 302
    with app.app_context():
        assert SafetyJournalPage.query.count() == 0
    data["instruction_choice"] = f"library:{items[0]['id']}"
    created = client.post(f"{draft_url}/compose", data=data)
    assert created.status_code == 302 and "preview=1" in created.headers["Location"]
    with app.app_context():
        page = SafetyJournalPage.query.one()
        assert page.kind == "class_teacher" and page.subject_snapshot == "Классное руководство"
        assert page.number.startswith("ОТ-КР-") and page.author_id == class_teacher_id
        page_id = page.id
    detail = client.get(created.headers["Location"]).get_data(as_text=True)
    pdf_link = unescape(re.search(r'data-pdf-url="([^" ]+/pdf\?token=[^"]+)"', detail).group(1))
    with pdfplumber.open(BytesIO(client.get(pdf_link).data)) as document:
        text = document.pages[0].extract_text()
        assert "Направление: Классное руководство" in text
        assert "ИОТ-01-2023" in text and "ПРЕДПРОСМОТР" not in text
    correction = client.post(f"/safety/journals/pages/{page_id}/correct")
    assert correction.status_code == 302
    data["child_ids"] = [str(ids["children"][1])]
    assert client.post(f"{correction.headers['Location']}/compose", data=data).status_code == 302
    with app.app_context():
        page = db.session.get(SafetyJournalPage, page_id)
        assert len(page.revisions) == 2
        assert [person.child_id for person in page.participants] == [ids["children"][1]]

    login(ids["teacher"])
    teacher_choices = client.get(f"/safety/journals/choices?journal_kind=class_teacher&grade=5&class_id={ids['class']}").json
    assert f"library:{items[0]['id']}" in {item["id"] for item in teacher_choices["instructions"]}
