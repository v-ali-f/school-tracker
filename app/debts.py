from datetime import datetime
from flask import Blueprint, redirect, url_for, request
from flask_login import login_required, current_user
from .models import Debt, Subject, Child
from app.core.extensions import db

debts_bp = Blueprint("debts", __name__)

def parse_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()

@debts_bp.route("/children/<int:child_id>/debt/new", methods=["POST"])
@login_required
def new_debt(child_id: int):
    Child.query.get_or_404(child_id)

    subject_name = (request.form.get("subject") or "").strip()
    detected_date = parse_date(request.form.get("detected_date"))
    due_date = parse_date(request.form.get("due_date"))
    comment = (request.form.get("comment") or "").strip() or None

    if not subject_name:
        return redirect(url_for("children.child_card", child_id=child_id))

    subject = Subject.query.filter_by(name=subject_name).first()
    if not subject:
        subject = Subject(name=subject_name)
        db.session.add(subject)
        db.session.flush()

    debt = Debt(
        child_id=child_id,
        subject_id=subject.id,
        detected_date=detected_date or datetime.today().date(),
        due_date=due_date,
        status="OPEN",
        comment=comment,
        responsible_user_id=current_user.id
    )
    db.session.add(debt)
    db.session.commit()
    return redirect(url_for("children.child_card", child_id=child_id))

@debts_bp.route("/debt/<int:debt_id>/close", methods=["POST"])
@login_required
def close_debt(debt_id: int):
    debt = Debt.query.get_or_404(debt_id)
    debt.status = "CLOSED"
    debt.closed_date = datetime.today().date()
    db.session.commit()
    return redirect(url_for("children.child_card", child_id=debt.child_id))
