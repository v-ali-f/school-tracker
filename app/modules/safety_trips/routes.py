"""Excursion journals for employees named in school orders."""

from uuid import uuid4

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload

from app.core.extensions import db
from app.models import SafetyJournalDraft, SafetyJournalDraftEvent, SafetyTripAssignment, SafetyTripOrder
from app.services.safety_passport_service import is_admin, is_director, is_officer, school_today
from app.services.safety_trip_service import STATUS_LABELS, active_assignment, can_view_trip, trip_status


safety_trips_bp = Blueprint("safety_trips", __name__, url_prefix="/safety/trips")


def _context():
    from app.modules.hub.routes import build_home_context
    return {
        "workspace_nav": build_home_context(),
        "workspace_context_title": "Техника безопасности",
        "workspace_context_subtitle": "Выезды и экскурсии",
    }


@safety_trips_bp.route("/")
@login_required
def index():
    manager = is_officer(current_user) or is_director(current_user) or is_admin(current_user)
    query = SafetyTripOrder.query.options(selectinload(SafetyTripOrder.assignments))
    if not manager:
        query = query.join(SafetyTripAssignment).filter(
            SafetyTripAssignment.user_id == current_user.id,
            SafetyTripAssignment.is_active.is_(True),
        )
    trips = query.order_by(SafetyTripOrder.trip_date.desc(), SafetyTripOrder.order_id.desc()).limit(300).all()
    if not manager and not trips:
        abort(403)
    return render_template("safety_trips/index.html", **_context(), trips=trips, status_labels=STATUS_LABELS, trip_status=trip_status)


@safety_trips_bp.route("/orders/<int:order_id>")
@login_required
def detail(order_id):
    trip = db.session.get(SafetyTripOrder, order_id) or abort(404)
    if not can_view_trip(current_user, trip):
        abort(403)
    assignment = active_assignment(trip, current_user)
    return render_template(
        "safety_trips/detail.html", **_context(), trip=trip, assignment=assignment,
        status=trip_status(trip), status_labels=STATUS_LABELS,
    )


@safety_trips_bp.route("/orders/<int:order_id>/drafts", methods=["POST"])
@login_required
def create_draft(order_id):
    trip = db.session.get(SafetyTripOrder, order_id) or abort(404)
    assignment = active_assignment(trip, current_user)
    if assignment is None:
        abort(403)
    page = assignment.current_page
    if page is not None and page.trip_order_revision == trip.revision_number and page.status != "annulled":
        flash("Страница по текущей редакции приказа уже сформирована.", "warning")
        return redirect(url_for("safety_journals.detail", page_id=page.id))
    prior = SafetyJournalDraft.query.filter_by(
        trip_assignment_id=assignment.id, trip_order_revision=trip.revision_number,
        author_id=current_user.id, status="draft",
    ).order_by(SafetyJournalDraft.created_at.desc()).first()
    if prior is not None:
        return redirect(url_for("safety_journals.edit", draft_id=prior.id))
    draft = SafetyJournalDraft(
        id=str(uuid4()), author_id=current_user.id,
        trip_order_id=trip.order_id, trip_assignment_id=assignment.id,
        trip_order_revision=trip.revision_number,
        instructed_on=min(school_today(), trip.trip_date),
        class_ids=[], selected_child_ids=[], removed_child_ids=[],
    )
    db.session.add(draft)
    db.session.flush()
    db.session.add(SafetyJournalDraftEvent(
        draft_id=draft.id, actor_id=current_user.id, action="created_from_trip",
        details={"order_id": trip.order_id, "revision": trip.revision_number},
    ))
    db.session.commit()
    return redirect(url_for("safety_journals.edit", draft_id=draft.id))
