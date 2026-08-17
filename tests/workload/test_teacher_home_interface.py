from app.core.extensions import db
from app.models import AcademicYear, Building, Child, ChildEnrollment, SchoolClass


def _assigned_viewer_context(app, make_user):
    viewer_id = make_user("VIEWER")
    with app.app_context():
        year = AcademicYear(name="2026/2027", is_current=True)
        building = Building(name="Учебный корпус")
        db.session.add_all((year, building))
        db.session.flush()
        own_class = SchoolClass(
            academic_year_id=year.id,
            building_id=building.id,
            name="5А",
            grade=5,
            letter="А",
            teacher_user_id=viewer_id,
            is_active=True,
            is_archived=False,
        )
        other_class = SchoolClass(
            academic_year_id=year.id,
            building_id=building.id,
            name="5Б",
            grade=5,
            letter="Б",
            is_active=True,
            is_archived=False,
        )
        own_child = Child(last_name="Иванов", first_name="Иван")
        other_child = Child(last_name="Петров", first_name="Пётр")
        db.session.add_all((own_class, other_class, own_child, other_child))
        db.session.flush()
        db.session.add_all((
            ChildEnrollment(
                child_id=own_child.id,
                academic_year_id=year.id,
                school_class_id=own_class.id,
                status="ACTIVE",
            ),
            ChildEnrollment(
                child_id=other_child.id,
                academic_year_id=year.id,
                school_class_id=other_class.id,
                status="ACTIVE",
            ),
        ))
        db.session.commit()
        return viewer_id, own_class.id, other_class.id


def test_assigned_viewer_gets_teacher_home_and_only_own_class(
    app,
    client,
    make_user,
    login,
):
    viewer_id, own_class_id, other_class_id = _assigned_viewer_context(
        app,
        make_user,
    )
    login(viewer_id)

    home = client.get("/")
    html = home.get_data(as_text=True)
    assert home.status_code == 200
    assert "Классное руководство" in html
    assert "Мой профиль преподавателя" in html
    assert "Добавить инцидент" in html
    assert "Мои инциденты" in html
    assert "Диагностики МЦКО" not in html
    assert "Дошкольное отделение" not in html
    assert ">Кафедры<" not in html
    assert 'id="navSearch"' not in html
    assert "Поиск ученика по школе" not in html

    own_children = client.get("/children")
    own_html = own_children.get_data(as_text=True)
    assert own_children.status_code == 200
    assert "Иванов" in own_html
    assert "Петров" not in own_html

    classroom = client.get("/hub/classroom")
    classroom_html = classroom.get_data(as_text=True)
    assert classroom.status_code == 200
    assert "5А" in classroom_html
    assert "Обучающихся" in classroom_html
    assert f"/social-passport/class/{own_class_id}" in classroom_html
    assert f"/hub/classroom/curriculum?class_id={own_class_id}" in classroom_html
    assert f"/hub/classroom/groups?class_id={own_class_id}" in classroom_html

    assert client.get(f"/social-passport/class/{own_class_id}").status_code == 200
    assert client.get(f"/social-passport/class/{other_class_id}").status_code == 403


def test_teacher_schoolwide_search_is_closed_but_incident_flow_is_available(
    app,
    client,
    make_user,
    login,
):
    viewer_id, own_class_id, _ = _assigned_viewer_context(app, make_user)
    login(viewer_id)

    search = client.get("/children/search-ajax?q=Иван")
    assert search.status_code == 200
    assert search.get_json() == []
    assert client.get("/contingent").status_code == 403
    assert client.get("/hub/departments").status_code == 403
    assert client.get("/diagnostics/").status_code == 403

    assert client.get("/incidents/new").status_code == 200
    assert client.get("/incidents/my").status_code == 200
    classes = client.get("/api/classes/by-grade?grade=5")
    assert classes.status_code == 200
    assert any(row["id"] == own_class_id for row in classes.get_json())
    children = client.get(f"/api/children/by-class?class_id={own_class_id}")
    assert children.status_code == 200
    assert any("Иванов" in row["fio"] for row in children.get_json())


def test_admin_and_methodist_keep_schoolwide_search_and_diagnostics(
    client,
    make_user,
    login,
):
    for role in ("ADMIN", "METHODIST"):
        user_id = make_user(role)
        login(user_id)
        home = client.get("/")
        html = home.get_data(as_text=True)
        assert home.status_code == 200
        assert 'id="navSearch"' in html
        assert "Поиск ученика по школе" in html
        assert client.get("/diagnostics/").status_code == 200
