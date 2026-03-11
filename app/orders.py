from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from . import db
from .models import SchoolOrder, OrderResponsible, OrderResponsibleLink, User
from .permissions import has_any_role

orders_bp = Blueprint("orders", __name__)

SECTIONS = [
    ("study", "Учебная часть"),
    ("upbringing", "Воспитательная часть"),
    ("extra", "Допобразование"),
    ("contingent", "Контингент"),
]
SECTION_MAP = dict(SECTIONS)


def _orders_access_required():
    if not has_any_role("ADMIN", "METHODIST"):
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


@orders_bp.route("/orders")
@login_required
def registry():
    _orders_access_required()
    section = (request.args.get("section") or "study").strip()
    query_text = (request.args.get("q") or "").strip()
    responsible_id = request.args.get("responsible_id", type=int)

    query = SchoolOrder.query
    if section in SECTION_MAP:
        query = query.filter(SchoolOrder.section == section)
    if query_text:
        like = f"%{query_text}%"
        query = query.filter(or_(SchoolOrder.number.ilike(like), SchoolOrder.title.ilike(like)))
    if responsible_id:
        query = query.outerjoin(OrderResponsibleLink, OrderResponsibleLink.order_id == SchoolOrder.id).filter(
            or_(SchoolOrder.responsible_user_id == responsible_id, OrderResponsibleLink.user_id == responsible_id)
        )

    items = query.distinct().order_by(SchoolOrder.order_date.desc(), SchoolOrder.number.desc()).all()
    _attach_responsible_display(items)
    responsibles = OrderResponsible.query.order_by(OrderResponsible.section.asc()).all()
    users = _sorted_users()
    return render_template(
        "orders_registry.html",
        items=items,
        sections=SECTIONS,
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
    if request.method == "POST":
        number = (request.form.get("number") or "").strip()
        title = (request.form.get("title") or "").strip()
        section = (request.form.get("section") or "study").strip()
        order_date = _parse_date(request.form.get("order_date"))
        responsible_user_ids = _responsible_ids_from_form()
        if not number or not title or not order_date or section not in SECTION_MAP:
            flash("Заполните номер, дату, название и раздел приказа.", "danger")
            return render_template("order_form.html", item=None, sections=SECTIONS, users=users, selected_responsible_ids=responsible_user_ids)

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
    return render_template("order_form.html", item=None, sections=SECTIONS, users=users, selected_responsible_ids=[])


@orders_bp.route("/orders/<int:order_id>/edit", methods=["GET", "POST"])
@login_required
def edit(order_id):
    _orders_access_required()
    item = SchoolOrder.query.get_or_404(order_id)
    users = _sorted_users()
    if request.method == "POST":
        number = (request.form.get("number") or "").strip()
        title = (request.form.get("title") or "").strip()
        section = (request.form.get("section") or item.section).strip()
        order_date = _parse_date(request.form.get("order_date"))
        responsible_user_ids = _responsible_ids_from_form()
        if not number or not title or not order_date or section not in SECTION_MAP:
            flash("Заполните номер, дату, название и раздел приказа.", "danger")
            return render_template(
                "order_form.html",
                item=item,
                sections=SECTIONS,
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
    return render_template("order_form.html", item=item, sections=SECTIONS, users=users, selected_responsible_ids=selected)


@orders_bp.route("/orders/<int:order_id>/delete", methods=["POST"])
@login_required
def delete(order_id):
    _orders_access_required()
    item = SchoolOrder.query.get_or_404(order_id)
    section = item.section
    db.session.delete(item)
    db.session.commit()
    flash("Приказ удалён.", "success")
    return redirect(url_for("orders.registry", section=section))


@orders_bp.route("/orders/responsibles", methods=["GET", "POST"])
@login_required
def responsibles():
    _orders_access_required()
    if request.method == "POST":
        for section, _label in SECTIONS:
            user_id = request.form.get(f"user_id_{section}", type=int)
            row = OrderResponsible.query.filter_by(section=section).first()
            if user_id:
                if row is None:
                    row = OrderResponsible(section=section, user_id=user_id)
                    db.session.add(row)
                else:
                    row.user_id = user_id
            elif row is not None:
                db.session.delete(row)
        db.session.commit()
        flash("Ответственные по разделам сохранены.", "success")
        return redirect(url_for("orders.responsibles"))
    users = _sorted_users()
    mapping = {r.section: r.user_id for r in OrderResponsible.query.all()}
    return render_template("order_responsibles.html", sections=SECTIONS, users=users, mapping=mapping)
