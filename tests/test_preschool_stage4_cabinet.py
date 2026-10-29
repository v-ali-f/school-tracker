from app.core.extensions import db
from app.models_legacy import AcademicYear, Building, TeacherAttestation, TeacherCourse, TeacherMckoResult, TeacherProfessionalRecordChange, User
from app.modules.preschool.access import CHIEF_EDUCATOR
from app.modules.preschool.models import PreschoolAchievement, PreschoolBuildingStaff, PreschoolChild, PreschoolGroup, PreschoolGroupAssignment, PreschoolProfileChange, PreschoolResponsibility


def _setup(app, make_user):
    admin = make_user("ADMIN")
    educator = make_user("EDUCATOR")
    assistant = make_user("ASSISTANT_EDUCATOR")
    senior = make_user("SENIOR_EDUCATOR")
    deputy = make_user("DEPUTY_DIRECTOR")
    with app.app_context():
        year = AcademicYear(name="2026/2027", is_current=True)
        first = Building(name="Детский сад 1", is_preschool=True)
        second = Building(name="Детский сад 2", is_preschool=True)
        db.session.add_all([year, first, second])
        db.session.flush()
        group = PreschoolGroup(name="Группа 1", academic_year_id=year.id, building_id=first.id)
        other = PreschoolGroup(name="Группа 2", academic_year_id=year.id, building_id=second.id)
        db.session.add_all([group, other])
        db.session.flush()
        child = PreschoolChild(group_id=group.id, last_name="Ребёнок", first_name="Один")
        other_child = PreschoolChild(group_id=other.id, last_name="Ребёнок", first_name="Два")
        db.session.add_all([child, other_child])
        db.session.add_all([
            PreschoolBuildingStaff(building_id=first.id, user_id=educator, position="EDUCATOR"),
            PreschoolBuildingStaff(building_id=first.id, user_id=assistant, position="ASSISTANT_EDUCATOR"),
            PreschoolBuildingStaff(building_id=first.id, user_id=senior, position="SENIOR_EDUCATOR"),
            PreschoolGroupAssignment(group_id=group.id, user_id=educator, position="EDUCATOR", building_id=first.id, academic_year_id=year.id),
            PreschoolGroupAssignment(group_id=group.id, user_id=assistant, position="ASSISTANT_EDUCATOR", building_id=first.id, academic_year_id=year.id),
        ])
        db.session.commit()
        return admin, educator, assistant, senior, deputy, group.id, child.id, other_child.id


def test_cabinet_edits_shared_mcko_and_course_records(app, client, make_user, login):
    admin, educator, _, _, _, _, _, _ = _setup(app, make_user)
    with app.app_context():
        imported = TeacherCourse(teacher_id=educator, title="Педагогика дошкольного образования", entry_source="ADMINISTRATION")
        db.session.add(imported)
        db.session.commit()
        imported_id = imported.id
    login(educator)
    page = client.get("/preschool/cabinet", follow_redirects=True)
    assert page.status_code == 200
    assert "Педагогика дошкольного образования" in page.get_data(as_text=True)
    assert client.post(f"/preschool/staff/{educator}/mcko", data={
        "passed_at": "2026-10-01", "level": "HIGH", "certificate_number": "ПК-123", "result_text": "Успешно",
    }).status_code == 302
    with app.app_context():
        record = TeacherMckoResult.query.filter_by(teacher_id=educator).one()
        record_id = record.id
        assert record.diagnostic_title == "Профессиональные компетенции воспитателя"
        assert TeacherProfessionalRecordChange.query.filter_by(record_type="MCKO", record_id=record_id).count() == 1
    assert client.post(f"/preschool/staff/{educator}/mcko", data={
        "record_id": record_id, "passed_at": "2026-10-02", "level": "EXPERT", "certificate_number": "ПК-123",
    }).status_code == 302
    assert client.post(f"/preschool/staff/{educator}/course", data={
        "record_id": imported_id, "title": "Педагогика дошкольного образования", "hours": "72", "document_number": "777",
    }).status_code == 302
    assert client.post(f"/preschool/staff/{educator}/course", data={
        "title": "Игровые технологии", "hours": "36", "document_number": "888",
    }).status_code == 302
    assert client.post(f"/preschool/staff/{educator}/course", data={
        "title": "Игровые технологии", "hours": "36", "document_number": "888",
    }).status_code == 409
    with app.app_context():
        assert db.session.get(TeacherMckoResult, record_id).level == "EXPERT"
        assert db.session.get(TeacherCourse, imported_id).hours == 72
        assert TeacherProfessionalRecordChange.query.filter_by(record_type="MCKO", record_id=record_id).count() == 2
        assert TeacherProfessionalRecordChange.query.filter_by(record_type="COURSE", record_id=imported_id).count() == 1
    login(admin)
    assert "Профессиональные компетенции воспитателя" in client.get("/professional-registers/mcko").get_data(as_text=True)
    assert "Игровые технологии" in client.get("/professional-registers/courses?scope=preschool").get_data(as_text=True)


def test_profile_and_achievements_protect_assignments_and_child_scope(app, client, make_user, login):
    admin, educator, assistant, senior, _, group, child, other_child = _setup(app, make_user)
    login(educator)
    response = client.post("/preschool/cabinet/profile", data={
        "last_name": "Новая", "first_name": "Фамилия", "phone": "+79990000000",
        "role": "ADMIN", "building_id": "999",
    })
    assert response.status_code == 302
    assert client.post(f"/preschool/staff/{educator}/achievement", data={
        "kind": "CHILD", "event_name": "Конкурс рисунков", "child_id": child,
        "event_date": "2026-10-20", "result": "Победитель",
    }).status_code == 302
    assert client.post(f"/preschool/staff/{educator}/achievement", data={
        "kind": "CHILD", "event_name": "Чужая группа", "child_id": other_child,
    }).status_code == 403
    assert client.post(f"/preschool/staff/{educator}/achievement", data={
        "kind": "PEDAGOGICAL", "event_name": "Воспитатель года", "result": "Лауреат",
    }).status_code == 302
    assert client.get(f"/preschool/staff/{assistant}/profile").status_code == 403
    login(assistant)
    assert client.get("/preschool/cabinet", follow_redirects=True).status_code == 200
    assert client.post(f"/preschool/staff/{educator}/course", data={"title": "Подмена"}).status_code == 403
    login(senior)
    assert client.get(f"/preschool/staff/{educator}/profile").status_code == 200
    assert client.post(f"/preschool/staff/{educator}/course", data={"title": "Подмена"}).status_code == 403
    login(admin)
    assert "Конкурс рисунков" in client.get("/professional-registers/achievements?kind=CHILD").get_data(as_text=True)
    assert "Воспитатель года" in client.get("/professional-registers/achievements?kind=PEDAGOGICAL").get_data(as_text=True)
    with app.app_context():
        user = db.session.get(User, educator)
        assert user.last_name == "Новая"
        assert user.role == "EDUCATOR"
        assert PreschoolProfileChange.query.filter_by(user_id=educator).count() == 1
        assert PreschoolAchievement.query.filter_by(teacher_id=educator).count() == 2


def test_chief_attests_all_preschool_staff_and_educator_is_read_only(app, client, make_user, login):
    admin, educator, assistant, senior, deputy, _, _, _ = _setup(app, make_user)
    other_educator = make_user("EDUCATOR")
    with app.app_context():
        second = Building.query.filter_by(name="Детский сад 2").one()
        db.session.add(PreschoolBuildingStaff(building_id=second.id, user_id=other_educator, position="EDUCATOR"))
        db.session.add(PreschoolResponsibility(kind=CHIEF_EDUCATOR, user_id=senior, assigned_by_user_id=admin))
        db.session.commit()
    login(educator)
    assert client.post(f"/preschool/staff/{educator}/attestation", data={
        "category": "FIRST", "decision_date": "2026-10-01", "valid_until": "2031-10-01",
    }).status_code == 403
    login(senior)
    assert client.get(f"/preschool/staff/{other_educator}/profile").status_code == 200
    assert client.post(f"/preschool/staff/{other_educator}/attestation", data={
        "category": "POSITION_COMPLIANCE", "decision_date": "2026-10-01", "position_title": "Воспитатель",
        "order_number": "123",
    }).status_code == 302
    assert client.post(f"/preschool/staff/{assistant}/attestation", data={
        "category": "FIRST", "decision_date": "2026-10-01", "valid_until": "2031-10-01",
    }).status_code == 403
    login(deputy)
    assert client.get(f"/preschool/staff/{other_educator}/profile").status_code == 200
    assert client.post(f"/preschool/staff/{other_educator}/attestation", data={
        "category": "FIRST", "decision_date": "2026-10-01", "valid_until": "2031-10-01",
    }).status_code == 403
    assert "Воспитатель" in client.get("/professional-registers/attestations").get_data(as_text=True)
    with app.app_context():
        record = TeacherAttestation.query.filter_by(teacher_id=other_educator).one()
        assert record.order_number == "123"
        assert TeacherProfessionalRecordChange.query.filter_by(record_type="ATTESTATION", record_id=record.id).count() == 1
