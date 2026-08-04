from datetime import date

from app.core.extensions import db
from app.models import AcademicYear, Child, ChildEnrollment, SchoolClass


def test_children_registry_uses_compact_matrix_style(
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
        school_class = SchoolClass(
            academic_year=year,
            name="5А",
            grade=5,
            letter="А",
        )
        child = Child(
            last_name="Иванова",
            first_name="Анна",
            middle_name="Сергеевна",
            birth_date=date(2015, 4, 12),
            gender="Ж",
            education_form="Очная",
        )
        db.session.add_all([year, school_class, child])
        db.session.flush()
        db.session.add(ChildEnrollment(
            child_id=child.id,
            academic_year_id=year.id,
            school_class_id=school_class.id,
            status="ACTIVE",
        ))
        db.session.commit()
        class_id = school_class.id

    login(admin_id)
    response = client.get(f"/children?class_id={class_id}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "registry_matrix.css" in html
    assert 'class="registry-matrix children-list-table"' in html
    assert 'class="row g-2 registry-filter-panel"' in html
    assert "Иванова Анна Сергеевна" in html
    assert "registry-row-action" in html

    registry_paths = (
        "/registry/ovz",
        "/registry/vshu",
        "/registry/kdn",
        "/registry/az",
        f"/classes/{class_id}",
        "/classes",
    )
    for path in registry_paths:
        registry_response = client.get(path)
        registry_html = registry_response.get_data(as_text=True)
        assert registry_response.status_code == 200
        assert "registry-matrix" in registry_html
        assert "registry-matrix-card" in registry_html
