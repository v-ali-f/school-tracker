from datetime import date
from decimal import Decimal

from app.core.extensions import db
from app.models import (
    AcademicYear,
    Child,
    ChildEnrollment,
    ChildTransferHistory,
    EducationActivity,
    EducationPlan,
    EducationPlanLine,
    EducationPlanLineScope,
    SchoolClass,
    TariffVersion,
    TeachingGroup,
    User,
    WorkloadAssignment,
    WorkloadNeed,
)
from app.services.academic_year_rollover_service import (
    initialize_academic_year,
)
from app.services.education_plan_service import (
    create_plan_bundle,
    ensure_draft_tariff_version,
    line_scope_key,
    plan_bundle_parts,
    plan_scope_code,
)


def test_rollover_copies_independent_plans_without_groups_or_workload(
    app,
    make_user,
):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")

    with app.app_context():
        source_year = AcademicYear(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
            is_current=True,
        )
        target_year = AcademicYear(
            name="2027/2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 8, 31),
            is_current=False,
        )
        db.session.add_all([source_year, target_year])
        db.session.flush()
        source_class = SchoolClass(
            academic_year_id=source_year.id,
            name="5А",
            grade=5,
            letter="А",
            max_students=30,
            teacher_user_id=teacher_id,
        )
        activity = EducationActivity(
            code="MATH_ROLLOVER",
            name="Математика",
            activity_kind="SUBJECT",
            is_global=True,
            is_tariffable=True,
            is_active=True,
        )
        db.session.add_all([source_class, activity])
        db.session.flush()
        _, source_version = ensure_draft_tariff_version(
            source_year,
            user_id=admin_id,
        )
        source_plan = EducationPlan(
            tariff_version_id=source_version.id,
            plan_kind="CURRICULUM",
            name="ООО",
            profile_name="Математический",
            education_level="OOO",
            scope_code=plan_scope_code("OOO"),
            status="DRAFT",
            created_by_user_id=admin_id,
            updated_by_user_id=admin_id,
        )
        db.session.add(source_plan)
        db.session.flush()
        create_plan_bundle(source_plan, user_id=admin_id)
        db.session.flush()
        source_line = EducationPlanLine(
            education_plan_id=source_plan.id,
            education_activity_id=activity.id,
            component_kind="MANDATORY",
            weekly_hours=Decimal("5"),
            weeks_count=Decimal("34"),
            annual_hours=Decimal("170"),
            sort_order=100,
            created_by_user_id=admin_id,
            updated_by_user_id=admin_id,
        )
        db.session.add(source_line)
        db.session.flush()
        source_line.scopes.append(EducationPlanLineScope(
            scope_kind="CLASS",
            school_class_id=source_class.id,
            scope_key=line_scope_key(
                "CLASS",
                school_class_id=source_class.id,
            ),
        ))
        source_group = TeachingGroup(
            tariff_version_id=source_version.id,
            education_activity_id=activity.id,
            group_type="CLASS",
            code="5A-MATH",
            name="5А · Математика",
            composition_mode="COUNT_ONLY",
            planned_size=30,
            valid_from=source_year.start_date,
            valid_to=source_year.end_date,
            source_plan_line_id=source_line.id,
            status="READY",
            created_by_user_id=admin_id,
            updated_by_user_id=admin_id,
        )
        db.session.add(source_group)
        db.session.flush()
        source_need = WorkloadNeed(
            tariff_version_id=source_version.id,
            teaching_group_id=source_group.id,
            education_activity_id=activity.id,
            date_from=source_year.start_date,
            date_to=source_year.end_date,
            weekly_hours=Decimal("5"),
            annual_hours=Decimal("170"),
            need_kind="PLAN",
            status="COVERED",
            created_by_user_id=admin_id,
            updated_by_user_id=admin_id,
        )
        db.session.add(source_need)
        db.session.flush()
        db.session.add(WorkloadAssignment(
            tariff_version_id=source_version.id,
            workload_need_id=source_need.id,
            employee_user_id=teacher_id,
            position_code="TEACHER",
            assignment_kind="MAIN",
            date_from=source_year.start_date,
            date_to=source_year.end_date,
            weekly_hours=Decimal("5"),
            annual_hours=Decimal("170"),
            status="CONFIRMED",
            created_by_user_id=admin_id,
            updated_by_user_id=admin_id,
        ))
        db.session.flush()

        result = initialize_academic_year(
            source_year,
            target_year,
            user_id=admin_id,
        )
        db.session.commit()

        assert result.plans_created == 1
        assert SchoolClass.query.filter_by(
            academic_year_id=target_year.id,
        ).count() == 0

        target_plan = (
            EducationPlan.query
            .join(EducationPlan.tariff_version)
            .join(TariffVersion.tariff_cycle)
            .filter(
                TariffVersion.tariff_cycle.has(
                    academic_year_id=target_year.id,
                ),
                EducationPlan.plan_kind == "CURRICULUM",
                EducationPlan.root_plan_id.is_(None),
            )
            .one()
        )
        target_parts = plan_bundle_parts(target_plan)
        assert set(target_parts) == {
            "CURRICULUM",
            "EXTRACURRICULAR",
            "ADDITIONAL_EDUCATION",
        }
        target_line = target_plan.lines[0]
        assert target_line.id != source_line.id
        assert target_line.source_line_id == source_line.id
        assert target_plan.profile_name == "Математический"
        assert target_line.weekly_hours == Decimal("5")
        assert target_line.scopes[0].scope_kind == "GRADE"
        assert target_line.scopes[0].grade == 5
        assert target_line.scopes[0].school_class_id is None

        target_version = target_plan.tariff_version
        assert TeachingGroup.query.filter_by(
            tariff_version_id=target_version.id,
        ).count() == 0
        assert WorkloadNeed.query.filter_by(
            tariff_version_id=target_version.id,
        ).count() == 0
        assert WorkloadAssignment.query.filter_by(
            tariff_version_id=target_version.id,
        ).count() == 0
        assert WorkloadAssignment.query.filter_by(
            tariff_version_id=source_version.id,
        ).count() == 1
        assert db.session.get(User, teacher_id) is not None

        source_line.weekly_hours = Decimal("6")
        db.session.commit()
        assert db.session.get(
            EducationPlanLine,
            target_line.id,
        ).weekly_hours == Decimal("5")


def test_class_name_is_unique_within_academic_year(
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
        db.session.commit()
        year_id = year.id
    login(admin_id)

    first = client.post(
        "/classes/new",
        data={
            "academic_year_id": year_id,
            "name": "7-а",
            "max_students": "30",
        },
    )
    duplicate = client.post(
        "/classes/new",
        data={
            "academic_year_id": year_id,
            "name": "7А",
            "max_students": "25",
        },
        follow_redirects=True,
    )

    assert first.status_code == 302
    assert duplicate.status_code == 200
    assert "уже существует" in duplicate.get_data(as_text=True)
    with app.app_context():
        classes = SchoolClass.query.filter_by(
            academic_year_id=year_id,
        ).all()
        assert len(classes) == 1
        assert classes[0].name == "7А"


def test_class_structure_copy_promotes_and_can_be_undone(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        source_year = AcademicYear(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
            is_current=True,
        )
        target_year = AcademicYear(
            name="2027/2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 8, 31),
        )
        db.session.add_all([source_year, target_year])
        db.session.flush()
        db.session.add_all([
            SchoolClass(
                academic_year_id=source_year.id,
                name="1А",
                grade=1,
                letter="А",
                max_students=30,
            ),
            SchoolClass(
                academic_year_id=source_year.id,
                name="8Б",
                grade=8,
                letter="Б",
                max_students=31,
            ),
            SchoolClass(
                academic_year_id=source_year.id,
                name="9В",
                grade=9,
                letter="В",
                max_students=32,
            ),
            SchoolClass(
                academic_year_id=source_year.id,
                name="10Г",
                grade=10,
                letter="Г",
                max_students=28,
            ),
            SchoolClass(
                academic_year_id=source_year.id,
                name="11Д",
                grade=11,
                letter="Д",
                max_students=27,
            ),
        ])
        db.session.commit()
        source_year_id = source_year.id
        target_year_id = target_year.id
    login(admin_id)

    response = client.post(
        "/classes/copy-from-year",
        data={
            "source_year_id": source_year_id,
            "target_year_id": target_year_id,
        },
    )

    assert response.status_code == 302
    assert f"academic_year_id={target_year_id}" in response.headers["Location"]
    with app.app_context():
        target_classes = (
            SchoolClass.query
            .filter_by(academic_year_id=target_year_id)
            .order_by(SchoolClass.grade.asc())
            .all()
        )
        assert [school_class.name for school_class in target_classes] == [
            "2А",
            "9Б",
            "11Г",
        ]
        assert [school_class.applications_count for school_class in target_classes] == [
            0,
            0,
            0,
        ]
        class_2a_id = target_classes[0].id

    registry = client.get(
        f"/classes?academic_year_id={target_year_id}",
    )
    assert "Отменить перенос (3)" in registry.get_data(as_text=True)

    applications = client.post(
        f"/classes/{class_2a_id}/applications",
        data={"applications_count": "7"},
    )
    assert applications.status_code == 302
    assert f"year_id={target_year_id}" in applications.headers["Location"]
    with app.app_context():
        assert db.session.get(
            SchoolClass,
            class_2a_id,
        ).applications_count == 7

    undo = client.post(
        "/classes/copy-from-year/undo",
        data={"target_year_id": target_year_id},
    )
    assert undo.status_code == 302
    assert f"academic_year_id={target_year_id}" in undo.headers["Location"]
    with app.app_context():
        assert SchoolClass.query.filter_by(
            academic_year_id=target_year_id,
        ).count() == 0


def test_mass_transfer_skips_existing_target_year_enrollment(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        source_year = AcademicYear(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
            is_current=True,
        )
        target_year = AcademicYear(
            name="2027/2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 8, 31),
        )
        db.session.add_all([source_year, target_year])
        db.session.flush()
        source_class = SchoolClass(
            academic_year_id=source_year.id,
            name="5А",
            grade=5,
            letter="А",
        )
        target_class = SchoolClass(
            academic_year_id=target_year.id,
            name="6А",
            grade=6,
            letter="А",
        )
        child = Child(last_name="Иванов", first_name="Иван")
        db.session.add_all([source_class, target_class, child])
        db.session.flush()
        source_enrollment = ChildEnrollment(
            child_id=child.id,
            academic_year_id=source_year.id,
            school_class_id=source_class.id,
            status="ACTIVE",
        )
        target_enrollment = ChildEnrollment(
            child_id=child.id,
            academic_year_id=target_year.id,
            school_class_id=target_class.id,
            status="ACTIVE",
        )
        db.session.add_all([source_enrollment, target_enrollment])
        db.session.commit()
        values = {
            "source_year_id": source_year.id,
            "target_year_id": target_year.id,
            "source_class_id": source_class.id,
            "target_class_id": target_class.id,
            "source_enrollment_id": source_enrollment.id,
        }
    login(admin_id)

    response = client.post(
        "/transfers/class",
        data={
            "action": "execute",
            "from_year_id": values["source_year_id"],
            "to_year_id": values["target_year_id"],
            "source_class_id": values["source_class_id"],
            "target_class_id": values["target_class_id"],
            "enrollment_ids": [str(values["source_enrollment_id"])],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Пропущено уже зачисленных" in response.get_data(as_text=True)
    with app.app_context():
        assert ChildEnrollment.query.filter_by(
            id=values["source_enrollment_id"],
        ).one().ended_at is None
        assert ChildTransferHistory.query.count() == 0
