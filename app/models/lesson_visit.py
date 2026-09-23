from datetime import datetime

from app.core.extensions import db


class LessonVisit(db.Model):
    """A completed lesson observation with a stable snapshot of lesson data."""

    __tablename__ = "lesson_visit"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )
    observer_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )
    academic_year_id = db.Column(
        db.Integer,
        db.ForeignKey("academic_year.id"),
        nullable=True,
        index=True,
    )
    workload_assignment_id = db.Column(
        db.Integer,
        db.ForeignKey("workload_assignment.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    visit_date = db.Column(db.Date, nullable=False, index=True)
    parallel = db.Column(db.SmallInteger, nullable=True, index=True)
    class_name = db.Column(db.String(120), nullable=False)
    subject_name = db.Column(db.String(255), nullable=False)
    topic = db.Column(db.String(500), nullable=False)
    checklist = db.Column(db.JSON, nullable=False, default=dict)
    strengths = db.Column(db.Text, nullable=False)
    growth_areas = db.Column(db.Text, nullable=False)
    repeat_required = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.false(),
        index=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    teacher = db.relationship("User", foreign_keys=[teacher_id])
    observer = db.relationship("User", foreign_keys=[observer_id])
    academic_year = db.relationship("AcademicYear")
    workload_assignment = db.relationship("WorkloadAssignment")

    __table_args__ = (
        db.CheckConstraint(
            "parallel IS NULL OR (parallel >= 1 AND parallel <= 11)",
            name="ck_lesson_visit_parallel",
        ),
        db.Index(
            "ix_lesson_visit_teacher_date",
            "teacher_id",
            "visit_date",
        ),
    )


__all__ = ["LessonVisit"]
