from datetime import datetime

from app.core.extensions import db


class PreschoolGroup(db.Model):
    __tablename__ = "preschool_group"

    id = db.Column(db.Integer, primary_key=True)

    academic_year_id = db.Column(
        db.Integer,
        db.ForeignKey("academic_year.id"),
        nullable=True,
        index=True,
    )

    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id"),
        nullable=True,
        index=True,
    )

    name = db.Column(db.String(255), nullable=False)
    age_level = db.Column(db.String(100), nullable=True)
    teacher_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True,
    )
    teacher_name = db.Column(db.String(255), nullable=True)

    teacher = db.relationship("User", foreign_keys=[teacher_user_id])

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    academic_year = db.relationship("AcademicYear", backref=db.backref("preschool_groups", lazy=True))
    building = db.relationship("Building", backref=db.backref("preschool_groups", lazy=True))

    __table_args__ = (
        db.UniqueConstraint(
            "academic_year_id",
            "building_id",
            "name",
            name="uq_preschool_group_year_building_name",
        ),
    )


class PreschoolChildrenImport(db.Model):
    __tablename__ = "preschool_children_import"

    id = db.Column(db.Integer, primary_key=True)

    academic_year_id = db.Column(
        db.Integer,
        db.ForeignKey("academic_year.id"),
        nullable=True,
        index=True,
    )

    filename = db.Column(db.String(500), nullable=True)
    added_count = db.Column(db.Integer, nullable=False, default=0)
    skipped_count = db.Column(db.Integer, nullable=False, default=0)
    created_groups_count = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    academic_year = db.relationship("AcademicYear")


class PreschoolChild(db.Model):
    __tablename__ = "preschool_child"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("preschool_group.id"), nullable=True)

    import_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("preschool_children_import.id"),
        nullable=True,
        index=True,
    )

    last_name = db.Column(db.String(150), nullable=False)
    first_name = db.Column(db.String(150), nullable=False)
    middle_name = db.Column(db.String(150), nullable=True)

    birth_date = db.Column(db.Date, nullable=True)
    personal_account = db.Column(db.String(100), nullable=True)

    status = db.Column(db.String(50), nullable=False, default="active")
    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    group = db.relationship("PreschoolGroup", backref=db.backref("children", lazy=True))
    import_batch = db.relationship("PreschoolChildrenImport", backref=db.backref("children", lazy=True))

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join([p for p in parts if p])
