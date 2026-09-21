from app.core.extensions import db
from app.models import Building, SchoolClassroom, User


def test_admin_manages_shared_teacher_classrooms(
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
            "teacher_user_ids": [teacher_id],
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

    same_building = client.post(
        "/classrooms/new",
        data={
            "building_id": first_id,
            "name": "Кабинет 202",
            "teacher_user_ids": [teacher_id],
            "is_active": "1",
        },
        follow_redirects=True,
    )
    assert "Кабинет добавлен" in same_building.get_data(as_text=True)

    second_building = client.post(
        "/classrooms/new",
        data={
            "building_id": second_id,
            "name": "Кабинет 101",
            "teacher_user_ids": [teacher_id],
            "is_active": "1",
        },
        follow_redirects=True,
    )
    assert "Кабинет добавлен" in second_building.get_data(as_text=True)
    with app.app_context():
        rooms = (
            SchoolClassroom.query
            .filter(SchoolClassroom.teachers.any(User.id == teacher_id))
            .all()
        )
        assert len(rooms) == 3
        assert {item.building_id for item in rooms} == {
            first_id,
            second_id,
        }
        assert all(teacher_id in item.assigned_teacher_ids for item in rooms)
