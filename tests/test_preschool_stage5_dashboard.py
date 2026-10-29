from datetime import date

from app.core.extensions import db
from app.models_legacy import AcademicYear, Building, TeacherAttestation, TeacherCourse, TeacherMckoResult, User
from app.modules.preschool.dashboard_service import staff_snapshot
from app.modules.preschool.models import PreschoolBuildingStaff, PreschoolDashboardSetting, PreschoolGroup, PreschoolGroupAssignment


def _data(app, make_user):
    admin = make_user("ADMIN")
    director = make_user("DIRECTOR")
    deputy = make_user("DEPUTY_DIRECTOR")
    senior = make_user("SENIOR_EDUCATOR")
    educator = make_user("EDUCATOR")
    educator_without = make_user("EDUCATOR")
    assistant = make_user("ASSISTANT_EDUCATOR")
    with app.app_context():
        year = AcademicYear(name="2026/2027", is_current=True)
        first = Building(name="Сад 1")
        second = Building(name="Сад 2")
        db.session.add_all([year, first, second])
        db.session.flush()
        group = PreschoolGroup(name="Группа 1", building_id=first.id, academic_year_id=year.id)
        db.session.add(group)
        db.session.flush()
        db.session.add_all([
            PreschoolBuildingStaff(building_id=first.id, user_id=senior, position="SENIOR_EDUCATOR"),
            PreschoolBuildingStaff(building_id=first.id, user_id=educator, position="EDUCATOR"),
            PreschoolBuildingStaff(building_id=second.id, user_id=educator, position="EDUCATOR"),
            PreschoolBuildingStaff(building_id=second.id, user_id=educator_without, position="EDUCATOR"),
            PreschoolBuildingStaff(building_id=first.id, user_id=assistant, position="ASSISTANT_EDUCATOR"),
            PreschoolGroupAssignment(group_id=group.id, user_id=educator, position="EDUCATOR", building_id=first.id, academic_year_id=year.id),
            TeacherMckoResult(teacher_id=educator, diagnostic_title="Профессиональные компетенции воспитателя", passed_at=date(2025, 1, 1), expires_at=date(2027, 1, 1), level="HIGH"),
            TeacherCourse(teacher_id=educator, title="Программа 1", hours=36, end_date=date(2026, 10, 1)),
            TeacherCourse(teacher_id=educator, title="Программа 2", hours=72, end_date=date(2027, 2, 1)),
            TeacherAttestation(teacher_id=educator, category="FIRST", decision_date=date(2026, 1, 1), valid_until=date(2031, 1, 1)),
        ])
        db.session.commit()
        return admin, director, deputy, senior, educator, educator_without, assistant, first.id, second.id, year.id


def test_dashboard_counts_unique_staff_and_drilldown_matches(app, client, make_user, login):
    admin, _, _, _, educator, educator_without, _, first, second, year = _data(app, make_user)
    login(admin)
    response = client.get(f"/preschool/dashboard?academic_year_id={year}&as_of=2026-10-29")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert ">4</strong><span>Всего сотрудников" in page
    assert ">2</strong><span>Всего воспитателей" in page
    assert ">1</strong><span>Без результата МЦКО" in page
    assert ">108</strong><span>Суммарные часы курсов" in page or ">108.0</strong><span>Суммарные часы курсов" in page
    valid = client.get(f"/preschool/staff/composition?status=mcko_valid&academic_year_id={year}&as_of=2026-10-29")
    assert valid.status_code == 200
    assert "С действующим МЦКО · 1" in valid.get_data(as_text=True)
    assert "Пользователь" in valid.get_data(as_text=True)
    missing = client.get(f"/preschool/staff/composition?status=mcko_missing&academic_year_id={year}&building_id={second}&as_of=2026-10-29")
    assert missing.status_code == 200
    assert "Без результата МЦКО · 1" in missing.get_data(as_text=True)
    assert client.get(f"/preschool/dashboard?building_id=99999&academic_year_id={year}").status_code == 403


def test_senior_scope_deputy_global_and_settings(app, client, make_user, login):
    admin, _, deputy, senior, _, _, _, first, second, year = _data(app, make_user)
    login(senior)
    page = client.get("/preschool/dashboard")
    assert page.status_code == 200
    assert "Сад 1" in page.get_data(as_text=True)
    assert "Сад 2" not in page.get_data(as_text=True)
    assert client.get(f"/preschool/staff/composition?building_id={second}").status_code == 403
    assert client.post("/preschool/dashboard/settings", data={"warning_months": 12}).status_code == 403
    login(deputy)
    assert "Сад 2" in client.get("/preschool/dashboard").get_data(as_text=True)
    assert client.post("/preschool/dashboard/settings", data={"warning_months": 12}).status_code == 403
    login(admin)
    assert client.post("/preschool/dashboard/settings", data={"warning_months": 12}).status_code == 302
    with app.app_context():
        assert db.session.get(PreschoolDashboardSetting, 1).warning_months == 12


def test_viewer_and_educator_cannot_open_management_dashboard(client, make_user, login):
    login(make_user("EDUCATOR"))
    assert client.get("/preschool/dashboard").status_code == 403
    assert client.get("/preschool/staff/composition").status_code == 403
    login(make_user("VIEWER"))
    assert client.get("/preschool/dashboard").status_code == 403


def test_attestation_recommendation_after_two_years_and_repeats_after_five(app, make_user):
    _, _, _, _, educator, educator_without, _, first, second, year_id = _data(app, make_user)
    with app.app_context():
        db.session.get(User, educator_without).employment_start_date = date(2024, 10, 29)
        db.session.add(TeacherAttestation(
            teacher_id=educator_without, category="POSITION_COMPLIANCE",
            decision_date=date(2025, 1, 1), valid_until=date(2027, 1, 1),
        ))
        db.session.commit()
        rows = staff_snapshot(
            as_of=date(2026, 10, 29), year=db.session.get(AcademicYear, year_id),
            allowed_building_ids={first, second}, warning_months=6,
        )
        by_id = {row.user.id: row for row in rows}
        assert by_id[educator_without].attestation_due_at == date(2030, 1, 1)
        assert by_id[educator_without].attestation_state == "VALID"
        db.session.get(TeacherAttestation, by_id[educator_without].attestation_record.id).is_archived = True
        db.session.commit()
        rows = staff_snapshot(
            as_of=date(2026, 10, 29), year=db.session.get(AcademicYear, year_id),
            allowed_building_ids={first, second}, warning_months=6,
        )
        by_id = {row.user.id: row for row in rows}
        assert by_id[educator_without].attestation_state == "DUE"
        assert by_id[educator_without].attestation_due_at == date(2026, 10, 29)
        assert by_id[educator].attestation_state == "VALID"
