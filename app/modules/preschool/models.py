from datetime import datetime

from app.core.extensions import db

PRESCHOOL_MCKO_TITLE = "Профессиональные компетенции воспитателя"


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


class PreschoolBuildingStaff(db.Model):
    __tablename__ = "preschool_building_staff"

    id = db.Column(db.Integer, primary_key=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    position = db.Column(db.String(40), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    building = db.relationship("Building")
    user = db.relationship("User", foreign_keys=[user_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_user_id])

    __table_args__ = (
        db.UniqueConstraint("building_id", "user_id", "position", name="uq_preschool_building_staff"),
    )


class PreschoolGroupAssignment(db.Model):
    __tablename__ = "preschool_group_assignment"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("preschool_group.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    position = db.Column(db.String(40), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    source = db.Column(db.String(20), nullable=False, default="manual")
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    group = db.relationship("PreschoolGroup", backref=db.backref("staff_assignments", lazy=True))
    user = db.relationship("User", foreign_keys=[user_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_user_id])
    academic_year = db.relationship("AcademicYear")
    building = db.relationship("Building")

    __table_args__ = (
        db.UniqueConstraint("group_id", "user_id", "position", name="uq_preschool_group_staff"),
    )


class PreschoolStaffChange(db.Model):
    __tablename__ = "preschool_staff_change"

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(20), nullable=False)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey("preschool_group.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    position = db.Column(db.String(40), nullable=False)
    action = db.Column(db.String(20), nullable=False)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class PreschoolAchievement(db.Model):
    __tablename__ = "preschool_achievement"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    child_id = db.Column(db.Integer, db.ForeignKey("preschool_child.id"), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey("preschool_group.id"), nullable=True)
    event_name = db.Column(db.String(255), nullable=False)
    level = db.Column(db.String(120), nullable=True)
    organizer = db.Column(db.String(255), nullable=True)
    event_date = db.Column(db.Date, nullable=True)
    result = db.Column(db.String(255), nullable=True)
    award = db.Column(db.String(255), nullable=True)
    document = db.Column(db.String(255), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    teacher = db.relationship("User", foreign_keys=[teacher_id])
    child = db.relationship("PreschoolChild")
    group = db.relationship("PreschoolGroup")


class PreschoolProfileChange(db.Model):
    __tablename__ = "preschool_profile_change"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    old_values = db.Column(db.JSON, nullable=False)
    new_values = db.Column(db.JSON, nullable=False)


class PreschoolDashboardSetting(db.Model):
    __tablename__ = "preschool_dashboard_setting"

    id = db.Column(db.Integer, primary_key=True)
    warning_months = db.Column(db.Integer, nullable=False, default=6)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PreschoolResponsibility(db.Model):
    __tablename__ = "preschool_responsibility"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(40), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_user_id])


class PreschoolResponsibilityChange(db.Model):
    __tablename__ = "preschool_responsibility_change"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(40), nullable=False, index=True)
    previous_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    new_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    previous_user = db.relationship("User", foreign_keys=[previous_user_id])
    new_user = db.relationship("User", foreign_keys=[new_user_id])
    changed_by = db.relationship("User", foreign_keys=[changed_by_user_id])


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

    reg_address = db.Column(db.String(700), nullable=True)
    living_address = db.Column(db.String(700), nullable=True)
    actual_address = db.Column(db.String(700), nullable=True)

    status = db.Column(db.String(50), nullable=False, default="active")
    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    group = db.relationship("PreschoolGroup", backref=db.backref("children", lazy=True))
    import_batch = db.relationship("PreschoolChildrenImport", backref=db.backref("children", lazy=True))

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join([p for p in parts if p])



class PreschoolRepresentative(db.Model):
    __tablename__ = "preschool_representative"

    id = db.Column(db.Integer, primary_key=True)

    child_id = db.Column(
        db.Integer,
        db.ForeignKey("preschool_child.id"),
        nullable=False,
        index=True,
    )

    relation = db.Column(db.String(100), nullable=True)
    full_name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    address = db.Column(db.String(500), nullable=True)
    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    child = db.relationship("PreschoolChild", backref=db.backref("representatives", lazy=True, cascade="all, delete-orphan"))



class PreschoolAttendanceUpload(db.Model):
    __tablename__ = "preschool_attendance_upload"

    id = db.Column(db.Integer, primary_key=True)

    academic_year_id = db.Column(
        db.Integer,
        db.ForeignKey("academic_year.id"),
        nullable=True,
        index=True,
    )

    month = db.Column(db.String(20), nullable=True, index=True)
    original_filename = db.Column(db.String(500), nullable=True)
    stored_filename = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="uploaded")
    comment = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    academic_year = db.relationship("AcademicYear")



class PreschoolAttendanceRecord(db.Model):
    __tablename__ = "preschool_attendance_record"

    id = db.Column(db.Integer, primary_key=True)

    upload_id = db.Column(
        db.Integer,
        db.ForeignKey("preschool_attendance_upload.id"),
        nullable=False,
        index=True,
    )

    group_id = db.Column(
        db.Integer,
        db.ForeignKey("preschool_group.id"),
        nullable=True,
        index=True,
    )

    child_id = db.Column(
        db.Integer,
        db.ForeignKey("preschool_child.id"),
        nullable=True,
        index=True,
    )

    source_filename = db.Column(db.String(500), nullable=True)
    child_name = db.Column(db.String(255), nullable=False)
    account_number = db.Column(db.String(100), nullable=True)

    missed_total = db.Column(db.Integer, nullable=False, default=0)
    credited_days = db.Column(db.Integer, nullable=False, default=0)
    payment_days = db.Column(db.Integer, nullable=False, default=0)
    child_days = db.Column(db.Integer, nullable=False, default=0)

    absence_reasons = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    upload = db.relationship("PreschoolAttendanceUpload", backref=db.backref("records", lazy=True, cascade="all, delete-orphan"))
    group = db.relationship("PreschoolGroup")
    child = db.relationship("PreschoolChild")



class PreschoolChildMovement(db.Model):
    __tablename__ = "preschool_child_movement"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("preschool_child.id"), nullable=False, index=True)

    movement_date = db.Column(db.Date, nullable=True, index=True)
    movement_type = db.Column(db.String(80), nullable=False)

    from_academic_year_id = db.Column(
        db.Integer,
        db.ForeignKey("academic_year.id"),
        nullable=True,
        index=True,
    )

    to_academic_year_id = db.Column(
        db.Integer,
        db.ForeignKey("academic_year.id"),
        nullable=True,
        index=True,
    )

    from_group_id = db.Column(db.Integer, db.ForeignKey("preschool_group.id"), nullable=True, index=True)
    to_group_id = db.Column(db.Integer, db.ForeignKey("preschool_group.id"), nullable=True, index=True)

    basis = db.Column(db.String(500), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    from_status = db.Column(db.String(50), nullable=True)
    to_status = db.Column(db.String(50), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reversed_at = db.Column(db.DateTime, nullable=True)
    reversed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    child = db.relationship("PreschoolChild", backref=db.backref("movements", lazy=True, cascade="all, delete-orphan"))
    from_academic_year = db.relationship("AcademicYear", foreign_keys=[from_academic_year_id])
    to_academic_year = db.relationship("AcademicYear", foreign_keys=[to_academic_year_id])
    from_group = db.relationship("PreschoolGroup", foreign_keys=[from_group_id])
    to_group = db.relationship("PreschoolGroup", foreign_keys=[to_group_id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    reversed_by = db.relationship("User", foreign_keys=[reversed_by_user_id])
