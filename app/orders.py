from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import bindparam, or_, text
from sqlalchemy.orm import selectinload, joinedload

from app.core.extensions import db
from .models import SchoolOrder, OrderResponsible, OrderResponsibleLink, User
from .permissions import has_any_role

orders_bp = Blueprint("orders", __name__)
# Принимаем и /orders, и /orders/ (закладки пользователей ходят по обоим).
orders_bp.url_map_strict_slashes = False

SECTIONS = [
    ("main_activity", "Основная деятельность"),
    ("procurement", "Закупки"),
    ("finance", "Финансы"),
    ("safety", "Безопасность"),
    ("building_access", "Допуск в здания и на территории"),
    ("excursions", "Экскурсионная деятельность"),
    ("students_movement", "Движение школьников"),
    ("preschool_movement", "Движение дошкольников"),
    ("olympiads_gia", "Олимпиады, конкурсы, соревнования, ГИА"),
    ("responsibles", "Назначение ответственных"),
    ("labor_protection", "Охрана труда"),
    ("iup", "ИУП"),
    ("ndo", "НДО"),
    ("family_education", "Семейная форма"),
    ("injuries", "Травмы"),
    ("az", "АЗ"),
    ("additional_education", "Дополнительное образование"),
]
SECTION_MAP = dict(SECTIONS)


def _is_orders_director():
    """Управление настройками реестра приказов: только директор/администратор портала."""
    return has_any_role("ADMIN", "DIRECTOR")


def _ensure_order_direction_access_table():
    """Создаёт таблицу доступа к направлениям приказов без миграций."""
    engine_name = db.engine.dialect.name
    if engine_name == "postgresql":
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS order_direction_access (
                id SERIAL PRIMARY KEY,
                section VARCHAR(80) NOT NULL,
                user_id INTEGER NOT NULL,
                access_type VARCHAR(20) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
    else:
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS order_direction_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section VARCHAR(80) NOT NULL,
                user_id INTEGER NOT NULL,
                access_type VARCHAR(20) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))

    db.session.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_order_direction_access_unique
        ON order_direction_access(section, user_id, access_type)
    """))
    db.session.commit()


def _order_access_rows():
    _ensure_order_direction_access_table()
    return db.session.execute(text("""
        SELECT section, user_id, access_type
        FROM order_direction_access
        ORDER BY section, access_type, user_id
    """)).mappings().all()


def _allowed_order_sections(mode="view"):
    """
    mode=view: пользователь видит направления, где он viewer или editor.
    mode=edit: пользователь редактирует направления, где он editor.
    директор видит и редактирует всё.
    """
    if _is_orders_director():
        return [code for code, _label in SECTIONS]

    _ensure_order_direction_access_table()
    if mode == "edit":
        access_types = ("editor",)
    else:
        access_types = ("editor", "viewer")

    rows = db.session.execute(
        text("""
            SELECT DISTINCT section
            FROM order_direction_access
            WHERE user_id = :user_id
              AND access_type IN :access_types
        """).bindparams(bindparam("access_types", expanding=True)),
        {
            "user_id": getattr(current_user, "id", None),
            "access_types": access_types,
        }
    ).scalars().all()

    valid = {code for code, _label in SECTIONS}
    return [section for section in rows if section in valid]


def _can_view_orders_section(section):
    return section in _allowed_order_sections("view")


def _can_edit_orders_section(section):
    return section in _allowed_order_sections("edit")


def _orders_access_required():
    if not _allowed_order_sections("view"):
        abort(403)


def _orders_settings_required():
    if not _is_orders_director():
        abort(403)


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _sorted_users():
    return User.query.order_by(User.last_name.asc(), User.first_name.asc(), User.middle_name.asc()).all()


def _responsible_ids_from_form():
    raw_ids = request.form.getlist("responsible_user_ids")
    result = []
    for raw in raw_ids:
        try:
            value = int(raw)
        except Exception:
            continue
        if value not in result:
            result.append(value)
    return result


def _sync_order_responsibles(item, user_ids):
    OrderResponsibleLink.query.filter_by(order_id=item.id).delete()
    for user_id in user_ids:
        db.session.add(OrderResponsibleLink(order_id=item.id, user_id=user_id))
    item.responsible_user_id = user_ids[0] if user_ids else None


def _attach_responsible_display(items):
    for item in items:
        links = sorted(
            [link for link in getattr(item, "responsible_links", []) if getattr(link, "user", None)],
            key=lambda x: ((x.user.last_name or ""), (x.user.first_name or ""), (x.user.middle_name or "")),
        )
        users = [link.user for link in links]
        item.responsible_users_display = users
        item.responsible_users_text = ", ".join([(u.fio or u.username or "") for u in users if (u.fio or u.username)]) or "—"
    return items


@orders_bp.route("/orders", strict_slashes=False)
@login_required
def registry():
    _orders_access_required()
    allowed_sections = _allowed_order_sections("view")
    visible_sections = [(code, label) for code, label in SECTIONS if code in allowed_sections]

    requested_section = (request.args.get("section") or "").strip()
    section = requested_section if requested_section in allowed_sections else (allowed_sections[0] if allowed_sections else "")

    query_text = (request.args.get("q") or "").strip()
    responsible_id = request.args.get("responsible_id", type=int)

    query = SchoolOrder.query
    if allowed_sections:
        query = query.filter(SchoolOrder.section.in_(allowed_sections))
    if section in SECTION_MAP:
        query = query.filter(SchoolOrder.section == section)
    if query_text:
        like = f"%{query_text}%"
        query = query.filter(or_(SchoolOrder.number.ilike(like), SchoolOrder.title.ilike(like)))
    if responsible_id:
        query = query.outerjoin(OrderResponsibleLink, OrderResponsibleLink.order_id == SchoolOrder.id).filter(
            or_(SchoolOrder.responsible_user_id == responsible_id, OrderResponsibleLink.user_id == responsible_id)
        )

    # s85: убираем N+1 на responsible_links[*].user
    query = query.options(
        selectinload(SchoolOrder.responsible_links).joinedload(OrderResponsibleLink.user)
    )
    items = query.distinct().order_by(SchoolOrder.order_date.desc(), SchoolOrder.number.desc()).all()
    _attach_responsible_display(items)
    responsibles = OrderResponsible.query.order_by(OrderResponsible.section.asc()).all()
    users = _sorted_users()
    return render_template(
        "orders_registry.html",
        items=items,
        sections=visible_sections,
        section=section,
        query_text=query_text,
        users=users,
        responsibles=responsibles,
        section_map=SECTION_MAP,
        responsible_id=responsible_id,
    )


@orders_bp.route("/orders/new", methods=["GET", "POST"])
@login_required
def create():
    _orders_access_required()
    users = _sorted_users()
    editable_codes = _allowed_order_sections("edit")
    editable_sections = [(code, label) for code, label in SECTIONS if code in editable_codes]
    if not editable_sections:
        abort(403)

    if request.method == "POST":
        number = (request.form.get("number") or "").strip()
        title = (request.form.get("title") or "").strip()
        section = (request.form.get("section") or "study").strip()
        order_date = _parse_date(request.form.get("order_date"))
        responsible_user_ids = _responsible_ids_from_form()
        if not number or not title or not order_date or section not in SECTION_MAP or section not in editable_codes:
            flash("Заполните номер, дату, название и доступное вам направление приказа.", "danger")
            return render_template("order_form.html", item=None, sections=editable_sections, users=users, selected_responsible_ids=responsible_user_ids)

        item = SchoolOrder(
            number=number,
            title=title,
            section=section,
            order_date=order_date,
            executor=(request.form.get("executor") or "").strip() or None,
            author=(request.form.get("author") or "").strip() or None,
            valid_until=_parse_date(request.form.get("valid_until")),
            original_submitted=bool(request.form.get("original_submitted")),
            approved_by_deputy=bool(request.form.get("approved_by_deputy")),
            notes=(request.form.get("notes") or "").strip() or None,
            created_by_id=getattr(current_user, "id", None),
        )
        db.session.add(item)
        db.session.flush()
        _sync_order_responsibles(item, responsible_user_ids)
        db.session.commit()
        flash("Приказ сохранён.", "success")
        return redirect(url_for("orders.registry", section=section))
    return render_template("order_form.html", item=None, sections=editable_sections, users=users, selected_responsible_ids=[])


@orders_bp.route("/orders/<int:order_id>/edit", methods=["GET", "POST"])
@login_required
def edit(order_id):
    _orders_access_required()
    item = SchoolOrder.query.get_or_404(order_id)
    if not _can_edit_orders_section(item.section):
        abort(403)

    users = _sorted_users()
    editable_codes = _allowed_order_sections("edit")
    editable_sections = [(code, label) for code, label in SECTIONS if code in editable_codes]
    if request.method == "POST":
        number = (request.form.get("number") or "").strip()
        title = (request.form.get("title") or "").strip()
        section = (request.form.get("section") or item.section).strip()
        order_date = _parse_date(request.form.get("order_date"))
        responsible_user_ids = _responsible_ids_from_form()
        if not number or not title or not order_date or section not in SECTION_MAP or section not in editable_codes:
            flash("Заполните номер, дату, название и доступное вам направление приказа.", "danger")
            return render_template(
                "order_form.html",
                item=item,
                sections=editable_sections,
                users=users,
                selected_responsible_ids=responsible_user_ids,
            )
        item.number = number
        item.title = title
        item.section = section
        item.order_date = order_date
        item.executor = (request.form.get("executor") or "").strip() or None
        item.author = (request.form.get("author") or "").strip() or None
        item.valid_until = _parse_date(request.form.get("valid_until"))
        item.original_submitted = bool(request.form.get("original_submitted"))
        item.approved_by_deputy = bool(request.form.get("approved_by_deputy"))
        item.notes = (request.form.get("notes") or "").strip() or None
        _sync_order_responsibles(item, responsible_user_ids)
        db.session.commit()
        flash("Изменения сохранены.", "success")
        return redirect(url_for("orders.registry", section=item.section))
    selected = [link.user_id for link in getattr(item, "responsible_links", [])]
    if not selected and item.responsible_user_id:
        selected = [item.responsible_user_id]
    return render_template("order_form.html", item=item, sections=editable_sections, users=users, selected_responsible_ids=selected)


@orders_bp.route("/orders/<int:order_id>/delete", methods=["POST"])
@login_required
def delete(order_id):
    _orders_access_required()
    item = SchoolOrder.query.get_or_404(order_id)
    if not _can_edit_orders_section(item.section):
        abort(403)
    section = item.section
    db.session.delete(item)
    db.session.commit()
    flash("Приказ удалён.", "success")
    return redirect(url_for("orders.registry", section=section))


@orders_bp.route("/orders/responsibles", methods=["GET", "POST"])
@login_required
def responsibles():
    _orders_settings_required()
    _ensure_order_direction_access_table()

    if request.method == "POST":
        section = (request.form.get("section_code") or "").strip()
        valid_sections = {code for code, _label in SECTIONS}

        if section not in valid_sections:
            flash("Не удалось определить направление для сохранения.", "danger")
            return redirect(url_for("orders.responsibles"))

        db.session.execute(
            text("DELETE FROM order_direction_access WHERE section = :section"),
            {"section": section},
        )

        editor_ids = request.form.getlist("editor_ids")
        viewer_ids = request.form.getlist("viewer_ids")

        for raw_user_id in editor_ids:
            if not raw_user_id:
                continue
            db.session.execute(
                text("""
                    INSERT INTO order_direction_access(section, user_id, access_type)
                    VALUES (:section, :user_id, 'editor')
                    ON CONFLICT DO NOTHING
                """),
                {"section": section, "user_id": int(raw_user_id)}
            )

        for raw_user_id in viewer_ids:
            if not raw_user_id:
                continue
            db.session.execute(
                text("""
                    INSERT INTO order_direction_access(section, user_id, access_type)
                    VALUES (:section, :user_id, 'viewer')
                    ON CONFLICT DO NOTHING
                """),
                {"section": section, "user_id": int(raw_user_id)}
            )

        db.session.commit()
        flash("Настройки доступа по направлению сохранены.", "success")
        return redirect(url_for("orders.responsibles") + f"#section-{section}")

    users = _sorted_users()
    rows = _order_access_rows()
    editor_mapping = {}
    viewer_mapping = {}

    for row in rows:
        if row["access_type"] == "editor":
            editor_mapping.setdefault(row["section"], []).append(row["user_id"])
        elif row["access_type"] == "viewer":
            viewer_mapping.setdefault(row["section"], []).append(row["user_id"])

    return render_template(
        "order_responsibles.html",
        sections=SECTIONS,
        users=users,
        editor_mapping=editor_mapping,
        viewer_mapping=viewer_mapping,
    )

