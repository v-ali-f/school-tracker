from datetime import date

from app.core.extensions import db
from app.models import AcademicYear, Child, ChildEnrollment, SchoolClass, User
from app.models.service_staff import ServiceAssignment, ServiceSpecialist


def _group_context(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("CLASS_TEACHER")
    psychologist_user_id = make_user("PSYCHOLOGIST")
    with app.app_context():
        year = AcademicYear(
            name="2026/2027",
            is_current=True,
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
        )
        db.session.add(year)
        db.session.flush()
        school_class = SchoolClass(
            academic_year_id=year.id,
            name="7А",
            grade=7,
            letter="А",
            teacher_user_id=teacher_id,
        )
        children = [
            Child(last_name="Иванов", first_name="Иван"),
            Child(last_name="Петров", first_name="Петр"),
        ]
        db.session.add_all([school_class, *children])
        db.session.flush()
        for child in children:
            db.session.add(
                ChildEnrollment(
                    child_id=child.id,
                    academic_year_id=year.id,
                    school_class_id=school_class.id,
                    status="ACTIVE",
                )
            )
        psychologist = ServiceSpecialist(
            user_id=psychologist_user_id,
            last_name="Иванова",
            first_name="Анна",
            middle_name="Алексеевна",
            position_title="Педагог-психолог",
            is_active=True,
        )
        db.session.add(psychologist)
        db.session.commit()
        return {
            "admin_id": admin_id,
            "child_ids": [child.id for child in children],
            "specialist_id": psychologist.id,
        }


def test_group_assignment_creates_registry_rows_with_order_and_iup(
    app,
    client,
    make_user,
    login,
):
    context = _group_context(app, make_user)
    login(context["admin_id"])

    response = client.post(
        "/service-staff/assignments/new",
        data={
            "child_ids": [str(child_id) for child_id in context["child_ids"]],
            "order_number": "145-ОД",
            "order_date": "2026-09-15",
            "iup_end_date": "2027-05-31",
            "status": "ACTIVE",
            "start_date": "2026-09-15",
            "enabled_roles": "pedagog_psychologist",
            "role_pedagog_psychologist_specialist_id": str(context["specialist_id"]),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "обучающихся — 2" in html
    assert "145-ОД" in html
    assert "31.05.2027" in html
    assert "Иванова А.А." in html
    assert "Педагог-психолог" in html
    assert "Социальный педагог</th>" not in html

    with app.app_context():
        rows = ServiceAssignment.query.order_by(ServiceAssignment.child_id).all()
        assert len(rows) == 2
        assert {row.child_id for row in rows} == set(context["child_ids"])
        assert {row.order_number for row in rows} == {"145-ОД"}
        assert {row.order_date for row in rows} == {date(2026, 9, 15)}
        assert {row.iup_end_date for row in rows} == {date(2027, 5, 31)}

    form_response = client.get("/service-staff/assignments/new")
    form_html = form_response.get_data(as_text=True)
    assert "Комментарий / примечание" in form_html
    assert "Параметры сопровождения" not in form_html
    assert "Дата завершения сопровождения" not in form_html


def test_group_assignment_requires_order_details(
    app,
    client,
    make_user,
    login,
):
    context = _group_context(app, make_user)
    login(context["admin_id"])

    response = client.post(
        "/service-staff/assignments/new",
        data={
            "child_ids": str(context["child_ids"][0]),
            "status": "ACTIVE",
            "enabled_roles": "pedagog_psychologist",
            "role_pedagog_psychologist_specialist_id": str(context["specialist_id"]),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Укажите номер приказа" in response.get_data(as_text=True)
    with app.app_context():
        assert ServiceAssignment.query.count() == 0
