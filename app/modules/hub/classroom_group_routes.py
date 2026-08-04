from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from app.core.extensions import db
from app.core.feature_flags import (
    WORKLOAD_MODULE,
    WORKLOAD_WRITE,
    is_feature_enabled,
)
from app.models import AcademicYear, SchoolClass
from app.services.classroom_group_service import (
    build_classroom_group_context,
    build_classroom_curriculum_rows,
    build_classroom_group_xlsx,
    select_classroom_composition_item,
)
from app.services.teaching_group_matrix_service import (
    approve_group_composition,
    replace_group_composition_assignments,
)
from app.services.teaching_group_service import GroupValidationError


CLASSROOM_GROUP_OVERSIGHT_ROLES = frozenset({
    "ADMIN",
    "DIRECTOR",
    "DEPUTY_DIRECTOR",
    "METHODIST",
})


def _role_codes():
    return {
        str(code).upper()
        for code in getattr(current_user, "role_codes", ())
    }


def _classroom_group_classes():
    if not is_feature_enabled(WORKLOAD_MODULE):
        abort(404)
    role_codes = _role_codes()
    can_oversee = bool(
        role_codes.intersection(CLASSROOM_GROUP_OVERSIGHT_ROLES)
    )
    academic_year = (
        AcademicYear.query
        .filter_by(is_current=True)
        .order_by(AcademicYear.id.desc())
        .first()
    )
    if academic_year is None:
        return []
    owns_class = (
        SchoolClass.query
        .filter_by(
            academic_year_id=academic_year.id,
            teacher_user_id=current_user.id,
            is_active=True,
            is_archived=False,
        )
        .first()
        is not None
    )
    if not can_oversee and not owns_class:
        abort(403)
    query = (
        SchoolClass.query
        .filter_by(
            academic_year_id=academic_year.id,
            is_active=True,
            is_archived=False,
        )
        .order_by(
            SchoolClass.grade.asc(),
            SchoolClass.name.asc(),
        )
    )
    if not can_oversee:
        query = query.filter_by(teacher_user_id=current_user.id)
    return query.all()


def _selected_school_class(classes, class_id=None):
    if not classes:
        return None
    try:
        requested_id = int(class_id)
    except (TypeError, ValueError):
        requested_id = None
    if requested_id is None:
        return classes[0]
    selected = next(
        (school_class for school_class in classes if school_class.id == requested_id),
        None,
    )
    if selected is None:
        abort(403)
    return selected


def _classroom_page_context(class_id=None, item_key=None):
    classes = _classroom_group_classes()
    school_class = _selected_school_class(classes, class_id)
    if school_class is None:
        return {
            "classes": classes,
            "selected_class": None,
            "selected_item": None,
            "composition": {
                "items": [],
                "complete_count": 0,
                "incomplete_count": 0,
                "assigned_count": 0,
                "student_count": 0,
            },
            "can_update": False,
            "can_approve": False,
        }
    context = build_classroom_group_context(school_class)
    selected_item = select_classroom_composition_item(
        context["composition"],
        item_key,
    )
    own_class = school_class.teacher_user_id == current_user.id
    can_update = bool(
        context["version"]
        and context["version"].status == "DRAFT"
        and is_feature_enabled(WORKLOAD_WRITE)
    )
    context.update({
        "classes": classes,
        "selected_class": school_class,
        "selected_item": selected_item,
        "can_update": can_update,
        "can_approve": can_update and own_class,
    })
    return context


def _ajax_request():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _composition_assignments(item):
    assignments = {}
    for enrollment in item["enrollments"]:
        group_id = request.form.get(
            f"member_{enrollment.id}",
            type=int,
        )
        if group_id is not None:
            assignments[enrollment.id] = group_id
    return assignments


def _redirect_to_classroom(context, item_key):
    return redirect(url_for(
        "hub.classroom_groups",
        class_id=context["selected_class"].id,
        item=item_key,
    ))


def register_classroom_group_routes(hub_bp):
    @hub_bp.get("/classroom/curriculum")
    @login_required
    def classroom_curriculum():
        context = _classroom_page_context(
            request.args.get("class_id"),
        )
        context["curriculum_rows"] = (
            build_classroom_curriculum_rows(context)
            if context["selected_class"] is not None
            else []
        )
        return render_template(
            "hub/classroom_curriculum.html",
            **context,
        )

    @hub_bp.get("/classroom/groups")
    @login_required
    def classroom_groups():
        context = _classroom_page_context(
            request.args.get("class_id"),
            request.args.get("item"),
        )
        return render_template(
            "hub/classroom_groups.html",
            **context,
        )

    @hub_bp.post("/classroom/groups")
    @login_required
    def classroom_groups_update():
        context = _classroom_page_context(
            request.form.get("class_id"),
            request.form.get("item_key"),
        )
        if not context["can_update"]:
            abort(403)
        item = context["selected_item"]
        if item is None:
            abort(404)
        try:
            result = replace_group_composition_assignments(
                item,
                _composition_assignments(item),
                user_id=current_user.id,
                allow_with_workload=True,
            )
            db.session.commit()
        except GroupValidationError as exc:
            db.session.rollback()
            if _ajax_request():
                return jsonify({
                    "ok": False,
                    "message": str(exc),
                }), 422
            flash(str(exc), "danger")
        else:
            message = (
                "Состав полностью распределён."
                if result["complete"]
                else (
                    f"Сохранено назначений: "
                    f"{result['assigned_count']} из "
                    f"{result['student_count']}."
                )
            )
            if _ajax_request():
                return jsonify({
                    "ok": True,
                    "message": message,
                    **result,
                })
            flash(message, "success")
        return _redirect_to_classroom(
            context,
            request.form.get("item_key"),
        )

    @hub_bp.post("/classroom/groups/approve")
    @login_required
    def classroom_groups_approve():
        context = _classroom_page_context(
            request.form.get("class_id"),
            request.form.get("item_key"),
        )
        if not context["can_approve"]:
            abort(403)
        item = context["selected_item"]
        if item is None:
            abort(404)
        try:
            approval = approve_group_composition(
                item,
                user_id=current_user.id,
            )
            db.session.commit()
        except GroupValidationError as exc:
            db.session.rollback()
            if _ajax_request():
                return jsonify({
                    "ok": False,
                    "message": str(exc),
                }), 422
            flash(str(exc), "danger")
        else:
            message = "Деление согласовано классным руководителем."
            if _ajax_request():
                return jsonify({
                    "ok": True,
                    "message": message,
                    "approved_at": approval.approved_at.isoformat(),
                })
            flash(message, "success")
        return _redirect_to_classroom(
            context,
            request.form.get("item_key"),
        )

    @hub_bp.get("/classroom/groups/export.xlsx")
    @login_required
    def classroom_groups_export():
        context = _classroom_page_context(
            request.args.get("class_id"),
        )
        school_class = context["selected_class"]
        if school_class is None:
            abort(404)
        output = build_classroom_group_xlsx(context)
        return send_file(
            output,
            as_attachment=True,
            download_name=(
                f"classroom_groups_{school_class.id}.xlsx"
            ),
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )


__all__ = ["register_classroom_group_routes"]
