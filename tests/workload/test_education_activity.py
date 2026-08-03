from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.models import (
    AcademicYear,
    Child,
    ControlWork,
    Debt,
    Department,
    DepartmentSubject,
    DiagnosticSession,
    EducationActivity,
    EducationActivityAlias,
    EducationActivityDepartment,
    EducationPlan,
    EducationPlanLine,
    ExternalActivityMappingLog,
    OlympiadResult,
    OlympiadSubjectMapping,
    OrganizationSettings,
    Subject,
    TariffCycle,
    TariffVersion,
    TeacherLoad,
    TeacherMckoResult,
    User,
)
from app.services.education_activity_service import (
    AMBIGUOUS,
    MATCHED,
    UNMATCHED,
    assign_subject_activity,
    get_or_create_subject_activity,
    get_or_create_subject_with_activity,
    list_subject_activities,
    normalize_activity_code,
    normalize_activity_name,
    record_activity_mapping,
    replace_activity_departments,
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


def test_replacing_departments_preserves_existing_primary_department(app):
    with app.app_context():
        activity = _global_activity("PHYSICS", "Физика")
        first = Department(name="Альтернативная кафедра")
        primary = Department(name="Основная кафедра")
        third = Department(name="Третья кафедра")
        db.session.add_all((first, primary, third))
        db.session.flush()
        db.session.add_all((
            EducationActivityDepartment(
                education_activity_id=activity.id,
                department_id=first.id,
                is_primary=False,
            ),
            EducationActivityDepartment(
                education_activity_id=activity.id,
                department_id=primary.id,
                is_primary=True,
            ),
        ))
        db.session.commit()

        replace_activity_departments(
            activity,
            [first.id, primary.id, third.id],
        )
        db.session.commit()

        current_primary = next(
            link
            for link in activity.department_links
            if link.is_active and link.is_primary
        )
        assert current_primary.department_id == primary.id


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
        item = EducationActivity.query.filter_by(
            name="Практическая математика",
        ).one()
        assert item.code.startswith("CATALOG_")
        assert item.activity_kind == "COURSE"
        assert item.education_level == "OOO"


def test_catalog_sections_are_separate_and_sorted_alphabetically(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        _global_activity("RUSSIAN", "Русский язык")
        _global_activity("ALGEBRA", "Алгебра")
        extracurricular = _global_activity(
            "FUNCTIONAL_LITERACY",
            "Функциональная грамотность",
        )
        extracurricular.activity_kind = "EXTRACURRICULAR_COURSE"
        additional = _global_activity("ROBOTICS", "Робототехника")
        additional.activity_kind = "ADDITIONAL_PROGRAM"
        db.session.commit()
    login(user_id)

    subjects = client.get("/workload/catalog/?section=SUBJECTS")
    assert subjects.status_code == 200
    assert subjects.data.index("Алгебра".encode()) < subjects.data.index(
        "Русский язык".encode()
    )
    assert "Функциональная грамотность".encode() not in subjects.data
    assert "Робототехника".encode() not in subjects.data

    extracurricular_page = client.get(
        "/workload/catalog/?section=EXTRACURRICULAR"
    )
    assert "Функциональная грамотность".encode() in extracurricular_page.data
    assert "Алгебра".encode() not in extracurricular_page.data

    additional_page = client.get("/workload/catalog/?section=ADDITIONAL")
    assert "Робототехника".encode() in additional_page.data
    assert "Алгебра".encode() not in additional_page.data

    create_page = client.get(
        "/workload/catalog/new?section=EXTRACURRICULAR"
    )
    assert b'value="EXTRACURRICULAR_COURSE" selected' in create_page.data


def test_legacy_subject_registry_redirects_to_unified_catalog(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    login(make_user("ADMIN"))

    response = client.get("/subjects?q=математика")

    assert response.status_code == 302
    location = urlparse(response.headers["Location"])
    assert location.path == "/workload/catalog/"
    assert parse_qs(location.query) == {
        "section": ["SUBJECTS"],
        "q": ["математика"],
    }


def test_unified_catalog_saves_multiple_levels_departments_and_subject_link(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        first = Department(name="Кафедра начального образования")
        second = Department(name="Кафедра математики")
        db.session.add_all((first, second))
        db.session.commit()
        department_ids = [first.id, second.id]
    login(user_id)

    response = client.post(
        "/workload/catalog/new",
        data={
            "section": "SUBJECTS",
            "name": "Математическая грамотность",
            "short_name": "Мат. грамотность",
            "activity_kind": "SUBJECT",
            "education_levels": ["NOO", "OOO"],
            "department_ids": [str(item) for item in department_ids],
        },
    )

    assert response.status_code == 302
    assert "section=SUBJECTS" in response.headers["Location"]
    with app.app_context():
        activity = EducationActivity.query.filter_by(
            name="Математическая грамотность",
        ).one()
        assert activity.code.startswith("CATALOG_")
        assert activity.education_levels == ("NOO", "OOO")
        assert {
            link.department_id
            for link in activity.department_links
            if link.is_active
        } == set(department_ids)
        subject = Subject.query.filter_by(
            education_activity_id=activity.id,
        ).one()
        assert subject.name == activity.name
        assert subject.short_name == activity.short_name
        assert {
            link.department_id
            for link in DepartmentSubject.query.filter_by(
                education_activity_id=activity.id,
            ).all()
        } == set(department_ids)


def test_catalog_can_convert_legacy_subject_and_preserve_mcko_results(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    login(user_id)

    create_response = client.post(
        "/workload/catalog/new",
        data={
            "section": "SUBJECTS",
            "name": "Функциональная грамотность",
            "activity_kind": "SUBJECT",
            "education_levels": ["OOO"],
        },
    )
    assert create_response.status_code == 302

    with app.app_context():
        activity = EducationActivity.query.filter_by(
            name="Функциональная грамотность",
        ).one()
        subject = Subject.query.filter_by(
            education_activity_id=activity.id,
        ).one()
        db.session.add(TeacherMckoResult(
            teacher_id=user_id,
            subject_id=subject.id,
            education_activity_id=activity.id,
            level="Высокий",
        ))
        db.session.commit()
        activity_id = activity.id
        result_id = TeacherMckoResult.query.one().id

    edit_response = client.post(
        f"/workload/catalog/{activity_id}/edit",
        data={
            "section": "SUBJECTS",
            "name": "Функциональная грамотность",
            "activity_kind": "EXTRACURRICULAR_COURSE",
            "education_levels": ["OOO"],
        },
    )

    assert edit_response.status_code == 302, edit_response.data.decode()
    assert "section=EXTRACURRICULAR" in edit_response.headers["Location"]
    with app.app_context():
        activity = db.session.get(EducationActivity, activity_id)
        result = db.session.get(TeacherMckoResult, result_id)
        assert activity.activity_kind == "EXTRACURRICULAR_COURSE"
        assert activity.legacy_subject is not None
        assert result.education_activity_id == activity.id
        assert result.subject_id == activity.legacy_subject.id
        assert activity not in list_subject_activities(include_inactive=True)


def test_catalog_can_update_short_name_repeatedly(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    login(user_id)

    with app.app_context():
        activity = _global_activity(
            "FUNCTIONAL_LITERACY",
            "Функциональная грамотность",
        )
        db.session.commit()
        activity_id = activity.id

    for short_name in ("ФГ", "Функц. грамотность"):
        response = client.post(
            f"/workload/catalog/{activity_id}/edit",
            data={
                "section": "SUBJECTS",
                "name": "Функциональная грамотность",
                "short_name": short_name,
                "activity_kind": "SUBJECT",
                "education_levels": ["OOO"],
            },
        )
        assert response.status_code == 302, response.data.decode()

    with app.app_context():
        activity = db.session.get(EducationActivity, activity_id)
        assert activity.short_name == "Функц. грамотность"
        assert activity.legacy_subject.short_name == "Функц. грамотность"


def test_catalog_deletes_unused_activity_and_legacy_subject(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    login(user_id)

    with app.app_context():
        activity = _global_activity("TEMP_SUBJECT", "Свободный предмет")
        from app.services.education_activity_service import (
            sync_subject_from_activity,
        )
        sync_subject_from_activity(activity)
        db.session.commit()
        activity_id = activity.id
        subject_id = activity.legacy_subject.id

    response = client.post(
        f"/workload/catalog/{activity_id}/delete",
        data={"csrf_token": "test"},
    )

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(EducationActivity, activity_id) is None
        assert db.session.get(Subject, subject_id) is None


def test_catalog_refuses_to_delete_activity_with_historical_result(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    login(user_id)

    with app.app_context():
        activity = _global_activity("MCKO_SUBJECT", "Предмет с результатом")
        from app.services.education_activity_service import (
            sync_subject_from_activity,
        )
        subject = sync_subject_from_activity(activity)
        db.session.flush()
        db.session.add(TeacherMckoResult(
            teacher_id=user_id,
            subject_id=subject.id,
            education_activity_id=activity.id,
            level="Высокий",
        ))
        db.session.commit()
        activity_id = activity.id

    response = client.post(
        f"/workload/catalog/{activity_id}/delete",
        data={"csrf_token": "test"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/workload/catalog/{activity_id}"
    )
    with app.app_context():
        assert db.session.get(EducationActivity, activity_id) is not None


def test_catalog_kind_change_names_blocking_education_plan(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    login(user_id)

    with app.app_context():
        year = AcademicYear(
            name="2026/2027",
            is_current=True,
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
        )
        activity = _global_activity(
            "FUNCTIONAL_LITERACY",
            "Функциональная грамотность",
        )
        db.session.add(year)
        db.session.flush()
        cycle = TariffCycle(
            academic_year_id=year.id,
            code="2026-2027",
            name="Тарификация 2026/2027",
        )
        db.session.add(cycle)
        db.session.flush()
        version = TariffVersion(
            tariff_cycle_id=cycle.id,
            version_no=1,
        )
        db.session.add(version)
        db.session.flush()
        plan = EducationPlan(
            tariff_version_id=version.id,
            plan_kind="CURRICULUM",
            name="Основной план ООО",
            education_level="OOO",
            scope_code="OOO",
        )
        db.session.add(plan)
        db.session.flush()
        db.session.add(EducationPlanLine(
            education_plan_id=plan.id,
            education_activity_id=activity.id,
            component_kind="MANDATORY",
            weekly_hours=Decimal("1"),
        ))
        db.session.commit()
        activity_id = activity.id

    response = client.post(
        f"/workload/catalog/{activity_id}/edit",
        data={
            "section": "SUBJECTS",
            "name": "Функциональная грамотность",
            "activity_kind": "EXTRACURRICULAR_COURSE",
            "education_levels": ["OOO"],
        },
    )

    assert response.status_code == 200
    assert "Основной план ООО".encode() in response.data
    assert "Точные места использования указаны ниже".encode() in response.data
    with app.app_context():
        assert (
            db.session.get(EducationActivity, activity_id).activity_kind
            == "SUBJECT"
        )


def test_canonical_activity_assignment_keeps_transition_links_consistent(app):
    with app.app_context():
        activity = _global_activity("MATHEMATICS", "Математика")
        department = Department(name="Кафедра математики")
        teacher = User(username="canonical-subject-teacher", role="TEACHER")
        teacher.set_password("local-test-password")
        db.session.add_all((department, teacher))
        db.session.flush()

        department_link = DepartmentSubject(department_id=department.id)
        teacher_load = TeacherLoad(teacher_id=teacher.id, hours=5)
        mcko_result = TeacherMckoResult(teacher_id=teacher.id)
        diagnostic = DiagnosticSession(
            title="МЦКО по математике",
            diagnostic_type="MCKO",
        )
        for target in (
            department_link,
            teacher_load,
            mcko_result,
            diagnostic,
        ):
            assign_subject_activity(target, activity)
            db.session.add(target)
        db.session.commit()

        subject = Subject.query.filter_by(
            education_activity_id=activity.id,
        ).one()
        assert department_link.education_activity_id == activity.id
        assert department_link.subject_id == subject.id
        assert teacher_load.education_activity_id == activity.id
        assert teacher_load.subject_id == subject.id
        assert teacher_load.subject_name == activity.name
        assert mcko_result.education_activity_id == activity.id
        assert mcko_result.subject_id == subject.id
        assert diagnostic.education_activity_id == activity.id
        assert diagnostic.subject == activity.name


def test_academic_consumers_share_one_canonical_subject(app):
    with app.app_context():
        activity = _global_activity("MATHEMATICS", "Математика")
        db.session.flush()

        control_work = ControlWork(theme="Входная диагностика")
        debt = Debt(child_id=1)
        olympiad_result = OlympiadResult(
            academic_year_id=1,
            child_id=1,
            stage="школьный",
        )
        olympiad_mapping = OlympiadSubjectMapping(
            olympiad_subject_name="Математика",
        )

        for target in (
            control_work,
            debt,
            olympiad_result,
            olympiad_mapping,
        ):
            assign_subject_activity(target, activity)

        subject = Subject.query.filter_by(
            education_activity_id=activity.id,
        ).one()
        assert {
            control_work.education_activity_id,
            debt.education_activity_id,
            olympiad_result.education_activity_id,
            olympiad_mapping.education_activity_id,
        } == {activity.id}
        assert {
            control_work.subject_id,
            debt.subject_id,
            olympiad_result.subject_id,
            olympiad_mapping.subject_id,
        } == {subject.id}
        assert control_work.subject_name == activity.name
        assert debt.subject_name == activity.name
        assert olympiad_result.resolved_subject_name == activity.name


def test_olympiad_mapping_uses_canonical_linked_subject_ids(app):
    with app.app_context():
        mathematics = _global_activity("MATHEMATICS", "Математика")
        geometry = _global_activity("GEOMETRY", "Геометрия")
        mapping = OlympiadSubjectMapping(
            olympiad_subject_name="Математика",
            linked_education_activity_ids=f"{geometry.id},{mathematics.id}",
        )
        assign_subject_activity(mapping, mathematics)

        assert mapping.linked_education_activity_id_list() == [
            mathematics.id,
            geometry.id,
        ]


def test_subject_activity_list_is_the_only_alphabetical_selector_source(app):
    with app.app_context():
        _global_activity("RUSSIAN", "Русский язык")
        _global_activity("ENGLISH", "Английский язык")
        _global_activity("ALGEBRA", "Алгебра")
        course = _global_activity("ROBOTICS", "Робототехника")
        course.activity_kind = "ADDITIONAL_PROGRAM"
        db.session.commit()

        assert [item.name for item in list_subject_activities()] == [
            "Алгебра",
            "Английский язык",
            "Русский язык",
        ]


def test_get_or_create_subject_activity_prefers_canonical_catalog(app):
    with app.app_context():
        activity = _global_activity("CHEMISTRY", "Химия")
        db.session.commit()

        selected, created = get_or_create_subject_activity("  Химия  ")
        db.session.commit()

        assert created is False
        assert selected.id == activity.id
        assert EducationActivity.query.filter_by(
            activity_kind="SUBJECT",
            name="Химия",
        ).count() == 1
        assert Subject.query.filter_by(
            education_activity_id=activity.id,
        ).count() == 1


def test_diagnostic_form_uses_canonical_activity_selector(
    app, client, make_user, login
):
    user_id = make_user("ADMIN")
    with app.app_context():
        _global_activity("PHYSICS", "Физика")
        db.session.commit()
    login(user_id)

    response = client.get("/diagnostics/new")

    assert response.status_code == 200
    assert b'name="education_activity_id"' in response.data
    assert b'name="subject"' not in response.data
    assert "Физика".encode() in response.data


def test_diagnostic_list_filters_by_canonical_subject_id(
    app, client, make_user, login
):
    user_id = make_user("ADMIN")
    with app.app_context():
        physics = _global_activity("PHYSICS", "Физика")
        chemistry = _global_activity("CHEMISTRY", "Химия")
        physics_session = DiagnosticSession(
            title="Диагностика по физике",
            diagnostic_type="MCKO",
        )
        chemistry_session = DiagnosticSession(
            title="Диагностика по химии",
            diagnostic_type="MCKO",
        )
        assign_subject_activity(physics_session, physics)
        assign_subject_activity(chemistry_session, chemistry)
        db.session.add_all((physics_session, chemistry_session))
        db.session.commit()
        physics_id = physics.id

    login(user_id)
    response = client.get(f"/diagnostics/?subject_id={physics_id}")

    assert response.status_code == 200
    assert b'name="subject_id"' in response.data
    assert "Диагностика по физике".encode() in response.data
    assert "Диагностика по химии".encode() not in response.data


def test_legacy_debt_route_uses_existing_canonical_subject(
    app, client, make_user, login
):
    user_id = make_user("ADMIN")
    with app.app_context():
        child = Child(last_name="Иванов", first_name="Иван")
        activity = _global_activity("BIOLOGY", "Биология")
        db.session.add(child)
        db.session.commit()
        child_id = child.id
        activity_id = activity.id

    login(user_id)
    response = client.post(
        f"/children/{child_id}/debt/new",
        data={"education_activity_id": activity_id},
    )

    assert response.status_code == 302
    with app.app_context():
        debt = Debt.query.filter_by(child_id=child_id).one()
        assert debt.education_activity_id == activity_id


def test_teacher_cannot_manage_catalog_even_when_write_flag_is_enabled(
    app, client, make_user, login
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    login(make_user("TEACHER"))

    response = client.get("/workload/catalog/new")

    assert response.status_code == 403
