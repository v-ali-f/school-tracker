import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timedelta

from sqlalchemy import func

from app.core.extensions import db
from app.models import (
    CalculationParameterSet,
    EducationPlan,
    EducationPlanLine,
    EducationPlanLinePeriod,
    EducationPlanLineScope,
    PopulationSnapshot,
    PopulationSnapshotClass,
    PopulationSnapshotEnrollment,
    TariffAllowanceRule,
    TariffApprovalDecision,
    TariffCoefficientValue,
    TariffRateNorm,
    TariffReviewComment,
    TariffReviewCycle,
    TariffReviewDecision,
    TariffValidationIssue,
    TariffValidationRun,
    TariffVersion,
    TariffVersionStatusHistory,
    TeachingGroup,
    TeachingGroupClass,
    TeachingGroupMember,
    TeachingMetagroupSource,
    WorkloadAssignment,
    WorkloadNeed,
    WorkloadNeedSource,
)
from app.services.tariff_calculation_service import (
    current_tariff_input_hash,
    latest_successful_run,
)


RULE_SET_VERSION = "ALT-WORKFLOW-1.0"
REVIEW_STAGE_ORDER = ("ACADEMIC", "HR", "FINANCE")
BLOCKING_SEVERITIES = {"BLOCKER", "ERROR"}


class TariffWorkflowError(ValueError):
    pass


class TariffWorkflowValidationError(TariffWorkflowError):
    """A business rejection whose validation result must remain in history."""


def _hash_payload(payload):
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _transition(version, to_status, *, user_id, comment=None):
    from_status = version.status
    if from_status == to_status:
        return
    version.status = to_status
    version.revision += 1
    version.updated_by_user_id = user_id
    db.session.add(TariffVersionStatusHistory(
        tariff_version_id=version.id,
        from_status=from_status,
        to_status=to_status,
        changed_by_user_id=user_id,
        comment=comment,
    ))


def latest_validation_run(version_id):
    return (
        TariffValidationRun.query
        .filter_by(tariff_version_id=version_id)
        .order_by(TariffValidationRun.run_no.desc())
        .first()
    )


def latest_review_cycle(version_id):
    return (
        TariffReviewCycle.query
        .filter_by(tariff_version_id=version_id)
        .order_by(TariffReviewCycle.round_no.desc())
        .first()
    )


def review_stage_state(cycle):
    cycle_decisions = (
        TariffReviewDecision.query
        .filter_by(review_cycle_id=cycle.id)
        .order_by(TariffReviewDecision.id.asc())
        .all()
        if cycle is not None and cycle.id is not None
        else []
    )
    decisions = {
        item.review_stage: item
        for item in cycle_decisions
    }
    if cycle is None or cycle.status != "OPEN":
        return decisions, None
    for stage in REVIEW_STAGE_ORDER:
        decision = decisions.get(stage)
        if decision is None:
            return decisions, stage
        if decision.decision != "APPROVED":
            return decisions, None
    return decisions, None


def _validation_payload(version, calculation_run):
    return {
        "version_id": version.id,
        "version_revision": version.revision,
        "status": version.status,
        "effective_from": version.effective_from,
        "plans": [
            (item.id, item.revision, item.status)
            for item in sorted(version.plans, key=lambda row: row.id)
        ],
        "groups": [
            (item.id, item.revision, item.status, item.actual_size)
            for item in sorted(
                version.teaching_groups,
                key=lambda row: row.id,
            )
        ],
        "needs": [
            (item.id, item.revision, item.status)
            for item in sorted(
                version.workload_needs,
                key=lambda row: row.id,
            )
        ],
        "assignments": [
            (item.id, item.revision, item.status, item.employee_user_id)
            for item in WorkloadAssignment.query
            .filter_by(tariff_version_id=version.id)
            .order_by(WorkloadAssignment.id.asc())
            .all()
        ],
        "calculation_run": (
            (
                calculation_run.id,
                calculation_run.input_hash,
                calculation_run.status,
            )
            if calculation_run else None
        ),
    }


def _issue(rule_code, severity, message, remediation, obj=None):
    object_type = obj.__class__.__name__ if obj is not None else None
    object_id = getattr(obj, "id", None)
    fingerprint = _hash_payload({
        "rule_code": rule_code,
        "object_type": object_type,
        "object_id": object_id,
        "message": message,
    })
    return {
        "rule_code": rule_code,
        "severity": severity,
        "object_type": object_type,
        "object_id": object_id,
        "message": message,
        "remediation": remediation,
        "fingerprint": fingerprint,
    }


def collect_validation_issues(version, calculation_run):
    issues = []
    year = version.tariff_cycle.academic_year
    if version.effective_from is None:
        issues.append(_issue(
            "WF-EFFECTIVE-DATE",
            "BLOCKER",
            "Не указана дата начала действия версии.",
            "Укажите дату начала действия в пределах учебного года.",
            version,
        ))
    elif not (year.start_date <= version.effective_from <= year.end_date):
        issues.append(_issue(
            "WF-EFFECTIVE-RANGE",
            "BLOCKER",
            "Дата начала действия выходит за пределы учебного года.",
            "Исправьте дату начала действия версии.",
            version,
        ))
    if version.version_type in {"CORRECTION", "EMERGENCY"} and not (
        version.reason_text or ""
    ).strip():
        issues.append(_issue(
            "WF-CORRECTION-REASON",
            "ERROR",
            "Для версии изменения отсутствует основание.",
            "Укажите причину и документальное основание изменения.",
            version,
        ))

    plans = list(version.plans)
    if not plans:
        issues.append(_issue(
            "WF-PLAN-MISSING",
            "BLOCKER",
            "В версии отсутствует учебный план.",
            "Создайте хотя бы один план и подготовьте его к проверке.",
            version,
        ))
    for plan in plans:
        if plan.status == "DRAFT":
            issues.append(_issue(
                "WF-PLAN-NOT-READY",
                "ERROR",
                f"План «{plan.name}» остаётся черновиком.",
                "Переведите план в состояние готовности.",
                plan,
            ))
        if not plan.lines:
            issues.append(_issue(
                "WF-PLAN-EMPTY",
                "ERROR",
                f"План «{plan.name}» не содержит строк.",
                "Добавьте дисциплины и часы.",
                plan,
            ))

    groups = list(version.teaching_groups)
    if not groups:
        issues.append(_issue(
            "WF-GROUPS-MISSING",
            "BLOCKER",
            "В версии отсутствуют учебные группы.",
            "Сформируйте группы по строкам учебного плана.",
            version,
        ))
    for group in groups:
        if group.status != "READY":
            issues.append(_issue(
                "WF-GROUP-NOT-READY",
                "ERROR",
                f"Группа «{group.name}» не готова к тарификации.",
                "Проверьте состав и переведите группу в статус «Готова».",
                group,
            ))
        if (group.actual_size or group.planned_size or 0) <= 0:
            issues.append(_issue(
                "WF-GROUP-POPULATION",
                "ERROR",
                f"У группы «{group.name}» отсутствует численность.",
                "Укажите фактическую или плановую численность.",
                group,
            ))

    needs = list(version.workload_needs)
    if not needs:
        issues.append(_issue(
            "WF-NEEDS-MISSING",
            "BLOCKER",
            "Потребность в педагогических часах не сформирована.",
            "Сформируйте потребности из готовых групп.",
            version,
        ))
    for need in needs:
        if need.status == "CANCELLED":
            continue
        if need.status != "COVERED":
            issues.append(_issue(
                "WF-NEED-NOT-COVERED",
                "ERROR",
                "Потребность распределена не полностью "
                f"({need.remaining_weekly_hours} ч. в неделю).",
                "Назначьте педагога на остаток часов.",
                need,
            ))

    assignments = (
        WorkloadAssignment.query
        .filter(
            WorkloadAssignment.tariff_version_id == version.id,
            WorkloadAssignment.status != "CANCELLED",
        )
        .all()
    )
    for assignment in assignments:
        if assignment.assignment_kind == "VACANCY":
            issues.append(_issue(
                "WF-VACANCY",
                "WARNING",
                "В версии присутствует вакантная нагрузка.",
                "Назначьте педагога или отразите вакансию в пакете.",
                assignment,
            ))
            continue
        employee = assignment.employee
        if (
            employee is None
            or not employee.is_active_user
            or employee.employment_status != "ACTIVE"
            or employee.archived_at is not None
        ):
            issues.append(_issue(
                "WF-EMPLOYEE-INACTIVE",
                "ERROR",
                "Назначение связано с неактивным сотрудником.",
                "Исправьте кадровое назначение.",
                assignment,
            ))
        if (
            version.version_type in {"CORRECTION", "EMERGENCY"}
            and assignment.origin_assignment_id is not None
            and assignment.revision == 1
        ):
            issues.append(_issue(
                "WF-CORRECTION-HOURS-REVIEW",
                "ERROR",
                "Скопированная строка изменения ещё не проверена "
                "для нового периода.",
                "Откройте назначение, проверьте недельные и годовые часы "
                "и сохраните строку с основанием.",
                assignment,
            ))

    if calculation_run is None:
        issues.append(_issue(
            "WF-CALCULATION-MISSING",
            "BLOCKER",
            "Нет успешного расчёта тарификации.",
            "Выполните расчёт после завершения распределения нагрузки.",
            version,
        ))
    else:
        current_hash = current_tariff_input_hash(
            version,
            calculation_run.parameter_set,
        )
        if current_hash != calculation_run.input_hash:
            issues.append(_issue(
                "WF-CALCULATION-STALE",
                "BLOCKER",
                "Расчёт устарел после изменения исходных данных.",
                "Повторно выполните расчёт тарификации.",
                calculation_run,
            ))

    open_blocking = (
        TariffReviewComment.query
        .filter(
            TariffReviewComment.tariff_version_id == version.id,
            TariffReviewComment.comment_kind == "BLOCKING",
            TariffReviewComment.status != "CLOSED",
        )
        .count()
    )
    if open_blocking:
        issues.append(_issue(
            "WF-OPEN-REVIEW-COMMENTS",
            "BLOCKER",
            f"Не закрыто блокирующих замечаний: {open_blocking}.",
            "Ответьте на замечания и получите подтверждение проверяющего.",
            version,
        ))
    return issues


def run_full_validation(version, *, user_id):
    started_at = datetime.utcnow()
    calculation_run = latest_successful_run(version.id)
    payload = _validation_payload(version, calculation_run)
    input_hash = _hash_payload(payload)
    issues = collect_validation_issues(version, calculation_run)
    counts = {
        severity: sum(
            1 for item in issues if item["severity"] == severity
        )
        for severity in ("BLOCKER", "ERROR", "WARNING", "INFO")
    }
    status = (
        "FAILED"
        if counts["BLOCKER"] or counts["ERROR"]
        else "PASSED"
    )
    run_no = (
        db.session.query(func.max(TariffValidationRun.run_no))
        .filter(TariffValidationRun.tariff_version_id == version.id)
        .scalar()
        or 0
    ) + 1
    run = TariffValidationRun(
        tariff_version_id=version.id,
        calculation_run_id=calculation_run.id if calculation_run else None,
        run_no=run_no,
        status=status,
        rule_set_version=RULE_SET_VERSION,
        input_hash=input_hash,
        summary_data={
            "counts": counts,
            "issue_count": len(issues),
            "blocking_count": counts["BLOCKER"] + counts["ERROR"],
        },
        started_at=started_at,
        finished_at=datetime.utcnow(),
        created_by_user_id=user_id,
    )
    db.session.add(run)
    db.session.flush()
    for item in issues:
        db.session.add(TariffValidationIssue(
            validation_run_id=run.id,
            tariff_version_id=version.id,
            **item,
        ))
    return run


def start_review(version, *, user_id):
    if version.status != "DRAFT":
        raise TariffWorkflowError(
            "На проверку можно направить только черновую версию."
        )
    run = run_full_validation(version, user_id=user_id)
    if run.status != "PASSED":
        return run, None
    round_no = (
        db.session.query(func.max(TariffReviewCycle.round_no))
        .filter(TariffReviewCycle.tariff_version_id == version.id)
        .scalar()
        or 0
    ) + 1
    cycle = TariffReviewCycle(
        tariff_version_id=version.id,
        validation_run_id=run.id,
        round_no=round_no,
        status="OPEN",
        started_by_user_id=user_id,
    )
    db.session.add(cycle)
    _transition(
        version,
        "VALIDATION",
        user_id=user_id,
        comment=f"Запущен цикл согласования № {round_no}.",
    )
    return run, cycle


def add_review_comment(
    cycle,
    *,
    review_stage,
    comment_kind,
    text,
    user_id,
    object_type=None,
    object_id=None,
    enforce_current_stage=True,
):
    if cycle.status != "OPEN":
        raise TariffWorkflowError("Цикл согласования уже завершён.")
    if review_stage not in REVIEW_STAGE_ORDER:
        raise TariffWorkflowError("Неизвестный этап согласования.")
    _, expected_stage = review_stage_state(cycle)
    if enforce_current_stage and review_stage != expected_stage:
        raise TariffWorkflowError(
            "Замечания оформляются на текущем этапе согласования."
        )
    if comment_kind not in {"BLOCKING", "RECOMMENDATION"}:
        raise TariffWorkflowError("Неизвестный вид замечания.")
    normalized = " ".join((text or "").split())
    if not normalized:
        raise TariffWorkflowError("Введите текст замечания.")
    item = TariffReviewComment(
        review_cycle_id=cycle.id,
        tariff_version_id=cycle.tariff_version_id,
        review_stage=review_stage,
        comment_kind=comment_kind,
        status="OPEN",
        object_type=(object_type or "").strip() or None,
        object_id=object_id,
        text=normalized,
        created_by_user_id=user_id,
    )
    db.session.add(item)
    return item


def answer_review_comment(comment, *, response_text, user_id):
    if comment.status == "CLOSED":
        raise TariffWorkflowError("Замечание уже закрыто.")
    normalized = " ".join((response_text or "").split())
    if not normalized:
        raise TariffWorkflowError("Введите ответ на замечание.")
    comment.response_text = normalized
    comment.status = "ANSWERED"
    comment.answered_by_user_id = user_id
    comment.answered_at = datetime.utcnow()
    return comment


def close_review_comment(comment, *, user_id):
    if comment.created_by_user_id != user_id:
        raise TariffWorkflowError(
            "Закрыть замечание может только его автор."
        )
    if comment.status != "ANSWERED":
        raise TariffWorkflowError(
            "Перед закрытием замечания требуется ответ."
        )
    comment.status = "CLOSED"
    comment.closed_by_user_id = user_id
    comment.closed_at = datetime.utcnow()
    return comment


def record_review_decision(
    version,
    cycle,
    *,
    review_stage,
    decision,
    comment,
    user_id,
):
    if version.status != "VALIDATION" or cycle.status != "OPEN":
        raise TariffWorkflowError("Версия не находится на согласовании.")
    decisions, expected_stage = review_stage_state(cycle)
    if review_stage != expected_stage:
        raise TariffWorkflowError(
            "Заключения должны оформляться последовательно."
        )
    if review_stage in decisions:
        raise TariffWorkflowError("Заключение этапа уже сохранено.")
    if decision not in {"APPROVED", "CHANGES_REQUESTED"}:
        raise TariffWorkflowError("Выберите допустимое решение.")
    normalized = " ".join((comment or "").split())
    if decision == "CHANGES_REQUESTED" and not normalized:
        raise TariffWorkflowError(
            "При возврате укажите причину и требуемое исправление."
        )
    open_stage_comments = (
        TariffReviewComment.query
        .filter(
            TariffReviewComment.review_cycle_id == cycle.id,
            TariffReviewComment.review_stage == review_stage,
            TariffReviewComment.comment_kind == "BLOCKING",
            TariffReviewComment.status != "CLOSED",
        )
        .count()
    )
    if decision == "APPROVED" and open_stage_comments:
        raise TariffWorkflowError(
            "Нельзя согласовать этап с открытыми блокирующими замечаниями."
        )
    item = TariffReviewDecision(
        review_cycle_id=cycle.id,
        tariff_version_id=version.id,
        review_stage=review_stage,
        decision=decision,
        comment=normalized or None,
        validation_input_hash=cycle.validation_run.input_hash,
        decided_by_user_id=user_id,
    )
    db.session.add(item)
    if decision == "CHANGES_REQUESTED":
        add_review_comment(
            cycle,
            review_stage=review_stage,
            comment_kind="BLOCKING",
            text=normalized,
            user_id=user_id,
            enforce_current_stage=False,
        )
        cycle.status = "RETURNED"
        cycle.completed_at = datetime.utcnow()
        _transition(
            version,
            "DRAFT",
            user_id=user_id,
            comment=f"Возврат с этапа {review_stage}: {normalized}",
        )
    elif review_stage == "FINANCE":
        cycle.status = "COMPLETED"
        cycle.completed_at = datetime.utcnow()
        _transition(
            version,
            "APPROVAL",
            user_id=user_id,
            comment="Все обязательные заключения получены.",
        )
    return item


def version_checksum(version, calculation_run=None):
    run = calculation_run or latest_successful_run(version.id)
    if run is None:
        raise TariffWorkflowError("Нет успешного расчётного снимка.")
    payload = {
        "version": {
            "id": version.id,
            "version_no": version.version_no,
            "version_type": version.version_type,
            "effective_from": version.effective_from,
            "effective_to": version.effective_to,
            "origin_version_id": version.origin_version_id,
            "reason_text": version.reason_text,
        },
        "calculation": {
            "id": run.id,
            "input_hash": run.input_hash,
            "algorithm_version": run.algorithm_version,
            "lines": [
                (line.id, line.line_hash, str(line.total_amount))
                for line in sorted(run.lines, key=lambda row: row.id)
            ],
        },
        "reviews": [
            (
                item.review_stage,
                item.decision,
                item.validation_input_hash,
                item.decided_by_user_id,
                item.decided_at,
            )
            for item in (
                TariffReviewDecision.query
                .filter_by(tariff_version_id=version.id)
                .order_by(
                    TariffReviewDecision.review_cycle_id.asc(),
                    TariffReviewDecision.id.asc(),
                )
                .all()
            )
        ],
    }
    return _hash_payload(payload)


def _activate_version(version, *, user_id, now=None):
    today = now or date.today()
    if version.status != "APPROVED":
        raise TariffWorkflowError(
            "Ввести в действие можно только утверждённую версию."
        )
    if version.effective_from is None or version.effective_from > today:
        raise TariffWorkflowError(
            "Дата начала действия версии ещё не наступила."
        )
    previous = (
        TariffVersion.query
        .filter(
            TariffVersion.tariff_cycle_id == version.tariff_cycle_id,
            TariffVersion.id != version.id,
            TariffVersion.status == "EFFECTIVE",
        )
        .order_by(TariffVersion.effective_from.desc())
        .first()
    )
    if previous is not None:
        previous.effective_to = version.effective_from - timedelta(days=1)
        _transition(
            previous,
            "SUPERSEDED",
            user_id=user_id,
            comment=f"Заменена версией № {version.version_no}.",
        )
    version.effective_at = datetime.utcnow()
    _transition(
        version,
        "EFFECTIVE",
        user_id=user_id,
        comment="Версия введена в действие.",
    )
    return version


def approve_version(
    version,
    *,
    decision,
    comment,
    effective_from,
    user_id,
    today=None,
):
    if version.status != "APPROVAL":
        raise TariffWorkflowError("Версия не передана на утверждение.")
    cycle = latest_review_cycle(version.id)
    if cycle is None or cycle.status != "COMPLETED":
        raise TariffWorkflowError("Не завершён обязательный цикл проверок.")
    if decision not in {"APPROVED", "REJECTED"}:
        raise TariffWorkflowError("Выберите допустимое решение директора.")
    normalized = " ".join((comment or "").split())
    if decision == "REJECTED" and not normalized:
        raise TariffWorkflowError("При отказе требуется мотивировка.")
    version.effective_from = effective_from
    validation = None
    if decision == "APPROVED":
        validation = run_full_validation(version, user_id=user_id)
        if validation.status != "PASSED":
            raise TariffWorkflowValidationError(
                "Повторная проверка перед утверждением выявила ошибки."
            )
    checksum = version_checksum(
        version,
        validation.calculation_run if validation is not None else None,
    )
    decision_no = (
        db.session.query(func.max(TariffApprovalDecision.decision_no))
        .filter(TariffApprovalDecision.tariff_version_id == version.id)
        .scalar()
        or 0
    ) + 1
    approval = TariffApprovalDecision(
        tariff_version_id=version.id,
        review_cycle_id=cycle.id,
        decision_no=decision_no,
        decision=decision,
        comment=normalized or None,
        version_checksum=checksum,
        effective_from=effective_from,
        decided_by_user_id=user_id,
    )
    db.session.add(approval)
    if decision == "REJECTED":
        cycle.status = "RETURNED"
        _transition(
            version,
            "DRAFT",
            user_id=user_id,
            comment=f"Отказ в утверждении: {normalized}",
        )
        return approval
    version.checksum = checksum
    version.approved_at = datetime.utcnow()
    for plan in version.plans:
        plan.status = "LOCKED"
    for parameter_set in version.calculation_parameter_sets:
        parameter_set.status = "LOCKED"
    for assignment in WorkloadAssignment.query.filter(
        WorkloadAssignment.tariff_version_id == version.id,
        WorkloadAssignment.status != "CANCELLED",
    ):
        assignment.status = "CONFIRMED"
    _transition(
        version,
        "APPROVED",
        user_id=user_id,
        comment=normalized or "Версия утверждена.",
    )
    if effective_from <= (today or date.today()):
        _activate_version(version, user_id=user_id, now=today)
    return approval


def activate_due_version(version, *, user_id, today=None):
    return _activate_version(version, user_id=user_id, now=today)


def clone_correction_version(
    source,
    *,
    effective_from,
    reason_text,
    user_id,
):
    if source.status not in {"APPROVED", "EFFECTIVE", "SUPERSEDED"}:
        raise TariffWorkflowError(
            "Версию изменения можно создать только из утверждённой версии."
        )
    reason = " ".join((reason_text or "").split())
    if not reason:
        raise TariffWorkflowError("Укажите основание изменения.")
    year = source.tariff_cycle.academic_year
    if not (year.start_date <= effective_from <= year.end_date):
        raise TariffWorkflowError(
            "Дата изменения выходит за пределы учебного года."
        )
    next_no = (
        db.session.query(func.max(TariffVersion.version_no))
        .filter(TariffVersion.tariff_cycle_id == source.tariff_cycle_id)
        .scalar()
        or 0
    ) + 1
    target = TariffVersion(
        tariff_cycle_id=source.tariff_cycle_id,
        version_no=next_no,
        version_type="CORRECTION",
        status="DRAFT",
        effective_from=effective_from,
        effective_to=year.end_date,
        origin_version_id=source.id,
        reason_text=reason,
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    db.session.add(target)
    db.session.flush()
    db.session.add(TariffVersionStatusHistory(
        tariff_version_id=target.id,
        from_status=None,
        to_status="DRAFT",
        changed_by_user_id=user_id,
        comment=f"Создана из версии № {source.version_no}: {reason}",
    ))

    snapshot_class_map = {}
    enrollment_map = {}
    for old_snapshot in source.population_snapshots:
        new_snapshot = PopulationSnapshot(
            tariff_version_id=target.id,
            revision_no=old_snapshot.revision_no,
            snapshot_date=old_snapshot.snapshot_date,
            status=old_snapshot.status,
            source_kind=old_snapshot.source_kind,
            checksum=old_snapshot.checksum,
            created_by_user_id=user_id,
        )
        db.session.add(new_snapshot)
        db.session.flush()
        for old_class in old_snapshot.classes:
            new_class = PopulationSnapshotClass(
                population_snapshot_id=new_snapshot.id,
                source_school_class_id=old_class.source_school_class_id,
                name_snapshot=old_class.name_snapshot,
                grade_snapshot=old_class.grade_snapshot,
                building_id=old_class.building_id,
                building_name_snapshot=old_class.building_name_snapshot,
                student_count=old_class.student_count,
            )
            db.session.add(new_class)
            db.session.flush()
            snapshot_class_map[old_class.id] = new_class.id
            for old_enrollment in old_class.enrollments:
                new_enrollment = PopulationSnapshotEnrollment(
                    population_snapshot_class_id=new_class.id,
                    source_child_id=old_enrollment.source_child_id,
                    source_enrollment_id=old_enrollment.source_enrollment_id,
                    fio_snapshot=old_enrollment.fio_snapshot,
                    status_snapshot=old_enrollment.status_snapshot,
                    started_on=old_enrollment.started_on,
                    ended_on=old_enrollment.ended_on,
                )
                db.session.add(new_enrollment)
                db.session.flush()
                enrollment_map[old_enrollment.id] = new_enrollment.id

    plan_map = {}
    line_map = {}
    for old_plan in source.plans:
        new_plan = EducationPlan(
            tariff_version_id=target.id,
            plan_kind=old_plan.plan_kind,
            name=old_plan.name,
            education_level=old_plan.education_level,
            building_id=old_plan.building_id,
            scope_code=old_plan.scope_code,
            status="DRAFT",
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        db.session.add(new_plan)
        db.session.flush()
        plan_map[old_plan.id] = new_plan.id
        for old_line in old_plan.lines:
            new_line = EducationPlanLine(
                education_plan_id=new_plan.id,
                education_activity_id=old_line.education_activity_id,
                component_kind=old_line.component_kind,
                weekly_hours=old_line.weekly_hours,
                weeks_count=old_line.weeks_count,
                annual_hours=old_line.annual_hours,
                requires_division=old_line.requires_division,
                profile_code=old_line.profile_code,
                source_line_id=old_line.id,
                sort_order=old_line.sort_order,
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
            )
            db.session.add(new_line)
            db.session.flush()
            line_map[old_line.id] = new_line.id
            for old_scope in old_line.scopes:
                db.session.add(EducationPlanLineScope(
                    education_plan_line_id=new_line.id,
                    scope_kind=old_scope.scope_kind,
                    school_class_id=old_scope.school_class_id,
                    grade=old_scope.grade,
                    profile_code=old_scope.profile_code,
                    building_id=old_scope.building_id,
                    scope_key=old_scope.scope_key,
                ))
            for old_period in old_line.periods:
                db.session.add(EducationPlanLinePeriod(
                    education_plan_line_id=new_line.id,
                    date_from=old_period.date_from,
                    date_to=old_period.date_to,
                    weeks_count=old_period.weeks_count,
                    weekly_hours=old_period.weekly_hours,
                    annual_hours=old_period.annual_hours,
                ))

    group_map = {}
    for old_group in source.teaching_groups:
        if old_group.valid_to < effective_from:
            continue
        new_group = TeachingGroup(
            tariff_version_id=target.id,
            education_activity_id=old_group.education_activity_id,
            group_type=old_group.group_type,
            code=old_group.code,
            name=old_group.name,
            composition_mode=old_group.composition_mode,
            building_id=old_group.building_id,
            department_id=old_group.department_id,
            planned_size=old_group.planned_size,
            actual_size=old_group.actual_size,
            valid_from=max(old_group.valid_from, effective_from),
            valid_to=old_group.valid_to,
            source_plan_line_id=line_map[old_group.source_plan_line_id],
            source_group_id=old_group.id,
            status="DRAFT",
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        db.session.add(new_group)
        db.session.flush()
        group_map[old_group.id] = new_group.id
        for old_link in old_group.source_classes:
            mapped_class = snapshot_class_map.get(
                old_link.population_snapshot_class_id
            )
            if mapped_class:
                db.session.add(TeachingGroupClass(
                    teaching_group_id=new_group.id,
                    population_snapshot_class_id=mapped_class,
                    relation_kind=old_link.relation_kind,
                    student_count=old_link.student_count,
                ))
        for old_member in old_group.members:
            mapped_enrollment = enrollment_map.get(
                old_member.snapshot_enrollment_id
            )
            if mapped_enrollment:
                db.session.add(TeachingGroupMember(
                    teaching_group_id=new_group.id,
                    snapshot_enrollment_id=mapped_enrollment,
                    valid_from=max(old_member.valid_from, effective_from),
                    valid_to=old_member.valid_to,
                    source_kind=old_member.source_kind,
                    note=old_member.note,
                ))

    for old_group in source.teaching_groups:
        if old_group.id not in group_map:
            continue
        for old_link in old_group.metagroup_sources:
            mapped_source_group_id = group_map.get(old_link.source_group_id)
            if mapped_source_group_id is None:
                continue
            db.session.add(TeachingMetagroupSource(
                metagroup_id=group_map[old_group.id],
                source_group_id=mapped_source_group_id,
                sort_order=old_link.sort_order,
            ))

    need_map = {}
    for old_need in source.workload_needs:
        if old_need.date_to < effective_from:
            continue
        new_need = WorkloadNeed(
            organization_id=old_need.organization_id,
            tariff_version_id=target.id,
            teaching_group_id=group_map.get(old_need.teaching_group_id),
            education_activity_id=old_need.education_activity_id,
            department_id=old_need.department_id,
            building_id=old_need.building_id,
            date_from=max(old_need.date_from, effective_from),
            date_to=old_need.date_to,
            weekly_hours=old_need.weekly_hours,
            annual_hours=old_need.annual_hours,
            need_kind=old_need.need_kind,
            status="OPEN",
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        db.session.add(new_need)
        db.session.flush()
        need_map[old_need.id] = new_need.id
        for old_source in old_need.sources:
            db.session.add(WorkloadNeedSource(
                workload_need_id=new_need.id,
                education_plan_line_id=line_map[
                    old_source.education_plan_line_id
                ],
                source_weekly_hours=old_source.source_weekly_hours,
                source_annual_hours=old_source.source_annual_hours,
                source_kind=old_source.source_kind,
            ))

    for old_assignment in WorkloadAssignment.query.filter(
        WorkloadAssignment.tariff_version_id == source.id,
        WorkloadAssignment.status != "CANCELLED",
    ):
        if (
            old_assignment.date_to < effective_from
            or old_assignment.workload_need_id not in need_map
        ):
            continue
        db.session.add(WorkloadAssignment(
            organization_id=old_assignment.organization_id,
            tariff_version_id=target.id,
            workload_need_id=need_map[old_assignment.workload_need_id],
            employee_user_id=old_assignment.employee_user_id,
            position_code=old_assignment.position_code,
            position_title=old_assignment.position_title,
            department_id=old_assignment.department_id,
            building_id=old_assignment.building_id,
            assignment_kind=old_assignment.assignment_kind,
            date_from=max(old_assignment.date_from, effective_from),
            date_to=old_assignment.date_to,
            weekly_hours=old_assignment.weekly_hours,
            annual_hours=old_assignment.annual_hours,
            status="DRAFT",
            origin_assignment_id=old_assignment.id,
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        ))

    for old_set in source.calculation_parameter_sets:
        if old_set.valid_to < effective_from:
            continue
        new_set = CalculationParameterSet(
            organization_id=old_set.organization_id,
            tariff_version_id=target.id,
            code=old_set.code,
            name=old_set.name,
            valid_from=max(old_set.valid_from, effective_from),
            valid_to=old_set.valid_to,
            student_hour_rate=old_set.student_hour_rate,
            periods_per_year=old_set.periods_per_year,
            rounding_rule=old_set.rounding_rule,
            currency_code=old_set.currency_code,
            status="DRAFT",
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
        )
        db.session.add(new_set)
        db.session.flush()
        for old_norm in old_set.rate_norms:
            if old_norm.valid_to < effective_from:
                continue
            db.session.add(TariffRateNorm(
                parameter_set_id=new_set.id,
                position_code=old_norm.position_code,
                position_name=old_norm.position_name,
                activity_kind=old_norm.activity_kind,
                weekly_norm_hours=old_norm.weekly_norm_hours,
                valid_from=max(old_norm.valid_from, effective_from),
                valid_to=old_norm.valid_to,
                source_text=old_norm.source_text,
                created_by_user_id=user_id,
            ))
        for old_value in old_set.coefficient_values:
            if old_value.valid_to < effective_from:
                continue
            db.session.add(TariffCoefficientValue(
                parameter_set_id=new_set.id,
                coefficient_type_id=old_value.coefficient_type_id,
                value=old_value.value,
                condition_kind=old_value.condition_kind,
                condition_data=deepcopy(old_value.condition_data),
                priority=old_value.priority,
                minimum_value=old_value.minimum_value,
                maximum_value=old_value.maximum_value,
                valid_from=max(old_value.valid_from, effective_from),
                valid_to=old_value.valid_to,
                source_text=old_value.source_text,
                created_by_user_id=user_id,
            ))
        for old_rule in old_set.allowance_rules:
            if old_rule.valid_to < effective_from:
                continue
            db.session.add(TariffAllowanceRule(
                parameter_set_id=new_set.id,
                allowance_type_id=old_rule.allowance_type_id,
                fixed_amount=old_rule.fixed_amount,
                percent_value=old_rule.percent_value,
                base_kind=old_rule.base_kind,
                condition_data=deepcopy(old_rule.condition_data),
                priority=old_rule.priority,
                valid_from=max(old_rule.valid_from, effective_from),
                valid_to=old_rule.valid_to,
                source_text=old_rule.source_text,
                created_by_user_id=user_id,
            ))
    return target


__all__ = [
    "BLOCKING_SEVERITIES",
    "REVIEW_STAGE_ORDER",
    "RULE_SET_VERSION",
    "TariffWorkflowError",
    "TariffWorkflowValidationError",
    "activate_due_version",
    "add_review_comment",
    "answer_review_comment",
    "approve_version",
    "clone_correction_version",
    "close_review_comment",
    "collect_validation_issues",
    "latest_review_cycle",
    "latest_validation_run",
    "record_review_decision",
    "review_stage_state",
    "run_full_validation",
    "start_review",
    "version_checksum",
]
