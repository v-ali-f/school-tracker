from datetime import datetime
from flask import Blueprint, flash, redirect, url_for, request
from flask_login import login_required, current_user
from .models import Debt, Child
from app.core.extensions import db
from app.services.education_activity_service import (
    MATCHED,
    assign_subject_activity,
    get_subject_activity,
    resolve_education_activity,
)

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

    activity = get_subject_activity(
        request.form.get("education_activity_id", type=int)
    )
    subject_name = (request.form.get("subject") or "").strip()
    if activity is None and subject_name:
        match = resolve_education_activity(
            subject_name,
            source_module="DEBT",
        )
        if match.status == MATCHED:
            activity = match.activity
    detected_date = parse_date(request.form.get("detected_date"))
    due_date = parse_date(request.form.get("due_date"))

    if activity is None:
        flash("Выберите предмет из единого реестра.", "warning")
        return redirect(url_for("children.child_card", child_id=child_id))

    debt = Debt(
        child_id=child_id,
        detected_date=detected_date or datetime.today().date(),
        due_date=due_date,
        status="OPEN",
    )
    assign_subject_activity(debt, activity)
    db.session.add(debt)
    db.session.commit()
    return redirect(url_for("children.child_card", child_id=child_id))

@debts_bp.route("/debt/<int:debt_id>/close", methods=["POST"])
@login_required
def close_debt(debt_id: int):
    debt = Debt.query.get_or_404(debt_id)
    debt.status = "CLOSED"
    debt.closed_at = datetime.utcnow()
    debt.closed_by_user_id = current_user.id
    db.session.commit()
    return redirect(url_for("children.child_card", child_id=debt.child_id))
