from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, inspect, or_, text

from app.core.extensions import db
from app.models_legacy import AcademicYear, Building, User
from .models import PreschoolChild, PreschoolGroup


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

    for model in (PreschoolGroup, PreschoolChild):
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

    _preschool_schema_checked = True


@bp.before_app_request
def before_request():
    ensure_preschool_tables()


@bp.route("/")
def index():
    groups_count = PreschoolGroup.query.count()
    children_count = PreschoolChild.query.count()

    return render_template(
        "preschool/index.html",
        groups_count=groups_count,
        children_count=children_count,
    )


@bp.route("/children", methods=["GET", "POST"])
def children():
    year_id = request.args.get("academic_year_id", type=int)
    building_id = request.args.get("building_id", type=int)
    group_id = request.args.get("group_id", type=int)
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

    buildings = Building.query.order_by(Building.name.asc()).all()

    groups_query = PreschoolGroup.query.filter(PreschoolGroup.academic_year_id == year.id)
    if building_id:
        groups_query = groups_query.filter(PreschoolGroup.building_id == building_id)

    groups = groups_query.order_by(PreschoolGroup.name.asc()).all()

    if request.method == "POST":
        last_name = (request.form.get("last_name") or "").strip()
        first_name = (request.form.get("first_name") or "").strip()
        middle_name = (request.form.get("middle_name") or "").strip()
        birth_date_raw = (request.form.get("birth_date") or "").strip()
        note = (request.form.get("note") or "").strip()
        group_id_raw = (request.form.get("group_id") or "").strip()

        if not last_name or not first_name:
            flash("Укажите фамилию и имя воспитанника.", "warning")
            return redirect(url_for("preschool.children", academic_year_id=year.id, building_id=building_id, group_id=group_id))

        birth_date = None
        if birth_date_raw:
            from datetime import datetime
            try:
                birth_date = datetime.strptime(birth_date_raw, "%Y-%m-%d").date()
            except ValueError:
                birth_date = None

        child = PreschoolChild(
            group_id=int(group_id_raw) if group_id_raw.isdigit() else None,
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name or None,
            birth_date=birth_date,
            status="active",
            note=note or None,
        )

        db.session.add(child)
        db.session.commit()

        flash("Воспитанник добавлен в контингент ДОУ.", "success")
        return redirect(url_for("preschool.children", academic_year_id=year.id, building_id=building_id, group_id=group_id))

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

    items = (
        base_query
        .order_by(PreschoolGroup.name.asc(), PreschoolChild.last_name.asc(), PreschoolChild.first_name.asc())
        .all()
    )

    stats_query = (
        db.session.query(PreschoolGroup.age_level, func.count(PreschoolChild.id))
        .join(PreschoolChild, PreschoolChild.group_id == PreschoolGroup.id)
        .filter(PreschoolGroup.academic_year_id == year.id)
    )

    if building_id:
        stats_query = stats_query.filter(PreschoolGroup.building_id == building_id)

    if group_id:
        stats_query = stats_query.filter(PreschoolGroup.id == group_id)

    age_counts = {name or "Не указано": count for name, count in stats_query.group_by(PreschoolGroup.age_level).all()}

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
        "total": len(items),
        "groups": groups_total_query.count(),
        "buildings": buildings_used_query.scalar() or 0,
        "early": age_counts.get("ранний возраст", 0),
        "junior": age_counts.get("младшая группа", 0),
        "middle": age_counts.get("средняя группа", 0),
        "senior": age_counts.get("старшая группа", 0),
        "prep": age_counts.get("подготовительная группа", 0),
    }

    return render_template(
        "preschool/children.html",
        items=items,
        groups=groups,
        buildings=buildings,
        all_years=all_years,
        year=year,
        selected_building_id=building_id,
        selected_group_id=group_id,
        q=q,
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
    buildings = Building.query.order_by(Building.name.asc()).all()
    teachers = (
        User.query
        .order_by(User.last_name.asc(), User.first_name.asc(), User.username.asc())
        .all()
    )

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        age_level = (request.form.get("age_level") or "").strip()
        teacher_user_id_raw = (request.form.get("teacher_user_id") or "").strip()
        teacher_name = (request.form.get("teacher_name") or "").strip()
        building_id_raw = (request.form.get("building_id") or "").strip()
        academic_year_id_raw = (request.form.get("academic_year_id") or "").strip()

        if not name:
            flash("Укажите название группы.", "warning")
            return redirect(url_for("preschool.groups", academic_year_id=year.id))

        academic_year_id = int(academic_year_id_raw) if academic_year_id_raw.isdigit() else year.id
        building_id = int(building_id_raw) if building_id_raw.isdigit() else None
        teacher_user_id = int(teacher_user_id_raw) if teacher_user_id_raw.isdigit() else None

        group = PreschoolGroup(
            academic_year_id=academic_year_id,
            building_id=building_id,
            name=name,
            age_level=age_level or None,
            teacher_user_id=teacher_user_id,
            teacher_name=teacher_name or None,
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
        buildings=buildings,
        teachers=teachers,
        age_levels=PRESCHOOL_AGE_LEVELS,
        all_years=all_years,
        year=year,
    )

@bp.route("/groups/<int:group_id>/edit", methods=["GET", "POST"])
def edit_group(group_id):
    group = PreschoolGroup.query.get_or_404(group_id)

    all_years = (
        AcademicYear.query
        .order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc())
        .all()
    )
    buildings = Building.query.order_by(Building.name.asc()).all()
    teachers = (
        User.query
        .order_by(User.last_name.asc(), User.first_name.asc(), User.username.asc())
        .all()
    )

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        age_level = (request.form.get("age_level") or "").strip()
        teacher_user_id_raw = (request.form.get("teacher_user_id") or "").strip()
        teacher_name = (request.form.get("teacher_name") or "").strip()
        building_id_raw = (request.form.get("building_id") or "").strip()
        academic_year_id_raw = (request.form.get("academic_year_id") or "").strip()

        if not name:
            flash("Укажите название группы.", "warning")
            return redirect(url_for("preschool.edit_group", group_id=group.id))

        group.name = name
        group.age_level = age_level or None
        group.teacher_user_id = int(teacher_user_id_raw) if teacher_user_id_raw.isdigit() else None
        group.teacher_name = teacher_name or None
        group.building_id = int(building_id_raw) if building_id_raw.isdigit() else None
        group.academic_year_id = int(academic_year_id_raw) if academic_year_id_raw.isdigit() else group.academic_year_id

        db.session.commit()

        flash("Группа ДОУ обновлена.", "success")
        return redirect(url_for("preschool.groups", academic_year_id=group.academic_year_id))

    return render_template(
        "preschool/group_form.html",
        group=group,
        buildings=buildings,
        teachers=teachers,
        age_levels=PRESCHOOL_AGE_LEVELS,
        all_years=all_years,
    )


@bp.route("/groups/<int:group_id>/delete", methods=["POST"])
def delete_group(group_id):
    group = PreschoolGroup.query.get_or_404(group_id)
    academic_year_id = group.academic_year_id

    if group.children:
        flash("Нельзя удалить группу, если к ней уже прикреплены воспитанники. Позже добавим архивирование.", "warning")
        return redirect(url_for("preschool.groups", academic_year_id=academic_year_id))

    db.session.delete(group)
    db.session.commit()

    flash("Группа ДОУ удалена.", "success")
    return redirect(url_for("preschool.groups", academic_year_id=academic_year_id))

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

        child.group_id = int(group_id_raw) if group_id_raw.isdigit() else None
        child.last_name = last_name
        child.first_name = first_name
        child.middle_name = middle_name or None
        child.birth_date = birth_date
        child.note = note or None

        db.session.commit()

        year_id = child.group.academic_year_id if child.group else None
        flash("Карточка воспитанника обновлена.", "success")
        return redirect(url_for("preschool.children", academic_year_id=year_id))

    return render_template(
        "preschool/child_form.html",
        child=child,
        groups=groups,
        all_years=all_years,
        year=year,
    )


@bp.route("/children/<int:child_id>/delete", methods=["POST"])
def delete_child(child_id):
    child = PreschoolChild.query.get_or_404(child_id)
    year_id = child.group.academic_year_id if child.group else None

    db.session.delete(child)
    db.session.commit()

    flash("Воспитанник удалён из тестового контингента ДОУ.", "success")
    return redirect(url_for("preschool.children", academic_year_id=year_id))

