from datetime import datetime
from decimal import Decimal

from app.core.extensions import db
from sqlalchemy.dialects.postgresql import JSONB


AUDIT_JSON_TYPE = db.JSON().with_variant(JSONB(), "postgresql")


WORKLOAD_NEED_KINDS = (
    "PLAN",
    "ADDITIONAL",
    "REPLACEMENT",
)

WORKLOAD_NEED_STATUSES = (
    "OPEN",
    "PARTIAL",
    "COVERED",
    "OVERALLOCATED",
    "CANCELLED",
)

WORKLOAD_NEED_STATUS_LABELS = {
    "OPEN": "Не распределено",
    "PARTIAL": "Распределено частично",
    "COVERED": "Распределено полностью",
    "OVERALLOCATED": "Распределено с превышением",
    "CANCELLED": "Отменено",
}

WORKLOAD_ASSIGNMENT_KINDS = (
    "MAIN",
    "SECONDARY",
    "INTERNAL_PART_TIME",
    "EXTERNAL_PART_TIME",
    "SUBSTITUTE",
    "VACANCY",
)

WORKLOAD_ASSIGNMENT_KIND_LABELS = {
    "MAIN": "Основная нагрузка",
    "SECONDARY": "Дополнительная нагрузка",
    "INTERNAL_PART_TIME": "Внутреннее совместительство",
    "EXTERNAL_PART_TIME": "Внешнее совместительство",
    "SUBSTITUTE": "Замещение",
    "VACANCY": "Вакансия",
}

WORKLOAD_ASSIGNMENT_STATUSES = (
    "DRAFT",
    "CONFIRMED",
    "CANCELLED",
)

WORKLOAD_ASSIGNMENT_STATUS_LABELS = {
    "DRAFT": "Черновик",
    "CONFIRMED": "Подтверждено",
    "CANCELLED": "Отменено",
}


class WorkloadNeed(db.Model):
    __tablename__ = "workload_need"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization_settings.id"),
        nullable=True,
        index=True,
    )
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    teaching_group_id = db.Column(
        db.Integer,
        db.ForeignKey("teaching_group.id"),
        nullable=True,
        index=True,
    )
    education_activity_id = db.Column(
        db.Integer,
        db.ForeignKey("education_activity.id"),
        nullable=False,
        index=True,
    )
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("department.id"),
        nullable=True,
        index=True,
    )
    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id"),
        nullable=True,
        index=True,
    )
    date_from = db.Column(db.Date, nullable=False, index=True)
    date_to = db.Column(db.Date, nullable=False, index=True)
    weekly_hours = db.Column(
        db.Numeric(8, 3),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    annual_hours = db.Column(
        db.Numeric(10, 3),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    need_kind = db.Column(
        db.String(30),
        nullable=False,
        default="PLAN",
        server_default="PLAN",
        index=True,
    )
    status = db.Column(
        db.String(30),
        nullable=False,
        default="OPEN",
        server_default="OPEN",
        index=True,
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

    organization = db.relationship("OrganizationSettings")
    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref(
            "workload_needs",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    teaching_group = db.relationship("TeachingGroup")
    education_activity = db.relationship("EducationActivity")
    department = db.relationship("Department")
    building = db.relationship("Building")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    @property
    def active_assignments(self):
        if self.id is None:
            return []
        return (
            WorkloadAssignment.query
            .filter(
                WorkloadAssignment.workload_need_id == self.id,
                WorkloadAssignment.status != "CANCELLED",
            )
            .all()
        )

    @property
    def allocated_weekly_hours(self):
        return sum(
            (
                item.weekly_hours or Decimal("0")
                for item in self.active_assignments
                if item.assignment_kind != "VACANCY"
            ),
            Decimal("0"),
        )

    @property
    def allocated_annual_hours(self):
        return sum(
            (
                item.annual_hours or Decimal("0")
                for item in self.active_assignments
                if item.assignment_kind != "VACANCY"
            ),
            Decimal("0"),
        )

    @property
    def remaining_weekly_hours(self):
        return (self.weekly_hours or Decimal("0")) - self.allocated_weekly_hours

    @property
    def remaining_annual_hours(self):
        return (self.annual_hours or Decimal("0")) - self.allocated_annual_hours

    __table_args__ = (
        db.CheckConstraint(
            "date_to >= date_from",
            name="ck_workload_need_period",
        ),
        db.CheckConstraint(
            "weekly_hours >= 0 AND annual_hours >= 0",
            name="ck_workload_need_hours",
        ),
        db.CheckConstraint(
            "need_kind IN ('PLAN','ADDITIONAL','REPLACEMENT')",
            name="ck_workload_need_kind",
        ),
        db.CheckConstraint(
            "status IN ("
            "'OPEN','PARTIAL','COVERED','OVERALLOCATED','CANCELLED'"
            ")",
            name="ck_workload_need_status",
        ),
        db.CheckConstraint(
            "revision > 0",
            name="ck_workload_need_revision",
        ),
        db.UniqueConstraint(
            "tariff_version_id",
            "teaching_group_id",
            "date_from",
            "date_to",
            "need_kind",
            name="uq_workload_need_group_period_kind",
        ),
        db.Index(
            "ix_workload_need_version_status_department",
            "tariff_version_id",
            "status",
            "department_id",
        ),
        db.Index(
            "ix_workload_need_activity_department",
            "education_activity_id",
            "department_id",
        ),
    )


class WorkloadNeedSource(db.Model):
    __tablename__ = "workload_need_source"

    id = db.Column(db.Integer, primary_key=True)
    workload_need_id = db.Column(
        db.Integer,
        db.ForeignKey("workload_need.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    education_plan_line_id = db.Column(
        db.Integer,
        db.ForeignKey("education_plan_line.id"),
        nullable=False,
        index=True,
    )
    source_weekly_hours = db.Column(db.Numeric(8, 3), nullable=False)
    source_annual_hours = db.Column(db.Numeric(10, 3), nullable=False)
    source_kind = db.Column(
        db.String(30),
        nullable=False,
        default="DIRECT",
        server_default="DIRECT",
    )

    workload_need = db.relationship(
        "WorkloadNeed",
        backref=db.backref(
            "sources",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    education_plan_line = db.relationship("EducationPlanLine")

    __table_args__ = (
        db.CheckConstraint(
            "source_weekly_hours >= 0 AND source_annual_hours >= 0",
            name="ck_workload_need_source_hours",
        ),
        db.CheckConstraint(
            "source_kind IN ('DIRECT','DIVISION','MERGE','MANUAL')",
            name="ck_workload_need_source_kind",
        ),
        db.UniqueConstraint(
            "workload_need_id",
            "education_plan_line_id",
            "source_kind",
            name="uq_workload_need_source_line_kind",
        ),
    )


class WorkloadAssignment(db.Model):
    __tablename__ = "workload_assignment"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization_settings.id"),
        nullable=True,
        index=True,
    )
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workload_need_id = db.Column(
        db.Integer,
        db.ForeignKey("workload_need.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True,
    )
    position_code = db.Column(
        db.String(80),
        nullable=False,
        default="TEACHER",
        server_default="TEACHER",
        index=True,
    )
    position_title = db.Column(db.String(180), nullable=True)
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("department.id"),
        nullable=True,
        index=True,
    )
    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id"),
        nullable=True,
        index=True,
    )
    assignment_kind = db.Column(db.String(30), nullable=False, index=True)
    date_from = db.Column(db.Date, nullable=False, index=True)
    date_to = db.Column(db.Date, nullable=False, index=True)
    weekly_hours = db.Column(db.Numeric(8, 3), nullable=False)
    annual_hours = db.Column(db.Numeric(10, 3), nullable=False)
    status = db.Column(
        db.String(30),
        nullable=False,
        default="DRAFT",
        server_default="DRAFT",
        index=True,
    )
    origin_assignment_id = db.Column(
        db.Integer,
        db.ForeignKey("workload_assignment.id"),
        nullable=True,
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

    organization = db.relationship("OrganizationSettings")
    tariff_version = db.relationship("TariffVersion")
    workload_need = db.relationship(
        "WorkloadNeed",
        backref=db.backref(
            "assignments",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="WorkloadAssignment.date_from",
        ),
    )
    employee = db.relationship(
        "User",
        foreign_keys=[employee_user_id],
    )
    department = db.relationship("Department")
    building = db.relationship("Building")
    origin_assignment = db.relationship(
        "WorkloadAssignment",
        remote_side=[id],
    )
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "date_to >= date_from",
            name="ck_workload_assignment_period",
        ),
        db.CheckConstraint(
            "weekly_hours >= 0 AND annual_hours >= 0",
            name="ck_workload_assignment_hours",
        ),
        db.CheckConstraint(
            "assignment_kind IN ("
            "'MAIN','SECONDARY','INTERNAL_PART_TIME',"
            "'EXTERNAL_PART_TIME','SUBSTITUTE','VACANCY'"
            ")",
            name="ck_workload_assignment_kind",
        ),
        db.CheckConstraint(
            "status IN ('DRAFT','CONFIRMED','CANCELLED')",
            name="ck_workload_assignment_status",
        ),
        db.CheckConstraint(
            "(assignment_kind = 'VACANCY' AND employee_user_id IS NULL) "
            "OR (assignment_kind <> 'VACANCY' "
            "AND employee_user_id IS NOT NULL)",
            name="ck_workload_assignment_employee",
        ),
        db.CheckConstraint(
            "revision > 0",
            name="ck_workload_assignment_revision",
        ),
        db.Index(
            "ix_workload_assignment_version_employee_status",
            "tariff_version_id",
            "employee_user_id",
            "status",
        ),
        db.Index(
            "ix_workload_assignment_need_status",
            "workload_need_id",
            "status",
        ),
        db.Index(
            "ix_workload_assignment_department_building",
            "department_id",
            "building_id",
        ),
    )


class WorkloadAssignmentChange(db.Model):
    __tablename__ = "workload_assignment_change"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    workload_assignment_id = db.Column(
        db.Integer,
        db.ForeignKey("workload_assignment.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    change_kind = db.Column(db.String(30), nullable=False, index=True)
    changed_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )
    changed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    before_data = db.Column(AUDIT_JSON_TYPE, nullable=True)
    after_data = db.Column(AUDIT_JSON_TYPE, nullable=True)
    reason = db.Column(db.String(500), nullable=True)

    workload_assignment = db.relationship(
        "WorkloadAssignment",
        backref=db.backref(
            "changes",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="WorkloadAssignmentChange.changed_at",
        ),
    )
    changed_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "change_kind IN ('CREATE','UPDATE','SPLIT','TRANSFER','CANCEL')",
            name="ck_workload_assignment_change_kind",
        ),
        db.Index(
            "ix_workload_assignment_change_assignment_time",
            "workload_assignment_id",
            "changed_at",
        ),
    )


__all__ = [
    "WORKLOAD_ASSIGNMENT_KINDS",
    "WORKLOAD_ASSIGNMENT_KIND_LABELS",
    "WORKLOAD_ASSIGNMENT_STATUSES",
    "WORKLOAD_ASSIGNMENT_STATUS_LABELS",
    "WORKLOAD_NEED_KINDS",
    "WORKLOAD_NEED_STATUSES",
    "WORKLOAD_NEED_STATUS_LABELS",
    "WorkloadAssignment",
    "WorkloadAssignmentChange",
    "WorkloadNeed",
    "WorkloadNeedSource",
]
