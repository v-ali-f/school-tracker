from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.extensions import db
from app.models import (
    AcademicYear,
    Building,
    CalculationParameterSet,
    Department,
    EducationActivity,
    EducationActivityDepartment,
    EducationPlan,
    EducationPlanLine,
    TariffVersion,
    TariffAllowanceRule,
    TariffCalculationRun,
    TariffCoefficientValue,
    TariffLine,
    TariffLineComponent,
    TariffDocumentArtifact,
    TariffReviewComment,
    TariffReviewDecision,
    TariffValidationRun,
    TariffRateNorm,
    TeachingGroup,
    TeacherLoad,
    TeacherMckoResult,
    User,
    WorkloadAssignment,
    WorkloadAssignmentChange,
    WorkloadEditorAccess,
    WorkloadNeed,
    WorkloadNeedSource,
    WorkloadReconciliationRun,
    WorkloadSourceSetting,
    WorkloadSourceTransition,
    Subject,
)
from app.services.education_plan_service import (
    ensure_draft_tariff_version,
    plan_scope_code,
)
from app.services.workload_distribution_service import (
    WorkloadDistributionError,
    calculate_assignment_annual_hours,
    cancel_assignment,
    delete_plan_lines_with_dependencies,
    generate_plan_needs,
    refresh_need_status,
    validate_assignment,
)
from app.services.tariff_calculation_service import (
    calculate_tariff_version,
    ensure_standard_tariff_types,
)
from app.services.tariff_document_service import (
    generate_tariff_document,
    resolve_artifact_path,
)
from app.services.tariff_workflow_service import (
    TariffWorkflowError,
    answer_review_comment,
    approve_version,
    clone_correction_version,
    close_review_comment,
    record_review_decision,
    run_full_validation,
    start_review,
)
from app.services.workload_integration_service import (
    WorkloadIntegrationError,
    internal_department_load_rows,
    reconcile_workload_sources,
    source_state,
    switch_workload_source,
)


def _distribution_context(user_id):
    year = AcademicYear(
        name="2026/2027",
        is_current=True,
        start_date=date(2026, 9, 1),
        end_date=date(2027, 8, 31),
    )
    building = Building(name="Главное здание", short_name="ГЗ")
    department = Department(
        name="Математика и информатика",
        code="math",
    )
    db.session.add_all([year, building, department])
    db.session.flush()
    activity = EducationActivity(
        code="MATH-DISTRIBUTION",
        name="Математика",
        activity_kind="SUBJECT",
        is_global=True,
        is_tariffable=True,
        is_active=True,
    )
    db.session.add(activity)
    db.session.flush()
    db.session.add(EducationActivityDepartment(
        education_activity_id=activity.id,
        department_id=department.id,
        is_primary=True,
        is_active=True,
    ))
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
    group = TeachingGroup(
        tariff_version_id=version.id,
        education_activity_id=activity.id,
        group_type="SUBGROUP",
        code="MATH_5A_1",
        name="Математика 5А, группа 1",
        composition_mode="COUNT_ONLY",
        building_id=building.id,
        planned_size=15,
        actual_size=15,
        valid_from=date(2026, 9, 1),
        valid_to=date(2027, 5, 31),
        source_plan_line_id=line.id,
        status="READY",
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    db.session.add(group)
    db.session.commit()
    return {
        "year_id": year.id,
        "building_id": building.id,
        "department_id": department.id,
        "version_id": version.id,
        "plan_id": plan.id,
        "group_id": group.id,
    }


def _generate(context, user_id):
    version = db.session.get(TariffVersion, context["version_id"])
    result = generate_plan_needs(version, user_id=user_id)
    db.session.commit()
    return result


def _assignment(need, employee_id, weekly, annual=None, kind="MAIN"):
    weekly = Decimal(weekly)
    annual = (
        Decimal(annual)
        if annual is not None
        else calculate_assignment_annual_hours(need, weekly, None)
    )
    return WorkloadAssignment(
        organization_id=need.organization_id,
        tariff_version_id=need.tariff_version_id,
        workload_need_id=need.id,
        employee_user_id=employee_id if kind != "VACANCY" else None,
        position_code="TEACHER",
        position_title="Учитель" if kind != "VACANCY" else "Вакансия",
        department_id=need.department_id,
        building_id=need.building_id,
        assignment_kind=kind,
        date_from=need.date_from,
        date_to=need.date_to,
        weekly_hours=weekly,
        annual_hours=annual,
        status="DRAFT",
    )


def test_generate_need_from_ready_group(app, make_user):
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _distribution_context(user_id)

        result = _generate(context, user_id)

        need = WorkloadNeed.query.one()
        assert result["created"] == 1
        assert need.weekly_hours == Decimal("5.000")
        assert need.annual_hours == Decimal("170.000")
        assert need.department_id == context["department_id"]
        assert need.status == "OPEN"
        source = WorkloadNeedSource.query.one()
        assert source.source_kind == "DIVISION"


def test_need_generation_is_idempotent(app, make_user):
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _distribution_context(user_id)
        _generate(context, user_id)

        second = _generate(context, user_id)

        assert second["created"] == 0
        assert WorkloadNeed.query.count() == 1
        assert WorkloadNeedSource.query.count() == 1


def test_need_generation_updates_full_teacher_assignment_from_plan(
    app,
    make_user,
):
    user_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(user_id)
        _generate(context, user_id)
        need = WorkloadNeed.query.one()
        assignment = _assignment(need, teacher_id, "5")
        validate_assignment(need, assignment)
        db.session.add(assignment)
        db.session.flush()
        refresh_need_status(need)
        db.session.commit()

        line = EducationPlanLine.query.one()
        line.weekly_hours = Decimal("6")
        line.annual_hours = Decimal("204")
        db.session.commit()
        result = _generate(context, user_id)

        assignment = WorkloadAssignment.query.one()
        need = WorkloadNeed.query.one()
        assert result["updated"] == 1
        assert need.weekly_hours == Decimal("6.000")
        assert need.status == "COVERED"
        assert assignment.weekly_hours == Decimal("6.000")
        assert assignment.annual_hours == Decimal("204.000")
        assert assignment.revision == 2
        change = WorkloadAssignmentChange.query.one()
        assert change.change_kind == "UPDATE"
        assert "учебным планом" in change.reason


def test_delete_plan_line_removes_groups_needs_and_assignments(
    app,
    make_user,
):
    user_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(user_id)
        _generate(context, user_id)
        need = WorkloadNeed.query.one()
        assignment = _assignment(need, teacher_id, "5")
        validate_assignment(need, assignment)
        db.session.add(assignment)
        db.session.commit()

        line = EducationPlanLine.query.one()
        deleted = delete_plan_lines_with_dependencies([line])
        db.session.commit()

        assert deleted == {"groups": 1, "needs": 1, "assignments": 1}
        assert EducationPlanLine.query.count() == 0
        assert TeachingGroup.query.count() == 0
        assert WorkloadNeed.query.count() == 0
        assert WorkloadNeedSource.query.count() == 0
        assert WorkloadAssignment.query.count() == 0


def test_plan_matrix_delete_route_cascades_to_workload(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    user_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(user_id)
        _generate(context, user_id)
        need = WorkloadNeed.query.one()
        assignment = _assignment(need, teacher_id, "5")
        validate_assignment(need, assignment)
        db.session.add(assignment)
        activity_id = need.education_activity_id
        db.session.commit()
    login(user_id)

    response = client.post(
        f"/workload/plans/{context['plan_id']}/matrix/rows/delete",
        data={
            "revision": "1",
            "education_activity_id": str(activity_id),
            "component_kind": "MANDATORY",
            "profile_code": "",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        assert EducationPlanLine.query.count() == 0
        assert TeachingGroup.query.count() == 0
        assert WorkloadNeed.query.count() == 0
        assert WorkloadAssignment.query.count() == 0


def test_need_generation_skips_plan_line_without_hours(app, make_user):
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _distribution_context(user_id)
        line = EducationPlanLine.query.one()
        line.weekly_hours = Decimal("0")
        line.annual_hours = Decimal("0")
        db.session.commit()

        result = _generate(context, user_id)

        assert result["created"] == 0
        assert result["skipped_empty"] == 1
        assert WorkloadNeed.query.count() == 0


def test_partial_assignment_updates_need_status(app, make_user):
    user_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(user_id)
        _generate(context, user_id)
        need = WorkloadNeed.query.one()
        assignment = _assignment(need, teacher_id, "3")
        validate_assignment(need, assignment)
        db.session.add(assignment)
        db.session.flush()
        refresh_need_status(need)
        db.session.commit()

        assert assignment.annual_hours == Decimal("102.000")
        assert need.status == "PARTIAL"
        assert need.remaining_weekly_hours == Decimal("2.000")


def test_overallocation_is_rejected(app, make_user):
    user_id = make_user("ADMIN")
    first_teacher = make_user("TEACHER")
    second_teacher = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(user_id)
        _generate(context, user_id)
        need = WorkloadNeed.query.one()
        first = _assignment(need, first_teacher, "4")
        validate_assignment(need, first)
        db.session.add(first)
        db.session.flush()

        with pytest.raises(
            WorkloadDistributionError,
            match="превышают потребность",
        ):
            validate_assignment(
                need,
                _assignment(need, second_teacher, "2"),
            )


def test_vacancy_does_not_cover_need(app, make_user):
    user_id = make_user("ADMIN")
    with app.app_context():
        context = _distribution_context(user_id)
        _generate(context, user_id)
        need = WorkloadNeed.query.one()
        vacancy = _assignment(
            need,
            None,
            "5",
            annual="170",
            kind="VACANCY",
        )
        validate_assignment(need, vacancy)
        db.session.add(vacancy)
        db.session.flush()
        refresh_need_status(need)

        assert need.status == "OPEN"
        assert need.remaining_weekly_hours == Decimal("5.000")


def test_cancel_assignment_reopens_need_and_keeps_history(
    app,
    make_user,
):
    user_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(user_id)
        _generate(context, user_id)
        need = WorkloadNeed.query.one()
        assignment = _assignment(need, teacher_id, "5")
        validate_assignment(need, assignment)
        db.session.add(assignment)
        db.session.flush()
        refresh_need_status(need)
        assert need.status == "COVERED"

        cancel_assignment(
            assignment,
            user_id=user_id,
            expected_revision=1,
            reason="Передача нагрузки",
        )
        db.session.commit()

        assert assignment.status == "CANCELLED"
        assert need.status == "OPEN"
        change = WorkloadAssignmentChange.query.one()
        assert change.change_kind == "CANCEL"
        assert change.reason == "Передача нагрузки"


def test_admin_creates_assignment_through_route(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(admin_id)
        _generate(context, admin_id)
        need_id = WorkloadNeed.query.one().id
    login(admin_id)

    response = client.post(
        f"/workload/needs/{need_id}/assignments/new",
        data={
            "assignment_kind": "MAIN",
            "employee_user_id": str(teacher_id),
            "position_title": "Учитель математики",
            "weekly_hours": "5",
            "annual_hours": "",
            "date_from": "2026-09-01",
            "date_to": "2027-05-31",
            "department_id": str(context["department_id"]),
            "building_id": str(context["building_id"]),
        },
    )

    assert response.status_code == 302
    with app.app_context():
        assignment = WorkloadAssignment.query.one()
        assert assignment.employee_user_id == teacher_id
        assert assignment.annual_hours == Decimal("170.000")
        assert assignment.workload_need.status == "COVERED"
        assert WorkloadAssignmentChange.query.one().change_kind == "CREATE"

    assert client.get("/workload/assignments/").status_code == 200
    workspace_response = client.get("/workload/assignments/workspace")
    workspace_html = workspace_response.get_data(as_text=True)
    assert workspace_response.status_code == 200
    assert "workload_distribution.css" in workspace_html
    assert "data-workload-matrix" in workspace_html
    assert "data-matrix-subject-column" in workspace_html
    assert "data-matrix-total-column" in workspace_html
    assert "data-matrix-class-column" in workspace_html
    assert "ФИО преподавателя" in workspace_html
    assert "По предмету" in workspace_html
    assert "workload-assignment-matrix__class-plan" in workspace_html
    assert workspace_html.index(
        "data-matrix-subject-column"
    ) < workspace_html.index(
        "data-matrix-total-column"
    ) < workspace_html.index(
        "data-matrix-class-column"
    )
    assert "data-need-context" not in workspace_html
    assert "Назначено" in workspace_html
    assert 'name="version_id"' in workspace_html
    assert "2026/2027" in workspace_html
    assert "версия 1" not in workspace_html.lower()
    assert 'data-active-mode="workload"' in workspace_html
    assert client.get(f"/workload/needs/{need_id}").status_code == 200
    assert client.get("/workload/teachers/").status_code == 200
    assert client.get(
        f"/workload/teachers/{teacher_id}"
    ).status_code == 200
    assert client.get("/workload/departments/").status_code == 200


def test_assignment_workspace_hides_unassigned_pseudo_teacher(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    with app.app_context():
        context = _distribution_context(admin_id)
        _generate(context, admin_id)
    login(admin_id)

    response = client.get(
        "/workload/assignments/workspace",
        query_string={"version_id": context["version_id"]},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "data-workload-matrix" in html
    assert "Не распределено" not in html
    assert "не назначено" not in html
    assert "workload-add-teacher-row" in html
    assert "Добавить преподавателя" in html
    assert "workload-matrix-head-add" not in html


def test_generate_from_workspace_returns_to_matrix(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    with app.app_context():
        context = _distribution_context(admin_id)
        line = EducationPlanLine.query.one()
        line.weekly_hours = Decimal("0")
        line.annual_hours = Decimal("0")
        db.session.commit()
    login(admin_id)

    response = client.post(
        "/workload/assignments/generate",
        data={
            "version_id": context["version_id"],
            "return_to": "workspace",
        },
    )

    assert response.status_code == 302
    assert response.location.endswith(
        f"/workload/assignments/workspace?version_id={context['version_id']}"
    )


def test_workspace_adds_teacher_subject_and_assigns_full_need(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(admin_id)
        _generate(context, admin_id)
        need = WorkloadNeed.query.one()
        need_id = need.id
        activity_id = need.education_activity_id
    login(admin_id)
    filters = {
        "version_id": str(context["version_id"]),
        "view": "all",
    }

    add_teacher = client.post(
        "/workload/assignments/workspace/teachers",
        data={**filters, "teacher_id": str(teacher_id)},
    )
    assert add_teacher.status_code == 302

    add_subject = client.post(
        "/workload/assignments/workspace/subjects",
        data={
            **filters,
            "teacher_id": str(teacher_id),
            "activity_plan_kind": f"{activity_id}:CURRICULUM",
        },
    )
    assert add_subject.status_code == 302

    matrix = client.get(
        "/workload/assignments/workspace",
        query_string=filters,
    )
    html = matrix.get_data(as_text=True)
    assert matrix.status_code == 200
    assert "Предмет не выбран" not in html
    assert "data-workload-cell-toggle" in html
    assert "workload-cell-entry is-available" in html
    assert "data-workload-cell-value></span>" in html
    assert 'name="hours"' in html
    assert 'type="hidden"' in html
    assert html.count('class="workload-subject-add"') == 1
    assert "Добавить предмет" in html

    assign = client.post(
        "/workload/assignments/workspace/cell",
        data={
            **filters,
            "need_id": str(need_id),
            "teacher_id": str(teacher_id),
            "hours": "5",
        },
    )
    assert assign.status_code == 302
    assigned_matrix = client.get(
        "/workload/assignments/workspace",
        query_string=filters,
    ).get_data(as_text=True)
    assert "data-workload-cell-value>5</span>" in assigned_matrix
    with app.app_context():
        assignment = WorkloadAssignment.query.one()
        assert assignment.employee_user_id == teacher_id
        assert assignment.weekly_hours == Decimal("5.000")
        assert assignment.workload_need.status == "COVERED"

    locked = client.post(
        "/workload/assignments/workspace/cell",
        data={
            **filters,
            "need_id": str(need_id),
            "teacher_id": str(admin_id),
            "hours": "5",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert locked.status_code == 422
    assert "другому преподавателю" in locked.get_json()["message"]

    client.post(
        "/workload/assignments/workspace/teachers",
        data={**filters, "teacher_id": str(admin_id)},
    )
    client.post(
        "/workload/assignments/workspace/subjects",
        data={
            **filters,
            "teacher_id": str(admin_id),
            "activity_id": str(activity_id),
            "plan_kind": "CURRICULUM",
        },
    )
    locked_matrix = client.get(
        "/workload/assignments/workspace",
        query_string=filters,
    ).get_data(as_text=True)
    assert "is-locked" in locked_matrix
    assert "Назначено другому преподавателю." in locked_matrix
    assert "disabled" in locked_matrix


def test_workspace_export_and_compact_hours(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    with app.app_context():
        context = _distribution_context(admin_id)
        _generate(context, admin_id)
    login(admin_id)

    matrix = client.get(
        "/workload/assignments/workspace",
        query_string={"version_id": context["version_id"]},
    )
    html = matrix.get_data(as_text=True)
    assert "5,000" not in html
    assert "5.000" not in html

    export = client.get(
        "/workload/assignments/workspace/export.xlsx",
        query_string={"version_id": context["version_id"]},
    )
    assert export.status_code == 200
    assert export.data.startswith(b"PK")
    assert "spreadsheetml.sheet" in export.content_type


def test_workspace_vacancy_can_be_filled_by_teacher(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(admin_id)
        _generate(context, admin_id)
        need = WorkloadNeed.query.one()
        need_id = need.id
        activity_id = need.education_activity_id
    login(admin_id)
    filters = {
        "version_id": str(context["version_id"]),
        "view": "all",
    }

    assert client.post(
        "/workload/assignments/workspace/teachers",
        data={**filters, "holder_type": "vacancy"},
    ).status_code == 302
    assert client.post(
        "/workload/assignments/workspace/subjects",
        data={
            **filters,
            "holder_type": "vacancy",
            "vacancy_key": "VACANCY_1",
            "activity_plan_kind": f"{activity_id}:CURRICULUM",
        },
    ).status_code == 302
    assigned = client.post(
        "/workload/assignments/workspace/cell",
        data={
            **filters,
            "holder_type": "vacancy",
            "vacancy_key": "VACANCY_1",
            "need_id": str(need_id),
            "hours": "5",
        },
    )
    assert assigned.status_code == 302
    with app.app_context():
        vacancy = WorkloadAssignment.query.one()
        assert vacancy.assignment_kind == "VACANCY"
        assert vacancy.employee_user_id is None
        assert vacancy.position_code == "VACANCY_1"

    vacancy_view = client.get(
        "/workload/assignments/workspace",
        query_string={**filters, "view": "vacancies"},
    ).get_data(as_text=True)
    assert "Вакансия 1" in vacancy_view
    assert "Преподаватель не назначен" in vacancy_view

    replaced = client.post(
        "/workload/assignments/workspace/holder/replace",
        data={
            **filters,
            "source_type": "vacancy",
            "source_vacancy_key": "VACANCY_1",
            "target_holder": f"teacher:{teacher_id}",
        },
    )
    assert replaced.status_code == 302
    with app.app_context():
        assignment = WorkloadAssignment.query.one()
        assert assignment.assignment_kind == "MAIN"
        assert assignment.employee_user_id == teacher_id
        assert assignment.position_code == "TEACHER"


def test_workspace_rejects_transfer_to_teacher_with_existing_load(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    source_teacher_id = make_user("TEACHER")
    occupied_teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(admin_id)
        _generate(context, admin_id)
        need = WorkloadNeed.query.one()
        source = _assignment(need, source_teacher_id, "5")
        occupied = _assignment(need, occupied_teacher_id, "1")
        occupied.workload_need_id = need.id
        db.session.add_all([source, occupied])
        db.session.commit()
    login(admin_id)

    response = client.post(
        "/workload/assignments/workspace/holder/replace",
        data={
            "version_id": str(context["version_id"]),
            "view": "all",
            "source_type": "teacher",
            "source_teacher_id": str(source_teacher_id),
            "target_holder": f"teacher:{occupied_teacher_id}",
        },
        follow_redirects=True,
    )
    assert "у Тестов Пользователь уже есть нагрузка" in response.get_data(as_text=True)
    with app.app_context():
        assert WorkloadAssignment.query.filter_by(
            employee_user_id=source_teacher_id,
        ).count() == 1


def test_workload_editor_settings_and_workspace_hide_draft_badge(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    methodist_id = make_user("METHODIST")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(admin_id)
    login(admin_id)

    settings = client.post(
        "/workload/settings/editors",
        data={"editor_ids": [str(admin_id), str(methodist_id)]},
        follow_redirects=True,
    )
    assert settings.status_code == 200
    settings_html = settings.get_data(as_text=True)
    assert "Ответственные за учебные планы и нагрузку сохранены" in settings_html
    assert f'data-editor-user data-user-id="{methodist_id}"' in settings_html
    assert f'data-editor-user data-user-id="{teacher_id}"' not in settings_html
    assert f'data-editor-option' in settings_html
    assert f'data-user-id="{teacher_id}"' in settings_html
    with app.app_context():
        assert WorkloadEditorAccess.query.filter_by(
            user_id=methodist_id,
            is_active=True,
        ).count() == 1

    workspace = client.get(
        "/workload/assignments/workspace",
        query_string={"version_id": context["version_id"]},
    ).get_data(as_text=True)
    assert "2026/2027" in workspace
    assert "Версия 1" not in workspace
    assert ">Черновик<" not in workspace


def test_department_and_workspace_read_current_load_and_mcko(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(admin_id)
        _generate(context, admin_id)
        need = WorkloadNeed.query.one()
        db.session.add(_assignment(need, teacher_id, "5"))
        db.session.add(TeacherMckoResult(
            teacher_id=teacher_id,
            education_activity_id=need.education_activity_id,
            passed_at=date(2026, 5, 26),
            expires_at=date(2029, 5, 26),
            level="HIGH",
        ))
        db.session.commit()
        year_id = context["year_id"]

    login(admin_id)
    workspace = client.get(
        "/workload/assignments/workspace",
        query_string={"version_id": context["version_id"]},
    ).get_data(as_text=True)
    assert f"/departments/teachers/{teacher_id}" in workspace
    assert "МЦКО: Математика — Высокий" in workspace
    assert "до 26.05.2029" in workspace

    load_page = client.get(
        "/departments/loads",
        query_string={"academic_year_id": year_id},
    ).get_data(as_text=True)
    assert "Данные поступают из матрицы распределения нагрузки" in load_page
    assert "Импортировать Excel" not in load_page
    assert "Математика" in load_page

    profile = client.get(
        f"/departments/teachers/{teacher_id}",
        query_string={"academic_year_id": year_id},
    )
    assert profile.status_code == 200
    profile_html = profile.get_data(as_text=True)
    assert "Профиль преподавателя" in profile_html
    assert "5 ч/нед." in profile_html
    assert "Высокий" in profile_html

    summary = client.get(
        "/departments/summary",
        query_string={
            "academic_year_id": year_id,
            "department_id": context["department_id"],
        },
    )
    summary_html = summary.get_data(as_text=True)
    assert summary.status_code == 200
    assert f"/departments/teachers/{teacher_id}" in summary_html
    assert "5" in summary_html


def test_teacher_can_view_only_own_workload(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    teacher_id = make_user("TEACHER")
    other_teacher_id = make_user("TEACHER")
    login(teacher_id)

    own = client.get(f"/workload/teachers/{teacher_id}")
    other = client.get(f"/workload/teachers/{other_teacher_id}")
    registry = client.get("/workload/assignments/")

    assert own.status_code == 200
    assert other.status_code == 403
    assert registry.status_code == 403


def test_inactive_employee_is_rejected(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context = _distribution_context(admin_id)
        _generate(context, admin_id)
        employee = db.session.get(User, teacher_id)
        employee.employment_status = "DISMISSED"
        need = WorkloadNeed.query.one()

        with pytest.raises(
            WorkloadDistributionError,
            match="неработающему",
        ):
            validate_assignment(
                need,
                _assignment(need, teacher_id, "5"),
            )


def _calculation_parameter_set(
    context,
    user_id,
    teacher_id,
    *,
    include_norm=True,
):
    version = db.session.get(TariffVersion, context["version_id"])
    parameter_set = CalculationParameterSet(
        tariff_version=version,
        code="BASE_2026",
        name="Основные параметры 2026/2027",
        valid_from=date(2026, 9, 1),
        valid_to=date(2027, 8, 31),
        student_hour_rate=Decimal("37"),
        periods_per_year=Decimal("12"),
        rounding_rule="HALF_UP",
        currency_code="RUB",
        status="DRAFT",
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    db.session.add(parameter_set)
    db.session.flush()
    coefficient_types, allowance_types = ensure_standard_tariff_types()
    if include_norm:
        db.session.add(TariffRateNorm(
            parameter_set_id=parameter_set.id,
            position_code="TEACHER",
            position_name="Учитель",
            activity_kind="SUBJECT",
            weekly_norm_hours=Decimal("18"),
            valid_from=date(2026, 9, 1),
            valid_to=date(2027, 8, 31),
            source_text="Тестовая норма",
            created_by_user_id=user_id,
        ))
    db.session.add(TariffCoefficientValue(
        parameter_set_id=parameter_set.id,
        coefficient_type_id=coefficient_types["DIVISION"].id,
        value=Decimal("25"),
        condition_kind="ALWAYS",
        condition_data={"only_above_one": True},
        priority=10,
        valid_from=date(2026, 9, 1),
        valid_to=date(2027, 8, 31),
        created_by_user_id=user_id,
    ))
    db.session.add(TariffCoefficientValue(
        parameter_set_id=parameter_set.id,
        coefficient_type_id=coefficient_types["COMPLEXITY"].id,
        value=Decimal("1.4"),
        condition_kind="ACTIVITY",
        condition_data={
            "activity_ids": [
                db.session.get(
                    TeachingGroup,
                    context["group_id"],
                ).education_activity_id,
            ],
        },
        priority=20,
        valid_from=date(2026, 9, 1),
        valid_to=date(2027, 8, 31),
        created_by_user_id=user_id,
    ))
    db.session.add(TariffAllowanceRule(
        parameter_set_id=parameter_set.id,
        allowance_type_id=allowance_types["CLASSROOM_CITY"].id,
        fixed_amount=Decimal("16000"),
        percent_value=None,
        base_kind="BASE",
        condition_data={"employee_user_ids": [teacher_id]},
        priority=30,
        valid_from=date(2026, 9, 1),
        valid_to=date(2027, 8, 31),
        source_text="Тестовая доплата",
        created_by_user_id=user_id,
    ))
    db.session.commit()
    return parameter_set.id


def _calculation_context(user_id, teacher_id, *, include_norm=True):
    context = _distribution_context(user_id)
    _generate(context, user_id)
    need = WorkloadNeed.query.one()
    assignment = _assignment(need, teacher_id, "5")
    validate_assignment(need, assignment)
    db.session.add(assignment)
    db.session.flush()
    refresh_need_status(need)
    db.session.commit()
    parameter_set_id = _calculation_parameter_set(
        context,
        user_id,
        teacher_id,
        include_norm=include_norm,
    )
    return context, assignment.id, parameter_set_id


def _workflow_context(user_id, teacher_id):
    context, assignment_id, parameter_set_id = _calculation_context(
        user_id,
        teacher_id,
    )
    version = db.session.get(TariffVersion, context["version_id"])
    version.effective_from = date(2026, 9, 1)
    version.effective_to = date(2027, 8, 31)
    version.plans[0].status = "READY"
    run, reused = calculate_tariff_version(
        version,
        db.session.get(CalculationParameterSet, parameter_set_id),
        user_id=user_id,
    )
    assert reused is False
    assert run.status == "SUCCEEDED"
    db.session.commit()
    return context, assignment_id, parameter_set_id


def test_tariff_calculation_matches_reference_formula(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, _, parameter_set_id = _calculation_context(
            admin_id,
            teacher_id,
        )
        run, reused = calculate_tariff_version(
            db.session.get(TariffVersion, context["version_id"]),
            db.session.get(CalculationParameterSet, parameter_set_id),
            user_id=admin_id,
        )
        db.session.commit()

        assert reused is False
        assert run.status == "SUCCEEDED"
        line = TariffLine.query.one()
        assert line.population_value == Decimal("15.000")
        assert line.rate_norm_hours == Decimal("18.000")
        assert line.fte_value == Decimal("0.277778")
        assert line.base_amount == Decimal("7862.50")
        assert line.total_amount == Decimal("32249.17")
        components = {
            item.component_code: item
            for item in TariffLineComponent.query.all()
        }
        assert components["DIVISION"].amount_value == Decimal("5241.67")
        assert components["COMPLEXITY"].amount_value == Decimal("3145.00")
        assert (
            components["CLASSROOM_CITY"].amount_value
            == Decimal("16000.00")
        )
        assert line.formula_snapshot["algorithm_version"] == "ALT-TARIFF-1.0"


def test_tariff_calculation_is_idempotent(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, _, parameter_set_id = _calculation_context(
            admin_id,
            teacher_id,
        )
        version = db.session.get(TariffVersion, context["version_id"])
        parameter_set = db.session.get(
            CalculationParameterSet,
            parameter_set_id,
        )
        first, first_reused = calculate_tariff_version(
            version,
            parameter_set,
            user_id=admin_id,
        )
        db.session.commit()
        second, second_reused = calculate_tariff_version(
            version,
            parameter_set,
            user_id=admin_id,
        )

        assert first_reused is False
        assert second_reused is True
        assert second.id == first.id
        assert TariffCalculationRun.query.count() == 1
        assert TariffLine.query.count() == 1


def test_missing_rate_norm_produces_failed_diagnostic_run(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, _, parameter_set_id = _calculation_context(
            admin_id,
            teacher_id,
            include_norm=False,
        )
        run, reused = calculate_tariff_version(
            db.session.get(TariffVersion, context["version_id"]),
            db.session.get(CalculationParameterSet, parameter_set_id),
            user_id=admin_id,
        )
        db.session.commit()

        assert reused is False
        assert run.status == "FAILED"
        assert run.summary_data["error_count"] == 1
        assert "норма ставки" in run.error_text
        assert TariffLine.query.count() == 0


def test_retired_tariffication_and_integration_routes_return_404(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    login(admin_id)

    for path in (
        "/workload/tariffication/",
        "/workload/tariffication/runs/1",
        "/workload/tariffication/lines/1",
        "/workload/tariffication/settings/",
        "/workload/tariffication/settings/1",
        "/workload/integration/",
    ):
        assert client.get(path).status_code == 404
    for path in (
        "/workload/tariffication/calculate",
        "/workload/tariffication/settings/new",
        "/workload/integration/reconcile",
        "/workload/integration/source",
    ):
        assert client.post(path).status_code == 404


def test_workflow_validation_blocks_incomplete_draft(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, _, parameter_set_id = _calculation_context(
            admin_id,
            teacher_id,
        )
        version = db.session.get(TariffVersion, context["version_id"])
        version.effective_from = date(2026, 9, 1)
        calculate_tariff_version(
            version,
            db.session.get(CalculationParameterSet, parameter_set_id),
            user_id=admin_id,
        )
        validation = run_full_validation(version, user_id=admin_id)
        db.session.commit()

        assert validation.status == "FAILED"
        assert any(
            issue.rule_code == "WF-PLAN-NOT-READY"
            for issue in validation.issues
        )
        run, cycle = start_review(version, user_id=admin_id)
        assert run.status == "FAILED"
        assert cycle is None
        assert version.status == "DRAFT"


def test_sequential_reviews_approve_and_activate_version(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, _, _ = _workflow_context(admin_id, teacher_id)
        version = db.session.get(TariffVersion, context["version_id"])
        validation, cycle = start_review(version, user_id=admin_id)
        assert validation.status == "PASSED"
        assert version.status == "VALIDATION"

        for stage in ("ACADEMIC", "HR", "FINANCE"):
            record_review_decision(
                version,
                cycle,
                review_stage=stage,
                decision="APPROVED",
                comment=f"Этап {stage} проверен",
                user_id=admin_id,
            )
        assert version.status == "APPROVAL"
        assert TariffReviewDecision.query.count() == 3

        approval = approve_version(
            version,
            decision="APPROVED",
            comment="Утверждаю",
            effective_from=date(2026, 9, 1),
            user_id=admin_id,
            today=date(2026, 9, 1),
        )
        db.session.commit()

        assert approval.decision == "APPROVED"
        assert version.status == "EFFECTIVE"
        assert version.checksum
        assert version.plans[0].status == "LOCKED"
        assert version.calculation_parameter_sets[0].status == "LOCKED"
        assignment = WorkloadAssignment.query.one()
        assert assignment.status == "CONFIRMED"
        assert [item.to_status for item in version.status_history] == [
            "DRAFT",
            "VALIDATION",
            "APPROVAL",
            "APPROVED",
            "EFFECTIVE",
        ]


def test_reviews_must_follow_required_order(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, _, _ = _workflow_context(admin_id, teacher_id)
        version = db.session.get(TariffVersion, context["version_id"])
        _, cycle = start_review(version, user_id=admin_id)

        with pytest.raises(
            TariffWorkflowError,
            match="последовательно",
        ):
            record_review_decision(
                version,
                cycle,
                review_stage="HR",
                decision="APPROVED",
                comment=None,
                user_id=admin_id,
            )


def test_returned_review_comment_requires_answer_and_author_close(
    app,
    make_user,
):
    admin_id = make_user("ADMIN")
    deputy_id = make_user("DEPUTY_DIRECTOR")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, _, _ = _workflow_context(admin_id, teacher_id)
        version = db.session.get(TariffVersion, context["version_id"])
        _, cycle = start_review(version, user_id=admin_id)
        record_review_decision(
            version,
            cycle,
            review_stage="ACADEMIC",
            decision="CHANGES_REQUESTED",
            comment="Уточнить период нагрузки",
            user_id=admin_id,
        )
        comment = TariffReviewComment.query.one()

        assert version.status == "DRAFT"
        assert cycle.status == "RETURNED"
        assert comment.status == "OPEN"
        answer_review_comment(
            comment,
            response_text="Период проверен и исправлен",
            user_id=deputy_id,
        )
        with pytest.raises(TariffWorkflowError, match="только его автор"):
            close_review_comment(comment, user_id=deputy_id)
        close_review_comment(comment, user_id=admin_id)
        assert comment.status == "CLOSED"


def test_stale_calculation_blocks_review(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, assignment_id, _ = _workflow_context(admin_id, teacher_id)
        version = db.session.get(TariffVersion, context["version_id"])
        assignment = db.session.get(WorkloadAssignment, assignment_id)
        assignment.weekly_hours = Decimal("4")
        assignment.annual_hours = Decimal("136")
        assignment.revision += 1
        validation = run_full_validation(version, user_id=admin_id)

        assert validation.status == "FAILED"
        assert any(
            issue.rule_code == "WF-CALCULATION-STALE"
            for issue in validation.issues
        )


def test_correction_clones_source_without_calculation(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, _, _ = _workflow_context(admin_id, teacher_id)
        source = db.session.get(TariffVersion, context["version_id"])
        _, cycle = start_review(source, user_id=admin_id)
        for stage in ("ACADEMIC", "HR", "FINANCE"):
            record_review_decision(
                source,
                cycle,
                review_stage=stage,
                decision="APPROVED",
                comment=None,
                user_id=admin_id,
            )
        approve_version(
            source,
            decision="APPROVED",
            comment=None,
            effective_from=date(2026, 9, 1),
            user_id=admin_id,
            today=date(2026, 9, 1),
        )
        target = clone_correction_version(
            source,
            effective_from=date(2027, 1, 15),
            reason_text="Изменение нагрузки с 15 января",
            user_id=admin_id,
        )
        db.session.commit()

        assert target.status == "DRAFT"
        assert target.origin_version_id == source.id
        assert target.calculation_runs == []
        assert len(target.plans) == len(source.plans)
        assert target.plans[0].status == "DRAFT"
        copied = WorkloadAssignment.query.filter_by(
            tariff_version_id=target.id,
        ).one()
        assert copied.origin_assignment_id is not None
        assert copied.date_from == date(2027, 1, 15)
        assert copied.revision == 1


def test_project_and_official_documents_are_versioned(app, make_user):
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, _, _ = _workflow_context(admin_id, teacher_id)
        version = db.session.get(TariffVersion, context["version_id"])
        project = generate_tariff_document(
            version,
            document_type="PERSONAL_TARIFF",
            employee_user_id=teacher_id,
            user_id=admin_id,
        )
        db.session.commit()
        assert project.status == "PROJECT"
        assert resolve_artifact_path(project).suffix == ".docx"

        _, cycle = start_review(version, user_id=admin_id)
        for stage in ("ACADEMIC", "HR", "FINANCE"):
            record_review_decision(
                version,
                cycle,
                review_stage=stage,
                decision="APPROVED",
                comment=None,
                user_id=admin_id,
            )
        approve_version(
            version,
            decision="APPROVED",
            comment=None,
            effective_from=date(2026, 9, 1),
            user_id=admin_id,
            today=date(2026, 9, 1),
        )
        official = generate_tariff_document(
            version,
            document_type="PERSONAL_TARIFF",
            employee_user_id=teacher_id,
            user_id=admin_id,
        )
        db.session.commit()

        assert official.status == "OFFICIAL"
        assert official.revision_no == 2
        assert official.version_checksum == version.checksum
        assert TariffDocumentArtifact.query.count() == 2
        assert resolve_artifact_path(official).is_file()


def test_workflow_routes_and_permissions(app, client, make_user, login):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    deputy_id = make_user("DEPUTY_DIRECTOR")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, _, _ = _workflow_context(admin_id, teacher_id)
        version = db.session.get(TariffVersion, context["version_id"])
        _, cycle = start_review(version, user_id=admin_id)
        db.session.commit()
        cycle_id = cycle.id

    login(admin_id)
    workflow_page = client.get(
        f"/workload/workflow/?version_id={context['version_id']}"
    )
    assert workflow_page.status_code == 200
    workflow_html = workflow_page.get_data(as_text=True)
    assert "workload-control-nav" in workflow_html
    assert "workload-control-counts" in workflow_html
    assert "Тарификация" not in workflow_html
    assert "Источник кафедр" not in workflow_html
    assert "/workload/integration" not in workflow_html
    documents_page = client.get(
        f"/workload/documents/?version_id={context['version_id']}"
    )
    assert documents_page.status_code == 200
    documents_html = documents_page.get_data(as_text=True)
    assert "workload-control-nav" in documents_html
    assert "workload-control-summary" in documents_html
    assert "Документы учебных планов и нагрузки" in documents_html
    assert "Тарификация" not in documents_html
    assert "Источник кафедр" not in documents_html
    assert "Пакет версии" not in documents_html

    login(deputy_id)
    forbidden = client.post(
        f"/workload/workflow/reviews/{cycle_id}/decision",
        data={"review_stage": "FINANCE", "decision": "APPROVED"},
    )
    assert forbidden.status_code == 403


def _effective_integration_context(app, admin_id, teacher_id, legacy_hours):
    context, assignment_id, _ = _workflow_context(admin_id, teacher_id)
    version = db.session.get(TariffVersion, context["version_id"])
    version.status = "EFFECTIVE"
    version.effective_at = datetime.utcnow()
    assignment = db.session.get(WorkloadAssignment, assignment_id)
    assignment.status = "CONFIRMED"
    activity = assignment.workload_need.education_activity
    subject = Subject(
        name=f"{activity.name} {context['version_id']}",
        education_activity_id=activity.id,
    )
    db.session.add(subject)
    db.session.flush()
    group = assignment.workload_need.teaching_group
    year = version.tariff_cycle.academic_year
    db.session.add(TeacherLoad(
        teacher_id=teacher_id,
        subject_id=subject.id,
        academic_year_id=year.id,
        department_id=assignment.department_id,
        building_id=assignment.building_id,
        class_name=group.name,
        group_name=group.name,
        hours=float(legacy_hours),
        subject_name=subject.name,
        building_name=assignment.building.name,
    ))
    db.session.commit()
    return context, version, year


def test_stage_eight_reconciles_switches_and_rolls_back(
    app,
    make_user,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_NEW_SOURCE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        context, version, year = _effective_integration_context(
            app,
            admin_id,
            teacher_id,
            "5",
        )

        run = reconcile_workload_sources(version, user_id=admin_id)
        assert run.status == "PASSED"
        assert run.blocking_count == 0
        assert run.internal_row_count == 1

        switch_workload_source(
            year,
            mode="COMPARE",
            tariff_version=version,
            user_id=admin_id,
            reason="Параллельная проверка",
        )
        switch_workload_source(
            year,
            mode="INTERNAL",
            tariff_version=version,
            user_id=admin_id,
            reason="Сверка завершена",
        )
        db.session.commit()

        state = source_state(year.id)
        assert state.configured_mode == "INTERNAL"
        assert state.effective_mode == "INTERNAL"
        rows = internal_department_load_rows(
            version,
            department_id=context["department_id"],
        )
        assert len(rows) == 1
        assert rows[0].hours == 5.0
        assert rows[0].teacher.id == teacher_id

        switch_workload_source(
            year,
            mode="LEGACY",
            tariff_version=version,
            user_id=admin_id,
            reason="Проверка аварийного отката",
        )
        db.session.commit()
        assert source_state(year.id).effective_mode == "LEGACY"
        assert WorkloadSourceTransition.query.count() == 3


def test_stage_eight_blocks_cutover_when_hours_differ(app, make_user):
    app.config["FEATURE_WORKLOAD_NEW_SOURCE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        _, version, year = _effective_integration_context(
            app,
            admin_id,
            teacher_id,
            "4",
        )
        run = reconcile_workload_sources(version, user_id=admin_id)
        assert run.status == "FAILED"
        assert run.blocking_count == 1

        with pytest.raises(
            WorkloadIntegrationError,
            match="успешная сверка",
        ):
            switch_workload_source(
                year,
                mode="INTERNAL",
                tariff_version=version,
                user_id=admin_id,
                reason="Нельзя применять",
            )


def test_stage_eight_feature_flag_forces_legacy_fallback(app, make_user):
    admin_id = make_user("ADMIN")
    with app.app_context():
        year = AcademicYear(
            name="2030/2031",
            is_current=True,
            start_date=date(2030, 9, 1),
            end_date=date(2031, 8, 31),
        )
        db.session.add(year)
        db.session.flush()
        db.session.add(WorkloadSourceSetting(
            academic_year_id=year.id,
            source_mode="INTERNAL",
            revision=2,
            change_reason="Тест",
            changed_by_user_id=admin_id,
        ))
        db.session.commit()

        app.config["FEATURE_WORKLOAD_NEW_SOURCE_ENABLED"] = False
        state = source_state(year.id)
        assert state.configured_mode == "INTERNAL"
        assert state.effective_mode == "LEGACY"


def test_internal_department_load_remains_available_without_integration_page(
    app,
    client,
    make_user,
    login,
):
    app.config["FEATURE_WORKLOAD_MODULE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_WRITE_ENABLED"] = True
    app.config["FEATURE_WORKLOAD_NEW_SOURCE_ENABLED"] = True
    admin_id = make_user("ADMIN")
    teacher_id = make_user("TEACHER")
    with app.app_context():
        _, version, year = _effective_integration_context(
            app,
            admin_id,
            teacher_id,
            "5",
        )
        run = reconcile_workload_sources(version, user_id=admin_id)
        switch_workload_source(
            year,
            mode="INTERNAL",
            tariff_version=version,
            user_id=admin_id,
            reason="Тест маршрута",
        )
        db.session.commit()
        run_id = run.id
        year_id = year.id

    login(admin_id)
    integration_page = client.get(
        f"/workload/integration/?academic_year_id={year_id}&run_id={run_id}"
    )
    assert integration_page.status_code == 404

    load_page = client.get(
        f"/departments/loads?academic_year_id={year_id}"
    )
    assert load_page.status_code == 200
    html = load_page.get_data(as_text=True)
    assert "данные поступают из матрицы распределения нагрузки" in html.lower()
    assert "Импортировать Excel" not in html
    assert "Добавить нагрузку вручную" not in html
