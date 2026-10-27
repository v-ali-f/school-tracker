"""Stage 3 acceptance paths: excursion orders, tasks and journal snapshots."""

import re
from datetime import date, datetime, timedelta
from html import unescape
from io import BytesIO

import pdfplumber

from app.core.extensions import db
from app.models import (
    AcademicYear, Child, ChildEnrollment, OrganizationSettings, SafetyInstructionVersion,
    SafetyJournalDraft, SafetyJournalPage, SafetyTripAssignment, SafetyTripOrder,
    SchoolClass, SchoolOrder, Task, TaskNotification,
)
from app.services.safety_passport_service import school_today
from app.services.safety_trip_service import trip_status


def _seed(app, make_user, tmp_path):
    director = make_user("DIRECTOR")
    teacher = make_user("TEACHER")
    second = make_user("TEACHER")
    outsider = make_user("TEACHER")
    secretary = make_user("VIEWER")
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    with app.app_context():
        today = school_today()
        year = AcademicYear(name=f"{today.year - 1}/{today.year + 1}", start_date=today - timedelta(days=300), end_date=today + timedelta(days=300), is_current=True)
        db.session.add(year)
        db.session.flush()
        classroom = SchoolClass(academic_year_id=year.id, name="5А", grade=5)
        db.session.add(classroom)
        db.session.flush()
        child = Child(last_name="Александров", first_name="Илья", birth_date=date(today.year - 13, today.month, today.day))
        db.session.add(child)
        db.session.flush()
        db.session.add(ChildEnrollment(child_id=child.id, academic_year_id=year.id, school_class_id=classroom.id, enrolled_at=datetime.combine(today - timedelta(days=100), datetime.min.time())))
        db.session.add(OrganizationSettings(full_name="ГБОУ Школа Тест", is_active=True))
        db.session.commit()
        return {"director": director, "teacher": teacher, "second": second, "outsider": outsider, "secretary": secretary, "class": classroom.id, "child": child.id, "today": today}


def _order_form(ids, **extra):
    data = {
        "number": "42", "title": "Учебная экскурсия", "section": "excursions",
        "order_date": ids["today"].isoformat(),
        "trip_date": (ids["today"] + timedelta(days=2)).isoformat(),
        "trip_destination": "Музей науки", "trip_kind": "Экскурсия",
        "responsible_user_ids": [str(ids["teacher"])],
        "trip_revision": "1",
    }
    data.update(extra)
    return data


def _create_instruction(app, director_id, today):
    from app.models import SafetyInstruction, SafetyInstructionVersion
    with app.app_context():
        instruction = SafetyInstruction(number="ИОТ-В", title="Безопасность на экскурсии", category="Выезды", briefing_kind="целевой", event_kind="экскурсия", created_by_id=director_id)
        db.session.add(instruction)
        db.session.flush()
        version = SafetyInstructionVersion(
            instruction_id=instruction.id, version_number=1, title_snapshot=instruction.title,
            approved_on=today - timedelta(days=1), effective_from=today - timedelta(days=1),
            status="active", approval_basis="Приказ № 1", summary="Безопасное поведение в поездке",
            original_filename="instruction.pdf", stored_filename="stage3-test.pdf",
            file_sha256="a" * 64, file_mime_type="application/pdf", created_by_id=director_id,
        )
        db.session.add(version)
        db.session.commit()
        return version.id


def test_excursion_order_creates_task_and_private_journal(app, client, make_user, login, tmp_path):
    ids = _seed(app, make_user, tmp_path)
    version_id = _create_instruction(app, ids["director"], ids["today"])
    login(ids["director"])
    assert client.post("/orders/new", data=_order_form(ids)).status_code == 302
    with app.app_context():
        trip = SafetyTripOrder.query.one()
        order_id = trip.order_id
        assignment = SafetyTripAssignment.query.one()
        task_id = assignment.task_id
        assert trip_status(trip) == "waiting"
        assert Task.query.count() == 1
        assert TaskNotification.query.filter_by(task_id=task_id, user_id=ids["teacher"]).count() == 1
    login(ids["outsider"])
    assert client.get(f"/safety/trips/orders/{order_id}").status_code == 403
    login(ids["teacher"])
    assert client.get(f"/tasks/{task_id}").status_code == 200
    assert "Открыть журнал выезда" in client.get(f"/tasks/{task_id}").get_data(as_text=True)
    assert client.get(f"/safety/trips/orders/{order_id}").status_code == 200
    response = client.post(f"/safety/trips/orders/{order_id}/drafts")
    assert response.status_code == 302
    draft_url = response.headers["Location"]
    assert client.get(draft_url).status_code == 200
    assert client.post(f"{draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "grade": "5",
        "instruction_version_id": str(version_id), "class_ids": [str(ids["class"])],
    }).status_code == 302
    preview = client.get(f"{draft_url}/preview")
    assert preview.status_code == 200
    digest = re.search(r'name="preview_digest" value="([^"]+)"', preview.get_data(as_text=True)).group(1)
    created = client.post(f"{draft_url}/generate", data={"preview_digest": digest})
    assert created.status_code == 302
    page_url = created.headers["Location"].split("?", 1)[0]
    detail = client.get(page_url)
    assert detail.status_code == 200
    pdf_link = unescape(re.search(r'data-pdf-url="([^"]+/pdf\?token=[^"]+)"', detail.get_data(as_text=True)).group(1))
    pdf = client.get(pdf_link)
    assert pdf.status_code == 200
    with pdfplumber.open(BytesIO(pdf.data)) as document:
        text = "\n".join(sheet.extract_text() or "" for sheet in document.pages)
        assert "Музей науки" in text and "Приказ № 42" in text
        assert "Дата рождения" in text and "ознакомлен" not in text
        assert ids["today"].strftime("%d.%m.%Y") not in text
        assert (ids["today"] + timedelta(days=2)).strftime("%d.%m.%Y") not in text
        assert date(ids["today"].year - 13, ids["today"].month, ids["today"].day).strftime("%d.%m.%Y") not in text
    with app.app_context():
        page = SafetyJournalPage.query.one()
        assert page.kind == "trip" and page.trip_snapshot["order_number"] == "42"
        assert trip_status(SafetyTripOrder.query.one()) == "generated"
        assert db.session.get(Task, task_id).status != Task.STATUS_DONE
        old_hash = page.revisions[0].pdf_sha256
    assert client.post(page_url + "/printed").status_code == 302
    with app.app_context():
        assert trip_status(SafetyTripOrder.query.one()) == "printed"
        assert db.session.get(Task, task_id).status == Task.STATUS_DONE
    assert client.post(page_url + "/pdf/reissue").status_code == 302
    with app.app_context():
        page = SafetyJournalPage.query.one()
        assert page.status == "generated" and len(page.revisions) == 2
        assert trip_status(SafetyTripOrder.query.one()) == "generated"
        assert db.session.get(Task, task_id).status != Task.STATUS_DONE
    assert client.post(page_url + "/printed").status_code == 302
    login(ids["director"])
    assert client.post(f"/orders/{order_id}/edit", data=_order_form(ids, trip_destination="Новый музей")).status_code == 302
    with app.app_context():
        trip = SafetyTripOrder.query.one()
        assert trip.revision_number == 2 and trip_status(trip) == "requires_update"
        assert db.session.get(Task, task_id).status == Task.STATUS_REWORK
        old_page = SafetyJournalPage.query.one()
        assert old_page.trip_snapshot["destination"] == "Музей науки"
        assert old_page.revisions[0].pdf_sha256 == old_hash
    stale_edit = client.post(f"/orders/{order_id}/edit", data=_order_form(ids, trip_destination="Ошибочная параллельная правка", trip_revision="1"))
    assert stale_edit.status_code == 302
    with app.app_context():
        assert SafetyTripOrder.query.one().destination == "Новый музей"
    login(ids["teacher"])
    new_draft = client.post(f"/safety/trips/orders/{order_id}/drafts")
    assert new_draft.status_code == 302
    new_draft_url = new_draft.headers["Location"]
    with app.app_context():
        assert SafetyJournalDraft.query.count() == 2
        assert SafetyJournalDraft.query.order_by(SafetyJournalDraft.created_at.desc()).first().trip_order_revision == 2
    assert client.post(f"{new_draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "grade": "5",
        "instruction_version_id": str(version_id), "class_ids": [str(ids["class"])],
    }).status_code == 302
    new_preview = client.get(f"{new_draft_url}/preview")
    new_digest = re.search(r'name="preview_digest" value="([^"]+)"', new_preview.get_data(as_text=True)).group(1)
    new_page_response = client.post(f"{new_draft_url}/generate", data={"preview_digest": new_digest})
    assert new_page_response.status_code == 302
    new_page_url = new_page_response.headers["Location"].split("?", 1)[0]
    assert client.post(new_page_url + "/printed").status_code == 302
    with app.app_context():
        pages = SafetyJournalPage.query.order_by(SafetyJournalPage.id).all()
        assert len(pages) == 2
        assert pages[0].trip_snapshot["destination"] == "Музей науки"
        assert pages[0].revisions[0].pdf_sha256 == old_hash
        assert pages[1].trip_snapshot["destination"] == "Новый музей"
        assert trip_status(SafetyTripOrder.query.one()) == "printed"
        assert db.session.get(Task, task_id).status == Task.STATUS_DONE
    login(ids["director"])
    assert client.post(f"/orders/{order_id}/delete").status_code == 302
    with app.app_context():
        assert db.session.get(SchoolOrder, order_id) is not None
        assert SafetyTripOrder.query.one().cancelled_at is not None
        assert trip_status(SafetyTripOrder.query.one()) == "cancelled"
        assert db.session.get(Task, task_id).status == Task.STATUS_CANCELLED
        assert SafetyJournalPage.query.order_by(SafetyJournalPage.id).first().revisions[0].pdf_sha256 == old_hash


def test_trip_validation_multiple_responsibles_and_secretary_scope(app, client, make_user, login, tmp_path):
    ids = _seed(app, make_user, tmp_path)
    login(ids["director"])
    assert client.post("/orders/new", data=_order_form(ids, responsible_user_ids=[])).status_code == 200
    with app.app_context():
        assert SchoolOrder.query.count() == 0
    data = _order_form(ids, responsible_user_ids=[str(ids["teacher"]), str(ids["second"])])
    assert client.post("/orders/new", data=data).status_code == 302
    with app.app_context():
        trip = SafetyTripOrder.query.one()
        order_id = trip.order_id
        assert len(trip.assignments) == 2
        assert Task.query.count() == 2
    assert client.post(f"/orders/{order_id}/edit", data=_order_form(ids, responsible_user_ids=[str(ids["teacher"]), str(ids["second"])], notes="Уточнение без изменения выезда")).status_code == 302
    with app.app_context():
        assert SafetyTripOrder.query.one().revision_number == 1
        assert Task.query.count() == 2
    # A direction viewer can see readiness in the order registry, not the student list or PDF.
    with app.app_context():
        from app.orders import _ensure_order_direction_access_table
        from sqlalchemy import text
        _ensure_order_direction_access_table()
        db.session.execute(text("INSERT INTO order_direction_access(section,user_id,access_type) VALUES ('excursions', :uid, 'viewer')"), {"uid": ids["secretary"]})
        db.session.commit()
    login(ids["secretary"])
    registry = client.get("/orders?section=excursions")
    assert registry.status_code == 200
    assert "Ожидает журнала" in registry.get_data(as_text=True)
    assert "Александров Илья" not in registry.get_data(as_text=True)
    assert client.get(f"/safety/trips/orders/{order_id}").status_code == 403
    login(ids["director"])
    assert client.post(f"/orders/{order_id}/edit", data=_order_form(ids, responsible_user_ids=[str(ids["teacher"])])).status_code == 302
    with app.app_context():
        removed = SafetyTripAssignment.query.filter_by(user_id=ids["second"]).one()
        assert not removed.is_active
        assert removed.task.status == Task.STATUS_CANCELLED
    login(ids["second"])
    assert client.get(f"/safety/trips/orders/{order_id}").status_code == 403


def test_changed_order_invalidates_trip_preview(app, client, make_user, login, tmp_path):
    ids = _seed(app, make_user, tmp_path)
    version_id = _create_instruction(app, ids["director"], ids["today"])
    login(ids["director"])
    client.post("/orders/new", data=_order_form(ids))
    with app.app_context():
        order_id = SafetyTripOrder.query.one().order_id
    login(ids["teacher"])
    draft_url = client.post(f"/safety/trips/orders/{order_id}/drafts").headers["Location"]
    client.post(f"{draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "grade": "5",
        "instruction_version_id": str(version_id), "class_ids": [str(ids["class"])],
    })
    preview = client.get(f"{draft_url}/preview")
    digest = re.search(r'name="preview_digest" value="([^"]+)"', preview.get_data(as_text=True)).group(1)
    login(ids["director"])
    client.post(f"/orders/{order_id}/edit", data=_order_form(ids, trip_destination="Другая площадка"))
    login(ids["teacher"])
    assert client.post(f"{draft_url}/generate", data={"preview_digest": digest}).status_code == 302
    with app.app_context():
        assert SafetyJournalPage.query.count() == 0
    fresh_url = client.post(f"/safety/trips/orders/{order_id}/drafts").headers["Location"]
    assert fresh_url != draft_url
