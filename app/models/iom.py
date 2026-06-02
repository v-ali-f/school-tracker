from datetime import datetime

from app.core.extensions import db


IOM_TYPE_CHOICES = [
    ("NOO", "ИОМ НОО"),
    ("OOO_SOO", "ИОМ ООО / СОО"),
    ("UO", "ИОМ УО"),
    ("DO", "ИОМ ДО"),
]
IOM_TYPE_LABELS = dict(IOM_TYPE_CHOICES)

IOM_STATUS_CHOICES = [
    ("DRAFT", "Черновик"),
    ("IN_PROGRESS", "На заполнении"),
    ("ON_APPROVAL", "На согласовании"),
    ("APPROVED_BY_HEAD", "Согласован руководителем СППиСС"),
    ("APPROVED", "Утвержден"),
    ("ARCHIVED", "В архиве"),
]
IOM_STATUS_LABELS = dict(IOM_STATUS_CHOICES)


class IomCard(db.Model):
    __tablename__ = "iom_card"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=False, index=True)
    iom_type = db.Column(db.String(30), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="DRAFT", index=True)

    student_fio = db.Column(db.String(255), nullable=False)
    birth_date = db.Column(db.Date, nullable=True)
    birth_year = db.Column(db.Integer, nullable=True)
    education_level = db.Column(db.String(50), nullable=True, index=True)
    school_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    class_name = db.Column(db.String(100), nullable=True)
    parallel = db.Column(db.String(20), nullable=True, index=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True, index=True)
    building_name = db.Column(db.String(120), nullable=True)
    ovz_status = db.Column(db.String(120), nullable=True)
    nosology = db.Column(db.String(255), nullable=True)
    aop_variant = db.Column(db.String(255), nullable=True)
    parent_info = db.Column(db.Text, nullable=True)
    class_teacher_name = db.Column(db.String(255), nullable=True)
    support_staff_summary = db.Column(db.Text, nullable=True)

    curator_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    curator_name = db.Column(db.String(255), nullable=True)
    sppiss_head_name = db.Column(db.String(255), nullable=True)
    director_name = db.Column(db.String(255), nullable=True)
    consent_mark = db.Column(db.String(255), nullable=True)
    agreed_at = db.Column(db.Date, nullable=True)
    approved_at = db.Column(db.Date, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    agreed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    previous_card_id = db.Column(db.Integer, db.ForeignKey("iom_card.id"), nullable=True, index=True)
    archived_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    archived_at = db.Column(db.DateTime, nullable=True, index=True)

    child = db.relationship("Child", backref=db.backref("iom_cards", lazy=True))
    academic_year = db.relationship("AcademicYear")
    school_class = db.relationship("SchoolClass")
    building = db.relationship("Building")
    curator = db.relationship("User", foreign_keys=[curator_user_id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])
    agreed_by = db.relationship("User", foreign_keys=[agreed_by_user_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_user_id])
    archived_by = db.relationship("User", foreign_keys=[archived_by_user_id])
    previous_card = db.relationship("IomCard", remote_side=[id], foreign_keys=[previous_card_id])

    @property
    def status_label(self):
        return IOM_STATUS_LABELS.get((self.status or "").upper(), self.status or "—")

    @property
    def iom_type_label(self):
        return IOM_TYPE_LABELS.get((self.iom_type or "").upper(), self.iom_type or "—")


class IomHistory(db.Model):
    __tablename__ = "iom_history"

    id = db.Column(db.Integer, primary_key=True)
    iom_card_id = db.Column(db.Integer, db.ForeignKey("iom_card.id"), nullable=False, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    comment = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    iom_card = db.relationship(
        "IomCard", backref=db.backref("history_entries", cascade="all, delete-orphan", order_by="desc(IomHistory.created_at)")
    )
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])


class IomScheduleLesson(db.Model):
    __tablename__ = "iom_schedule_lesson"

    id = db.Column(db.Integer, primary_key=True)
    iom_card_id = db.Column(db.Integer, db.ForeignKey("iom_card.id"), nullable=False, index=True)
    weekday = db.Column(db.String(20), nullable=False, index=True)
    start_time = db.Column(db.String(20), nullable=False)
    subject_name = db.Column(db.String(255), nullable=False)
    source_type = db.Column(db.String(20), nullable=False, default="IMPORTED", index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    iom_card = db.relationship(
        "IomCard",
        backref=db.backref("schedule_lessons", cascade="all, delete-orphan", lazy=True, order_by="IomScheduleLesson.weekday, IomScheduleLesson.sort_order, IomScheduleLesson.start_time"),
    )




class IomScheduleCorrection(db.Model):
    __tablename__ = "iom_schedule_correction"

    id = db.Column(db.Integer, primary_key=True)
    iom_card_id = db.Column(db.Integer, db.ForeignKey("iom_card.id"), nullable=False, index=True)
    specialist_id = db.Column(db.Integer, db.ForeignKey("service_specialist.id"), nullable=False, index=True)
    weekday = db.Column(db.String(20), nullable=False, index=True)
    start_time = db.Column(db.String(20), nullable=False)
    end_time = db.Column(db.String(20), nullable=False)
    course_name = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.String(255), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    iom_card = db.relationship(
        "IomCard",
        backref=db.backref(
            "schedule_corrections",
            cascade="all, delete-orphan",
            lazy=True,
            order_by="IomScheduleCorrection.weekday, IomScheduleCorrection.start_time, IomScheduleCorrection.end_time",
        ),
    )
    specialist = db.relationship("ServiceSpecialist", foreign_keys=[specialist_id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

class IomImportSessionSchedule(db.Model):
    __tablename__ = "iom_import_session_schedule"

    id = db.Column(db.Integer, primary_key=True)
    iom_card_id = db.Column(db.Integer, db.ForeignKey("iom_card.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    rows_loaded = db.Column(db.Integer, nullable=False, default=0)
    imported_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    imported_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    comment = db.Column(db.String(255), nullable=True)

    iom_card = db.relationship(
        "IomCard",
        backref=db.backref("schedule_import_sessions", cascade="all, delete-orphan", lazy=True, order_by="desc(IomImportSessionSchedule.imported_at)"),
    )
    imported_by = db.relationship("User", foreign_keys=[imported_by_user_id])


class IomSectionData(db.Model):
    __tablename__ = "iom_section_data"

    id = db.Column(db.Integer, primary_key=True)
    iom_card_id = db.Column(db.Integer, db.ForeignKey("iom_card.id"), nullable=False, index=True)
    section_code = db.Column(db.String(80), nullable=False, index=True)
    section_title = db.Column(db.String(255), nullable=False)
    payload_json = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    iom_card = db.relationship(
        "IomCard",
        backref=db.backref("section_rows", cascade="all, delete-orphan", lazy=True),
    )
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (db.UniqueConstraint("iom_card_id", "section_code", name="uq_iom_section_per_card"),)


class IomSpecialistPlan(db.Model):
    __tablename__ = "iom_specialist_plan"

    id = db.Column(db.Integer, primary_key=True)
    iom_card_id = db.Column(db.Integer, db.ForeignKey("iom_card.id"), nullable=False, index=True)
    role_title = db.Column(db.String(150), nullable=False, index=True)
    specialist_id = db.Column(db.Integer, db.ForeignKey("service_specialist.id"), nullable=True, index=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("service_assignment.id"), nullable=True, index=True)
    recommendation_text = db.Column(db.Text, nullable=True)
    deficits_text = db.Column(db.Text, nullable=True)
    resources_text = db.Column(db.Text, nullable=True)
    tasks_text = db.Column(db.Text, nullable=True)
    work_form = db.Column(db.String(255), nullable=True)
    sessions_per_week = db.Column(db.String(50), nullable=True)
    course_name = db.Column(db.String(255), nullable=True)
    frequency = db.Column(db.String(255), nullable=True)
    expected_result = db.Column(db.Text, nullable=True)
    monitoring_terms = db.Column(db.String(255), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=100)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    iom_card = db.relationship(
        "IomCard",
        backref=db.backref("specialist_plans", cascade="all, delete-orphan", lazy=True, order_by="IomSpecialistPlan.sort_order, IomSpecialistPlan.id"),
    )
    specialist = db.relationship("ServiceSpecialist", foreign_keys=[specialist_id])
    assignment = db.relationship("ServiceAssignment", foreign_keys=[assignment_id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])


class IomCyclegramLink(db.Model):
    __tablename__ = "iom_cyclegram_link"

    id = db.Column(db.Integer, primary_key=True)
    correction_id = db.Column(db.Integer, db.ForeignKey("iom_schedule_correction.id"), nullable=False, unique=True, index=True)
    cyclegram_entry_id = db.Column(db.Integer, db.ForeignKey("service_cyclegram_entry.id"), nullable=False, index=True)
    sync_key = db.Column(db.String(255), nullable=True, index=True)
    synced_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    synced_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)

    correction = db.relationship("IomScheduleCorrection", backref=db.backref("cyclegram_links", cascade="all, delete-orphan", lazy=True))
    synced_by = db.relationship("User", foreign_keys=[synced_by_user_id])


class IomMonitoringTemplate(db.Model):
    __tablename__ = "iom_monitoring_template"

    id = db.Column(db.Integer, primary_key=True)
    iom_type = db.Column(db.String(30), nullable=False, index=True)
    period = db.Column(db.String(30), nullable=False, index=True)
    block_code = db.Column(db.String(50), nullable=False, index=True)
    block_title = db.Column(db.String(255), nullable=False)
    line_code = db.Column(db.String(80), nullable=False)
    line_title = db.Column(db.String(255), nullable=False)
    scale_type = db.Column(db.String(30), nullable=False, default='TEXT')
    is_enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=100)


class IomMonitoringEntry(db.Model):
    __tablename__ = "iom_monitoring_entry"

    id = db.Column(db.Integer, primary_key=True)
    iom_card_id = db.Column(db.Integer, db.ForeignKey("iom_card.id"), nullable=False, index=True)
    period = db.Column(db.String(30), nullable=False, index=True)
    block_code = db.Column(db.String(50), nullable=False, index=True)
    payload_json = db.Column(db.Text, nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    iom_card = db.relationship("IomCard", backref=db.backref("monitoring_entries", cascade="all, delete-orphan", lazy=True))
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (db.UniqueConstraint("iom_card_id", "period", "block_code", name="uq_iom_monitoring_entry"),)


class IomExportLog(db.Model):
    __tablename__ = "iom_export_log"

    id = db.Column(db.Integer, primary_key=True)
    iom_card_id = db.Column(db.Integer, db.ForeignKey("iom_card.id"), nullable=False, index=True)
    export_format = db.Column(db.String(10), nullable=False, index=True)
    status_snapshot = db.Column(db.String(30), nullable=True)
    exported_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    exported_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    iom_card = db.relationship("IomCard", backref=db.backref("export_logs", cascade="all, delete-orphan", lazy=True, order_by="desc(IomExportLog.exported_at)"))
    exported_by = db.relationship("User", foreign_keys=[exported_by_user_id])
