from datetime import datetime

from app.core.extensions import db


TARIFF_CYCLE_STATUSES = ("OPEN", "CLOSED", "ARCHIVED")
TARIFF_VERSION_TYPES = ("BASE", "CORRECTION", "EMERGENCY")
TARIFF_VERSION_STATUSES = (
    "DRAFT",
    "VALIDATION",
    "APPROVAL",
    "APPROVED",
    "EFFECTIVE",
    "SUPERSEDED",
    "ARCHIVED",
)
PLAN_KINDS = ("CURRICULUM", "EXTRACURRICULAR", "ADDITIONAL_EDUCATION")
PLAN_KIND_LABELS = {
    "CURRICULUM": "Основной учебный план",
    "EXTRACURRICULAR": "Внеурочная деятельность",
    "ADDITIONAL_EDUCATION": "Дополнительное образование",
}
PLAN_STATUSES = ("DRAFT", "READY", "LOCKED")
PLAN_STATUS_LABELS = {
    "DRAFT": "Черновик",
    "READY": "Готов к проверке",
    "LOCKED": "Заблокирован",
}
PLAN_COMPONENT_KINDS = (
    "MANDATORY",
    "PARTICIPANT_FORMED",
    "ELECTIVE",
    "EXTRACURRICULAR",
    "ADDITIONAL",
    "OTHER",
)
PLAN_COMPONENT_LABELS = {
    "MANDATORY": "Обязательная часть",
    "PARTICIPANT_FORMED": "Часть, формируемая участниками",
    "ELECTIVE": "Курс по выбору",
    "EXTRACURRICULAR": "Внеурочная деятельность",
    "ADDITIONAL": "Дополнительное образование",
    "OTHER": "Иная часть",
}
PLAN_SCOPE_KINDS = ("CLASS", "GRADE", "PROFILE")
PLAN_SCOPE_LABELS = {
    "CLASS": "Класс",
    "GRADE": "Параллель",
    "PROFILE": "Профиль",
}


class TariffCycle(db.Model):
    __tablename__ = "tariff_cycle"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization_settings.id"),
        nullable=True,
        index=True,
    )
    academic_year_id = db.Column(
        db.Integer,
        db.ForeignKey("academic_year.id"),
        nullable=False,
        index=True,
    )
    code = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(
        db.String(40),
        nullable=False,
        default="OPEN",
        server_default="OPEN",
        index=True,
    )
    opened_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    organization = db.relationship("OrganizationSettings")
    academic_year = db.relationship("AcademicYear")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('OPEN','CLOSED','ARCHIVED')",
            name="ck_tariff_cycle_status",
        ),
        db.CheckConstraint(
            "closed_at IS NULL OR opened_at IS NULL OR closed_at >= opened_at",
            name="ck_tariff_cycle_period",
        ),
        db.Index(
            "uq_tariff_cycle_global_year",
            "academic_year_id",
            unique=True,
            postgresql_where=db.text("organization_id IS NULL"),
            sqlite_where=db.text("organization_id IS NULL"),
        ),
        db.Index(
            "uq_tariff_cycle_local_year",
            "organization_id",
            "academic_year_id",
            unique=True,
            postgresql_where=db.text("organization_id IS NOT NULL"),
            sqlite_where=db.text("organization_id IS NOT NULL"),
        ),
        db.Index(
            "ix_tariff_cycle_scope_status",
            "organization_id",
            "status",
        ),
    )


class TariffVersion(db.Model):
    __tablename__ = "tariff_version"

    id = db.Column(db.Integer, primary_key=True)
    tariff_cycle_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_cycle.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_no = db.Column(db.Integer, nullable=False)
    version_type = db.Column(
        db.String(40),
        nullable=False,
        default="BASE",
        server_default="BASE",
    )
    status = db.Column(
        db.String(40),
        nullable=False,
        default="DRAFT",
        server_default="DRAFT",
        index=True,
    )
    effective_from = db.Column(db.Date, nullable=True)
    effective_to = db.Column(db.Date, nullable=True)
    origin_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id"),
        nullable=True,
    )
    reason_text = db.Column(db.String(500), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    effective_at = db.Column(db.DateTime, nullable=True)
    checksum = db.Column(db.String(128), nullable=True)
    revision = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    tariff_cycle = db.relationship(
        "TariffCycle",
        backref=db.backref("versions", lazy=True, cascade="all, delete-orphan"),
    )
    origin_version = db.relationship("TariffVersion", remote_side=[id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "version_type IN ('BASE','CORRECTION','EMERGENCY')",
            name="ck_tariff_version_type",
        ),
        db.CheckConstraint(
            "status IN ("
            "'DRAFT','VALIDATION','APPROVAL','APPROVED','EFFECTIVE',"
            "'SUPERSEDED','ARCHIVED'"
            ")",
            name="ck_tariff_version_status",
        ),
        db.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL "
            "OR effective_to >= effective_from",
            name="ck_tariff_version_effective_period",
        ),
        db.CheckConstraint("revision > 0", name="ck_tariff_version_revision"),
        db.UniqueConstraint(
            "tariff_cycle_id",
            "version_no",
            name="uq_tariff_version_cycle_number",
        ),
        db.Index(
            "ix_tariff_version_cycle_status",
            "tariff_cycle_id",
            "status",
        ),
    )


class TariffVersionStatusHistory(db.Model):
    __tablename__ = "tariff_version_status_history"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status = db.Column(db.String(40), nullable=True)
    to_status = db.Column(db.String(40), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    changed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    comment = db.Column(db.Text, nullable=True)

    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref(
            "status_history",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="TariffVersionStatusHistory.changed_at",
        ),
    )
    changed_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "to_status IN ("
            "'DRAFT','VALIDATION','APPROVAL','APPROVED','EFFECTIVE',"
            "'SUPERSEDED','ARCHIVED'"
            ")",
            name="ck_tariff_version_history_to_status",
        ),
        db.CheckConstraint(
            "from_status IS NULL OR from_status IN ("
            "'DRAFT','VALIDATION','APPROVAL','APPROVED','EFFECTIVE',"
            "'SUPERSEDED','ARCHIVED'"
            ")",
            name="ck_tariff_version_history_from_status",
        ),
        db.Index(
            "ix_tariff_version_history_changed",
            "tariff_version_id",
            "changed_at",
        ),
    )


class EducationPlan(db.Model):
    __tablename__ = "education_plan"

    id = db.Column(db.Integer, primary_key=True)
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    root_plan_id = db.Column(
        db.Integer,
        db.ForeignKey("education_plan.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    plan_kind = db.Column(db.String(40), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    profile_name = db.Column(db.String(160), nullable=True)
    education_level = db.Column(db.String(20), nullable=True, index=True)
    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id"),
        nullable=True,
        index=True,
    )
    scope_code = db.Column(db.String(80), nullable=False, default="ALL", server_default="ALL")
    status = db.Column(
        db.String(30),
        nullable=False,
        default="DRAFT",
        server_default="DRAFT",
        index=True,
    )
    revision = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref("plans", lazy=True, cascade="all, delete-orphan"),
    )
    root_plan = db.relationship(
        "EducationPlan",
        remote_side=[id],
        foreign_keys=[root_plan_id],
        backref=db.backref(
            "companion_plans",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    building = db.relationship("Building")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "plan_kind IN ('CURRICULUM','EXTRACURRICULAR','ADDITIONAL_EDUCATION')",
            name="ck_education_plan_kind",
        ),
        db.CheckConstraint(
            "status IN ('DRAFT','READY','LOCKED')",
            name="ck_education_plan_status",
        ),
        db.CheckConstraint(
            "root_plan_id IS NULL OR plan_kind <> 'CURRICULUM'",
            name="ck_education_plan_companion_kind",
        ),
        db.CheckConstraint("revision > 0", name="ck_education_plan_revision"),
        db.UniqueConstraint(
            "tariff_version_id",
            "plan_kind",
            "scope_code",
            "name",
            name="uq_education_plan_version_scope_name",
        ),
        db.Index(
            "ix_education_plan_version_kind",
            "tariff_version_id",
            "plan_kind",
        ),
        db.Index(
            "uq_education_plan_root_kind",
            "root_plan_id",
            "plan_kind",
            unique=True,
            postgresql_where=db.text("root_plan_id IS NOT NULL"),
            sqlite_where=db.text("root_plan_id IS NOT NULL"),
        ),
    )


class EducationPlanLine(db.Model):
    __tablename__ = "education_plan_line"

    id = db.Column(db.Integer, primary_key=True)
    education_plan_id = db.Column(
        db.Integer,
        db.ForeignKey("education_plan.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    education_activity_id = db.Column(
        db.Integer,
        db.ForeignKey("education_activity.id"),
        nullable=False,
        index=True,
    )
    component_kind = db.Column(db.String(40), nullable=False, index=True)
    weekly_hours = db.Column(db.Numeric(8, 3), nullable=True)
    weeks_count = db.Column(db.Numeric(6, 3), nullable=True)
    annual_hours = db.Column(db.Numeric(8, 3), nullable=True)
    requires_division = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.false(),
    )
    profile_code = db.Column(db.String(80), nullable=True)
    source_line_id = db.Column(
        db.Integer,
        db.ForeignKey("education_plan_line.id"),
        nullable=True,
    )
    sort_order = db.Column(db.Integer, nullable=False, default=100, server_default="100")
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    education_plan = db.relationship(
        "EducationPlan",
        backref=db.backref(
            "lines",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="EducationPlanLine.sort_order",
        ),
    )
    education_activity = db.relationship("EducationActivity")
    source_line = db.relationship("EducationPlanLine", remote_side=[id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "component_kind IN ("
            "'MANDATORY','PARTICIPANT_FORMED','ELECTIVE',"
            "'EXTRACURRICULAR','ADDITIONAL','OTHER'"
            ")",
            name="ck_education_plan_line_component",
        ),
        db.CheckConstraint(
            "(weekly_hours IS NOT NULL OR annual_hours IS NOT NULL) "
            "AND (weekly_hours IS NULL OR weekly_hours >= 0) "
            "AND (weeks_count IS NULL OR weeks_count > 0) "
            "AND (annual_hours IS NULL OR annual_hours >= 0)",
            name="ck_education_plan_line_hours",
        ),
        db.Index(
            "ix_education_plan_line_activity_component",
            "education_activity_id",
            "component_kind",
        ),
    )


class EducationPlanLineScope(db.Model):
    __tablename__ = "education_plan_line_scope"

    id = db.Column(db.Integer, primary_key=True)
    education_plan_line_id = db.Column(
        db.Integer,
        db.ForeignKey("education_plan_line.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_kind = db.Column(db.String(30), nullable=False, index=True)
    school_class_id = db.Column(
        db.Integer,
        db.ForeignKey("school_class.id"),
        nullable=True,
        index=True,
    )
    grade = db.Column(db.SmallInteger, nullable=True)
    profile_code = db.Column(db.String(80), nullable=True)
    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id"),
        nullable=True,
        index=True,
    )
    scope_key = db.Column(db.String(180), nullable=False)

    education_plan_line = db.relationship(
        "EducationPlanLine",
        backref=db.backref("scopes", lazy=True, cascade="all, delete-orphan"),
    )
    school_class = db.relationship("SchoolClass")
    building = db.relationship("Building")

    __table_args__ = (
        db.CheckConstraint(
            "scope_kind IN ('CLASS','GRADE','PROFILE')",
            name="ck_education_plan_line_scope_kind",
        ),
        db.CheckConstraint(
            "(scope_kind = 'CLASS' AND school_class_id IS NOT NULL "
            "AND grade IS NULL AND profile_code IS NULL) OR "
            "(scope_kind = 'GRADE' AND school_class_id IS NULL "
            "AND grade BETWEEN 1 AND 11 AND profile_code IS NULL) OR "
            "(scope_kind = 'PROFILE' AND school_class_id IS NULL "
            "AND profile_code IS NOT NULL)",
            name="ck_education_plan_line_scope_fields",
        ),
        db.UniqueConstraint(
            "education_plan_line_id",
            "scope_key",
            name="uq_education_plan_line_scope_key",
        ),
        db.Index(
            "ix_education_plan_scope_grade_profile",
            "grade",
            "profile_code",
            "building_id",
        ),
    )


class EducationPlanLinePeriod(db.Model):
    __tablename__ = "education_plan_line_period"

    id = db.Column(db.Integer, primary_key=True)
    education_plan_line_id = db.Column(
        db.Integer,
        db.ForeignKey("education_plan_line.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(db.Date, nullable=False)
    weeks_count = db.Column(db.Numeric(6, 3), nullable=True)
    weekly_hours = db.Column(db.Numeric(8, 3), nullable=True)
    annual_hours = db.Column(db.Numeric(8, 3), nullable=True)

    education_plan_line = db.relationship(
        "EducationPlanLine",
        backref=db.backref(
            "periods",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="EducationPlanLinePeriod.date_from",
        ),
    )

    __table_args__ = (
        db.CheckConstraint(
            "date_to >= date_from",
            name="ck_education_plan_line_period_dates",
        ),
        db.CheckConstraint(
            "(weeks_count IS NULL OR weeks_count >= 0) "
            "AND (weekly_hours IS NULL OR weekly_hours >= 0) "
            "AND (annual_hours IS NULL OR annual_hours >= 0)",
            name="ck_education_plan_line_period_hours",
        ),
        db.UniqueConstraint(
            "education_plan_line_id",
            "date_from",
            "date_to",
            name="uq_education_plan_line_period_dates",
        ),
        db.Index(
            "ix_education_plan_line_period_range",
            "education_plan_line_id",
            "date_from",
            "date_to",
        ),
    )


PLAN_BINDING_MODES = (
    "CLASS",
    "STUDENTS",
)


class EducationPlanBinding(db.Model):
    __tablename__ = "education_plan_binding"

    id = db.Column(db.Integer, primary_key=True)
    education_plan_id = db.Column(
        db.Integer,
        db.ForeignKey("education_plan.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    population_snapshot_class_id = db.Column(
        db.Integer,
        db.ForeignKey("population_snapshot_class.id"),
        nullable=False,
        index=True,
    )
    binding_mode = db.Column(
        db.String(20),
        nullable=False,
        default="STUDENTS",
        server_default="STUDENTS",
    )
    revision = db.Column(
        db.Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    updated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
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

    education_plan = db.relationship(
        "EducationPlan",
        backref=db.backref(
            "class_bindings",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    population_snapshot_class = db.relationship("PopulationSnapshotClass")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "binding_mode IN ('CLASS','STUDENTS')",
            name="ck_education_plan_binding_mode",
        ),
        db.CheckConstraint(
            "revision > 0",
            name="ck_education_plan_binding_revision",
        ),
        db.UniqueConstraint(
            "education_plan_id",
            "population_snapshot_class_id",
            name="uq_education_plan_binding_plan_class",
        ),
        db.Index(
            "ix_education_plan_binding_class_plan",
            "population_snapshot_class_id",
            "education_plan_id",
        ),
    )


class EducationPlanBindingMember(db.Model):
    __tablename__ = "education_plan_binding_member"

    id = db.Column(db.Integer, primary_key=True)
    education_plan_binding_id = db.Column(
        db.Integer,
        db.ForeignKey("education_plan_binding.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_enrollment_id = db.Column(
        db.Integer,
        db.ForeignKey("population_snapshot_enrollment.id"),
        nullable=False,
        index=True,
    )
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    education_plan_binding = db.relationship(
        "EducationPlanBinding",
        backref=db.backref(
            "members",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    snapshot_enrollment = db.relationship("PopulationSnapshotEnrollment")
    created_by = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint(
            "education_plan_binding_id",
            "snapshot_enrollment_id",
            name="uq_education_plan_binding_member",
        ),
        db.Index(
            "ix_education_plan_binding_member_enrollment",
            "snapshot_enrollment_id",
            "education_plan_binding_id",
        ),
    )


__all__ = [
    "TARIFF_CYCLE_STATUSES",
    "TARIFF_VERSION_TYPES",
    "TARIFF_VERSION_STATUSES",
    "PLAN_KINDS",
    "PLAN_KIND_LABELS",
    "PLAN_STATUSES",
    "PLAN_STATUS_LABELS",
    "PLAN_COMPONENT_KINDS",
    "PLAN_COMPONENT_LABELS",
    "PLAN_SCOPE_KINDS",
    "PLAN_SCOPE_LABELS",
    "TariffCycle",
    "TariffVersion",
    "TariffVersionStatusHistory",
    "EducationPlan",
    "EducationPlanLine",
    "EducationPlanLineScope",
    "EducationPlanLinePeriod",
    "PLAN_BINDING_MODES",
    "EducationPlanBinding",
    "EducationPlanBindingMember",
]
