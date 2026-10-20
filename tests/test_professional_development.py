from datetime import date
from io import BytesIO

from openpyxl import Workbook

from app.core.extensions import db
from app.models import StaffCourseImport, User
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
