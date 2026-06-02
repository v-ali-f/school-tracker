from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, inspect, or_, text

from app.core.extensions import db
from app.models_legacy import AcademicYear, Building, User
from .models import PreschoolChild, PreschoolChildrenImport, PreschoolGroup, PreschoolRepresentative


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

    for model in (PreschoolGroup, PreschoolChildrenImport, PreschoolChild, PreschoolRepresentative):
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

    buildings = Building.query.order_by(Building.name.asc()).all()

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
        children_count = PreschoolChild.query.filter(PreschoolChild.group_id == group.id).count()
        total_children += children_count

        if group.building_id:
            building_ids.add(group.building_id)

        age_name = group.age_level or "Не указано"
        age_counts[age_name] = age_counts.get(age_name, 0) + children_count

        group_rows.append({
            "id": group.id,
            "name": group.name,
            "building": group.building.name if group.building else "—",
            "age_level": group.age_level or "—",
            "teacher": (
                f"{group.teacher.last_name or ''} {group.teacher.first_name or ''} {group.teacher.middle_name or ''}".strip()
                if group.teacher else (group.teacher_name or "—")
            ),
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
            return redirect(url_for("preschool.children_registry", academic_year_id=year.id, building_id=building_id, group_id=group_id))

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
        return redirect(url_for("preschool.children_registry", academic_year_id=year.id, building_id=building_id, group_id=group_id))

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
        "preschool/children_registry.html",
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
    buildings = Building.query.order_by(Building.name.asc()).all()
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

        if not uploaded.filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
            flash("Поддерживаются файлы .xlsx, .xlsm или выгрузки Excel с расширением .xls.", "warning")
            return redirect(url_for("preschool.import_children", academic_year_id=year.id))

        try:
            from openpyxl import load_workbook
        except Exception:
            flash("Не установлен openpyxl. Установите зависимости из requirements.txt.", "danger")
            return redirect(url_for("preschool.import_children", academic_year_id=year.id))

        workbook = load_workbook(uploaded, data_only=True)
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
                .filter(func.lower(PreschoolChild.middle_name) == (middle_name or "").lower())
            )

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

        if not uploaded.filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
            flash("Поддерживаются файлы .xlsx, .xlsm или выгрузки Excel с расширением .xls.", "warning")
            return redirect(url_for("preschool.import_representatives", academic_year_id=year.id))

        try:
            from openpyxl import load_workbook
        except Exception:
            flash("Не установлен openpyxl. Установите зависимости из requirements.txt.", "danger")
            return redirect(url_for("preschool.import_representatives", academic_year_id=year.id))

        workbook = load_workbook(uploaded, data_only=True)
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

    return render_template(
        "preschool/child_card.html",
        child=child,
        group=group,
        year=year,
        representatives=representatives,
    )


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
        return redirect(url_for("preschool.children_registry", academic_year_id=year_id))

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
    return redirect(url_for("preschool.children_registry", academic_year_id=year_id))

