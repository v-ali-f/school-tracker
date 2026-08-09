from datetime import date

from app.core.extensions import db
from app.models import (
    Department,
    DepartmentLeader,
    TeacherAttestation,
    TeacherLoad,
    TeacherProfessionalRecordChange,
    User,
)


def test_admin_registry_lists_teacher_without_hire_date_and_hub_link(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    make_user("TEACHER")
    login(admin_id)

    hub = client.get("/hub/registries")
    registry = client.get("/professional-registers/attestations")

    assert hub.status_code == 200
    assert "Аттестация педагогов" in hub.get_data(as_text=True)
    assert registry.status_code == 200
    html = registry.get_data(as_text=True)
    assert "Не указана дата приёма" in html
    assert "registry-table-scroll" in html
    assert "professional_registry.js" in html
    assert "Добавить аттестацию" in html


def test_deputy_creates_edits_and_archives_attestation_with_history(
    app,
    client,
    make_user,
    login,
):
    deputy_id = make_user("DEPUTY_DIRECTOR")
    teacher_id = make_user("TEACHER")
    login(deputy_id)

    created = client.post(
        "/professional-registers/attestations/new",
        data={
            "teacher_id": teacher_id,
            "employment_start_date": "2024-09-01",
            "position_title": "Учитель",
            "category": "POSITION_COMPLIANCE",
            "decision_date": "2026-07-01",
            "order_number": "АТ-10",
        },
    )
    assert created.status_code == 302

    with app.app_context():
        teacher = db.session.get(User, teacher_id)
        record = TeacherAttestation.query.one()
        assert teacher.employment_start_date == date(2024, 9, 1)
        assert record.valid_until == date(2028, 7, 1)
        assert record.is_indefinite is False
        assert record.created_by_user_id == deputy_id
        assert record.entry_source == "ADMINISTRATION"
        record_id = record.id

    edited = client.post(
        f"/professional-registers/attestations/{record_id}/edit",
        data={
            "teacher_id": teacher_id,
            "employment_start_date": "2024-09-01",
            "position_title": "Учитель",
            "category": "HIGHEST",
            "decision_date": "2026-08-01",
            "term_type": "INDEFINITE",
            "order_number": "АТ-11",
        },
    )
    archived = client.post(
        f"/professional-registers/attestations/{record_id}/archive"
    )
    assert edited.status_code == 302
    assert archived.status_code == 302

    with app.app_context():
        record = db.session.get(TeacherAttestation, record_id)
        assert record.category == "HIGHEST"
        assert record.is_indefinite is True
        assert record.valid_until is None
        assert record.is_archived is True
        changes = TeacherProfessionalRecordChange.query.order_by(
            TeacherProfessionalRecordChange.id
        ).all()
        assert [item.change_kind for item in changes] == [
            "CREATED",
            "UPDATED",
            "ARCHIVED",
        ]
        assert all(item.changed_by_user_id == deputy_id for item in changes)


def test_methodist_can_view_but_cannot_manage_attestations(
    app,
    client,
    make_user,
    login,
):
    methodist_id = make_user("METHODIST")
    login(methodist_id)

    assert client.get("/professional-registers/attestations").status_code == 200
    assert client.get("/professional-registers/attestations/new").status_code == 403


def test_department_head_sees_attestation_only_for_own_department(
    app,
    client,
    make_user,
    login,
):
    head_id = make_user("DEPARTMENT_HEAD")
    own_teacher_id = make_user("TEACHER")
    other_teacher_id = make_user("TEACHER")
    with app.app_context():
        db.session.get(User, own_teacher_id).last_name = "Свой"
        db.session.get(User, other_teacher_id).last_name = "Чужой"
        own_department = Department(name="Своя кафедра")
        other_department = Department(name="Другая кафедра")
        db.session.add_all([own_department, other_department])
        db.session.flush()
        db.session.add_all([
            DepartmentLeader(department_id=own_department.id, user_id=head_id),
            TeacherLoad(
                teacher_id=own_teacher_id,
                department_id=own_department.id,
                subject_name="Математика",
                hours=4,
            ),
            TeacherLoad(
                teacher_id=other_teacher_id,
                department_id=other_department.id,
                subject_name="Физика",
                hours=4,
            ),
        ])
        db.session.commit()

    login(head_id)
    response = client.get("/professional-registers/attestations")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Свой Пользователь" in html
    assert "Чужой Пользователь" not in html
    assert "Своя кафедра" in html
    assert "Другая кафедра" not in html
    assert client.get("/professional-registers/attestations/new").status_code == 403
