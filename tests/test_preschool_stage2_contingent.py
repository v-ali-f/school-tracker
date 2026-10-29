from io import BytesIO
import re

from app.core.extensions import db
from app.models_legacy import AcademicYear, Building
from app.modules.preschool.models import PreschoolChild, PreschoolChildMovement, PreschoolGroup


def _sample_contingent(app):
    with app.app_context():
        year = AcademicYear(name="2026/2027", is_current=True)
        db.session.add(year)
        db.session.flush()
        first = PreschoolGroup(name="Ромашка", academic_year_id=year.id)
        second = PreschoolGroup(name="Берёзка", academic_year_id=year.id)
        db.session.add_all([first, second])
        db.session.flush()
        child = PreschoolChild(group_id=first.id, last_name="Иванова", first_name="Анна")
        db.session.add(child)
        db.session.commit()
        return year.id, first.id, second.id, child.id


def test_contingent_pages_use_shared_workspace(app, client, make_user, login):
    year_id, first_id, _, child_id = _sample_contingent(app)
    login(make_user("ADMIN"))
    for path in (
        "/preschool/children",
        "/preschool/children/registry",
        f"/preschool/children/{child_id}",
        f"/preschool/children/{child_id}/edit",
        "/preschool/movements",
        f"/preschool/movements/bulk?academic_year_id={year_id}",
        "/preschool/children/import",
        "/preschool/representatives/import",
        "/preschool/groups",
        f"/preschool/groups/{first_id}/edit",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert b"sp-workspace ws-workspace" in response.data, path
    assert "Иванова Анна" in client.get("/preschool/children/registry").get_data(as_text=True)


def test_child_create_edit_and_transfer_keep_data_consistent(app, client, make_user, login):
    year_id, first_id, second_id, child_id = _sample_contingent(app)
    login(make_user("ADMIN"))

    create = client.post(
        f"/preschool/children/registry?academic_year_id={year_id}",
        data={"last_name": "Петров", "first_name": "Пётр", "group_id": str(first_id), "personal_account": "П-1"},
    )
    assert create.status_code == 302
    with app.app_context():
        created = PreschoolChild.query.filter_by(last_name="Петров").one()
        assert created.group_id == first_id
        assert created.personal_account == "П-1"

    edit = client.post(
        f"/preschool/children/{child_id}/edit",
        data={"last_name": "Иванова", "first_name": "Анна", "group_id": str(first_id), "personal_account": "А-1", "reg_address": "Москва"},
    )
    assert edit.status_code == 302
    with app.app_context():
        child = db.session.get(PreschoolChild, child_id)
        assert child.personal_account == "А-1"
        assert child.reg_address == "Москва"
        assert child.group_id == first_id

    silent_transfer = client.post(
        f"/preschool/children/{child_id}/edit",
        data={"last_name": "Иванова", "first_name": "Анна", "group_id": str(second_id)},
    )
    assert silent_transfer.status_code == 302
    with app.app_context():
        assert db.session.get(PreschoolChild, child_id).group_id == first_id

    transfer = client.post(
        f"/preschool/children/{child_id}/movement",
        data={"movement_type": "transfer_group", "to_group_id": str(second_id), "movement_date": "2026-10-29", "basis": "Приказ"},
    )
    assert transfer.status_code == 302
    with app.app_context():
        child = db.session.get(PreschoolChild, child_id)
        assert child.group_id == second_id
        movement = PreschoolChildMovement.query.filter_by(child_id=child_id).one()
        assert movement.from_group_id == first_id
        assert movement.to_group_id == second_id
        assert movement.from_academic_year_id == year_id
        assert movement.to_academic_year_id == year_id
        assert movement.created_by_user_id is not None
        movement_id = movement.id
    assert "Иванова Анна" in client.get("/preschool/movements").get_data(as_text=True)

    undo = client.post(f"/preschool/movements/{movement_id}/delete")
    assert undo.status_code == 302
    with app.app_context():
        child = db.session.get(PreschoolChild, child_id)
        movement = db.session.get(PreschoolChildMovement, movement_id)
        assert child.group_id == first_id
        assert movement.reversed_at is not None
        assert movement.reversed_by_user_id is not None
    assert client.post(f"/preschool/movements/{movement_id}/delete").status_code == 409


def test_bulk_transfer_rejects_children_outside_selected_group(app, client, make_user, login):
    year_id, first_id, second_id, child_id = _sample_contingent(app)
    login(make_user("ADMIN"))
    response = client.post(
        "/preschool/movements/bulk",
        data={
            "academic_year_id": str(year_id),
            "source_group_id": str(second_id),
            "movement_type": "transfer_group",
            "target_group_id": str(first_id),
            "child_ids": [str(child_id)],
        },
    )
    assert response.status_code == 400
    with app.app_context():
        assert db.session.get(PreschoolChild, child_id).group_id == first_id
        assert PreschoolChildMovement.query.count() == 0


def test_bulk_year_transfer_is_visible_in_both_years(app, client, make_user, login):
    year_id, first_id, _, child_id = _sample_contingent(app)
    with app.app_context():
        next_year = AcademicYear(name="2027/2028")
        db.session.add(next_year)
        db.session.flush()
        target = PreschoolGroup(name="Школьная подготовка", academic_year_id=next_year.id)
        db.session.add(target)
        db.session.commit()
        next_year_id = next_year.id
        target_id = target.id
    login(make_user("SENIOR_EDUCATOR"))
    response = client.post(
        "/preschool/movements/bulk",
        data={
            "academic_year_id": str(year_id),
            "target_academic_year_id": str(next_year_id),
            "source_group_id": str(first_id),
            "movement_type": "year_transfer",
            "target_group_id": str(target_id),
            "child_ids": [str(child_id)],
        },
    )
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(PreschoolChild, child_id).group_id == target_id
        movement = PreschoolChildMovement.query.filter_by(child_id=child_id).one()
        assert movement.from_academic_year_id == year_id
        assert movement.to_academic_year_id == next_year_id
    assert "Иванова Анна" in client.get(f"/preschool/movements?academic_year_id={year_id}").get_data(as_text=True)
    assert "Иванова Анна" in client.get(f"/preschool/movements?academic_year_id={next_year_id}").get_data(as_text=True)


def test_old_child_days_pages_are_hidden_without_deleting_tables(app, client, make_user, login):
    login(make_user("ADMIN"))
    with app.app_context():
        inspector = db.inspect(db.engine)
        assert "preschool_attendance_record" in inspector.get_table_names()
    for path in ("/preschool/attendance", "/preschool/attendance/analytics"):
        response = client.get(path)
        assert response.status_code == 200
        assert "временно выведен из работы" in response.get_data(as_text=True)
        assert b"sp-workspace ws-workspace" in response.data
    assert client.post("/preschool/attendance", data={}).status_code == 403


def test_import_rejects_unsupported_or_damaged_excel(app, client, make_user, login):
    _sample_contingent(app)
    login(make_user("ADMIN"))
    for path in ("/preschool/children/import", "/preschool/representatives/import"):
        old_format = client.post(path, data={"file": (BytesIO(b"old"), "list.xls")}, content_type="multipart/form-data")
        assert old_format.status_code == 302
        damaged = client.post(path, data={"file": (BytesIO(b"damaged"), "list.xlsx")}, content_type="multipart/form-data")
        assert damaged.status_code == 302


def test_repeated_child_import_does_not_duplicate_existing_children(app, client, make_user, login):
    from openpyxl import Workbook

    _sample_contingent(app)
    login(make_user("ADMIN"))
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ФИО", "Группа"])
    sheet.append(["Иванова Анна", "Ромашка"])
    sheet.append(["Смирнова Мария", "Ромашка"])
    payload = BytesIO()
    workbook.save(payload)
    for _ in range(2):
        payload.seek(0)
        response = client.post(
            "/preschool/children/import",
            data={"file": (BytesIO(payload.getvalue()), "children.xlsx")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 200
    with app.app_context():
        assert PreschoolChild.query.filter_by(last_name="Иванова").count() == 1
        assert PreschoolChild.query.filter_by(last_name="Смирнова").count() == 1


def test_group_uses_common_year_and_building_and_cannot_change_year_silently(app, client, make_user, login):
    year_id, _, _, _ = _sample_contingent(app)
    with app.app_context():
        building = Building(name="Детский сад № 1")
        db.session.add(building)
        db.session.commit()
        building_id = building.id
    login(make_user("ADMIN"))
    create = client.post(
        "/preschool/groups",
        data={"name": "Звёздочка", "academic_year_id": str(year_id), "building_id": str(building_id)},
    )
    assert create.status_code == 302
    with app.app_context():
        group = PreschoolGroup.query.filter_by(name="Звёздочка").one()
        assert group.academic_year_id == year_id
        assert group.building_id == building_id
        group_id = group.id
        next_year = AcademicYear(name="2027/2028")
        db.session.add(next_year)
        db.session.commit()
        next_year_id = next_year.id
    edit = client.post(
        f"/preschool/groups/{group_id}/edit",
        data={"name": "Звёздочка", "academic_year_id": str(next_year_id), "building_id": str(building_id)},
    )
    assert edit.status_code == 302
    with app.app_context():
        assert db.session.get(PreschoolGroup, group_id).academic_year_id == year_id


def test_contingent_counts_only_active_children_and_registry_filters_status(app, client, make_user, login):
    year_id, _, _, child_id = _sample_contingent(app)
    login(make_user("ADMIN"))
    leaving = client.post(f"/preschool/children/{child_id}/movement", data={"movement_type": "leaving"})
    assert leaving.status_code == 302
    summary = client.get(f"/preschool/children?academic_year_id={year_id}").get_data(as_text=True)
    assert re.search(r'Воспитанников</span><strong class="ws-metric-value">0</strong>', summary)
    assert "Иванова Анна" not in client.get("/preschool/children/registry").get_data(as_text=True)
    assert "Иванова Анна" in client.get("/preschool/children/registry?status=left").get_data(as_text=True)
    with app.app_context():
        assert db.session.get(PreschoolChild, child_id).status == "left"
