from datetime import datetime

from app.core.extensions import db


ACTIVITY_KINDS = (
    "SUBJECT",
    "COURSE",
    "MODULE",
    "EXTRACURRICULAR_COURSE",
    "ADDITIONAL_PROGRAM",
    "CLUB_OR_SECTION",
    "OLYMPIAD_DIRECTION",
)

ACTIVITY_KIND_LABELS = {
    "SUBJECT": "Учебный предмет",
    "COURSE": "Учебный курс",
    "MODULE": "Учебный модуль",
    "EXTRACURRICULAR_COURSE": "Внеурочный курс",
    "ADDITIONAL_PROGRAM": "Программа дополнительного образования",
    "CLUB_OR_SECTION": "Кружок или секция",
    "OLYMPIAD_DIRECTION": "Олимпиадное направление",
}


class EducationActivity(db.Model):
    __tablename__ = "education_activity"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization_settings.id"),
        nullable=True,
        index=True,
    )
    code = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    short_name = db.Column(db.String(120), nullable=True)
    activity_kind = db.Column(db.String(40), nullable=False, index=True)
    education_level = db.Column(db.String(20), nullable=True, index=True)
    is_global = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    is_tariffable = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true(), index=True)
    valid_from = db.Column(db.Date, nullable=True)
    valid_to = db.Column(db.Date, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    organization = db.relationship("OrganizationSettings", foreign_keys=[organization_id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "activity_kind IN ("
            "'SUBJECT','COURSE','MODULE','EXTRACURRICULAR_COURSE',"
            "'ADDITIONAL_PROGRAM','CLUB_OR_SECTION','OLYMPIAD_DIRECTION'"
            ")",
            name="ck_education_activity_kind",
        ),
        db.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_education_activity_valid_period",
        ),
        db.CheckConstraint(
            "(is_global AND organization_id IS NULL) OR "
            "(NOT is_global AND organization_id IS NOT NULL)",
            name="ck_education_activity_organization_scope",
        ),
        db.Index(
            "uq_education_activity_global_code",
            "code",
            unique=True,
            postgresql_where=db.text("organization_id IS NULL"),
            sqlite_where=db.text("organization_id IS NULL"),
        ),
        db.Index(
            "uq_education_activity_local_code",
            "organization_id",
            "code",
            unique=True,
            postgresql_where=db.text("organization_id IS NOT NULL"),
            sqlite_where=db.text("organization_id IS NOT NULL"),
        ),
        db.Index(
            "ix_education_activity_catalog",
            "organization_id",
            "activity_kind",
            "is_active",
        ),
    )

    def __repr__(self):
        return f"<EducationActivity {self.code}:{self.name}>"


class EducationActivityAlias(db.Model):
    __tablename__ = "education_activity_alias"

    id = db.Column(db.Integer, primary_key=True)
    education_activity_id = db.Column(
        db.Integer,
        db.ForeignKey("education_activity.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization_settings.id"),
        nullable=True,
        index=True,
    )
    alias = db.Column(db.String(300), nullable=False)
    normalized_alias = db.Column(db.String(300), nullable=False, index=True)
    source_module = db.Column(
        db.String(50),
        nullable=False,
        default="GENERAL",
        server_default="GENERAL",
        index=True,
    )
    source_system = db.Column(
        db.String(100),
        nullable=False,
        default="",
        server_default="",
    )
    valid_from = db.Column(db.Date, nullable=True)
    valid_to = db.Column(db.Date, nullable=True)
    confirmed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    match_priority = db.Column(
        db.SmallInteger,
        nullable=False,
        default=100,
        server_default="100",
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true(), index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    education_activity = db.relationship(
        "EducationActivity",
        backref=db.backref("aliases", lazy=True, cascade="all, delete-orphan"),
    )
    organization = db.relationship("OrganizationSettings", foreign_keys=[organization_id])
    confirmed_by = db.relationship("User", foreign_keys=[confirmed_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_education_activity_alias_valid_period",
        ),
        db.Index(
            "uq_education_activity_alias_global",
            "normalized_alias",
            "source_module",
            "source_system",
            unique=True,
            postgresql_where=db.text("organization_id IS NULL"),
            sqlite_where=db.text("organization_id IS NULL"),
        ),
        db.Index(
            "uq_education_activity_alias_local",
            "organization_id",
            "normalized_alias",
            "source_module",
            "source_system",
            unique=True,
            postgresql_where=db.text("organization_id IS NOT NULL"),
            sqlite_where=db.text("organization_id IS NOT NULL"),
        ),
    )


class EducationActivityDepartment(db.Model):
    __tablename__ = "education_activity_department"

    id = db.Column(db.Integer, primary_key=True)
    education_activity_id = db.Column(
        db.Integer,
        db.ForeignKey("education_activity.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("department.id"),
        nullable=False,
        index=True,
    )
    is_primary = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    valid_from = db.Column(db.Date, nullable=True)
    valid_to = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true(), index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    education_activity = db.relationship(
        "EducationActivity",
        backref=db.backref("department_links", lazy=True, cascade="all, delete-orphan"),
    )
    department = db.relationship("Department")

    __table_args__ = (
        db.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_education_activity_department_valid_period",
        ),
        db.UniqueConstraint(
            "education_activity_id",
            "department_id",
            "valid_from",
            name="uq_education_activity_department_period",
        ),
        db.Index(
            "uq_education_activity_department_default_period",
            "education_activity_id",
            "department_id",
            unique=True,
            postgresql_where=db.text("valid_from IS NULL"),
            sqlite_where=db.text("valid_from IS NULL"),
        ),
        db.Index(
            "uq_education_activity_department_current_primary",
            "education_activity_id",
            unique=True,
            postgresql_where=db.text(
                "is_primary AND is_active AND valid_to IS NULL"
            ),
            sqlite_where=db.text(
                "is_primary = 1 AND is_active = 1 AND valid_to IS NULL"
            ),
        ),
        db.Index(
            "ix_education_activity_department_period",
            "department_id",
            "valid_from",
            "valid_to",
        ),
    )


class ExternalActivityMappingLog(db.Model):
    __tablename__ = "external_activity_mapping_log"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization_settings.id"),
        nullable=True,
        index=True,
    )
    academic_year_id = db.Column(
        db.Integer,
        db.ForeignKey("academic_year.id"),
        nullable=True,
        index=True,
    )
    source_module = db.Column(db.String(50), nullable=False, index=True)
    source_system = db.Column(db.String(100), nullable=True)
    source_value = db.Column(db.String(500), nullable=False)
    normalized_value = db.Column(db.String(500), nullable=False, index=True)
    education_activity_id = db.Column(
        db.Integer,
        db.ForeignKey("education_activity.id"),
        nullable=True,
        index=True,
    )
    # The plan table is introduced at the next stage. Keep the future
    # identifier without a foreign key until that migration exists.
    education_plan_item_id = db.Column(db.Integer, nullable=True, index=True)
    mapping_method = db.Column(db.String(30), nullable=False, index=True)
    confidence = db.Column(db.Numeric(5, 4), nullable=True)
    import_batch_type = db.Column(db.String(50), nullable=True)
    import_batch_id = db.Column(db.BigInteger, nullable=True)
    confirmed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    organization = db.relationship("OrganizationSettings", foreign_keys=[organization_id])
    academic_year = db.relationship("AcademicYear")
    education_activity = db.relationship("EducationActivity")
    confirmed_by = db.relationship("User", foreign_keys=[confirmed_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "mapping_method IN ("
            "'CODE','CANONICAL_NAME','ALIAS','MANUAL','AMBIGUOUS','UNMATCHED'"
            ")",
            name="ck_external_activity_mapping_method",
        ),
        db.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_external_activity_mapping_confidence",
        ),
        db.Index(
            "ix_external_activity_mapping_source",
            "source_module",
            "source_system",
            "normalized_value",
        ),
    )


__all__ = [
    "ACTIVITY_KINDS",
    "ACTIVITY_KIND_LABELS",
    "EducationActivity",
    "EducationActivityAlias",
    "EducationActivityDepartment",
    "ExternalActivityMappingLog",
]
