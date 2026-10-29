from datetime import date, datetime
from pathlib import Path
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, inspect, or_, text
from werkzeug.utils import secure_filename

from app.core.extensions import db, login_manager
from app.models_legacy import AcademicYear, Building, User
from app.roles import require_roles
from .access import (
    CHIEF_EDUCATOR,
    CONTINGENT_MANAGER,
    SENIOR_EDUCATOR,
    RESPONSIBILITY_KINDS,
    assigned_group_ids,
    assigned_building_ids,
    can_assign_responsibilities,
    can_manage_staff_in_building,
    can_manage_group_in_building,
    can_manage_contingent,
    can_open_preschool,
    can_view_all_contingent,
    can_view_child,
    managed_building_ids,
    manageable_group_building_ids,
    is_responsible,
    role_codes,
)
from .models import PreschoolAchievement, PreschoolAttendanceRecord, PreschoolAttendanceUpload, PreschoolBuildingStaff, PreschoolChild, PreschoolChildMovement, PreschoolChildrenImport, PreschoolDashboardSetting, PreschoolGroup, PreschoolGroupAssignment, PreschoolProfileChange, PreschoolRepresentative, PreschoolResponsibility, PreschoolResponsibilityChange, PreschoolRoleGrant, PreschoolStaffChange
from .roles import ensure_preschool_role, release_preschool_role_if_unused


bp = Blueprint(
    "preschool",
    __name__,
    url_prefix="/preschool",
    template_folder="templates",
)

_preschool_schema_checked = False

PRESCHOOL_AGE_LEVELS = [
    "ранний возраст",
    "младшая группа",
    "средняя группа",
    "старшая группа",
    "подготовительная группа",
    "разновозрастная группа",
]

STAFF_POSITIONS = {
    "SENIOR_EDUCATOR": "Старший воспитатель",
    "EDUCATOR": "Воспитатель",
    "ASSISTANT_EDUCATOR": "Помощник воспитателя",
    "PSYCHOLOGIST": "Педагог-психолог",
    "LOGOPEDIST": "Учитель-логопед",
    "DEFECTOLOGIST": "Учитель-дефектолог",
    "SOCIAL_PEDAGOG": "Социальный педагог",
    "TUTOR": "Тьютор",
    "SPECIALIST": "Другой специалист",
}
GROUP_POSITIONS = {key: STAFF_POSITIONS[key] for key in ("EDUCATOR", "ASSISTANT_EDUCATOR")}


def _date_from_form(name):
    value = (request.form.get(name) or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        abort(400)


def _valid_period(start_date, end_date):
    return not (start_date and end_date and start_date > end_date)


def _staff_change(scope, building_id, group_id, user_id, position, action):
    db.session.add(PreschoolStaffChange(
        scope=scope, building_id=building_id, group_id=group_id,
        user_id=user_id, position=position, action=action,
        changed_by_user_id=current_user.id,
    ))


def _get_current_year():
    year = (
        AcademicYear.query
        .filter_by(is_current=True)
        .order_by(AcademicYear.id.desc())
        .first()
    )
    if year:
        return year

    return (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .first()
    )


def _add_column_if_missing(inspector, table_name, column_name, ddl):
    columns = {c["name"] for c in inspector.get_columns(table_name)}
    if column_name not in columns:
        db.session.execute(text(ddl))
        db.session.commit()


def ensure_preschool_tables():
    """Создаёт и мягко обновляет таблицы ДОУ на чистой/тестовой базе."""
    global _preschool_schema_checked

    if _preschool_schema_checked:
        return

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    for model in (PreschoolGroup, PreschoolChildrenImport, PreschoolChild, PreschoolRepresentative, PreschoolChildMovement, PreschoolAttendanceUpload, PreschoolAttendanceRecord, PreschoolResponsibility, PreschoolResponsibilityChange, PreschoolRoleGrant, PreschoolBuildingStaff, PreschoolGroupAssignment, PreschoolStaffChange, PreschoolAchievement, PreschoolProfileChange, PreschoolDashboardSetting):
        if model.__tablename__ not in existing_tables:
            model.__table__.create(db.engine, checkfirst=True)

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    # Если preschool_group уже была создана на первом черновом этапе,
    # добавляем новые поля без пересоздания таблицы.
    if "preschool_group" in existing_tables:
        try:
            _add_column_if_missing(
                inspector,
                "preschool_group",
                "academic_year_id",
                "ALTER TABLE preschool_group ADD COLUMN academic_year_id INTEGER",
            )
            _add_column_if_missing(
                inspector,
                "preschool_group",
                "teacher_user_id",
                "ALTER TABLE preschool_group ADD COLUMN teacher_user_id INTEGER",
            )
            _add_column_if_missing(
                inspector,
                "preschool_group",
                "is_archived",
                "ALTER TABLE preschool_group ADD COLUMN is_archived BOOLEAN DEFAULT FALSE",
            )
        except Exception:
            db.session.rollback()

    if "preschool_child" in existing_tables:
        try:
            _add_column_if_missing(
                inspector,
                "preschool_child",
                "import_batch_id",
                "ALTER TABLE preschool_child ADD COLUMN import_batch_id INTEGER",
            )
            _add_column_if_missing(
                inspector,
                "preschool_child",
                "reg_address",
                "ALTER TABLE preschool_child ADD COLUMN reg_address VARCHAR(700)",
            )
            _add_column_if_missing(
                inspector,
                "preschool_child",
                "living_address",
                "ALTER TABLE preschool_child ADD COLUMN living_address VARCHAR(700)",
            )
            _add_column_if_missing(
                inspector,
                "preschool_child",
                "actual_address",
                "ALTER TABLE preschool_child ADD COLUMN actual_address VARCHAR(700)",
            )
        except Exception:
            db.session.rollback()

    if "preschool_representative" in existing_tables:
        try:
            _add_column_if_missing(
                inspector,
                "preschool_representative",
                "address",
                "ALTER TABLE preschool_representative ADD COLUMN address VARCHAR(700)",
            )
        except Exception:
            db.session.rollback()

    if "preschool_child_movement" in existing_tables:
        for column, ddl in (
            ("from_status", "ALTER TABLE preschool_child_movement ADD COLUMN from_status VARCHAR(50)"),
            ("to_status", "ALTER TABLE preschool_child_movement ADD COLUMN to_status VARCHAR(50)"),
            ("created_by_user_id", "ALTER TABLE preschool_child_movement ADD COLUMN created_by_user_id INTEGER"),
            ("reversed_at", "ALTER TABLE preschool_child_movement ADD COLUMN reversed_at TIMESTAMP"),
            ("reversed_by_user_id", "ALTER TABLE preschool_child_movement ADD COLUMN reversed_by_user_id INTEGER"),
        ):
            try:
                _add_column_if_missing(inspect(db.engine), "preschool_child_movement", column, ddl)
            except Exception:
                db.session.rollback()

    if "preschool_child_movement" in existing_tables:
        try:
            _add_column_if_missing(
                inspector,
                "preschool_child_movement",
                "from_academic_year_id",
                "ALTER TABLE preschool_child_movement ADD COLUMN from_academic_year_id INTEGER",
            )
            _add_column_if_missing(
                inspector,
                "preschool_child_movement",
                "to_academic_year_id",
                "ALTER TABLE preschool_child_movement ADD COLUMN to_academic_year_id INTEGER",
            )
        except Exception:
            db.session.rollback()

    if "teacher_mcko_result" in existing_tables:
        try:
            _add_column_if_missing(
                inspect(db.engine), "teacher_mcko_result", "diagnostic_title",
                "ALTER TABLE teacher_mcko_result ADD COLUMN diagnostic_title VARCHAR(255)",
            )
        except Exception:
            db.session.rollback()

    if "teacher_course" in existing_tables:
        for column, ddl in (
            ("document_title", "ALTER TABLE teacher_course ADD COLUMN document_title VARCHAR(255)"),
            ("document_number", "ALTER TABLE teacher_course ADD COLUMN document_number VARCHAR(120)"),
            ("entry_source", "ALTER TABLE teacher_course ADD COLUMN entry_source VARCHAR(24) DEFAULT 'LEGACY'"),
            ("created_by_user_id", "ALTER TABLE teacher_course ADD COLUMN created_by_user_id INTEGER"),
            ("updated_by_user_id", "ALTER TABLE teacher_course ADD COLUMN updated_by_user_id INTEGER"),
            ("updated_at", "ALTER TABLE teacher_course ADD COLUMN updated_at TIMESTAMP"),
        ):
            try:
                _add_column_if_missing(inspect(db.engine), "teacher_course", column, ddl)
            except Exception:
                db.session.rollback()

    _preschool_schema_checked = True


def _migrate_legacy_group_staff():
    """Copy one-teacher links once per application; inactive rows block re-grants."""
    from flask import current_app

    if current_app.config.get("_PRESCHOOL_LEGACY_STAFF_MIGRATED"):
        return
    for group in PreschoolGroup.query.filter(PreschoolGroup.teacher_user_id.isnot(None)).all():
        if db.session.get(User, group.teacher_user_id) is None:
            continue
        existing = PreschoolGroupAssignment.query.filter_by(
            group_id=group.id, user_id=group.teacher_user_id, position="EDUCATOR",
        ).first()
        if existing:
            continue
        db.session.add(PreschoolGroupAssignment(
            group_id=group.id, user_id=group.teacher_user_id,
            position="EDUCATOR", academic_year_id=group.academic_year_id,
            building_id=group.building_id, source="legacy",
        ))
        if group.building_id and not PreschoolBuildingStaff.query.filter_by(
            building_id=group.building_id, user_id=group.teacher_user_id, position="EDUCATOR",
        ).first():
            db.session.add(PreschoolBuildingStaff(
                building_id=group.building_id, user_id=group.teacher_user_id,
                position="EDUCATOR",
            ))
    db.session.commit()
    current_app.config["_PRESCHOOL_LEGACY_STAFF_MIGRATED"] = True


@bp.before_app_request
def before_request():
    ensure_preschool_tables()
    _migrate_legacy_group_staff()


@bp.before_request
def require_preschool_access():
    """Protect every existing preschool URL, including imports and POST actions."""
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    endpoint = (request.endpoint or "").rsplit(".", 1)[-1]
    if endpoint in {
        "attendance", "attendance_analytics", "attendance_upload_detail",
        "process_attendance_upload", "delete_attendance_upload",
    }:
        # Historical records remain stored while a replacement is designed.
        if request.method != "GET" or not can_open_preschool():
            abort(403)
        return render_template("preschool/attendance_paused.html")
    if endpoint == "index":
        if not can_open_preschool():
            abort(403)
    elif endpoint == "access_settings":
        if not can_assign_responsibilities():
            abort(403)
    elif endpoint == "staff_search":
        if not (can_assign_responsibilities() or managed_building_ids() or is_responsible(current_user, CONTINGENT_MANAGER)):
            abort(403)
    elif endpoint == "my_group":
        if not can_open_preschool():
            abort(403)
    elif endpoint in {
        "cabinet", "staff_profile", "profile_update", "mcko_save", "course_save",
        "achievement_save", "attestation_save", "composition", "dashboard", "dashboard_settings",
    }:
        if not can_open_preschool():
            abort(403)
    elif endpoint in {"staff", "building_staff_change", "group_staff", "group_staff_change"}:
        group_endpoint = endpoint in {"group_staff", "group_staff_change"}
        if group_endpoint:
            group = db.session.get(PreschoolGroup, request.view_args["group_id"])
            if group is None:
                abort(404)
            building_id = group.building_id
        else:
            building_id = request.view_args.get("building_id") if request.view_args else None
        if request.method == "GET":
            if not (can_assign_responsibilities() or "DEPUTY_DIRECTOR" in role_codes() or (manageable_group_building_ids() if group_endpoint else managed_building_ids())):
                abort(403)
            if building_id and not (can_assign_responsibilities() or "DEPUTY_DIRECTOR" in role_codes() or (can_manage_group_in_building(building_id) if group_endpoint else can_manage_staff_in_building(building_id))):
                abort(403)
        elif group_endpoint and request.form.get("action") in {"set_building", "inline_save"} and building_id is None:
            if not manageable_group_building_ids():
                abort(403)
        elif not (can_manage_group_in_building(building_id) if group_endpoint else can_manage_staff_in_building(building_id)):
            abort(403)
    elif endpoint == "child_card":
        child = db.session.get(PreschoolChild, request.view_args["child_id"])
        if child is None:
            abort(404)
        if not can_view_child(child):
            abort(403)
    elif endpoint in {"children", "children_registry"} and request.method == "GET":
        if not can_view_all_contingent():
            abort(403)
    elif not can_manage_contingent():
        abort(403)


@bp.context_processor
def _preschool_workspace_context():
    from app.modules.hub.routes import build_home_context

    return {
        "workspace_nav": build_home_context(),
        "workspace_context_title": "Дошкольное образование",
        "workspace_context_subtitle": "Группы, воспитанники и сотрудники",
        "can_manage_preschool_contingent": can_manage_contingent(),
        "can_view_all_preschool_contingent": can_view_all_contingent(),
        "can_assign_preschool_responsibilities": can_assign_responsibilities(),
        "can_manage_preschool_staff": can_assign_responsibilities() or bool(managed_building_ids()),
    }


@bp.route("/")
def index():
    year = _get_current_year()
    full_access = can_view_all_contingent()
    groups_query = PreschoolGroup.query.filter_by(is_archived=False)
    if year:
        groups_query = groups_query.filter_by(academic_year_id=year.id)
    if not full_access:
        groups_query = groups_query.filter(PreschoolGroup.id.in_(assigned_group_ids() or {-1}))
    groups = groups_query.order_by(PreschoolGroup.name.asc()).all()
    group_ids = [group.id for group in groups]
    children_count = PreschoolChild.query.filter(
        PreschoolChild.group_id.in_(group_ids or {-1}),
        PreschoolChild.status == "active",
    ).count()

    return render_template(
        "preschool/index.html",
        groups_count=len(groups),
        children_count=children_count,
        current_year_name=year.name if year else None,
        groups=groups,
        full_access=full_access,
        can_edit_contingent=can_manage_contingent(),
    )


@bp.get("/my-group")
def my_group():
    year = _get_current_year()
    query = PreschoolGroup.query.filter(
        PreschoolGroup.id.in_(assigned_group_ids() or {-1}),
        PreschoolGroup.is_archived.is_(False),
    )
    if year:
        query = query.filter(PreschoolGroup.academic_year_id == year.id)
    groups = query.order_by(PreschoolGroup.name.asc()).all()
    children = PreschoolChild.query.filter(
        PreschoolChild.group_id.in_([group.id for group in groups] or {-1}),
        PreschoolChild.status == "active",
    ).order_by(PreschoolChild.last_name.asc(), PreschoolChild.first_name.asc()).all()
    return render_template("preschool/my_group.html", groups=groups, children=children)


def _assignment_current(row):
    return bool(row and row.is_active)


def _group_staff_names(group, position):
    names = [row.user.fio or row.user.username for row in group.staff_assignments
             if row.position == position and _assignment_current(row)
             and group.id in assigned_group_ids(row.user)]
    return ", ".join(names) if names else "—"


def _group_staff_contacts(group, position):
    return [
        {"name": row.user.fio or row.user.username, "phone": row.user.phone,
         "user_id": row.user_id, "position": row.position}
        for row in group.staff_assignments
        if row.position == position and row.is_active and row.user
    ]


@bp.get("/staff/search")
def staff_search():
    query_text = " ".join((request.args.get("q") or "").split())[:80]
    if not query_text:
        return jsonify([])
    query = User.query.filter(
        User.is_active_user.is_(True), User.employment_status == "ACTIVE",
    )
    for token in query_text.split()[:4]:
        escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.filter(or_(
            User.last_name.ilike(pattern, escape="\\"),
            User.first_name.ilike(pattern, escape="\\"),
            User.middle_name.ilike(pattern, escape="\\"),
            User.username.ilike(pattern, escape="\\"),
        ))
    users = query.order_by(User.last_name, User.first_name, User.username).limit(12).all()
    return jsonify([
        {"id": user.id, "label": f"{user.fio or user.username} — {user.username}"}
        for user in users
    ])


@bp.get("/staff")
def staff():
    can_see_all = can_assign_responsibilities() or "DEPUTY_DIRECTOR" in role_codes()
    building_ids = managed_building_ids()
    year = _get_current_year()
    linked_building_ids = {
        building_id for building_id, in PreschoolGroup.query.with_entities(PreschoolGroup.building_id).filter(
            PreschoolGroup.academic_year_id == year.id if year else False,
            PreschoolGroup.is_archived.is_(False),
        ).distinct().all() if building_id
    }
    visible_ids = linked_building_ids if can_see_all else linked_building_ids & building_ids
    buildings = Building.query.filter(
        Building.is_preschool.is_(True), Building.id.in_(visible_ids or {-1}),
    ).order_by(Building.name.asc()).all()
    rows = PreschoolBuildingStaff.query.filter(
        PreschoolBuildingStaff.building_id.in_([building.id for building in buildings] or {-1}),
        PreschoolBuildingStaff.is_active.is_(True),
    ).order_by(PreschoolBuildingStaff.building_id, PreschoolBuildingStaff.position).all()
    groups = PreschoolGroup.query.filter(
        PreschoolGroup.building_id.in_([building.id for building in buildings] or {-1}),
        PreschoolGroup.is_archived.is_(False),
        PreschoolGroup.academic_year_id == year.id if year else False,
    ).order_by(PreschoolGroup.name.asc()).all()
    return render_template(
        "preschool/staff.html", buildings=buildings, rows=rows, groups=groups,
        positions=STAFF_POSITIONS,
        assignable_positions=STAFF_POSITIONS if can_assign_responsibilities() else {
            key: value for key, value in STAFF_POSITIONS.items() if key != SENIOR_EDUCATOR
        },
        editable_building_ids=building_ids,
    )


@bp.post("/staff/buildings/<int:building_id>")
def building_staff_change(building_id):
    building = db.session.get(Building, building_id)
    if building is None or not building.is_preschool:
        abort(404)
    user_id = request.form.get("user_id", type=int)
    position = (request.form.get("position") or "").strip()
    action = (request.form.get("action") or "assign").strip()
    user = db.session.get(User, user_id) if user_id else None
    if not user or position not in STAFF_POSITIONS or action not in {"assign", "revoke"}:
        abort(400)
    if action == "assign" and (not user.is_active_user or user.employment_status != "ACTIVE"):
        abort(400)
    if position == SENIOR_EDUCATOR and not can_assign_responsibilities():
        abort(403)
    row = PreschoolBuildingStaff.query.filter_by(
        building_id=building_id, user_id=user_id, position=position,
    ).first()
    if action == "revoke":
        if row is None or not row.is_active:
            abort(404)
        row.is_active = False
        for group_row in PreschoolGroupAssignment.query.filter_by(
            user_id=user_id, building_id=building_id, position=position, is_active=True,
        ).all():
            group_row.is_active = False
            group_row.end_date = date.today()
            _staff_change("group", building_id, group_row.group_id, user_id, position, "revoke")
        db.session.flush()
        release_preschool_role_if_unused(user, position)
    else:
        if row is None:
            row = PreschoolBuildingStaff(
                building_id=building_id, user_id=user_id, position=position,
            )
            db.session.add(row)
        elif row.is_active:
            abort(409)
        row.start_date = None
        row.end_date = None
        row.is_active = True
        row.assigned_by_user_id = current_user.id
        ensure_preschool_role(user, position)
        if position == SENIOR_EDUCATOR:
            _add_responsibility(SENIOR_EDUCATOR, user)
    _staff_change("building", building_id, None, user_id, position, action)
    db.session.commit()
    flash("Назначение сотрудника обновлено.", "success")
    return redirect(url_for("preschool.staff"))


@bp.route("/groups/<int:group_id>/staff", methods=["GET", "POST"])
def group_staff(group_id):
    group = db.session.get(PreschoolGroup, group_id)
    if group is None:
        abort(404)
    if group.building_id and (not group.building or not group.building.is_preschool):
        abort(404)
    if request.method == "POST":
        action = (request.form.get("action") or "assign").strip()
        return_to_summary = action == "inline_save" or request.form.get("return_to") == "summary"
        if action == "inline_save":
            building_id = request.form.get("building_id", type=int)
            building = db.session.get(Building, building_id) if building_id else None
            if not building or not building.is_preschool or not can_manage_group_in_building(building.id):
                abort(403)
            if group.building_id != building.id and PreschoolGroupAssignment.query.filter_by(group_id=group.id, is_active=True).first():
                flash("Перед сменой корпуса снимите назначения сотрудников группы.", "warning")
                return redirect(url_for("preschool.children", academic_year_id=group.academic_year_id))
            group.building_id = building.id
            if not request.form.get("user_id", type=int):
                db.session.commit()
                flash("Корпус группы сохранён.", "success")
                return redirect(url_for("preschool.children", academic_year_id=group.academic_year_id))
            action = "assign"
        if action == "set_building":
            building_id = request.form.get("building_id", type=int)
            building = db.session.get(Building, building_id) if building_id else None
            if not building or not building.is_preschool or not can_manage_group_in_building(building.id):
                abort(403)
            if group.building_id != building.id and PreschoolGroupAssignment.query.filter_by(group_id=group.id, is_active=True).first():
                flash("Перед сменой корпуса снимите назначения сотрудников группы.", "warning")
                return redirect(url_for("preschool.group_staff", group_id=group.id))
            group.building_id = building.id
            db.session.commit()
            flash("Корпус группы обновлён.", "success")
            return redirect(url_for("preschool.group_staff", group_id=group.id))
        if not group.building_id:
            abort(409)
        user_id = request.form.get("user_id", type=int)
        position = (request.form.get("position") or "").strip()
        user = db.session.get(User, user_id) if user_id else None
        if not user or position not in GROUP_POSITIONS or action not in {"assign", "revoke"}:
            abort(400)
        if action == "assign" and (not user.is_active_user or user.employment_status != "ACTIVE"):
            abort(400)
        row = PreschoolGroupAssignment.query.filter_by(
            group_id=group.id, user_id=user_id, position=position,
        ).first()
        if action == "revoke":
            if row is None or not row.is_active:
                abort(404)
            row.is_active = False
            row.end_date = date.today()
        else:
            if not group.is_active or group.is_archived or group.academic_year_id is None:
                abort(409)
            member = PreschoolBuildingStaff.query.filter_by(
                building_id=group.building_id, user_id=user_id, position=position,
            ).first()
            if not _assignment_current(member):
                if member is None:
                    member = PreschoolBuildingStaff(building_id=group.building_id, user_id=user_id, position=position)
                    db.session.add(member)
                member.is_active = True
                member.start_date = None
                member.end_date = None
                member.assigned_by_user_id = current_user.id
                ensure_preschool_role(user, position)
                _staff_change("building", group.building_id, None, user_id, position, "assign")
            if row is None:
                row = PreschoolGroupAssignment(group_id=group.id, user_id=user_id, position=position)
                db.session.add(row)
            elif row.is_active:
                abort(409)
            row.academic_year_id = group.academic_year_id
            row.building_id = group.building_id
            row.start_date = None
            row.end_date = None
            row.is_active = True
            row.source = "manual"
            row.assigned_by_user_id = current_user.id
        _staff_change("group", group.building_id, group.id, user_id, position, action)
        db.session.commit()
        flash("Состав группы обновлён.", "success")
        return redirect(url_for("preschool.children", academic_year_id=group.academic_year_id) if return_to_summary else url_for("preschool.group_staff", group_id=group.id))
    assignments = PreschoolGroupAssignment.query.filter_by(
        group_id=group.id, is_active=True,
    ).order_by(PreschoolGroupAssignment.position.asc()).all()
    available_buildings = Building.query.filter(
        Building.id.in_(manageable_group_building_ids() or {-1}),
        Building.is_preschool.is_(True),
    ).order_by(Building.name.asc()).all()
    return render_template(
        "preschool/group_staff.html", group=group, assignments=assignments,
        available_buildings=available_buildings,
        positions=GROUP_POSITIONS, can_edit=can_manage_group_in_building(group.building_id),
        can_set_building=bool(available_buildings),
    )


def _add_responsibility(kind, user):
    if PreschoolResponsibility.query.filter_by(kind=kind, user_id=user.id).first():
        return False
    db.session.add(PreschoolResponsibility(
        kind=kind, user_id=user.id, assigned_by_user_id=current_user.id,
    ))
    db.session.add(PreschoolResponsibilityChange(
        kind=kind, previous_user_id=None, new_user_id=user.id,
        changed_by_user_id=current_user.id,
    ))
    if kind == SENIOR_EDUCATOR:
        ensure_preschool_role(user, SENIOR_EDUCATOR)
    return True


def _remove_responsibility(row):
    user = row.user
    db.session.add(PreschoolResponsibilityChange(
        kind=row.kind, previous_user_id=row.user_id, new_user_id=None,
        changed_by_user_id=current_user.id,
    ))
    db.session.delete(row)
    db.session.flush()
    if row.kind == SENIOR_EDUCATOR and user:
        release_preschool_role_if_unused(user, SENIOR_EDUCATOR)


@bp.route("/access", methods=["GET", "POST"])
def access_settings():
    if request.method == "POST":
        kind = (request.form.get("kind") or "").strip()
        action = (request.form.get("action") or "assign").strip()
        user_id = request.form.get("user_id", type=int)
        if action == "assign" and not user_id and kind in {CONTINGENT_MANAGER, CHIEF_EDUCATOR}:
            action = "revoke"
        if kind not in RESPONSIBILITY_KINDS or action not in {"assign", "revoke"}:
            abort(400)
        user = db.session.get(User, user_id) if user_id else None
        if action == "assign" and user_id and (
            user is None or not user.is_active_user or user.employment_status != "ACTIVE"
        ):
            flash("Выберите действующего сотрудника.", "warning")
            return redirect(url_for("preschool.access_settings"))

        if kind == CHIEF_EDUCATOR:
            row = PreschoolResponsibility.query.filter_by(kind=kind).first()
            if action == "revoke" or not user_id:
                if row:
                    _remove_responsibility(row)
            else:
                _add_responsibility(SENIOR_EDUCATOR, user)
                previous_user_id = row.user_id if row else None
                if previous_user_id != user.id:
                    if row is None:
                        row = PreschoolResponsibility(kind=kind)
                        db.session.add(row)
                    row.user_id = user.id
                    row.assigned_by_user_id = current_user.id
                    db.session.add(PreschoolResponsibilityChange(
                        kind=kind, previous_user_id=previous_user_id,
                        new_user_id=user.id, changed_by_user_id=current_user.id,
                    ))
        elif action == "assign":
            if user is None:
                abort(400)
            _add_responsibility(kind, user)
        else:
            rows = PreschoolResponsibility.query.filter_by(kind=kind)
            if user_id:
                rows = rows.filter_by(user_id=user_id)
            selected = rows.all()
            if user_id and not selected:
                abort(404)
            for row in selected:
                if kind == SENIOR_EDUCATOR and PreschoolResponsibility.query.filter_by(
                    kind=CHIEF_EDUCATOR, user_id=row.user_id,
                ).first():
                    flash("Сначала смените ответственного за аттестацию.", "warning")
                    return redirect(url_for("preschool.access_settings"))
                _remove_responsibility(row)

        db.session.commit()
        flash("Назначения обновлены.", "success")
        return redirect(url_for("preschool.access_settings"))

    assignments = {kind: [] for kind in RESPONSIBILITY_KINDS}
    for row in PreschoolResponsibility.query.filter(
        PreschoolResponsibility.kind.in_(RESPONSIBILITY_KINDS),
        PreschoolResponsibility.user_id.isnot(None),
    ).order_by(PreschoolResponsibility.id).all():
        assignments[row.kind].append(row)
    changes = PreschoolResponsibilityChange.query.order_by(
        PreschoolResponsibilityChange.changed_at.desc(),
        PreschoolResponsibilityChange.id.desc(),
    ).limit(20).all()
    return render_template(
        "preschool/access.html",
        assignments=assignments,
        changes=changes,
        chief_kind=CHIEF_EDUCATOR,
        senior_kind=SENIOR_EDUCATOR,
        contingent_kind=CONTINGENT_MANAGER,
    )


@bp.route("/children")
def children():
    year_id = request.args.get("academic_year_id", type=int)
    building_id = request.args.get("building_id", type=int)

    year = AcademicYear.query.get(year_id) if year_id else _get_current_year()

    if not year:
        flash("Сначала создайте учебный год в служебном разделе.", "warning")
        return redirect(url_for("children.academic_years_registry"))

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )
    month_options = _academic_year_month_options(year)
    month_options = _academic_year_month_options(year)

    buildings = Building.query.filter_by(is_preschool=True).order_by(Building.name.asc()).all()

    groups_query = (
        PreschoolGroup.query
        .filter(PreschoolGroup.academic_year_id == year.id)
        .outerjoin(Building, PreschoolGroup.building_id == Building.id)
    )

    if building_id:
        groups_query = groups_query.filter(PreschoolGroup.building_id == building_id)

    groups = (
        groups_query
        .order_by(Building.name.asc(), PreschoolGroup.name.asc())
        .all()
    )

    group_rows = []
    total_children = 0
    age_counts = {}
    building_ids = set()

    for group in groups:
        children_count = PreschoolChild.query.filter(
            PreschoolChild.group_id == group.id,
            PreschoolChild.status == "active",
        ).count()
        total_children += children_count

        if group.building_id:
            building_ids.add(group.building_id)

        age_name = group.age_level or "Не указано"
        age_counts[age_name] = age_counts.get(age_name, 0) + children_count

        group_rows.append({
            "id": group.id,
            "name": group.name,
            "building": group.building.name if group.building else "Не назначено",
            "building_id": group.building_id,
            "age_level": group.age_level or "—",
            "educators": _group_staff_contacts(group, "EDUCATOR"),
            "assistants": _group_staff_contacts(group, "ASSISTANT_EDUCATOR"),
            "can_manage": can_manage_group_in_building(group.building_id) if group.building_id else bool(manageable_group_building_ids()),
            "children_count": children_count,
        })

    stats = {
        "total": total_children,
        "groups": len(groups),
        "buildings": len(building_ids),
        "early": age_counts.get("ранний возраст", 0),
        "junior": age_counts.get("младшая группа", 0),
        "middle": age_counts.get("средняя группа", 0),
        "senior": age_counts.get("старшая группа", 0),
        "prep": age_counts.get("подготовительная группа", 0),
    }

    return render_template(
        "preschool/children.html",
        group_rows=group_rows,
        buildings=buildings,
        available_group_buildings=[building for building in buildings if building.id in manageable_group_building_ids()],
        all_years=all_years,
        year=year,
        selected_building_id=building_id,
        stats=stats,
    )


@bp.route("/children/registry", methods=["GET", "POST"])
def children_registry():
    year_id = request.args.get("academic_year_id", type=int)
    building_id = request.args.get("building_id", type=int)
    group_id = request.args.get("group_id", type=int)
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "active").strip()
    if status not in {"active", "left", "transfer_school", "all"}:
        status = "active"

    page = max(request.args.get("page", 1, type=int), 1)
    per_page = request.args.get("per_page", 20, type=int)
    if per_page not in (20, 50, 100):
        per_page = 20

    year = AcademicYear.query.get(year_id) if year_id else _get_current_year()

    if not year:
        flash("Сначала создайте учебный год в служебном разделе.", "warning")
        return redirect(url_for("children.academic_years_registry"))

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )

    buildings = Building.query.filter_by(is_preschool=True).order_by(Building.name.asc()).all()

    groups_query = PreschoolGroup.query.filter(PreschoolGroup.academic_year_id == year.id)
    if building_id:
        groups_query = groups_query.filter(PreschoolGroup.building_id == building_id)

    groups = groups_query.order_by(PreschoolGroup.name.asc()).all()

    if request.method == "POST":
        last_name = (request.form.get("last_name") or "").strip()
        first_name = (request.form.get("first_name") or "").strip()
        middle_name = (request.form.get("middle_name") or "").strip()
        birth_date_raw = (request.form.get("birth_date") or "").strip()
        personal_account = (request.form.get("personal_account") or "").strip()
        reg_address = (request.form.get("reg_address") or "").strip()
        living_address = (request.form.get("living_address") or "").strip()
        actual_address = (request.form.get("actual_address") or "").strip()
        note = (request.form.get("note") or "").strip()
        group_id_raw = (request.form.get("group_id") or "").strip()

        if not last_name or not first_name:
            flash("Укажите фамилию и имя воспитанника.", "warning")
            return redirect(url_for(
                "preschool.children_registry",
                academic_year_id=year.id,
                building_id=building_id,
                group_id=group_id,
                per_page=per_page,
            ))

        selected_group = db.session.get(PreschoolGroup, int(group_id_raw)) if group_id_raw.isdigit() else None
        if selected_group is None or selected_group.academic_year_id != year.id or selected_group.is_archived or not selected_group.is_active:
            flash("Выберите группу выбранного учебного года.", "warning")
            return redirect(url_for("preschool.children_registry", academic_year_id=year.id))

        birth_date = None
        if birth_date_raw:
            from datetime import datetime
            try:
                birth_date = datetime.strptime(birth_date_raw, "%Y-%m-%d").date()
            except ValueError:
                birth_date = None

        child = PreschoolChild(
            group_id=selected_group.id,
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name or None,
            birth_date=birth_date,
            personal_account=personal_account or None,
            reg_address=reg_address or None,
            living_address=living_address or None,
            actual_address=actual_address or None,
            status="active",
            note=note or None,
        )

        db.session.add(child)
        db.session.commit()

        flash("Воспитанник добавлен в реестр ДОУ.", "success")
        return redirect(url_for(
            "preschool.children_registry",
            academic_year_id=year.id,
            building_id=building_id,
            group_id=group_id,
            per_page=per_page,
        ))

    base_query = (
        PreschoolChild.query
        .join(PreschoolGroup, PreschoolChild.group_id == PreschoolGroup.id)
        .filter(PreschoolGroup.academic_year_id == year.id)
    )

    if building_id:
        base_query = base_query.filter(PreschoolGroup.building_id == building_id)

    if group_id:
        base_query = base_query.filter(PreschoolChild.group_id == group_id)

    if q:
        like = f"%{q}%"
        base_query = base_query.filter(
            or_(
                PreschoolChild.last_name.ilike(like),
                PreschoolChild.first_name.ilike(like),
                PreschoolChild.middle_name.ilike(like),
            )
        )

    if status != "all":
        base_query = base_query.filter(PreschoolChild.status == status)

    ordered_query = (
        base_query
        .order_by(
            PreschoolGroup.name.asc(),
            PreschoolChild.last_name.asc(),
            PreschoolChild.first_name.asc(),
        )
    )

    pagination = ordered_query.paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    items = pagination.items

    stats_query = (
        db.session.query(PreschoolGroup.age_level, func.count(PreschoolChild.id))
        .join(PreschoolChild, PreschoolChild.group_id == PreschoolGroup.id)
        .filter(PreschoolGroup.academic_year_id == year.id)
    )

    if building_id:
        stats_query = stats_query.filter(PreschoolGroup.building_id == building_id)

    if group_id:
        stats_query = stats_query.filter(PreschoolGroup.id == group_id)
    if status != "all":
        stats_query = stats_query.filter(PreschoolChild.status == status)

    age_counts = {
        name or "Не указано": count
        for name, count in stats_query.group_by(PreschoolGroup.age_level).all()
    }

    groups_total_query = PreschoolGroup.query.filter(PreschoolGroup.academic_year_id == year.id)
    if building_id:
        groups_total_query = groups_total_query.filter(PreschoolGroup.building_id == building_id)

    buildings_used_query = (
        db.session.query(func.count(func.distinct(PreschoolGroup.building_id)))
        .filter(PreschoolGroup.academic_year_id == year.id)
        .filter(PreschoolGroup.building_id.isnot(None))
    )
    if building_id:
        buildings_used_query = buildings_used_query.filter(PreschoolGroup.building_id == building_id)

    stats = {
        "total": pagination.total,
        "groups": groups_total_query.count(),
        "buildings": buildings_used_query.scalar() or 0,
        "early": age_counts.get("ранний возраст", 0),
        "junior": age_counts.get("младшая группа", 0),
        "middle": age_counts.get("средняя группа", 0),
        "senior": age_counts.get("старшая группа", 0),
        "prep": age_counts.get("подготовительная группа", 0),
    }

    return render_template(
        "preschool/children_registry.html",
        items=items,
        groups=groups,
        buildings=buildings,
        all_years=all_years,
        year=year,
        selected_building_id=building_id,
        selected_group_id=group_id,
        q=q,
        status=status,
        pagination=pagination,
        page=page,
        per_page=per_page,
        stats=stats,
    )


@bp.route("/buildings")
def buildings_redirect():
    # Отдельного справочника корпусов ДОУ больше нет:
    # используем общий реестр зданий проекта.
    return redirect(url_for("children.buildings_registry"))


@bp.route("/groups", methods=["GET", "POST"])
def groups():
    year_id = request.args.get("academic_year_id", type=int)
    year = AcademicYear.query.get(year_id) if year_id else _get_current_year()

    if not year:
        flash("Сначала создайте учебный год в служебном разделе.", "warning")
        return redirect(url_for("children.academic_years_registry"))

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )
    buildings = Building.query.filter_by(is_preschool=True).order_by(Building.name.asc()).all()
    if request.method == "POST":
        if not can_assign_responsibilities():
            abort(403)
        name = (request.form.get("name") or "").strip()
        age_level = (request.form.get("age_level") or "").strip()
        building_id_raw = (request.form.get("building_id") or "").strip()
        academic_year_id_raw = (request.form.get("academic_year_id") or "").strip()

        if not name:
            flash("Укажите название группы.", "warning")
            return redirect(url_for("preschool.groups", academic_year_id=year.id))

        academic_year_id = int(academic_year_id_raw) if academic_year_id_raw.isdigit() else year.id
        building_id = int(building_id_raw) if building_id_raw.isdigit() else None
        building = db.session.get(Building, building_id) if building_id else None
        if db.session.get(AcademicYear, academic_year_id) is None or not building or not building.is_preschool:
            flash("Выберите действующий учебный год и дошкольный корпус.", "warning")
            return redirect(url_for("preschool.groups", academic_year_id=year.id))
        if PreschoolGroup.query.filter_by(academic_year_id=academic_year_id, building_id=building_id, name=name).first():
            flash("Группа с таким названием уже есть в выбранном здании и учебном году.", "warning")
            return redirect(url_for("preschool.groups", academic_year_id=year.id))

        group = PreschoolGroup(
            academic_year_id=academic_year_id,
            building_id=building_id,
            name=name,
            age_level=age_level or None,
            is_active=True,
            is_archived=False,
        )
        db.session.add(group)
        db.session.commit()

        flash("Группа ДОУ учебного года добавлена.", "success")
        return redirect(url_for("preschool.groups", academic_year_id=academic_year_id))

    items = (
        PreschoolGroup.query
        .filter(PreschoolGroup.academic_year_id == year.id)
        .outerjoin(Building, PreschoolGroup.building_id == Building.id)
        .order_by(Building.name.asc(), PreschoolGroup.name.asc())
        .all()
    )

    return render_template(
        "preschool/groups.html",
        items=items,
        group_staff_names=_group_staff_names,
        group_staff_contacts=_group_staff_contacts,
        can_edit_group_metadata=can_assign_responsibilities(),
        can_manage_group=lambda group: not group.building_id and bool(manageable_group_building_ids()) or can_manage_group_in_building(group.building_id),
        buildings=buildings,
        age_levels=PRESCHOOL_AGE_LEVELS,
        all_years=all_years,
        year=year,
    )

@bp.route("/groups/<int:group_id>/edit", methods=["GET", "POST"])
@require_roles("ADMIN")
def edit_group(group_id):
    group = PreschoolGroup.query.get_or_404(group_id)

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )
    buildings = Building.query.filter_by(is_preschool=True).order_by(Building.name.asc()).all()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        age_level = (request.form.get("age_level") or "").strip()
        building_id_raw = (request.form.get("building_id") or "").strip()
        academic_year_id_raw = (request.form.get("academic_year_id") or "").strip()

        if not name:
            flash("Укажите название группы.", "warning")
            return redirect(url_for("preschool.edit_group", group_id=group.id))

        if academic_year_id_raw and (not academic_year_id_raw.isdigit() or int(academic_year_id_raw) != group.academic_year_id):
            flash("Учебный год группы не меняется через редактирование. Используйте движение воспитанников.", "warning")
            return redirect(url_for("preschool.edit_group", group_id=group.id))
        building_id = int(building_id_raw) if building_id_raw.isdigit() else None
        building = db.session.get(Building, building_id) if building_id else None
        if not building or not building.is_preschool:
            flash("Выберите дошкольный корпус из общего реестра.", "warning")
            return redirect(url_for("preschool.edit_group", group_id=group.id))
        if building_id != group.building_id and any(row.is_active for row in group.staff_assignments):
            flash("Сначала снимите назначения сотрудников группы перед сменой здания.", "warning")
            return redirect(url_for("preschool.edit_group", group_id=group.id))
        duplicate = PreschoolGroup.query.filter_by(
            academic_year_id=group.academic_year_id,
            building_id=building_id,
            name=name,
        ).filter(PreschoolGroup.id != group.id).first()
        if duplicate:
            flash("Группа с таким названием уже есть в выбранном здании и учебном году.", "warning")
            return redirect(url_for("preschool.edit_group", group_id=group.id))

        group.name = name
        group.age_level = age_level or None
        group.building_id = building_id

        db.session.commit()

        flash("Группа ДОУ обновлена.", "success")
        return redirect(url_for("preschool.groups", academic_year_id=group.academic_year_id))

    return render_template(
        "preschool/group_form.html",
        group=group,
        buildings=buildings,
        age_levels=PRESCHOOL_AGE_LEVELS,
        all_years=all_years,
    )


@bp.route("/groups/<int:group_id>/delete", methods=["POST"])
@require_roles("ADMIN")
def delete_group(group_id):
    group = PreschoolGroup.query.get_or_404(group_id)
    academic_year_id = group.academic_year_id

    if group.children or any(row.is_active for row in group.staff_assignments):
        flash("Нельзя удалить группу, если к ней уже прикреплены воспитанники. Позже добавим архивирование.", "warning")
        return redirect(url_for("preschool.groups", academic_year_id=academic_year_id))

    db.session.delete(group)
    db.session.commit()

    flash("Группа ДОУ удалена.", "success")
    return redirect(url_for("preschool.groups", academic_year_id=academic_year_id))

def _normalize_header(value):
    value = str(value or "").strip().lower()
    value = value.replace("ё", "е")
    value = value.replace(".", "")
    value = value.replace(" ", "")
    value = value.replace("_", "")
    return value


def _split_full_name(full_name):
    parts = [p for p in str(full_name or "").strip().split() if p]
    if not parts:
        return "", "", None

    last_name = parts[0] if len(parts) >= 1 else ""
    first_name = parts[1] if len(parts) >= 2 else ""
    middle_name = " ".join(parts[2:]) if len(parts) >= 3 else None
    return last_name, first_name, middle_name


def _parse_excel_date(value):
    if not value:
        return None

    from datetime import datetime, date

    if isinstance(value, date):
        return value

    raw = str(value).strip()
    if not raw:
        return None

    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass

    return None


@bp.route("/children/import", methods=["GET", "POST"])
def import_children():
    year_id = request.args.get("academic_year_id", type=int) or request.form.get("academic_year_id", type=int)
    year = AcademicYear.query.get(year_id) if year_id else _get_current_year()

    if not year:
        flash("Сначала создайте учебный год в служебном разделе.", "warning")
        return redirect(url_for("children.academic_years_registry"))

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )

    groups = (
        PreschoolGroup.query
        .filter(PreschoolGroup.academic_year_id == year.id)
        .order_by(PreschoolGroup.name.asc())
        .all()
    )
    groups_by_name = {g.name.strip().lower(): g for g in groups}
    buildings = Building.query.filter_by(is_preschool=True).order_by(Building.name.asc()).all()
    buildings_by_name = {b.name.strip().lower(): b for b in buildings}

    imports = (
        PreschoolChildrenImport.query
        .filter(PreschoolChildrenImport.academic_year_id == year.id)
        .order_by(PreschoolChildrenImport.created_at.desc(), PreschoolChildrenImport.id.desc())
        .all()
    )

    result = None

    if request.method == "POST":
        uploaded = request.files.get("file")

        if not uploaded or not uploaded.filename:
            flash("Выберите Excel-файл с контингентом ДОУ.", "warning")
            return redirect(url_for("preschool.import_children", academic_year_id=year.id))

        if not uploaded.filename.lower().endswith((".xlsx", ".xlsm")):
            flash("Поддерживаются файлы .xlsx и .xlsm. Старый формат .xls сохраните в новом формате Excel.", "warning")
            return redirect(url_for("preschool.import_children", academic_year_id=year.id))

        try:
            from openpyxl import load_workbook
        except Exception:
            flash("Не установлен openpyxl. Установите зависимости из requirements.txt.", "danger")
            return redirect(url_for("preschool.import_children", academic_year_id=year.id))

        try:
            workbook = load_workbook(uploaded, data_only=True)
        except Exception:
            flash("Не удалось прочитать файл Excel. Проверьте формат и содержимое.", "warning")
            return redirect(url_for("preschool.import_children", academic_year_id=year.id))
        sheet = workbook.active

        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            flash("Файл пустой.", "warning")
            return redirect(url_for("preschool.import_children", academic_year_id=year.id))

        header_row_index = None
        header_map = {}

        aliases = {
            "case_number": {"личноедело№", "личноедело", "номерличногодела"},
            "fio": {"фио", "фиоребенка", "фиовоспитанника", "фамилияимяотчество", "воспитанник", "ребенок"},
            "group": {"группа", "группадоу", "наименованиегруппы"},
            "birth_date": {"датарождения", "др", "рождение", "родился", "родилась"},
            "reg_address": {"адресрегистрации", "регистрация", "адреспрописки", "прописка", "регистрацияпоместужительства", "адресрегистрациипоместужительства"},
            "living_address": {"адреспроживания", "проживание", "адресместажительства", "местожительства", "регистрацияпоместупребывания", "адресрегистрациипоместупребывания"},
            "actual_address": {"фактическийадрес", "адресфактический", "фактическоепроживание", "адресфактическогопроживания", "фактическоеместопроживания"},
            "note": {"примечание", "комментарий", "комментарии", "дополнительныесведениякод", "дополнительныесведения"},
        }

        for idx, row in enumerate(rows[:15]):
            normalized = [_normalize_header(cell) for cell in row]
            found = {}
            for col_index, name in enumerate(normalized):
                for key, variants in aliases.items():
                    if name in variants:
                        found[key] = col_index

            if "fio" in found and "group" in found:
                header_row_index = idx
                header_map = found
                break

        if header_row_index is None:
            flash("Не удалось найти заголовки. Нужны минимум колонки: ФИО и Группа.", "danger")
            return redirect(url_for("preschool.import_children", academic_year_id=year.id))

        added = 0
        skipped = 0
        created_groups = 0
        errors = []

        import_batch = PreschoolChildrenImport(
            academic_year_id=year.id,
            filename=uploaded.filename,
            added_count=0,
            skipped_count=0,
            created_groups_count=0,
        )
        db.session.add(import_batch)
        db.session.flush()

        for row_number, row in enumerate(rows[header_row_index + 1:], start=header_row_index + 2):
            case_number = row[header_map["case_number"]] if header_map.get("case_number") is not None and header_map["case_number"] < len(row) else None
            fio = row[header_map["fio"]] if header_map.get("fio") is not None and header_map["fio"] < len(row) else None
            group_name = row[header_map["group"]] if header_map.get("group") is not None and header_map["group"] < len(row) else None
            birth_raw = row[header_map["birth_date"]] if header_map.get("birth_date") is not None and header_map["birth_date"] < len(row) else None
            reg_address = row[header_map["reg_address"]] if header_map.get("reg_address") is not None and header_map["reg_address"] < len(row) else None
            living_address = row[header_map["living_address"]] if header_map.get("living_address") is not None and header_map["living_address"] < len(row) else None
            actual_address = row[header_map["actual_address"]] if header_map.get("actual_address") is not None and header_map["actual_address"] < len(row) else None
            note = row[header_map["note"]] if header_map.get("note") is not None and header_map["note"] < len(row) else None

            if not fio and not group_name:
                continue

            last_name, first_name, middle_name = _split_full_name(fio)
            if not last_name or not first_name:
                skipped += 1
                errors.append(f"Строка {row_number}: не удалось разобрать ФИО «{fio}»")
                continue

            group_key = str(group_name or "").strip().lower()
            group = groups_by_name.get(group_key)

            if not group:
                clean_group_name = str(group_name or "").strip()

                # Пытаемся определить здание по первой части названия группы:
                # например, ДК2-7 -> ДК2.
                building = None
                building_key = None

                if "-" in clean_group_name:
                    building_key = clean_group_name.split("-", 1)[0].strip().lower()
                    building = buildings_by_name.get(building_key)

                group = PreschoolGroup(
                    academic_year_id=year.id,
                    building_id=building.id if building else None,
                    name=clean_group_name,
                    age_level=None,
                    teacher_user_id=None,
                    teacher_name=None,
                    is_active=True,
                    is_archived=False,
                )
                db.session.add(group)
                db.session.flush()

                groups_by_name[group_key] = group
                created_groups += 1

            parsed_birth_date = _parse_excel_date(birth_raw)

            duplicate_query = (
                PreschoolChild.query
                .filter(PreschoolChild.group_id == group.id)
                .filter(func.lower(PreschoolChild.last_name) == last_name.lower())
                .filter(func.lower(PreschoolChild.first_name) == first_name.lower())
            )
            if middle_name:
                duplicate_query = duplicate_query.filter(func.lower(PreschoolChild.middle_name) == middle_name.lower())
            else:
                duplicate_query = duplicate_query.filter(or_(
                    PreschoolChild.middle_name.is_(None),
                    PreschoolChild.middle_name == "",
                ))

            if parsed_birth_date:
                duplicate_query = duplicate_query.filter(PreschoolChild.birth_date == parsed_birth_date)

            duplicate = duplicate_query.first()

            if duplicate:
                skipped += 1
                continue

            child = PreschoolChild(
                group_id=group.id,
                import_batch_id=import_batch.id,
                last_name=last_name,
                first_name=first_name,
                middle_name=middle_name,
                birth_date=parsed_birth_date,
                personal_account=str(case_number).strip() if case_number else None,
                reg_address=str(reg_address).strip() if reg_address else None,
                living_address=str(living_address).strip() if living_address else None,
                actual_address=str(actual_address).strip() if actual_address else None,
                status="active",
                note=str(note).strip() if note else None,
            )

            db.session.add(child)
            added += 1

        import_batch.added_count = added
        import_batch.skipped_count = skipped
        import_batch.created_groups_count = created_groups

        db.session.commit()

        imports = (
            PreschoolChildrenImport.query
            .filter(PreschoolChildrenImport.academic_year_id == year.id)
            .order_by(PreschoolChildrenImport.created_at.desc(), PreschoolChildrenImport.id.desc())
            .all()
        )

        result = {
            "added": added,
            "skipped": skipped,
            "created_groups": created_groups,
            "errors": errors[:30],
            "errors_total": len(errors),
        }

        flash(f"Импорт завершён: добавлено {added}, создано групп {created_groups}, пропущено {skipped}.", "success")

    return render_template(
        "preschool/import_children.html",
        year=year,
        all_years=all_years,
        groups=groups,
        imports=imports,
        result=result,
    )


@bp.route("/children/imports/<int:import_id>/delete", methods=["POST"])
def delete_children_import(import_id):
    import_batch = PreschoolChildrenImport.query.get_or_404(import_id)
    year_id = import_batch.academic_year_id

    deleted_count = PreschoolChild.query.filter(
        PreschoolChild.import_batch_id == import_batch.id
    ).delete(synchronize_session=False)

    db.session.delete(import_batch)
    db.session.commit()

    flash(f"Импорт удалён. Удалено воспитанников: {deleted_count}.", "success")
    return redirect(url_for("preschool.import_children", academic_year_id=year_id))


@bp.route("/children/clear-year", methods=["POST"])
def clear_children_year():
    year_id = request.form.get("academic_year_id", type=int)
    year = AcademicYear.query.get_or_404(year_id)

    child_ids = [
        child_id for (child_id,) in (
            db.session.query(PreschoolChild.id)
            .join(PreschoolGroup, PreschoolChild.group_id == PreschoolGroup.id)
            .filter(PreschoolGroup.academic_year_id == year.id)
            .all()
        )
    ]

    deleted_count = 0
    if child_ids:
        deleted_count = PreschoolChild.query.filter(
            PreschoolChild.id.in_(child_ids)
        ).delete(synchronize_session=False)

    PreschoolChildrenImport.query.filter(
        PreschoolChildrenImport.academic_year_id == year.id
    ).delete(synchronize_session=False)

    db.session.commit()

    flash(f"Контингент ДОУ за {year.name} очищен. Удалено воспитанников: {deleted_count}.", "success")
    return redirect(url_for("preschool.import_children", academic_year_id=year.id))


def _normalize_phone(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    return raw


@bp.route("/representatives/import", methods=["GET", "POST"])
def import_representatives():
    year_id = request.args.get("academic_year_id", type=int) or request.form.get("academic_year_id", type=int)
    year = AcademicYear.query.get(year_id) if year_id else _get_current_year()

    if not year:
        flash("Сначала создайте учебный год в служебном разделе.", "warning")
        return redirect(url_for("children.academic_years_registry"))

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )

    result = None

    if request.method == "POST":
        uploaded = request.files.get("file")

        if not uploaded or not uploaded.filename:
            flash("Выберите Excel-файл с представителями.", "warning")
            return redirect(url_for("preschool.import_representatives", academic_year_id=year.id))

        if not uploaded.filename.lower().endswith((".xlsx", ".xlsm")):
            flash("Поддерживаются файлы .xlsx и .xlsm. Старый формат .xls сохраните в новом формате Excel.", "warning")
            return redirect(url_for("preschool.import_representatives", academic_year_id=year.id))

        try:
            from openpyxl import load_workbook
        except Exception:
            flash("Не установлен openpyxl. Установите зависимости из requirements.txt.", "danger")
            return redirect(url_for("preschool.import_representatives", academic_year_id=year.id))

        try:
            workbook = load_workbook(uploaded, data_only=True)
        except Exception:
            flash("Не удалось прочитать файл Excel. Проверьте формат и содержимое.", "warning")
            return redirect(url_for("preschool.import_representatives", academic_year_id=year.id))
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))

        if not rows:
            flash("Файл пустой.", "warning")
            return redirect(url_for("preschool.import_representatives", academic_year_id=year.id))

        aliases = {
            "case_number": {"личноедело№", "личноедело", "номерличногодела", "лд"},
            "child_fio": {"фиоребенка", "ребенок", "воспитанник", "фиовоспитанника"},
            "relation": {"родство", "степеньродства", "типпредставителя", "представитель", "законныйпредставитель"},
            "full_name": {"фио", "фиопредставителя", "фиородителя", "родитель", "представительфио"},
            "phone": {"телефон", "мобильныйтелефон", "контактныйтелефон", "тел"},
            "email": {"email", "почта", "электроннаяпочта", "e-mail"},
            "address": {"адрес", "адресрегистрации", "адреспроживания", "фактическийадрес"},
            "note": {"примечание", "комментарий", "комментарии"},
        }

        header_row_index = None
        header_map = {}

        for idx, row in enumerate(rows[:20]):
            normalized = [_normalize_header(cell) for cell in row]
            found = {}
            for col_index, name in enumerate(normalized):
                for key, variants in aliases.items():
                    if name in variants:
                        found[key] = col_index

            if ("case_number" in found or "child_fio" in found) and "full_name" in found:
                header_row_index = idx
                header_map = found
                break

        if header_row_index is None:
            flash("Не удалось найти заголовки. Нужны минимум: Личное дело № или ФИО ребёнка, и ФИО представителя.", "danger")
            return redirect(url_for("preschool.import_representatives", academic_year_id=year.id))

        added = 0
        skipped = 0
        errors = []

        for row_number, row in enumerate(rows[header_row_index + 1:], start=header_row_index + 2):
            case_number = row[header_map["case_number"]] if header_map.get("case_number") is not None and header_map["case_number"] < len(row) else None
            child_fio = row[header_map["child_fio"]] if header_map.get("child_fio") is not None and header_map["child_fio"] < len(row) else None
            relation = row[header_map["relation"]] if header_map.get("relation") is not None and header_map["relation"] < len(row) else None
            full_name = row[header_map["full_name"]] if header_map.get("full_name") is not None and header_map["full_name"] < len(row) else None
            phone = row[header_map["phone"]] if header_map.get("phone") is not None and header_map["phone"] < len(row) else None
            email = row[header_map["email"]] if header_map.get("email") is not None and header_map["email"] < len(row) else None
            address = row[header_map["address"]] if header_map.get("address") is not None and header_map["address"] < len(row) else None
            note = row[header_map["note"]] if header_map.get("note") is not None and header_map["note"] < len(row) else None

            if not full_name:
                continue

            child = None

            if case_number:
                child = (
                    PreschoolChild.query
                    .join(PreschoolGroup, PreschoolChild.group_id == PreschoolGroup.id)
                    .filter(PreschoolGroup.academic_year_id == year.id)
                    .filter(PreschoolChild.personal_account == str(case_number).strip())
                    .first()
                )

            if not child and child_fio:
                last_name, first_name, middle_name = _split_full_name(child_fio)
                if last_name and first_name:
                    query = (
                        PreschoolChild.query
                        .join(PreschoolGroup, PreschoolChild.group_id == PreschoolGroup.id)
                        .filter(PreschoolGroup.academic_year_id == year.id)
                        .filter(func.lower(PreschoolChild.last_name) == last_name.lower())
                        .filter(func.lower(PreschoolChild.first_name) == first_name.lower())
                    )
                    if middle_name:
                        query = query.filter(func.lower(PreschoolChild.middle_name) == middle_name.lower())
                    child = query.first()

            if not child:
                skipped += 1
                errors.append(f"Строка {row_number}: ребёнок не найден")
                continue

            duplicate = (
                PreschoolRepresentative.query
                .filter(PreschoolRepresentative.child_id == child.id)
                .filter(func.lower(PreschoolRepresentative.full_name) == str(full_name).strip().lower())
                .first()
            )

            if duplicate:
                skipped += 1
                continue

            representative = PreschoolRepresentative(
                child_id=child.id,
                relation=str(relation).strip() if relation else None,
                full_name=str(full_name).strip(),
                phone=_normalize_phone(phone),
                email=str(email).strip() if email else None,
                address=str(address).strip() if address else None,
                note=str(note).strip() if note else None,
            )

            db.session.add(representative)
            added += 1

        db.session.commit()

        result = {
            "added": added,
            "skipped": skipped,
            "errors": errors[:30],
            "errors_total": len(errors),
        }

        flash(f"Импорт представителей завершён: добавлено {added}, пропущено {skipped}.", "success")

    return render_template(
        "preschool/import_representatives.html",
        year=year,
        all_years=all_years,
        result=result,
    )


@bp.route("/representatives/<int:representative_id>/delete", methods=["POST"])
def delete_representative(representative_id):
    representative = PreschoolRepresentative.query.get_or_404(representative_id)
    child_id = representative.child_id

    db.session.delete(representative)
    db.session.commit()

    flash("Представитель удалён.", "success")
    return redirect(url_for("preschool.child_card", child_id=child_id))


def _decode_zip_name(name):
    try:
        return name.encode("cp437").decode("utf-8")
    except Exception:
        return name


def _extract_preschool_group_name(filename):
    import re

    clean = _decode_zip_name(filename)
    base = Path(clean).name
    match = re.search(r"(ДК\s*\d+\s*[-–]\s*\d+)", base, re.IGNORECASE)
    if not match:
        return None

    group_name = match.group(1)
    group_name = group_name.replace(" ", "")
    group_name = group_name.replace("–", "-")
    return group_name.upper()


def _int_from_cell(value):
    if value is None:
        return 0

    raw = str(value).strip()
    if not raw:
        return 0

    raw = raw.replace(",", ".")
    try:
        return int(float(raw))
    except Exception:
        return 0


def _split_attendance_name(full_name):
    parts = [p for p in str(full_name or "").strip().split() if p]
    if len(parts) < 2:
        return None, None, None

    last_name = parts[0]
    first_name = parts[1]
    middle_name = " ".join(parts[2:]) if len(parts) > 2 else None
    return last_name, first_name, middle_name


def _is_attendance_service_row(value):
    """Пропускаем даты, итоги и технические строки внутри табеля."""
    if value is None:
        return True

    raw = str(value).strip()
    if not raw:
        return True

    lowered = raw.lower().replace("ё", "е")

    service_words = (
        "итого",
        "всего",
        "дата",
        "дни",
        "месяц",
        "табель",
        "группа",
        "воспитатель",
    )

    if any(lowered.startswith(word) for word in service_words):
        return True

    # Примеры из табеля: "31 мая 2026 г.", "1 май 2026 г."
    month_words = (
        "январ", "феврал", "март", "апрел", "мая", "май",
        "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр",
    )

    if any(month in lowered for month in month_words) and any(ch.isdigit() for ch in lowered):
        return True

    # Даты вида 31.05.2026 или 2026-05-31
    import re
    if re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", lowered):
        return True

    if re.fullmatch(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", lowered):
        return True

    return False


def _find_or_create_preschool_group(year, group_name):
    if not group_name:
        return None

    group = (
        PreschoolGroup.query
        .filter(PreschoolGroup.academic_year_id == year.id)
        .filter(func.lower(PreschoolGroup.name) == group_name.lower())
        .first()
    )

    if group:
        return group

    building = None
    if "-" in group_name:
        building_key = group_name.split("-", 1)[0].strip().lower()
        building = (
            Building.query
            .filter(Building.is_preschool.is_(True), func.lower(Building.name) == building_key)
            .first()
        )

    group = PreschoolGroup(
        academic_year_id=year.id,
        building_id=building.id if building else None,
        name=group_name,
        is_active=True,
        is_archived=False,
    )
    db.session.add(group)
    db.session.flush()

    return group


def _find_preschool_child(year, group, child_name, account_number):
    if account_number:
        child = (
            PreschoolChild.query
            .join(PreschoolGroup, PreschoolChild.group_id == PreschoolGroup.id)
            .filter(PreschoolGroup.academic_year_id == year.id)
            .filter(PreschoolChild.personal_account == str(account_number).strip())
            .first()
        )
        if child:
            return child

    last_name, first_name, middle_name = _split_attendance_name(child_name)
    if not last_name or not first_name:
        return None

    query = (
        PreschoolChild.query
        .join(PreschoolGroup, PreschoolChild.group_id == PreschoolGroup.id)
        .filter(PreschoolGroup.academic_year_id == year.id)
        .filter(func.lower(PreschoolChild.last_name) == last_name.lower())
        .filter(func.lower(PreschoolChild.first_name) == first_name.lower())
    )

    if middle_name:
        query = query.filter(func.lower(PreschoolChild.middle_name) == middle_name.lower())

    if group:
        query = query.filter(PreschoolChild.group_id == group.id)

    return query.first()


def _parse_attendance_workbook(year, upload, filename, file_bytes):
    from io import BytesIO
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(file_bytes), data_only=True)
    sheet = workbook.active

    group_name = _extract_preschool_group_name(filename)
    group = _find_or_create_preschool_group(year, group_name)

    created = 0
    errors = []

    # В табелях из архива реальные колонки такие:
    # C = ФИО, AB = номер счета, DI = пропущено всего,
    # DN = засчитываемые пропуски, DT = дни к оплате, EC = причины.
    for row in range(14, sheet.max_row + 1):
        child_name = sheet.cell(row=row, column=3).value

        if not child_name:
            continue

        child_name = str(child_name).strip()

        # Пропускаем даты, итоги и технические строки.
        if _is_attendance_service_row(child_name):
            continue

        # ФИО ребёнка должно состоять минимум из фамилии и имени.
        last_name_check, first_name_check, _ = _split_attendance_name(child_name)
        if not last_name_check or not first_name_check:
            continue

        account_number = sheet.cell(row=row, column=28).value
        missed_total = _int_from_cell(sheet.cell(row=row, column=113).value)
        credited_days = _int_from_cell(sheet.cell(row=row, column=118).value)
        payment_days = _int_from_cell(sheet.cell(row=row, column=124).value)
        reasons = sheet.cell(row=row, column=133).value

        child_days = max(payment_days - credited_days, 0)

        child = _find_preschool_child(year, group, child_name, account_number)

        record = PreschoolAttendanceRecord(
            upload_id=upload.id,
            group_id=group.id if group else None,
            child_id=child.id if child else None,
            source_filename=_decode_zip_name(filename),
            child_name=child_name,
            account_number=str(account_number).strip() if account_number else None,
            missed_total=missed_total,
            credited_days=credited_days,
            payment_days=payment_days,
            child_days=child_days,
            absence_reasons=str(reasons).strip() if reasons else None,
        )

        db.session.add(record)
        created += 1

        if not child:
            errors.append(f"{child_name}: не найден в контингенте")

    return {
        "created": created,
        "group_name": group.name if group else group_name,
        "errors": errors,
    }


def _process_attendance_zip(year, upload):
    import zipfile

    processed_files = 0
    created_records = 0
    errors = []

    with zipfile.ZipFile(upload.stored_filename, "r") as archive:
        for member in archive.namelist():
            decoded_name = _decode_zip_name(member)

            if member.startswith("__MACOSX/") or decoded_name.startswith("__MACOSX/"):
                continue

            if not decoded_name.lower().endswith((".xlsx", ".xlsm")):
                continue

            file_bytes = archive.read(member)
            processed_files += 1

            try:
                result = _parse_attendance_workbook(year, upload, decoded_name, file_bytes)
                created_records += result["created"]
                errors.extend(result["errors"][:20])
            except Exception as exc:
                errors.append(f"{decoded_name}: {exc}")

    upload.status = "processed"
    upload.comment = (
        f"Обработано файлов: {processed_files}. "
        f"Создано строк табеля: {created_records}. "
        f"Ошибок сопоставления: {len(errors)}."
    )

    db.session.commit()

    return {
        "processed_files": processed_files,
        "created_records": created_records,
        "errors": errors,
    }


MONTH_LABELS_RU = {
    "01": "Январь",
    "02": "Февраль",
    "03": "Март",
    "04": "Апрель",
    "05": "Май",
    "06": "Июнь",
    "07": "Июль",
    "08": "Август",
    "09": "Сентябрь",
    "10": "Октябрь",
    "11": "Ноябрь",
    "12": "Декабрь",
}


def _academic_year_month_options(year):
    """Список месяцев для выбранного учебного года: сентябрь–август."""
    if not year or not year.name or "/" not in year.name:
        return []

    try:
        start_year = int(str(year.name).split("/", 1)[0])
    except Exception:
        return []

    months = []
    for month_num in range(9, 13):
        value = f"{start_year}-{month_num:02d}"
        months.append({"value": value, "label": f"{MONTH_LABELS_RU[f'{month_num:02d}']} {start_year}"})

    next_year = start_year + 1
    for month_num in range(1, 9):
        value = f"{next_year}-{month_num:02d}"
        months.append({"value": value, "label": f"{MONTH_LABELS_RU[f'{month_num:02d}']} {next_year}"})

    return months


def _month_label(value):
    if not value or "-" not in str(value):
        return "—"

    year_part, month_part = str(value).split("-", 1)
    month_part = month_part[:2]

    return f"{MONTH_LABELS_RU.get(month_part, month_part)} {year_part}"


def _detect_month_from_zip(stored_filename, year):
    """Пытаемся определить месяц по названиям файлов внутри архива: ДК1-1 май.xlsx."""
    import zipfile

    if not stored_filename or not year:
        return None

    month_words = {
        "январ": "01",
        "феврал": "02",
        "март": "03",
        "апрел": "04",
        "май": "05",
        "мая": "05",
        "июн": "06",
        "июл": "07",
        "август": "08",
        "сентябр": "09",
        "октябр": "10",
        "ноябр": "11",
        "декабр": "12",
    }

    try:
        start_year = int(str(year.name).split("/", 1)[0])
    except Exception:
        start_year = None

    try:
        with zipfile.ZipFile(stored_filename, "r") as archive:
            names = [_decode_zip_name(name).lower() for name in archive.namelist()]
    except Exception:
        return None

    for name in names:
        for word, month_num in month_words.items():
            if word in name:
                if not start_year:
                    return None

                # Учебный год: сентябрь-декабрь относятся к первому году,
                # январь-август — ко второму.
                year_num = start_year if int(month_num) >= 9 else start_year + 1
                return f"{year_num}-{month_num}"

    return None


@bp.route("/attendance", methods=["GET", "POST"])
def attendance():
    year_id = request.args.get("academic_year_id", type=int) or request.form.get("academic_year_id", type=int)
    month = (request.args.get("month") or request.form.get("month") or "").strip()

    year = AcademicYear.query.get(year_id) if year_id else _get_current_year()

    if not year:
        flash("Сначала создайте учебный год в служебном разделе.", "warning")
        return redirect(url_for("children.academic_years_registry"))

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )
    month_options = _academic_year_month_options(year)

    if request.method == "POST":
        uploaded = request.files.get("file")

        if not uploaded or not uploaded.filename:
            flash("Выберите ZIP-архив с табелями ДОУ.", "warning")
            return redirect(url_for("preschool.attendance", academic_year_id=year.id, month=month))

        if not uploaded.filename.lower().endswith(".zip"):
            flash("Для загрузки табелей нужен ZIP-архив.", "warning")
            return redirect(url_for("preschool.attendance", academic_year_id=year.id, month=month))

        from flask import current_app
        import uuid

        upload_root = Path(current_app.config.get("UPLOAD_FOLDER", "uploads"))
        folder = upload_root / "preschool" / "attendance"
        folder.mkdir(parents=True, exist_ok=True)

        safe_name = secure_filename(uploaded.filename)
        stored_name = f"{uuid.uuid4().hex}_{safe_name}"
        stored_path = folder / stored_name
        uploaded.save(stored_path)

        detected_month = month or _detect_month_from_zip(str(stored_path), year)

        item = PreschoolAttendanceUpload(
            academic_year_id=year.id,
            month=detected_month or None,
            original_filename=uploaded.filename,
            stored_filename=str(stored_path),
            status="uploaded",
            comment="Архив загружен.",
        )

        db.session.add(item)
        db.session.commit()

        try:
            result = _process_attendance_zip(year, item)
            flash(
                f"ZIP загружен и обработан: файлов {result['processed_files']}, строк {result['created_records']}.",
                "success",
            )
            month = item.month or month
        except Exception as exc:
            item.status = "error"
            item.comment = f"Ошибка обработки архива: {exc}"
            db.session.commit()
            flash(f"ZIP загружен, но обработка завершилась ошибкой: {exc}", "danger")

        return redirect(url_for("preschool.attendance", academic_year_id=year.id, month=month))

    query = PreschoolAttendanceUpload.query.filter(PreschoolAttendanceUpload.academic_year_id == year.id)

    if month:
        query = query.filter(PreschoolAttendanceUpload.month == month)

    uploads = query.order_by(
        PreschoolAttendanceUpload.created_at.desc(),
        PreschoolAttendanceUpload.id.desc()
    ).all()

    upload_stats = {}
    for item in uploads:
        records = PreschoolAttendanceRecord.query.filter(
            PreschoolAttendanceRecord.upload_id == item.id
        )
        upload_stats[item.id] = {
            "records": records.count(),
            "child_days": db.session.query(func.coalesce(func.sum(PreschoolAttendanceRecord.child_days), 0))
                .filter(PreschoolAttendanceRecord.upload_id == item.id)
                .scalar() or 0,
            "payment_days": db.session.query(func.coalesce(func.sum(PreschoolAttendanceRecord.payment_days), 0))
                .filter(PreschoolAttendanceRecord.upload_id == item.id)
                .scalar() or 0,
            "credited_days": db.session.query(func.coalesce(func.sum(PreschoolAttendanceRecord.credited_days), 0))
                .filter(PreschoolAttendanceRecord.upload_id == item.id)
                .scalar() or 0,
        }

    return render_template(
        "preschool/attendance.html",
        year=year,
        all_years=all_years,
        month=month,
        uploads=uploads,
        upload_stats=upload_stats,
        month_options=month_options,
        month_label=_month_label,
    )


@bp.route("/attendance/analytics")
def attendance_analytics():
    year_id = request.args.get("academic_year_id", type=int)
    month = (request.args.get("month") or "").strip()
    upload_id = request.args.get("upload_id", type=int)

    year = AcademicYear.query.get(year_id) if year_id else _get_current_year()

    if not year:
        flash("Сначала создайте учебный год в служебном разделе.", "warning")
        return redirect(url_for("children.academic_years_registry"))

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )
    month_options = _academic_year_month_options(year)

    uploads_query = PreschoolAttendanceUpload.query.filter(
        PreschoolAttendanceUpload.academic_year_id == year.id
    )

    if month:
        uploads_query = uploads_query.filter(PreschoolAttendanceUpload.month == month)

    uploads = uploads_query.order_by(
        PreschoolAttendanceUpload.created_at.desc(),
        PreschoolAttendanceUpload.id.desc()
    ).all()

    records_query = (
        PreschoolAttendanceRecord.query
        .join(PreschoolAttendanceUpload, PreschoolAttendanceRecord.upload_id == PreschoolAttendanceUpload.id)
        .outerjoin(PreschoolGroup, PreschoolAttendanceRecord.group_id == PreschoolGroup.id)
        .outerjoin(Building, PreschoolGroup.building_id == Building.id)
        .filter(PreschoolAttendanceUpload.academic_year_id == year.id)
    )

    if month:
        records_query = records_query.filter(PreschoolAttendanceUpload.month == month)

    if upload_id:
        records_query = records_query.filter(PreschoolAttendanceRecord.upload_id == upload_id)

    records = records_query.all()

    total = {
        "records": len(records),
        "matched": sum(1 for item in records if item.child_id),
        "unmatched": sum(1 for item in records if not item.child_id),
        "payment_days": sum(item.payment_days or 0 for item in records),
        "credited_days": sum(item.credited_days or 0 for item in records),
        "child_days": sum(item.child_days or 0 for item in records),
    }

    building_map = {}
    group_map = {}

    for record in records:
        group = record.group
        building_name = group.building.name if group and group.building else "Без корпуса"
        group_name = group.name if group else "Без группы"

        if building_name not in building_map:
            building_map[building_name] = {
                "name": building_name,
                "records": 0,
                "matched": 0,
                "unmatched": 0,
                "payment_days": 0,
                "credited_days": 0,
                "child_days": 0,
                "groups": set(),
            }

        building_row = building_map[building_name]
        building_row["records"] += 1
        building_row["payment_days"] += record.payment_days or 0
        building_row["credited_days"] += record.credited_days or 0
        building_row["child_days"] += record.child_days or 0
        building_row["groups"].add(group_name)

        if record.child_id:
            building_row["matched"] += 1
        else:
            building_row["unmatched"] += 1

        if group_name not in group_map:
            group_map[group_name] = {
                "name": group_name,
                "building": building_name,
                "records": 0,
                "matched": 0,
                "unmatched": 0,
                "payment_days": 0,
                "credited_days": 0,
                "child_days": 0,
            }

        group_row = group_map[group_name]
        group_row["records"] += 1
        group_row["payment_days"] += record.payment_days or 0
        group_row["credited_days"] += record.credited_days or 0
        group_row["child_days"] += record.child_days or 0

        if record.child_id:
            group_row["matched"] += 1
        else:
            group_row["unmatched"] += 1

    building_rows = []
    for row in building_map.values():
        row = dict(row)
        row["groups_count"] = len(row["groups"])
        row.pop("groups", None)
        building_rows.append(row)

    building_rows = sorted(building_rows, key=lambda x: x["name"])
    group_rows = sorted(group_map.values(), key=lambda x: (x["building"], x["name"]))

    # Динамика по месяцам строится по всем загрузкам выбранного учебного года.
    month_records_query = (
        PreschoolAttendanceRecord.query
        .join(PreschoolAttendanceUpload, PreschoolAttendanceRecord.upload_id == PreschoolAttendanceUpload.id)
        .filter(PreschoolAttendanceUpload.academic_year_id == year.id)
    )

    if upload_id:
        month_records_query = month_records_query.filter(PreschoolAttendanceRecord.upload_id == upload_id)

    month_records = month_records_query.all()

    month_map = {}
    for record in month_records:
        upload = record.upload
        month_key = upload.month or "Не указан"

        if month_key not in month_map:
            month_map[month_key] = {
                "month": month_key,
                "month_label": _month_label(month_key) if month_key != "Не указан" else "Не указан",
                "records": 0,
                "payment_days": 0,
                "credited_days": 0,
                "child_days": 0,
            }

        row = month_map[month_key]
        row["records"] += 1
        row["payment_days"] += record.payment_days or 0
        row["credited_days"] += record.credited_days or 0
        row["child_days"] += record.child_days or 0

    def _month_sort_key(row):
        value = row["month"]
        if value == "Не указан":
            return "9999-99"
        return value

    month_rows = sorted(month_map.values(), key=_month_sort_key)

    max_building_child_days = max([row["child_days"] for row in building_rows] or [1])
    max_group_child_days = max([row["child_days"] for row in group_rows] or [1])
    max_month_child_days = max([row["child_days"] for row in month_rows] or [1])

    return render_template(
        "preschool/attendance_analytics.html",
        year=year,
        all_years=all_years,
        month=month,
        upload_id=upload_id,
        uploads=uploads,
        month_options=month_options,
        total=total,
        building_rows=building_rows,
        group_rows=group_rows,
        month_rows=month_rows,
        max_building_child_days=max_building_child_days,
        max_group_child_days=max_group_child_days,
        max_month_child_days=max_month_child_days,
        month_label=_month_label,
    )


@bp.route("/attendance/uploads/<int:upload_id>")
def attendance_upload_detail(upload_id):
    item = PreschoolAttendanceUpload.query.get_or_404(upload_id)

    records_query = (
        PreschoolAttendanceRecord.query
        .filter(PreschoolAttendanceRecord.upload_id == item.id)
        .outerjoin(PreschoolGroup, PreschoolAttendanceRecord.group_id == PreschoolGroup.id)
        .order_by(
            PreschoolGroup.name.asc(),
            PreschoolAttendanceRecord.child_name.asc(),
        )
    )

    records = records_query.all()

    group_rows = []
    group_map = {}

    for record in records:
        key = record.group.name if record.group else "Без группы"

        if key not in group_map:
            group_map[key] = {
                "group_name": key,
                "records": 0,
                "matched": 0,
                "unmatched": 0,
                "payment_days": 0,
                "credited_days": 0,
                "child_days": 0,
            }

        row = group_map[key]
        row["records"] += 1
        row["payment_days"] += record.payment_days or 0
        row["credited_days"] += record.credited_days or 0
        row["child_days"] += record.child_days or 0

        if record.child_id:
            row["matched"] += 1
        else:
            row["unmatched"] += 1

    group_rows = sorted(group_map.values(), key=lambda x: x["group_name"])

    total = {
        "records": len(records),
        "matched": sum(1 for record in records if record.child_id),
        "unmatched": sum(1 for record in records if not record.child_id),
        "payment_days": sum(record.payment_days or 0 for record in records),
        "credited_days": sum(record.credited_days or 0 for record in records),
        "child_days": sum(record.child_days or 0 for record in records),
    }

    unmatched_records = [record for record in records if not record.child_id]

    return render_template(
        "preschool/attendance_upload_detail.html",
        item=item,
        records=records,
        group_rows=group_rows,
        total=total,
        unmatched_records=unmatched_records,
    )


@bp.route("/attendance/uploads/<int:upload_id>/process", methods=["POST"])
def process_attendance_upload(upload_id):
    item = PreschoolAttendanceUpload.query.get_or_404(upload_id)
    year = item.academic_year

    if not year:
        flash("У загрузки не указан учебный год.", "warning")
        return redirect(url_for("preschool.attendance"))

    # Удаляем старые строки этой загрузки, если уже пробовали обрабатывать.
    PreschoolAttendanceRecord.query.filter(
        PreschoolAttendanceRecord.upload_id == item.id
    ).delete(synchronize_session=False)
    db.session.commit()

    try:
        result = _process_attendance_zip(year, item)
        flash(
            f"Архив обработан: файлов {result['processed_files']}, строк {result['created_records']}.",
            "success",
        )
    except Exception as exc:
        item.status = "error"
        item.comment = f"Ошибка обработки архива: {exc}"
        db.session.commit()
        flash(f"Ошибка обработки архива: {exc}", "danger")

    return redirect(url_for(
        "preschool.attendance",
        academic_year_id=item.academic_year_id,
        month=item.month,
    ))


@bp.route("/attendance/uploads/<int:upload_id>/delete", methods=["POST"])
def delete_attendance_upload(upload_id):
    item = PreschoolAttendanceUpload.query.get_or_404(upload_id)
    year_id = item.academic_year_id
    month = item.month

    try:
        if item.stored_filename:
            path = Path(item.stored_filename)
            if path.exists():
                path.unlink()
    except Exception:
        pass

    PreschoolAttendanceRecord.query.filter(
        PreschoolAttendanceRecord.upload_id == item.id
    ).delete(synchronize_session=False)

    db.session.delete(item)
    db.session.commit()

    flash("Загрузка табелей удалена.", "success")
    return redirect(url_for("preschool.attendance", academic_year_id=year_id, month=month))


@bp.route("/movements")
def movements():
    year_id = request.args.get("academic_year_id", type=int)
    movement_type = (request.args.get("movement_type") or "").strip()
    q = (request.args.get("q") or "").strip()

    year = AcademicYear.query.get(year_id) if year_id else _get_current_year()

    if not year:
        flash("Сначала создайте учебный год в служебном разделе.", "warning")
        return redirect(url_for("children.academic_years_registry"))

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )

    query = (
        PreschoolChildMovement.query
        .join(PreschoolChild, PreschoolChildMovement.child_id == PreschoolChild.id)
        .outerjoin(PreschoolGroup, PreschoolChild.group_id == PreschoolGroup.id)
        .filter(or_(
            PreschoolChildMovement.from_academic_year_id == year.id,
            PreschoolChildMovement.to_academic_year_id == year.id,
            PreschoolGroup.academic_year_id == year.id,
        ))
    )

    if movement_type:
        query = query.filter(PreschoolChildMovement.movement_type == movement_type)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                PreschoolChild.last_name.ilike(like),
                PreschoolChild.first_name.ilike(like),
                PreschoolChild.middle_name.ilike(like),
            )
        )

    items = (
        query
        .order_by(
            PreschoolChildMovement.movement_date.desc().nullslast(),
            PreschoolChildMovement.created_at.desc(),
        )
        .all()
    )

    active_items = [item for item in items if item.reversed_at is None]
    movement_counts = {
        "total": len(active_items),
        "admission": sum(1 for item in active_items if item.movement_type == "admission"),
        "transfer_group": sum(1 for item in active_items if item.movement_type == "transfer_group"),
        "leaving": sum(1 for item in active_items if item.movement_type == "leaving"),
        "transfer_school": sum(1 for item in active_items if item.movement_type == "transfer_school"),
        "year_transfer": sum(1 for item in active_items if item.movement_type == "year_transfer"),
    }

    return render_template(
        "preschool/movements.html",
        year=year,
        all_years=all_years,
        items=items,
        movement_type=movement_type,
        q=q,
        movement_counts=movement_counts,
    )


@bp.route("/movements/bulk", methods=["GET", "POST"])
def bulk_movements():
    year_id = request.args.get("academic_year_id", type=int) or request.form.get("academic_year_id", type=int)
    target_year_id = request.args.get("target_academic_year_id", type=int) or request.form.get("target_academic_year_id", type=int)
    source_group_id = request.args.get("source_group_id", type=int) or request.form.get("source_group_id", type=int)

    year = AcademicYear.query.get(year_id) if year_id else _get_current_year()
    target_year = AcademicYear.query.get(target_year_id) if target_year_id else None

    if not year:
        flash("Сначала создайте учебный год в служебном разделе.", "warning")
        return redirect(url_for("children.academic_years_registry"))

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )

    groups = (
        PreschoolGroup.query
        .filter(
            PreschoolGroup.academic_year_id == year.id,
            PreschoolGroup.is_archived.is_(False),
            PreschoolGroup.is_active.is_(True),
        )
        .order_by(PreschoolGroup.name.asc())
        .all()
    )

    target_groups = (
        PreschoolGroup.query
        .filter(
            PreschoolGroup.academic_year_id == target_year.id,
            PreschoolGroup.is_archived.is_(False),
            PreschoolGroup.is_active.is_(True),
        )
        .order_by(PreschoolGroup.name.asc())
        .all()
        if target_year else []
    )

    children = []
    if source_group_id:
        source_group = db.session.get(PreschoolGroup, source_group_id)
        if source_group is None or source_group.academic_year_id != year.id:
            abort(400)
        children = (
            PreschoolChild.query
            .filter(PreschoolChild.group_id == source_group_id)
            .order_by(PreschoolChild.last_name.asc(), PreschoolChild.first_name.asc())
            .all()
        )

    if request.method == "POST":
        movement_type = (request.form.get("movement_type") or "").strip()
        movement_date_raw = (request.form.get("movement_date") or "").strip()
        target_group_id = request.form.get("target_group_id", type=int)
        basis = (request.form.get("basis") or "").strip()
        comment = (request.form.get("comment") or "").strip()

        child_ids = request.form.getlist("child_ids")

        if movement_type not in ("transfer_group", "leaving", "year_transfer"):
            flash("Выберите тип массового движения.", "warning")
            return redirect(url_for(
                "preschool.bulk_movements",
                academic_year_id=year.id,
                target_academic_year_id=target_year.id if target_year else None,
                source_group_id=source_group_id,
            ))

        if not child_ids:
            flash("Выберите хотя бы одного воспитанника.", "warning")
            return redirect(url_for(
                "preschool.bulk_movements",
                academic_year_id=year.id,
                target_academic_year_id=target_year.id if target_year else None,
                source_group_id=source_group_id,
            ))

        if source_group_id is None:
            abort(400)

        if movement_type in ("transfer_group", "year_transfer") and not target_group_id:
            flash("Для перевода выберите группу назначения.", "warning")
            return redirect(url_for(
                "preschool.bulk_movements",
                academic_year_id=year.id,
                target_academic_year_id=target_year.id if target_year else None,
                source_group_id=source_group_id,
            ))

        target_group = PreschoolGroup.query.get(target_group_id) if target_group_id else None

        if movement_type == "year_transfer":
            if not target_year or target_year.id == year.id:
                flash("Для перевода в новый учебный год выберите учебный год назначения.", "warning")
                return redirect(url_for(
                    "preschool.bulk_movements",
                    academic_year_id=year.id,
                    source_group_id=source_group_id,
                ))

            if not target_group or target_group.academic_year_id != target_year.id or target_group.is_archived or not target_group.is_active:
                flash("Группа назначения должна относиться к выбранному новому учебному году.", "warning")
                return redirect(url_for(
                    "preschool.bulk_movements",
                    academic_year_id=year.id,
                    target_academic_year_id=target_year.id,
                    source_group_id=source_group_id,
                ))

        if movement_type == "transfer_group":
            if not target_group or target_group.academic_year_id != year.id or target_group.id == source_group_id or target_group.is_archived or not target_group.is_active:
                flash("Для перевода внутри года выберите группу текущего учебного года.", "warning")
                return redirect(url_for(
                    "preschool.bulk_movements",
                    academic_year_id=year.id,
                    source_group_id=source_group_id,
                ))

        movement_date = None
        if movement_date_raw:
            from datetime import datetime
            try:
                movement_date = datetime.strptime(movement_date_raw, "%Y-%m-%d").date()
            except ValueError:
                movement_date = None

        selected_children = PreschoolChild.query.filter(
            PreschoolChild.id.in_(child_ids),
            PreschoolChild.group_id == source_group_id,
        ).all()
        if len(selected_children) != len(set(child_ids)):
            abort(400)

        created = 0

        for child in selected_children:
            from_group = child.group
            from_group_id = child.group_id
            from_year_id = from_group.academic_year_id if from_group else year.id
            from_status = child.status

            if movement_type == "transfer_group":
                child.group_id = target_group_id
                child.status = "active"
                to_group_id = target_group_id
                to_year_id = year.id

            elif movement_type == "year_transfer":
                child.group_id = target_group_id
                child.status = "active"
                to_group_id = target_group_id
                to_year_id = target_year.id

            else:
                child.status = "left"
                to_group_id = None
                to_year_id = from_year_id

            movement = PreschoolChildMovement(
                child_id=child.id,
                movement_date=movement_date,
                movement_type=movement_type,
                from_academic_year_id=from_year_id,
                to_academic_year_id=to_year_id,
                from_group_id=from_group_id,
                to_group_id=to_group_id,
                from_status=from_status,
                to_status=child.status,
                created_by_user_id=current_user.id,
                basis=basis or None,
                comment=comment or None,
            )

            db.session.add(movement)
            created += 1

        db.session.commit()

        flash(f"Массовое движение сохранено. Обработано воспитанников: {created}.", "success")
        return redirect(url_for("preschool.movements", academic_year_id=to_year_id, movement_type=movement_type))

    return render_template(
        "preschool/bulk_movements.html",
        year=year,
        target_year=target_year,
        all_years=all_years,
        groups=groups,
        target_groups=target_groups,
        children=children,
        source_group_id=source_group_id,
        target_year_id=target_year_id,
    )


@bp.route("/children/<int:child_id>")
def child_card(child_id):
    child = PreschoolChild.query.get_or_404(child_id)
    group = child.group
    year = group.academic_year if group and group.academic_year else _get_current_year()

    representatives = (
        PreschoolRepresentative.query
        .filter(PreschoolRepresentative.child_id == child.id)
        .order_by(PreschoolRepresentative.relation.asc(), PreschoolRepresentative.full_name.asc())
        .all()
    )

    groups = (
        PreschoolGroup.query
        .filter(
            PreschoolGroup.academic_year_id == year.id,
            PreschoolGroup.is_archived.is_(False),
            PreschoolGroup.is_active.is_(True),
        )
        .order_by(PreschoolGroup.name.asc())
        .all()
        if year else []
    )

    movements = (
        PreschoolChildMovement.query
        .filter(PreschoolChildMovement.child_id == child.id)
        .order_by(PreschoolChildMovement.movement_date.desc().nullslast(), PreschoolChildMovement.created_at.desc())
        .all()
    )
    latest_active_movement = PreschoolChildMovement.query.filter_by(
        child_id=child.id,
        reversed_at=None,
    ).order_by(PreschoolChildMovement.created_at.desc(), PreschoolChildMovement.id.desc()).first()

    return render_template(
        "preschool/child_card.html",
        child=child,
        group=group,
        educators=_group_staff_names(group, "EDUCATOR") if group else "—",
        assistants=_group_staff_names(group, "ASSISTANT_EDUCATOR") if group else "—",
        year=year,
        representatives=representatives,
        groups=groups,
        movements=movements,
        latest_active_movement_id=latest_active_movement.id if latest_active_movement else None,
    )


@bp.route("/children/<int:child_id>/movement", methods=["POST"])
def add_child_movement(child_id):
    child = PreschoolChild.query.get_or_404(child_id)

    movement_type = (request.form.get("movement_type") or "").strip()
    movement_date_raw = (request.form.get("movement_date") or "").strip()
    to_group_id = request.form.get("to_group_id", type=int)
    basis = (request.form.get("basis") or "").strip()
    comment = (request.form.get("comment") or "").strip()

    if movement_type not in ("admission", "transfer_group", "leaving", "transfer_school"):
        flash("Выберите тип движения.", "warning")
        return redirect(url_for("preschool.child_card", child_id=child.id))

    movement_date = None
    if movement_date_raw:
        from datetime import datetime
        try:
            movement_date = datetime.strptime(movement_date_raw, "%Y-%m-%d").date()
        except ValueError:
            movement_date = None

    from_group_id = child.group_id
    from_academic_year_id = child.group.academic_year_id if child.group else None
    from_status = child.status
    target_group = db.session.get(PreschoolGroup, to_group_id) if to_group_id else None

    if movement_type in ("admission", "transfer_group") and to_group_id:
        if target_group is None or target_group.is_archived or not target_group.is_active:
            flash("Выберите действующую группу назначения.", "warning")
            return redirect(url_for("preschool.child_card", child_id=child.id))
        if from_academic_year_id and target_group.academic_year_id != from_academic_year_id:
            flash("Перевод в другой учебный год оформляется через массовое движение.", "warning")
            return redirect(url_for("preschool.child_card", child_id=child.id))

    if movement_type == "transfer_group":
        if not to_group_id:
            flash("Для перевода выберите новую группу.", "warning")
            return redirect(url_for("preschool.child_card", child_id=child.id))
        if to_group_id == from_group_id:
            flash("Выберите другую группу для перевода.", "warning")
            return redirect(url_for("preschool.child_card", child_id=child.id))
        child.group_id = to_group_id
        child.status = "active"

    elif movement_type == "leaving":
        child.status = "left"

    elif movement_type == "admission":
        child.status = "active"
        if to_group_id:
            child.group_id = to_group_id

    elif movement_type == "transfer_school":
        child.status = "transfer_school"

    movement = PreschoolChildMovement(
        child_id=child.id,
        movement_date=movement_date,
        movement_type=movement_type,
        from_academic_year_id=from_academic_year_id,
        to_academic_year_id=child.group.academic_year_id if child.group else from_academic_year_id,
        from_group_id=from_group_id,
        to_group_id=child.group_id if movement_type in ("admission", "transfer_group") else to_group_id,
        from_status=from_status,
        to_status=child.status,
        created_by_user_id=current_user.id,
        basis=basis or None,
        comment=comment or None,
    )

    db.session.add(movement)
    db.session.commit()

    flash("Движение воспитанника сохранено.", "success")
    return redirect(url_for("preschool.child_card", child_id=child.id))


@bp.route("/movements/<int:movement_id>/delete", methods=["POST"])
def delete_child_movement(movement_id):
    movement = PreschoolChildMovement.query.get_or_404(movement_id)
    latest = PreschoolChildMovement.query.filter_by(
        child_id=movement.child_id,
        reversed_at=None,
    ).order_by(PreschoolChildMovement.created_at.desc(), PreschoolChildMovement.id.desc()).first()
    if latest is None or latest.id != movement.id or movement.from_status is None:
        abort(409)
    child = movement.child
    if child.status != movement.to_status:
        abort(409)
    if movement.movement_type in {"admission", "transfer_group", "year_transfer"} and child.group_id != movement.to_group_id:
        abort(409)
    child.group_id = movement.from_group_id
    child.status = movement.from_status
    movement.reversed_at = datetime.utcnow()
    movement.reversed_by_user_id = current_user.id
    db.session.commit()
    flash("Движение отменено. Запись сохранена в истории.", "success")
    return redirect(url_for("preschool.child_card", child_id=child.id))


@bp.route("/children/<int:child_id>/edit", methods=["GET", "POST"])
def edit_child(child_id):
    child = PreschoolChild.query.get_or_404(child_id)

    current_group = child.group
    year = current_group.academic_year if current_group and current_group.academic_year else _get_current_year()

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )

    groups = (
        PreschoolGroup.query
        .filter(PreschoolGroup.academic_year_id == year.id)
        .order_by(PreschoolGroup.name.asc())
        .all()
        if year else []
    )

    if request.method == "POST":
        last_name = (request.form.get("last_name") or "").strip()
        first_name = (request.form.get("first_name") or "").strip()
        middle_name = (request.form.get("middle_name") or "").strip()
        birth_date_raw = (request.form.get("birth_date") or "").strip()
        personal_account = (request.form.get("personal_account") or "").strip()
        reg_address = (request.form.get("reg_address") or "").strip()
        living_address = (request.form.get("living_address") or "").strip()
        actual_address = (request.form.get("actual_address") or "").strip()
        note = (request.form.get("note") or "").strip()
        group_id_raw = (request.form.get("group_id") or "").strip()

        if not last_name or not first_name:
            flash("Укажите фамилию и имя воспитанника.", "warning")
            return redirect(url_for("preschool.edit_child", child_id=child.id))

        birth_date = None
        if birth_date_raw:
            from datetime import datetime
            try:
                birth_date = datetime.strptime(birth_date_raw, "%Y-%m-%d").date()
            except ValueError:
                birth_date = None

        if group_id_raw and (not group_id_raw.isdigit() or int(group_id_raw) != child.group_id):
            flash("Перевод между группами оформляется в разделе движения.", "warning")
            return redirect(url_for("preschool.edit_child", child_id=child.id))
        child.last_name = last_name
        child.first_name = first_name
        child.middle_name = middle_name or None
        child.birth_date = birth_date
        child.personal_account = personal_account or None
        child.reg_address = reg_address or None
        child.living_address = living_address or None
        child.actual_address = actual_address or None
        child.note = note or None

        db.session.commit()

        year_id = child.group.academic_year_id if child.group else None
        flash("Карточка воспитанника обновлена.", "success")
        return redirect(url_for("preschool.children_registry", academic_year_id=year_id))

    representatives = (
        PreschoolRepresentative.query
        .filter(PreschoolRepresentative.child_id == child.id)
        .order_by(PreschoolRepresentative.full_name.asc())
        .all()
    )

    return render_template(
        "preschool/child_form.html",
        child=child,
        groups=groups,
        all_years=all_years,
        year=year,
        representatives=representatives,
    )


@bp.route("/children/<int:child_id>/delete", methods=["POST"])
def delete_child(child_id):
    child = PreschoolChild.query.get_or_404(child_id)
    year_id = child.group.academic_year_id if child.group else None

    db.session.delete(child)
    db.session.commit()

    flash("Воспитанник удалён из тестового контингента ДОУ.", "success")
    return redirect(url_for("preschool.children_registry", academic_year_id=year_id))


from .professional import register_routes as register_preschool_professional_routes

register_preschool_professional_routes(bp)

from .dashboard import register_routes as register_preschool_dashboard_routes

register_preschool_dashboard_routes(bp)
