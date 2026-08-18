from datetime import datetime

from app.core.extensions import db


class SchoolClassroom(db.Model):
    """A physical classroom and its optional teacher assignment."""

    __tablename__ = "school_classroom"

    id = db.Column(db.Integer, primary_key=True)
    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    short_name = db.Column(db.String(50), nullable=True)
    capacity = db.Column(db.Integer, nullable=True)
    teacher_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
        index=True,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    building = db.relationship(
        "Building",
        backref=db.backref(
            "classrooms",
            lazy=True,
            order_by="SchoolClassroom.name",
        ),
    )
    teacher = db.relationship(
        "User",
        foreign_keys=[teacher_user_id],
        backref=db.backref("assigned_classrooms", lazy=True),
    )

    __table_args__ = (
        db.CheckConstraint(
            "capacity IS NULL OR capacity > 0",
            name="ck_school_classroom_capacity_positive",
        ),
        db.UniqueConstraint(
            "building_id",
            "name",
            name="uq_school_classroom_building_name",
        ),
        db.UniqueConstraint(
            "building_id",
            "teacher_user_id",
            name="uq_school_classroom_teacher_building",
        ),
    )


__all__ = ["SchoolClassroom"]
