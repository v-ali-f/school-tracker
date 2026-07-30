from datetime import datetime
from decimal import Decimal

from sqlalchemy.dialects.postgresql import JSONB

from app.core.extensions import db


INTEGRATION_JSON_TYPE = db.JSON().with_variant(JSONB(), "postgresql")

WORKLOAD_SOURCE_MODES = ("LEGACY", "COMPARE", "INTERNAL")
WORKLOAD_SOURCE_MODE_LABELS = {
    "LEGACY": "Excel-источник",
    "COMPARE": "Параллельная сверка",
    "INTERNAL": "Утверждённая нагрузка",
}

RECONCILIATION_STATUSES = (
    "RUNNING",
    "PASSED",
    "FAILED",
    "TECHNICAL_ERROR",
)
RECONCILIATION_ITEM_STATUSES = (
    "MATCH",
    "HOURS_MISMATCH",
    "LEGACY_ONLY",
    "INTERNAL_ONLY",
    "UNMAPPED_ACTIVITY",
)


class WorkloadSourceSetting(db.Model):
    __tablename__ = "workload_source_setting"

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
    source_mode = db.Column(
        db.String(20),
        nullable=False,
        default="LEGACY",
        server_default="LEGACY",
        index=True,
    )
    selected_tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id"),
        nullable=True,
        index=True,
    )
    revision = db.Column(
        db.Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    change_reason = db.Column(db.String(500), nullable=True)
    changed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    changed_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    organization = db.relationship("OrganizationSettings")
    academic_year = db.relationship("AcademicYear")
    selected_tariff_version = db.relationship("TariffVersion")
    changed_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "source_mode IN ('LEGACY','COMPARE','INTERNAL')",
            name="ck_workload_source_setting_mode",
        ),
        db.CheckConstraint(
            "revision > 0",
            name="ck_workload_source_setting_revision",
        ),
        db.Index(
            "uq_workload_source_setting_global_year",
            "academic_year_id",
            unique=True,
            postgresql_where=db.text("organization_id IS NULL"),
            sqlite_where=db.text("organization_id IS NULL"),
        ),
        db.Index(
            "uq_workload_source_setting_local_year",
            "organization_id",
            "academic_year_id",
            unique=True,
            postgresql_where=db.text("organization_id IS NOT NULL"),
            sqlite_where=db.text("organization_id IS NOT NULL"),
        ),
    )


class WorkloadReconciliationRun(db.Model):
    __tablename__ = "workload_reconciliation_run"

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
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculation_run_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_calculation_run.id"),
        nullable=False,
        index=True,
    )
    run_no = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.String(30),
        nullable=False,
        default="RUNNING",
        server_default="RUNNING",
        index=True,
    )
    tolerance_hours = db.Column(
        db.Numeric(8, 3),
        nullable=False,
        default=Decimal("0.001"),
        server_default="0.001",
    )
    legacy_row_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    internal_row_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    matched_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    blocking_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    legacy_weekly_hours = db.Column(
        db.Numeric(12, 3),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    internal_weekly_hours = db.Column(
        db.Numeric(12, 3),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    summary_data = db.Column(INTEGRATION_JSON_TYPE, nullable=False, default=dict)
    error_text = db.Column(db.Text, nullable=True)
    started_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    finished_at = db.Column(db.DateTime, nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    organization = db.relationship("OrganizationSettings")
    academic_year = db.relationship("AcademicYear")
    tariff_version = db.relationship("TariffVersion")
    calculation_run = db.relationship("TariffCalculationRun")
    created_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('RUNNING','PASSED','FAILED','TECHNICAL_ERROR')",
            name="ck_workload_reconciliation_run_status",
        ),
        db.CheckConstraint(
            "run_no > 0 AND tolerance_hours >= 0",
            name="ck_workload_reconciliation_run_values",
        ),
        db.CheckConstraint(
            "legacy_row_count >= 0 AND internal_row_count >= 0 "
            "AND matched_count >= 0 AND blocking_count >= 0",
            name="ck_workload_reconciliation_run_counts",
        ),
        db.UniqueConstraint(
            "tariff_version_id",
            "run_no",
            name="uq_workload_reconciliation_run_version_number",
        ),
        db.Index(
            "ix_workload_reconciliation_year_status",
            "academic_year_id",
            "status",
        ),
    )


class WorkloadReconciliationItem(db.Model):
    __tablename__ = "workload_reconciliation_item"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    reconciliation_run_id = db.Column(
        db.Integer,
        db.ForeignKey("workload_reconciliation_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_key = db.Column(db.String(180), nullable=False)
    status = db.Column(db.String(30), nullable=False, index=True)
    employee_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
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
    subject_id = db.Column(
        db.Integer,
        db.ForeignKey("subject.id"),
        nullable=True,
        index=True,
    )
    education_activity_id = db.Column(
        db.Integer,
        db.ForeignKey("education_activity.id"),
        nullable=True,
        index=True,
    )
    legacy_weekly_hours = db.Column(
        db.Numeric(12, 3),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    internal_weekly_hours = db.Column(
        db.Numeric(12, 3),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    difference_hours = db.Column(
        db.Numeric(12, 3),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    details = db.Column(INTEGRATION_JSON_TYPE, nullable=True)

    reconciliation_run = db.relationship(
        "WorkloadReconciliationRun",
        backref=db.backref(
            "items",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="WorkloadReconciliationItem.id",
        ),
    )
    employee = db.relationship("User")
    department = db.relationship("Department")
    building = db.relationship("Building")
    subject = db.relationship("Subject")
    education_activity = db.relationship("EducationActivity")

    __table_args__ = (
        db.CheckConstraint(
            "status IN ("
            "'MATCH','HOURS_MISMATCH','LEGACY_ONLY','INTERNAL_ONLY',"
            "'UNMAPPED_ACTIVITY'"
            ")",
            name="ck_workload_reconciliation_item_status",
        ),
        db.UniqueConstraint(
            "reconciliation_run_id",
            "match_key",
            name="uq_workload_reconciliation_item_key",
        ),
        db.Index(
            "ix_workload_reconciliation_item_run_status",
            "reconciliation_run_id",
            "status",
        ),
    )


class WorkloadSourceTransition(db.Model):
    __tablename__ = "workload_source_transition"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    workload_source_setting_id = db.Column(
        db.Integer,
        db.ForeignKey("workload_source_setting.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reconciliation_run_id = db.Column(
        db.Integer,
        db.ForeignKey("workload_reconciliation_run.id"),
        nullable=True,
        index=True,
    )
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id"),
        nullable=True,
        index=True,
    )
    from_mode = db.Column(db.String(20), nullable=False)
    to_mode = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
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

    workload_source_setting = db.relationship(
        "WorkloadSourceSetting",
        backref=db.backref(
            "transitions",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="WorkloadSourceTransition.changed_at",
        ),
    )
    reconciliation_run = db.relationship("WorkloadReconciliationRun")
    tariff_version = db.relationship("TariffVersion")
    changed_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "from_mode IN ('LEGACY','COMPARE','INTERNAL') "
            "AND to_mode IN ('LEGACY','COMPARE','INTERNAL')",
            name="ck_workload_source_transition_modes",
        ),
    )


__all__ = [
    "RECONCILIATION_ITEM_STATUSES",
    "RECONCILIATION_STATUSES",
    "WORKLOAD_SOURCE_MODES",
    "WORKLOAD_SOURCE_MODE_LABELS",
    "WorkloadReconciliationItem",
    "WorkloadReconciliationRun",
    "WorkloadSourceSetting",
    "WorkloadSourceTransition",
]
