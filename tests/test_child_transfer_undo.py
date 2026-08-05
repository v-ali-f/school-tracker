from datetime import date, datetime

from app.core.extensions import db
from app.models import (
    AcademicYear,
    Child,
    ChildEnrollment,
    ChildEvent,
    ChildMovement,
    ChildTransferHistory,
    SchoolClass,
)


def _build_erroneous_transfer_chain():
    year_2025 = AcademicYear(
        name="2025/2026",
        start_date=date(2025, 9, 1),
        end_date=date(2026, 8, 31),
        is_current=True,
    )
    year_2026 = AcademicYear(
        name="2026/2027",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 8, 31),
    )
    db.session.add_all([year_2025, year_2026])
    db.session.flush()

    class_1m = SchoolClass(
        academic_year_id=year_2025.id,
        name="1М",
        grade=1,
        letter="М",
    )
    class_2z = SchoolClass(
        academic_year_id=year_2025.id,
        name="2З",
        grade=2,
        letter="З",
    )
    class_2m = SchoolClass(
        academic_year_id=year_2026.id,
        name="2М",
        grade=2,
        letter="М",
    )
    child = Child(last_name="Иванов", first_name="Иван")
    db.session.add_all([class_1m, class_2z, class_2m, child])
    db.session.flush()

    first_at = datetime(2026, 4, 29, 8, 0)
    promotion_at = datetime(2026, 8, 3, 9, 0)
    manual_at = datetime(2026, 8, 5, 10, 0)
    source = ChildEnrollment(
        child_id=child.id,
        academic_year_id=year_2025.id,
        school_class_id=class_1m.id,
        status="PROMOTED",
        enrolled_at=first_at,
        ended_at=promotion_at,
    )
    promoted_target = ChildEnrollment(
        child_id=child.id,
        academic_year_id=year_2026.id,
        school_class_id=class_2m.id,
        status="ACTIVE",
        enrolled_at=promotion_at,
    )
    # This reproduces the legacy child-card class change that did not create
    # ChildTransferHistory.
    manual_target = ChildEnrollment(
        child_id=child.id,
        academic_year_id=year_2025.id,
        school_class_id=class_2z.id,
        status="ACTIVE",
        enrolled_at=manual_at,
    )
    transfer = ChildTransferHistory(
        child_id=child.id,
        from_academic_year_id=year_2025.id,
        to_academic_year_id=year_2026.id,
        from_class_id=class_1m.id,
        to_class_id=class_2m.id,
        transfer_type="PROMOTED",
        transfer_date=promotion_at.date(),
        created_at=promotion_at,
    )
    db.session.add_all([
        source,
        promoted_target,
        manual_target,
        transfer,
    ])
    db.session.commit()
    return {
        "child_id": child.id,
        "source_id": source.id,
        "promoted_target_id": promoted_target.id,
        "manual_target_id": manual_target.id,
        "transfer_id": transfer.id,
    }


def test_admin_undoes_child_transfers_from_latest_to_oldest(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        ids = _build_erroneous_transfer_chain()
    login(admin_id)

    out_of_order = client.post(
        f"/children/{ids['child_id']}/enrollments/"
        f"{ids['promoted_target_id']}/undo",
    )
    assert out_of_order.status_code == 302
    with app.app_context():
        assert db.session.get(
            ChildEnrollment,
            ids["promoted_target_id"],
        ).ended_at is None

    first_undo = client.post(
        f"/children/{ids['child_id']}/enrollments/"
        f"{ids['manual_target_id']}/undo",
    )
    assert first_undo.status_code == 302
    with app.app_context():
        source = db.session.get(ChildEnrollment, ids["source_id"])
        manual_target = db.session.get(
            ChildEnrollment,
            ids["manual_target_id"],
        )
        original_transfer = db.session.get(
            ChildTransferHistory,
            ids["transfer_id"],
        )
        assert source.status == "ACTIVE"
        assert source.ended_at is None
        assert manual_target.status == "CANCELLED"
        assert manual_target.ended_at is not None
        assert original_transfer.reversed_at is None
        legacy_audit = ChildTransferHistory.query.filter_by(
            to_class_id=manual_target.school_class_id,
        ).one()
        assert legacy_audit.reversed_at is not None

    second_undo = client.post(
        f"/children/{ids['child_id']}/enrollments/"
        f"{ids['promoted_target_id']}/undo",
    )
    assert second_undo.status_code == 302
    with app.app_context():
        source = db.session.get(ChildEnrollment, ids["source_id"])
        promoted_target = db.session.get(
            ChildEnrollment,
            ids["promoted_target_id"],
        )
        original_transfer = db.session.get(
            ChildTransferHistory,
            ids["transfer_id"],
        )
        assert source.status == "ACTIVE"
        assert source.ended_at is None
        assert promoted_target.status == "CANCELLED"
        assert promoted_target.ended_at is not None
        assert original_transfer.reversed_at is not None
        assert original_transfer.reversed_by == admin_id
        assert ChildMovement.query.filter_by(
            child_id=ids["child_id"],
            movement_type="correction",
        ).count() == 2
        assert ChildEvent.query.filter_by(
            child_id=ids["child_id"],
            event_type="TRANSFER_UNDO",
        ).count() == 2


def test_transfer_undo_is_admin_only(
    app,
    client,
    make_user,
    login,
):
    teacher_id = make_user("TEACHER")
    with app.app_context():
        ids = _build_erroneous_transfer_chain()
    login(teacher_id)

    response = client.post(
        f"/children/{ids['child_id']}/enrollments/"
        f"{ids['manual_target_id']}/undo",
    )

    assert response.status_code == 403


def test_manual_child_card_transfer_writes_complete_audit(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        year = AcademicYear(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
            is_current=True,
        )
        db.session.add(year)
        db.session.flush()
        source_class = SchoolClass(
            academic_year_id=year.id,
            name="2А",
            grade=2,
            letter="А",
        )
        target_class = SchoolClass(
            academic_year_id=year.id,
            name="2Б",
            grade=2,
            letter="Б",
        )
        child = Child(last_name="Петров", first_name="Пётр")
        db.session.add_all([source_class, target_class, child])
        db.session.flush()
        source = ChildEnrollment(
            child_id=child.id,
            academic_year_id=year.id,
            school_class_id=source_class.id,
            status="ACTIVE",
        )
        db.session.add(source)
        db.session.commit()
        child_id = child.id
        source_id = source.id
        target_class_id = target_class.id
    login(admin_id)

    response = client.post(
        f"/children/{child_id}/transfer",
        data={
            "school_class_id": target_class_id,
            "note": "Исправление распределения",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        source = db.session.get(ChildEnrollment, source_id)
        target = ChildEnrollment.query.filter_by(
            child_id=child_id,
            school_class_id=target_class_id,
            status="ACTIVE",
        ).one()
        history = ChildTransferHistory.query.filter_by(
            child_id=child_id,
            to_class_id=target_class_id,
        ).one()
        assert source.status == "TRANSFERRED"
        assert source.ended_at is not None
        assert history.transfer_type == "MANUAL"
        assert history.reversed_at is None
        assert ChildMovement.query.filter_by(
            child_id=child_id,
            from_class_id=source.school_class_id,
            to_class_id=target_class_id,
            movement_type="transfer",
        ).count() == 1

    card = client.get(f"/children/{child_id}")
    assert card.status_code == 200
    assert "Отменить последнее изменение" in card.get_data(as_text=True)


def test_expulsion_closes_future_enrollment_and_admin_can_undo_it(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        current_year = AcademicYear(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 8, 31),
            is_current=True,
        )
        next_year = AcademicYear(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
        )
        db.session.add_all([current_year, next_year])
        db.session.flush()
        future_class = SchoolClass(
            academic_year_id=next_year.id,
            name="3Л",
            grade=3,
            letter="Л",
        )
        child = Child(last_name="Сидоров", first_name="Семён")
        db.session.add_all([future_class, child])
        db.session.flush()
        enrollment = ChildEnrollment(
            child_id=child.id,
            academic_year_id=next_year.id,
            school_class_id=future_class.id,
            status="ACTIVE",
            enrolled_at=datetime(2026, 8, 3, 11, 21),
        )
        db.session.add(enrollment)
        db.session.commit()
        child_id = child.id
        class_id = future_class.id
        enrollment_id = enrollment.id
    login(admin_id)

    expelled = client.post(
        f"/children/{child_id}/expel",
        data={"note": "Ошибочное действие"},
    )
    assert expelled.status_code == 302
    with app.app_context():
        enrollment = db.session.get(ChildEnrollment, enrollment_id)
        child = db.session.get(Child, child_id)
        assert enrollment.status == "EXPELLED"
        assert enrollment.ended_at is not None
        assert child.status == "EXPELLED"
        assert ChildEvent.query.filter_by(
            child_id=child_id,
            event_type="EXPEL",
        ).count() == 1
        assert ChildTransferHistory.query.filter_by(
            child_id=child_id,
            transfer_type="EXPELLED",
        ).count() == 1

    class_page = client.get(f"/classes/{class_id}")
    assert "Сидоров Семён".encode() not in class_page.data
    card = client.get(f"/children/{child_id}")
    assert "Отменить отчисление".encode() in card.data
    assert "data-bs-target=\"#expelModal\"".encode() not in card.data

    repeated = client.post(f"/children/{child_id}/expel")
    assert repeated.status_code == 302
    with app.app_context():
        assert ChildEvent.query.filter_by(
            child_id=child_id,
            event_type="EXPEL",
        ).count() == 1

    restored = client.post(f"/children/{child_id}/expel/undo")
    assert restored.status_code == 302
    with app.app_context():
        enrollment = db.session.get(ChildEnrollment, enrollment_id)
        child = db.session.get(Child, child_id)
        assert enrollment.status == "ACTIVE"
        assert enrollment.ended_at is None
        assert child.status == "ACTIVE"
        assert ChildEvent.query.filter_by(
            child_id=child_id,
            event_type="EXPEL_UNDO",
        ).count() == 1
        history = ChildTransferHistory.query.filter_by(
            child_id=child_id,
            transfer_type="EXPELLED",
        ).one()
        assert history.reversed_at is not None

    restored_class_page = client.get(f"/classes/{class_id}")
    assert "Сидоров Семён".encode() in restored_class_page.data
    registry = client.get("/registry/expelled")
    assert "Сидоров Семён".encode() not in registry.data


def test_legacy_expel_event_hides_active_enrollment_until_undo(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        year = AcademicYear(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
            is_current=True,
        )
        db.session.add(year)
        db.session.flush()
        school_class = SchoolClass(
            academic_year_id=year.id,
            name="3Л",
            grade=3,
            letter="Л",
        )
        child = Child(last_name="Старая", first_name="Запись")
        db.session.add_all([school_class, child])
        db.session.flush()
        enrollment = ChildEnrollment(
            child_id=child.id,
            academic_year_id=year.id,
            school_class_id=school_class.id,
            status="ACTIVE",
            enrolled_at=datetime(2026, 8, 3, 11, 21),
        )
        event = ChildEvent(
            child_id=child.id,
            author_id=admin_id,
            event_type="EXPEL",
            from_class="3Л",
            reason="Старое ошибочное отчисление",
            created_at=datetime(2026, 8, 5, 11, 23),
        )
        db.session.add_all([enrollment, event])
        db.session.commit()
        child_id = child.id
        class_id = school_class.id
        enrollment_id = enrollment.id
    login(admin_id)

    hidden_page = client.get(f"/classes/{class_id}")
    assert "Старая Запись".encode() not in hidden_page.data
    registry = client.get("/registry/expelled")
    assert "Старая Запись".encode() in registry.data

    response = client.post(f"/children/{child_id}/expel/undo")
    assert response.status_code == 302
    with app.app_context():
        enrollment = db.session.get(ChildEnrollment, enrollment_id)
        assert enrollment.status == "ACTIVE"
        assert enrollment.ended_at is None
        assert ChildEvent.query.filter_by(
            child_id=child_id,
            event_type="EXPEL_UNDO",
        ).count() == 1

    visible_page = client.get(f"/classes/{class_id}")
    assert "Старая Запись".encode() in visible_page.data


def test_children_registry_shows_current_academic_year(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        ids = _build_erroneous_transfer_chain()
        assert ids["child_id"]
    login(admin_id)

    response = client.get("/children?grade=2&per_page=20")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Учебный год:" in page
    assert "2025/2026" in page
