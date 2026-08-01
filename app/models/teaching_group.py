from datetime import datetime

from app.core.extensions import db


POPULATION_SNAPSHOT_STATUSES = (
    "CURRENT",
    "SUPERSEDED",
    "LOCKED",
)

TEACHING_GROUP_TYPES = (
    "CLASS",
    "SUBGROUP",
    "METAGROUP",
    "EXTRACURRICULAR_GROUP",
    "ADDITIONAL_GROUP",
    "INDIVIDUAL",
)

TEACHING_GROUP_TYPE_LABELS = {
    "CLASS": "Целый класс",
    "SUBGROUP": "Подгруппа",
    "METAGROUP": "Метагруппа",
    "EXTRACURRICULAR_GROUP": "Внеурочная группа",
    "ADDITIONAL_GROUP": "Группа дополнительного образования",
    "INDIVIDUAL": "Индивидуальная группа",
}

TEACHING_GROUP_STATUSES = (
    "DRAFT",
    "READY",
    "CLOSED",
)

TEACHING_GROUP_STATUS_LABELS = {
    "DRAFT": "Черновик",
    "READY": "Готова",
    "CLOSED": "Закрыта",
}

GROUP_COMPOSITION_MODES = (
    "PERSONAL",
    "COUNT_ONLY",
)

GROUP_COMPOSITION_MODE_LABELS = {
    "PERSONAL": "Поимённый состав",
    "COUNT_ONLY": "Только численность",
}

GROUP_CLASS_RELATION_KINDS = (
    "FULL",
    "PARTIAL",
    "SOURCE",
)

GROUP_MEMBER_SOURCE_KINDS = (
    "MANUAL",
    "IMPORT",
    "AUTO",
)


class PopulationSnapshot(db.Model):
    __tablename__ = "population_snapshot"

    id = db.Column(db.Integer, primary_key=True)
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_no = db.Column(db.Integer, nullable=False)
    snapshot_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(
        db.String(30),
        nullable=False,
        default="CURRENT",
        server_default="CURRENT",
        index=True,
    )
    source_kind = db.Column(
        db.String(30),
        nullable=False,
        default="REGISTRY",
        server_default="REGISTRY",
    )
    checksum = db.Column(db.String(128), nullable=False)
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

    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref(
            "population_snapshots",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="PopulationSnapshot.revision_no",
        ),
    )
    created_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "revision_no > 0",
            name="ck_population_snapshot_revision",
        ),
        db.CheckConstraint(
            "status IN ('CURRENT','SUPERSEDED','LOCKED')",
            name="ck_population_snapshot_status",
        ),
        db.UniqueConstraint(
            "tariff_version_id",
            "revision_no",
            name="uq_population_snapshot_version_revision",
        ),
        db.Index(
            "uq_population_snapshot_current",
            "tariff_version_id",
            unique=True,
            postgresql_where=db.text("status = 'CURRENT'"),
            sqlite_where=db.text("status = 'CURRENT'"),
        ),
    )


class PopulationSnapshotClass(db.Model):
    __tablename__ = "population_snapshot_class"

    id = db.Column(db.Integer, primary_key=True)
    population_snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("population_snapshot.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_school_class_id = db.Column(
        db.Integer,
        db.ForeignKey("school_class.id"),
        nullable=False,
        index=True,
    )
    name_snapshot = db.Column(db.String(40), nullable=False)
    grade_snapshot = db.Column(db.SmallInteger, nullable=True, index=True)
    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id"),
        nullable=True,
        index=True,
    )
    building_name_snapshot = db.Column(db.String(255), nullable=True)
    student_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    population_snapshot = db.relationship(
        "PopulationSnapshot",
        backref=db.backref(
            "classes",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="PopulationSnapshotClass.grade_snapshot",
        ),
    )
    source_school_class = db.relationship("SchoolClass")
    building = db.relationship("Building")

    __table_args__ = (
        db.CheckConstraint(
            "student_count >= 0",
            name="ck_population_snapshot_class_count",
        ),
        db.UniqueConstraint(
            "population_snapshot_id",
            "source_school_class_id",
            name="uq_population_snapshot_source_class",
        ),
        db.Index(
            "ix_population_snapshot_class_grade_building",
            "population_snapshot_id",
            "grade_snapshot",
            "building_id",
        ),
    )


class PopulationSnapshotEnrollment(db.Model):
    __tablename__ = "population_snapshot_enrollment"

    id = db.Column(db.Integer, primary_key=True)
    population_snapshot_class_id = db.Column(
        db.Integer,
        db.ForeignKey("population_snapshot_class.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_child_id = db.Column(
        db.Integer,
        db.ForeignKey("child.id"),
        nullable=False,
        index=True,
    )
    source_enrollment_id = db.Column(
        db.Integer,
        db.ForeignKey("child_enrollment.id"),
        nullable=True,
        index=True,
    )
    fio_snapshot = db.Column(db.String(380), nullable=False)
    status_snapshot = db.Column(db.String(30), nullable=True)
    started_on = db.Column(db.Date, nullable=True)
    ended_on = db.Column(db.Date, nullable=True)

    population_snapshot_class = db.relationship(
        "PopulationSnapshotClass",
        backref=db.backref(
            "enrollments",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="PopulationSnapshotEnrollment.fio_snapshot",
        ),
    )
    source_child = db.relationship("Child")
    source_enrollment = db.relationship("ChildEnrollment")

    __table_args__ = (
        db.CheckConstraint(
            "ended_on IS NULL OR started_on IS NULL OR ended_on >= started_on",
            name="ck_population_snapshot_enrollment_period",
        ),
        db.UniqueConstraint(
            "population_snapshot_class_id",
            "source_child_id",
            name="uq_population_snapshot_class_child",
        ),
    )


class TeachingGroup(db.Model):
    __tablename__ = "teaching_group"

    id = db.Column(db.Integer, primary_key=True)
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    education_activity_id = db.Column(
        db.Integer,
        db.ForeignKey("education_activity.id"),
        nullable=False,
        index=True,
    )
    group_type = db.Column(db.String(40), nullable=False, index=True)
    code = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    composition_mode = db.Column(
        db.String(30),
        nullable=False,
        default="PERSONAL",
        server_default="PERSONAL",
    )
    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id"),
        nullable=True,
        index=True,
    )
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("department.id"),
        nullable=True,
        index=True,
    )
    planned_size = db.Column(db.Integer, nullable=True)
    actual_size = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    valid_from = db.Column(db.Date, nullable=False, index=True)
    valid_to = db.Column(db.Date, nullable=False, index=True)
    source_plan_line_id = db.Column(
        db.Integer,
        db.ForeignKey("education_plan_line.id"),
        nullable=False,
        index=True,
    )
    source_group_id = db.Column(
        db.Integer,
        db.ForeignKey("teaching_group.id"),
        nullable=True,
    )
    status = db.Column(
        db.String(30),
        nullable=False,
        default="DRAFT",
        server_default="DRAFT",
        index=True,
    )
    close_reason = db.Column(db.String(500), nullable=True)
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

    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref(
            "teaching_groups",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    education_activity = db.relationship("EducationActivity")
    building = db.relationship("Building")
    department = db.relationship("Department")
    source_plan_line = db.relationship("EducationPlanLine")
    source_group = db.relationship("TeachingGroup", remote_side=[id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "group_type IN ("
            "'CLASS','SUBGROUP','METAGROUP','EXTRACURRICULAR_GROUP',"
            "'ADDITIONAL_GROUP','INDIVIDUAL'"
            ")",
            name="ck_teaching_group_type",
        ),
        db.CheckConstraint(
            "composition_mode IN ('PERSONAL','COUNT_ONLY')",
            name="ck_teaching_group_composition",
        ),
        db.CheckConstraint(
            "status IN ('DRAFT','READY','CLOSED')",
            name="ck_teaching_group_status",
        ),
        db.CheckConstraint(
            "planned_size IS NULL OR planned_size >= 0",
            name="ck_teaching_group_planned_size",
        ),
        db.CheckConstraint(
            "actual_size >= 0",
            name="ck_teaching_group_actual_size",
        ),
        db.CheckConstraint(
            "valid_to >= valid_from",
            name="ck_teaching_group_period",
        ),
        db.CheckConstraint(
            "revision > 0",
            name="ck_teaching_group_revision",
        ),
        db.UniqueConstraint(
            "tariff_version_id",
            "code",
            name="uq_teaching_group_version_code",
        ),
        db.Index(
            "ix_teaching_group_version_activity",
            "tariff_version_id",
            "education_activity_id",
        ),
        db.Index(
            "ix_teaching_group_department_building",
            "department_id",
            "building_id",
        ),
    )


class TeachingGroupClass(db.Model):
    __tablename__ = "teaching_group_class"

    id = db.Column(db.Integer, primary_key=True)
    teaching_group_id = db.Column(
        db.Integer,
        db.ForeignKey("teaching_group.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    population_snapshot_class_id = db.Column(
        db.Integer,
        db.ForeignKey("population_snapshot_class.id"),
        nullable=False,
        index=True,
    )
    relation_kind = db.Column(
        db.String(30),
        nullable=False,
        default="SOURCE",
        server_default="SOURCE",
    )
    student_count = db.Column(db.Integer, nullable=True)

    teaching_group = db.relationship(
        "TeachingGroup",
        backref=db.backref(
            "source_classes",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    population_snapshot_class = db.relationship("PopulationSnapshotClass")

    __table_args__ = (
        db.CheckConstraint(
            "relation_kind IN ('FULL','PARTIAL','SOURCE')",
            name="ck_teaching_group_class_relation",
        ),
        db.CheckConstraint(
            "student_count IS NULL OR student_count >= 0",
            name="ck_teaching_group_class_count",
        ),
        db.UniqueConstraint(
            "teaching_group_id",
            "population_snapshot_class_id",
            name="uq_teaching_group_snapshot_class",
        ),
    )


class TeachingGroupMember(db.Model):
    __tablename__ = "teaching_group_member"

    id = db.Column(db.Integer, primary_key=True)
    teaching_group_id = db.Column(
        db.Integer,
        db.ForeignKey("teaching_group.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_enrollment_id = db.Column(
        db.Integer,
        db.ForeignKey("population_snapshot_enrollment.id"),
        nullable=False,
        index=True,
    )
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=False)
    source_kind = db.Column(
        db.String(30),
        nullable=False,
        default="MANUAL",
        server_default="MANUAL",
    )
    note = db.Column(db.String(500), nullable=True)

    teaching_group = db.relationship(
        "TeachingGroup",
        backref=db.backref(
            "members",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    snapshot_enrollment = db.relationship("PopulationSnapshotEnrollment")

    __table_args__ = (
        db.CheckConstraint(
            "valid_to >= valid_from",
            name="ck_teaching_group_member_period",
        ),
        db.CheckConstraint(
            "source_kind IN ('MANUAL','IMPORT','AUTO')",
            name="ck_teaching_group_member_source",
        ),
        db.UniqueConstraint(
            "teaching_group_id",
            "snapshot_enrollment_id",
            "valid_from",
            name="uq_teaching_group_member_period_start",
        ),
        db.Index(
            "ix_teaching_group_member_period",
            "teaching_group_id",
            "valid_from",
            "valid_to",
        ),
    )


class TeachingMetagroupSource(db.Model):
    __tablename__ = "teaching_metagroup_source"

    id = db.Column(db.Integer, primary_key=True)
    metagroup_id = db.Column(
        db.Integer,
        db.ForeignKey("teaching_group.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_group_id = db.Column(
        db.Integer,
        db.ForeignKey("teaching_group.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sort_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    metagroup = db.relationship(
        "TeachingGroup",
        foreign_keys=[metagroup_id],
        backref=db.backref(
            "metagroup_sources",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="TeachingMetagroupSource.sort_order",
        ),
    )
    source_group = db.relationship(
        "TeachingGroup",
        foreign_keys=[source_group_id],
        backref=db.backref(
            "metagroup_membership",
            lazy=True,
            uselist=False,
        ),
    )

    __table_args__ = (
        db.CheckConstraint(
            "metagroup_id <> source_group_id",
            name="ck_teaching_metagroup_distinct_source",
        ),
        db.CheckConstraint(
            "sort_order >= 0",
            name="ck_teaching_metagroup_source_order",
        ),
        db.UniqueConstraint(
            "metagroup_id",
            "source_group_id",
            name="uq_teaching_metagroup_source",
        ),
        db.UniqueConstraint(
            "source_group_id",
            name="uq_teaching_metagroup_single_membership",
        ),
    )


class TeachingGroupHistory(db.Model):
    __tablename__ = "teaching_group_history"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    teaching_group_id = db.Column(
        db.Integer,
        db.ForeignKey("teaching_group.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_code = db.Column(db.String(40), nullable=False, index=True)
    details = db.Column(db.Text(), nullable=True)
    changed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    changed_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    teaching_group = db.relationship(
        "TeachingGroup",
        backref=db.backref(
            "history",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="TeachingGroupHistory.changed_at",
        ),
    )
    changed_by = db.relationship("User")


__all__ = [
    "GROUP_CLASS_RELATION_KINDS",
    "GROUP_COMPOSITION_MODES",
    "GROUP_COMPOSITION_MODE_LABELS",
    "GROUP_MEMBER_SOURCE_KINDS",
    "POPULATION_SNAPSHOT_STATUSES",
    "PopulationSnapshot",
    "PopulationSnapshotClass",
    "PopulationSnapshotEnrollment",
    "TEACHING_GROUP_STATUSES",
    "TEACHING_GROUP_STATUS_LABELS",
    "TEACHING_GROUP_TYPES",
    "TEACHING_GROUP_TYPE_LABELS",
    "TeachingGroup",
    "TeachingGroupClass",
    "TeachingGroupHistory",
    "TeachingGroupMember",
    "TeachingMetagroupSource",
]
