from datetime import date
from decimal import Decimal

import pytest

from app.core.extensions import db
from app.models import (
    AcademicYear,
    EducationActivity,
    EducationPlan,
    EducationPlanLine,
    EducationPlanLineScope,
    TariffCycle,
    TariffVersion,
    TariffVersionStatusHistory,
)
from app.services.education_plan_service import (
    PlanValidationError,
    calculate_annual_hours,
    ensure_draft_tariff_version,
    line_scope_key,
    plan_scope_code,
    validate_line_values,
    validate_period_range,
)


def _academic_year():
    year = AcademicYear(
        name="2026/2027",
        is_current=True,
        start_date=date(2026, 9, 1),
        end_date=date(2027, 8, 31),
    )
    db.session.add(year)
    db.session.flush()
    return year


def _activity(code="MATH", name="Математика", kind="SUBJECT"):
    activity = EducationActivity(
        code=code,
        name=name,
        activity_kind=kind,
        is_global=True,
        is_tariffable=True,
        is_active=True,
    )
    db.session.add(activity)
    db.session.flush()
    return activity


def _plan(user_id, plan_kind="CURRICULUM", activity_kind="SUBJECT"):
    year = _academic_year()
    activity = _activity(kind=activity_kind)
    _, version = ensure_draft_tariff_version(
        year,
        user_id=user_id,
    )
    plan = EducationPlan(
        tariff_version_id=version.id,
        plan_kind=plan_kind,
        name="Тестовый план",
        education_level="OOO",
        scope_code=plan_scope_code("OOO"),
        status="DRAFT",
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    db.session.add(plan)
    db.session.commit()
    return plan.id, activity.id


def _line_form(activity_id, revision=1, component="MANDATORY"):
    return {
        "revision": str(revision),
        "education_activity_id": str(activity_id),
        "component_kind": component,
        "weekly_hours": "5",
        "weeks_count": "34",
        "annual_hours": "170",
        "scope_kind": "GRADE",
        "grade": "5",
        "sort_order": "100",
    }


def test_draft_cycle_and_version_are_created_once(app, make_user):
    user_id = make_user("ADMIN")
    with app.app_context():
        year = _academic_year()

        first_cycle, first_version = ensure_draft_tariff_version(
            year,
            user_id=user_id,
        )
        second_cycle, second_version = ensure_draft_tariff_version(
            year,
            user_id=user_id,
        )
        db.session.commit()

        assert first_cycle.id == second_cycle.id
        assert first_version.id == second_version.id
        assert TariffCycle.query.count() == 1
        assert TariffVersion.query.count() == 1
        assert TariffVersionStatusHistory.query.count() == 1


@pytest.mark.parametrize(
    ("plan_kind", "activity_kind", "component"),
    [
        ("CURRICULUM", "SUBJECT", "MANDATORY"),
        ("EXTRACURRICULAR", "EXTRACURRICULAR_COURSE", "EXTRACURRICULAR"),
        ("ADDITIONAL_EDUCATION", "ADDITIONAL_PROGRAM", "ADDITIONAL"),
    ],
)
def test_each_plan_kind_accepts_only_its_own_content(
    app,
    make_user,
    plan_kind,
    activity_kind,
    component,
):
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id, plan_kind, activity_kind)
        plan = db.session.get(EducationPlan, plan_id)
        activity = db.session.get(EducationActivity, activity_id)

        validate_line_values(
            plan,
            activity,
            component,
            Decimal("1"),
            None,
        )

        with pytest.raises(PlanValidationError):
            validate_line_values(
                plan,
                activity,
                "MANDATORY" if component != "MANDATORY" else "ADDITIONAL",
                Decimal("1"),
                None,
            )


def test_period_must_stay_inside_academic_year(app, make_user):
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, _ = _plan(user_id)
        plan = db.session.get(EducationPlan, plan_id)

        validate_period_range(
            plan,
            date(2026, 9, 1),
            date(2027, 5, 31),
        )
        with pytest.raises(PlanValidationError):
            validate_period_range(
                plan,
                date(2026, 8, 31),
                date(2027, 5, 31),
            )


def test_scope_key_is_stable_for_grade_and_building():
    assert line_scope_key("GRADE", grade=5, building_id=2) == "GRADE:5:B2"
    assert (
        line_scope_key("PROFILE", profile_code="  ИТ профиль ", building_id=1)
        == "PROFILE:ИТ ПРОФИЛЬ:B1"
    )


def test_annual_hours_are_calculated_from_weekly_hours_and_weeks():
    assert calculate_annual_hours(
        Decimal("5"),
        Decimal("34"),
        None,
    ) == Decimal("170.000")

    with pytest.raises(PlanValidationError):
        calculate_annual_hours(None, Decimal("34"), None)


def test_plan_write_requires_write_feature_flag(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    login(make_user("ADMIN"))

    response = client.get("/workload/plans/new")

    assert response.status_code == 404


def test_teacher_cannot_open_all_education_plans(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    login(make_user("TEACHER"))

    response = client.get("/workload/plans/")

    assert response.status_code == 403


def test_administrator_can_create_plan(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        year = _academic_year()
        db.session.commit()
        year_id = year.id
    login(user_id)

    response = client.post(
        "/workload/plans/new",
        data={
            "academic_year_id": year_id,
            "plan_kind": "CURRICULUM",
            "name": "Основной учебный план",
            "education_level": "OOO",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/matrix")
    matrix_response = client.get(response.headers["Location"])
    assert matrix_response.status_code == 200
    assert "Учебный план".encode() in matrix_response.data
    assert "Внеурочная деятельность".encode() in matrix_response.data
    assert "Дополнительное образование".encode() in matrix_response.data
    with app.app_context():
        plans = EducationPlan.query.order_by(
            EducationPlan.id.asc()
        ).all()
        assert len(plans) == 3
        root_plan = next(
            item for item in plans if item.plan_kind == "CURRICULUM"
        )
        assert root_plan.root_plan_id is None
        assert {
            item.plan_kind
            for item in plans
            if item.root_plan_id == root_plan.id
        } == {"EXTRACURRICULAR", "ADDITIONAL_EDUCATION"}
        assert root_plan.tariff_version.status == "DRAFT"


def test_curriculum_plan_requires_education_level(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        year = _academic_year()
        db.session.commit()
        year_id = year.id
    login(user_id)

    response = client.post(
        "/workload/plans/new",
        data={
            "academic_year_id": year_id,
            "plan_kind": "CURRICULUM",
            "name": "План без уровня",
        },
    )

    assert response.status_code == 200
    assert "НОО, ООО или СОО".encode() in response.data
    with app.app_context():
        assert EducationPlan.query.count() == 0


def test_administrator_can_add_grade_line_to_plan(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)

    response = client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(activity_id),
    )

    assert response.status_code == 302
    with app.app_context():
        line = EducationPlanLine.query.one()
        scope = EducationPlanLineScope.query.one()
        plan = db.session.get(EducationPlan, plan_id)
        assert line.weekly_hours == Decimal("5.000")
        assert line.weeks_count == Decimal("34.000")
        assert line.annual_hours == Decimal("170.000")
        assert scope.scope_kind == "GRADE"
        assert scope.grade == 5
        assert plan.revision == 2


def test_plan_rejects_activity_from_another_plan_kind(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(
            user_id,
            "EXTRACURRICULAR",
            "SUBJECT",
        )
    login(user_id)

    response = client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(
            activity_id,
            component="EXTRACURRICULAR",
        ),
    )

    assert response.status_code == 200
    assert "не соответствует".encode() in response.data
    with app.app_context():
        assert EducationPlanLine.query.count() == 0


def test_administrator_can_edit_plan_line(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)
    client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(activity_id),
    )
    with app.app_context():
        line_id = EducationPlanLine.query.one().id

    response = client.post(
        f"/workload/plans/{plan_id}/lines/{line_id}/edit",
        data={
            **_line_form(activity_id, revision=2),
            "weekly_hours": "6",
            "weeks_count": "34",
            "annual_hours": "",
            "grade": "6",
            "requires_division": "1",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        line = db.session.get(EducationPlanLine, line_id)
        plan = db.session.get(EducationPlan, plan_id)
        assert line.weekly_hours == Decimal("6.000")
        assert line.weeks_count == Decimal("34.000")
        assert line.annual_hours == Decimal("204.000")
        assert line.requires_division is True
        assert line.scopes[0].grade == 6
        assert plan.revision == 3


def test_stale_revision_does_not_add_second_line(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)
    first = client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(activity_id, revision=1),
    )
    assert first.status_code == 302

    stale = client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(activity_id, revision=1),
    )

    assert stale.status_code == 200
    assert "другим пользователем".encode() in stale.data
    with app.app_context():
        assert EducationPlanLine.query.count() == 1


def test_ready_plan_is_read_only_until_returned_to_draft(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)
    client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(activity_id, revision=1),
    )

    ready = client.post(
        f"/workload/plans/{plan_id}/status",
        data={"status": "READY", "revision": "2"},
    )
    assert ready.status_code == 302

    blocked = client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(activity_id, revision=3),
    )
    assert blocked.status_code == 200
    assert "верните план".encode() in blocked.data

    back_to_draft = client.post(
        f"/workload/plans/{plan_id}/status",
        data={"status": "DRAFT", "revision": "3"},
    )
    assert back_to_draft.status_code == 302
    with app.app_context():
        plan = db.session.get(EducationPlan, plan_id)
        assert plan.status == "DRAFT"
        assert plan.revision == 4


def test_plan_matrix_renders_scope_columns(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)
    client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(activity_id),
    )

    response = client.get(f"/workload/plans/{plan_id}/matrix")

    assert response.status_code == 200
    for grade in range(5, 10):
        assert f"{grade} класс".encode() in response.data
    assert "Математика".encode() in response.data
    assert "Обязательная часть".encode() in response.data
    assert 'data-plan-cell'.encode() in response.data
    assert 'name="weekly_hours"'.encode() in response.data
    assert 'name="weeks_count"'.encode() in response.data
    assert 'value="5"'.encode() in response.data
    assert 'value="34"'.encode() in response.data
    assert "170.000".encode() not in response.data
    assert 'data-annual="170"'.encode() in response.data
    assert response.data.count(">год.<".encode()) == 6
    assert "Состояние рабочего пространства".encode() not in response.data
    assert "Нераспределено".encode() not in response.data
    assert "Пустые группы".encode() not in response.data
    assert "Готовность".encode() not in response.data
    assert "Версия 1".encode() not in response.data
    assert "Черновик".encode() not in response.data


def test_empty_noo_plan_shows_all_grade_columns(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, _ = _plan(user_id)
        plan = db.session.get(EducationPlan, plan_id)
        plan.education_level = "NOO"
        plan.scope_code = plan_scope_code("NOO")
        db.session.commit()
    login(user_id)

    response = client.get(f"/workload/plans/{plan_id}/matrix")

    assert response.status_code == 200
    for grade in range(1, 5):
        assert f"{grade} класс".encode() in response.data
    assert "Выберите предмет выше".encode() in response.data


def test_noo_matrix_shows_split_periods_for_first_grade(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, _ = _plan(user_id)
        plan = db.session.get(EducationPlan, plan_id)
        plan.education_level = "NOO"
        plan.scope_code = plan_scope_code("NOO")
        db.session.commit()
    login(user_id)

    response = client.get(f"/workload/plans/{plan_id}/matrix")

    assert response.status_code == 200
    assert "сент.–окт.".encode() in response.data
    assert "нояб.–май".encode() in response.data
    assert ">9 нед.<".encode() in response.data
    assert ">25 нед.<".encode() in response.data
    assert response.data.count(">год.<".encode()) == 5


def test_noo_first_grade_period_hours_are_saved_and_summed(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
        plan = db.session.get(EducationPlan, plan_id)
        plan.education_level = "NOO"
        plan.scope_code = plan_scope_code("NOO")
        db.session.commit()
    login(user_id)
    client.post(
        f"/workload/plans/{plan_id}/matrix/activities",
        data={
            "revision": "1",
            "education_activity_id": str(activity_id),
            "component_kind": "MANDATORY",
        },
    )
    matrix_response = client.get(f"/workload/plans/{plan_id}/matrix")
    assert 'name="period_1_weeks_count"'.encode() in matrix_response.data
    assert 'name="period_2_weeks_count"'.encode() in matrix_response.data
    assert "ч/нед".encode() not in matrix_response.data
    assert "за год".encode() not in matrix_response.data
    assert "data-period-annual=".encode() not in matrix_response.data
    assert "data-period-total-annual=".encode() not in matrix_response.data
    assert "workload-plan-matrix__scope-end".encode() in matrix_response.data
    with app.app_context():
        line = (
            EducationPlanLine.query
            .join(EducationPlanLineScope)
            .filter(EducationPlanLineScope.grade == 1)
            .one()
        )
        line_id = line.id

    response = client.post(
        f"/workload/plans/{plan_id}/lines/{line_id}/period-hours",
        data={
            "revision": "2",
            "period_1_weekly_hours": "4",
            "period_2_weekly_hours": "5",
        },
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["weekly_hours"] == "5"
    assert payload["weeks_count"] == "34"
    assert payload["annual_hours"] == "161"
    assert payload["periods"] == [
        {
            "weekly_hours": "4",
            "weeks_count": "9",
            "annual_hours": "36",
        },
        {
            "weekly_hours": "5",
            "weeks_count": "25",
            "annual_hours": "125",
        },
    ]
    with app.app_context():
        line = db.session.get(EducationPlanLine, line_id)
        assert line.annual_hours == Decimal("161.000")
        assert [period.weeks_count for period in line.periods] == [
            Decimal("9.000"),
            Decimal("25.000"),
        ]

    repeated_update = client.post(
        f"/workload/plans/{plan_id}/lines/{line_id}/period-hours",
        data={
            "revision": "3",
            "period_1_weekly_hours": "3",
            "period_1_weeks_count": "8",
            "period_2_weekly_hours": "4",
            "period_2_weeks_count": "26",
        },
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )
    assert repeated_update.status_code == 200
    assert repeated_update.get_json()["annual_hours"] == "128"
    with app.app_context():
        line = db.session.get(EducationPlanLine, line_id)
        assert len(line.periods) == 2
        assert line.annual_hours == Decimal("128.000")
        assert [period.weeks_count for period in line.periods] == [
            Decimal("8.000"),
            Decimal("26.000"),
        ]


def test_soo_eleventh_grade_uses_attestation_periods(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
        plan = db.session.get(EducationPlan, plan_id)
        plan.education_level = "SOO"
        plan.scope_code = plan_scope_code("SOO")
        db.session.commit()
    login(user_id)
    client.post(
        f"/workload/plans/{plan_id}/matrix/activities",
        data={
            "revision": "1",
            "education_activity_id": str(activity_id),
            "component_kind": "MANDATORY",
        },
    )
    response = client.get(f"/workload/plans/{plan_id}/matrix")
    assert response.status_code == 200
    assert "I период".encode() in response.data
    assert "II период".encode() in response.data
    assert ">20 нед.<".encode() in response.data
    assert ">14 нед.<".encode() in response.data

    with app.app_context():
        line = (
            EducationPlanLine.query
            .join(EducationPlanLineScope)
            .filter(EducationPlanLineScope.grade == 11)
            .one()
        )
        line_id = line.id
    update = client.post(
        f"/workload/plans/{plan_id}/lines/{line_id}/period-hours",
        data={
            "revision": "2",
            "period_1_weekly_hours": "3",
            "period_1_weeks_count": "19",
            "period_2_weekly_hours": "2",
            "period_2_weeks_count": "15",
        },
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )

    assert update.status_code == 200
    assert update.get_json()["annual_hours"] == "87"
    with app.app_context():
        line = db.session.get(EducationPlanLine, line_id)
        assert line.weeks_count == Decimal("34.000")
        assert line.annual_hours == Decimal("87.000")
        assert [period.weeks_count for period in line.periods] == [
            Decimal("19.000"),
            Decimal("15.000"),
        ]


def test_quick_add_creates_subject_row_for_every_grade(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)

    response = client.post(
        f"/workload/plans/{plan_id}/matrix/activities",
        data={
            "revision": "1",
            "education_activity_id": str(activity_id),
            "component_kind": "MANDATORY",
        },
    )

    assert response.status_code == 302
    assert f"/workload/plans/{plan_id}/matrix" in response.headers["Location"]
    with app.app_context():
        lines = EducationPlanLine.query.order_by(
            EducationPlanLine.id.asc()
        ).all()
        assert len(lines) == 5
        assert {line.scopes[0].grade for line in lines} == set(range(5, 10))
        assert {line.weekly_hours for line in lines} == {Decimal("0.000")}
        assert {line.weeks_count for line in lines} == {Decimal("34.000")}
        assert {line.annual_hours for line in lines} == {Decimal("0.000")}


def test_matrix_can_fill_a_missing_grade_cell(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)
    client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(activity_id),
    )

    matrix_response = client.get(f"/workload/plans/{plan_id}/matrix")

    assert matrix_response.status_code == 200
    assert matrix_response.data.count(b"data-plan-cell-create") == 4
    assert (
        'aria-label="Часов в неделю: Математика, 6 класс"'.encode()
        in matrix_response.data
    )
    assert 'value="34"'.encode() in matrix_response.data

    response = client.post(
        f"/workload/plans/{plan_id}/matrix/cells",
        data={
            "revision": "2",
            "education_activity_id": str(activity_id),
            "component_kind": "MANDATORY",
            "grade": "6",
            "weekly_hours": "3",
            "weeks_count": "34",
            "annual_hours": "",
            "sort_order": "100",
        },
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["annual_hours"] == "102"
    assert response.get_json()["revision"] == 3
    with app.app_context():
        lines = EducationPlanLine.query.order_by(EducationPlanLine.id).all()
        assert len(lines) == 2
        added = next(line for line in lines if line.scopes[0].grade == 6)
        assert added.weekly_hours == Decimal("3.000")
        assert added.weeks_count == Decimal("34.000")
        assert added.annual_hours == Decimal("102.000")


def test_matrix_ajax_update_returns_recalculated_hours(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)
    client.post(
        f"/workload/plans/{plan_id}/matrix/activities",
        data={
            "revision": "1",
            "education_activity_id": str(activity_id),
            "component_kind": "MANDATORY",
        },
    )
    with app.app_context():
        line = (
            EducationPlanLine.query
            .join(EducationPlanLineScope)
            .filter(EducationPlanLineScope.grade == 5)
            .one()
        )
        line_id = line.id

    response = client.post(
        f"/workload/plans/{plan_id}/lines/{line_id}/hours",
        data={
            "revision": "2",
            "weekly_hours": "3",
            "weeks_count": "34",
            "annual_hours": "",
        },
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["weekly_hours"] == "3"
    assert payload["weeks_count"] == "34"
    assert payload["annual_hours"] == "102"
    assert payload["revision"] == 3


def test_matrix_can_delete_an_entire_subject_row(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)
    client.post(
        f"/workload/plans/{plan_id}/matrix/activities",
        data={
            "revision": "1",
            "education_activity_id": str(activity_id),
            "component_kind": "MANDATORY",
        },
    )

    response = client.post(
        f"/workload/plans/{plan_id}/matrix/rows/delete",
        data={
            "revision": "2",
            "education_activity_id": str(activity_id),
            "component_kind": "MANDATORY",
            "profile_code": "",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/workload/plans/{plan_id}/matrix"
    )
    with app.app_context():
        assert EducationPlanLine.query.count() == 0
        assert db.session.get(EducationPlan, plan_id).revision == 3


def test_matrix_preserves_only_significant_decimal_places(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)
    form = _line_form(activity_id)
    form["weekly_hours"] = "1,5"
    form["weeks_count"] = "34"
    form["annual_hours"] = ""
    client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=form,
    )

    response = client.get(f"/workload/plans/{plan_id}/matrix")

    assert response.status_code == 200
    assert 'value="1,5"'.encode() in response.data
    assert 'data-weekly="1,5"'.encode() in response.data
    assert "1,500".encode() not in response.data
    assert 'data-annual="51"'.encode() in response.data


def test_matrix_hours_update_recalculates_annual_hours(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)
    client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(activity_id),
    )
    with app.app_context():
        line_id = EducationPlanLine.query.one().id

    response = client.post(
        f"/workload/plans/{plan_id}/lines/{line_id}/hours",
        data={
            "revision": "2",
            "weekly_hours": "6",
            "weeks_count": "35",
            "annual_hours": "999",
        },
    )

    assert response.status_code == 302
    assert f"selected_line_id={line_id}" in response.headers["Location"]
    with app.app_context():
        line = db.session.get(EducationPlanLine, line_id)
        plan = db.session.get(EducationPlan, plan_id)
        assert line.weekly_hours == Decimal("6.000")
        assert line.weeks_count == Decimal("35.000")
        assert line.annual_hours == Decimal("210.000")
        assert plan.revision == 3


def test_matrix_hours_update_respects_plan_revision(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    with app.app_context():
        plan_id, activity_id = _plan(user_id)
    login(user_id)
    client.post(
        f"/workload/plans/{plan_id}/lines/new",
        data=_line_form(activity_id),
    )
    with app.app_context():
        line_id = EducationPlanLine.query.one().id

    response = client.post(
        f"/workload/plans/{plan_id}/lines/{line_id}/hours",
        data={
            "revision": "1",
            "weekly_hours": "7",
            "weeks_count": "34",
            "annual_hours": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "другим пользователем".encode() in response.data
    with app.app_context():
        line = db.session.get(EducationPlanLine, line_id)
        assert line.weekly_hours == Decimal("5.000")
        assert line.annual_hours == Decimal("170.000")
