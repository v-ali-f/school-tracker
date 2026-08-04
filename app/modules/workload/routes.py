from decimal import Decimal, InvalidOperation
from uuid import uuid4

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.core.feature_flags import WORKLOAD_WRITE, is_feature_enabled
from app.models import (
    ACTIVITY_KINDS,
    ACTIVITY_KIND_LABELS,
    EDUCATION_LEVELS,
    EDUCATION_LEVEL_LABELS,
    ControlWork,
    Debt,
    DiagnosticSession,
    AcademicYear,
    Department,
    DepartmentLeader,
    DepartmentSubject,
    EducationActivity,
    EducationActivityAlias,
    EducationActivityDepartment,
    EducationActivityLevel,
    EducationPlanLine,
    ExternalActivityMappingLog,
    OlympiadImportSession,
    OlympiadResult,
    OlympiadSubjectMapping,
    OrganizationSettings,
    Subject,
    TariffLine,
    TeacherLoad,
    TeacherMckoResult,
    TeachingGroup,
    User,
    WorkloadEditorAccess,
    WorkloadNeed,
    WorkloadReconciliationItem,
)
from app.services.education_activity_service import (
    normalize_activity_name,
    replace_activity_departments,
    sync_subject_from_activity,
)

from .access import (
    WORKLOAD_DEFAULT_EDITOR_ROLES,
    can_access_workload_module,
    can_use_workload_permission,
    require_workload_module,
    require_workload_write,
)
from .plan_routes import register_plan_routes
from .plan_binding_routes import register_plan_binding_routes
from .group_routes import register_group_routes
from .assignment_routes import register_assignment_routes
from .workflow_routes import register_workflow_routes


workload_bp = Blueprint("workload", __name__, url_prefix="/workload")

CATALOG_SECTIONS = {
    "SUBJECTS": {
        "label": "Учебные предметы и курсы",
        "kinds": ("SUBJECT", "COURSE", "MODULE"),
        "default_kind": "SUBJECT",
        "empty": "Учебные предметы и курсы ещё не добавлены.",
    },
    "EXTRACURRICULAR": {
        "label": "Внеурочная деятельность",
        "kinds": ("EXTRACURRICULAR_COURSE",),
        "default_kind": "EXTRACURRICULAR_COURSE",
        "empty": "Курсы внеурочной деятельности ещё не добавлены.",
    },
    "ADDITIONAL": {
        "label": "Дополнительное образование",
        "kinds": ("ADDITIONAL_PROGRAM", "CLUB_OR_SECTION"),
        "default_kind": "ADDITIONAL_PROGRAM",
        "empty": "Программы дополнительного образования ещё не добавлены.",
    },
    "ALL": {
        "label": "Весь каталог",
        "kinds": ACTIVITY_KINDS,
        "default_kind": "SUBJECT",
        "empty": "В каталоге пока нет записей.",
    },
}


def _catalog_section_for_kind(activity_kind):
    for code in ("SUBJECTS", "EXTRACURRICULAR", "ADDITIONAL"):
        if activity_kind in CATALOG_SECTIONS[code]["kinds"]:
            return code
    return "ALL"


@workload_bp.app_template_filter("compact_decimal")
def compact_decimal(value):
    """Render stored fixed-scale decimals without insignificant zeroes."""
    if value is None:
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    if not number.is_finite():
        return str(value)
    return format(number.normalize(), "f").replace(".", ",")


@workload_bp.app_template_filter("education_level_label")
def education_level_label(value):
    if not value:
        return "Все уровни"
    return EDUCATION_LEVEL_LABELS.get(value, value)


@workload_bp.before_request
def protect_workload_module():
    require_workload_module()
    if current_user.is_authenticated and not can_access_workload_module(current_user):
        abort(403)


@workload_bp.get("/")
@login_required
def index():
    if (
        current_user.has_role("TEACHER")
        and len(current_user.role_codes) == 1
    ):
        return redirect(url_for(
            "workload.workload_teacher_detail",
            user_id=current_user.id,
        ))
    return redirect(url_for("workload.plans"))


@workload_bp.route("/settings/editors", methods=["GET", "POST"])
@login_required
def editor_access():
    _require_catalog_manage()
    users = (
        User.query
        .filter(
            User.is_active_user.is_(True),
            User.archived_at.is_(None),
        )
        .order_by(
            User.last_name.asc(),
            User.first_name.asc(),
            User.middle_name.asc(),
        )
        .all()
    )
    default_user_ids = {
        item.id
        for item in users
        if set(item.role_codes).intersection(WORKLOAD_DEFAULT_EDITOR_ROLES)
    }
    if request.method == "POST":
        selected_ids = {
            int(value)
            for value in request.form.getlist("editor_ids")
            if value.isdigit()
        }
        allowed_ids = {item.id for item in users}
        selected_ids.intersection_update(allowed_ids)
        WorkloadEditorAccess.query.delete(synchronize_session=False)
        for user_id in sorted(selected_ids - default_user_ids):
            db.session.add(WorkloadEditorAccess(
                user_id=user_id,
                is_active=True,
                created_by_user_id=current_user.id,
            ))
        db.session.commit()
        flash("Ответственные за учебные планы и нагрузку сохранены.", "success")
        return redirect(url_for("workload.editor_access"))

    selected_ids = default_user_ids | {
        item.user_id
        for item in WorkloadEditorAccess.query.filter_by(is_active=True).all()
    }
    selected_users = [
        item for item in users if item.id in selected_ids
    ]
    department_heads = (
        DepartmentLeader.query
        .order_by(DepartmentLeader.department_id.asc())
        .all()
    )
    return render_template(
        "workload/editor_access.html",
        users=users,
        selected_users=selected_users,
        selected_ids=selected_ids,
        default_user_ids=default_user_ids,
        department_heads=department_heads,
    )


def _require_catalog_manage():
    require_workload_write()
    if not can_use_workload_permission("workload.settings.manage", current_user):
        abort(403)


def _current_organization_id():
    organization = (
        OrganizationSettings.query
        .filter_by(is_active=True)
        .order_by(OrganizationSettings.id.asc())
        .first()
    )
    return organization.id if organization else None


def _activity_usage(activity):
    plan_lines = (
        EducationPlanLine.query
        .filter_by(education_activity_id=activity.id)
        .order_by(EducationPlanLine.education_plan_id.asc())
        .all()
    )
    plans = []
    seen_plan_ids = set()
    for line in plan_lines:
        plan = line.education_plan
        if plan.id in seen_plan_ids:
            continue
        seen_plan_ids.add(plan.id)
        academic_year = (
            plan.tariff_version.tariff_cycle.academic_year
            if plan.tariff_version
            and plan.tariff_version.tariff_cycle
            else None
        )
        plans.append({
            "id": plan.id,
            "name": plan.name,
            "academic_year": academic_year.name if academic_year else None,
        })

    blocking = [
        {
            "label": "Строки учебных планов",
            "count": len(plan_lines),
        },
        {
            "label": "Учебные группы и метагруппы",
            "count": TeachingGroup.query.filter_by(
                education_activity_id=activity.id,
            ).count(),
        },
        {
            "label": "Потребность и распределение нагрузки",
            "count": WorkloadNeed.query.filter_by(
                education_activity_id=activity.id,
            ).count(),
        },
        {
            "label": "Рассчитанные строки тарификации",
            "count": TariffLine.query.filter_by(
                education_activity_id=activity.id,
            ).count(),
        },
    ]
    blocking = [item for item in blocking if item["count"]]

    subject_id = (
        activity.legacy_subject.id
        if activity.legacy_subject is not None
        else None
    )

    def legacy_reference_count(model):
        conditions = [model.education_activity_id == activity.id]
        if subject_id is not None and hasattr(model, "subject_id"):
            conditions.append(model.subject_id == subject_id)
        return model.query.filter(or_(*conditions)).count()

    references = [
        {
            "label": "Результаты МЦКО преподавателей",
            "count": legacy_reference_count(TeacherMckoResult),
        },
        {
            "label": "Диагностики МЦКО, ЕКР и ФГ",
            "count": DiagnosticSession.query.filter_by(
                education_activity_id=activity.id,
            ).count(),
        },
        {
            "label": "Контрольные работы",
            "count": legacy_reference_count(ControlWork),
        },
        {
            "label": "Результаты и импорты олимпиад",
            "count": (
                legacy_reference_count(OlympiadResult)
                + legacy_reference_count(OlympiadImportSession)
                + legacy_reference_count(OlympiadSubjectMapping)
            ),
        },
        {
            "label": "Академические задолженности",
            "count": legacy_reference_count(Debt),
        },
        {
            "label": "Действующая нагрузка старого раздела",
            "count": TeacherLoad.query.filter(
                TeacherLoad.is_archived.is_(False),
                or_(
                    TeacherLoad.education_activity_id == activity.id,
                    *(
                        [TeacherLoad.subject_id == subject_id]
                        if subject_id is not None
                        else []
                    ),
                ),
            ).count(),
        },
        {
            "label": "Сопоставления импортированных названий",
            "count": ExternalActivityMappingLog.query.filter_by(
                education_activity_id=activity.id,
            ).count(),
        },
        {
            "label": "Сверки старой и новой нагрузки",
            "count": WorkloadReconciliationItem.query.filter(
                or_(
                    WorkloadReconciliationItem.education_activity_id
                    == activity.id,
                    *(
                        [
                            WorkloadReconciliationItem.subject_id
                            == subject_id
                        ]
                        if subject_id is not None
                        else []
                    ),
                )
            ).count(),
        },
    ]
    references = [item for item in references if item["count"]]
    return {
        "plans": plans,
        "blocking": blocking,
        "blocking_count": sum(item["count"] for item in blocking),
        "references": references,
        "reference_count": sum(item["count"] for item in references),
    }


def _detach_archived_teacher_loads(activity):
    subject_id = (
        activity.legacy_subject.id
        if activity.legacy_subject is not None
        else None
    )
    conditions = [TeacherLoad.education_activity_id == activity.id]
    if subject_id is not None:
        conditions.append(TeacherLoad.subject_id == subject_id)
    TeacherLoad.query.filter(
        TeacherLoad.is_archived.is_(True),
        or_(*conditions),
    ).update(
        {
            TeacherLoad.education_activity_id: None,
            TeacherLoad.subject_id: None,
        },
        synchronize_session=False,
    )


def _activity_from_form(activity=None):
    name = " ".join((request.form.get("name") or "").split())
    activity_kind = (request.form.get("activity_kind") or "").strip().upper()
    education_levels = list(dict.fromkeys(
        value.strip().upper()
        for value in request.form.getlist("education_levels")
        if value.strip()
    ))
    legacy_level = (
        (request.form.get("education_level") or "").strip().upper()
    )
    if not education_levels and legacy_level:
        education_levels = [legacy_level]
    department_values = request.form.getlist("department_ids")
    try:
        department_ids = list(dict.fromkeys(
            int(value) for value in department_values if value
        ))
    except ValueError as exc:
        raise ValueError("Выберите существующие кафедры.") from exc

    if not name:
        raise ValueError("Укажите наименование.")
    if activity_kind not in ACTIVITY_KINDS:
        raise ValueError("Выберите допустимый вид образовательной активности.")
    if any(level not in EDUCATION_LEVELS for level in education_levels):
        raise ValueError("Выберите допустимые уровни образования.")
    departments = (
        Department.query
        .filter(Department.id.in_(department_ids))
        .order_by(Department.name.asc())
        .all()
        if department_ids else []
    )
    if len(departments) != len(department_ids):
        raise ValueError("Одна из выбранных кафедр не найдена.")

    item = activity or EducationActivity()
    duplicate_query = EducationActivity.query.filter(
        func.lower(EducationActivity.name) == name.lower(),
        EducationActivity.activity_kind == activity_kind,
    )
    if item.id is not None:
        duplicate_query = duplicate_query.filter(
            EducationActivity.id != item.id
        )
    if duplicate_query.first() is not None:
        raise ValueError(
            "Элемент с таким наименованием и видом уже существует."
        )
    if (
        item.id is not None
        and activity_kind != item.activity_kind
        and _activity_usage(item)["blocking_count"]
    ):
        raise ValueError(
            "Вид нельзя изменить, пока запись используется в учебных "
            "планах, группах, нагрузке или рассчитанной тарификации. "
            "Точные места использования указаны ниже."
        )

    if activity is None:
        item.organization_id = _current_organization_id()
        item.is_global = item.organization_id is None
        item.code = f"CATALOG_{uuid4().hex[:16].upper()}"
    item.name = name
    item.short_name = (request.form.get("short_name") or "").strip() or None
    item.activity_kind = activity_kind
    item.education_level = education_levels[0] if education_levels else None
    item.is_tariffable = True
    item.updated_by_user_id = current_user.id
    if activity is None:
        item.created_by_user_id = current_user.id
        db.session.add(item)
    db.session.flush()

    desired_levels = set(education_levels)
    existing_levels = {
        link.education_level: link
        for link in item.level_links
    }
    for level, link in existing_levels.items():
        if level not in desired_levels:
            db.session.delete(link)
    for level in education_levels:
        if level not in existing_levels:
            db.session.add(EducationActivityLevel(
                education_activity_id=item.id,
                education_level=level,
            ))

    sync_subject_from_activity(item)
    replace_activity_departments(
        item,
        [department.id for department in departments],
    )
    return item


def _catalog_integrity_message(_error):
    return (
        "Изменения не сохранены из-за связанной записи. Обновите страницу "
        "и повторите действие; если ошибка сохранится, проверьте блок "
        "«Где используется»."
    )


@workload_bp.get("/catalog/")
@login_required
def catalog():
    query = EducationActivity.query
    search = (request.args.get("q") or "").strip()
    section = (request.args.get("section") or "SUBJECTS").strip().upper()
    if section not in CATALOG_SECTIONS:
        section = "SUBJECTS"
    section_config = CATALOG_SECTIONS[section]
    activity_kind = (request.args.get("activity_kind") or "").strip().upper()
    show_archived = request.args.get("archived") == "1"

    organization_id = _current_organization_id()
    if organization_id is None:
        query = query.filter(EducationActivity.organization_id.is_(None))
    else:
        query = query.filter(or_(
            EducationActivity.organization_id == organization_id,
            EducationActivity.organization_id.is_(None),
        ))
    if not show_archived:
        query = query.filter(EducationActivity.is_active.is_(True))
    query = query.filter(
        EducationActivity.activity_kind.in_(section_config["kinds"])
    )
    if activity_kind in section_config["kinds"]:
        query = query.filter(EducationActivity.activity_kind == activity_kind)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.filter(or_(
            func.lower(EducationActivity.name).like(pattern),
            func.lower(func.coalesce(EducationActivity.short_name, "")).like(pattern),
        ))

    activities = query.order_by(EducationActivity.id.asc()).limit(500).all()
    activities.sort(
        key=lambda item: (
            " ".join(item.name.casefold().split()),
            item.id,
        )
    )
    can_manage = (
        is_feature_enabled(WORKLOAD_WRITE)
        and can_use_workload_permission("workload.settings.manage", current_user)
    )
    return render_template(
        "workload/catalog.html",
        activities=activities,
        activity_kinds=section_config["kinds"],
        kind_labels=ACTIVITY_KIND_LABELS,
        education_level_labels=EDUCATION_LEVEL_LABELS,
        catalog_sections=CATALOG_SECTIONS,
        selected_section=section,
        section_config=section_config,
        selected_kind=activity_kind,
        search=search,
        show_archived=show_archived,
        can_manage=can_manage,
    )


@workload_bp.route("/catalog/new", methods=["GET", "POST"])
@login_required
def catalog_create():
    _require_catalog_manage()
    section = (request.values.get("section") or "SUBJECTS").strip().upper()
    if section not in CATALOG_SECTIONS:
        section = "SUBJECTS"
    default_kind = (
        (request.values.get("activity_kind") or "").strip().upper()
        or CATALOG_SECTIONS[section]["default_kind"]
    )
    if default_kind not in ACTIVITY_KINDS:
        default_kind = CATALOG_SECTIONS[section]["default_kind"]
    if request.method == "POST":
        try:
            activity = _activity_from_form()
            db.session.add(activity)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except IntegrityError as exc:
            db.session.rollback()
            flash(_catalog_integrity_message(exc), "danger")
        else:
            flash("Элемент каталога создан.", "success")
            return redirect(url_for(
                "workload.catalog",
                section=_catalog_section_for_kind(activity.activity_kind),
            ))

    return render_template(
        "workload/activity_form.html",
        activity=None,
        activity_kinds=CATALOG_SECTIONS[section]["kinds"],
        kind_labels=ACTIVITY_KIND_LABELS,
        education_levels=EDUCATION_LEVELS,
        education_level_labels=EDUCATION_LEVEL_LABELS,
        departments=Department.query.order_by(Department.name.asc()).all(),
        selected_kind=default_kind,
        selected_section=section,
    )


@workload_bp.get("/catalog/<int:activity_id>")
@login_required
def catalog_detail(activity_id):
    activity = EducationActivity.query.get_or_404(activity_id)
    can_manage = (
        is_feature_enabled(WORKLOAD_WRITE)
        and can_use_workload_permission("workload.settings.manage", current_user)
    )
    return render_template(
        "workload/activity_detail.html",
        activity=activity,
        kind_labels=ACTIVITY_KIND_LABELS,
        education_level_labels=EDUCATION_LEVEL_LABELS,
        departments=Department.query.order_by(Department.name.asc()).all(),
        activity_usage=_activity_usage(activity),
        can_manage=can_manage,
    )


@workload_bp.route("/catalog/<int:activity_id>/edit", methods=["GET", "POST"])
@login_required
def catalog_edit(activity_id):
    _require_catalog_manage()
    activity = EducationActivity.query.get_or_404(activity_id)
    if request.method == "POST":
        try:
            _activity_from_form(activity)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except IntegrityError as exc:
            db.session.rollback()
            flash(_catalog_integrity_message(exc), "danger")
        else:
            flash("Элемент каталога сохранён.", "success")
            return redirect(url_for(
                "workload.catalog",
                section=_catalog_section_for_kind(activity.activity_kind),
            ))

    return render_template(
        "workload/activity_form.html",
        activity=activity,
        activity_kinds=ACTIVITY_KINDS,
        kind_labels=ACTIVITY_KIND_LABELS,
        education_levels=EDUCATION_LEVELS,
        education_level_labels=EDUCATION_LEVEL_LABELS,
        departments=Department.query.order_by(Department.name.asc()).all(),
        selected_kind=activity.activity_kind,
        selected_section=_catalog_section_for_kind(activity.activity_kind),
        activity_usage=_activity_usage(activity),
    )


@workload_bp.post("/catalog/<int:activity_id>/toggle-active")
@login_required
def catalog_toggle_active(activity_id):
    _require_catalog_manage()
    activity = EducationActivity.query.get_or_404(activity_id)
    activity.is_active = not activity.is_active
    activity.updated_by_user_id = current_user.id
    db.session.commit()
    flash("Статус элемента каталога изменён.", "success")
    return redirect(url_for("workload.catalog_detail", activity_id=activity.id))


@workload_bp.post("/catalog/<int:activity_id>/delete")
@login_required
def catalog_delete(activity_id):
    _require_catalog_manage()
    activity = EducationActivity.query.get_or_404(activity_id)
    usage = _activity_usage(activity)
    if usage["blocking_count"] or usage["reference_count"]:
        flash(
            "Удаление невозможно: запись используется другими разделами. "
            "Точные связи указаны в блоке «Где используется». Можно "
            "перевести запись в архив.",
            "danger",
        )
        return redirect(url_for(
            "workload.catalog_detail",
            activity_id=activity.id,
        ))

    section = _catalog_section_for_kind(activity.activity_kind)
    subject = activity.legacy_subject
    _detach_archived_teacher_loads(activity)
    if subject is not None:
        DepartmentSubject.query.filter_by(
            subject_id=subject.id,
        ).delete(synchronize_session=False)
        db.session.delete(subject)
        db.session.flush()
    db.session.delete(activity)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(
            "Удаление невозможно: в системе осталась связанная запись. "
            "Предмет не изменён; используйте перевод в архив.",
            "danger",
        )
        return redirect(url_for(
            "workload.catalog_detail",
            activity_id=activity.id,
        ))

    flash("Запись удалена из единого реестра.", "success")
    return redirect(url_for("workload.catalog", section=section))


@workload_bp.post("/catalog/<int:activity_id>/aliases")
@login_required
def catalog_alias_add(activity_id):
    _require_catalog_manage()
    activity = EducationActivity.query.get_or_404(activity_id)
    alias_value = " ".join((request.form.get("alias") or "").split())
    source_module = (request.form.get("source_module") or "GENERAL").strip().upper()
    source_system = (request.form.get("source_system") or "").strip()
    normalized = normalize_activity_name(alias_value)
    if not normalized:
        flash("Укажите вариант наименования.", "danger")
        return redirect(url_for("workload.catalog_detail", activity_id=activity.id))

    alias = EducationActivityAlias(
        education_activity_id=activity.id,
        organization_id=activity.organization_id,
        alias=alias_value,
        normalized_alias=normalized,
        source_module=source_module,
        source_system=source_system,
        confirmed_by_user_id=current_user.id,
        confirmed_at=db.func.now(),
    )
    db.session.add(alias)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Такое правило сопоставления уже существует.", "warning")
    else:
        flash("Алиас добавлен.", "success")
    return redirect(url_for("workload.catalog_detail", activity_id=activity.id))


@workload_bp.post("/catalog/<int:activity_id>/aliases/<int:alias_id>/toggle")
@login_required
def catalog_alias_toggle(activity_id, alias_id):
    _require_catalog_manage()
    alias = EducationActivityAlias.query.filter_by(
        id=alias_id,
        education_activity_id=activity_id,
    ).first_or_404()
    alias.is_active = not alias.is_active
    db.session.commit()
    flash("Статус алиаса изменён.", "success")
    return redirect(url_for("workload.catalog_detail", activity_id=activity_id))


@workload_bp.post("/catalog/<int:activity_id>/departments")
@login_required
def catalog_department_add(activity_id):
    _require_catalog_manage()
    activity = EducationActivity.query.get_or_404(activity_id)
    department_id = request.form.get("department_id", type=int)
    department = db.session.get(Department, department_id) if department_id else None
    if not department:
        flash("Выберите кафедру.", "danger")
        return redirect(url_for("workload.catalog_detail", activity_id=activity.id))

    existing = EducationActivityDepartment.query.filter_by(
        education_activity_id=activity.id,
        department_id=department.id,
        is_active=True,
    ).first()
    if existing:
        flash("Кафедра уже связана с элементом каталога.", "warning")
        return redirect(url_for("workload.catalog_detail", activity_id=activity.id))

    is_primary = request.form.get("is_primary") == "1"
    if is_primary:
        EducationActivityDepartment.query.filter_by(
            education_activity_id=activity.id,
            is_primary=True,
            is_active=True,
        ).update({"is_primary": False})
    db.session.add(EducationActivityDepartment(
        education_activity_id=activity.id,
        department_id=department.id,
        is_primary=is_primary,
    ))
    db.session.commit()
    flash("Связь с кафедрой добавлена.", "success")
    return redirect(url_for("workload.catalog_detail", activity_id=activity.id))


@workload_bp.post("/catalog/<int:activity_id>/departments/<int:link_id>/toggle")
@login_required
def catalog_department_toggle(activity_id, link_id):
    _require_catalog_manage()
    link = EducationActivityDepartment.query.filter_by(
        id=link_id,
        education_activity_id=activity_id,
    ).first_or_404()
    link.is_active = not link.is_active
    if not link.is_active:
        link.is_primary = False
    db.session.commit()
    flash("Статус связи с кафедрой изменён.", "success")
    return redirect(url_for("workload.catalog_detail", activity_id=activity_id))


register_plan_routes(workload_bp)
register_plan_binding_routes(workload_bp)
register_group_routes(workload_bp)
register_assignment_routes(workload_bp)
register_workflow_routes(workload_bp)


__all__ = ["workload_bp"]
