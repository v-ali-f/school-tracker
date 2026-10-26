"""Excursion order details, responsible assignments and their audit trail."""

from app.core.extensions import db
from app.models.safety_passport import utc_now


class SafetyTripOrder(db.Model):
    __tablename__ = "safety_trip_order"

    order_id = db.Column(db.Integer, db.ForeignKey("school_order.id", ondelete="RESTRICT"), primary_key=True)
    trip_date = db.Column(db.Date, nullable=False)
    destination = db.Column(db.String(500), nullable=False)
    trip_kind = db.Column(db.String(120), nullable=False)
    revision_number = db.Column(db.Integer, nullable=False, default=1)
    cancelled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    order = db.relationship("SchoolOrder", foreign_keys=[order_id])
    assignments = db.relationship("SafetyTripAssignment", back_populates="trip", order_by="SafetyTripAssignment.id")
    events = db.relationship("SafetyTripEvent", back_populates="trip", order_by="SafetyTripEvent.created_at")


class SafetyTripAssignment(db.Model):
    __tablename__ = "safety_trip_assignment"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("safety_trip_order.order_id", ondelete="RESTRICT"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id", ondelete="SET NULL"), nullable=True, unique=True)
    current_page_id = db.Column(db.Integer, db.ForeignKey("safety_journal_page.id", ondelete="SET NULL"), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    retired_at = db.Column(db.DateTime(timezone=True), nullable=True)

    trip = db.relationship("SafetyTripOrder", back_populates="assignments")
    user = db.relationship("User", foreign_keys=[user_id])
    task = db.relationship("Task", foreign_keys=[task_id])
    current_page = db.relationship("SafetyJournalPage", foreign_keys=[current_page_id])

    __table_args__ = (db.UniqueConstraint("order_id", "user_id", name="uq_safety_trip_assignment_user"),)


class SafetyTripEvent(db.Model):
    __tablename__ = "safety_trip_event"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("safety_trip_order.order_id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    action = db.Column(db.String(40), nullable=False)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    trip = db.relationship("SafetyTripOrder", back_populates="events")
    actor = db.relationship("User", foreign_keys=[actor_id])


__all__ = ["SafetyTripOrder", "SafetyTripAssignment", "SafetyTripEvent"]
