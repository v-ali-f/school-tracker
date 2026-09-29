from datetime import date

from app.core.extensions import db
from app.models import AcademicYear, Child, ChildEnrollment, SchoolClass, User
from app.models.service_staff import ServiceAssignment, ServiceSpecialist
from app.service_staff import _class_choices


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


def test_assignment_form_uses_only_current_academic_year_classes(
    app,
    make_user,
):
    teacher_id = make_user("CLASS_TEACHER")
    with app.app_context():
        previous_year = AcademicYear(name="2025/2026", is_current=False)
        current_year = AcademicYear(name="2026/2027", is_current=True)
        db.session.add_all([previous_year, current_year])
        db.session.flush()
        db.session.add_all([
            SchoolClass(
                academic_year_id=previous_year.id,
                name="2А",
                grade=2,
                letter="А",
                teacher_user_id=teacher_id,
            ),
            SchoolClass(
                academic_year_id=current_year.id,
                name="2А",
                grade=2,
                letter="А",
                teacher_user_id=teacher_id,
            ),
        ])
        db.session.commit()

        rows = _class_choices()

        assert [row.name for row in rows] == ["2А"]
        assert rows[0].academic_year_id == current_year.id


def test_group_assignment_accepts_children_from_different_classes(
    app,
    client,
    make_user,
    login,
):
    context = _group_context(app, make_user)
    with app.app_context():
        current_year = AcademicYear.query.filter_by(is_current=True).one()
        second_class = SchoolClass(
            academic_year_id=current_year.id,
            name="8Б",
            grade=8,
            letter="Б",
        )
        second_child = Child(last_name="Сидоров", first_name="Сидор")
        db.session.add_all([second_class, second_child])
        db.session.flush()
        db.session.add(ChildEnrollment(
            child_id=second_child.id,
            academic_year_id=current_year.id,
            school_class_id=second_class.id,
            status="ACTIVE",
        ))
        db.session.commit()
        second_child_id = second_child.id

    login(context["admin_id"])
    selected_ids = [context["child_ids"][0], second_child_id]
    response = client.post(
        "/service-staff/assignments/new",
        data={
            "child_ids": [str(child_id) for child_id in selected_ids],
            "order_number": "201-ОД",
            "order_date": "2026-09-29",
            "iup_end_date": "2027-05-31",
            "enabled_roles": "pedagog_psychologist",
            "role_pedagog_psychologist_specialist_id": str(context["specialist_id"]),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "обучающихся — 2" in response.get_data(as_text=True)
    with app.app_context():
        assert {row.child_id for row in ServiceAssignment.query.all()} == set(selected_ids)
