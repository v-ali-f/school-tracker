from datetime import datetime

from app.core.extensions import db


school_classroom_teacher = db.Table(
    "school_classroom_teacher",
    db.Column(
        "classroom_id",
        db.Integer,
        db.ForeignKey("school_classroom.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "teacher_user_id",
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


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
    teachers = db.relationship(
        "User",
        secondary=school_classroom_teacher,
        backref=db.backref("shared_classrooms", lazy=True),
        lazy="selectin",
    )

    @property
    def assigned_teachers(self):
        """Return all linked teachers, including legacy single-room data."""
        result = list(self.teachers or ())
        if self.teacher is not None and all(
            item.id != self.teacher.id for item in result
        ):
            result.append(self.teacher)
        return sorted(
            result,
            key=lambda item: (item.fio or item.username).casefold(),
        )

    @property
    def assigned_teacher_ids(self):
        return [item.id for item in self.assigned_teachers]

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
    )


__all__ = ["SchoolClassroom", "school_classroom_teacher"]
