from datetime import datetime

from app.core.extensions import db


class ServiceSpecialization(db.Model):
    __tablename__ = "service_specialization"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<ServiceSpecialization {self.code}>"


class ServiceSpecialist(db.Model):
    __tablename__ = "service_specialist"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    last_name = db.Column(db.String(120), nullable=False)
    first_name = db.Column(db.String(120), nullable=False)
    middle_name = db.Column(db.String(120), nullable=True)
    position_title = db.Column(db.String(150), nullable=True)
    rate_value = db.Column(db.Float, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    main_building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True, index=True)
    phone = db.Column(db.String(64), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    admin_comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
    main_building = db.relationship("Building", foreign_keys=[main_building_id])

    @property
    def fio(self):
        parts = [self.last_name or "", self.first_name or "", self.middle_name or ""]
        return " ".join(x.strip() for x in parts if x and x.strip())

    @property
    def specializations_text(self):
        names = [
            link.specialization.name
            for link in sorted(
                self.specialization_links,
                key=lambda x: (
                    (x.specialization.sort_order if x.specialization else 999),
                    (x.specialization.name if x.specialization else ""),
                ),
            )
            if link.specialization
        ]
        return ", ".join(names)

    @property
    def buildings_text(self):
        names = [link.building.short_name or link.building.name for link in self.building_links if link.building]
        return ", ".join(dict.fromkeys(names))

    @property
    def is_responsible(self):
        return any(item.is_active for item in self.responsible_links)

    def __repr__(self):
        return f"<ServiceSpecialist {self.fio}>"


class ServiceSpecialistSpecialization(db.Model):
    __tablename__ = "service_specialist_specialization"

    specialist_id = db.Column(db.Integer, db.ForeignKey("service_specialist.id"), primary_key=True)
    specialization_id = db.Column(db.Integer, db.ForeignKey("service_specialization.id"), primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    specialist = db.relationship(
        "ServiceSpecialist",
        backref=db.backref("specialization_links", cascade="all, delete-orphan", lazy="joined"),
    )
    specialization = db.relationship(
        "ServiceSpecialization",
        backref=db.backref("specialist_links", cascade="all, delete-orphan", lazy="joined"),
    )


class ServiceSpecialistBuilding(db.Model):
    __tablename__ = "service_specialist_building"

    specialist_id = db.Column(db.Integer, db.ForeignKey("service_specialist.id"), primary_key=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), primary_key=True)
    is_main = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    specialist = db.relationship(
        "ServiceSpecialist", backref=db.backref("building_links", cascade="all, delete-orphan", lazy="joined")
    )
    building = db.relationship(
        "Building", backref=db.backref("service_specialist_links", cascade="all, delete-orphan", lazy="joined")
    )


class ServiceResponsible(db.Model):
    __tablename__ = "service_responsible"

    id = db.Column(db.Integer, primary_key=True)
    specialist_id = db.Column(db.Integer, db.ForeignKey("service_specialist.id"), nullable=False, index=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    specialist = db.relationship(
        "ServiceSpecialist", backref=db.backref("responsible_links", cascade="all, delete-orphan", lazy="joined")
    )
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_user_id])

    __table_args__ = (db.UniqueConstraint("specialist_id", name="uq_service_responsible_specialist"),)

    def __repr__(self):
        return f"<ServiceResponsible specialist={self.specialist_id} active={self.is_active}>"


class ServiceAssignment(db.Model):
    __tablename__ = "service_assignment"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    specialist_id = db.Column(db.Integer, db.ForeignKey("service_specialist.id"), nullable=False, index=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True, index=True)
    role_title = db.Column(db.String(150), nullable=True)
    start_date = db.Column(db.Date, nullable=True, index=True)
    end_date = db.Column(db.Date, nullable=True, index=True)
    basis = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="ACTIVE", index=True)
    comment = db.Column(db.Text, nullable=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), nullable=True, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    child = db.relationship("Child", backref=db.backref("service_assignments", cascade="all, delete-orphan", lazy=True))
    specialist = db.relationship(
        "ServiceSpecialist", backref=db.backref("child_assignments", cascade="all, delete-orphan", lazy=True)
    )
    building = db.relationship("Building", foreign_keys=[building_id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    incident = db.relationship("Incident", foreign_keys=[incident_id])

    @property
    def is_active_assignment(self):
        return (self.status or "").upper() == "ACTIVE"

    @property
    def status_label(self):
        return {"ACTIVE": "Активно", "FINISHED": "Завершено", "ARCHIVED": "Архив"}.get(
            (self.status or "").upper(), self.status or "—"
        )

    @property
    def child_class_name(self):
        return self.child.current_class_name if self.child else None

    @property
    def child_building_name(self):
        if self.child and self.child.current_building:
            return self.child.current_building.short_name or self.child.current_building.name
        return None


class ServiceAssignmentHistory(db.Model):
    __tablename__ = "service_assignment_history"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("service_assignment.id"), nullable=False, index=True)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    old_status = db.Column(db.String(20), nullable=True)
    new_status = db.Column(db.String(20), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    assignment = db.relationship(
        "ServiceAssignment", backref=db.backref("history_entries", cascade="all, delete-orphan", lazy="joined")
    )
    changed_by = db.relationship("User", foreign_keys=[changed_by_user_id])


class ServiceActivityType(db.Model):
    __tablename__ = "service_activity_type"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(120), nullable=False, unique=True, index=True)
    name = db.Column(db.String(255), nullable=False)
    work_category = db.Column(db.String(30), nullable=False, index=True)
    specialist_scope = db.Column(db.String(255), nullable=True)
    template_text = db.Column(db.String(255), nullable=True)
    requires_child = db.Column(db.Boolean, nullable=False, default=False)
    requires_group = db.Column(db.Boolean, nullable=False, default=False)
    is_group_activity = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=100)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @property
    def work_category_label(self):
        return {"PRACTICAL": "Практическая", "METHODICAL": "Организационно-методическая"}.get(
            (self.work_category or "").upper(), self.work_category or "—"
        )


class ServiceCyclegram(db.Model):
    __tablename__ = "service_cyclegram"

    id = db.Column(db.Integer, primary_key=True)
    specialist_id = db.Column(db.Integer, db.ForeignKey("service_specialist.id"), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=True)
    position_title = db.Column(db.String(150), nullable=True)
    rate_value = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="DRAFT", index=True)
    buildings_text = db.Column(db.String(255), nullable=True)
    copied_from_cyclegram_id = db.Column(db.Integer, db.ForeignKey("service_cyclegram.id"), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewer_comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    specialist = db.relationship(
        "ServiceSpecialist", backref=db.backref("cyclegrams", cascade="all, delete-orphan", lazy=True)
    )
    copied_from = db.relationship("ServiceCyclegram", remote_side=[id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    @property
    def status_label(self):
        return {
            "DRAFT": "Черновик",
            "REVIEW": "На проверке",
            "APPROVED": "Утверждена",
            "ARCHIVED": "Архив",
        }.get((self.status or "").upper(), self.status or "—")


class ServiceCyclegramEntry(db.Model):
    __tablename__ = "service_cyclegram_entry"

    id = db.Column(db.Integer, primary_key=True)
    cyclegram_id = db.Column(db.Integer, db.ForeignKey("service_cyclegram.id"), nullable=False, index=True)
    weekday = db.Column(db.Integer, nullable=False, index=True)
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    activity_type_id = db.Column(db.Integer, db.ForeignKey("service_activity_type.id"), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=True, index=True)
    group_text = db.Column(db.String(255), nullable=True)
    work_category = db.Column(db.String(30), nullable=False, index=True)
    minutes = db.Column(db.Integer, nullable=False, default=0)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True, index=True)
    comment = db.Column(db.Text, nullable=True)
    minutes_adjusted = db.Column(db.Boolean, nullable=False, default=False)
    adjustment_reason = db.Column(db.String(255), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=100)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    cyclegram = db.relationship(
        "ServiceCyclegram", backref=db.backref("entries", cascade="all, delete-orphan", lazy=True)
    )
    activity_type = db.relationship("ServiceActivityType")
    child = db.relationship("Child")
    building = db.relationship("Building")

    @property
    def weekday_label(self):
        return {
            1: "Понедельник",
            2: "Вторник",
            3: "Среда",
            4: "Четверг",
            5: "Пятница",
            6: "Суббота",
            7: "Воскресенье",
        }.get(self.weekday, str(self.weekday))

    @property
    def interval_text(self):
        return f"{self.start_time}–{self.end_time}"


class ServiceCyclegramHistory(db.Model):
    __tablename__ = "service_cyclegram_history"

    id = db.Column(db.Integer, primary_key=True)
    cyclegram_id = db.Column(db.Integer, db.ForeignKey("service_cyclegram.id"), nullable=False, index=True)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    old_status = db.Column(db.String(20), nullable=True)
    new_status = db.Column(db.String(20), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    cyclegram = db.relationship(
        "ServiceCyclegram", backref=db.backref("history_entries", cascade="all, delete-orphan", lazy="joined")
    )
    changed_by = db.relationship("User", foreign_keys=[changed_by_user_id])



class ServicePresentation(db.Model):
    __tablename__ = "service_presentation"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    basis = db.Column(db.String(40), nullable=True, index=True)
    initiator_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    methodist_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="DRAFT", index=True)
    title = db.Column(db.String(255), nullable=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True, index=True)
    school_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    last_changed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    ready_percent = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    child = db.relationship("Child", backref=db.backref("service_presentations", cascade="all, delete-orphan", lazy=True))
    initiator = db.relationship("User", foreign_keys=[initiator_user_id])
    methodist = db.relationship("User", foreign_keys=[methodist_user_id])
    last_changed_by = db.relationship("User", foreign_keys=[last_changed_by_user_id])
    building = db.relationship("Building", foreign_keys=[building_id])
    school_class = db.relationship("SchoolClass", foreign_keys=[school_class_id])

    @property
    def status_label(self):
        return {
            "DRAFT": "Черновик",
            "IN_PROGRESS": "В работе",
            "REVIEW": "На проверке",
            "APPROVED": "Согласовано",
            "EXPORTED": "Выгружено",
            "ARCHIVED": "Архив",
        }.get((self.status or "").upper(), self.status or "—")


class ServicePresentationBlock(db.Model):
    __tablename__ = "service_presentation_block"

    id = db.Column(db.Integer, primary_key=True)
    presentation_id = db.Column(db.Integer, db.ForeignKey("service_presentation.id"), nullable=False, index=True)
    block_code = db.Column(db.String(80), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=100)
    fill_mode = db.Column(db.String(30), nullable=False, default="MANUAL")
    executor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    executor_specialist_id = db.Column(db.Integer, db.ForeignKey("service_specialist.id"), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="NOT_STARTED", index=True)
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    hint_text = db.Column(db.Text, nullable=True)
    recommended_text = db.Column(db.Text, nullable=True)
    content_text = db.Column(db.Text, nullable=True)
    reviewer_comment = db.Column(db.Text, nullable=True)
    source_name = db.Column(db.String(120), nullable=True)
    source_updated_at = db.Column(db.DateTime, nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    presentation = db.relationship(
        "ServicePresentation", backref=db.backref("blocks", cascade="all, delete-orphan", lazy=True)
    )
    executor_user = db.relationship("User", foreign_keys=[executor_user_id])
    executor_specialist = db.relationship("ServiceSpecialist", foreign_keys=[executor_specialist_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (db.UniqueConstraint("presentation_id", "block_code", name="uq_service_presentation_block"),)

    @property
    def status_label(self):
        return {
            "NOT_STARTED": "Не начат",
            "IN_PROGRESS": "В работе",
            "FILLED": "Заполнен",
            "CHECKED": "Проверен",
        }.get((self.status or "").upper(), self.status or "—")


class ServicePresentationHistory(db.Model):
    __tablename__ = "service_presentation_history"

    id = db.Column(db.Integer, primary_key=True)
    presentation_id = db.Column(db.Integer, db.ForeignKey("service_presentation.id"), nullable=False, index=True)
    block_id = db.Column(db.Integer, db.ForeignKey("service_presentation_block.id"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    action = db.Column(db.String(80), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    presentation = db.relationship(
        "ServicePresentation", backref=db.backref("history_entries", cascade="all, delete-orphan", lazy=True)
    )
    block = db.relationship("ServicePresentationBlock", foreign_keys=[block_id])
    user = db.relationship("User", foreign_keys=[user_id])


class ServiceRateNorm(db.Model):
    __tablename__ = "service_rate_norm"

    id = db.Column(db.Integer, primary_key=True)
    specialization_id = db.Column(db.Integer, db.ForeignKey("service_specialization.id"), nullable=False, index=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True, index=True)
    effective_from = db.Column(db.Date, nullable=False, index=True, default=datetime.utcnow)
    children_per_rate = db.Column(db.Float, nullable=False, default=25.0)
    category_coefficient = db.Column(db.Float, nullable=False, default=1.0)
    weekly_hours_norm = db.Column(db.Float, nullable=False, default=36.0)
    complexity_coefficient = db.Column(db.Float, nullable=False, default=1.0)
    rounding_rule = db.Column(db.String(20), nullable=False, default="UP")
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    comment = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    specialization = db.relationship("ServiceSpecialization", foreign_keys=[specialization_id])
    building = db.relationship("Building", foreign_keys=[building_id])

    @property
    def rounding_rule_label(self):
        return {
            "UP": "Округление вверх",
            "HALF_UP": "До 0,5",
            "INT": "До целого",
        }.get((self.rounding_rule or "").upper(), self.rounding_rule or "—")
