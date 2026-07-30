from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.models import (
    Department,
    EducationActivity,
    EducationActivityAlias,
    EducationActivityDepartment,
    ExternalActivityMappingLog,
    OrganizationSettings,
    Subject,
)
from app.services.education_activity_service import (
    AMBIGUOUS,
    MATCHED,
    UNMATCHED,
    get_or_create_subject_with_activity,
    normalize_activity_code,
    normalize_activity_name,
    record_activity_mapping,
    resolve_education_activity,
)


def _global_activity(code, name, short_name=None):
    item = EducationActivity(
        code=code,
        name=name,
        short_name=short_name,
        activity_kind="SUBJECT",
        is_global=True,
        is_tariffable=True,
        is_active=True,
    )
    db.session.add(item)
    db.session.flush()
    return item


def test_normalization_is_stable_for_import_names():
    assert normalize_activity_name("  Русский  язык (база) ") == "русский язык база"
    assert normalize_activity_name("ВСЁ о Ёлках") == "все о елках"
    assert normalize_activity_code("  course-math 01 ") == "COURSE_MATH_01"


def test_legacy_subject_creation_also_creates_catalog_activity(app):
    with app.app_context():
        subject, created = get_or_create_subject_with_activity(
            "Математика",
            short_name="Мат.",
        )
        db.session.commit()

        assert created is True
        assert subject.education_activity_id is not None
        assert subject.education_activity.code == f"LEGACY_SUBJECT_{subject.id}"
        assert subject.education_activity.activity_kind == "SUBJECT"

        same_subject, created_again = get_or_create_subject_with_activity("математика")
        assert created_again is False
        assert same_subject.id == subject.id
        assert EducationActivity.query.count() == 1


def test_match_by_code_name_and_short_name(app):
    with app.app_context():
        activity = _global_activity("MATH", "Математика", "Мат.")
        db.session.commit()

        by_code = resolve_education_activity("math")
        by_name = resolve_education_activity("МАТЕМАТИКА")
        by_short_name = resolve_education_activity("Мат.")

        assert by_code.status == MATCHED
        assert by_code.activity.id == activity.id
        assert by_code.method == "CODE"
        assert by_name.method == "CANONICAL_NAME"
        assert by_short_name.activity.id == activity.id


def test_alias_is_limited_by_source_module(app):
    with app.app_context():
        activity = _global_activity("SOCIAL_STUDIES", "Обществознание")
        db.session.add(EducationActivityAlias(
            education_activity_id=activity.id,
            alias="Общество",
            normalized_alias=normalize_activity_name("Общество"),
            source_module="OLYMPIAD",
            source_system="",
        ))
        db.session.commit()

        olympiad_match = resolve_education_activity(
            "общество",
            source_module="OLYMPIAD",
        )
        mcko_match = resolve_education_activity(
            "общество",
            source_module="MCKO",
        )

        assert olympiad_match.status == MATCHED
        assert olympiad_match.activity.id == activity.id
        assert olympiad_match.method == "ALIAS"
        assert mcko_match.status == UNMATCHED


def test_unknown_name_is_not_created_automatically(app):
    with app.app_context():
        before_count = EducationActivity.query.count()

        match = resolve_education_activity("Неизвестная дисциплина")

        assert match.status == UNMATCHED
        assert EducationActivity.query.count() == before_count


def test_ambiguous_name_requires_manual_resolution(app):
    with app.app_context():
        first = _global_activity("ECONOMICS_1", "Экономика")
        second = _global_activity("ECONOMICS_2", "Экономика")
        db.session.commit()

        match = resolve_education_activity("Экономика")

        assert match.status == AMBIGUOUS
        assert {item.id for item in match.candidates} == {first.id, second.id}
        assert match.activity is None


def test_organization_specific_code_has_priority_over_global(app):
    with app.app_context():
        organization = OrganizationSettings(short_name="Тестовая школа", is_active=True)
        db.session.add(organization)
        db.session.flush()
        global_activity = _global_activity("MATH", "Математика")
        local_activity = EducationActivity(
            organization_id=organization.id,
            code="MATH",
            name="Математика школы",
            activity_kind="SUBJECT",
            is_global=False,
            is_tariffable=True,
            is_active=True,
        )
        db.session.add(local_activity)
        db.session.commit()

        local_match = resolve_education_activity(
            "MATH",
            organization_id=organization.id,
        )
        global_match = resolve_education_activity("MATH")

        assert local_match.activity.id == local_activity.id
        assert global_match.activity.id == global_activity.id


def test_mapping_decision_is_recorded_for_reproducible_import(app):
    with app.app_context():
        activity = _global_activity("PHYSICS", "Физика")
        db.session.commit()
        match = resolve_education_activity("Физика", source_module="MCKO")

        log = record_activity_mapping(
            source_value="Физика",
            source_module="MCKO",
            source_system="PDF",
            match=match,
            import_batch_type="diagnostic_import_batch",
            import_batch_id=42,
        )
        db.session.commit()

        stored = db.session.get(ExternalActivityMappingLog, log.id)
        assert stored.education_activity_id == activity.id
        assert stored.mapping_method == "CANONICAL_NAME"
        assert stored.confidence == Decimal("1.0000")
        assert stored.normalized_value == "физика"


def test_department_link_cannot_be_duplicated_without_period(app):
    with app.app_context():
        activity = _global_activity("CHEMISTRY", "Химия")
        department = Department(name="Кафедра естественных наук")
        db.session.add(department)
        db.session.flush()
        db.session.add(EducationActivityDepartment(
            education_activity_id=activity.id,
            department_id=department.id,
        ))
        db.session.commit()

        db.session.add(EducationActivityDepartment(
            education_activity_id=activity.id,
            department_id=department.id,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_activity_has_only_one_current_primary_department(app):
    with app.app_context():
        activity = _global_activity("PHYSICS", "Физика")
        first = Department(name="Кафедра естественных наук")
        second = Department(name="Кафедра точных наук")
        db.session.add_all((first, second))
        db.session.flush()
        db.session.add(EducationActivityDepartment(
            education_activity_id=activity.id,
            department_id=first.id,
            is_primary=True,
        ))
        db.session.commit()

        db.session.add(EducationActivityDepartment(
            education_activity_id=activity.id,
            department_id=second.id,
            is_primary=True,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_catalog_write_requires_separate_feature_flag(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    login(make_user("ADMIN"))

    list_response = client.get("/workload/catalog/")
    create_response = client.get("/workload/catalog/new")

    assert list_response.status_code == 200
    assert create_response.status_code == 404


def test_administrator_can_create_catalog_item_when_write_is_enabled(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    login(make_user("ADMIN"))

    response = client.post(
        "/workload/catalog/new",
        data={
            "code": "PRACTICAL_MATH",
            "name": "Практическая математика",
            "activity_kind": "COURSE",
            "education_level": "OOO",
            "is_tariffable": "1",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        item = EducationActivity.query.filter_by(code="PRACTICAL_MATH").one()
        assert item.activity_kind == "COURSE"
        assert item.education_level == "OOO"


def test_teacher_cannot_manage_catalog_even_when_write_flag_is_enabled(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    login(make_user("TEACHER"))

    response = client.get("/workload/catalog/new")

    assert response.status_code == 403
