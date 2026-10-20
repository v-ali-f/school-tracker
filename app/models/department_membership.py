from datetime import datetime

from app.core.extensions import db


class DepartmentTeacherMembership(db.Model):
    """An explicit inclusion or exclusion from a workload-derived department."""

    __tablename__ = "department_teacher_membership"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    mode = db.Column(db.String(10), nullable=False)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    department = db.relationship("Department", foreign_keys=[department_id])
    teacher = db.relationship("User", foreign_keys=[teacher_id])

    __table_args__ = (
        db.UniqueConstraint("department_id", "teacher_id", name="uq_department_teacher_membership"),
        db.CheckConstraint("mode IN ('INCLUDE','EXCLUDE')", name="ck_department_teacher_membership_mode"),
    )
