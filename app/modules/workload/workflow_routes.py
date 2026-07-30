from datetime import date

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from app.core.extensions import db
from app.models import (
    OrganizationSettings,
    TariffDocumentArtifact,
    TariffReviewComment,
    TariffReviewCycle,
    TariffVersion,
    TariffCycle,
    User,
)
from app.services.tariff_document_service import (
    DOCUMENT_LABELS,
    FINANCIAL_DOCUMENT_TYPES,
    generate_tariff_document,
    resolve_artifact_path,
)
from app.services.tariff_workflow_service import (
    TariffWorkflowError,
    TariffWorkflowValidationError,
    activate_due_version,
    add_review_comment,
    answer_review_comment,
    approve_version,
    clone_correction_version,
    close_review_comment,
    latest_review_cycle,
    latest_validation_run,
    record_review_decision,
    review_stage_state,
    run_full_validation,
    start_review,
)

from .access import can_use_workload_permission, require_workload_write


REVIEW_PERMISSION = {
    "ACADEMIC": "workload.review.academic",
    "HR": "workload.review.hr",
    "FINANCE": "workload.review.finance",
}
VERSION_STATUS_LABELS = {
    "DRAFT": "Черновик",
    "VALIDATION": "На согласовании",
    "APPROVAL": "На утверждении",
    "APPROVED": "Утверждена",
    "EFFECTIVE": "Действует",
    "SUPERSEDED": "Заменена",
    "ARCHIVED": "Архив",
}
REVIEW_STAGE_LABELS = {
    "ACADEMIC": "Содержательная проверка",
    "HR": "Кадровая проверка",
    "FINANCE": "Финансовая проверка",
}


def _current_organization_id():
    organization = (
        OrganizationSettings.query
        .filter_by(is_active=True)
        .order_by(OrganizationSettings.id.asc())
        .first()
    )
    return organization.id if organization else None


def _versions_query():
    query = TariffVersion.query.join(TariffCycle)
    organization_id = _current_organization_id()
    if organization_id is None:
        query = query.filter(TariffCycle.organization_id.is_(None))
    else:
        query = query.filter(TariffCycle.organization_id == organization_id)
    return query.order_by(TariffVersion.id.desc())


def _get_version(version_id):
    return _versions_query().filter(TariffVersion.id == version_id).first_or_404()


def _parse_date(value, label):
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise TariffWorkflowError(f"Укажите корректную дату: {label}.") from exc


def _require_permission(permission):
    if not can_use_workload_permission(permission, current_user):
        abort(403)


def _require_any_permission(*permissions):
    if not any(
        can_use_workload_permission(permission, current_user)
        for permission in permissions
    ):
        abort(403)


def _redirect_workflow(version_id):
    return redirect(url_for("workload.workflow", version_id=version_id))


def _handle_action(action, *, success, version_id):
    try:
        action()
        db.session.commit()
    except TariffWorkflowValidationError as exc:
        db.session.commit()
        flash(str(exc), "danger")
    except TariffWorkflowError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    else:
        flash(success, "success")
    return _redirect_workflow(version_id)


def _document_access_allowed(artifact):
    own_personal = (
        artifact.document_type == "PERSONAL_TARIFF"
        and artifact.employee_user_id == current_user.id
        and can_use_workload_permission("workload.self.read", current_user)
    )
    if own_personal:
        return True
    if not (
        can_use_workload_permission(
            "workload.documents.generate",
            current_user,
        )
        or can_use_workload_permission("workload.audit.read", current_user)
    ):
        return False
    if (
        artifact.document_type in FINANCIAL_DOCUMENT_TYPES
        and not can_use_workload_permission(
            "workload.finance.read",
            current_user,
        )
    ):
        return False
    return True


def register_workflow_routes(workload_bp):
    @workload_bp.get("/workflow/")
    @login_required
    def workflow():
        _require_any_permission(
            "workload.read",
            "workload.self.read",
        )
        versions = _versions_query().all()
        version_id = request.args.get("version_id", type=int)
        version = _get_version(version_id) if version_id else (
            versions[0] if versions else None
        )
        validation = latest_validation_run(version.id) if version else None
        cycle = latest_review_cycle(version.id) if version else None
        decisions, expected_stage = review_stage_state(cycle)
        stage_permissions = {
            stage: can_use_workload_permission(permission, current_user)
            for stage, permission in REVIEW_PERMISSION.items()
        }
        return render_template(
            "workload/workflow.html",
            versions=versions,
            version=version,
            validation=validation,
            validation_issues=list(validation.issues) if validation else [],
            cycle=cycle,
            decisions=decisions,
            expected_stage=expected_stage,
            stage_permissions=stage_permissions,
            can_start=can_use_workload_permission(
                "workload.review.academic",
                current_user,
            ),
            can_approve=can_use_workload_permission(
                "workload.approve",
                current_user,
            ),
            can_answer=can_use_workload_permission(
                "workload.assignments.update",
                current_user,
            ),
            status_labels=VERSION_STATUS_LABELS,
            stage_labels=REVIEW_STAGE_LABELS,
        )

    @workload_bp.post("/workflow/validate")
    @login_required
    def workflow_validate():
        require_workload_write()
        _require_permission("workload.review.academic")
        version = _get_version(request.form.get("version_id", type=int))

        def action():
            run_full_validation(version, user_id=current_user.id)

        return _handle_action(
            action,
            success="Полная проверка выполнена.",
            version_id=version.id,
        )

    @workload_bp.post("/workflow/start")
    @login_required
    def workflow_start():
        require_workload_write()
        _require_permission("workload.review.academic")
        version = _get_version(request.form.get("version_id", type=int))

        try:
            run, cycle = start_review(version, user_id=current_user.id)
            db.session.commit()
        except TariffWorkflowError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            if cycle is None:
                flash(
                    "Согласование не запущено: устраните ошибки проверки.",
                    "danger",
                )
            else:
                flash(
                    "Версия направлена на последовательное согласование.",
                    "success",
                )
        return _redirect_workflow(version.id)

    @workload_bp.post("/workflow/reviews/<int:cycle_id>/comments")
    @login_required
    def workflow_comment_add(cycle_id):
        require_workload_write()
        cycle = TariffReviewCycle.query.get_or_404(cycle_id)
        version = _get_version(cycle.tariff_version_id)
        stage = (request.form.get("review_stage") or "").strip().upper()
        permission = REVIEW_PERMISSION.get(stage)
        if permission is None:
            abort(400)
        _require_permission(permission)

        def action():
            add_review_comment(
                cycle,
                review_stage=stage,
                comment_kind=request.form.get("comment_kind"),
                text=request.form.get("text"),
                user_id=current_user.id,
            )

        return _handle_action(
            action,
            success="Замечание сохранено.",
            version_id=version.id,
        )

    @workload_bp.post("/workflow/comments/<int:comment_id>/answer")
    @login_required
    def workflow_comment_answer(comment_id):
        require_workload_write()
        _require_any_permission(
            "workload.assignments.update",
            "workload.plan.update",
        )
        comment = TariffReviewComment.query.get_or_404(comment_id)
        version = _get_version(comment.tariff_version_id)

        def action():
            answer_review_comment(
                comment,
                response_text=request.form.get("response_text"),
                user_id=current_user.id,
            )

        return _handle_action(
            action,
            success="Ответ на замечание сохранён.",
            version_id=version.id,
        )

    @workload_bp.post("/workflow/comments/<int:comment_id>/close")
    @login_required
    def workflow_comment_close(comment_id):
        require_workload_write()
        comment = TariffReviewComment.query.get_or_404(comment_id)
        version = _get_version(comment.tariff_version_id)
        permission = REVIEW_PERMISSION.get(comment.review_stage)
        if permission is None:
            abort(400)
        _require_permission(permission)

        def action():
            close_review_comment(comment, user_id=current_user.id)

        return _handle_action(
            action,
            success="Замечание закрыто.",
            version_id=version.id,
        )

    @workload_bp.post("/workflow/reviews/<int:cycle_id>/decision")
    @login_required
    def workflow_review_decision(cycle_id):
        require_workload_write()
        cycle = TariffReviewCycle.query.get_or_404(cycle_id)
        version = _get_version(cycle.tariff_version_id)
        stage = (request.form.get("review_stage") or "").strip().upper()
        permission = REVIEW_PERMISSION.get(stage)
        if permission is None:
            abort(400)
        _require_permission(permission)

        def action():
            record_review_decision(
                version,
                cycle,
                review_stage=stage,
                decision=request.form.get("decision"),
                comment=request.form.get("comment"),
                user_id=current_user.id,
            )

        return _handle_action(
            action,
            success="Заключение сохранено.",
            version_id=version.id,
        )

    @workload_bp.post("/workflow/versions/<int:version_id>/approve")
    @login_required
    def workflow_approve(version_id):
        require_workload_write()
        _require_permission("workload.approve")
        version = _get_version(version_id)

        def action():
            approve_version(
                version,
                decision=request.form.get("decision"),
                comment=request.form.get("comment"),
                effective_from=_parse_date(
                    request.form.get("effective_from"),
                    "начало действия",
                ),
                user_id=current_user.id,
            )

        return _handle_action(
            action,
            success="Решение директора сохранено.",
            version_id=version.id,
        )

    @workload_bp.post("/workflow/versions/<int:version_id>/activate")
    @login_required
    def workflow_activate(version_id):
        require_workload_write()
        _require_permission("workload.approve")
        version = _get_version(version_id)

        def action():
            activate_due_version(version, user_id=current_user.id)

        return _handle_action(
            action,
            success="Версия введена в действие.",
            version_id=version.id,
        )

    @workload_bp.post("/workflow/versions/<int:version_id>/corrections")
    @login_required
    def workflow_correction(version_id):
        require_workload_write()
        _require_permission("workload.approve")
        source = _get_version(version_id)
        target_id = None
        try:
            target = clone_correction_version(
                source,
                effective_from=_parse_date(
                    request.form.get("effective_from"),
                    "дата изменения",
                ),
                reason_text=request.form.get("reason_text"),
                user_id=current_user.id,
            )
            db.session.commit()
            target_id = target.id
        except TariffWorkflowError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash(
                "Создана корректирующая версия. Проверьте периоды и часы "
                "каждой скопированной строки.",
                "success",
            )
        return _redirect_workflow(target_id or source.id)

    @workload_bp.get("/documents/")
    @login_required
    def tariff_documents():
        _require_any_permission(
            "workload.documents.generate",
            "workload.audit.read",
            "workload.self.read",
        )
        versions = _versions_query().all()
        version_id = request.args.get("version_id", type=int)
        version = _get_version(version_id) if version_id else (
            versions[0] if versions else None
        )
        artifacts = []
        if version is not None:
            query = TariffDocumentArtifact.query.filter_by(
                tariff_version_id=version.id,
            )
            if can_use_workload_permission(
                "workload.self.read",
                current_user,
            ) and not can_use_workload_permission(
                "workload.documents.generate",
                current_user,
            ):
                query = query.filter_by(
                    document_type="PERSONAL_TARIFF",
                    employee_user_id=current_user.id,
                )
            artifacts = query.order_by(
                TariffDocumentArtifact.created_at.desc()
            ).all()
            artifacts = [
                item for item in artifacts if _document_access_allowed(item)
            ]
        employees = (
            User.query
            .filter(
                User.is_active_user.is_(True),
                User.employment_status == "ACTIVE",
                User.archived_at.is_(None),
            )
            .order_by(User.last_name, User.first_name, User.middle_name)
            .all()
        )
        return render_template(
            "workload/documents.html",
            versions=versions,
            version=version,
            artifacts=artifacts,
            document_labels=DOCUMENT_LABELS,
            employees=employees,
            can_generate=can_use_workload_permission(
                "workload.documents.generate",
                current_user,
            ),
            can_view_finance=can_use_workload_permission(
                "workload.finance.read",
                current_user,
            ),
        )

    @workload_bp.post("/documents/generate")
    @login_required
    def tariff_document_generate():
        require_workload_write()
        _require_permission("workload.documents.generate")
        version = _get_version(request.form.get("version_id", type=int))
        document_type = (
            request.form.get("document_type") or ""
        ).strip().upper()
        if (
            document_type in FINANCIAL_DOCUMENT_TYPES
            and not can_use_workload_permission(
                "workload.finance.read",
                current_user,
            )
        ):
            abort(403)
        try:
            artifact = generate_tariff_document(
                version,
                document_type=document_type,
                employee_user_id=request.form.get(
                    "employee_user_id",
                    type=int,
                ),
                department_id=request.form.get("department_id", type=int),
                user_id=current_user.id,
            )
            db.session.commit()
        except TariffWorkflowError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        else:
            flash(
                f"Документ «{artifact.filename}» сформирован.",
                "success",
            )
        return redirect(
            url_for("workload.tariff_documents", version_id=version.id)
        )

    @workload_bp.get("/documents/<int:artifact_id>/download")
    @login_required
    def tariff_document_download(artifact_id):
        artifact = TariffDocumentArtifact.query.get_or_404(artifact_id)
        _get_version(artifact.tariff_version_id)
        if not _document_access_allowed(artifact):
            abort(403)
        try:
            path = resolve_artifact_path(artifact)
        except TariffWorkflowError as exc:
            abort(409, str(exc))
        return send_file(
            path,
            as_attachment=True,
            download_name=artifact.filename,
            mimetype=artifact.mime_type,
        )


__all__ = ["register_workflow_routes"]
