from app import db
from datetime import datetime


class PreschoolBuilding(db.Model):
    __tablename__ = "preschool_building"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    short_name = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class PreschoolGroup(db.Model):
    __tablename__ = "preschool_group"

    id = db.Column(db.Integer, primary_key=True)
    building_id = db.Column(db.Integer, db.ForeignKey("preschool_building.id"), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    age_level = db.Column(db.String(100), nullable=True)
    teacher_name = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    building = db.relationship("PreschoolBuilding", backref=db.backref("groups", lazy=True))


class PreschoolChild(db.Model):
    __tablename__ = "preschool_child"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("preschool_group.id"), nullable=True)

    last_name = db.Column(db.String(150), nullable=False)
    first_name = db.Column(db.String(150), nullable=False)
    middle_name = db.Column(db.String(150), nullable=True)

    birth_date = db.Column(db.Date, nullable=True)
    personal_account = db.Column(db.String(100), nullable=True)

    status = db.Column(db.String(50), nullable=False, default="active")
    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    group = db.relationship("PreschoolGroup", backref=db.backref("children", lazy=True))

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join([p for p in parts if p])
