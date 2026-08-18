from app.core.extensions import db
from app.models import Building, SchoolClassroom, User


def test_admin_manages_teacher_classrooms_per_building(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        teacher = db.session.get(User, teacher_id)
        teacher.last_name = "Иванова"
        teacher.first_name = "Мария"
        first = Building(name="Первый корпус", short_name="К1")
        second = Building(name="Второй корпус", short_name="К2")
        db.session.add_all([first, second])
        db.session.commit()
        first_id = first.id
        second_id = second.id

    login(admin_id)
    created = client.post(
        "/classrooms/new",
        data={
            "building_id": first_id,
            "name": "Кабинет 201",
            "short_name": "201",
            "capacity": "30",
            "teacher_user_id": teacher_id,
            "is_active": "1",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200
    assert "Кабинет добавлен" in created.get_data(as_text=True)
    assert "Кабинет 201" in created.get_data(as_text=True)
    assert 'class="registry-matrix registry-matrix-wide' in (
        created.get_data(as_text=True)
    )
    assert "data-classroom-edit-button" in created.get_data(as_text=True)

    duplicate_teacher = client.post(
        "/classrooms/new",
        data={
            "building_id": first_id,
            "name": "Кабинет 202",
            "teacher_user_id": teacher_id,
            "is_active": "1",
        },
        follow_redirects=True,
    )
    assert "за педагогом уже закреплён кабинет" in (
        duplicate_teacher.get_data(as_text=True)
    )

    second_building = client.post(
        "/classrooms/new",
        data={
            "building_id": second_id,
            "name": "Кабинет 101",
            "teacher_user_id": teacher_id,
            "is_active": "1",
        },
        follow_redirects=True,
    )
    assert "Кабинет добавлен" in second_building.get_data(as_text=True)
    with app.app_context():
        rooms = SchoolClassroom.query.filter_by(
            teacher_user_id=teacher_id
        ).all()
        assert {item.building_id for item in rooms} == {
            first_id,
            second_id,
        }
