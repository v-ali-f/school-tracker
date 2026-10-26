"""Versioned safety passports for physical classrooms."""

from datetime import datetime, timezone

from app.core.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class SafetyOfficerAssignment(db.Model):
    __tablename__ = "safety_officer_assignment"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=True)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoked_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True)
    can_manage_instructions = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())

    user = db.relationship("User", foreign_keys=[user_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])
    revoked_by = db.relationship("User", foreign_keys=[revoked_by_id])

    __table_args__ = (
        db.CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_safety_officer_period"),
    )


class SafetyPassport(db.Model):
    __tablename__ = "safety_passport"

    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("school_classroom.id", ondelete="RESTRICT"), nullable=False, unique=True)
    template_code = db.Column(db.String(50), nullable=False, default="general")
    template_version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(32), nullable=False, default="not_started")
    current_revision_number = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    classroom = db.relationship("SchoolClassroom", backref=db.backref("safety_passport", uselist=False))
    revisions = db.relationship("SafetyPassportRevision", back_populates="passport", order_by="SafetyPassportRevision.number", cascade="all, delete-orphan")


class SafetyPassportRevision(db.Model):
    __tablename__ = "safety_passport_revision"

    id = db.Column(db.Integer, primary_key=True)
    passport_id = db.Column(db.Integer, db.ForeignKey("safety_passport.id", ondelete="CASCADE"), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    data = db.Column(db.JSON, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    passport = db.relationship("SafetyPassport", back_populates="revisions")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    reviews = db.relationship("SafetyPassportReview", back_populates="revision", order_by="SafetyPassportReview.reviewed_at")

    __table_args__ = (
        db.UniqueConstraint("passport_id", "number", name="uq_safety_passport_revision_number"),
    )


class SafetyPassportReview(db.Model):
    __tablename__ = "safety_passport_review"

    id = db.Column(db.Integer, primary_key=True)
    revision_id = db.Column(db.Integer, db.ForeignKey("safety_passport_revision.id", ondelete="RESTRICT"), nullable=False, index=True)
    result = db.Column(db.String(32), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    revision = db.relationship("SafetyPassportRevision", back_populates="reviews")
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])


class SafetyPassportDocument(db.Model):
    __tablename__ = "safety_passport_document"

    id = db.Column(db.Integer, primary_key=True)
    passport_id = db.Column(db.Integer, db.ForeignKey("safety_passport.id", ondelete="RESTRICT"), nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(80), nullable=False, unique=True)
    mime_type = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    passport = db.relationship("SafetyPassport", backref=db.backref("documents", order_by="SafetyPassportDocument.uploaded_at"))
    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])


__all__ = [
    "SafetyOfficerAssignment", "SafetyPassport", "SafetyPassportRevision",
    "SafetyPassportReview", "SafetyPassportDocument",
]
