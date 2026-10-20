"""Courses imported from staff professional development workbooks."""

from datetime import datetime

from app.core.extensions import db


class StaffCourseImport(db.Model):
    __tablename__ = "staff_course_import"

    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(64), nullable=False, unique=True)
    source_name = db.Column(db.String(255), nullable=False)
    source_year = db.Column(db.Integer, nullable=False, index=True)
    source_row = db.Column(db.Integer, nullable=False)
    employee_name = db.Column(db.String(255), nullable=False)
    position = db.Column(db.String(255), nullable=True)
    title = db.Column(db.String(512), nullable=False)
    provider = db.Column(db.String(512), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    completed_at = db.Column(db.Date, nullable=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    imported_at = db.Column(db.DateTime(), nullable=False, default=datetime.utcnow)

    teacher = db.relationship("User", foreign_keys=[teacher_id])

    @property
    def hours(self):
        return None

    @property
    def start_date(self):
        return None

    @property
    def end_date(self):
        return self.completed_at

    @property
    def notes(self):
        return f"Из таблицы за {self.source_year}/{self.source_year + 1} учебный год"
