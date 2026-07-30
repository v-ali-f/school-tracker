from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.extensions import db
from app.models import (
    AcademicYear,
    Building,
    Child,
    ChildEnrollment,
    EducationActivity,
    EducationPlan,
    EducationPlanBinding,
    EducationPlanLine,
    EducationPlanLineScope,
    PopulationSnapshot,
    PopulationSnapshotClass,
    PopulationSnapshotEnrollment,
    SchoolClass,
    TariffVersion,
    TeachingGroup,
    TeachingGroupHistory,
)
from app.services.education_plan_service import (
    ensure_draft_tariff_version,
    line_scope_key,
    plan_scope_code,
)
from app.services.education_plan_binding_service import (
    class_plan_allocations,
    replace_plan_binding_members,
)
from app.services.teaching_group_service import (
    GroupValidationError,
    build_population_snapshot,
    change_group_status,
    group_coverage,
    population_registry_status,
    validate_group_sources,
)


def _child(last_name, first_name):
    child = Child(last_name=last_name, first_name=first_name)
    db.session.add(child)
    db.session.flush()
    return child


def _group_context(user_id):
    year = AcademicYear(
        name="2026/2027",
        is_current=True,
        start_date=date(2026, 9, 1),
        end_date=date(2027, 8, 31),
    )
    building = Building(name="Главное здание", short_name="ГЗ")
    db.session.add_all([year, building])
    db.session.flush()

    class_a = SchoolClass(
        academic_year_id=year.id,
        building_id=building.id,
        name="5А",
        grade=5,
        letter="А",
    )
    class_b = SchoolClass(
        academic_year_id=year.id,
        building_id=building.id,
        name="5Б",
        grade=5,
        letter="Б",
    )
    db.session.add_all([class_a, class_b])
    db.session.flush()

    children = [
        _child("Иванов", "Иван"),
        _child("Петрова", "Анна"),
        _child("Сидоров", "Олег"),
    ]
    for child, school_class in (
        (children[0], class_a),
        (children[1], class_a),
        (children[2], class_b),
    ):
        db.session.add(ChildEnrollment(
            child_id=child.id,
            academic_year_id=year.id,
            school_class_id=school_class.id,
            status="ACTIVE",
            enrolled_at=datetime(2026, 9, 1),
        ))

    activity = EducationActivity(
        code="MATH",
        name="Математика",
        activity_kind="SUBJECT",
        is_global=True,
        is_tariffable=True,
        is_active=True,
    )
    db.session.add(activity)
    db.session.flush()
    _, version = ensure_draft_tariff_version(year, user_id=user_id)
    plan = EducationPlan(
        tariff_version_id=version.id,
        plan_kind="CURRICULUM",
        name="Основной учебный план",
        education_level="OOO",
        building_id=building.id,
        scope_code=plan_scope_code("OOO", building.id),
        status="DRAFT",
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    db.session.add(plan)
    db.session.flush()
    line = EducationPlanLine(
        education_plan_id=plan.id,
        education_activity_id=activity.id,
        component_kind="MANDATORY",
        weekly_hours=Decimal("5"),
        weeks_count=Decimal("34"),
        annual_hours=Decimal("170"),
        requires_division=True,
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    db.session.add(line)
    db.session.flush()
    db.session.add(EducationPlanLineScope(
        education_plan_line_id=line.id,
        scope_kind="GRADE",
        grade=5,
        building_id=building.id,
        scope_key=line_scope_key(
            "GRADE",
            grade=5,
            building_id=building.id,
        ),
    ))
    db.session.commit()
    return {
        "year_id": year.id,
        "building_id": building.id,
        "version_id": version.id,
        "plan_line_id": line.id,
    }


def _snapshot(user_id, version_id):
    version = db.session.get(TariffVersion, version_id)
    snapshot = build_population_snapshot(
        version,
        user_id=user_id,
        snapshot_date=date(2026, 9, 1),
    )
    db.session.commit()
    return snapshot.id


def _group_form(context, class_ids, member_ids=(), **overrides):
    data = {
        "source_plan_line_id": str(context["plan_line_id"]),
        "group_type": "SUBGROUP",
        "code": "MATH_5A_1",
        "name": "Математика 5А, группа 1",
        "composition_mode": "PERSONAL",
        "planned_size": "1",
        "valid_from": "2026-09-01",
        "valid_to": "2027-05-31",
        "building_id": str(context["building_id"]),
        "snapshot_class_ids": [str(item) for item in class_ids],
        "snapshot_enrollment_ids": [str(item) for item in member_ids],
    }
    data.update(overrides)
    return data


def test_population_snapshot_preserves_classes_and_students(app, make_user):
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])

        snapshot = db.session.get(PopulationSnapshot, snapshot_id)
        assert snapshot.revision_no == 1
        assert len(snapshot.classes) == 2
        assert PopulationSnapshotEnrollment.query.count() == 3
        assert sorted(item.student_count for item in snapshot.classes) == [1, 2]


def test_snapshot_refresh_keeps_previous_revision(app, make_user):
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        first_id = _snapshot(user_id, context["version_id"])
        second_id = _snapshot(user_id, context["version_id"])

        first = db.session.get(PopulationSnapshot, first_id)
        second = db.session.get(PopulationSnapshot, second_id)
        assert first.status == "SUPERSEDED"
        assert second.status == "CURRENT"
        assert second.revision_no == 2


def test_class_students_can_be_split_between_two_curricula(app, make_user):
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        snapshot = db.session.get(PopulationSnapshot, snapshot_id)
        snapshot_class = next(
            item
            for item in snapshot.classes
            if item.name_snapshot == "5А"
        )
        first_plan = db.session.get(
            EducationPlan,
            db.session.get(
                EducationPlanLine,
                context["plan_line_id"],
            ).education_plan_id,
        )
        second_plan = EducationPlan(
            tariff_version_id=context["version_id"],
            plan_kind="CURRICULUM",
            name="Профильный учебный план",
            education_level="OOO",
            building_id=context["building_id"],
            scope_code="OOO_PROFILE",
            status="DRAFT",
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        db.session.add(second_plan)
        db.session.flush()
        enrollment_ids = {
            item.id for item in snapshot_class.enrollments
        }

        replace_plan_binding_members(
            first_plan,
            snapshot_class,
            enrollment_ids,
            user_id=user_id,
        )
        moved_enrollment_id = next(iter(enrollment_ids))
        replace_plan_binding_members(
            second_plan,
            snapshot_class,
            {moved_enrollment_id},
            user_id=user_id,
        )
        db.session.commit()

        allocations, student_plan_ids = class_plan_allocations(
            snapshot_class,
            [first_plan, second_plan],
        )
        assert allocations[second_plan.id] == {moved_enrollment_id}
        assert allocations[first_plan.id] == (
            enrollment_ids - {moved_enrollment_id}
        )
        assert student_plan_ids[moved_enrollment_id] == second_plan.id
        assert EducationPlanBinding.query.count() == 2


def test_plan_bindings_page_reads_snapshot_classes(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        snapshot_class_id = (
            PopulationSnapshotClass.query
            .filter_by(
                population_snapshot_id=snapshot_id,
                name_snapshot="5А",
            )
            .one()
            .id
        )

    login(user_id)
    response = client.get(
        f"/workload/plan-bindings/?version_id={context['version_id']}"
    )

    assert response.status_code == 200
    assert "Привязка учебных планов".encode() in response.data
    assert "5А".encode() in response.data
    assert "Иванов Иван".encode() not in response.data

    response = client.get(
        f"/workload/plan-bindings/?version_id={context['version_id']}"
        f"&class_id={snapshot_class_id}"
    )
    assert response.status_code == 200
    assert "Иванов Иван".encode() in response.data


def test_plan_bindings_page_warns_when_population_registry_changed(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        db.session.add(SchoolClass(
            academic_year_id=context["year_id"],
            building_id=context["building_id"],
            name="5В",
            grade=5,
            letter="В",
        ))
        db.session.commit()

        version = db.session.get(TariffVersion, context["version_id"])
        snapshot = db.session.get(PopulationSnapshot, snapshot_id)
        registry_status = population_registry_status(version, snapshot)
        assert registry_status["is_stale"] is True
        assert registry_status["class_count"] == 3
        assert registry_status["snapshot_class_count"] == 2

    login(user_id)
    response = client.get(
        f"/workload/plan-bindings/?version_id={context['version_id']}"
    )

    assert response.status_code == 200
    assert "Сводный контингент изменён".encode() in response.data
    assert "Обновить данные".encode() in response.data


def test_class_plan_can_be_overridden_for_one_student(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        snapshot_class = (
            PopulationSnapshotClass.query
            .filter_by(
                population_snapshot_id=snapshot_id,
                name_snapshot="5А",
            )
            .one()
        )
        first_plan = db.session.get(
            EducationPlan,
            db.session.get(
                EducationPlanLine,
                context["plan_line_id"],
            ).education_plan_id,
        )
        second_plan = EducationPlan(
            tariff_version_id=context["version_id"],
            plan_kind="CURRICULUM",
            name="Профильный учебный план",
            education_level="OOO",
            building_id=context["building_id"],
            scope_code="OOO_PROFILE",
            status="DRAFT",
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        db.session.add(second_plan)
        db.session.commit()
        class_id = snapshot_class.id
        first_plan_id = first_plan.id
        second_plan_id = second_plan.id
        enrollment_ids = [
            item.id for item in snapshot_class.enrollments
        ]
        version_id = context["version_id"]

    login(user_id)
    response = client.post(
        "/workload/plan-bindings/class",
        data={
            "version_id": version_id,
            "class_id": class_id,
            "plan_id": first_plan_id,
        },
    )
    assert response.status_code == 302

    with app.app_context():
        snapshot_class = db.session.get(
            PopulationSnapshotClass,
            class_id,
        )
        plans = [
            db.session.get(EducationPlan, first_plan_id),
            db.session.get(EducationPlan, second_plan_id),
        ]
        allocations, _ = class_plan_allocations(
            snapshot_class,
            plans,
        )
        assert allocations[first_plan_id] == set(enrollment_ids)
        assert EducationPlanBinding.query.one().binding_mode == "CLASS"

    response = client.post(
        "/workload/plan-bindings/student",
        data={
            "version_id": version_id,
            "class_id": class_id,
            "enrollment_id": enrollment_ids[0],
            "plan_id": second_plan_id,
        },
    )
    assert response.status_code == 302

    with app.app_context():
        snapshot_class = db.session.get(
            PopulationSnapshotClass,
            class_id,
        )
        plans = [
            db.session.get(EducationPlan, first_plan_id),
            db.session.get(EducationPlan, second_plan_id),
        ]
        allocations, student_plan_ids = class_plan_allocations(
            snapshot_class,
            plans,
        )
        assert allocations[second_plan_id] == {enrollment_ids[0]}
        assert allocations[first_plan_id] == {enrollment_ids[1]}
        assert student_plan_ids[enrollment_ids[0]] == second_plan_id
        assert {
            item.binding_mode
            for item in EducationPlanBinding.query.all()
        } == {"STUDENTS"}

    page = client.get(
        f"/workload/plan-bindings/?version_id={version_id}"
        f"&class_id={class_id}"
    )
    assert page.status_code == 200
    assert "Индивидуальные назначения".encode() in page.data
    assert "Профильный учебный план".encode() in page.data


def test_metagroup_requires_two_source_classes():
    with pytest.raises(GroupValidationError):
        validate_group_sources("METAGROUP", [object()])


def test_administrator_creates_personal_subgroup(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        snapshot_class = (
            PopulationSnapshotClass.query
            .filter_by(
                population_snapshot_id=snapshot_id,
                name_snapshot="5А",
            )
            .one()
        )
        member_id = snapshot_class.enrollments[0].id
        class_id = snapshot_class.id
    login(user_id)

    response = client.post(
        "/workload/groups/new",
        data=_group_form(context, [class_id], [member_id]),
    )

    assert response.status_code == 302
    with app.app_context():
        group = TeachingGroup.query.one()
        assert group.group_type == "SUBGROUP"
        assert group.actual_size == 1
        assert len(group.members) == 1
        assert TeachingGroupHistory.query.count() == 1

    registry = client.get("/workload/groups/")
    registry_html = registry.get_data(as_text=True)
    assert registry.status_code == 200
    assert "workload_distribution.css" in registry_html
    assert "data-group-select" in registry_html
    assert "data-group-context" not in registry_html
    assert "Математика 5А, группа 1" in registry_html


def test_whole_class_automatically_gets_all_members(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        class_id = (
            PopulationSnapshotClass.query
            .filter_by(
                population_snapshot_id=snapshot_id,
                name_snapshot="5А",
            )
            .one()
            .id
        )
    login(user_id)

    response = client.post(
        "/workload/groups/new",
        data=_group_form(
            context,
            [class_id],
            group_type="CLASS",
            code="MATH_5A",
            name="Математика 5А",
            snapshot_enrollment_ids=[],
        ),
    )

    assert response.status_code == 302
    with app.app_context():
        group = TeachingGroup.query.one()
        assert group.actual_size == 2
        assert len(group.members) == 2
        assert group.source_classes[0].relation_kind == "FULL"


def test_duplicate_parallel_membership_is_rejected(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        snapshot_class = (
            PopulationSnapshotClass.query
            .filter_by(
                population_snapshot_id=snapshot_id,
                name_snapshot="5А",
            )
            .one()
        )
        class_id = snapshot_class.id
        member_id = snapshot_class.enrollments[0].id
    login(user_id)
    first = client.post(
        "/workload/groups/new",
        data=_group_form(context, [class_id], [member_id]),
    )
    assert first.status_code == 302

    duplicate = client.post(
        "/workload/groups/new",
        data=_group_form(
            context,
            [class_id],
            [member_id],
            code="MATH_5A_2",
            name="Математика 5А, группа 2",
        ),
    )

    assert duplicate.status_code == 200
    assert "уже включён".encode() in duplicate.data
    with app.app_context():
        assert TeachingGroup.query.count() == 1


def test_count_only_group_uses_manual_actual_size(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        class_id = (
            PopulationSnapshotClass.query
            .filter_by(
                population_snapshot_id=snapshot_id,
                name_snapshot="5А",
            )
            .one()
            .id
        )
    login(user_id)

    response = client.post(
        "/workload/groups/new",
        data=_group_form(
            context,
            [class_id],
            member_ids=[],
            composition_mode="COUNT_ONLY",
            actual_size="14",
        ),
    )

    assert response.status_code == 302
    with app.app_context():
        group = TeachingGroup.query.one()
        assert group.actual_size == 14
        assert group.members == []


def test_subgroup_coverage_reports_missing_students(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        snapshot_class = (
            PopulationSnapshotClass.query
            .filter_by(
                population_snapshot_id=snapshot_id,
                name_snapshot="5А",
            )
            .one()
        )
        class_id = snapshot_class.id
        member_id = snapshot_class.enrollments[0].id
    login(user_id)
    client.post(
        "/workload/groups/new",
        data=_group_form(context, [class_id], [member_id]),
    )

    with app.app_context():
        coverage = group_coverage(context["plan_line_id"])
        assert coverage[0]["expected_count"] == 2
        assert coverage[0]["assigned_count"] == 1
        assert coverage[0]["missing_count"] == 1
        assert coverage[0]["complete"] is False


def test_ready_group_is_read_only(app, client, make_user, login):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        snapshot_class = (
            PopulationSnapshotClass.query
            .filter_by(
                population_snapshot_id=snapshot_id,
                name_snapshot="5А",
            )
            .one()
        )
        class_id = snapshot_class.id
        member_id = snapshot_class.enrollments[0].id
    login(user_id)
    client.post(
        "/workload/groups/new",
        data=_group_form(context, [class_id], [member_id]),
    )
    with app.app_context():
        group_id = TeachingGroup.query.one().id

    response = client.post(
        f"/workload/groups/{group_id}/status",
        data={"status": "READY", "revision": "1"},
    )

    assert response.status_code == 302
    with app.app_context():
        group = db.session.get(TeachingGroup, group_id)
        assert group.status == "READY"
        assert group.revision == 2


def test_group_close_records_date_and_truncates_members(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _group_context(user_id)
        snapshot_id = _snapshot(user_id, context["version_id"])
        snapshot_class = (
            PopulationSnapshotClass.query
            .filter_by(
                population_snapshot_id=snapshot_id,
                name_snapshot="5А",
            )
            .one()
        )
        class_id = snapshot_class.id
        member_id = snapshot_class.enrollments[0].id
    login(user_id)
    client.post(
        "/workload/groups/new",
        data=_group_form(context, [class_id], [member_id]),
    )
    with app.app_context():
        group_id = TeachingGroup.query.one().id

    response = client.post(
        f"/workload/groups/{group_id}/status",
        data={
            "status": "CLOSED",
            "revision": "1",
            "close_date": "2027-01-31",
            "close_reason": "Изменение учебного плана",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        group = db.session.get(TeachingGroup, group_id)
        assert group.status == "CLOSED"
        assert group.valid_to == date(2027, 1, 31)
        assert group.members[0].valid_to == date(2027, 1, 31)
        assert group.close_reason == "Изменение учебного плана"


def test_teacher_cannot_open_group_registry(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    login(make_user("TEACHER"))

    response = client.get("/workload/groups/")

    assert response.status_code == 403
