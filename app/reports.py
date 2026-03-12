from datetime import date
from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func
from .models import Child, Debt, Subject
from app.core.extensions import db

reports_bp = Blueprint("reports", __name__)

@reports_bp.route("/reports/az")
@login_required
def report_az():
    cls = (request.args.get("class") or "").strip()
    status = (request.args.get("status") or "OPEN").strip().upper()
    qtext = (request.args.get("q") or "").strip()
    overdue_only = (request.args.get("overdue_only") or "") == "1"

    today = date.today()

    base = (
        db.session.query(
            Child.id.label("child_id"),
            Child.class_name.label("class_name"),
            Child.last_name.label("last_name"),
            Child.first_name.label("first_name"),
            Child.middle_name.label("middle_name"),
            func.count(Debt.id).label("debt_count"),
            func.min(Debt.due_date).label("nearest_due"),
            func.group_concat(Subject.name, ", ").label("subjects")
        )
        .join(Debt, Debt.child_id == Child.id)
        .join(Subject, Subject.id == Debt.subject_id)
    )

    if cls:
        base = base.filter(Child.class_name == cls)

    if qtext:
        ql = qtext.lower()
        base = base.filter(
            func.lower(Child.last_name).contains(ql) |
            func.lower(Child.first_name).contains(ql) |
            func.lower(Child.middle_name).contains(ql)
        )

    if status != "ALL":
        base = base.filter(Debt.status == status)

    if overdue_only:
        base = (
            base.filter(Debt.due_date.isnot(None))
                .filter(Debt.due_date < today)
                .filter(Debt.status != "CLOSED")
        )

    rows = (
        base.group_by(Child.id)
            .order_by(
                Child.class_name.asc(),
                Child.last_name.asc(),
                Child.first_name.asc()
            )
            .all()
    )

    return render_template(
        "report_az.html",
        rows=rows,
        cls=cls,
        status=status,
        q=qtext,
        overdue_only=overdue_only
    )
