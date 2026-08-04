from datetime import datetime

from app.models import WorkloadAssignment


class WorkloadEditingWorkflowError(ValueError):
    pass


def require_groups_editable(version):
    if version.status != "DRAFT":
        raise WorkloadEditingWorkflowError(
            "Версия учебного года уже закрыта для изменения."
        )
    if version.groups_editing_status != "EDITING":
        raise WorkloadEditingWorkflowError(
            "Изменение групп закрыто. Нажмите «Внести изменения»."
        )


def change_groups_editing_status(version, action, *, user_id):
    if version.status != "DRAFT":
        raise WorkloadEditingWorkflowError(
            "Версия учебного года уже закрыта для изменения."
        )
    action = (action or "").strip().upper()
    transitions = {
        ("EDITING", "SAVE"): "SAVED",
        ("SAVED", "EDIT"): "EDITING",
    }
    target = transitions.get((version.groups_editing_status, action))
    if target is None:
        raise WorkloadEditingWorkflowError(
            "Состояние групп уже изменилось. Обновите страницу."
        )
    version.groups_editing_status = target
    version.updated_by_user_id = user_id
    version.revision += 1
    return target


def require_workload_editable(version):
    if version.status != "DRAFT":
        raise WorkloadEditingWorkflowError(
            "Версия учебного года уже закрыта для изменения."
        )
    if version.workload_approval_status != "EDITING":
        raise WorkloadEditingWorkflowError(
            "Нагрузка закрыта для изменения."
        )


def change_workload_approval_status(
    version,
    action,
    *,
    user_id,
    comment=None,
):
    if version.status != "DRAFT":
        raise WorkloadEditingWorkflowError(
            "Версия учебного года уже закрыта для изменения."
        )
    action = (action or "").strip().upper()
    current = version.workload_approval_status
    normalized_comment = " ".join((comment or "").split()) or None
    if action == "REQUEST_CHANGES" and normalized_comment is None:
        raise WorkloadEditingWorkflowError(
            "Укажите, что нужно исправить в нагрузке."
        )
    transitions = {
        ("EDITING", "SAVE"): "SAVED",
        ("SAVED", "EDIT"): "EDITING",
        ("SAVED", "SUBMIT"): "PENDING_APPROVAL",
        ("PENDING_APPROVAL", "APPROVE"): "APPROVED",
        ("PENDING_APPROVAL", "REQUEST_CHANGES"): "CHANGES_REQUESTED",
        ("APPROVED", "REQUEST_CHANGES"): "CHANGES_REQUESTED",
        ("CHANGES_REQUESTED", "EDIT"): "EDITING",
    }
    target = transitions.get((current, action))
    if target is None:
        raise WorkloadEditingWorkflowError(
            "Состояние нагрузки уже изменилось. Обновите страницу."
        )

    now = datetime.utcnow()
    version.workload_approval_status = target
    version.updated_by_user_id = user_id
    version.revision += 1
    if target == "PENDING_APPROVAL":
        version.workload_submitted_at = now
        version.workload_review_comment = None
        version.workload_reviewed_at = None
        version.workload_reviewed_by_user_id = None
    elif target in {"APPROVED", "CHANGES_REQUESTED"}:
        version.workload_reviewed_at = now
        version.workload_reviewed_by_user_id = user_id
        version.workload_review_comment = normalized_comment

    assignments = (
        WorkloadAssignment.query
        .filter(
            WorkloadAssignment.tariff_version_id == version.id,
            WorkloadAssignment.status != "CANCELLED",
        )
        .all()
    )
    if target == "APPROVED":
        for assignment in assignments:
            assignment.status = "CONFIRMED"
            assignment.updated_by_user_id = user_id
    elif target in {"EDITING", "CHANGES_REQUESTED"}:
        for assignment in assignments:
            assignment.status = "DRAFT"
            assignment.updated_by_user_id = user_id
    return target


__all__ = [
    "WorkloadEditingWorkflowError",
    "change_groups_editing_status",
    "change_workload_approval_status",
    "require_groups_editable",
    "require_workload_editable",
]
