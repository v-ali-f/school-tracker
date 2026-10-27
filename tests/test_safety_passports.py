from io import BytesIO

from app.core.extensions import db
from app.models import Building, SafetyOfficerAssignment, SafetyPassport, SchoolClassroom, User


def _save_form(base_number=0, year="2026/2027", purpose="Учебные занятия"):
    return {
        "base_revision_number": str(base_number),
        "purpose": purpose,
        "safety_notes": "Проверять проходы перед занятием",
        "annual_year": year,
        "compliance_fire": "yes",
        "inventory_name[]": ["Парты"],
        "inventory_quantity[]": ["15"],
    }


def test_passport_stays_with_classroom_after_teacher_change_and_review(
    app, client, make_user, login,
):
    director_id = make_user("DIRECTOR")
    officer_id = make_user("TEACHER")
    first_id = make_user("TEACHER")
    second_id = make_user("TEACHER")
    with app.app_context():
        building = Building(name="Учебный корпус")
        db.session.add(building)
        db.session.flush()
        classroom = SchoolClassroom(
            building_id=building.id, name="Кабинет 101",
            room_type="Начальные классы", area=45, floor=1,
        )
        classroom.teachers.append(db.session.get(User, first_id))
        db.session.add(classroom)
        db.session.commit()
        classroom_id = classroom.id

    login(first_id)
    assert client.get("/safety/passports/").status_code == 200
    assert client.get(f"/safety/passports/{classroom_id}").status_code == 200
    saved = client.post(f"/safety/passports/{classroom_id}/save", data=_save_form())
    assert saved.status_code == 302
    assert client.post(f"/safety/passports/{classroom_id}/submit").status_code == 302

    login(director_id)
    assert client.get("/safety/passports/officers").status_code == 200
    assert client.get("/safety/passports/").status_code == 200
    appointed = client.post("/safety/passports/officers", data={
        "user_id": officer_id, "valid_from": "2026-01-01",
    })
    assert appointed.status_code == 302
    assert client.get("/safety/passports/officers").status_code == 200
    client.post("/safety/passports/officers", data={
        "user_id": second_id, "valid_from": "2026-02-01",
    })
    with app.app_context():
        assert SafetyOfficerAssignment.query.count() == 1
    client.post("/safety/passports/officers", data={
        "user_id": director_id, "valid_from": "2026-02-01", "can_manage_instructions": "1",
    })
    with app.app_context():
        assignments = SafetyOfficerAssignment.query.all()
        assert len(assignments) == 2
        assert any(item.user_id == director_id and item.can_manage_instructions for item in assignments)
    login(officer_id)
    assert client.get(f"/safety/passports/{classroom_id}").status_code == 200
    assert client.get(f"/safety/passports/{classroom_id}/print").status_code == 200
    reviewed = client.post(f"/safety/passports/{classroom_id}/review", data={
        "result": "verified", "comment": "Соответствует",
    })
    assert reviewed.status_code == 302
    corrected = client.post(f"/safety/passports/{classroom_id}/review", data={
        "result": "verified", "comment": "Исправлена опечатка в отметке",
    })
    assert corrected.status_code == 302

    with app.app_context():
        classroom = db.session.get(SchoolClassroom, classroom_id)
        classroom.teachers = [db.session.get(User, second_id)]
        classroom.teacher_user_id = second_id
        db.session.commit()
        passport_id = classroom.safety_passport.id

    login(first_id)
    assert client.get(f"/safety/passports/{classroom_id}").status_code == 403
    assert client.post(f"/safety/passports/{classroom_id}/save", data=_save_form(1)).status_code == 403

    login(second_id)
    page = client.get(f"/safety/passports/{classroom_id}")
    assert page.status_code == 200
    assert "Учебные занятия" in page.get_data(as_text=True)
    assert client.get(f"/safety/passports/{classroom_id}/print").status_code == 200
    changed = client.post(
        f"/safety/passports/{classroom_id}/save",
        data=_save_form(1, "2027/2028", "Новый учебный год"),
    )
    assert changed.status_code == 302
    with app.app_context():
        passports = SafetyPassport.query.filter_by(classroom_id=classroom_id).all()
        assert len(passports) == 1
        assert passports[0].id == passport_id
        assert passports[0].status == "needs_recheck"
        assert [item.number for item in passports[0].revisions] == [1, 2]
        assert [check.result for check in passports[0].revisions[0].reviews] == ["verified", "verified"]


def test_concurrent_edit_is_rejected_and_only_officer_reviews(app, client, make_user, login):
    teacher_id = make_user("TEACHER")
    director_id = make_user("DIRECTOR")
    with app.app_context():
        building = Building(name="Основной корпус")
        db.session.add(building)
        db.session.flush()
        classroom = SchoolClassroom(building_id=building.id, name="Кабинет 202", teacher_user_id=teacher_id)
        db.session.add(classroom)
        db.session.commit()
        classroom_id = classroom.id
    login(teacher_id)
    client.get(f"/safety/passports/{classroom_id}")
    assert client.post(f"/safety/passports/{classroom_id}/save", data=_save_form()).status_code == 302
    stale = client.post(f"/safety/passports/{classroom_id}/save", data=_save_form(0, purpose="Чужая правка"))
    assert stale.status_code == 409
    assert client.post(f"/safety/passports/{classroom_id}/review", data={"result": "verified"}).status_code == 403
    login(director_id)
    assert client.post(f"/safety/passports/{classroom_id}/review", data={"result": "verified"}).status_code == 403
    with app.app_context():
        passport = SafetyPassport.query.filter_by(classroom_id=classroom_id).one()
        assert passport.current_revision_number == 1
        assert passport.revisions[0].data["purpose"] == "Учебные занятия"


def test_director_and_admin_can_edit_active_classroom_passport(app, client, make_user, login):
    director_id = make_user("DIRECTOR")
    admin_id = make_user("ADMIN")
    viewer_id = make_user("VIEWER")
    with app.app_context():
        building = Building(name="Корпус")
        db.session.add(building)
        db.session.flush()
        classroom = SchoolClassroom(building_id=building.id, name="Кабинет 205")
        db.session.add(classroom)
        db.session.commit()
        classroom_id = classroom.id

    login(director_id)
    assert 'id="passport-form"' in client.get(f"/safety/passports/{classroom_id}").get_data(as_text=True)
    assert client.post(f"/safety/passports/{classroom_id}/save", data=_save_form()).status_code == 302
    login(admin_id)
    assert 'id="passport-form"' in client.get(f"/safety/passports/{classroom_id}").get_data(as_text=True)
    assert client.post(f"/safety/passports/{classroom_id}/save", data=_save_form(1, purpose="Уточнение администратора")).status_code == 302
    with app.app_context():
        passport = SafetyPassport.query.filter_by(classroom_id=classroom_id).one()
        assert passport.current_revision_number == 2
    login(viewer_id)
    assert client.post(f"/safety/passports/{classroom_id}/save", data=_save_form(2)).status_code == 403


def test_document_with_russian_name_is_private(app, client, make_user, login, tmp_path):
    teacher_id = make_user("TEACHER")
    viewer_id = make_user("VIEWER")
    with app.app_context():
        building = Building(name="Корпус Б")
        db.session.add(building)
        db.session.flush()
        classroom = SchoolClassroom(building_id=building.id, name="Кабинет 301", teacher_user_id=teacher_id)
        db.session.add(classroom)
        db.session.commit()
        classroom_id = classroom.id
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    login(teacher_id)
    client.get(f"/safety/passports/{classroom_id}")
    uploaded = client.post(
        f"/safety/passports/{classroom_id}/documents",
        data={"document": (BytesIO(b"%PDF-1.4 test"), "Паспорт кабинета.pdf")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 302
    with app.app_context():
        passport = SafetyPassport.query.filter_by(classroom_id=classroom_id).one()
        document = passport.documents[0]
        assert document.original_name == "Паспорт кабинета.pdf"
        document_id = document.id
    response = client.get(f"/safety/passports/{classroom_id}/documents/{document_id}")
    assert response.status_code == 200
    assert response.data.startswith(b"%PDF")
    login(viewer_id)
    assert client.get(f"/safety/passports/{classroom_id}/documents/{document_id}").status_code == 403
