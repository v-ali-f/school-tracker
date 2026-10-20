from datetime import date
from io import BytesIO

from openpyxl import Workbook

from app.core.extensions import db
from app.models import AcademicYear, Department, StaffCourseImport, TeacherCourse, User
from app.modules.preschool.models import PreschoolGroup
from app.services.professional_development_service import course_status, import_courses, parse_courses


def _workbook(rows):
    book = Workbook()
    sheet = book.active
    sheet.append(["ФИО", "Должность", "Наименование курса", "Организация"])
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def test_import_matches_unique_employee_and_reimport_is_idempotent(app, client, make_user, login):
    employee_id = make_user("TEACHER")
    admin_id = make_user("ADMIN")
    with app.app_context():
        employee = db.session.get(User, employee_id)
        employee.last_name, employee.first_name, employee.middle_name = "Иванова", "Анна", "Петровна"
        db.session.commit()
        content = _workbook([
            ("Иванова  Анна Петровна", "Учитель", "Методика преподавания", "Учебный центр"),
            ("Неизвестная Мария Андреевна", "Учитель", "Новый курс", "Учебный центр"),
        ])
        first = import_courses(content, "Курсы 2023-2024.xlsx")
        second = import_courses(content, "Курсы 2023-2024.xlsx")
        assert (first["total"], first["linked"], first["unlinked"]) == (2, 1, 1)
        assert second["created"] == 0
        assert StaffCourseImport.query.count() == 2
        linked = StaffCourseImport.query.filter_by(teacher_id=employee_id).one()
        assert linked.title == "Методика преподавания"
        assert course_status([linked], date(2026, 10, 20))["code"] == "due"
    login(admin_id)
    profile = client.get(f"/departments/teachers/{employee_id}")
    assert profile.status_code == 200
    assert "Методика преподавания" in profile.get_data(as_text=True)
    assert "2023/2024" in profile.get_data(as_text=True)


def test_import_replaces_removed_rows_without_losing_history(app):
    with app.app_context():
        first = _workbook([("Учитель Один Первый", "Учитель", "Первый курс", "Центр")])
        second = _workbook([("Учитель Один Первый", "Учитель", "Второй курс", "Центр")])
        import_courses(first, "Курсы 2024-2025.xlsx")
        result = import_courses(second, "Курсы 2024-2025.xlsx")
        assert result["archived"] == 1
        assert StaffCourseImport.query.filter_by(is_archived=False).count() == 1


def test_manager_dashboard_and_personal_visibility(app, client, make_user, login):
    admin_id = make_user("ADMIN")
    viewer_id = make_user("VIEWER")
    login(viewer_id)
    assert client.get("/professional-development/").status_code == 403
    assert client.get("/professional-development/my").status_code == 200
    login(admin_id)
    response = client.get("/professional-development/")
    assert response.status_code == 200
    assert "Повышение квалификации" in response.get_data(as_text=True)


def test_uploaded_source_requires_year_and_known_columns():
    content = _workbook([("Иванов Иван Иванович", "Учитель", "Курс", "Центр")])
    assert parse_courses(content, "Курсы 2025-2026.xlsx")[0] == 2025
    try:
        parse_courses(content, "Курсы.xlsx")
    except ValueError as exc:
        assert "учебный год" in str(exc)
    else:
        assert False, "missing year must be rejected"


def test_teacher_can_update_imported_hours_and_corrections_survive_reimport(app, client, make_user, login):
    teacher_id = make_user("TEACHER")
    with app.app_context():
        teacher = db.session.get(User, teacher_id)
        teacher.last_name, teacher.first_name, teacher.middle_name = "Иванова", "Анна", "Петровна"
        db.session.commit()
        content = _workbook([("Иванова Анна Петровна", "Учитель", "Старое название", "Центр")])
        import_courses(content, "Курсы 2025-2026.xlsx")
        row_id = StaffCourseImport.query.one().id
    login(teacher_id)
    form = client.get(f"/professional-development/course/imported/{row_id}/edit")
    assert form.status_code == 200
    response = client.post(f"/professional-development/course/imported/{row_id}/edit", data={
        "title": "Уточнённое название", "provider": "Центр", "hours": "72",
        "completed_at": "2026-06-15",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Уточнённое название" in response.get_data(as_text=True)
    with app.app_context():
        import_courses(content, "Курсы 2025-2026.xlsx")
        row = db.session.get(StaffCourseImport, row_id)
        assert row.source_title == "Старое название"
        assert row.title == "Уточнённое название"
        assert row.hours == 72
        assert row.completed_at == date(2026, 6, 15)


def test_self_and_methodist_can_add_courses_but_cannot_edit_another_users_course(app, client, make_user, login):
    teacher_id = make_user("TEACHER")
    other_id = make_user("TEACHER")
    methodist_id = make_user("METHODIST")
    login(teacher_id)
    response = client.post("/professional-development/course/new", data={
        "teacher_id": other_id, "title": "Курс вне выгрузки", "provider": "Институт",
        "hours": "36", "end_date": "2026-10-01",
    })
    assert response.status_code == 302
    with app.app_context():
        row = TeacherCourse.query.one()
        assert row.teacher_id == teacher_id
        assert row.hours == 36
        record_id = row.id
    assert client.get(f"/professional-development/course/manual/{record_id}/edit").status_code == 200
    login(other_id)
    assert client.get(f"/professional-development/course/manual/{record_id}/edit").status_code == 403
    login(methodist_id)
    assert client.get(f"/professional-development/course/manual/{record_id}/edit").status_code == 200
    response = client.post("/professional-development/course/new", data={
        "teacher_id": other_id, "title": "Курс методиста", "hours": "16",
    })
    assert response.status_code == 302
    with app.app_context():
        assert TeacherCourse.query.filter_by(teacher_id=other_id, title="Курс методиста").count() == 1


def test_course_registry_filters_department_preschool_staff_and_course_name(
    app, client, make_user, login, monkeypatch,
):
    admin_id = make_user("ADMIN")
    preschool_id = make_user("VIEWER")
    school_id = make_user("TEACHER")
    with app.app_context():
        preschool = db.session.get(User, preschool_id)
        preschool.last_name, preschool.first_name = "Воспитатель", "Анна"
        school = db.session.get(User, school_id)
        school.last_name, school.first_name = "Учитель", "Борис"
        preschool_department = Department(name="Дошкольное отделение")
        school_department = Department(name="Кафедра математики")
        db.session.add_all([preschool_department, school_department])
        db.session.flush()
        db.session.add(StaffCourseImport(
            source_key="preschool-course", source_name="Курсы 2025-2026.xlsx",
            source_year=2025, source_row=2, employee_name=preschool.fio,
            position="Воспитатель", source_title="Работа с дошкольниками",
            source_provider="Педагогический центр", teacher_id=preschool_id,
        ))
        db.session.add(TeacherCourse(
            teacher_id=school_id, title="Алгебра в школе", provider="Институт", hours=72,
        ))
        db.session.commit()
        preschool_department_id = preschool_department.id
        school_department_id = school_department.id
    from app import professional_development as module
    monkeypatch.setattr(module, "current_department_memberships", lambda: (
        Department.query.filter(Department.id.in_([preschool_department_id, school_department_id])).all(),
        {preschool_id: {preschool_department_id}, school_id: {school_department_id}},
    ))
    login(admin_id)
    response = client.get(
        f"/professional-development/?department_id={preschool_department_id}"
        "&scope=preschool&q=дошкольниками"
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Работа с дошкольниками" in html
    assert "Воспитатель Анна" in html
    assert "Алгебра в школе" not in html
    assert "Реестр курсов сотрудников" in html
    response = client.get(
        f"/professional-development/?department_id={school_department_id}&scope=preschool"
    )
    assert "По выбранным условиям записей нет" in response.get_data(as_text=True)


def test_preschool_group_teacher_appears_without_imported_course(app, client, make_user, login):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("VIEWER")
    with app.app_context():
        teacher = db.session.get(User, teacher_id)
        teacher.last_name, teacher.first_name = "Педагог", "Детсада"
        year = AcademicYear(name="2026/2027", is_current=True)
        db.session.add(year)
        db.session.flush()
        db.session.add(PreschoolGroup(
            academic_year_id=year.id, name="Группа Радуга", teacher_user_id=teacher_id,
            is_active=True, is_archived=False,
        ))
        db.session.commit()
    login(admin_id)
    response = client.get("/professional-development/?scope=preschool")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Педагог Детсада" in html
    assert "Сведения о курсах отсутствуют" in html
    assert "Нет сведений" in html
    assert "Из 1 педагогических работников" in html
